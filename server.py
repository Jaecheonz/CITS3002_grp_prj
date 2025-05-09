# server.py
# Game logic is handled entirely on the server using battleship.py.
# First 2 clients are active players, others are spectators.

import socket
import threading
import select
import time
from battleship import run_multiplayer_game_online

HOST = '127.0.0.1'
PORT = 5000

# Configuration
ACTIVE_PLAYERS = 2  # Exactly 2 active players needed
MAX_CONNECTIONS = 8  # Maximum total connections (players + spectators)
GAME_START_DELAY = 8  # Seconds to wait after active players join before starting
CONNECTION_TIMEOUT = 30  # Seconds to wait for a response before considering the connection lost

# Global variables to track connections
active_player_connections = []  # List of active players (max 2)
spectator_connections = []      # List of spectators
connection_lock = threading.Lock()
game_in_progress = False
game_in_progress_lock = threading.Lock()
game_ready_event = threading.Event()
countdown_timer_running = False
countdown_timer_lock = threading.Lock()
reconnect_event = threading.Event()
reconnect_event.set()
reconnecting = False

player_rfiles = []  # List of rfiles for active players
player_wfiles = []  # List of wfiles for active players
spectator_rfiles = []  # List of rfiles for spectators
spectator_wfiles = []  # List of wfiles for spectators

def map_wrfiles_(active_player_connections, spectator_connections):
    # Map the rfiles and wfiles for active players and spectators
    global player_rfiles, player_wfiles, spectator_rfiles, spectator_wfiles
    # reset the lists to avoid duplication
    while True:
        try:
            reconnect_event.wait()  # Wait for the reconnect event to be set
            with connection_lock:
                player_rfiles.clear()
                player_wfiles.clear()
                spectator_rfiles.clear()
                spectator_wfiles.clear()
                
                # make sure list is right size
                for i in range(len(active_player_connections)):
                    player_rfiles.append(None)
                    player_wfiles.append(None)
                # Extract the rfiles and wfiles for active players based on the player number
                for _, _, rfile, wfile, player_num in active_player_connections:
                    player_rfiles[player_num - 1] = rfile
                    player_wfiles[player_num - 1] = wfile

                # make sure list is right size
                for i in range(len(spectator_connections)):
                    spectator_rfiles.append(None)
                    spectator_wfiles.append(None)
                # Extract the rfiles and wfiles for spectators (for game watching)
                for _, _, rfile, wfile, spectator_num in spectator_connections:
                    spectator_rfiles[spectator_num - 1] = rfile
                    spectator_wfiles[spectator_num - 1] = wfile
            time.sleep(1)  # Sleep for a second before checking again
        except Exception as e:
            print(f"[ERROR] Error mapping rfiles/wfiles: {e}")
            break

def monitor_connections(): 
    #monitors connections during the game phase
    global active_player_connections, game_in_progress, reconnecting, spectator_connections
    global reconnect_event
    try:
        while game_in_progress:
            # Check active player connections
            for i in range(len(active_player_connections) - 1, -1, -1):
                conn, addr, _, _, player_num = active_player_connections[i]
                try:
                    # Test if the connection is still alive
                    conn.send(b'\0')  # Send a null byte
                except:
                    reconnecting = True # Set reconnecting flag
                    del_player_num = player_num # Store the player number for reconnecting
                    print(f"[INFO] Player {del_player_num} ({addr}) has lost connection.")
                    del active_player_connections[i]

                    # Notify remaining connections
                    for _, _, _, wf, _ in active_player_connections + spectator_connections:
                        wf.write(f"[INFO] Player {del_player_num} has lost connection. Awaiting reconnect...\n\n")
                        wf.flush()
                    
                    reconnect_event.clear() # clear the event to make the game wait for reconnection
                    
                    # Start a thread to wait for reconnection
                    reconnect_thread = threading.Thread(target=reconnect_player, args=(del_player_num,))
                    reconnect_thread.daemon = True
                    
                    reconnect_thread.start()
                    reconnect_thread.join()

            #check spectator connections
            for i in range(len(spectator_connections) - 1, -1, -1):
                conn, addr, _, _, spectator_num = spectator_connections[i]
                try:
                    # Test if the connection is still alive
                    conn.send(b'\0')  # Send a null byte
                except:
                    print(f"[INFO] Spectator {spectator_num} ({addr}) has lost connection.")
                    del spectator_connections[i]

            print(f"[INFO] Monitoring connections... {len(active_player_connections)} active players, {len(spectator_connections)} spectators.\n")
            time.sleep(1)  # Check connections every second
    except Exception as e:
        print(f"[ERROR] Connection monitoring error: {e}")

