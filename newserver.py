# server.py
# Game logic is handled entirely on the server using battleship.py.
# First 2 clients are active players, others are spectators.

import socket
import threading
import select
import time
from newbattleship import run_multiplayer_game_online

HOST = '127.0.0.1'
PORT = 5000

# Configuration
ACTIVE_PLAYERS = 2  # Exactly 2 active players needed
MAX_CONNECTIONS = 8  # Maximum total connections (players + spectators)
GAME_START_DELAY = 8  # Seconds to wait after active players join before starting

# Global variables to track connections
active_player_connections = []  # List of active players (max 2)
spectator_connections = []      # List of spectators
connection_lock = threading.Lock()
game_in_progress = False
game_in_progress_lock = threading.Lock()
game_ready_event = threading.Event()
countdown_timer_running = False
countdown_timer_lock = threading.Lock()

def handle_client(conn, addr):
    # Handle a client connection by adding it to the appropriate connection list.
    global game_in_progress, active_player_connections, spectator_connections, countdown_timer_running
    
    print(f"[INFO] New connection from {addr}\n")
    
    try:
        with connection_lock:
            if game_in_progress:
                # Game already in progress, reject connection
                reject_file = conn.makefile('w')
                reject_file.write("[INFO] Sorry, a game is already in progress. Please try again later.\n\n")
                reject_file.flush()
                conn.close()
                return
            
            if len(active_player_connections) + len(spectator_connections) >= MAX_CONNECTIONS:
                # Too many connections, reject connection
                reject_file = conn.makefile('w')
                reject_file.write(f"[INFO] Sorry, the server has reached the maximum number of connections ({MAX_CONNECTIONS}). Please try again later.\n\n")
                reject_file.flush()
                conn.close()
                return
            
            # Setup file handlers for the connection
            rfile = conn.makefile('r')
            wfile = conn.makefile('w')
            
            # Determine if this is an active player or spectator
            is_active_player = len(active_player_connections) < ACTIVE_PLAYERS
            
            if is_active_player:
                # Active player - gets to play the game
                player_num = len(active_player_connections) + 1
                active_player_connections.append((conn, addr, rfile, wfile, player_num))
                wfile.write(f"[INFO] Welcome! You are Active Player {player_num}.\n\n")
                
                if player_num < ACTIVE_PLAYERS:
                    wfile.write(f"[INFO] Waiting for Player 2 to connect...\n\n")
            else:
                # Spectator - can only watch
                spectator_num = len(spectator_connections) + 1
                spectator_connections.append((conn, addr, rfile, wfile, spectator_num))
                wfile.write(f"[INFO] Welcome! You are Spectator {spectator_num}.\n\n")
                wfile.write(f"[INFO] Active players: {len(active_player_connections)}/{ACTIVE_PLAYERS}. You will be able to watch the game but not participate.\n\n")
            
            wfile.write("[TIP] Type 'quit' to exit.\n\n")
            wfile.flush()
            
            # Notify all other clients about the new connection
            total_connected = len(active_player_connections) + len(spectator_connections)
            connection_type = "Active Player" if is_active_player else "Spectator"
            connection_num = player_num if is_active_player else spectator_num
            
            for c, _, _, wf, _ in active_player_connections + spectator_connections:
                if c != conn:
                    try:
                        wf.write(f"[INFO] {connection_type} {connection_num} has joined. ({total_connected}/{MAX_CONNECTIONS} total connections)\n\n")
                        wf.flush()
                    except:
                        pass
            
            # Check if we have both active players to start a game
            if len(active_player_connections) == ACTIVE_PLAYERS and not game_in_progress:
                with countdown_timer_lock:
                    # Only announce and start timer if not already running
                    if not countdown_timer_running:
                        countdown_timer_running = True
                        
                        # We have both active players, announce game will start soon
                        for _, _, _, wf, _ in active_player_connections + spectator_connections:
                            wf.write(f"[INFO] Both players connected! Game will start in {GAME_START_DELAY} seconds.\n\n")
                            wf.write(f"[INFO] Currently {len(spectator_connections)} spectators connected.\n\n")
                            wf.write("[INFO] More spectators can still join before the game starts.\n\n")
                            wf.flush()
                        
                        # Start a countdown timer in a new thread
                        start_timer_thread = threading.Thread(target=start_game_countdown)
                        start_timer_thread.daemon = True
                        start_timer_thread.start()
                    else:
                        # Timer already running, just inform the new connection
                        wfile.write(f"[INFO] Game is already counting down and will start soon.\n\n")
                        wfile.write(f"[INFO] Currently {len(spectator_connections)} spectators connected.\n\n")
                        wfile.flush()
    
    except Exception as e:
        print(f"[ERROR] Connection error: {e}\n\n")
        # If anything goes wrong, clean up connection
        with connection_lock:
            # Determine which list to remove from
            removed = False
            for connections_list in [active_player_connections, spectator_connections]:
                for i, (c, _, _, _, _) in enumerate(connections_list):
                    if c == conn:
                        del connections_list[i]
                        removed = True
                        break
                if removed:
                    break
        
        try:
            conn.close()
        except:
            pass
        return
        
    # Keep connection open and check for commands while waiting for game to start
    try:
        waiting_for_game = True
        while waiting_for_game and not game_in_progress:
            # Make the socket non-blocking for reading with timeout
            ready, _, _ = select.select([conn], [], [], 0.5)
            if ready:
                cmd = rfile.readline().strip().upper()
                if cmd == 'QUIT':
                    print(f"[INFO] Connection from {addr} has quit while waiting.\n\n")
                    # Clean up connection
                    with connection_lock:
                        # Determine which list to remove from and the type of connection
                        removed_from_active = False
                        for i, (c, _, _, _, num) in enumerate(active_player_connections):
                            if c == conn:
                                print(f"[INFO] Active Player {num} has quit while waiting.\n\n")
                                del active_player_connections[i]
                                removed_from_active = True
                                break
                        
                        if not removed_from_active:
                            for i, (c, _, _, _, num) in enumerate(spectator_connections):
                                if c == conn:
                                    print(f"[INFO] Spectator {num} has quit while waiting.\n\n")
                                    del spectator_connections[i]
                                    break
                        
                        # If we lose an active player, cancel the countdown
                        if removed_from_active:
                            game_ready_event.clear()
                            
                            # Notify all remaining connections
                            for _, _, _, wf, _ in active_player_connections + spectator_connections:
                                wf.write("[INFO] A player left. Game start cancelled.\n\n")
                                wf.write("[INFO] Disconnecting all connections. Please reconnect.\n\n")
                                wf.flush()
                            
                            # Make copies of the connection lists before modifying them
                            connections_to_close = active_player_connections.copy() + spectator_connections.copy()
                            
                            # Clear the connection lists to reset player numbers
                            active_player_connections.clear()
                            spectator_connections.clear()
                            
                            # Close all remaining connections
                            for c, _, _, _, _ in connections_to_close:
                                try:
                                    c.close()
                                except:
                                    pass
                    
                    conn.close()
                    return
            
            # Check if the game is starting (indicated by the event)
            if game_ready_event.is_set():
                waiting_for_game = False
            
    except Exception as e:
        print(f"[INFO] Connection from {addr} disconnected while waiting: {e}\n\n")
        with connection_lock:
            # Determine which list to remove from and the type of connection
            removed_from_active = False
            for i, (c, _, _, _, num) in enumerate(active_player_connections):
                if c == conn:
                    print(f"[INFO] Active Player {num} disconnected while waiting.\n\n")
                    del active_player_connections[i]
                    removed_from_active = True
                    break
            
            if not removed_from_active:
                for i, (c, _, _, _, num) in enumerate(spectator_connections):
                    if c == conn:
                        print(f"[INFO] Spectator {num} disconnected while waiting.\n\n")
                        del spectator_connections[i]
                        break
            
            # If we lose an active player, cancel the countdown
            if removed_from_active:
                game_ready_event.clear()
                
                # Notify all remaining connections
                for _, _, _, wf, _ in active_player_connections + spectator_connections:
                    wf.write("[INFO] A player left. Game start cancelled.\n\n")
                    wf.write("[INFO] Disconnecting all connections. Please reconnect.\n\n")
                    wf.flush()
                
                # Make copies of the connection lists before modifying them
                connections_to_close = active_player_connections.copy() + spectator_connections.copy()
                
                # Clear the connection lists to reset player numbers
                active_player_connections.clear()
                spectator_connections.clear()
                
                # Close all remaining connections
                for c, _, _, _, _ in connections_to_close:
                    try:
                        c.close()
                    except:
                        pass
        
        try:
            conn.close()
        except:
            pass
        return

