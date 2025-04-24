"""
server.py

Serves a two-player Battleship game session.
Game logic is handled entirely on the server using battleship.py.
Accepts exactly two client connections and starts the game once both are connected.
Uses threading to handle multiple clients concurrently.
"""

import socket
import threading
import select
from battleship import run_two_player_game_online

HOST = '127.0.0.1'
PORT = 5000

# Global variables to track connections
player_connections = []
connection_lock = threading.Lock()
player2_connected = threading.Event()

def handle_client(conn, addr):
    """
    Handle a client connection by adding it to the player_connections list.
    This function runs in its own thread for each client.
    """
    print(f"[INFO] New connection from {addr}")
    
    try:
        with connection_lock:
            # Determine player number (1 or 2)
            player_num = len(player_connections) + 1
            
            # Setup file handlers for the connection
            rfile = conn.makefile('r')
            wfile = conn.makefile('w')
            
            # Immediately inform the player of their player number
            wfile.write(f"Welcome! You are Player {player_num}.\n")
            
            if player_num == 1:
                wfile.write("Waiting for Player 2 to connect...\n")
                wfile.write("Type 'quit' to exit.\n")
            
            wfile.flush()
            
            # Add connection to our list with all necessary info
            player_connections.append((conn, addr, rfile, wfile, player_num))
            
            # If we have exactly 2 players, start the game
            if len(player_connections) == 2:
                player2_connected.set()
                # Get both connections
                conn1, addr1, rfile1, wfile1, _ = player_connections[0]
                conn2, addr2, rfile2, wfile2, _ = player_connections[1]
                
                # Start the game in a new thread
                game_thread = threading.Thread(
                    target=run_game_session,
                    args=(conn1, rfile1, wfile1, conn2, rfile2, wfile2)
                )
                game_thread.daemon = True
                game_thread.start()
                # This code block will finish execution here
                
    except Exception as e:
        print(f"[ERROR] Connection error: {e}")
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
        
    # If player 1, wait for commands while player 2 isn't connected
    if player_num == 1:
        try:
            while not player2_connected.is_set():
                # Make the socket non-blocking for reading with timeout
                ready, _, _ = select.select([conn], [], [], 0.5)
                if ready:
                    cmd = rfile.readline().strip().upper()
                    if cmd == 'QUIT':
                        print("[INFO] Player 1 has quit while waiting.")
                        print("[INFO] Server is ready for a new game.")
                        # Clean up connection
                        with connection_lock:
                            player_connections.clear()
                            player2_connected.clear()
                        conn.close()
                        return

        except Exception as e:
            # Now we properly capture the exception as e
            print(f"[INFO] Player 1 disconnected while waiting: {e}")
            with connection_lock:
                player_connections.clear()
                player2_connected.clear()  # Reset the event
            conn.close()
            return

def run_game_session(conn1, rfile1, wfile1, conn2, rfile2, wfile2):
    """Run a game session between two connected clients"""
    try:
        # Notify players that the game is starting
        wfile1.write("Player 2 has connected. Game is starting!\n")
        wfile1.flush()
        wfile2.write("Game is starting!\n")
        wfile2.flush()
        
        # Run the game with both players
        run_two_player_game_online(rfile1, wfile1, rfile2, wfile2)
    except ConnectionResetError as e:
        # Specifically handle connection reset errors
        print(f"[INFO] A player disconnected during the game: {e}")
        try:
            wfile1.write("Your opponent disconnected. The game will now end.\n")
            wfile1.flush()
        except:
            pass
        try:
            wfile2.write("Your opponent disconnected. The game will now end.\n")
            wfile2.flush()
        except:
            pass
    except Exception as e:
        print(f"[ERROR] Game error: {e}")
    finally:
        # Close connections when the game ends
        print("[INFO] Game ended. Closing connections.")
        try:
            conn1.close()
        except:
            pass
        try:
            conn2.close()
        except:
            pass
        
        # Reset player connections for a new game
        with connection_lock:
            player_connections.clear()
            player2_connected.clear()

def main():
    print(f"[INFO] Server listening on {HOST}:{PORT}")
    
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
        server_socket.bind((HOST, PORT))
        server_socket.listen(2)  # Listen for connections
        
        try:
            while True:
                # Accept a new connection
                conn, addr = server_socket.accept()
                
                # Start a new thread to handle this client
                client_thread = threading.Thread(target=handle_client, args=(conn, addr))
                client_thread.daemon = True
                client_thread.start()
        except KeyboardInterrupt:
            print("\n[INFO] Server shutting down.")
        except Exception as e:
            print(f"[ERROR] Server error: {e}")

if __name__ == "__main__":
    main()