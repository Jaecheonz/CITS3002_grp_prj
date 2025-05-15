"""
battleship.py

Contains core data structures and logic for Battleship, including:
- Board class for storing ship positions, hits, misses
- Utility function parse_coordinate for translating e.g. 'B5' -> (row, col)
- A test harness run_single_player_game() to demonstrate the logic in a local, single-player mode

"""

import random
import threading
import select
import time
from protocol import safe_send, safe_recv, PACKET_TYPES
import logging

MAX_PLAYERS = 2
INACTIVITY_TIMEOUT = 15
BOARD_SIZE = 10
SHIPS = [
    ("Carrier", 5),
    ("Battleship", 4),
    ("Cruiser", 3),
    ("Submarine", 3),
    ("Destroyer", 2)
]


class Board:
    """
    Represents a single Battleship board with hidden ships.
    We store:
    - self.hidden_grid: tracks real positions of ships ('S'), hits ('X'), misses ('o')
    - self.display_grid: the version we show to the player ('.' for unknown, 'X' for hits, 'o' for misses)
    - self.placed_ships: a list of dicts, each dict with:
        {
            'name': <ship_name>,
            'positions': set of (r, c),
        }
        used to determine when a specific ship has been fully sunk.

    In a full 2-player networked game:
    - Each player has their own Board instance.
    - When a player fires at their opponent, the server calls
        opponent_board.fire_at(...) and sends back the result.
    """

    def __init__(self, size=BOARD_SIZE):
        self.size = size
        # '.' for empty water
        self.hidden_grid = [['.' for _ in range(size)] for _ in range(size)]
        # display_grid is what the player or an observer sees (no 'S')
        self.display_grid = [['.' for _ in range(size)] for _ in range(size)]
        self.placed_ships = []  # e.g. [{'name': 'Destroyer', 'positions': {(r, c), ...}}, ...]

    def place_ships_randomly(self, ships=SHIPS):
        """
        Randomly place each ship in 'ships' on the hidden_grid, storing positions for each ship.
        In a networked version, you might parse explicit placements from a player's commands
        (e.g. "PLACE A1 H BATTLESHIP") or prompt the user for board coordinates and placement orientations; 
        the self.place_ships_manually() can be used as a guide.
        """
        for ship_name, ship_size in ships:
            placed = False
            while not placed:
                orientation = random.randint(0, 1)  # 0 => horizontal, 1 => vertical
                row = random.randint(0, self.size - 1)
                col = random.randint(0, self.size - 1)

                if self.can_place_ship(row, col, ship_size, orientation):
                    occupied_positions = self.do_place_ship(row, col, ship_size, orientation)
                    self.placed_ships.append({
                        'name': ship_name,
                        'positions': occupied_positions
                    })
                    placed = True


    def place_ships_manually(self, ships=SHIPS):
        """
        Prompt the user for each ship's starting coordinate and orientation (H or V).
        Validates the placement; if invalid, re-prompts.
        """
        print("\nPlease place your ships manually on the board.")
        for ship_name, ship_size in ships:
            while True:
                self.print_display_grid(show_hidden_board=True)
                print(f"\nPlacing your {ship_name} (size {ship_size}).")
                coord_str = input("  Enter starting coordinate (e.g. A1): ").strip()
                orientation_str = input("  Orientation? Enter 'H' (horizontal) or 'V' (vertical): ").strip().upper()

                try:
                    row, col = parse_coordinate(coord_str)
                except ValueError as e:
                    print(f"  [!] Invalid coordinate: {e}")
                    continue

                # Convert orientation_str to 0 (horizontal) or 1 (vertical)
                if orientation_str == 'H':
                    orientation = 0
                elif orientation_str == 'V':
                    orientation = 1
                else:
                    print("  [!] Invalid orientation. Please enter 'H' or 'V'.")
                    continue

                # Check if we can place the ship
                if self.can_place_ship(row, col, ship_size, orientation):
                    occupied_positions = self.do_place_ship(row, col, ship_size, orientation)
                    self.placed_ships.append({
                        'name': ship_name,
                        'positions': occupied_positions
                    })
                    break
                else:
                    print(f"  [!] Cannot place {ship_name} at {coord_str} (orientation={orientation_str}). Try again.")


    def can_place_ship(self, row, col, ship_size, orientation):
        """
        Check if we can place a ship of length 'ship_size' at (row, col)
        with the given orientation (0 => horizontal, 1 => vertical).
        Returns True if the space is free, False otherwise.
        """
        if orientation == 0:  # Horizontal
            if col + ship_size > self.size:
                return False
            for c in range(col, col + ship_size):
                if self.hidden_grid[row][c] != '.':
                    return False
        else:  # Vertical
            if row + ship_size > self.size:
                return False
            for r in range(row, row + ship_size):
                if self.hidden_grid[r][col] != '.':
                    return False
        return True

    def do_place_ship(self, row, col, ship_size, orientation):
        """
        Place the ship on hidden_grid by marking 'S', and return the set of occupied positions.
        """
        occupied = set()
        if orientation == 0:  # Horizontal
            for c in range(col, col + ship_size):
                self.hidden_grid[row][c] = 'S'
                occupied.add((row, c))
        else:  # Vertical
            for r in range(row, row + ship_size):
                self.hidden_grid[r][col] = 'S'
                occupied.add((r, col))
        return occupied

    def fire_at(self, row, col):
        """
        Fire at (row, col). Return a tuple (result, sunk_ship_name).
        Possible outcomes:
        - ('hit', None)          if it's a hit but not sunk
        - ('hit', <ship_name>)   if that shot causes the entire ship to sink
        - ('miss', None)         if no ship was there
        - ('already_shot', None) if that cell was already revealed as 'X' or 'o'

        The server can use this result to inform the firing player.
        """
        cell = self.hidden_grid[row][col]
        if cell == 'S':
            # Mark a hit
            self.hidden_grid[row][col] = 'X'
            self.display_grid[row][col] = 'X'
            # Check if that hit sank a ship
            sunk_ship_name = self._mark_hit_and_check_sunk(row, col)
            if sunk_ship_name:
                return ('hit', sunk_ship_name)  # A ship has just been sunk
            else:
                return ('hit', None)
        elif cell == '.':
            # Mark a miss
            self.hidden_grid[row][col] = 'o'
            self.display_grid[row][col] = 'o'
            return ('miss', None)
        elif cell == 'X' or cell == 'o':
            return ('already_shot', None)
        else:
            # In principle, this branch shouldn't happen if 'S', '.', 'X', 'o' are all possibilities
            return ('already_shot', None)

    def _mark_hit_and_check_sunk(self, row, col):
        """
        Remove (row, col) from the relevant ship's positions.
        If that ship's positions become empty, return the ship name (it's sunk).
        Otherwise return None.
        """
        for ship in self.placed_ships:
            if (row, col) in ship['positions']:
                ship['positions'].remove((row, col))
                if len(ship['positions']) == 0:
                    return ship['name']
                break
        return None

    def all_ships_sunk(self):
        """
        Check if all ships are sunk (i.e. every ship's positions are empty).
        """
        for ship in self.placed_ships:
            if len(ship['positions']) > 0:
                return False
        return True

    def print_display_grid(self, show_hidden_board=False):
        """
        Print the board as a 2D grid.
        
        If show_hidden_board is False (default), it prints the 'attacker' or 'observer' view:
        - '.' for unknown cells,
        - 'X' for known hits,
        - 'o' for known misses.
        
        If show_hidden_board is True, it prints the entire hidden grid:
        - 'S' for ships,
        - 'X' for hits,
        - 'o' for misses,
        - '.' for empty water.
        """
        # Decide which grid to print
        grid_to_print = self.hidden_grid if show_hidden_board else self.display_grid

        # Column headers (1 .. N)
        print("  " + "".join(str(i + 1).rjust(2) for i in range(self.size)))
        # Each row labeled with A, B, C, ...
        for r in range(self.size):
            row_label = chr(ord('A') + r)
            row_str = " ".join(grid_to_print[r][c] for c in range(self.size))
            print(f"{row_label:2} {row_str}")


