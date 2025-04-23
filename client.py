"""
client.py

Connects to a Battleship server which runs the game.
Uses threading to separate receiving server messages and sending user input.
"""

import socket
import threading
import os

HOST = '127.0.0.1'
PORT = 5000

# Flag to control the message receiving thread
running = True

def receive_messages(rfile):
    """Continuously receive and display messages from the server"""
    global running
    try:
        while running:
            line = rfile.readline()
            if not line:
                print("[INFO] Server disconnected.")
                running = False
                break

            line = line.strip()

            if line == "GRID":
                # Begin reading board lines
                print("\n[Board]")
                while True:
                    board_line = rfile.readline()
                    if not board_line or board_line.strip() == "":
                        break
                    print(board_line.strip())
            else:
                # Normal message
                print(line)
                
                # Check for game end messages
                if "The game will now end." in line or "Game over!" in line:
                    print("[INFO] Game has ended. Exiting...")
                    running = False
                    # Force exit to terminate all threads
                    os._exit(0)
                
                # Also detect forfeit messages
                if "Your opponent forfeited" in line:
                    print("[INFO] Your opponent has left the game.")
                    # Let the message display for a moment before potentially exiting
                    # If "The game will now end" message comes after, it will trigger exit
    except Exception as e:
        print(f"[ERROR] Exception in receive thread: {e}")
        running = False
        # Force exit on exception
        os._exit(1)

def main():
    global running
    running = True
    
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.connect((HOST, PORT))
            print(f"[INFO] Connected to server at {HOST}:{PORT}")
            rfile = s.makefile('r')
            wfile = s.makefile('w')

            # Start a thread for receiving messages
            receive_thread = threading.Thread(target=receive_messages, args=(rfile,))
            receive_thread.daemon = True  # Thread will terminate when main thread exits
            receive_thread.start()

            # Main thread handles sending user input
            while running:
                user_input = input("")
                wfile.write(user_input + '\n')
                wfile.flush()
                
                if user_input.lower() == 'quit':
                    print("[INFO] You chose to quit.")
                    running = False
                    break
                    
        except ConnectionRefusedError:
            print("[ERROR] Connection refused. Make sure the server is running.")
        except KeyboardInterrupt:
            print("\n[INFO] Client exiting.")
        except Exception as e:
            print(f"[ERROR] {e}")
        finally:
            running = False
            print("[INFO] Disconnected from server.")

if __name__ == "__main__":
    main()