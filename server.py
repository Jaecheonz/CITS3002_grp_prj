# server.py
# Game logic is handled entirely on the server using battleship.py.
# Client sends FIRE commands, and receives game feedback.

import socket
import threading
import select
import time
from battleship import run_multiplayer_game_online

HOST = '127.0.0.1'
PORT = 5000

# Configuration
MIN_PLAYERS = 2  # Minimum players needed to start a game
MAX_PLAYERS = 8  # Maximum players allowed in a game
GAME_START_DELAY = 5  # Seconds to wait after minimum players join before starting

# Global variables to track connections
player_connections = []
connection_lock = threading.Lock()
game_in_progress = False
game_in_progress_lock = threading.Lock()
game_ready_event = threading.Event()

# Add a global set to track players who have voted to start
start_votes = set()

def handle_client(conn, addr):
    global game_in_progress, player_connections, start_votes

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
            
            if len(player_connections) >= MAX_PLAYERS:
                # Too many players, reject connection
                reject_file = conn.makefile('w')
                reject_file.write(f"[INFO] Sorry, the server has reached the maximum number of players ({MAX_PLAYERS}). Please try again later.\n\n")
                reject_file.flush()
                conn.close()
                return
            
            # Determine player number (1-based)
            player_num = len(player_connections) + 1
            
            # Setup file handlers for the connection
            rfile = conn.makefile('r')
            wfile = conn.makefile('w')
            
            # Immediately inform the player of their player number
            wfile.write(f"[INFO] Welcome! You are Player {player_num}.\n\n")
            
            if player_num < MIN_PLAYERS:
                wfile.write(f"[INFO] Waiting for at least {MIN_PLAYERS - player_num} more player(s) to connect...\n\n")
            
            wfile.write("[TIP] Type 'start' when you are ready to begin the game.\n")
            wfile.write("[TIP] Type 'quit' to exit.\n\n")
            wfile.flush()
            
            # Add connection to our list with all necessary info
            player_connections.append((conn, addr, rfile, wfile, player_num))
            
    except Exception as e:
        print(f"[ERROR] Connection error: {e}\n\n")
        cleanup_connection(conn)
        return
        
    # Keep connection open and check for commands while waiting for game to start
    try:
        waiting_for_game = True
        while waiting_for_game and not game_in_progress:
            # Make the socket non-blocking for reading with timeout
            ready, _, _ = select.select([conn], [], [], 0.5)
            if ready:
                cmd = rfile.readline().strip().lower()
                if cmd == 'quit':
                    print(f"[INFO] Player {player_num} has quit while waiting.\n\n")
                    cleanup_connection(conn)
                    return
                elif cmd == 'start':
                    with connection_lock:
                        start_votes.add(player_num)
                        print(f"[INFO] Player {player_num} voted to start. ({len(start_votes)}/{len(player_connections)} votes)\n")
                        
                        # Notify all players of the current vote count
                        for _, _, _, wf, _ in player_connections:
                            wf.write(f"[INFO] Player {player_num} voted to start. ({len(start_votes)}/{len(player_connections)} votes)\n\n")
                            wf.flush()
                        
                        # Check if all players have voted to start
                        if len(start_votes) == len(player_connections):
                            print("[INFO] All players have voted to start. Initiating countdown...\n")
                            for _, _, _, wf, _ in player_connections:
                                wf.write("[INFO] All players have voted to start. Game will begin shortly.\n\n")
                                wf.flush()
                            
                            # Start the countdown timer in a new thread
                            start_timer_thread = threading.Thread(target=start_game_countdown)
                            start_timer_thread.daemon = True
                            start_timer_thread.start()
                            waiting_for_game = False
            
            # Check if the game is starting (indicated by the event)
            if game_ready_event.is_set():
                waiting_for_game = False
            
    except Exception as e:
        print(f"[INFO] Player {player_num} disconnected while waiting: {e}\n\n")
        cleanup_connection(conn)
        return

def cleanup_connection(conn):
    # Helper function to clean up a player's connection
    global player_connections, start_votes
    with connection_lock:
        to_remove = None
        for i, (c, _, _, _, player_num) in enumerate(player_connections):
            if c == conn:
                to_remove = i
                break
        
        if to_remove is not None:
            _, _, _, _, player_num = player_connections[to_remove]
            del player_connections[to_remove]
            start_votes.discard(player_num)  # Remove their vote if they disconnect
        
        # If we fall below minimum players, cancel the countdown
        if len(player_connections) < MIN_PLAYERS:
            game_ready_event.clear()
            
            # Notify remaining players
            for _, _, _, wf, _ in player_connections:
                wf.write("[INFO] Not enough players left. Game start cancelled.\n\n")
                wf.flush()
            
            # Clear the player_connections list to reset player numbers
            player_connections.clear()
            
            # Close all remaining connections
            for c, _, _, _, _ in player_connections:
                try:
                    c.close()
                except:
                    pass
    
    try:
        conn.close()
    except:
        pass

