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
    # Define active players (first two players) and spectators (everyone else)
    active_players = list(range(min(2, num_players)))  # First two players
    spectator_players = list(range(2, num_players))  # Everyone else

    def send_to_player(player_idx, msg):
        # Send a message to a specific player.
        if player_idx not in active_players and player_idx not in spectator_players:
            return False
            
        try:
            wfile = player_wfiles[player_idx]
            # Check if the file is still valid/open
            if wfile.closed:
                raise BrokenPipeError("File already closed")
            
            wfile.write(msg + '\n')
            wfile.flush()
            return True
        except (BrokenPipeError, ConnectionError, ConnectionResetError, IOError) as e:
            handle_player_disconnect(player_idx)
            return False
    
    def send_to_all_spectators(msg):
        for idx in spectator_players:
            send_to_player(idx, msg)

    def update_spectators_game_state():
        for spec_idx in spectator_players:
            send_to_player(spec_idx, "[INFO] Current game state:")
            for active_idx in active_players:
                send_board_to_player(spec_idx, active_idx, boards[active_idx], False)

    def handle_player_disconnect(player_idx):
        setup_success[player_idx] = False
        player_ready_events[player_idx].set()

        if player_idx in active_players:
            other_player_idx = active_players[0] if player_idx == active_players[1] else active_players[1]
            send_to_player(other_player_idx, f"[INFO] Player {player_idx + 1} disconnected. You win!\n\n")
            send_to_all_spectators(f"[INFO] Player {player_idx + 1} disconnected. Player {other_player_idx + 1} wins!\n\n")
            send_to_all_players("[INFO] Game has ended.", include_spectators=True)
            return False  # Signal game end
        
        elif player_idx in spectator_players:
            spectator_players.remove(player_idx)
            send_to_all_spectators(f"[INFO] A spectator (Player {player_idx + 1}) has disconnected.\n")
        
        return True  # Continue game

    # Inform each player of their role
    for idx in active_players:
        send_to_player(idx, f"[INFO] You are Player {idx + 1} (Active player)\n")
    for idx in spectator_players:
        send_to_player(idx, f"[INFO] You are a spectator. You can watch the game but cannot participate.\n")
    
    # Modify send_to_all_players to include a parameter for spectators:
    def send_to_all_players(msg, exclude_idx=None, include_spectators=True):
        # Send to active players
        if exclude_idx is None:
            exclude_idx = []
        elif not isinstance(exclude_idx, list):
            exclude_idx = [exclude_idx]
            
        for idx in active_players:
            if idx not in exclude_idx:
                send_to_player(idx, msg)
        
        # Send to spectators if specified
        if include_spectators:
            for idx in spectator_players:
                if idx not in exclude_idx:
                    send_to_player(idx, msg)

    def check_opponent_forfeit(player_idx):
        for idx in range(len(player_ready_events)):
            if idx == player_idx:
                continue
            if player_ready_events[idx].is_set() and setup_success[idx] is False:
                send_to_player(player_idx, "[INFO] Opponent has forfeited during setup. Game cannot continue.\n")
                setup_success[player_idx] = False
                player_ready_events[player_idx].set()
                return True
        return False

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
            handle_player_disconnect(player_idx)
            return False
        
    def recv_from_player(player_idx, timeout=None):
        try:
            # Check if there's data available to read without blocking
            if timeout is not None:
                # Set up select with timeout
                readable, _, _ = select.select([player_rfiles[player_idx].fileno()], [], [], timeout)
                if not readable:
                    return None  # Timeout occurred, no data available
            
            # Read the line
            line = player_rfiles[player_idx].readline().strip()
            if not line:  # Empty string indicates disconnection
                handle_player_disconnect(player_idx)
                return False
            
            # Return the received line
            return line
            
        except (ConnectionError, IOError, ValueError) as e:
            handle_player_disconnect(player_idx)
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
            for i in active_players + spectator_players:  # Include spectators in our check
                try:
                    fd = player_rfiles[i].fileno()
                    if fd >= 0:  # Check if it's a valid file descriptor
                        read_list.append(fd)
                        fd_to_player[fd] = i
                except (ValueError, IOError):
                    # File descriptor is invalid or closed
                    handle_player_disconnect(i)
                    return False
            
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
                            handle_player_disconnect(player_idx)
                            return False
                    else:
                        # Not this player's turn
                        # Check if they're a spectator
                        if player_i in spectator_players:
                            # It's a spectator - ignore their input but warn them
                            try:
                                _ = recv_from_player(player_i)
                                send_to_player(player_i, "[WARNING] Spectators cannot participate. You can only watch the game.\n")
                            except ConnectionResetError:
                                handle_player_disconnect(player_i)
                                return False
                        else:
                            # It's another active player - warn them once
                            if player_i not in warned_players:
                                send_to_player(player_i, f"[WARNING] It's not your turn. Please wait for Player {player_idx + 1} to complete their turn.\n")
                                warned_players.add(player_i)
                            
                            # Consume the input
                            try:
                                _ = recv_from_player(player_i)
                            except ConnectionResetError:
                                handle_player_disconnect(player_i)
                                return False
                        
            except (select.error, ValueError, IOError) as e:
                # Handle potential errors with select
                print(f"[ERROR] Select error: {e}")
                time.sleep(0.1)
    
    # Create boards for all players
    boards = [Board(BOARD_SIZE) for _ in range(2)]
    
    # Setup phase - let all players place their ships concurrently using threads
    for idx in range(2):
        send_to_player(idx, f"[INFO] SETUP PHASE: Place your ships. Type 'RANDOM' for random placement or 'MANUAL' for manual placement.\n")
    
    # Using threading Event objects to synchronise the players
    player_ready_events = [threading.Event() for _ in range(2)]
    setup_success = [False] * 2  # Track whether each player completed setup successfully
    
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
            input_prompt_sent = False
            current_ship_index = 0
            ships_to_place = list(SHIPS)  # Make a copy of the ships list
            manual_placement_started = False
            waiting_for_placement_input = False
            
            while True:
                if check_opponent_forfeit(player_idx):
                    return False
                
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
                    # Use a shorter timeout to check more frequently if opponent quits
                    placement = recv_from_player(player_idx, timeout=min(remaining_time, 0.1))
                    waiting_for_placement_input = False
                    
                    # If we got no input, continue the loop to check time again
                    if placement is None:
                        if check_opponent_forfeit(player_idx):
                            return False
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
                        setup_success[player_idx] = True
                        player_ready_events[player_idx].set()
                        send_to_player(player_idx, f"[INFO] Your ships are placed. Waiting for other players to finish placing their ships...\n")
                        return True
                    
                    ship_name, ship_size = ships_to_place[current_ship_index]
                    
                    # Show current board state and prompt, but only if we haven't shown it already
                    if not input_prompt_sent:
                        send_board_to_player(player_idx, player_idx, player_board, True)
                        send_to_player(player_idx, f"Placing {ship_name} (size {ship_size}). Enter starting coordinate and orientation (e.g., 'A1 H' or 'B5 V'):")
                        input_prompt_sent = True
                    
                    # Wait for placement input with a short timeout to keep timer accurate and check opponent status
                    placement = recv_from_player(player_idx, timeout=min(remaining_time, 0.1))
                    
                    if placement is None:
                        if check_opponent_forfeit(player_idx):
                            return False
                        continue
                    
                    # We got input, so reset the prompt flag
                    input_prompt_sent = False
                    
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
    
    def handle_player_turn(player_idx, is_retry=False):
        # Handle a player's turn.
        # Args:
        #     player_idx: Index of the player whose turn it is
        # Returns:
        #     True: Turn completed successfully
        #     False: Game should end
        #     None: Invalid move, retry
        nonlocal active_players, current_turn_player
        
        try:
            current_turn_player = player_idx
            
            # First, show the player their own board with ships
            send_to_player(player_idx, "Your board:")
            send_board_to_player(player_idx, player_idx, boards[player_idx], True)
            
            # Show opponent board - simplified for exactly two players
            target_player_idx = active_players[0] if player_idx == active_players[1] else active_players[1]
            send_to_player(player_idx, f"Player {target_player_idx + 1}'s board:")
            send_board_to_player(player_idx, target_player_idx, boards[target_player_idx], False)
            
            # Let other players know whose turn it is - only if this is not a retry
            if not is_retry:
                for idx in active_players:
                    if idx != player_idx:
                        send_to_player(idx, f"[INFO] Player {player_idx + 1}'s turn. Please wait...\n")
                send_to_all_spectators(f"[INFO] Player {player_idx + 1}'s turn is starting.\n")
            
            send_to_player(player_idx, "[INFO] Your turn! Enter a coordinate to fire at (e.g., 'B5'):")
            fire_input = handle_input_during_turn(player_idx, turn_timeout=15)

            if fire_input == "timeout":
                send_to_all_spectators(f"[INFO] Player {player_idx + 1} timed out and gave up their turn.")
                return True
            elif fire_input.lower() == "quit":
                handle_player_disconnect(player_idx)
                return False

            try:
                # Parse coordinate and fire - simplified to only expect coordinates
                coord_str = fire_input.strip().upper()
                row, col = parse_coordinate(coord_str)
                
                # Determine the target player automatically
                target_player_idx = active_players[0] if player_idx == active_players[1] else active_players[1]
                target_player_num = target_player_idx + 1
                
                target_board = boards[target_player_idx]
                result, sunk_name = target_board.fire_at(row, col)
                
                # Notify players of the result
                if result == 'hit':
                    if sunk_name:
                        send_to_player(player_idx, f"\n[INFO] HIT! You sank Player {target_player_num}'s {sunk_name}!\n\n")
                        send_to_player(target_player_idx, f"[INFO] Your {sunk_name} was sunk by Player {player_idx + 1}!\n\n")
                        send_to_all_spectators(f"[INFO] Player {player_idx + 1} sank Player {target_player_num}'s {sunk_name}!\n\n")
    
                    else:
                        send_to_player(player_idx, f"\n[INFO] HIT on Player {target_player_num}'s ship!\n\n")
                        send_to_player(target_player_idx, f"[INFO] Your ship at {coord_str} was hit by Player {player_idx + 1}!\n\n")
                        send_to_all_spectators(f"[INFO] Player {player_idx + 1} hit Player {target_player_num}'s ship at {coord_str}!\n\n")

                    if target_board.all_ships_sunk():
                        send_to_player(player_idx, f"\n[INFO] You've sunk all of Player {target_player_num}'s ships! You win!\n\n")
                        send_to_player(target_player_idx, "[INFO] All your ships have been sunk. You lose!\n\n")
                        send_to_all_spectators(f"[INFO] Player {player_idx + 1} won by sinking all of Player {target_player_num}'s ships!\n\n")
                        
                        # Game is now over
                        send_to_all_players("[INFO] Game has ended.", include_spectators=True)
                        return False  # Signal game end
                    
                elif result == 'miss':
                    send_to_player(player_idx, f"\n[INFO] MISS on Player {target_player_num}'s board!\n")
                    send_to_player(target_player_idx, f"[INFO] Player {player_idx + 1} fired at {coord_str} and missed.\n")
                    send_to_all_spectators(f"[INFO] Player {player_idx + 1} fired at {coord_str} on Player {target_player_num}'s board and missed.\n")
                
                elif result == 'already_shot':
                    send_to_player(player_idx, f"\n[INFO]You've already fired at that location on Player {target_player_num}'s board. Try again.\n")
                    return None
            
            except ValueError as e:
                send_to_player(player_idx, f"\n[TIP] Invalid input: {e}\n")
                return None
            
            return True

        except ConnectionResetError:
            handle_player_disconnect(player_idx)
            return False
    
    # Main game loop
    while len(active_players) > 1:
        update_spectators_game_state()

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
        else:
            update_spectators_game_state()
            
            # Notify spectators whose turn is next
            next_player_idx = active_players[(active_players.index(current_idx) + 1) % len(active_players)]
            send_to_all_spectators(f"[INFO] Next turn: Player {next_player_idx + 1}\n")
            
        # Move to the next player
        current_player_idx = (active_players.index(current_idx) + 1) % len(active_players)