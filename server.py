"""
server.py
"""

import socket
import threading
import select
import time
from battleship import run_multiplayer_game_online
import struct
from protocol import Packet, PACKET_TYPES, next_sequence_num, safe_send, safe_recv

HOST = '127.0.0.1'
PORT = 5000

# Configuration
MAX_PLAYERS = 2  # Maximum players allowed in a game
MAX_SPECTATORS = 12  # Maximum number of spectators allowed (increased to accommodate waiting players)
GAME_START_DELAY = 8  # Seconds to wait after minimum players join before starting
INACTIVITY_TIMEOUT = 30  # Seconds before a player's turn is skipped
GAME_END_DELAY = 10  # Seconds to wait after game ends before starting new game
CONNECTION_TIMEOUT = 30  # Seconds before a connection is considered inactive

# Global variables to track connections and games
all_connections = []  # List of (conn, addr, rfile, wfile, player_num) for all connections
connection_lock = threading.Lock()
game_in_progress = False
game_in_progress_lock = threading.Lock()
game_ready_event = threading.Event()
countdown_timer_running = False
countdown_timer_lock = threading.Lock()
player_reconnecting = threading.Event()
player_reconnecting.set()

def get_active_players():
    """Get the first two players from all_connections."""
    return all_connections[:2]

def get_spectators():
    """Get all connections after the first two."""
    return all_connections[2:]

def cleanup_connection(conn, player_quit=False):
    """Clean up a connection and its associated resources."""
    with connection_lock:
        for conn_list in [all_connections]:
            for i, (c, _, rfile, wfile, *_) in enumerate(conn_list):
                if c == conn:
                    try:
                        rfile.close()
                    except:
                        pass
                    try:
                        wfile.close()
                    except:
                        pass
                    conn_list.pop(i)
                    break
    try:
        conn.close()
    except:
        pass

def handle_p1_quit(conn):
    with connection_lock:
        # Remove P1 (index 0)
        print(f"[INFO] Player 1 quit.\n\n")
        all_connections.pop(0)
        
        # Reset game state
        game_ready_event.clear()
        
        # Clear the connection list
        all_connections.clear()

    try:
        conn.close()
    except:
        pass

def reconnect_player(conn, addr):
    """replace the disconnected player with a new connection."""
    global all_connections, player_reconnecting
    # Find the first available slot for the new connection
    for i in range(len(all_connections)):
        if all_connections[i] is None:
            all_connections[i] = (conn, addr, conn.makefile('rb'), conn.makefile('wb'), i + 1)
            return
    else:
        # No available slot, append to the list
        print(f"[INFO] No available slot for reconnection.\n")
    
    # Notify the player about their new position
    _, _, rfile, wfile, num = all_connections[i]
    safe_send(wfile, rfile, f"[INFO] Welcome back! You are Player {num}.\n\n")
    player_reconnecting.set()

def wait_for_player_reconnect(disconnected_index):
    """Wait for a player to reconnect after disconnection."""
    global all_connections, player_reconnecting, game_in_progress

    if game_in_progress:
        print(f"[INFO] Game is in progress. Attempting Reconnection.\n")
        start_time = time.time()

        print(f"[INFO] Waiting for Player {disconnected_index + 1} to reconnect...\n")
        # Wait for a maximum of CONNECTION_TIMEOUT seconds
        while time.time() < start_time + CONNECTION_TIMEOUT:
            if all_connections[disconnected_index] is not None:
                # Player has reconnected
                print(f"[INFO] Player {disconnected_index + 1} has reconnected.\n")
                player_reconnecting.set()
                return True
            time.sleep(1)
        else:
            # Timeout reached, player did not reconnect
            print(f"[INFO] Player {disconnected_index + 1} did not reconnect in time.\n")
            # Handle disconnection
            with connection_lock:
                all_connections[disconnected_index] = None
                player_reconnecting.clear()
                game_in_progress = False  # <-- Add this line to end the game
                print(f"[INFO] Player {disconnected_index + 1} has been removed from the game.\n")
                # Notify all players and spectators
                for entry in all_connections:
                    if entry is not None:
                        _, _, rfile, wfile, num = entry
                        safe_send(wfile, rfile, "[INFO] Game ended due to player disconnect. Waiting for next game...\n\n")
                return False
    else:
        print(f"[INFO] Game is not in progress. No need to wait for reconnection.\n")
        player_reconnecting.clear()
        return False

