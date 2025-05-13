"""
client.py
"""

import socket
import threading
import sys
import time
import select

HOST = '127.0.0.1'
PORT = 5000
# Constants
INACTIVITY_TIMEOUT = 60  # 60 seconds timeout for inactivity
MAX_RETRIES = 3  # Maximum number of retries for connection
RETRY_DELAY = 2

# Global flag for controlling the client loop
running = True

def receive_messages(rfile):
    """Continuously receive and print messages from the server."""
    global running
    try:
        while running:
            # Read directly from the file object instead of using select
            line = rfile.readline()
            if not line:  # Server closed connection
                print("\n[INFO] Server closed the connection")
                break
                
            line = line.strip()
            if not line:
                continue
                
            # Check if this is a grid message
            if line == "GRID":
                # Print the grid
                while True:
                    grid_line = rfile.readline().strip()
                    if not grid_line:
                        break
                    print(grid_line)
                print()  # Add extra newline after grid
            else:
                print(line)
                
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
    global running
    
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
            
            rfile = s.makefile('r')
            wfile = s.makefile('w')
            
            # Start a thread for receiving messages
            receive_thread = threading.Thread(target=receive_messages, args=(rfile,))
            receive_thread.daemon = True  # Thread will terminate when main thread exits
            receive_thread.start()
            
            # Main thread handles sending user input
            while running:
                user_input = get_user_input(">> ")
                if user_input is None:
                    continue
                    
                wfile.write(user_input + '\n')
                wfile.flush()
                
                if user_input.lower() == 'quit':
                    print("[INFO] You chose to quit.")
                    running = False
                    break
                    
        except KeyboardInterrupt:
            print("\n[INFO] Client exiting.")
        except Exception as e:
            print(f"[ERROR] {e}")
        finally:
            running = False
            print("[INFO] Disconnected from server.")

if __name__ == "__main__":
    main()