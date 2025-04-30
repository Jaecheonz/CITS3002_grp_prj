# battleship.py
# Contains core data structures and logic for Battleship, including:
# - Board class for storing ship positions, hits, misses
# - Utility function parse_coordinate for translating e.g. 'B5' -> (row, col)

import random
import threading
import select
import time

BOARD_SIZE = 10
SHIPS = [
    ("Carrier", 5),
    ("Battleship", 4),
    ("Cruiser", 3),
    ("Submarine", 3),
    ("Destroyer", 2)
]


class Board:
    def __init__(self, size=BOARD_SIZE):
        self.size = size
        # '.' for empty water
        self.hidden_grid = [['.' for _ in range(size)] for _ in range(size)]
        # display_grid is what the player or an observer sees (no 'S')
        self.display_grid = [['.' for _ in range(size)] for _ in range(size)]
        self.placed_ships = []  # e.g. [{'name': 'Destroyer', 'positions': {(r, c), ...}}, ...]

    def place_ships_randomly(self, ships=SHIPS):
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
        for ship in self.placed_ships:
            if (row, col) in ship['positions']:
                ship['positions'].remove((row, col))
                if len(ship['positions']) == 0:
                    return ship['name']
                break
        return None

    def all_ships_sunk(self):
        for ship in self.placed_ships:
            if len(ship['positions']) > 0:
                return False
        return True

    def print_display_grid(self, show_hidden_board=False):
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