def check_all_connections(check_index=None):
    """Check all connections in the server and handle disconnections appropriately.
    If check_index is provided, only check that specific index."""
    global all_connections, player_reconnecting
    # First, check connections without holding the lock
    disconnected_indices = []
    print(f"[DEBUG] Starting connection check.")
    
    # Determine which indices to check
    if check_index is not None:
        indices_to_check = [check_index]
    else:
        indices_to_check = range(len(all_connections))
    
    for i in indices_to_check:
        if all_connections[i] is not None:
            try:
                conn, addr, rfile, wfile, num = all_connections[i]
                print(f"[DEBUG] Checking connection {num} at index {i}")
                
                # Use select with a very short timeout to check if socket is readable
                readable, _, _ = select.select([conn], [], [], 0)
                if readable:
                    try:
                        # Try to peek at the socket without consuming data
                        data = conn.recv(1, socket.MSG_PEEK)
                        if not data:  # Empty data means connection closed
                            print(f"[DEBUG] Connection {num} at index {i} is disconnected (empty data)")
                            raise ConnectionResetError()
                    except BlockingIOError:
                        # Socket would block - this is normal for non-blocking sockets
                        # and doesn't indicate a disconnection
                        pass
                    except (ConnectionResetError, OSError) as e:
                        print(f"[DEBUG] Exception caught for connection {num} at index {i}: {str(e)}")
                        disconnected_indices.append((i, num))
            except (ConnectionResetError, OSError) as e:
                print(f"[DEBUG] Exception caught for connection {num} at index {i}: {str(e)}")
                disconnected_indices.append((i, num))
    
    print(f"[DEBUG] Found {len(disconnected_indices)} disconnected connections")
    
    # Handle disconnections if any found
    if disconnected_indices:
        for i, num in disconnected_indices:
            if num <= MAX_PLAYERS:  # This is a player
                # Set their data to None instead of removing
                all_connections[i] = None
                player_reconnecting.clear()
                print(f"[INFO] Player {num} disconnected. Game will be paused.\n")
                # Wait for player to reconnect
                if game_in_progress:
                    if wait_for_player_reconnect(i):
                        print(f"[DEBUG] a player reconnection detected in check_all_connections")
                        # Player reconnected, resume game
                        return False

            else:  # This is a spectator
                # Remove spectator from list
                all_connections.pop(i)
                # Update remaining spectator numbers
                spectator_count = 0
                for j in range(MAX_PLAYERS, len(all_connections)):
                    if all_connections[j] is not None:
                        spectator_count += 1
                        conn, addr, rfile, wfile, _ = all_connections[j]
                        all_connections[j] = (conn, addr, rfile, wfile, MAX_PLAYERS + spectator_count)
                        safe_send(wfile, rfile, f"[INFO] You are now Spectator {spectator_count}.\n\n")
                print(f"[INFO] Spectator {num - MAX_PLAYERS} disconnected.\n")
        # Clear the list after processing
        disconnected_indices.clear()
        print(f"[DEBUG] a player disconnection detected in check_all_connections")
        return True
    print(f"[DEBUG] No disconnections detected in check_all_connections")
    return False

def monitor_connections():
    """Monitor all connections and check for disconnections."""
    global all_connections, player_reconnecting
    while True:
        with connection_lock:
            # Check all connections
            check_all_connections()
        time.sleep(1)  # Sleep for a short duration before checking again

