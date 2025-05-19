"""
client.py
"""

import socket
import threading
import sys
import time
import select
from protocol import safe_send, safe_recv, PACKET_TYPES

HOST = '127.0.0.1'
PORT = 5000
# Constants
INACTIVITY_TIMEOUT = 60  # 60 seconds timeout for inactivity
MAX_RETRIES = 3  # Maximum number of retries for connection
RETRY_DELAY = 2

# Global flags for controlling the client loop
running = True
is_my_turn = False  # Flag to track if it's this client's turn
is_setup_phase = True  # Flag to track if we're in the ship placement phase


def receive_messages(rfile, wfile):
    """Continuously receive and print messages from the server."""
    global running, is_my_turn, is_setup_phase
    try:
        while running:
            message = safe_recv(rfile, wfile)
            if message is None:  # Timeout or invalid packet
                continue  # Just continue the loop on timeout
                
            if not message:
                continue
                
            # Check if this is a grid message
            if message.startswith("GRID"):
                # Print the entire grid message
                print(message)
            else:
                print(message)
                # Update turn status based on server messages
                if "It's your turn to fire!" in message or "Enter a coordinate to fire at" in message:
                    is_my_turn = True
                    is_setup_phase = False  # Game has started
                elif "Invalid" in message or "Invalid coordinate" in message:
                    # Keep turn if move was invalid
                    is_my_turn = True
                elif "Place your ships" in message:
                    is_setup_phase = True
                elif "Waiting for Player" in message:
                    # Always suspend input while waiting for reconnection
                    is_my_turn = False
                elif "Timer expired!" in message:
                    is_my_turn = False  # Turn was given up due to timeout
                elif "All ships have been placed. Game is starting!" in message:
                    is_setup_phase = False
                elif "HIT!" in message or "MISS!" in message:
                    # Only end turn if it was a valid move
                    if not ("Invalid" in message or "Invalid coordinate" in message):
                        is_my_turn = False  # Turn is over after a valid move
                
    except ConnectionResetError:
        print("\n[ERROR] Connection to server was reset")
    except ConnectionAbortedError:
        print("\n[ERROR] Connection to server was aborted")
    except Exception as e:
        print(f"\n[ERROR] An error occurred: {str(e)}")
    finally:
        # Ensure we exit the program when the connection is lost
        running = False
        sys.exit(1)

def get_user_input(prompt, timeout=INACTIVITY_TIMEOUT):
    """Get user input with timeout."""
    print(prompt, end='', flush=True)
    
    try:
        return input()
    except EOFError:
        print("\n[ERROR] Input stream closed")
        return None

def main():
    global running, is_my_turn, is_setup_phase
    
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            # Try to connect with retry logic
            for attempt in range(MAX_RETRIES):
                try:
                    s.connect((HOST, PORT))
                    print(f"[INFO] Connected to server at {HOST}:{PORT}")
                    break
                except ConnectionRefusedError:
                    if attempt < MAX_RETRIES - 1:
                        print(f"[INFO] Connection refused. Retrying in {RETRY_DELAY} seconds...")
                        time.sleep(RETRY_DELAY)
                    else:
                        print("[ERROR] Could not connect to server after multiple attempts")
                        sys.exit(1)
            
            # Use binary mode for file objects
            rfile = s.makefile('rb')
            wfile = s.makefile('wb')
            
            # Start a thread for receiving messages
            receive_thread = threading.Thread(target=receive_messages, args=(rfile, wfile))
            receive_thread.daemon = True  # Thread will terminate when main thread exits
            receive_thread.start()
            
            # Main thread handles sending user input
            while running:
                user_input = get_user_input(">> please wait after input, result message may very rarely be corrupted ;)\n>> it wont come in that case T_T but dont disconnect because your move is valid!\n>> you can see it on your opponent's board in your next turn\n\n")
                if user_input is None:
                    continue
                
                # Always process quit command regardless of phase or turn
                if user_input.lower() == 'quit':
                    print("[INFO] You chose to quit.")
                    safe_send(wfile, rfile, user_input, PACKET_TYPES['PLAYER_MOVE'])
                    running = False
                    break
                
                # During setup phase, process all commands
                if is_setup_phase:
                    safe_send(wfile, rfile, user_input, PACKET_TYPES['PLAYER_MOVE'])
                    time.sleep(0.1)
                # During gameplay, only process moves during player's turn
                elif is_my_turn:
                    safe_send(wfile, rfile, user_input, PACKET_TYPES['PLAYER_MOVE'])
                    time.sleep(0.1)
                else:
                    print("[INFO] It's not your turn. Please wait for your turn to make a move.")
                    time.sleep(0.1)
                    
        except KeyboardInterrupt:
            print("\n[INFO] Client exiting.")
            sys.exit(0)
        except Exception as e:
            print(f"[ERROR] {e}")
        finally:
            running = False
            print("[INFO] Disconnected from server.")
            sys.exit(0)

if __name__ == "__main__":
    main()