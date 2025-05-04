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
MAX_PLAYERS = 2  # Maximum active players allowed (exactly 2)
MAX_SPECTATORS = 6  # Maximum spectators allowed
TOTAL_CONNECTIONS = MAX_PLAYERS + MAX_SPECTATORS  # Total connections allowed
GAME_START_DELAY = 1  # Seconds to wait after minimum players join before starting

# Global variables to track connections
player_connections = []
connection_lock = threading.Lock()
game_in_progress = False
game_in_progress_lock = threading.Lock()
game_ready_event = threading.Event()
countdown_timer_running = False
countdown_timer_lock = threading.Lock()

def handle_client(conn, addr):
    # Handle a client connection by adding it to the player_connections list.
    # This function runs in its own thread for each client.
    global game_in_progress, player_connections, countdown_timer_running
    
    print(f"[INFO] New connection from {addr}\n")
    
    try:
        with connection_lock:
            # Check if we've reached total connection limit
            if len(player_connections) >= TOTAL_CONNECTIONS:
                # Too many total connections, reject
                reject_file = conn.makefile('w')
                reject_file.write(f"[INFO] Sorry, the server has reached the maximum number of connections ({TOTAL_CONNECTIONS}). Please try again later.\n\n")
                reject_file.flush()
                conn.close()
                return
            
            # Setup file handlers for the connection
            rfile = conn.makefile('r')
            wfile = conn.makefile('w')
            
            # Count current active players
            active_player_count = len([p for p in player_connections if p[4] <= MAX_PLAYERS])
            
            # Determine if this should be an active player or spectator
            if active_player_count < MAX_PLAYERS and not game_in_progress:
                # This will be an active player
                player_num = active_player_count + 1  # Player numbers are 1 or 2
                
                wfile.write(f"[INFO] Welcome! You are Player {player_num}.\n\n")
                
                if player_num < MIN_PLAYERS:
                    wfile.write(f"[INFO] Waiting for {MIN_PLAYERS - player_num} more player(s) to connect...\n\n")
            else:
                # This will be a spectator
                spectator_count = len([p for p in player_connections if p[4] > MAX_PLAYERS])
                spectator_num = spectator_count + 1
                player_num = MAX_PLAYERS + spectator_num  # Player numbers > MAX_PLAYERS are spectators
                
                wfile.write(f"[INFO] Welcome! You are connected as spectator #{spectator_num}.\n\n")
                wfile.write("[INFO] You can observe the game but cannot participate.\n\n")
                
                if game_in_progress:
                    wfile.write("[INFO] A game is currently in progress. You are joining as a spectator.\n\n")
                else:
                    wfile.write("[INFO] Waiting for active players to connect. You will be spectating.\n\n")
            
            wfile.write("[TIP] Type 'quit' to exit.\n\n")
            wfile.flush()
            
            # Add connection to our list with all necessary info
            player_connections.append((conn, addr, rfile, wfile, player_num))
            
            # Check if we have enough players to start a game
            active_players = [p for p in player_connections if p[4] <= MAX_PLAYERS]
            if len(active_players) >= MIN_PLAYERS and not game_in_progress:
                with countdown_timer_lock:
                    # Only announce and start timer if not already running
                    if not countdown_timer_running:
                        countdown_timer_running = True
                        
                        # We have minimum players, announce game will start soon
                        for _, _, _, wf, pnum in player_connections:
                            if pnum <= MAX_PLAYERS:
                                wf.write(f"[INFO] Minimum player count reached! Game will start in {GAME_START_DELAY} seconds.\n\n")
                                wf.flush()
                            else:
                                wf.write(f"[INFO] The game will start in {GAME_START_DELAY} seconds. You will be spectating.\n\n")
                                wf.flush()

                        # Start a countdown timer in a new thread
                        start_timer_thread = threading.Thread(target=start_game_countdown)
                        start_timer_thread.daemon = True
                        start_timer_thread.start()

    except Exception as e:
        print(f"[ERROR] Connection error: {e}\n\n")
        # If anything goes wrong, clean up player connection
        with connection_lock:
            # Remove this player from connections if they're there
            for i, (c, _, _, _, _) in enumerate(player_connections):
                if c == conn:
                    del player_connections[i]
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
                    print(f"[INFO] Player {player_num} has quit while waiting.\n\n")
                    # Clean up connection
                    with connection_lock:
                        to_remove = None
                        for i, (c, _, _, _, _) in enumerate(player_connections):
                            if c == conn:
                                to_remove = i
                                break
                        
                        if to_remove is not None:
                            del player_connections[to_remove]
                        
                        # If we fall below minimum players, cancel the countdown
                        if len(player_connections) < MIN_PLAYERS:
                            game_ready_event.clear()
                            
                            # Notify remaining players
                            for _, _, _, wf, pnum in player_connections:
                                wf.write("[INFO] Not enough players left. Game start cancelled.\n\n")
                                wf.write("[INFO] Disconnecting all remaining players. Please reconnect.\n]n")
                                wf.flush()
                            
                            # Make a copy of the connection list before modifying it
                            connections_to_close = player_connections.copy()
                            
                            # Clear the player_connections list to reset player numbers
                            player_connections.clear()
                            
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
        print(f"[INFO] Player {player_num} disconnected while waiting: {e}\n\n")
        with connection_lock:
            to_remove = None
            for i, (c, _, _, _, _) in enumerate(player_connections):
                if c == conn:
                    to_remove = i
                    break
            
            if to_remove is not None:
                del player_connections[to_remove]
            
            # If we fall below minimum players, cancel the countdown
            if len(player_connections) < MIN_PLAYERS:
                game_ready_event.clear()
                
                # Notify remaining players
                for _, _, _, wf, _ in player_connections:
                    wf.write("[INFO] Not enough players left. Game start cancelled.\n\n")
                    wf.write("[INFO] Disconnecting all remaining players. Please reconnect.\n\n")
                    wf.flush()
                
                # Make a copy of the connection list before modifying it
                connections_to_close = player_connections.copy()
                
                # Clear the player_connections list to reset player numbers
                player_connections.clear()
                
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
    # if we still have at least MIN_PLAYERS.
    global game_in_progress, player_connections, countdown_timer_running
    
    try:
        # Wait for the countdown time
        for i in range(GAME_START_DELAY, 0, -1):
            # Every few seconds, update players on time remaining
            if i % 5 == 0 or i <= 3:
                with connection_lock:
                    # Make sure we still have enough ACTIVE players
                    active_players = [p for p in player_connections if p[4] <= MAX_PLAYERS]
                    if len(active_players) < MIN_PLAYERS:
                        # Reset timer flag before returning
                        with countdown_timer_lock:
                            countdown_timer_running = False
                        
                        # Notify all players before closing
                        for _, _, _, wf, _ in player_connections:
                            try:
                                wf.write("[INFO] Not enough active players left. Game start cancelled.\n\n")
                                wf.write("[INFO] Disconnecting all connections. Please reconnect.\n\n")
                                wf.flush()
                            except:
                                pass
                        
                        # Close all player connections
                        for conn in player_connections:
                            try:
                                conn.close()
                            except:
                                pass
                        player_connections.clear()
                        
                        return
                    
                    # Update players on countdown
                    for _, _, _, wf, _ in player_connections:
                        wf.write(f"[INFO] Game starting in {i} seconds...\n\n")
                        wf.flush()
            
            time.sleep(1)
    
        # Time's up, start the game if we still have enough players
        with connection_lock:
            # Reset timer flag no matter what happens next
            with countdown_timer_lock:
                countdown_timer_running = False

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
        
    except Exception as e:
        # Make sure to reset the flag even if an error occurs
        with countdown_timer_lock:
            countdown_timer_running = False
        print(f"[ERROR] Countdown error: {e}")