def handle_client(conn, addr):
    """Handle a client connection by adding it to the appropriate list."""
    global game_in_progress, all_connections, countdown_timer_running
    
    print(f"[INFO] New connection from {addr}\n")
    
    try:
        with connection_lock:
            if len(all_connections) >= MAX_PLAYERS + MAX_SPECTATORS:
                # Too many total connections
                wfile = conn.makefile('wb')
                rfile = conn.makefile('rb')
                safe_send(wfile, rfile, f"[INFO] Sorry, the server has reached the maximum number of connections ({MAX_PLAYERS + MAX_SPECTATORS}). Please try again later.\n\n")
                wfile.close()
                rfile.close()
                conn.close()
                return
            
            # Wrap the connection with file handlers
            rfile = conn.makefile('rb')
            wfile = conn.makefile('wb')
            
            # Add to main list, reusing None slots if available
            connection_num = None
            for i in range(len(all_connections)):
                if all_connections[i] is None:
                    connection_num = i + 1
                    all_connections[i] = (conn, addr, rfile, wfile, connection_num)
                    break
            if connection_num is None:
                connection_num = len(all_connections) + 1
                all_connections.append((conn, addr, rfile, wfile, connection_num))

            # Determine if they're an active player or spectator
            if connection_num <= MAX_PLAYERS and not game_in_progress:
                safe_send(wfile, rfile, f"[INFO] Welcome! You are Player {connection_num}.\n")
                if connection_num < MAX_PLAYERS:
                    safe_send(wfile, rfile, f"[INFO] Waiting for opponent to connect...\n")
            else:
                if game_in_progress and not player_reconnecting.is_set():
                    # If game is in progress and player reconnects
                    safe_send(wfile, rfile, f"[INFO] Welcome back! You are Player {connection_num}.\n")
                    player_reconnecting.set()
                else:
                    safe_send(wfile, rfile, f"[INFO] Welcome! You are Spectator {connection_num - MAX_PLAYERS}.\n")
                if game_in_progress:
                    safe_send(wfile, rfile, f"[INFO] Current game in progress. You will receive game updates.\n")
                else:
                    safe_send(wfile, rfile, f"[INFO] Waiting for game to start. You will be notified when it begins.\n")
            
            safe_send(wfile, rfile, "[TIP] Type 'quit' to exit.\n\n")
            
            # Notify all connected clients
            for c, _, rf, wf, _ in all_connections:
                if c != conn:
                    safe_send(wf, rf, f"[INFO] New connection from {addr[0]}:{addr[1]}. ({len(all_connections)}/{MAX_PLAYERS + MAX_SPECTATORS} total connections)\n")
            
            # Check if ready to start countdown
            if len(get_active_players()) == MAX_PLAYERS and not game_in_progress:
                with countdown_timer_lock:
                    if not countdown_timer_running:
                        countdown_timer_running = True
                        for _, _, rf, wf, _ in all_connections:
                            safe_send(wf, rf, f"[INFO] Both players connected! Game will start in {GAME_START_DELAY} seconds.\n")
                        
                        # Start countdown thread
                        start_timer_thread = threading.Thread(target=start_game_countdown)
                        start_timer_thread.daemon = True
                        start_timer_thread.start()

    except Exception as e:
        print(f"[ERROR] Connection setup error: {e}\n\n")
        cleanup_connection(conn)
        return

    try:
        # Main loop while waiting for game to start
        waiting_for_game = True
        while waiting_for_game and not game_in_progress:
            ready, _, _ = select.select([conn], [], [], 0.5)
            if ready:
                cmd = rfile.readline().strip().upper()
                if cmd == 'QUIT':
                    print(f"[INFO] {addr} has quit.\n\n")
                    handle_p1_quit(conn)
                    return
            
            if game_ready_event.is_set():
                waiting_for_game = False

    except Exception as e:
        print(f"[INFO] {addr} disconnected while waiting: {e}\n\n")
        handle_p1_quit(conn)
        return