def reconnect_player(disconnected_player_num):
    global reconnecting, reconnect_event
    global active_player_connections
    global spectator_connections

    print(f"[INFO] Waiting for Player {disconnected_player_num} to reconnect...\n")

    if reconnecting:
        # Wait for CONNECTION_TIMEOUT seconds for a new connection
        start_time = time.time()
        while time.time() - start_time < CONNECTION_TIMEOUT:
            if len(active_player_connections) < ACTIVE_PLAYERS and reconnecting:
                time.sleep(1)  # Check every second
                print("[INFO] Waiting for reconnection...\n")
            else:
                # If player reconnects, break out of the loop
                print(f"[INFO] Player {disconnected_player_num} has reconnected.")
                reconnecting = False
                reconnect_event.set()  # Clear the event to notify waiting threads
                break
    if reconnecting:
        # If the player didn't reconnect in time, notify all connections and exit game
        for _, _, _, wf, _ in active_player_connections + spectator_connections:
            wf.write(f"[INFO] Player {disconnected_player_num} did not reconnect in time. Not enough players to continue.\n\n")
            wf.flush()
            reconnect_event.clear  # Clear the event to notify waiting threads
    

def handle_client(conn, addr):
    # Handle a client connection by adding it to the appropriate connection list.
    global game_in_progress, active_player_connections, spectator_connections, countdown_timer_running, reconnecting
 
    print(f"[INFO] New connection from {addr}\n")
    
    try:
        with connection_lock:
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

            if is_active_player and reconnecting:
                # Active player reconnecting - get the player number from the list
                player_num = 3 - active_player_connections[0][4] # Assuming player numbers are 1 and 2 calculate the reconnecting player number
                active_player_connections.append(conn, addr, rfile, wfile, player_num)
                wfile.write(f"[INFO] Welcome back! You are Active Player {player_num}.\n\n")
                reconnecting = False # Reset reconnecting flag

            elif is_active_player:
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
                            wf.write("[INFO] More spectators can still join after the game starts.\n\n")
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
            
        # Start the game and connection monitor in a new thread
        monitor_thread = threading.Thread(
            target=monitor_connections
        )
        monitor_thread.daemon = True
        monitor_thread.start()

        # Start a thread to map the rfiles and wfiles for active players and spectators
        mapping_thread = threading.Thread(
            target=map_wrfiles_, 
            args=(active_player_connections, spectator_connections)
        )
        mapping_thread.daemon = True
        mapping_thread.start()

        # Start the game session in a new thread
        game_thread = threading.Thread(
            target=run_game_session,
            args=(active_player_connections, spectator_connections)
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

    global player_rfiles, player_wfiles, spectator_rfiles, spectator_wfiles
    try:
        # Extract the rfiles and wfiles for active players (for game interaction)
        for _, _, rfile, wfile, _ in active_player_connections:
            player_rfiles.append(rfile)
            player_wfiles.append(wfile)

        # Extract the rfiles and wfiles for spectators (for game watching)
        for _, _, rfile, wfile, _ in spectator_connections:
            spectator_rfiles.append(rfile)
            spectator_wfiles.append(wfile)
    except Exception as e:
        print(f"[ERROR] Error extracting rfiles/wfiles: {e}")
        return

    try:
        # Notify all connections that the game is starting
        spectator_count = len(spectator_connections)
        
        # Notify active players
        for _, _, _, wfile, _ in active_player_connections:
            wfile.write(f"[INFO] Game is starting with {spectator_count} spectators!\n\n")
            wfile.write("[INFO] You are an active player - you can make moves.\n\n")
            wfile.flush()
            
        
        # Notify spectators
        for _, _, _, wfile, _ in spectator_connections:
            try:
                wfile.write(f"[INFO] Game is starting with {spectator_count} spectators!\n\n")
                wfile.write("[INFO] You are a spectator - you can only watch the game.\n\n")
                wfile.flush()
            except:
                print(f"[ERROR] Failed to notify spectator about game start. \n\n")
                pass
        
        # Run the multiplayer game (passing both player files and spectator wfiles)
        run_multiplayer_game_online(reconnect_event, player_rfiles, player_wfiles, spectator_rfiles, spectator_wfiles)
        
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