"""
server.py
"""

import socket
import threading
import select
import time
from battleship import run_multiplayer_game_online

HOST = '127.0.0.1'
PORT = 5000

# Configuration
MIN_PLAYERS = 2  # Minimum players needed to start a game
MAX_PLAYERS = 2  # Maximum players allowed in a game
MAX_WAITING = 4  # Maximum number of players in waiting lobby
GAME_START_DELAY = 3  # Seconds to wait after minimum players join before starting
INACTIVITY_TIMEOUT = 30  # Seconds before a player's turn is skipped
GAME_END_DELAY = 5  # Seconds to wait after game ends before starting new game

# Global variables to track connections and games
active_player_connections = []  # List of (conn, addr, rfile, wfile, player_num) for active players
waiting_player_connections = []  # List of (conn, addr, rfile, wfile, player_num) for waiting players
connection_lock = threading.Lock()
game_in_progress = False
game_in_progress_lock = threading.Lock()
game_ready_event = threading.Event()
countdown_timer_running = False
countdown_timer_lock = threading.Lock()

def cleanup_connection(conn, player_quit=False):
    """Clean up a connection and its associated resources."""
    with connection_lock:
        for conn_list in [active_player_connections, waiting_player_connections]:
            for i, (c, _, rfile, wfile, _) in enumerate(conn_list):
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

def handle_quit(conn):
    """Handle client quitting while waiting."""
    with connection_lock:
        removed_from_active = False
        for i, (c, _, rfile, wfile, num) in enumerate(active_player_connections):
            if c == conn:
                print(f"[INFO] Active Player {num} quit.\n\n")
                active_player_connections.pop(i)
                removed_from_active = True
                break
        
        if not removed_from_active:
            for i, (c, _, rfile, wfile, num) in enumerate(waiting_player_connections):
                if c == conn:
                    print(f"[INFO] Waiting Player {num} quit.\n\n")
                    waiting_player_connections.pop(i)
                    break
        
        if removed_from_active:
            game_ready_event.clear()
            for _, _, _, wf, _ in active_player_connections + waiting_player_connections:
                safe_send(wf, "[INFO] A player left. Game start cancelled.\n\n")
                safe_send(wf, "[INFO] Disconnecting all connections. Please reconnect.\n\n")

            # Close all
            connections_to_close = active_player_connections + waiting_player_connections
            active_player_connections.clear()
            waiting_player_connections.clear()
            
            for c, _, rfile, wfile, _ in connections_to_close:
                try:
                    rfile.close()
                except:
                    pass
                try:
                    wfile.close()
                except:
                    pass
                try:
                    c.close()
                except:
                    pass

    try:
        conn.close()
    except:
        pass

def safe_send(wfile, message):
    """Safely send a message to a client."""
    try:
        wfile.write(message)
        wfile.flush()
    except:
        pass

def handle_client(conn, addr):
    """Handle a client connection by adding it to the appropriate list."""
    global game_in_progress, active_player_connections, waiting_player_connections, countdown_timer_running
    
    print(f"[INFO] New connection from {addr}\n")
    
    try:
        with connection_lock:
            if len(active_player_connections) + len(waiting_player_connections) >= MAX_PLAYERS + MAX_WAITING:
                # Too many total connections
                wfile = conn.makefile('w')
                safe_send(wfile, f"[INFO] Sorry, the server has reached the maximum number of connections ({MAX_PLAYERS + MAX_WAITING}). Please try again later.\n\n")
                wfile.close()
                conn.close()
                return
            
            # Wrap the connection with file handlers
            rfile = conn.makefile('r')
            wfile = conn.makefile('w')
            
            is_active_player = len(active_player_connections) < MAX_PLAYERS and not game_in_progress
            if is_active_player:
                player_num = len(active_player_connections) + 1
                active_player_connections.append((conn, addr, rfile, wfile, player_num))
                safe_send(wfile, f"[INFO] Welcome! You are Active Player {player_num}.\n\n")
                
                if player_num < MIN_PLAYERS:
                    safe_send(wfile, f"[INFO] Waiting for Player {MIN_PLAYERS} to connect...\n\n")
            else:
                # Add to waiting lobby
                waiting_num = len(waiting_player_connections) + 1
                waiting_player_connections.append((conn, addr, rfile, wfile, waiting_num))
                safe_send(wfile, f"[INFO] Welcome! You are in the waiting lobby (position {waiting_num}).\n\n")
                safe_send(wfile, f"[INFO] Current game in progress. You will be notified when it ends.\n\n")
            
            safe_send(wfile, "[TIP] Type 'quit' to exit.\n\n")
            
            # Notify other clients
            total_connected = len(active_player_connections) + len(waiting_player_connections)
            connection_type = "Active Player" if is_active_player else "Waiting Player"
            connection_num = player_num if is_active_player else waiting_num

            for c, _, _, wf, _ in active_player_connections + waiting_player_connections:
                if c != conn:
                    safe_send(wf, f"[INFO] {connection_type} {connection_num} has joined. ({total_connected}/{MAX_PLAYERS + MAX_WAITING} total connections)\n\n")
            
            # Check if ready to start countdown
            if len(active_player_connections) == MIN_PLAYERS and not game_in_progress:
                with countdown_timer_lock:
                    if not countdown_timer_running:
                        countdown_timer_running = True
                        for _, _, _, wf, _ in active_player_connections + waiting_player_connections:
                            safe_send(wf, f"[INFO] Both players connected! Game will start in {GAME_START_DELAY} seconds.\n\n")
                        
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
                    handle_quit(conn)
                    return
            
            if game_ready_event.is_set():
                waiting_for_game = False

    except Exception as e:
        print(f"[INFO] {addr} disconnected while waiting: {e}\n\n")
        handle_quit(conn)
        return