def start_game_countdown():
    # Count down for GAME_START_DELAY seconds, then start the game
    # if we still have both active players.
    global game_in_progress, active_player_connections, spectator_connections, countdown_timer_running
    
    try:
        # Wait for the countdown time
        for i in range(GAME_START_DELAY, 0, -1):
            # Every few seconds, update connections on time remaining
            if i % 5 == 0 or i <= 3:
                with connection_lock:
                    # Make sure we still have both active players
                    if len(active_player_connections) < ACTIVE_PLAYERS:
                        # Reset timer flag before returning
                        with countdown_timer_lock:
                            countdown_timer_running = False
                            
                        # Make copies of the connection lists before modifying them
                        connections_to_close = active_player_connections.copy() + spectator_connections.copy()
                        
                        # Notify all connections before closing
                        for _, _, _, wf, _ in connections_to_close:
                            try:
                                wf.write("[INFO] Not enough active players left. Game start cancelled.\n\n")
                                wf.write("[INFO] Disconnecting all connections. Please reconnect.\n\n")
                                wf.flush()
                            except:
                                pass
                        
                        # Clear the connection lists to reset player numbers
                        active_player_connections.clear()
                        spectator_connections.clear()
                        
                        # Close all remaining connections
                        for c, _, _, _, _ in connections_to_close:
                            try:
                                c.close()
                            except:
                                pass
                        
                        return
                    
                    # Update all connections on countdown
                    for _, _, _, wf, _ in active_player_connections + spectator_connections:
                        wf.write(f"[INFO] Game starting in {i} seconds... ({len(spectator_connections)} spectators)\n\n")
                        wf.flush()
            
            time.sleep(1)
    
        # Time's up, start the game if we still have both active players
        with connection_lock:
            # Reset timer flag no matter what happens next
            with countdown_timer_lock:
                countdown_timer_running = False

            # If we have both active players, mark game as in progress
            with game_in_progress_lock:
                game_in_progress = True
            
            # Set the event to notify waiting threads
            game_ready_event.set()
            
            # Collect players' and spectators' connection info
            active_connections = active_player_connections.copy()
            spectator_conns = spectator_connections.copy()
        
        # Start the game in a new thread
        game_thread = threading.Thread(
            target=run_game_session,
            args=(active_connections, spectator_conns)
        )
        game_thread.daemon = True
        game_thread.start()
        
    except Exception as e:
        # Make sure to reset the flag even if an error occurs
        with countdown_timer_lock:
            countdown_timer_running = False
        print(f"[ERROR] Countdown error: {e}")

