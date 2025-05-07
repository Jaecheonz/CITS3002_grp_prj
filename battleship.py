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

def run_multiplayer_game_online(reconnect_event, player_rfiles, player_wfiles, spectator_wfiles=None):
    """
    Run a Battleship game with 2 players and optional spectators.
    
    Args:
        player_rfiles: List of read file objects for players/spectators
        player_wfiles: List of write file objects for players/spectators
    """
    total_connections = len(player_rfiles)
    if total_connections < 2:
        raise ValueError("At least 2 connections required")
    
    # First two connections will be players, rest are spectators
    num_players = 2
    player_indices = [0, 1]  # Fixed player indices
    spectator_indices = list(range(2, total_connections))
    
    def send_to_connection(conn_idx, msg):
        if reconnect_event.is_set():
            print("[INFO] Waiting for a player to reconnect...\n")
        while reconnect_event.is_set():
            time.sleep(1)  # Wait for reconnection
        # Send a message to a specific connection (player or spectator)
        try:
            wfile = player_wfiles[conn_idx]
            # Check if the file is still valid/open
            if wfile.closed:
                raise BrokenPipeError("File already closed")
            
            wfile.write(msg + '\n')
            wfile.flush()
            return True
        except (BrokenPipeError, ConnectionError, ConnectionResetError, IOError) as e:
            print(f"[ERROR] Failed to send message to {'Player' if conn_idx < 2 else 'Spectator'} {conn_idx + 1}: {e}\n\n")
            '''
            # Handle disconnection based on if it's a player or spectator
            if conn_idx in player_indices:
                player_indices.remove(conn_idx)
                send_to_all_others(f"[INFO] Player {conn_idx + 1} disconnected from the game.\n\n", exclude_idx=conn_idx)
            elif conn_idx in spectator_indices:
                spectator_indices.remove(conn_idx)
            '''
    
    def send_to_all_others(msg, exclude_idx=None):
        # Send a message to all connections except excluded ones
        if exclude_idx is None:
            exclude_idx = []
        elif not isinstance(exclude_idx, list):
            exclude_idx = [exclude_idx]
            
        # Send to active players first
        for idx in player_indices:
            if idx not in exclude_idx:
                send_to_connection(idx, msg)
        
        # Then send to spectators
        for idx in spectator_indices:
            if idx not in exclude_idx:
                send_to_connection(idx, msg)
    
    def send_to_spectators(msg):
        # Helper function to send message only to spectators
        for idx in spectator_indices:
            send_to_connection(idx, msg)
    
    def send_board_to_connection(conn_idx, board_idx, board, show_hidden=False):
        # Send a board state to a connection
        try:
            wfile = player_wfiles[conn_idx]
            
            # Determine if this is the player's own board or opponent's board
            is_own_board = conn_idx == board_idx
            
            if conn_idx in player_indices:
                # This is a player
                board_owner = "Your" if is_own_board else "Opponent's"
            else:
                # This is a spectator
                board_owner = f"Player {board_idx + 1}'s"
            
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
            print(f"[ERROR] Failed to send board to {'Player' if conn_idx < 2 else 'Spectator'} {conn_idx + 1}: {e}\n\n")
            
            # Handle disconnection
            if conn_idx in player_indices:
                player_indices.remove(conn_idx)
                send_to_all_others(f"[INFO] Player {conn_idx + 1} disconnected from the game.\n\n", exclude_idx=conn_idx)
            elif conn_idx in spectator_indices:
                spectator_indices.remove(conn_idx)
            
            return False
    
    def handle_input_during_turn(player_idx, turn_timeout=15):
        # Keep track of which connections have already been warned
        warned_connections = set()

        # Timer variables
        start_time = time.time()
        time_remaining = turn_timeout
        
        # Track when reminders have been sent
        reminders_sent = set()  # Keep track of which reminders have been sent

        # Send initial timer message
        send_to_connection(player_idx, f"[INFO] Enter a coordinate ({time_remaining}s remaining)")

        while True:
            # Update timer
            elapsed_time = time.time() - start_time
            time_remaining = max(0, turn_timeout - int(elapsed_time))
            
            # Check if time has expired
            if time_remaining == 0:
                send_to_connection(player_idx, "[INFO] Time expired! You did not enter a coordinate, giving up your turn.")
                send_to_all_others(f"[INFO] Player {player_idx + 1} timed out and gave up their turn.", exclude_idx=player_idx)
                return "timeout"  # Return a special value to indicate timeout
            
            # Define reminder thresholds
            reminder_thresholds = [10, 5]  # Default reminders for 15s timer
            
            # Send reminders at appropriate times
            for threshold in reminder_thresholds:
                if time_remaining <= threshold and threshold not in reminders_sent:
                    send_to_connection(player_idx, f"[INFO] Enter a coordinate ({time_remaining}s remaining)")
                    reminders_sent.add(threshold)
                    break  # Only send one reminder at a time

            # Get list of file descriptors to check
            read_list = []
            fd_to_conn = {}  # Map file descriptors to connection indices
            
            # Collect valid file descriptors for all connections
            all_connections = player_indices + spectator_indices
            for i in all_connections:
                try:
                    fd = player_rfiles[i].fileno()
                    if fd >= 0:  # Check if it's a valid file descriptor
                        read_list.append(fd)
                        fd_to_conn[fd] = i
                except (ValueError, IOError):
                    # File descriptor is invalid or closed
                    if i in player_indices:
                        player_indices.remove(i)
                        send_to_all_others(f"[INFO] Player {i + 1} disconnected from the game.\n\n", exclude_idx=i)
                    elif i in spectator_indices:
                        spectator_indices.remove(i)
            
            # If there are no valid file descriptors, we can't continue
            if not read_list:
                time.sleep(0.1)
                continue
                
            # Use select to check which connections have input available
            try:
                readable, _, _ = select.select(read_list, [], [], 0.1)
                
                # Process readable file descriptors
                for fd in readable:
                    conn_i = fd_to_conn[fd]
                    
                    if conn_i == player_idx:
                        # It's this player's turn - get their input
                        try:
                            return recv_from_connection(conn_i)
                        except ConnectionResetError:
                            # Handle player disconnection
                            if conn_i in player_indices:
                                player_indices.remove(conn_i)
                                send_to_all_others(f"[INFO] Player {conn_i + 1} disconnected from the game.\n\n", exclude_idx=conn_i)
                            return 'problem'
                    else:
                        # Not this connection's turn
                        if conn_i in player_indices:
                            # This is the other player - warn them once
                            if conn_i not in warned_connections:
                                send_to_connection(conn_i, f"[WARNING] It's not your turn. Please wait for Player {player_idx + 1} to complete their turn.\n")
                                warned_connections.add(conn_i)
                        else:
                            # This is a spectator - remind them they're watching
                            if conn_i not in warned_connections:
                                send_to_connection(conn_i, f"[INFO] You are a spectator. Player {player_idx + 1} is currently taking their turn.\n")
                                warned_connections.add(conn_i)
                        
                        # Consume the input
                        try:
                            _ = recv_from_connection(conn_i)
                        except ConnectionResetError:
                            # Handle disconnection
                            if conn_i in player_indices:
                                player_indices.remove(conn_i)
                                send_to_all_others(f"[INFO] Player {conn_i + 1} disconnected from the game.\n\n", exclude_idx=conn_i)
                            elif conn_i in spectator_indices:
                                spectator_indices.remove(conn_i)
                    
            except (select.error, ValueError, IOError) as e:
                # Handle potential errors with select
                print(f"[ERROR] Select error: {e}")
                time.sleep(0.1)

    player_buffers = ["", ""]

    def recv_from_connection(conn_idx, timeout=None):
        try:
            # Check if there's data available to read without blocking
            if timeout is not None:
                # Set up select with timeout
                readable, _, _ = select.select([player_rfiles[conn_idx].fileno()], [], [], timeout)
                if not readable:
                    return None  # Timeout occurred, no data available
            
            # Read the line from the file-like object (not from socket)
            line = player_rfiles[conn_idx].readline()
            if not line:  # Empty string indicates disconnection
                raise ConnectionResetError(f"[INFO] {'Player' if conn_idx < 2 else 'Spectator'} {conn_idx + 1} disconnected\n\n")
            return line.strip()
        except (ConnectionError, IOError, ValueError) as e:
            # Catch broader range of connection issues
            raise ConnectionResetError(f"[INFO] {'Player' if conn_idx < 2 else 'Spectator'} {conn_idx + 1} disconnected: {str(e)}\n\n")
    
    # Create boards for the two players
    boards = [Board(BOARD_SIZE), Board(BOARD_SIZE)]
    
    # Inform all connections about their roles
    for idx in range(total_connections):
        if idx < 2:
            send_to_connection(idx, f"[INFO] You are Player {idx + 1}. SETUP PHASE: Place your ships. Type 'RANDOM' for random placement or 'MANUAL' for manual placement.\n")
        else:
            send_to_connection(idx, f"[INFO] You are a Spectator. Waiting for Players 1 and 2 to set up their ships.\n")
    
    # Setup phase - let players place their ships
    player_ready_events = [threading.Event(), threading.Event()]  # Only need events for the two players
    setup_success = [False, False]  # Track whether each player completed setup
    
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
            send_to_connection(player_idx, "[INFO] You have 1 minute to place your ships. Type 'RANDOM' for random placement or 'MANUAL' for manual placement.")
            placement = None
            
            # For manual placement, we need to track which ship we're placing
            current_ship_index = 0
            ships_to_place = list(SHIPS)  # Make a copy of the ships list
            manual_placement_started = False
            waiting_for_placement_input = False
            first_placement = True
            
            while True:
                # Check if we're out of time
                elapsed_time = time.time() - start_time
                remaining_time = time_limit - elapsed_time
                
                # Send time reminders
                for reminder_time in reminder_times:
                    if remaining_time <= reminder_time and reminder_time not in sent_reminders:
                        send_to_connection(player_idx, f"[TIME] {reminder_time} seconds remaining to place your ships!")
                        sent_reminders.add(reminder_time)
                
                # If time is up, place ships randomly
                if remaining_time <= 0:
                    send_to_connection(player_idx, "[TIME] Time's up! Placing ships randomly.")
                    player_board.place_ships_randomly(SHIPS)
                    send_to_connection(player_idx, "[INFO] Ships placed randomly due to time limit.")
                    send_board_to_connection(player_idx, player_idx, player_board, True)
                    break
                
                # If we're not waiting for a specific ship placement input,
                # wait for initial placement choice (RANDOM/MANUAL)
                if not manual_placement_started and not waiting_for_placement_input:
                    waiting_for_placement_input = True
                    placement = recv_from_connection(player_idx, timeout=min(remaining_time, 5))
                    waiting_for_placement_input = False
                    
                    # If we got no input, continue the loop to check time again
                    if placement is None:
                        continue
                    
                    if placement.lower() == 'quit':
                        send_to_connection(player_idx, "[INFO] You forfeited during setup.\n\n")
                        send_to_all_others(f"[INFO] Player {player_idx + 1} forfeited during setup.\n\n", exclude_idx=player_idx)
                        
                        # Mark this player as not successful
                        setup_success[player_idx] = False
                        
                        # Set this player's ready event
                        player_ready_events[player_idx].set()
                        return False
                    
                    elif placement.upper() == 'RANDOM':
                        player_board.place_ships_randomly(SHIPS)
                        send_to_connection(player_idx, "[INFO] Ships placed randomly.")
                        send_board_to_connection(player_idx, player_idx, player_board, True)
                        break
                    
                    elif placement.upper() == 'MANUAL':
                        # Start manual placement process
                        manual_placement_started = True
                        send_to_connection(player_idx, "[INFO] Placing ships manually:")
                        current_ship_index = 0
                    
                    else:
                        # Invalid placement option - ask player to try again
                        send_to_connection(player_idx, "[TIP] Invalid option. Please type 'RANDOM' for random placement or 'MANUAL' for manual placement.")
                        continue
                
                # Handle manual placement of ships
                if manual_placement_started:
                    if current_ship_index >= len(ships_to_place):
                        # All ships placed successfully
                        send_board_to_connection(player_idx, player_idx, player_board, True)
                        send_to_connection(player_idx, "[INFO] All ships placed successfully.")
                        break
                    
                    ship_name, ship_size = ships_to_place[current_ship_index]
                    
                    # Show current board state
                    if first_placement:
                        send_board_to_connection(player_idx, player_idx, player_board, True)
                        send_to_connection(player_idx, f"Placing {ship_name} (size {ship_size}). Enter starting coordinate and orientation (e.g., 'A1 H' or 'B5 V'):")
                        first_placement = False
                    
                    # use select to check the opponent's socket for disconnections
                    opponent_idx = 1 - player_idx
                    try:
                        readable, _, _ = select.select([player_rfiles[opponent_idx].fileno()], [], [], 0)
                        if readable:
                            opponent_line = player_rfiles[opponent_idx].readline()
                            if not opponent_line:
                                raise ConnectionResetError()
                    except (ConnectionResetError, OSError):
                        send_to_connection(player_idx, "[ALERT] Your opponent has disconnected. Setup aborted.\n\n")
                        setup_success[player_idx] = False
                        player_ready_events[player_idx].set()
                        return False
    
                    # Wait for placement input with timeout
                    waiting_for_placement_input = True
                    placement = recv_from_connection(player_idx, timeout=min(remaining_time, 0.1))  # Poll every 5 seconds max
                    waiting_for_placement_input = False
                    
                    # If we got no input, continue the loop to check time again
                    if placement is None:
                        continue
                    
                    if placement.lower() == 'quit':
                        send_to_connection(player_idx, "[INFO] You forfeited during setup.\n\n")
                        send_to_all_others(f"[INFO] Player {player_idx + 1} forfeited during setup.\n\n", exclude_idx=player_idx)
                        
                        # Mark this player as not successful
                        setup_success[player_idx] = False
                        
                        # Set this player's ready event
                        player_ready_events[player_idx].set()
                        return False
                    
                    try:
                        parts = placement.strip().split()
                        if len(parts) != 2:
                            send_to_connection(player_idx, "[TIP] Invalid format. Use 'COORD ORIENTATION' (e.g., 'A1 H')")
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
                            send_to_connection(player_idx, f"[INFO] {ship_name} placed successfully.")
                            current_ship_index += 1
                        else:
                            send_to_connection(player_idx, "[TIP] Cannot place ship there. Try again.")
                    except ValueError as e:
                        send_to_connection(player_idx, f"[TIP] Invalid input: {e}")
                        continue
            
            # Signal that this player is ready and wait for other player
            setup_success[player_idx] = True
            send_to_connection(player_idx, f"[INFO] Your ships are placed. Waiting for the other player to finish placing their ships...\n")
            
            # Update spectators
            send_to_spectators(f"[INFO] Player {player_idx + 1} has finished placing their ships.\n")
            
            player_ready_events[player_idx].set()
            return True
            
        except ConnectionResetError:
            # Player disconnected
            send_to_all_others(f"[INFO] Player {player_idx + 1} disconnected during setup.\n\n", exclude_idx=player_idx)
            
            # Mark this player as not successful
            setup_success[player_idx] = False
            
            # Set this player's ready event
            player_ready_events[player_idx].set()
            return False
    
    # Create and start threads for each player's setup
    setup_threads = []
    for i in range(2):  # Only the first two connections are players
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
    for i in range(2):
        if not player_ready_events[i].is_set() or not setup_success[i]:
            # Remove player from active player list
            if i in player_indices:
                player_indices.remove(i)
    
    # Check if we have enough players to continue
    if len(player_indices) < 2:
        send_to_all_others("[INFO] Not enough players completed setup. Game canceled.\n\n")
        return
    
    # Gameplay phase
    for idx in player_indices:
        send_to_connection(idx, f"[INFO] GAME PHASE: All ships have been placed. Game is starting!\n")
    
    # Inform spectators
    send_to_spectators("[INFO] Both players have placed their ships. The game is now starting!")
    
    # Determine starting player (always player 0 in this two-player version)
    current_player_idx = 0
    
    def handle_player_turn(player_idx, is_retry=False):
        # Handle a player's turn.
        # Returns:
        #     True: Turn completed successfully
        #     False: Game should end
        #     None: Invalid move, retry
        try:
            # First, show both boards to the current player
            send_to_connection(player_idx, "Your board:")
            send_board_to_connection(player_idx, player_idx, boards[player_idx], True)
            
            # Determine opponent index (the other player)
            opponent_idx = 1 if player_idx == 0 else 0
            
            send_to_connection(player_idx, "Opponent's board:")
            send_board_to_connection(player_idx, opponent_idx, boards[opponent_idx], False)
            
            # Let the other player and spectators know whose turn it is
            if not is_retry:
                send_to_connection(opponent_idx, f"[INFO] Player {player_idx + 1}'s turn. Please wait...\n")
                send_to_spectators(f"[INFO] Player {player_idx + 1}'s turn.\n")
                
                # Show spectators both boards (opponent's without hidden ships)
                for spec_idx in spectator_indices:
                    send_board_to_connection(spec_idx, player_idx, boards[player_idx], False)
                    send_board_to_connection(spec_idx, opponent_idx, boards[opponent_idx], False)
            
            # Player's turn to fire
            send_to_connection(player_idx, "[INFO] Your turn!\n\n [TIP] Enter a coordinate to fire at (e.g., 'B5'):")
            
            # Get input with timeout
            fire_input = handle_input_during_turn(player_idx, turn_timeout=15)  # 15 second timeout

            if fire_input == "timeout":
                return True  # Continue game with next player
            
            try:
                if fire_input.strip().lower() == 'quit':
                    send_to_connection(player_idx, "[INFO] You forfeited the game.\n")
                    send_to_connection(opponent_idx, f"[INFO] Player {player_idx + 1} forfeited. You win!\n")
                    send_to_spectators(f"[INFO] Player {player_idx + 1} forfeited. Player {opponent_idx + 1} wins!\n")
                    return False
            
                # Parse coordinate and fire
                coord_str = fire_input.strip()
                row, col = parse_coordinate(coord_str)
                target_board = boards[opponent_idx]
                result, sunk_name = target_board.fire_at(row, col)
                
                # Notify players and spectators of the result
                if result == 'hit':
                    if sunk_name:
                        # Ship sunk
                        send_to_connection(player_idx, f"\n[INFO] HIT! You sank your opponent's {sunk_name}!\n\n")
                        send_to_connection(opponent_idx, f"[INFO] Your {sunk_name} was sunk!\n\n")
                        send_to_spectators(f"[INFO] Player {player_idx + 1} sank Player {opponent_idx + 1}'s {sunk_name}!\n\n")
                        
                        # Check if all opponent's ships are sunk
                        if target_board.all_ships_sunk():
                            send_to_connection(player_idx, "\n[INFO] You've sunk all of your opponent's ships! You win!\n\n")
                            send_to_connection(opponent_idx, "[INFO] All your ships have been sunk. You lose!\n\n")
                            send_to_spectators(f"[INFO] Player {player_idx + 1} has won the game by sinking all of Player {opponent_idx + 1}'s ships!\n\n")
                            return False
                    else:
                        # Just a hit
                        send_to_connection(player_idx, f"\n[INFO] HIT!\n\n")
                        send_to_connection(opponent_idx, f"[INFO] Your ship at {coord_str} was hit!\n\n")
                        send_to_spectators(f"[INFO] Player {player_idx + 1} hit Player {opponent_idx + 1}'s ship at {coord_str}!\n\n")
                    
                elif result == 'miss':
                    send_to_connection(player_idx, f"\n[INFO] MISS!\n")
                    send_to_connection(opponent_idx, f"[INFO] Player {player_idx + 1} fired at {coord_str} and missed.\n")
                    send_to_spectators(f"[INFO] Player {player_idx + 1} fired at {coord_str} and missed.\n")
                
                elif result == 'already_shot':
                    send_to_connection(player_idx, f"\n[INFO] You've already fired at that location. Try again.\n")
                    return None
            
            except ValueError as e:
                send_to_connection(player_idx, f"\n[TIP] Invalid input: {e}\n")
                return None
            
            return True

        except ConnectionError:
            '''
            # Handle player disconnection
            opponent_idx = 1 if player_idx == 0 else 0
            
            send_to_connection(opponent_idx, f"[INFO] Player {player_idx + 1} disconnected. You win by default!\n\n")
            send_to_spectators(f"[INFO] Player {player_idx + 1} disconnected. Player {opponent_idx + 1} wins by default!\n\n")
            return False
            '''
    
    # Main game loop
    current_player_idx = 0  # Start with Player 1
    while len(player_indices) == 2:
        result = handle_player_turn(current_player_idx, is_retry=False)
        
        # Check the result of the turn
        if result is False:
            # Game ended
            break
        elif result is None:
            # Invalid move, retry with the same player
            while result is None:
                result = handle_player_turn(current_player_idx, is_retry=True)
                if result is False:
                    break
        else:
            # Valid move, switch to other player
            current_player_idx = 1 if current_player_idx == 0 else 0

    # Game has ended, final message
    for idx in player_indices + spectator_indices:
        send_to_connection(idx, "[INFO] Game has ended.\n")