def start_game_countdown():
    """Start a countdown timer before the game begins."""
    global game_in_progress, countdown_timer_running
    
    try:
        # Wait for the specified delay
        time.sleep(GAME_START_DELAY)
        
        with game_in_progress_lock:
            if not game_in_progress:
                game_in_progress = True
                game_ready_event.set()
                
                # Notify all players that the game is starting
                with connection_lock:
                    for _, _, _, wfile, _ in active_player_connections + waiting_player_connections:
                        safe_send(wfile, "[INFO] Game is starting!\n\n")
                
                # Start the game
                player_rfiles = [rfile for _, _, rfile, _, _ in active_player_connections]
                player_wfiles = [wfile for _, _, _, wfile, _ in active_player_connections]
                run_multiplayer_game_online(player_rfiles, player_wfiles)
                
                # After game ends, notify all players
                with connection_lock:
                    for _, _, _, wfile, _ in active_player_connections + waiting_player_connections:
                        safe_send(wfile, "[INFO] Game has ended. Waiting for new game to start...\n\n")
                
                # Wait before starting new game
                time.sleep(GAME_END_DELAY)
                
                # Reset game state
                with game_in_progress_lock:
                    game_in_progress = False
                
                # Move waiting players to active if possible
                with connection_lock:
                    # First, clear active players list
                    active_player_connections.clear()
                    
                    # Then add waiting players to active
                    while len(active_player_connections) < MAX_PLAYERS and waiting_player_connections:
                        player = waiting_player_connections.pop(0)
                        active_player_connections.append(player)
                        _, _, _, wfile, num = player
                        safe_send(wfile, f"[INFO] You are now Active Player {len(active_player_connections)}.\n\n")
                
                # Start new game if we have enough players
                if len(active_player_connections) == MIN_PLAYERS:
                    with countdown_timer_lock:
                        if not countdown_timer_running:
                            countdown_timer_running = True
                            for _, _, _, wf, _ in active_player_connections + waiting_player_connections:
                                safe_send(wf, f"[INFO] New game starting in {GAME_START_DELAY} seconds!\n\n")
                            
                            # Start countdown thread
                            start_timer_thread = threading.Thread(target=start_game_countdown)
                            start_timer_thread.daemon = True
                            start_timer_thread.start()
    
    except Exception as e:
        print(f"[ERROR] Countdown error: {e}\n")
    finally:
        countdown_timer_running = False

def main():
    print(f"[INFO] Server listening on {HOST}:{PORT}\n")
    print(f"[INFO] Waiting for {MIN_PLAYERS} players to connect...\n")
    
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
        # Set socket options to allow reuse of address
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((HOST, PORT))
        server_socket.listen(MAX_PLAYERS + MAX_WAITING)
        
        # Set socket to non-blocking mode
        server_socket.setblocking(False)
        
        try:
            while True:
                try:
                    # Try to accept a new connection with a timeout
                    conn, addr = server_socket.accept()
                    
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
                for _, _, _, wfile, _ in active_player_connections + waiting_player_connections:
                    try:
                        wfile.write("[INFO] Server is shutting down. Disconnecting all players.\n\n")
                        wfile.flush()
                    except:
                        pass
                # Close all connections
                for conn, _, rfile, wfile, _ in active_player_connections + waiting_player_connections:
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
                active_player_connections.clear()
                waiting_player_connections.clear()
            print("[INFO] All connections closed. Server shutdown complete.\n")
        except Exception as e:
            print(f"[ERROR] Server error: {e}\n")

if __name__ == "__main__":
    main()