# Fix for the run_game_session function in server.py

def run_game_session(player_connections):
    # Run a game session with all connected players.
    # Args:
    #     player_connections: List of (conn, addr, rfile, wfile, player_num) tuples
    global game_in_progress, countdown_timer_running
    
    try:
        # Separate active players and spectators
        active_players = [p for p in player_connections if p[4] <= MAX_PLAYERS]
        spectators = [p for p in player_connections if p[4] > MAX_PLAYERS]

        # Extract the rfiles and wfiles for all players
        player_rfiles = []
        player_wfiles = []
        
        for _, _, rfile, wfile, _ in active_players:
            player_rfiles.append(rfile)
            player_wfiles.append(wfile)
        
        # Notify players that the game is starting
        player_count = len(active_players)
        spectator_count = len(spectators)
        
        for _, _, _, wfile, pnum in player_connections:
            try:
                if pnum <= MAX_PLAYERS:
                    wfile.write(f"[INFO] Game is starting with {player_count} players and {spectator_count} spectators!\n\n")
                else:
                    wfile.write(f"[INFO] You are spectating a game with {player_count} players.\n\n")
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
        # Game has ended - offer players to play again
        remaining_players = []
        
        with connection_lock:
            # Ask all active players if they want to play again
            for conn, addr, rfile, wfile, player_num in player_connections:
                if player_num <= MAX_PLAYERS:  # Only ask active players
                    try:
                        wfile.write("[INFO] Game over! Would you like to play again? (yes/no)\n\n")
                        wfile.flush()
                        
                        # Add a brief delay for player to see final game state
                        time.sleep(3)
                        
                        # Make the socket non-blocking for reading with timeout
                        ready, _, _ = select.select([conn], [], [], 10)  # 10-second timeout
                        if ready:
                            response = rfile.readline().strip().lower()
                            if response == 'yes':
                                # Keep this player for next game
                                remaining_players.append((conn, addr, rfile, wfile, player_num))
                                continue
                    except:
                        pass
                
                # Close connections for spectators and players who don't want to continue
                try:
                    wfile.write("[INFO] Thanks for playing! Disconnecting...\n\n")
                    wfile.flush()
                    conn.close()
                except:
                    pass
        
        # Reset game state
        with game_in_progress_lock:
            game_in_progress = False
        game_ready_event.clear()
        
        # IMPORTANT FIX: Create a new list instead of modifying the global directly
        # This prevents circular references that can cause recursion issues
        new_player_connections = list(remaining_players)
        
        # Update the global player_connections list with remaining players
        with connection_lock:
            # Don't use globals() here, which can cause issues with recursion
            player_connections.clear()
            player_connections.extend(new_player_connections)
        
        print(f"[INFO] Game ended. {len(remaining_players)} players remaining for next game.\n")
        
        # If we have enough players to start a new game, start the countdown
        if len(remaining_players) >= MIN_PLAYERS:
            with countdown_timer_lock:
                if not countdown_timer_running:
                    countdown_timer_running = True
                    start_timer_thread = threading.Thread(target=start_game_countdown)
                    start_timer_thread.daemon = True
                    start_timer_thread.start()

def main():
    print(f"[INFO] Server listening on {HOST}:{PORT}\n")
    print(f"[INFO] Minimum players required: {MIN_PLAYERS}\n")
    
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