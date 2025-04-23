"""
server.py

Serves a two-player Battleship game session.
Game logic is handled entirely on the server using battleship.py.
Accepts exactly two client connections and starts the game once both are connected.
Uses threading to handle multiple clients concurrently.
"""

import socket
import threading
from battleship import run_two_player_game

HOST = '127.0.0.1'
PORT = 5000

# Global variables to track connections
player_connections = []
connection_lock = threading.Lock()

def handle_client(conn, addr):
    """
    Handle a client connection by adding it to the player_connections list.
    This function runs in its own thread for each client.
    """
    print(f"[INFO] New connection from {addr}")
    
    with connection_lock:
        player_connections.append((conn, addr))
        
        # If we have exactly 2 players, start the game
        if len(player_connections) == 2:
            # Get both connections
            conn1, addr1 = player_connections[0]
            conn2, addr2 = player_connections[1]
            
            # Set up file-like objects for both connections
            rfile1 = conn1.makefile('r')
            wfile1 = conn1.makefile('w')
            rfile2 = conn2.makefile('r')
            wfile2 = conn2.makefile('w')
            
            # Start the game in a new thread
            game_thread = threading.Thread(
                target=run_game_session, 
                args=(conn1, rfile1, wfile1, conn2, rfile2, wfile2)
            )
            game_thread.daemon = True
            game_thread.start()

def run_game_session(conn1, rfile1, wfile1, conn2, rfile2, wfile2):
    """Run a game session between two connected clients"""
    try:
        # Notify players that the game is starting
        wfile1.write("Game is starting! You are Player 1.\n")
        wfile1.flush()
        wfile2.write("Game is starting! You are Player 2.\n")
        wfile2.flush()
        
        # Run the game with both players
        run_two_player_game(rfile1, wfile1, rfile2, wfile2)
    except Exception as e:
        print(f"[ERROR] Game error: {e}")
    finally:
        # Close connections when the game ends
        print("[INFO] Game ended. Closing connections.")
        conn1.close()
        conn2.close()
        
        # Reset player connections for a new game
        with connection_lock:
            player_connections.clear()

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