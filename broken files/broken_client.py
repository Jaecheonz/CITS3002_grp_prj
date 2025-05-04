# client.py
# Connects to a Battleship server which runs the 2-player Battleship game with spectators.
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
# Variable to track if user is a player or spectator
is_spectator = False

def receive_messages(rfile):
    # Continuously receive and display messages from the server
    global running, game_phase, is_spectator
    try:
        while running:
            line = rfile.readline()
            if not line:
                print("[INFO] Server disconnected.\n\n")
                running = False
                break
                
            line = line.strip()
            
            # Check if user is a spectator
            if any(phrase in line for phrase in ["connected as spectator", "joining as spectator"]):
                is_spectator = True
                print("[INFO] You joined as a spectator.\n")
            
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
                
            # Check for game end messages - now handles both player and spectator scenarios
            if any(phrase in line for phrase in [
                "Game has ended", 
                "Game canceled",
                "Game start canceled",
                "You win!", 
                "You lose!",
                "wins the game",
                "Player 1 wins",
                "Player 2 wins"
            ]):
                print("\n[INFO] Game has ended.")
                if is_spectator:
                    print("[INFO] You may disconnect with 'quit' or continue watching post-game chat.\n")
                else:
                    print("[INFO] Game complete. You may disconnect with 'quit'.\n")
                # Don't automatically exit - allow player to quit manually
                
            # Handle active player disconnect/forfeit differently than spectator disconnect
            if "forfeited" in line or "disconnected" in line:
                # Check if one of the two active players left
                if any(player in line for player in ["Player 1", "Player 2"]):
                    if is_spectator:
                        print("\n[INFO] An active player has left the game.")
                    else:
                        # If we're a player and the other player left, we win
                        print("\n[INFO] The other player has left the game.")
                        
            # Handle not enough players scenario
            if "Not enough players" in line:
                print("\n[INFO] Not enough active players to continue. Game will end.\n")
                running = False
                time.sleep(2)
                os._exit(0)
                
    except Exception as e:
        print(f"[ERROR] Exception in receive thread: {e}")
        running = False
        # Don't force exit immediately - let main thread handle it
        time.sleep(1)

def main():
    global running, game_phase, is_spectator
    running = True
    game_phase = "setup"
    is_spectator = False
    
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.connect((HOST, PORT))
            print(f"[INFO] Connected to server at {HOST}:{PORT}\n")
            print("[INFO] Waiting for the game to start...\n")
            
            rfile = s.makefile('r')
            wfile = s.makefile('w')
            
            # Start a thread for receiving messages
            receive_thread = threading.Thread(target=receive_messages, args=(rfile,))
            receive_thread.daemon = True  # Thread will terminate when main thread exits
            receive_thread.start()
            
            # Main thread handles sending user input
            while running:
                user_input = input("")

                # Only send if still connected
                if running:
                    wfile.write(user_input + '\n')
                    wfile.flush()
                
                if user_input.lower() == 'quit':
                    print("[INFO] You chose to quit.\n")
                    if running:
                        try:
                            wfile.write('quit\n')  # <--- explicitly notify server
                            wfile.flush()
                        except:
                            pass
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
            # Give time for any remaining messages to display
            time.sleep(1)
            # Clean exit
            os._exit(0)

if __name__ == "__main__":
    main()