# client.py
# Connects to a Battleship server which runs the N-player Battleship game.
# Uses threading to separate receiving server messages and sending user input.

import socket
import threading
import os
import time

HOST = '127.0.0.1'
PORT = 5000

# Flag to control the message receiving thread
running = True
# Variable to track the game phase
game_phase = "setup"  # Can be "setup" or "gameplay"

def receive_messages(rfile):
    # Continuously receive and display messages from the server
    global running, game_phase
    try:
        while running:
            line = rfile.readline()
            if not line:
                print("[INFO] Server disconnected.\n\n")
                running = False
                break
                
            line = line.strip()
            
            # Check for phase transition
            if "GAME PHASE" in line:
                game_phase = "gameplay"
                print("[INFO] Entered gameplay phase.\n")
            
            # Handle different types of messages
            if line.endswith("Grid:"):
                # Begin reading board lines
                print(f"\n[{line}]")
                while True:
                    board_line = rfile.readline()
                    if not board_line or board_line.strip() == "":
                        break
                    print(board_line.strip())
            else:
                # Normal message
                print(line)
                
            # Check for game end messages
            if any(phrase in line for phrase in [
                "Game has ended", 
                "Game canceled",
                "Game start canceled" 
                "You win!", 
                "You are eliminated",
                "wins the game",
                "You are the last player standing"
            ]):
                print("\n[INFO] Game has ended. Exiting...\n")
                running = False
                # Force exit to terminate all threads
                time.sleep(3)
                os._exit(0)
                
            # Detect forfeit/disconnect messages
            if any(phrase in line for phrase in [
                "forfeited", 
                "disconnected", 
                "Not enough players"
            ]):
                # Don't exit immediately as the game might continue with other players
                print("\n[INFO] A player has left the game.")
                
    except Exception as e:
        print(f"[ERROR] Exception in receive thread: {e}")
        running = False
        # Force exit on exception
        time.sleep(3)
        os._exit(1)

def main():
    global running, game_phase
    running = True
    game_phase = "setup"
    
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.connect((HOST, PORT))
            print(f"[INFO] Connected to server at {HOST}:{PORT}\n")
            print("[INFO] Waiting for the game to start with enough players...\n")
            
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
                    print("[INFO] You chose to quit.\n")
                    running = False
                    break
                    
        except ConnectionRefusedError:
            print("[ERROR] Connection refused. Make sure the server is running.\n\n")
        except KeyboardInterrupt:
            print("\n[INFO] Client exiting.\n\n")
        except Exception as e:
            print(f"[ERROR] {e}\n\n")
        finally:
            running = False
            print("[INFO] Disconnected from server.\n")

if __name__ == "__main__":
    main()
    