def run_multiplayer_game_online(player_rfiles, player_wfiles):
    # Run a Battleship game with n players.
    # Args:
    #     player_rfiles: List of read file objects for each player
    #     player_wfiles: List of write file objects for each player
    num_players = len(player_rfiles)
    if num_players < 2:
        raise ValueError("At least 2 players required")
    
    def send_to_player(player_idx, msg):
        # Send a message to a specific player.
        if player_idx not in active_players:
            return False  # Don't send to inactive players
            
        try:
            wfile = player_wfiles[player_idx]
            # Check if the file is still valid/open
            if wfile.closed:
                raise BrokenPipeError("File already closed")
            
            wfile.write(msg + '\n')
            wfile.flush()
            return True
        except (BrokenPipeError, ConnectionError, ConnectionResetError, IOError) as e:
            print(f"[ERROR] Failed to send message to Player {player_idx + 1}: {e}\n\n")
            # Remove disconnected player from active players
            if player_idx in active_players:
                active_players.remove(player_idx)
                eliminated_players.add(player_idx)
                # Notify other players about the disconnection
                send_to_all_players(f"[INFO] Player {player_idx + 1} disconnected from the game.\n\n", exclude_idx=player_idx)
                
            return False
    
    def send_to_all_players(msg, exclude_idx=None):
        # Send a message to all players, optionally excluding one.
        if exclude_idx is None:
            exclude_idx = []
        elif not isinstance(exclude_idx, list):
            exclude_idx = [exclude_idx]
            
        for idx in active_players:
            if idx not in exclude_idx:
                send_to_player(idx, msg)
    
    def send_board_to_player(player_idx, target_board_idx, board, show_hidden=False):
        # Send a board state to a player.
        # Args:
        #     player_idx: Index of the player to send the board to
        #     target_board_idx: Index of the board to display
        #     board: The board object
        #     show_hidden: Whether to show hidden ships
        if player_idx not in active_players:
            return False  # Don't send to inactive players
            
        try:
            wfile = player_wfiles[player_idx]
            
            # Determine if this is the player's own board or another player's board
            is_own_board = player_idx == target_board_idx
            board_owner = "Your" if is_own_board else f"Player {target_board_idx + 1}'s"
            
            wfile.write(f"{board_owner} Grid:\n")
            
            # Which grid to display depends on whether we're showing hidden ships
            grid_to_show = board.hidden_grid if show_hidden else board.display_grid
            
            # Column headers
            wfile.write("+  " + " ".join(str(i + 1) for i in range(board.size)) + '\n')
            
            # Each row with label
            for r in range(board.size):
                row_label = chr(ord('A') + r)
                row_str = " ".join(grid_to_show[r][c] for c in range(board.size))
                wfile.write(f"{row_label:2} {row_str}\n")
            
            wfile.write('\n')
            wfile.flush()
            return True
        except (BrokenPipeError, ConnectionError) as e:
            print(f"[ERROR] Failed to send board to Player {player_idx + 1}: {e}\n\n")
            # Remove disconnected player from active players
            if player_idx in active_players:
                active_players.remove(player_idx)
                eliminated_players.add(player_idx)
                # Notify other players
                send_to_all_players(f"[INFO] Player {player_idx + 1} disconnected from the game.\n\n", exclude_idx=player_idx)
            return False
    
    def handle_input_during_turn(player_idx, turn_timeout=15):
        nonlocal current_turn_player
        
        # Keep track of which players have already been warned
        # so we only warn them once per turn
        warned_players = set()

        # Timer variables
        start_time = time.time()
        time_remaining = turn_timeout
        
        # Track when reminders have been sent
        reminders_sent = set()  # Keep track of which reminders have been sent

        # Send initial timer message
        send_to_player(player_idx, f"[INFO] Enter a coordinate ({time_remaining}s remaining)")

        while True:
            # Update timer
            elapsed_time = time.time() - start_time
            time_remaining = max(0, turn_timeout - int(elapsed_time))
            
            # Check if time has expired
            if time_remaining == 0:
                send_to_player(player_idx, "[INFO] Time expired! You did not enter a coordinate, giving up your turn.")
                send_to_all_players(f"[INFO] Player {player_idx + 1} timed out and gave up their turn.", exclude_idx=player_idx)
                return "timeout"  # Return a special value to indicate timeout
            
            # Define reminder thresholds based on turn_timeout
            reminder_thresholds = [10, 5]  # Default reminders for 15s timer
            
            # Send reminders at appropriate times
            for threshold in reminder_thresholds:
                if time_remaining <= threshold and threshold not in reminders_sent:
                    send_to_player(player_idx, f"[INFO] Enter a coordinate ({time_remaining}s remaining)")
                    reminders_sent.add(threshold)
                    break  # Only send one reminder at a time

            # Get list of file descriptors to check
            read_list = []
            fd_to_player = {}  # Map file descriptors to player indices
            
            # Collect valid file descriptors and map them to player indices
            for i in active_players:
                try:
                    fd = player_rfiles[i].fileno()
                    if fd >= 0:  # Check if it's a valid file descriptor
                        read_list.append(fd)
                        fd_to_player[fd] = i
                except (ValueError, IOError):
                    # File descriptor is invalid or closed
                    if i in active_players:
                        active_players.remove(i)
                        eliminated_players.add(i)
                        # Notify other players about the disconnection
                        send_to_all_players(f"[INFO] Player {i + 1} disconnected from the game.\n\n", exclude_idx=i)
            
            # If there are no valid file descriptors, we can't continue
            if not read_list:
                time.sleep(0.1)
                continue
                
            # Use select to check which players have input available (with short timeout)
            try:
                readable, _, _ = select.select(read_list, [], [], 0.1)
                
                # Process readable file descriptors
                for fd in readable:
                    player_i = fd_to_player[fd]
                    
                    if player_i == player_idx:
                        # It's this player's turn - get their input
                        try:
                            return recv_from_player(player_i)
                        except ConnectionResetError:
                            # Handle player disconnection
                            if player_i in active_players:
                                active_players.remove(player_i)
                                eliminated_players.add(player_i)
                                send_to_all_players(f"[INFO] Player {player_i + 1} disconnected from the game.\n\n", exclude_idx=player_i)
                            return "quit"
                    else:
                        # Not this player's turn - warn them once
                        if player_i not in warned_players:
                            send_to_player(player_i, f"[WARNING] It's not your turn. Please wait for Player {player_idx + 1} to complete their turn.\n")
                            warned_players.add(player_i)
                        
                        # Consume the input
                        try:
                            _ = recv_from_player(player_i)
                        except ConnectionResetError:
                            # Handle player disconnection
                            if player_i in active_players:
                                active_players.remove(player_i)
                                eliminated_players.add(player_i)
                                send_to_all_players(f"[INFO] Player {player_i + 1} disconnected from the game.\n\n", exclude_idx=player_i)
                    
            except (select.error, ValueError, IOError) as e:
                # Handle potential errors with select
                print(f"[ERROR] Select error: {e}")
                time.sleep(0.1)

    def recv_from_player(player_idx, timeout=None):
        try:
            # Check if there's data available to read without blocking
            if timeout is not None:
                # Set up select with timeout
                readable, _, _ = select.select([player_rfiles[player_idx].fileno()], [], [], timeout)
                if not readable:
                    return None  # Timeout occurred, no data available
            
            # Read the line
            line = player_rfiles[player_idx].readline()
            if not line:  # Empty string indicates disconnection
                raise ConnectionResetError(f"[INFO] Player {player_idx + 1} disconnected\n\n")
            return line.strip()
        except (ConnectionError, IOError, ValueError) as e:
            # Catch broader range of connection issues
            raise ConnectionResetError(f"[INFO] Player {player_idx + 1} disconnected: {str(e)}\n\n")
    
    # Create boards for all players
    boards = [Board(BOARD_SIZE) for _ in range(num_players)]
    
    # Keep track of active players (initially all are active)
    active_players = list(range(num_players))
    
    # Setup phase - let all players place their ships concurrently using threads
    for idx in range(num_players):
        send_to_player(idx, f"[INFO] SETUP PHASE: Place your ships. Type 'RANDOM' for random placement or 'MANUAL' for manual placement.\n")
    
    # Using threading Event objects to synchronise the players
    player_ready_events = [threading.Event() for _ in range(num_players)]
    setup_success = [False] * num_players  # Track whether each player completed setup successfully
    
    # Define a function to handle ship placement for any player with a timer
    def setup_player_ships(player_idx):
        nonlocal setup_success
        
        try:
            player_board = boards[player_idx]
            
            # Set up timer-related variables
            start_time = time.time()
            time_limit = 60  # 1 minute in seconds
            reminder_times = {45, 30, 15, 10, 5}  # Reminders to send
            sent_reminders = set()  # Track which reminders have been sent
            
            # Send initial instructions
            send_to_player(player_idx, "[INFO] You have 1 minute to place your ships. Type 'RANDOM' for random placement or 'MANUAL' for manual placement.")
            placement = None
            
            # For manual placement, we need to track which ship we're placing
            current_ship_index = 0
            ships_to_place = list(SHIPS)  # Make a copy of the ships list
            manual_placement_started = False
            waiting_for_placement_input = False
            
            while True:
                # Check if we're out of time
                elapsed_time = time.time() - start_time
                remaining_time = time_limit - elapsed_time
                
                # Send time reminders
                for reminder_time in reminder_times:
                    if remaining_time <= reminder_time and reminder_time not in sent_reminders:
                        send_to_player(player_idx, f"[TIME] {reminder_time} seconds remaining to place your ships!")
                        sent_reminders.add(reminder_time)
                
                # If time is up, place ships randomly
                if remaining_time <= 0:
                    send_to_player(player_idx, "[TIME] Time's up! Placing ships randomly.")
                    player_board.place_ships_randomly(SHIPS)
                    send_to_player(player_idx, "[INFO] Ships placed randomly due to time limit.")
                    send_board_to_player(player_idx, player_idx, player_board, True)
                    break
                
                # If we're not waiting for a specific ship placement input,
                # wait for initial placement choice (RANDOM/MANUAL)
                if not manual_placement_started and not waiting_for_placement_input:
                    waiting_for_placement_input = True
                    placement = recv_from_player(player_idx, timeout=min(remaining_time, 5))  # Poll every 5 seconds max
                    waiting_for_placement_input = False
                    
                    # If we got no input, continue the loop to check time again
                    if placement is None:
                        continue
                    
                    if placement.lower() == 'quit':
                        send_to_player(player_idx, "[INFO] You forfeited during setup.\n\n")
                        send_to_all_players(f"[INFO] Player {player_idx + 1} forfeited during setup.\n\n", exclude_idx=player_idx)
                        
                        # Mark this player as not successful
                        setup_success[player_idx] = False
                        
                        # Set this player's ready event
                        player_ready_events[player_idx].set()
                        return False
                    
                    elif placement.upper() == 'RANDOM':
                        player_board.place_ships_randomly(SHIPS)
                        send_to_player(player_idx, "[INFO] Ships placed randomly.")
                        send_board_to_player(player_idx, player_idx, player_board, True)
                        break
                    
                    elif placement.upper() == 'MANUAL':
                        # Start manual placement process
                        manual_placement_started = True
                        send_to_player(player_idx, "[INFO] Placing ships manually:")
                        current_ship_index = 0
                    
                    else:
                        # Invalid placement option - ask player to try again
                        send_to_player(player_idx, "[TIP] Invalid option. Please type 'RANDOM' for random placement or 'MANUAL' for manual placement.")
                        continue
                
                # Handle manual placement of ships
                if manual_placement_started:
                    if current_ship_index >= len(ships_to_place):
                        # All ships placed successfully
                        send_board_to_player(player_idx, player_idx, player_board, True)
                        send_to_player(player_idx, "[INFO] All ships placed successfully.")
                        break
                    
                    ship_name, ship_size = ships_to_place[current_ship_index]
                    
                    # Show current board state
                    send_board_to_player(player_idx, player_idx, player_board, True)
                    send_to_player(player_idx, f"Placing {ship_name} (size {ship_size}). Enter starting coordinate and orientation (e.g., 'A1 H' or 'B5 V'):")
                    
                    # Wait for placement input with timeout
                    waiting_for_placement_input = True
                    placement = recv_from_player(player_idx, timeout=min(remaining_time, 5))  # Poll every 5 seconds max
                    waiting_for_placement_input = False
                    
                    # If we got no input, continue the loop to check time again
                    if placement is None:
                        continue
                    
                    if placement.lower() == 'quit':
                        send_to_player(player_idx, "[INFO] You forfeited during setup.\n\n")
                        send_to_all_players(f"[INFO] Player {player_idx + 1} forfeited during setup.\n\n", exclude_idx=player_idx)
                        
                        # Mark this player as not successful
                        setup_success[player_idx] = False
                        
                        # Set this player's ready event
                        player_ready_events[player_idx].set()
                        return False
                    
                    try:
                        parts = placement.strip().split()
                        if len(parts) != 2:
                            send_to_player(player_idx, "[TIP] Invalid format. Use 'COORD ORIENTATION' (e.g., 'A1 H')")
                            continue
                        
                        coord_str, orientation_str = parts
                        row, col = parse_coordinate(coord_str)
                        orientation = 0 if orientation_str.upper() == 'H' else 1
                        
                        if player_board.can_place_ship(row, col, ship_size, orientation):
                            occupied_positions = player_board.do_place_ship(row, col, ship_size, orientation)
                            player_board.placed_ships.append({
                                'name': ship_name,
                                'positions': occupied_positions
                            })
                            send_to_player(player_idx, f"[INFO] {ship_name} placed successfully.")
                            current_ship_index += 1
                        else:
                            send_to_player(player_idx, "[TIP] Cannot place ship there. Try again.")
                    except ValueError as e:
                        send_to_player(player_idx, f"[TIP] Invalid input: {e}")
                        continue
            
            # Signal that this player is ready and wait for other players
            setup_success[player_idx] = True
            send_to_player(player_idx, f"[INFO] Your ships are placed. Waiting for other players to finish placing their ships...\n")
            player_ready_events[player_idx].set()
            return True
            
        except ConnectionResetError:
            # Player disconnected
            send_to_all_players(f"[INFO] Player {player_idx + 1} disconnected during setup.\n\n", exclude_idx=player_idx)
            
            # Mark this player as not successful
            setup_success[player_idx] = False
            
            # Set this player's ready event
            player_ready_events[player_idx].set()
            return False
    
    # Create and start threads for each player's setup
    setup_threads = []
    for i in range(num_players):
        thread = threading.Thread(
            target=setup_player_ships,
            args=(i,)
        )
        setup_threads.append(thread)
        thread.start()
    
    # Wait for all threads to complete
    for thread in setup_threads:
        thread.join()
    
    # Check which players completed setup successfully
    for i in range(num_players):
        if not player_ready_events[i].is_set() or not setup_success[i]:
            # Remove player from active players
            if i in active_players:
                active_players.remove(i)
    
    # Check if we have enough players to continue
    if len(active_players) < 2:
        send_to_all_players("[INFO] Not enough players completed setup. Game canceled.\n\n")
        return
    
    # Gameplay phase
    for idx in active_players:
        send_to_player(idx, f"[INFO] GAME PHASE: All ships have been placed. Game is starting with {len(active_players)} players!\n")
    
    # Initialise player states
    current_turn_player = None
    current_player_idx = 0  # Index into active_players list
    eliminated_players = set()
    
    def handle_player_turn(player_idx, is_retry=False):
        # Handle a player's turn.
        # Args:
        #     player_idx: Index of the player whose turn it is
        # Returns:
        #     True: Turn completed successfully
        #     False: Game should end
        #     None: Invalid move, retry
        nonlocal active_players, eliminated_players, current_turn_player
        
        try:
            current_turn_player = player_idx
            
            # First, show the player their own board with ships
            send_to_player(player_idx, "Your board:")
            send_board_to_player(player_idx, player_idx, boards[player_idx], True)
            
            # Show all opponent boards
            for opponent_idx in active_players:
                if opponent_idx != player_idx:
                    send_to_player(player_idx, f"Player {opponent_idx + 1}'s board:")
                    send_board_to_player(player_idx, opponent_idx, boards[opponent_idx], False)
            
            # Let other players know whose turn it is - only if this is not a retry
            if not is_retry:
                for idx in active_players:
                    if idx != player_idx:
                        send_to_player(idx, f"[INFO] Player {player_idx + 1}'s turn. Please wait...\n")
            
            # Player's turn to fire
            send_to_player(player_idx, "[INFO] Your turn!\n\n [TIP] Enter a coordinate and player number to fire at (e.g., 'B5 3' to fire at B5 on Player 3's board):")
            
            # Get input with timeout
            fire_input = handle_input_during_turn(player_idx, turn_timeout=15)  # 15 second timeout

            if fire_input == "timeout":
                return True  # Continue game with next player
            
            try:
                if fire_input.strip().lower() == 'quit':
                    send_to_all_players(f"[INFO] Player {player_idx + 1} forfeited.\n", exclude_idx=player_idx)
                    
                    # Remove player from active list
                    if player_idx in active_players:
                        active_players.remove(player_idx)
                        eliminated_players.add(player_idx)
                    
                    # Check if only one player remains
                    if len(active_players) <= 1:
                        if active_players:
                            winner_idx = active_players[0]
                            send_to_player(winner_idx, "[INFO] You are the last player standing. You win!")
                        return False
                    return True
            
                parts = fire_input.strip().split()
                if len(parts) != 2:
                    send_to_player(player_idx, "[TIP] Invalid format. Use 'COORDINATE PLAYER_NUMBER' (e.g., 'B5 3')")
                    return None
                
                coord_str, target_player_str = parts
                
                # Convert target player number (1-based) to index (0-based)
                try:
                    target_player_num = int(target_player_str)
                    target_player_idx = target_player_num - 1
                    
                    if target_player_idx == player_idx:
                        send_to_player(player_idx, "[TIP] You cannot fire at your own board. Choose another player.\n\n")
                        return None
                    
                    if target_player_idx not in active_players:
                        send_to_player(player_idx, f"[INFO] Player {target_player_num} is not an active player. Choose another target.\n\n")
                        return None
                    
                except ValueError:
                    send_to_player(player_idx, "[INFO] Invalid player number.\n\n")
                    return None
                
                # Parse coordinate and fire
                row, col = parse_coordinate(coord_str)
                target_board = boards[target_player_idx]
                result, sunk_name = target_board.fire_at(row, col)
                
                # Notify players of the result
                if result == 'hit':
                    if sunk_name:
                        send_to_player(player_idx, f"\n[INFO] HIT! You sank Player {target_player_num}'s {sunk_name}!\n\n")
                        send_to_player(target_player_idx, f"[INFO] Your {sunk_name} was sunk by Player {player_idx + 1}!\n\n")
                        send_to_all_players(f"[INFO]Player {player_idx + 1} sank Player {target_player_num}'s {sunk_name}!\n\n", 
                                        exclude_idx=[player_idx, target_player_idx])
                    else:
                        send_to_player(player_idx, f"\n[INFO] HIT on Player {target_player_num}'s ship!\n\n")
                        send_to_player(target_player_idx, f"[INFO] Your ship at {coord_str} was hit by Player {player_idx + 1}!\n\n")
                        send_to_all_players(f"[INFO] Player {player_idx + 1} hit Player {target_player_num}'s ship!\n\n", 
                                        exclude_idx=[player_idx, target_player_idx])
                    
                    # Check if target player is eliminated
                    if target_board.all_ships_sunk():
                        send_to_player(player_idx, f"\n[INFO] You've sunk all of Player {target_player_num}'s ships!\n\n")
                        send_to_player(target_player_idx, "[INFO] All your ships have been sunk. You are eliminated!\n\n")
                        send_to_all_players(f"[INFO] Player {target_player_num} has been eliminated by Player {player_idx + 1}!\n\n", 
                                        exclude_idx=[player_idx, target_player_idx])
                        
                        # Remove the eliminated player (with check to prevent the bug)
                        if target_player_idx in active_players:  # Check if player is still in the list
                            active_players.remove(target_player_idx)
                            eliminated_players.add(target_player_idx)
                        
                        # Check if only one player remains
                        if len(active_players) <= 1:
                            if active_players:
                                winner_idx = active_players[0]
                                send_to_player(winner_idx, "[INFO] You are the last player standing. You win!\n\n")
                                send_to_all_players(f"[INFO] Player {winner_idx + 1} wins the game!\n", exclude_idx=winner_idx)
                            return False
                    
                elif result == 'miss':
                    send_to_player(player_idx, f"\n[INFO] MISS on Player {target_player_num}'s board!\n")
                    send_to_player(target_player_idx, f"[INFO] Player {player_idx + 1} fired at {coord_str} and missed.\n")
                    send_to_all_players(f"[INFO] Player {player_idx + 1} missed when firing at Player {target_player_num}!\n", 
                                    exclude_idx=[player_idx, target_player_idx])
                
                elif result == 'already_shot':
                    send_to_player(player_idx, f"\n[INFO]You've already fired at that location on Player {target_player_num}'s board. Try again.\n")
                    return None
            
            except ValueError as e:
                send_to_player(player_idx, f"\n[TIP] Invalid input: {e}\n")
                return None
            
            return True

        except ConnectionResetError:
            # Handle player disconnection
            send_to_all_players(f"[INFO] Player {player_idx + 1} disconnected during their turn.\n\n", exclude_idx=player_idx)
            
            # Remove player from active list
            if player_idx in active_players:
                active_players.remove(player_idx)
                eliminated_players.add(player_idx)
            
            # Check if only one player remains
            if len(active_players) <= 1:
                if active_players:
                    winner_idx = active_players[0]
                    send_to_player(winner_idx, "[INFO] You are the last player standing. You win!\n\n")
                    send_to_all_players(f"[INFO] Player {winner_idx + 1} wins the game!\n\n", exclude_idx=winner_idx)
                return False
            
            return True
    
    # Main game loop
    while len(active_players) > 1:
        current_idx = active_players[current_player_idx]
        result = handle_player_turn(current_idx, is_retry=False)
        
        # Check the result of the turn
        if result is False:
            # Game ended
            break
        elif result is None:
            # Invalid move, retry with the same player, but mark as retry
            # This will prevent sending duplicate turn notifications
            while result is None:
                result = handle_player_turn(current_idx, is_retry=True)
                if result is False:
                    break

        # Additional check for active players after a successful turn
        if len(active_players) <= 1:
            # Game ended - only one or zero players left
            if active_players:
                winner_idx = active_players[0]
                send_to_player(winner_idx, "[INFO] You are the last player standing. You win!\n\n")
            break
            
        # Move to the next player
        current_player_idx = (active_players.index(current_idx) + 1) % len(active_players)

    # Game has ended, notify any remaining players
    for idx in active_players:
        send_to_player(idx, "[INFO] Game has ended.\n")