def start_game_countdown():
    # Count down for GAME_START_DELAY seconds, then start the game
    # if we still have at least MIN_PLAYERS.
    global game_in_progress, player_connections
    
    # Wait for the countdown time
    for i in range(GAME_START_DELAY, 0, -1):
        # Every few seconds, update players on time remaining
        if i % 5 == 0 or i <= 3:
            with connection_lock:
                # Make sure we still have enough players
                if len(player_connections) < MIN_PLAYERS:
                    # Make a copy of the connection list before modifying it
                    connections_to_close = player_connections.copy()
                    
                    # Notify all players before closing
                    for _, _, _, wf, _ in connections_to_close:
                        try:
                            wf.write("[INFO] Not enough players left. Game start cancelled.\n\n")
                            wf.write("[INFO] Disconnecting all remaining players. Please reconnect.\n\n")
                            wf.flush()
                        except:
                            pass
                    
                    # Clear the player_connections list to reset player numbers
                    player_connections.clear()
                    
                    # Close all remaining connections
                    for c, _, _, _, _ in connections_to_close:
                        try:
                            c.close()
                        except:
                            pass
                    
                    return
                
                # Update players on countdown
                for _, _, _, wf, _ in player_connections:
                    wf.write(f"[INFO] Game starting in {i} seconds... ({len(player_connections)} players connected)\n\n")
                    wf.flush()
        
        time.sleep(1)
    
    # Time's up, start the game if we still have enough players
    with connection_lock:
        if len(player_connections) < MIN_PLAYERS:
            # Make a copy of the connection list before modifying it
            connections_to_close = player_connections.copy()
            
            # Notify all players before closing
            for _, _, _, wf, _ in connections_to_close:
                try:
                    wf.write("[INFO] Not enough players left. Game start cancelled.\n\n")
                    wf.write("[INFO] Disconnecting all remaining players. Please reconnect.\n\n")
                    wf.flush()
                except:
                    pass
            
            # Clear the player_connections list to reset player numbers
            player_connections.clear()
            
            # Close all remaining connections
            for c, _, _, _, _ in connections_to_close:
                try:
                    c.close()
                except:
                    pass
            
            return
        
        # If we have enough players, mark game as in progress
        with game_in_progress_lock:
            game_in_progress = True
        
        # Set the event to notify waiting threads
        game_ready_event.set()
        
        # Collect players' connection info
        connections = player_connections.copy()
    
    # Start the game in a new thread
    game_thread = threading.Thread(
        target=run_game_session,
        args=(connections,)
    )
    game_thread.daemon = True
    game_thread.start()

def run_game_session(player_connections):
    # Run a game session with all connected players.
    # Args:
    #     player_connections: List of (conn, addr, rfile, wfile, player_num) tuples
    global game_in_progress
    
    try:
        # Extract the rfiles and wfiles for all players
        player_rfiles = []
        player_wfiles = []
        
        for _, _, rfile, wfile, _ in player_connections:
            player_rfiles.append(rfile)
            player_wfiles.append(wfile)
        
        # Notify players that the game is starting
        player_count = len(player_connections)
        for wfile in player_wfiles:
            try:
                wfile.write(f"[INFO] Game is starting with {player_count} players!\n\n")
                wfile.flush()
            except:
                pass
        
        # Run the multiplayer game
        run_multiplayer_game_online(player_rfiles, player_wfiles)
        
        # Game has ended - notify players
        for wfile in player_wfiles:
            try:
                wfile.write("[INFO] Game over! Thank you for playing!\n\n")
                wfile.flush()
            except:
                pass
        
    except Exception as e:
        print(f"[ERROR] Game error: {e}")
        # Notify players of the error
        for _, _, _, wfile, _ in player_connections:
            try:
                wfile.write("[ERROR] An error occurred in the game. The session will end.\n\n")
                wfile.flush()
            except:
                pass
    
    finally:
        # Close all connections
        for conn, _, _, _, _ in player_connections:
            try:
                conn.close()
            except:
                pass
        
        # Reset game state
        with game_in_progress_lock:
            game_in_progress = False
        game_ready_event.clear()
        
        # IMPORTANT: Clear the global player_connections list
        # This ensures that player numbers are reset for the next game
        with connection_lock:
            # We need to clear the global player_connections, not just the local copy
            globals()['player_connections'].clear()
        
        print("[INFO] Game ended. Server ready for new players.\n")

def main():
    print(f"[INFO] Server listening on {HOST}:{PORT}\n")
    print(f"[INFO] Minimum players required: {MIN_PLAYERS}\n")
    print(f"[INFO] Maximum players allowed: {MAX_PLAYERS}\n")
    
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
        # Set socket options to allow reuse of address
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((HOST, PORT))
        server_socket.listen(MAX_PLAYERS)
        
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