def start_game_countdown():
    """Start a countdown timer before the game begins."""
    global game_in_progress, countdown_timer_running
    
    try:
        for i in range(GAME_START_DELAY, 0, -1):
            if i % 5 == 0 or i <= 3:
            # Wait until next announcement
            # Send countdown message to all players
                with connection_lock:
                    for _, _, rf, wf, _ in all_connections:
                        safe_send(wf, rf, f"[INFO] Game starting in {i} seconds...\n\n")
            time.sleep(1)
        
        with game_in_progress_lock:
            game_in_progress = True
            game_ready_event.set()
            countdown_timer_running = False
        
        # Notify all players that the game is starting
        with connection_lock:
            for _, _, rf, wf, num in all_connections:
                if num <= MAX_PLAYERS:
                    safe_send(wf, rf, f"[INFO] Game is starting! You are Player {num}.\n\n")
                else:
                    safe_send(wf, rf, f"[INFO] Game is starting! You are Spectator {num - MAX_PLAYERS}.\n\n")

        print(f"[DEBUG] monitor connections thread started")
        # start check connections thread
        check_connections_thread = threading.Thread(target=monitor_connections)
        check_connections_thread.daemon = True
        check_connections_thread.start()

        run_multiplayer_game_online(player_reconnecting, all_connections)

        print(f"[DEBUG] Game finished")

        # After game ends, notify all players
        with connection_lock:
            for _, _, rf, wf, num in all_connections:
                if num <= MAX_PLAYERS:
                    safe_send(wf, rf, f"[INFO] Game has ended. You were Player {num}.\n\n[INFO] Next game will start after the {GAME_START_DELAY} second timer ends\n\n")
                else:
                    safe_send(wf, rf, f"[INFO] Game has ended. You were Spectator {num - MAX_PLAYERS}.\n\n[INFO] Next game will start after the {GAME_START_DELAY} second timer ends\n\n")
        
        # Wait before starting new game
        time.sleep(GAME_END_DELAY)
        print(f"[DEBUG] sleep timer is up")
        # Reset game state
        with game_in_progress_lock:
            game_in_progress = False
        print(f"[DEBUG] resetted game_in_progress to false")
        # Handle next game players
        with connection_lock:
            print(f"[DEBUG] connection lock is locked")
            # Check and remove disconnected players
            for i in range(MAX_PLAYERS):  # Only check first two indices
                if all_connections[i] is not None:  # Only check if connection exists
                    if check_all_connections(i):  # Check specific index
                        print(f"[INFO] Connection {i} has disconnected.\n")
            
            # Handle player 2 position
            if all_connections[0] is None:  # If P1 left
                # Move P2 to P1 position
                all_connections[0] = all_connections[1]
                all_connections[1] = None
                # Notify the player about their new position
                _, _, rfile, wfile, _ = all_connections[0]
                safe_send(wfile, rfile, f"[INFO] You will be Player 1 in the next game!\n\n")
                print(f"[DEBUG] moved P2 to P1 position")
            
            # Promote spectators to fill vacant player slots
            vacant_slots = [i for i in range(MAX_PLAYERS) if all_connections[i] is None]
            print(f"[DEBUG] vacant_slots: {vacant_slots}")
            if vacant_slots:  # If we have any vacant player slots
                # Find the first spectators to promote
                for slot in vacant_slots:
                    # Look for the first spectator (index >= MAX_PLAYERS)
                    for i in range(MAX_PLAYERS, len(all_connections)):
                        if all_connections[i] is not None:
                            # Move this spectator to the vacant player slot
                            all_connections[slot] = all_connections[i]
                            all_connections.pop(i)
                            # Notify the promoted spectator
                            _, _, rfile_, wfile, _ = all_connections[slot]
                            safe_send(wfile, rfile, f"[INFO] You have been promoted to Player {slot + 1} for the next game!\n\n")
                            break
            
            # Update remaining spectator positions
            spectator_count = 0
            for i in range(MAX_PLAYERS, len(all_connections)):
                if all_connections[i] is not None:
                    spectator_count += 1
                    conn, addr, rfile, wfile, _ = all_connections[i]
                    all_connections[i] = (conn, addr, rfile, wfile, MAX_PLAYERS + spectator_count)
                    safe_send(wfile, rfile, f"[INFO] You are now Spectator {spectator_count}.\n\n")
            
            # Update player numbers
            for i in range(len(all_connections)):
                if all_connections[i] is not None:  # Only update if connection exists
                    conn, addr, rfile, wfile, _ = all_connections[i]
                    all_connections[i] = (conn, addr, rfile, wfile, i + 1)
                    if i < MAX_PLAYERS:
                        safe_send(wfile, rfile, f"[INFO] You will be Player {i + 1} in the next game!\n\n")
                    else:
                        safe_send(wfile, rfile, f"[INFO] You are Spectator {i - MAX_PLAYERS + 1}.\n\n")

        print(f"[DEBUG] Number of connections: {len(all_connections)}")
        print(f"[DEBUG] Countdown timer running: {countdown_timer_running}")

        # Start countdown for next game if we have enough players
        if len(get_active_players()) == MAX_PLAYERS:
            print("[DEBUG] Attempting to start next game countdown")
            with countdown_timer_lock:
                if not countdown_timer_running:
                    print("[DEBUG] Starting new countdown thread")
                    countdown_timer_running = True
                    start_timer_thread = threading.Thread(target=start_game_countdown)
                    start_timer_thread.daemon = True
                    start_timer_thread.start()
                    print("[DEBUG] Countdown thread started")
                else:
                    print("[DEBUG] Countdown already running")

        else:
            print("[DEBUG] Not enough players for next game")
            for _, _, rfile, wfile, _ in get_spectators():
                safe_send(wfile, rfile, "[INFO] Waiting for more players to join before starting next game...\n\n")
    
    except Exception as e:
        print(f"[ERROR] Error in game countdown: {e}\n")
    finally:
        print("[DEBUG] Resetting countdown timer flag")
        with countdown_timer_lock:
            countdown_timer_running = False