def parse_coordinate(coord_str):
    # check for correct input length
    coord_str = coord_str.strip().upper()
    if not coord_str or not (2 <= len(coord_str) <= 3):
        raise ValueError("[TIP] Coordinate must be at least 2 characters and no more than 3 (e.g. A10)")
    
    # check for row letter within bounds
    row_letter = coord_str[0]
    if not ('A' <= row_letter <= 'J'):
        raise ValueError(f"[TIP] Row must be within A-J, got '{row_letter}'")
    
    # check for column number being a number
    col_digits = coord_str[1:]
    try:
        col_num = int(col_digits)
    except ValueError:
        raise ValueError(f"[TIP] Column must be a number, got '{col_digits}'")

    # check for column number within bounds
    if not (1 <= col_num <= 10):
        raise ValueError(f"[TIP] Column must be within 1-10, got {col_num}")
    
    row = ord(row_letter) - ord('A')
    col = int(col_digits) - 1  # zero-based

    return (row, col)

def run_multiplayer_game_online(all_connections):
    """
    Run a 2-player Battleship game with I/O redirected to socket file objects.
    Args:
        player_rfiles: List of 2 file-like objects to .readline() from clients
        player_wfiles: List of 2 file-like objects to .write() back to clients
        spectator_wfiles: List of file-like objects to .write() to spectators
    """
    def send_to_player(player_idx, msg, packet_type=PACKET_TYPES['SYSTEM_MESSAGE']):
        """Send a message to a specific player."""
        try:
            safe_send(all_connections[player_idx][3], all_connections[player_idx][2], msg, packet_type)
        except Exception as e:
            print(f"Error sending to player {player_idx}: {e}")

    def send_to_spectators(msg, packet_type=PACKET_TYPES['SYSTEM_MESSAGE']):
        """Send a message to all spectators."""
        try:
            for i in range(MAX_PLAYERS, len(all_connections)):
                if all_connections[i] is not None:
                    safe_send(all_connections[i][3], all_connections[i][2], msg, packet_type)
        except Exception as e:
            print(f"Error sending to spectators: {e}")

    def send_board_to_player(player_idx, board, show_hidden=False):
        """Send a board representation to a specific player."""
        try:
            safe_send(all_connections[player_idx][3], all_connections[player_idx][2], "GRID", PACKET_TYPES['BOARD_UPDATE'])
            safe_send(all_connections[player_idx][3], all_connections[player_idx][2], "  " + " ".join(str(i + 1).rjust(2) for i in range(board.size)))
            for row in range(board.size):
                row_label = chr(65 + row)  # A, B, C, ...
                row_str = " ".join(board.hidden_grid[row] if show_hidden else board.display_grid[row])
                safe_send(all_connections[player_idx][3], all_connections[player_idx][2], f"{row_label:2} {row_str}")
            safe_send(all_connections[player_idx][3], all_connections[player_idx][2], "")  # Empty line to end grid
        except Exception as e:
            print(f"Error sending board to player {player_idx}: {e}")

    def send_board_to_spectators(board):
        """Send a board representation to all spectators."""
        try:
            for i in range(MAX_PLAYERS, len(all_connections)):
                if all_connections[i] is not None:
                    safe_send(all_connections[i][3], all_connections[i][2], "GRID", PACKET_TYPES['BOARD_UPDATE'])
                    safe_send(all_connections[i][3], all_connections[i][2], "  " + " ".join(str(i + 1).rjust(2) for i in range(board.size)))
                    for row in range(board.size):
                        row_label = chr(65 + row)  # A, B, C, ...
                        row_str = " ".join(board.display_grid[row])
                        safe_send(all_connections[i][3], all_connections[i][2], f"{row_label:2} {row_str}")
                    safe_send(all_connections[i][3], all_connections[i][2], "")  # Empty line to end grid
        except Exception as e:
            print(f"Error sending board to spectators: {e}")

    def recv_from_player(player_idx, timeout=INACTIVITY_TIMEOUT):
        """Receive a message from a specific player."""
        try:
            message = safe_recv(all_connections[player_idx][2], all_connections[player_idx][3], timeout)
            return message
        except Exception as e:
            print(f"Error receiving from player {player_idx}: {e}")
            return None

    def handle_input_during_turn(player_idx, timeout=INACTIVITY_TIMEOUT):
        """Handle input during a player's turn, warning other players who try to input."""
        warned_players = set()
        start_time = time.time()
        time_remaining = timeout
        reminders_sent = set()

        send_to_player(player_idx, f"[INFO] Enter a coordinate to fire at ({time_remaining}s remaining)")

        while True:
            elapsed_time = time.time() - start_time
            time_remaining = max(0, timeout - int(elapsed_time))
            
            if time_remaining == 0:
                # Current player timed out
                send_to_player(player_idx, "[INFO] Time expired! You did not enter a coordinate, giving up your turn.")
                send_to_player(1 - player_idx, f"[INFO] Player {player_idx + 1} timed out and gave up their turn.")
                # Send board updates to both players after timeout
                send_board_to_player(1 - player_idx, boards[1 - player_idx], True)  # Show their own board with ships
                send_board_to_player(1 - player_idx, boards[player_idx], False)  # Show opponent's board
                # Send board updates to spectators
                send_to_spectators(f"\nPlayer {player_idx + 1} timed out and gave up their turn.")
                if player_idx == 0:
                    send_to_spectators("\nPlayer 2's turn.")
                else:
                    send_to_spectators("\nPlayer 1's turn.")
                send_to_spectators(f"\nPlayer Boards:\n")
                send_to_spectators(f"\nPlayer 1's Board:\n")
                send_board_to_spectators(boards[0])
                send_to_spectators(f"\nPlayer 2's Board:\n")
                send_board_to_spectators(boards[1])
                return None  # Return None to indicate timeout

            # Send reminders at 10s and 5s remaining
            reminder_thresholds = [10, 5]
            for threshold in reminder_thresholds:
                if time_remaining <= threshold and threshold not in reminders_sent:
                    send_to_player(player_idx, f"[INFO] Enter a coordinate to fire at ({time_remaining}s remaining)")
                    reminders_sent.add(threshold)
                    break

            try:
                # Check for input from both players using recv_from_player
                for idx in range(2):
                    input_data = recv_from_player(idx, timeout=0.1)  # Use small timeout to keep checking
                    if input_data is not None:
                        if idx == player_idx:
                            # Current player's input
                            return input_data
                        else:
                            # Other player's input - warn them
                            if idx not in warned_players:
                                send_to_player(idx, f"[WARNING] It's not your turn! Please wait for Player {player_idx + 1}'s move.")
                                warned_players.add(idx)

            except ConnectionResetError as e:
                send_to_player(1 - player_idx, f"[INFO] {e}")
                return None

            time.sleep(0.1)

    # Create boards for both players
    boards = [Board(BOARD_SIZE) for _ in range(2)]
    
    # Setup phase - let players place their ships concurrently using threads
    for idx in range(2):
        send_to_player(idx, f"Welcome to Online Multiplayer Battleship! You are Player {idx + 1}.")
        send_to_player(idx, "Place your ships. Type 'RANDOM' for random placement or 'MANUAL' for manual placement.")
    
    # Using threading Event objects to synchronise the players
    player_ready_events = [threading.Event() for _ in range(2)]
    setup_success = [False] * 2  # Track whether each player completed setup successfully
    
    def setup_player_ships(player_idx):
        """Handle ship placement for a single player with timeout."""
        nonlocal setup_success
        
        try:
            while True:
                send_to_player(player_idx, f"[INFO] You have {INACTIVITY_TIMEOUT} seconds to place your ships.")
                placement = recv_from_player(player_idx)
                if placement is None:
                    # Timeout occurred
                    send_to_player(player_idx, f"[TIMEOUT] No input received for {INACTIVITY_TIMEOUT} seconds. Placing ships randomly.")
                    boards[player_idx].place_ships_randomly(SHIPS)
                    send_to_player(player_idx, "Ships placed randomly due to timeout.")
                    send_board_to_player(player_idx, boards[player_idx], True)
                    setup_success[player_idx] = True
                    player_ready_events[player_idx].set()
                    return
                
                if placement.upper() == 'RANDOM':
                    boards[player_idx].place_ships_randomly(SHIPS)
                    send_to_player(player_idx, "Ships placed randomly.")
                    send_board_to_player(player_idx, boards[player_idx], True)
                    setup_success[player_idx] = True
                    player_ready_events[player_idx].set()
                    return
                elif placement.upper() == 'MANUAL':
                    # Handle manual placement
                    current_ship_index = 0
                    ships_to_place = list(SHIPS)
                    
                    while current_ship_index < len(ships_to_place):
                        ship_name, ship_size = ships_to_place[current_ship_index]
                        send_board_to_player(player_idx, boards[player_idx], show_hidden=True)
                        send_to_player(player_idx, f"Placing {ship_name} (size {ship_size}). Enter starting coordinate and orientation (e.g., 'A1 H' or 'B5 V'):")
                        
                        try:
                            placement = recv_from_player(player_idx)
                            if placement is None:
                                # Timeout occurred
                                send_to_player(player_idx, f"[TIMEOUT] No input received for {INACTIVITY_TIMEOUT} seconds. Placing remaining ships randomly.")
                                # Place remaining ships randomly
                                remaining_ships = ships_to_place[current_ship_index:]
                                boards[player_idx].place_ships_randomly(remaining_ships)
                                send_to_player(player_idx, "Remaining ships placed randomly due to timeout.")
                                send_board_to_player(player_idx, boards[player_idx], True)
                                setup_success[player_idx] = True
                                player_ready_events[player_idx].set()
                                return
                            
                            opponent_idx = 1 - player_idx
                            try:
                                readable, _, _ = select.select([all_connections[opponent_idx][2].fileno()], [], [], 0)
                                if readable:
                                    opponent_line = all_connections[opponent_idx][2].readline()
                                    if not opponent_line:  # Opponent disconnected
                                        raise ConnectionResetError()
                            except (ConnectionResetError, OSError):
                                send_to_player(player_idx, "[ALERT] Your opponent has lost connection. \n\n")
                                setup_success[player_idx] = False
                                player_ready_events[player_idx].set()
                                return False
                    
                            parts = placement.strip().split()
                            if len(parts) != 2:
                                send_to_player(player_idx, "Invalid format. Use 'COORD ORIENTATION' (e.g., 'A1 H')")
                                continue
                            
                            coord_str, orientation_str = parts
                            try:
                                row, col = parse_coordinate(coord_str)
                            except ValueError as e:
                                send_to_player(player_idx, f"Invalid coordinate: {e}")
                                continue
                            
                            if orientation_str.upper() not in ['H', 'V']:
                                send_to_player(player_idx, "Invalid orientation. Use 'H' for horizontal or 'V' for vertical.")
                                continue
                            
                            orientation = 0 if orientation_str.upper() == 'H' else 1
                            
                            if boards[player_idx].can_place_ship(row, col, ship_size, orientation):
                                occupied_positions = boards[player_idx].do_place_ship(row, col, ship_size, orientation)
                                boards[player_idx].placed_ships.append({
                                    'name': ship_name,
                                    'positions': occupied_positions
                                })
                                send_to_player(player_idx, f"{ship_name} placed successfully.")
                                current_ship_index += 1
                            else:
                                send_to_player(player_idx, "Cannot place ship there. Try again.")
                        except ValueError as e:
                            send_to_player(player_idx, f"Invalid input: {e}")
                    
                    # All ships placed successfully
                    setup_success[player_idx] = True
                    player_ready_events[player_idx].set()
                    return
                else:
                    send_to_player(player_idx, "Invalid option. Please type 'RANDOM' for random placement or 'MANUAL' for manual placement.")
        except ConnectionResetError as e:
            # Player disconnected during setup
            send_to_player(1 - player_idx, f"[INFO] {e}")
            setup_success[player_idx] = False
            player_ready_events[player_idx].set()
            return

    # Create and start threads for each player's setup
    setup_threads = []
    for i in range(2):
        thread = threading.Thread(target=setup_player_ships, args=(i,))
        setup_threads.append(thread)
        thread.start()

    # Wait for all threads to complete
    for thread in setup_threads:
        thread.join()

    # Check if both players completed setup successfully
    if not all(setup_success):
        # At least one player failed to complete setup
        return

    # Gameplay phase
    for idx in range(2):
        try:
            send_to_player(idx, "All ships have been placed. Game is starting!")
        except ConnectionResetError:
            return
    
    send_to_spectators("Game is starting! You will receive updates as the game progresses.")
    
    current_player = 0
    last_move_time = time.time()
    
    while True:
        try:
            # Show boards to current player
            send_to_player(current_player, "Your board:")
            send_board_to_player(current_player, boards[current_player], True)
            send_to_player(current_player, "Opponent's board:")
            send_board_to_player(current_player, boards[1 - current_player], False)
            
            # Send turn notification
            send_to_player(current_player, f"\nIt's your turn to fire!\n Enter coordinate to fire at (e.g., B5):")
            send_to_player(1 - current_player, f"\nWaiting for Player {current_player + 1}'s move...")
            send_to_spectators(f"\nPlayer {current_player + 1}'s turn to fire...")
            send_to_spectators(f"\nPlayer Boards:\n")
            send_to_spectators(f"\nPlayer 1's Board:\n")
            send_board_to_spectators(boards[0])
            send_to_spectators(f"\nPlayer 2's Board:\n")
            send_board_to_spectators(boards[1])
            
            # Get firing coordinate from current player
            # while True:
            #     try:
            #         coord_str = handle_input_during_turn(current_player)
            #         if coord_str is None:  # Timeout or disconnection
            #             current_player = 1 - current_player  # Switch turns
            #             continue
                    
            #         # Process the coordinate
            #         try:
            #             row, col = parse_coordinate(coord_str)
            #         except ValueError as e:
            #             send_to_player(current_player, f"Invalid coordinate: {e}")
            #             continue
                    
            #         result, sunk_name = boards[1 - current_player].fire_at(row, col)
                    
            #         # Update all players and spectators
            #         if result == 'hit':
            #             if sunk_name:
            #                 send_to_player(current_player, f"HIT! You sank the {sunk_name}!")
            #                 send_to_player(1 - current_player, f"Your {sunk_name} was sunk!")
            #                 send_to_spectators(f"Player {current_player + 1} sank Player {2 - current_player}'s {sunk_name}!")
            #             else:
            #                 send_to_player(current_player, "HIT!")
            #                 send_to_player(1 - current_player, f"Your ship was hit at {coord_str}!")
            #                 send_to_spectators(f"Player {current_player + 1} hit a ship at {coord_str}!")
                        
            #             if boards[1 - current_player].all_ships_sunk():
            #                 send_to_player(current_player, "Congratulations! You sank all ships!")
            #                 send_to_player(1 - current_player, "Game over! All your ships have been sunk.")
            #                 send_to_spectators(f"Game Over! Player {current_player + 1} has won!")
            #                 return
            #         elif result == 'miss':
            #             send_to_player(current_player, "MISS!")
            #             send_to_player(1 - current_player, f"Opponent fired at {coord_str} and missed.")
            #             send_to_spectators(f"Player {current_player + 1} missed at {coord_str}!")
            #         elif result == 'already_shot':
            #             send_to_player(current_player, "You've already fired at that location.")
            #             continue
                    
            #         # Update spectator boards after each move
            #         send_to_spectators(f"\nPlayer 1's Board:\n")
            #         send_board_to_spectators(boards[0])
            #         send_to_spectators(f"\nPlayer 2's Board:\n")
            #         send_board_to_spectators(boards[1])
                    
            #     except ValueError as e:
            #         send_to_player(current_player, f"Invalid input: {e}")
            #         continue
                
            #     # Switch players
            #     current_player = 1 - current_player
            #     last_move_time = time.time()
            #     break
            return
        except ConnectionResetError as e:
            # Player disconnected during gameplay
            send_to_player(1 - current_player, f"[INFO] {e}")
            send_to_spectators(f"[INFO] {e}")
            return