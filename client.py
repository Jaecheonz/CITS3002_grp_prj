"""
client.py

Connects to a Battleship server which runs the game.
Uses threading to separate receiving server messages and sending user input.
"""

import socket
import threading

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
    except Exception as e:
        print(f"[ERROR] Exception in receive thread: {e}")
        running = False

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