def main():
    print(f"[INFO] Server listening on {HOST}:{PORT}\n")
    print(f"[INFO] Waiting for {MAX_SPECTATORS} players to connect...\n")
    
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
        # Set socket options to allow reuse of address
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((HOST, PORT))
        server_socket.listen(MAX_PLAYERS + MAX_SPECTATORS)
        
        # Set socket to non-blocking mode
        server_socket.setblocking(False)
        
        try:
            while True:
                try:
                    # Try to accept a new connection with a timeout
                    conn, addr = server_socket.accept()
                    
                    if not player_reconnecting.is_set() and game_in_progress:
                        # If a player is reconnecting, wait for them to finish
                        print(f"[INFO] Player {addr} is reconnecting...\n")
                        reconnect_player(conn, addr)
                    else:
                        # Start a new thread to handle this client
                        client_thread = threading.Thread(target=handle_client, args=(conn, addr))
                        client_thread.daemon = True
                        client_thread.start()
                except BlockingIOError:
                    # No connection available, sleep briefly to prevent CPU spinning
                    time.sleep(0.1)
                    continue
                    
        except KeyboardInterrupt:
            print("\n[INFO] Server shutting down...\n")
            # Notify all connected players
            with connection_lock:
                for _, _, _, wfile, _ in all_connections:
                    try:
                        wfile.write(b"[INFO] Server is shutting down. Disconnecting all players.\n\n")
                        wfile.flush()
                    except:
                        pass
                # Close all connections
                for conn, _, rfile, wfile, _ in all_connections:
                    try:
                        rfile.close()
                    except:
                        pass
                    try:
                        wfile.close()
                    except:
                        pass
                    try:
                        conn.close()
                    except:
                        pass
                all_connections.clear()
            print("[INFO] All connections closed. Server shutdown complete.\n")
        except Exception as e:
            print(f"[ERROR] Server error: {e}\n")

if __name__ == "__main__":
    main()