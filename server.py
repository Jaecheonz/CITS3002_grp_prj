# server.py
# Game logic is handled entirely on the server using battleship.py.
# First 2 clients are active players, others are spectators.

import socket
import threading
import select
import time
import utils  # Import utils module for checksum functions
from battleship import run_multiplayer_game_online

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

# Custom send function to add checksums
def send_message(conn, message):
    try:
        if isinstance(message, str):
            message_bytes = message.encode()
        else:
            message_bytes = message
        
        # Add checksum to the message
        packet = utils.add_checksum(message_bytes)
        
        # Send the packet with checksum
        conn.sendall(packet)
        return True
    except Exception as e:
        print(f"[ERROR] Failed to send message: {e}")
        return False

def safe_send(wfile, message):
    try:
        wfile.write(message)
        wfile.flush()
        time.sleep(0.01)  # Add small delay to avoid overwhelming the stream
    except Exception as e:
        print(f"[WARNING] Failed to send message: {e}")

# Custom receive function to verify checksums
def receive_message(conn, buffer_size=4096):
    try:
        message_bytes = conn.recv(buffer_size)
        if not message_bytes:
            return None
        
        # Verify the checksum
        if not utils.verify_checksum(message_bytes):
            print(f"[WARNING] Received corrupted packet. Discarding...")
            return None
        
        # Strip the checksum to get the original message
        data = utils.strip_checksum(message_bytes)
        return data.decode().strip()
    except Exception as e:
        print(f"[ERROR] Failed to receive message: {e}")
        return None

# Modified file-like object that uses checksums
class ChecksumFile:
    def __init__(self, conn, mode):
        self.conn = conn
        self.mode = mode
        self.buffer = []
        self._closed = False  # Track if closed manually
        
    def write(self, message):
        if self.mode != 'w':
            raise IOError("File not open for writing")
        self.buffer.append(message)
        return len(message)
    
    def flush(self):
        if self.mode != 'w':
            raise IOError("File not open for writing")
        try:
            message = ''.join(self.buffer)
            send_message(self.conn, message)
            self.buffer = []
            return True
        except Exception as e:
            print(f"[ERROR] Failed to flush buffer: {e}")
            return False
    
    def readline(self):
        if self.mode != 'r':
            raise IOError("File not open for reading")
        try:
            msg = receive_message(self.conn)
            if msg is None:
                return ""
            return msg + "\n"
        except Exception as e:
            print(f"[ERROR] Failed to read line: {e}")
            return ""

    def close(self):
        """Manually close the connection and mark as closed."""
        if not self._closed:
            try:
                self.conn.close()
            except Exception as e:
                print(f"[ERROR] Failed to close connection: {e}")
            self._closed = True

    @property
    def closed(self):
        return self._closed

def cleanup_connection(conn, player_quit=False):
    with connection_lock:
        for conn_list in [active_player_connections, spectator_connections]:
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
            for i, (c, _, rfile, wfile, num) in enumerate(spectator_connections):
                if c == conn:
                    print(f"[INFO] Spectator {num} quit.\n\n")
                    spectator_connections.pop(i)
                    break
        
        if removed_from_active:
            game_ready_event.clear()
            for _, _, _, wf, _ in active_player_connections + spectator_connections:
                safe_send(wf, "[INFO] A player left. Game start cancelled.\n\n")
                safe_send(wf, "[INFO] Disconnecting all connections. Please reconnect.\n\n")

            # Close all
            connections_to_close = active_player_connections + spectator_connections
            active_player_connections.clear()
            spectator_connections.clear()
            
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

