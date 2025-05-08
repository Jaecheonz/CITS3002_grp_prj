# client.py
# Connects to a Battleship server which runs the N-player Battleship game.
# Uses threading to separate receiving server messages and sending user input.

import socket
import threading
import os
import time
import utils

HOST = '127.0.0.1'
PORT = 5000

# Flag to control the message receiving thread
running = True
# Variable to track the game phase
game_phase = "setup"

def receive_messages(sock):
    global running, game_phase
    grid_mode = False
    try:
        while running:
            full_packet = sock.recv(4096)
            if not full_packet:
                print("[INFO] Server disconnected.\n\n")
                running = False
                break

            if not utils.verify_checksum(full_packet):
                print("[WARNING] Corrupted packet received. Discarding...")
                continue  # Skip this corrupted packet

            data = utils.strip_checksum(full_packet)
            lines = data.decode().splitlines()

            for line in lines:
                line = line.strip()
                if not line:
                    continue

                if grid_mode:
                    # We are currently receiving a grid
                    if line == "":
                        # Empty line means grid transmission done
                        grid_mode = False
                        continue
                    print(line)
                    continue

                # Normal message handling
                if "GAME PHASE" in line:
                    game_phase = "gameplay"
                    print("[INFO] Entered gameplay phase.\n")

                if line.endswith("Grid:"):
                    print(f"\n[{line}]")
                    grid_mode = True
                    continue

                print(line)

                if any(phrase in line for phrase in [
                    "Game has ended",
                    "Game canceled",
                    "Game start canceled",
                    "You win!",
                    "You are eliminated",
                    "wins the game",
                    "You are the last player standing"
                ]):
                    print("\n[INFO] Game has ended. Exiting...\n")
                    running = False
                    time.sleep(3)
                    os._exit(0)

                if any(phrase in line for phrase in [
                    "forfeited",
                    "disconnected",
                    "Not enough players"
                ]):
                    print("\n[INFO] A player has left the game.")

    except Exception as e:
        print(f"[ERROR] Exception in receive thread: {e}")
        running = False
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

            # Start a thread for receiving messages
            receive_thread = threading.Thread(target=receive_messages, args=(s,))
            receive_thread.daemon = True
            receive_thread.start()

            # Main thread handles sending user input
            while running:
                user_input = input("")
                if not user_input:
                    continue

                # Send the user input with checksum
                packet = utils.add_checksum(user_input.encode())
                s.sendall(packet)

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