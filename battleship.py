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

RECONNECTING_TIMEOUT = 30
MAX_PLAYERS = 2
INACTIVITY_TIMEOUT = 120
GAME_MOVE_TIMEOUT = 20
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

    def is_spot_hit(self, row, col):
        """Check if a spot has already been hit or missed."""
        return self.hidden_grid[row][col] in ['X', 'o']

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
        raise ValueError("[TIP] Invalid move.Coordinate must be at least 2 characters and no more than 3 (e.g. A10)")
    
    # check for row letter within bounds
    row_letter = coord_str[0]
    if not ('A' <= row_letter <= 'J'):
        raise ValueError(f"[TIP] Invalid move. Row must be within A-J, got '{row_letter}'")
    
    # check for column number being a number
    col_digits = coord_str[1:]
    try:
        col_num = int(col_digits)
    except ValueError:
        raise ValueError(f"[TIP] Invalid move. Column must be a number, got '{col_digits}'")

    # check for column number within bounds
    if not (1 <= col_num <= 10):
        raise ValueError(f"[TIP] Invalid move. Column must be within 1-10, got {col_num}")
    
    row = ord(row_letter) - ord('A')
    col = int(col_digits) - 1  # zero-based

    return (row, col)

def run_multiplayer_game_online(player_reconnecting, all_connections):
    """
    Run a 2-player Battleship game with I/O redirected to socket file objects.
    Args:
        player_reconnecting: threading.Event() - set when all players are connected, cleared if a player is reconnecting
        all_connections: list of tuples for each player/spectator
    """
    # Ensure the reconnect flag is set at the beginning of every new game so
    # timer logic inside handle_input_during_turn() starts with the correct
    # assumption that both players are present.
    player_reconnecting.set()

    def send_to_player(player_idx, message):
        """Send a message to a player."""
        try:
            # Defensive guard – the slot might be empty (player dropped out)
            if player_idx >= len(all_connections) or all_connections[player_idx] is None:
                print(f"[DEBUG] Cannot send to player {player_idx}: slot is empty")
                return False

            conn, _, rfile, wfile, _ = all_connections[player_idx]
            # Use GAME_STATE packet type for critical game messages
            for attempt in range(3):
                if safe_send(wfile, rfile, message, PACKET_TYPES['GAME_STATE']):
                    return True
                time.sleep(0.1)  # Small delay between retries
            print(f"[WARNING] Failed to send critical message to Player {player_idx + 1} after 3 attempts")
            return False

        except Exception as e:
            print(f"[ERROR] Failed to send message to Player {player_idx + 1}: {e}")
            return False

    def send_to_spectators(message):
        """Send a message to all spectators."""
        success = True
        for i in range(MAX_PLAYERS, len(all_connections)):
            if all_connections[i] is not None:
                try:
                    conn, _, rfile, wfile, _ = all_connections[i]
                    # Use GAME_STATE packet type for critical game messages
                    if any(keyword in message for keyword in ["HIT!", "MISS!", "turn", "Timer expired", "Your turn", "Waiting for Player"]):
                        # For critical messages, retry up to 3 times
                        for attempt in range(3):
                            if safe_send(wfile, rfile, message, PACKET_TYPES['GAME_STATE']):
                                break
                            time.sleep(0.1)  # Small delay between retries
                        else:
                            print(f"[WARNING] Failed to send critical message to Spectator {i - MAX_PLAYERS + 1} after 3 attempts")
                            success = False
                    else:
                        # For non-critical messages, just try once
                        if not safe_send(wfile, rfile, message):
                            success = False
                except Exception as e:
                    print(f"[ERROR] Failed to send message to Spectator {i - MAX_PLAYERS + 1}: {e}")
                    success = False
        return success

    def send_board_to_player(player_idx, board, show_hidden=False):
        """Send a board representation to a specific player."""
        try:
            if all_connections[player_idx] is None:
                print(f"[DEBUG] Cannot send board to player {player_idx} - connection is None")
                return False
            # Build the entire board message as a single string
            board_msg = "GRID\n+"  # Start with GRID marker
            board_msg += "  " + " ".join(str(i + 1) for i in range(board.size)) + '\n'
            for row in range(board.size):
                row_label = chr(65 + row)  # A, B, C, ...
                row_str = " ".join(board.hidden_grid[row] if show_hidden else board.display_grid[row])
                board_msg += f"{row_label:2} {row_str}\n"
            board_msg += '\n'  # Empty line to end grid
            
            # Send the entire board as a single message
            safe_send(all_connections[player_idx][3], all_connections[player_idx][2], board_msg, PACKET_TYPES['BOARD_UPDATE'])
            time.sleep(0.1)  # Add a small delay to prevent message duplication
            return True
        except Exception as e:
            print(f"Error sending board to player {player_idx}: {e}")

    def send_board_to_spectators(board):
        """Send a board representation to all spectators."""
        try:
            # Build the entire board message as a single string
            board_msg = "GRID\n+"  # Start with GRID marker
            board_msg += "  " + " ".join(str(i + 1) for i in range(board.size)) + '\n'
            for row in range(board.size):
                row_label = chr(65 + row)  # A, B, C, ...
                row_str = " ".join(board.display_grid[row])
                board_msg += f"{row_label:2} {row_str}\n"
            board_msg += '\n'  # Empty line to end grid
            
            # Send the entire board as a single message to each spectator
            for i in range(MAX_PLAYERS, len(all_connections)):
                if all_connections[i] is not None:
                    safe_send(all_connections[i][3], all_connections[i][2], board_msg, PACKET_TYPES['BOARD_UPDATE'])
                    time.sleep(0.1)  # Add a small delay to prevent message duplication
        except Exception as e:
            print(f"Error sending board to spectators: {e}")

    def recv_from_player(player_idx, timeout=INACTIVITY_TIMEOUT):
        """Receive a message from a specific player."""
        try:
            if all_connections[player_idx] is None:
                print(f"[DEBUG] Cannot receive from player {player_idx} - connection is None")
                return None
            message = safe_recv(all_connections[player_idx][2], all_connections[player_idx][3], timeout)
            return message
        except Exception as e:
            print(f"Error receiving from player {player_idx}: {e}")
            return None

    def handle_input_during_turn(player_idx, timeout=GAME_MOVE_TIMEOUT):
        """Handle input during a player's turn, focusing on timer and coordinate validation."""
        start_time = time.time()
        reminders_sent = set()

        # Wait for reconnection before allowing input
        if not player_reconnecting.wait(timeout=RECONNECTING_TIMEOUT):
            return None

        if not send_to_player(player_idx, f"[INFO] Enter a coordinate to fire at ({timeout}s remaining)"):
            return None

        while True:
            # Pause if a player is reconnecting
            if not player_reconnecting.wait(timeout=RECONNECTING_TIMEOUT):
                return None

            time_remaining = timeout - (time.time() - start_time)
            if time_remaining <= 0:
                send_to_player(player_idx, "[INFO] Timer expired! Your turn is over.")
                return None

            # Send reminders at 15s, 10s, 5s, 3s, 1s remaining
            reminder_thresholds = [15, 10, 5, 3, 1]
            for threshold in reminder_thresholds:
                if time_remaining <= threshold and threshold not in reminders_sent:
                    send_to_player(player_idx, f"[INFO] Enter a coordinate to fire at ({threshold}s remaining)")
                    reminders_sent.add(threshold)
                    break

            try:
                input_data = recv_from_player(player_idx, timeout=0.1)  # Use small timeout to keep checking
                if input_data is not None:
                    try:
                        result = parse_coordinate(input_data)
                        row, col = result
                        # Check if spot has already been hit before returning
                        if boards[1 - player_idx].is_spot_hit(row, col):
                            send_to_player(player_idx, "[INFO] Invalid move. You've already fired at that location.")
                            continue
                        return result
                    except ValueError as e:
                        send_to_player(player_idx, f"[INFO] Invalid coordinate: {e}")
                        continue
            except Exception as e:
                print(f"[ERROR] Error handling input: {str(e)}")
                # Don't return None here, just continue the loop
                continue

            time.sleep(0.1)

    # Create boards for both players
    boards = [Board(BOARD_SIZE) for _ in range(2)]
    
    # Setup phase - let players place their ships concurrently using threads
    for idx in range(2):
        if not send_to_player(idx, f"Welcome to Online Multiplayer Battleship! You are Player {idx + 1}."):
            return
        if not send_to_player(idx, "Place your ships. Type 'RANDOM' for random placement or 'MANUAL' for manual placement."):
            return
    
    # Using threading Event objects to synchronise the players
    player_ready_events = [threading.Event() for _ in range(2)]
    setup_success = [False] * 2  # Track whether each player completed setup successfully
    
    def setup_player_ships(player_idx):
        """Handle ship placement for a single player with timeout."""
        nonlocal setup_success
        
        try:
            while True:
                if not send_to_player(player_idx, f"[INFO] You have {INACTIVITY_TIMEOUT} seconds to place your ships."):
                    setup_success[player_idx] = False
                    player_ready_events[player_idx].set()
                    return
                    
                placement = recv_from_player(player_idx)
                if placement is None:
                    # Timeout occurred
                    if not send_to_player(player_idx, f"[TIMEOUT] No input received for {INACTIVITY_TIMEOUT} seconds. Placing ships randomly."):
                        setup_success[player_idx] = False
                        player_ready_events[player_idx].set()
                        return
                    boards[player_idx].place_ships_randomly(SHIPS)
                    if not send_to_player(player_idx, "Ships placed randomly due to timeout."):
                        setup_success[player_idx] = False
                        player_ready_events[player_idx].set()
                        return
                    if not send_board_to_player(player_idx, boards[player_idx], True):
                        setup_success[player_idx] = False
                        player_ready_events[player_idx].set()
                        return
                    if not send_to_player(player_idx, "Waiting for opponent to place their ships..."):
                        setup_success[player_idx] = False
                        player_ready_events[player_idx].set()
                        return
                    setup_success[player_idx] = True
                    player_ready_events[player_idx].set()
                    return
                
                if placement.upper() == 'RANDOM':
                    boards[player_idx].place_ships_randomly(SHIPS)
                    if not send_to_player(player_idx, "Ships placed randomly."):
                        setup_success[player_idx] = False
                        player_ready_events[player_idx].set()
                        return
                    if not send_board_to_player(player_idx, boards[player_idx], True):
                        setup_success[player_idx] = False
                        player_ready_events[player_idx].set()
                        return
                    if not send_to_player(player_idx, "Waiting for opponent to place their ships..."):
                        setup_success[player_idx] = False
                        player_ready_events[player_idx].set()
                        return
                    setup_success[player_idx] = True
                    player_ready_events[player_idx].set()
                    return
                elif placement.upper() == 'MANUAL':
                    # Handle manual placement
                    current_ship_index = 0
                    ships_to_place = list(SHIPS)
                    
                    while current_ship_index < len(ships_to_place):
                        ship_name, ship_size = ships_to_place[current_ship_index]
                        if not send_board_to_player(player_idx, boards[player_idx], show_hidden=True):
                            setup_success[player_idx] = False
                            player_ready_events[player_idx].set()
                            return
                        if not send_to_player(player_idx, f"Placing {ship_name} (size {ship_size}). Enter starting coordinate and orientation (e.g., 'A1 H' or 'B5 V'):"):
                            setup_success[player_idx] = False
                            player_ready_events[player_idx].set()
                            return
                        
                        try:
                            placement = recv_from_player(player_idx)
                            if placement is None:
                                # Timeout occurred
                                if not send_to_player(player_idx, f"[TIMEOUT] No input received for {INACTIVITY_TIMEOUT} seconds. Placing remaining ships randomly."):
                                    setup_success[player_idx] = False
                                    player_ready_events[player_idx].set()
                                    return
                                # Place remaining ships randomly
                                remaining_ships = ships_to_place[current_ship_index:]
                                boards[player_idx].place_ships_randomly(remaining_ships)
                                if not send_to_player(player_idx, "Remaining ships placed randomly due to timeout."):
                                    setup_success[player_idx] = False
                                    player_ready_events[player_idx].set()
                                    return
                                if not send_board_to_player(player_idx, boards[player_idx], True):
                                    setup_success[player_idx] = False
                                    player_ready_events[player_idx].set()
                                    return
                                if not send_to_player(player_idx, "Waiting for opponent to place their ships..."):
                                    setup_success[player_idx] = False
                                    player_ready_events[player_idx].set()
                                    return
                                setup_success[player_idx] = True
                                player_ready_events[player_idx].set()
                                return
                            
                            opponent_idx = 1 - player_idx
                            try:
                                if all_connections[opponent_idx] is not None:
                                    readable, _, _ = select.select([all_connections[opponent_idx][2].fileno()], [], [], 0)
                                    if readable:
                                        opponent_line = all_connections[opponent_idx][2].readline()
                                        if not opponent_line:  # Opponent disconnected
                                            raise ConnectionResetError()
                            except (ConnectionResetError, OSError):
                                if not send_to_player(player_idx, "[ALERT] Your opponent has lost connection. \n\n"):
                                    setup_success[player_idx] = False
                                    player_ready_events[player_idx].set()
                                    return False
                    
                            parts = placement.strip().split()
                            if len(parts) != 2:
                                if not send_to_player(player_idx, "Invalid format. Use 'COORD ORIENTATION' (e.g., 'A1 H')"):
                                    setup_success[player_idx] = False
                                    player_ready_events[player_idx].set()
                                    return
                                continue
                            
                            coord_str, orientation_str = parts
                            try:
                                row, col = parse_coordinate(coord_str)
                            except ValueError as e:
                                if not send_to_player(player_idx, f"Invalid coordinate: {e}"):
                                    setup_success[player_idx] = False
                                    player_ready_events[player_idx].set()
                                    return
                                continue
                            
                            if orientation_str.upper() not in ['H', 'V']:
                                if not send_to_player(player_idx, "Invalid orientation. Use 'H' for horizontal or 'V' for vertical."):
                                    setup_success[player_idx] = False
                                    player_ready_events[player_idx].set()
                                    return
                                continue
                            
                            orientation = 0 if orientation_str.upper() == 'H' else 1
                            
                            if boards[player_idx].can_place_ship(row, col, ship_size, orientation):
                                occupied_positions = boards[player_idx].do_place_ship(row, col, ship_size, orientation)
                                boards[player_idx].placed_ships.append({
                                    'name': ship_name,
                                    'positions': occupied_positions
                                })
                                if not send_to_player(player_idx, f"{ship_name} placed successfully."):
                                    setup_success[player_idx] = False
                                    player_ready_events[player_idx].set()
                                    return
                                current_ship_index += 1
                            else:
                                if not send_to_player(player_idx, "Cannot place ship there. Try again."):
                                    setup_success[player_idx] = False
                                    player_ready_events[player_idx].set()
                                    return
                        except ValueError as e:
                            if not send_to_player(player_idx, f"Invalid input: {e}"):
                                setup_success[player_idx] = False
                                player_ready_events[player_idx].set()
                                return
                    
                    # All ships placed successfully
                    if not send_to_player(player_idx, "Your ships have been placed successfully!"):
                        setup_success[player_idx] = False
                        player_ready_events[player_idx].set()
                        return
                    if not send_to_player(player_idx, "Waiting for opponent to place their ships..."):
                        setup_success[player_idx] = False
                        player_ready_events[player_idx].set()
                        return
                    setup_success[player_idx] = True
                    player_ready_events[player_idx].set()
                    return
                else:
                    if not send_to_player(player_idx, "Invalid option. Please type 'RANDOM' for random placement or 'MANUAL' for manual placement."):
                        setup_success[player_idx] = False
                        player_ready_events[player_idx].set()
                        return
        except ConnectionResetError as e:
            # Player disconnected during setup
            if not send_to_player(1 - player_idx, f"[INFO] {e}"):
                setup_success[player_idx] = False
                player_ready_events[player_idx].set()
                return
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
            if not send_to_player(idx, "All ships have been placed. Game is starting!"):
                return
        except ConnectionResetError:
            return

    send_to_spectators("Game is starting! You will receive updates as the game progresses.")
    
    current_player = 0

    RECONNECT_TIMEOUT = 60
    REMINDER_INTERVAL = 15

    def wait_for_player_return(disconnected_idx):
        """Pause the game and wait up to RECONNECT_TIMEOUT seconds for
        `disconnected_idx` to reconnect.  Sends reminder messages every
        REMINDER_INTERVAL seconds.  Returns True if the player rejoined,
        False otherwise."""
        start_time = time.time()
        next_reminder = start_time + REMINDER_INTERVAL

        # Inform everyone once immediately
        send_to_spectators(f"[INFO] Waiting for Player {disconnected_idx + 1} to reconnect…")
        send_to_player(1 - disconnected_idx, f"[INFO] Waiting for Player {disconnected_idx + 1} to reconnect…")

        while True:
            remaining = RECONNECT_TIMEOUT - (time.time() - start_time)
            if remaining <= 0:
                return False  # timed-out

            # Wait until either player_reconnecting is set or reminder interval
            if player_reconnecting.is_set():
                # Player came back
                send_to_spectators(f"[INFO] Player {disconnected_idx + 1} has reconnected — game resumes.")
                send_to_player(1 - disconnected_idx, f"[INFO] Player {disconnected_idx + 1} reconnected. Your opponent is back!")
                return True

            # Not yet — time for another reminder?
            if time.time() >= next_reminder:
                send_to_spectators(f"[INFO] Still waiting for Player {disconnected_idx + 1} to reconnect… ({int(remaining)} s left)")
                send_to_player(1 - disconnected_idx, f"[INFO] Still waiting for Player {disconnected_idx + 1} to reconnect… ({int(remaining)} s left)")
                next_reminder += REMINDER_INTERVAL

            # Small sleep to avoid busy loop if REMINDER_INTERVAL is large.
            time.sleep(0.5)
    
    while True:
        # Ensure both players are connected before starting the turn.
        if not player_reconnecting.is_set():
            # Identify which player is missing (slot is None)
            disconnected_idx = None
            for idx_chk in range(MAX_PLAYERS):
                if idx_chk >= len(all_connections) or all_connections[idx_chk] is None:
                    disconnected_idx = idx_chk
                    break

            # If we couldn't determine, abort the game
            if disconnected_idx is None:
                send_to_spectators("[INFO] Player disconnected. Game ended.")
                return

            # Pause and wait for possible reconnection
            if wait_for_player_return(disconnected_idx):
                # Reconnected → resume the outer while-loop
                current_player = disconnected_idx  # make sure the turn returns to the player that lost connection
                continue

            # No reconnection – declare the remaining player as winner
            winner_idx = 1 - disconnected_idx
            send_to_player(winner_idx, "[INFO] Opponent did not reconnect in time. You win by default!")
            send_to_spectators(f"[INFO] Player {winner_idx + 1} wins by default – opponent failed to return.")
            return

        try:
            # Show boards to current player
            if not send_to_player(current_player, "Your board:"):
                return
            if not send_board_to_player(current_player, boards[current_player], True):
                return
            if not send_to_player(current_player, "Opponent's board:"):
                return
            if not send_board_to_player(current_player, boards[1 - current_player], False):
                return

            # Send turn notification
            if not send_to_player(current_player, f"\n[INFO] It's your turn to fire!\n\n[INFO] Enter coordinate to fire at (e.g., B5):"):
                return
            if not send_to_player(1 - current_player, f"\nWaiting for Player {current_player + 1}'s move..."):
                return
            send_to_spectators(f"\nPlayer {current_player + 1}'s turn to fire...")
            send_to_spectators(f"\nPlayer Boards:\n")
            send_to_spectators(f"\nPlayer 1's Board:\n")
            send_board_to_spectators(boards[0])
            send_to_spectators(f"\nPlayer 2's Board:\n")
            send_board_to_spectators(boards[1])

            # Get firing coordinate from current player
            while True:
                # Wait for reconnection before each input
                if not player_reconnecting.wait(timeout=RECONNECTING_TIMEOUT):
                    send_to_player(current_player, "[INFO] Connection lost or player quit. Ending game.")
                    send_to_player(1 - current_player, "[INFO] Connection lost or player quit. Ending game.")
                    send_to_spectators("[INFO] Connection lost or player quit. Game ended.")
                    return

                try:
                    coord_str = handle_input_during_turn(current_player)
                    if coord_str is None:  # Timeout or disconnection
                        current_player = 1 - current_player  # Switch turns
                        break

                    # Process the coordinate
                    row, col = coord_str

                    result, sunk_name = boards[1 - current_player].fire_at(row, col)

                    # Update all players and spectators
                    if result == 'hit':
                        if sunk_name:
                            send_to_player(current_player, f"HIT! You sank the {sunk_name}!")
                            send_to_player(1 - current_player, f"Your {sunk_name} was sunk!")
                            send_to_spectators(f"Player {current_player + 1} sank Player {2 - current_player}'s {sunk_name}!")
                        else:
                            send_to_player(current_player, "HIT! You hit a ship!")
                            send_to_player(1 - current_player, f"Your ship was hit at {chr(65 + row)}{col + 1}!")
                            send_to_spectators(f"Player {current_player + 1} hit a ship at {chr(65 + row)}{col + 1}!")
                        # After the move, check if the opponent has lost all ships
                        if boards[1 - current_player].all_ships_sunk():
                            send_to_player(current_player, "Congratulations! You sank all ships!")
                            send_to_player(1 - current_player, "Game over! All your ships have been sunk.")
                            send_to_spectators(f"Game Over! Player {current_player + 1} has won!")
                            return
                    elif result == 'miss':
                        send_to_player(current_player, "MISS! You missed.")
                        send_to_player(1 - current_player, f"Opponent fired at {chr(65 + row)}{col + 1} and missed.")
                        send_to_spectators(f"Player {current_player + 1} missed at {chr(65 + row)}{col + 1}!")
                    elif result == 'already_shot':
                        send_to_player(current_player, "You've already fired at that location.")
                        continue

                    # Update spectator boards after each move
                    send_to_spectators(f"\nPlayer 1's Board:\n")
                    send_board_to_spectators(boards[0])
                    send_to_spectators(f"\nPlayer 2's Board:\n")
                    send_board_to_spectators(boards[1])

                except ValueError as e:
                    send_to_player(current_player, f"Invalid input: {e}")
                    continue

                # Force a small delay to ensure messages are sent
                time.sleep(0.1)

                # Switch players
                current_player = 1 - current_player

                # Force another small delay to ensure turn change messages are sent
                time.sleep(0.1)
                break

        except ConnectionResetError as e:
            send_to_player(current_player, "[INFO] Connection lost or player quit. Ending game.")
            send_to_player(1 - current_player, "[INFO] Connection lost or player quit. Ending game.")
            send_to_spectators("[INFO] Connection lost or player quit. Game ended.")
            return