def run_game_session(active_player_connections, spectator_connections):
    # Run a game session with active players and spectators.
    # Args:
    #     active_player_connections: List of (conn, addr, rfile, wfile, player_num) tuples for active players
    #     spectator_connections: List of (conn, addr, rfile, wfile, spectator_num) tuples for spectators
    global game_in_progress
    
    try:
        # Extract the rfiles and wfiles for active players (for game interaction)
        player_rfiles = []
        player_wfiles = []
        
        for _, _, rfile, wfile, _ in active_player_connections:
            player_rfiles.append(rfile)
            player_wfiles.append(wfile)
        
        # Extract wfiles for spectators (for read-only updates)
        spectator_wfiles = []
        for _, _, _, wfile, _ in spectator_connections:
            spectator_wfiles.append(wfile)
        
        # Notify all connections that the game is starting
        spectator_count = len(spectator_connections)
        
        # Notify active players
        for wfile in player_wfiles:
            try:
                wfile.write(f"[INFO] Game is starting with {spectator_count} spectators!\n\n")
                wfile.write("[INFO] You are an active player - you can make moves.\n\n")
                wfile.flush()
            except:
                pass
        
        # Notify spectators
        for wfile in spectator_wfiles:
            try:
                wfile.write(f"[INFO] Game is starting with {spectator_count} spectators!\n\n")
                wfile.write("[INFO] You are a spectator - you can only watch the game.\n\n")
                wfile.flush()
            except:
                pass
        
        # Run the multiplayer game (passing both player files and spectator wfiles)
        run_multiplayer_game_online(player_rfiles, player_wfiles, spectator_wfiles)
        
        # Game has ended - notify all connections
        for wfile in player_wfiles + spectator_wfiles:
            try:
                wfile.write("[INFO] Game over! Thank you for playing/watching!\n\n")
                wfile.flush()
            except:
                pass
        
    except Exception as e:
        print(f"[ERROR] Game error: {e}")
        # Notify all connections of the error
        for _, _, _, wfile, _ in active_player_connections + spectator_connections:
            try:
                wfile.write("[ERROR] An error occurred in the game. The session will end.\n\n")
                wfile.flush()
            except:
                pass
    
    finally:
        # Close all connections
        for conn, _, _, _, _ in active_player_connections + spectator_connections:
            try:
                conn.close()
            except:
                pass
        
        # Reset game state
        with game_in_progress_lock:
            game_in_progress = False
        game_ready_event.clear()
        
        # Clear the global connection lists
        with connection_lock:
            globals()['active_player_connections'].clear()
            globals()['spectator_connections'].clear()
        
        print("[INFO] Game ended. Server ready for new players and spectators.\n")

def main():
    print(f"[INFO] Server listening on {HOST}:{PORT}\n")
    print(f"[INFO] Active players required: {ACTIVE_PLAYERS}\n")
    print(f"[INFO] Maximum total connections allowed (players + spectators): {MAX_CONNECTIONS}\n")
    
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
        # Set socket options to allow reuse of address
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((HOST, PORT))
        server_socket.listen(MAX_CONNECTIONS)
        
        try:
            while True:
                # Accept a new connection
                conn, addr = server_socket.accept()
                
                # Start a new thread to handle this client
                client_thread = threading.Thread(target=handle_client, args=(conn, addr))
                client_thread.daemon = True
                client_thread.start()
        except KeyboardInterrupt:
            print("\n[INFO] Server shutting down.\n\n")
        except Exception as e:
            print(f"[ERROR] Server error: {e}\n\n")

if __name__ == "__main__":
    main()