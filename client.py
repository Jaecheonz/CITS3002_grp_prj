"""
client.py

Connects to a Battleship server which runs the single-player game.
Simply pipes user input to the server, and prints all server responses.

TODO: Fix the message synchronization issue using concurrency (Tier 1, item 1).
"""

import socket

HOST = '127.0.0.1'
PORT = 5000

# added import for threading and flag for thread coordination
import threading
running = True

# added dedicated function to receive the messages from the server
def receive_messages(rfile):
    global running
    
    # changed true to only run when the flag is true/ there is a connection to the server
    while running:
        try:
            line = rfile.readline()
            if not line:
                print("[INFO] server disconnected")
                # change the running flag to false to show the connection is lost
                running = False
                break
            
            line = line.strip()
            
            if line == "GRID":
                print("\n[Board]")
                # changed forever true to the flag to accomodate for server disconnected
                while running:
                    board_line = rfile.readline()
                    if not board_line or board_line.strip() == "":
                        break
                    print(board_line.strip())
            else:
                # normal message
                print(line)
        
        # error handling
        except Exception as e:
            print(f"[ERROR] {e} has occurred")
            running = False
            break
        
def main():
    global running
    running = True
    
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.connect((HOST, PORT))
            rfile = s.makefile('r')
            wfile = s.makefile('w')

            # create reader thread, single element tuple declaration syntax for args : args=(rfile,)
            reader_thread = threading.Thread(target=receive_messages, args=(rfile,))
            # daemon to automatically terminate the thread when the main program exits
            reader_thread.daemon = True
            # start the thread
            reader_thread.start()
            
            # changed true to only run when the flag is true/ there is a connection to the server
            while running:
                user_input = input(">> ")
                if user_input.lower() == 'exit':
                    # change flag to false to show the connection is lost
                    running = False
                    break
                
                #send user input to the server
                wfile.write(user_input + '\n')
                wfile.flush()

        # keyboard interruption and error handling
        except KeyboardInterrupt:
            print("\n[INFO] Client exiting.")
            running = False
        except Exception as e:
            print(f"[ERROR] {e}")
            running = False
        
        # wait for reader thread to finish
        if 'reader_thread' in locals() and reader_thread.is_alive():
            reader_thread.join(timeout=1)

if __name__ == "__main__":
    main()