def handle_client(conn, addr):
    global game_in_progress, active_player_connections, spectator_connections, countdown_timer_running
    
    print(f"[INFO] New connection from {addr}\n")
    
    try:
        with connection_lock:
            if len(active_player_connections) + len(spectator_connections) >= MAX_CONNECTIONS:
                # Too many connections
                send_message(conn, f"[INFO] Sorry, the server has reached the maximum number of connections ({MAX_CONNECTIONS}). Please try again later.\n\n")
                conn.close()
                return
            
            # Wrap the connection with checksum file handlers
            rfile = ChecksumFile(conn, 'r')
            wfile = ChecksumFile(conn, 'w')
            
            is_active_player = len(active_player_connections) < ACTIVE_PLAYERS
            if is_active_player:
                player_num = len(active_player_connections) + 1
                active_player_connections.append((conn, addr, rfile, wfile, player_num))
                safe_send(wfile, f"[INFO] Welcome! You are Active Player {player_num}.\n\n")
                
                if player_num < ACTIVE_PLAYERS:
                    safe_send(wfile, f"[INFO] Waiting for Player 2 to connect...\n\n")
            else:
                spectator_num = len(spectator_connections) + 1
                spectator_connections.append((conn, addr, rfile, wfile, spectator_num))
                safe_send(wfile, f"[INFO] Welcome! You are Spectator {spectator_num}.\n\n")
                safe_send(wfile, f"[INFO] Active players: {len(active_player_connections)}/{ACTIVE_PLAYERS}. You will be able to watch the game but not participate.\n\n")
            
            safe_send(wfile, "[TIP] Type 'quit' to exit.\n\n")
            
            # Notify other clients
            total_connected = len(active_player_connections) + len(spectator_connections)
            connection_type = "Active Player" if is_active_player else "Spectator"
            connection_num = player_num if is_active_player else spectator_num

            for c, _, _, wf, _ in active_player_connections + spectator_connections:
                if c != conn:
                    safe_send(wf, f"[INFO] {connection_type} {connection_num} has joined. ({total_connected}/{MAX_CONNECTIONS} total connections)\n\n")
            
            # Check if ready to start countdown
            if len(active_player_connections) == ACTIVE_PLAYERS and not game_in_progress:
                with countdown_timer_lock:
                    if not countdown_timer_running:
                        countdown_timer_running = True
                        for _, _, _, wf, _ in active_player_connections + spectator_connections:
                            safe_send(wf, f"[INFO] Both players connected! Game will start in {GAME_START_DELAY} seconds.\n\n")
                            safe_send(wf, f"[INFO] Currently {len(spectator_connections)} spectators connected.\n\n")
                            safe_send(wf, "[INFO] More spectators can still join before the game starts.\n\n")
                        
                        # Start countdown thread
                        start_timer_thread = threading.Thread(target=start_game_countdown)
                        start_timer_thread.daemon = True
                        start_timer_thread.start()
                    else:
                        safe_send(wfile, f"[INFO] Game is already counting down and will start soon.\n\n")
                        safe_send(wfile, f"[INFO] Currently {len(spectator_connections)} spectators connected.\n\n")
    
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

    except Exception as e:
        print(f"[INFO] {addr} disconnected while waiting: {e}\n\n")
        cleanup_connection(conn)

def start_game_countdown():
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
                            safe_send(wf, "[INFO] Not enough active players left. Game start cancelled.\n\n")
                            safe_send(wf, "[INFO] Disconnecting all connections. Please reconnect.\n\n")
                        
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
                        safe_send(wf, f"[INFO] Game starting in {i} seconds... ({len(spectator_connections)} spectators)\n\n")
            
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

def run_game_session(active_connections, spectator_conns):
    global game_in_progress

    try:
        # Extract the rfiles and wfiles for active players (for game interaction)
        player_rfiles = []
        player_wfiles = []
        
        for _, _, rfile, wfile, _ in active_connections:
            player_rfiles.append(rfile)
            player_wfiles.append(wfile)
        
        # Extract wfiles for spectators (for read-only updates)
        spectator_wfiles = []
        for _, _, _, wfile, _ in spectator_conns:
            spectator_wfiles.append(wfile)
        
        # Notify all connections that the game is starting
        spectator_count = len(spectator_conns)

        # Notify active players
        for wfile in player_wfiles:
            safe_send(wfile, f"[INFO] Game is starting with {spectator_count} spectators!\n\n")
            safe_send(wfile, "[INFO] You are an active player - you can make moves.\n\n")
        
        # Notify spectators
        for wfile in spectator_wfiles:
            safe_send(wfile, f"[INFO] Game is starting with {spectator_count} spectators!\n\n")
            safe_send(wfile, "[INFO] You are a spectator - you can only watch the game.\n\n")
        
        # Run the multiplayer game (passing both player files and spectator wfiles)
        run_multiplayer_game_online(player_rfiles, player_wfiles, spectator_wfiles)
        
        # Game has ended - notify all connections
        for wfile in player_wfiles + spectator_wfiles:
            safe_send(wfile, "[INFO] Game over! Thank you for playing/watching!\n\n")

    except Exception as e:
        print(f"[ERROR] Game error: {e}")
        # Notify all connections of the error
        for _, _, _, wfile, _ in active_connections + spectator_conns:
            safe_send(wfile, "[ERROR] An error occurred in the game. The session will end.\n\n")
    
    finally:
        # Close all connections and checksum files
        for conn, _, rfile, wfile, _ in active_connections + spectator_conns:
            for f in (rfile, wfile, conn):
                try:
                    f.close()
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