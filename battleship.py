"""
battleship.py

Contains core data structures and logic for Battleship, including:
- Board class for storing ship positions, hits, misses
- Utility function parse_coordinate for translating e.g. 'B5' -> (row, col)
- A test harness run_single_player_game() to demonstrate the logic in a local, single-player mode

"""

import random
import threading

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
    """
    Convert something like 'B5' into zero-based (row, col).
    Example: 'A1' => (0, 0), 'C10' => (2, 9)
    HINT: you might want to add additional input validation here...
    """
    # check for correct input length
    coord_str = coord_str.strip().upper()
    if not coord_str or not (2 <= len(coord_str) <= 3):
        raise ValueError("Coordinate must be at least 2 characters and no more than 3 (e.g. A10)")
    
    # check for row letter within bounds
    row_letter = coord_str[0]
    if not ('A' <= row_letter <= 'J'):
        raise ValueError(f"Row must be within A-J, got '{row_letter}'")
    
    # check for column number being a number
    col_digits = coord_str[1:]
    try:
        col_num = int(col_digits)
    except ValueError:
        raise ValueError(f"Column must be a number, got '{col_digits}'")

    # check for column number within bounds
    if not (1 <= col_num <= 10):
        raise ValueError(f"Column must be within 1-10, got {col_num}")
    
    row = ord(row_letter) - ord('A')
    col = int(col_digits) - 1  # zero-based

    return (row, col)

def run_two_player_game(rfile1, wfile1, rfile2, wfile2):
    """
    Run a two-player Battleship game with I/O redirected to socket file objects.
    
    Args:
        rfile1, wfile1: file-like objects for player 1
        rfile2, wfile2: file-like objects for player 2
    """
    def send_to_player(player_num, msg):
        """Send a message to the specified player"""
        if player_num == 1:
            wfile1.write(msg + '\n')
            wfile1.flush()
        else:
            wfile2.write(msg + '\n')
            wfile2.flush()
    
    def send_board_to_player(player_num, board, show_hidden=False):
        """Send the current board state to the specified player"""
        wfile = wfile1 if player_num == 1 else wfile2
        wfile.write("GRID\n")
        
        # Which grid to display depends on whether we're showing hidden ships
        grid_to_show = board.hidden_grid if show_hidden else board.display_grid
        
        # Column headers
        wfile.write("  " + " ".join(str(i + 1).rjust(2) for i in range(board.size)) + '\n')
        
        # Each row with label
        for r in range(board.size):
            row_label = chr(ord('A') + r)
            row_str = " ".join(grid_to_show[r][c] for c in range(board.size))
            wfile.write(f"{row_label:2} {row_str}\n")
        
        wfile.write('\n')
        wfile.flush()
    
    def recv_from_player(player_num):
        """Receive a message from the specified player"""
        if player_num == 1:
            return rfile1.readline().strip()
        else:
            return rfile2.readline().strip()
    
    # Create boards for both players
    board1 = Board(BOARD_SIZE)  # Player 1's board (that player 2 fires at)
    board2 = Board(BOARD_SIZE)  # Player 2's board (that player 1 fires at)
    
    # Setup phase - let both players place their ships concurrently using threads
    send_to_player(1, "SETUP PHASE: Place your ships. Type 'RANDOM' for random placement or 'MANUAL' for manual placement.")
    send_to_player(2, "SETUP PHASE: Place your ships. Type 'RANDOM' for random placement or 'MANUAL' for manual placement.")
    
    # Using threading Event objects to synchronize the two players
    player1_ready = threading.Event()
    player2_ready = threading.Event()
    
    # Define a generic function to handle ship placement for either player
    def setup_player_ships(player_num, player_board, player_ready_event, other_player_ready_event):
        """Generic function to handle ship placement for any player"""
        other_player = 3 - player_num  # If player_num is 1, other is 2; if player_num is 2, other is 1
        
        placement = recv_from_player(player_num)
        if placement.lower() == 'quit':
            send_to_player(player_num, "You forfeited the game.")
            send_to_player(other_player, "Your opponent forfeited during setup. You win!")
            
            # Set both events to allow threads to exit
            player1_ready.set()
            player2_ready.set()
            return False
        elif placement.upper() == 'RANDOM':
            player_board.place_ships_randomly(SHIPS)
            send_to_player(player_num, "Ships placed randomly.")
            send_board_to_player(player_num, player_board, True)  # Show player their board with ships
        elif placement.upper() == 'MANUAL':
            # Handle manual placement
            send_to_player(player_num, "Placing ships manually:")
            for ship_name, ship_size in SHIPS:
                placed = False
                while not placed:
                    send_board_to_player(player_num, player_board, True)  # Always show the current state
                    send_to_player(player_num, f"Placing {ship_name} (size {ship_size}). Enter starting coordinate and orientation (e.g., 'A1 H' or 'B5 V'):")
                    try:
                        placement = recv_from_player(player_num)
                        if placement.lower() == 'quit':
                            send_to_player(player_num, "You forfeited the game.")
                            send_to_player(other_player, "Your opponent forfeited during setup. You win!")
                            # Set both events to allow threads to exit
                            player1_ready.set()
                            player2_ready.set()
                            return False
                        
                        parts = placement.strip().split()
                        if len(parts) != 2:
                            send_to_player(player_num, "Invalid format. Use 'COORD ORIENTATION' (e.g., 'A1 H')")
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
                            send_to_player(player_num, f"{ship_name} placed successfully.")
                            placed = True
                        else:
                            send_to_player(player_num, "Cannot place ship there. Try again.")
                    except ValueError as e:
                        send_to_player(player_num, f"Invalid input: {e}")
            
            # Show final board after all ships placed
            send_board_to_player(player_num, player_board, True)
        else:
            # Invalid placement option - ask player to try again
            send_to_player(player_num, "Invalid option. Please type 'RANDOM' for random placement or 'MANUAL' for manual placement.")
            # Recursively call the function again to get valid input
            return setup_player_ships(player_num, player_board, player_ready_event, other_player_ready_event)
        
        # Signal that this player is ready and wait for the other player
        player_ready_event.set()
        send_to_player(player_num, f"Your ships are placed. Waiting for Player {other_player} to finish placing their ships...")
        other_player_ready_event.wait()  # Wait for other player to finish
        return True
    
    # Create and start threads for each player's setup
    p1_setup_thread = threading.Thread(
        target=setup_player_ships,
        args=(1, board1, player1_ready, player2_ready)
    )
    
    p2_setup_thread = threading.Thread(
        target=setup_player_ships,
        args=(2, board2, player2_ready, player1_ready)
    )
    
    p1_setup_thread.start()
    p2_setup_thread.start()
    
    # Wait for both threads to complete
    p1_setup_thread.join()
    p2_setup_thread.join()
    
    # Check if setup was completed successfully
    if not (player1_ready.is_set() and player2_ready.is_set()):
        # If either event is not set, it means there was an error or forfeit
        return
    
    # Gameplay phase
    send_to_player(1, "GAME PHASE: All ships have been placed. Game is starting!")
    send_to_player(2, "GAME PHASE: All ships have been placed. Game is starting!")
    
    current_player = 1  # Player 1 goes first
    
    def handle_player_turn(player_num, player_board, opponent_board):
        """Generic function to handle a player's turn in the game"""
        other_player = 3 - player_num  # If player_num is 1, other is 2; if player_num is 2, other is 1
        
        # Show player their own board with ships
        send_to_player(player_num, "Your board:")
        send_board_to_player(player_num, player_board, True)
        # Show player their opponent's board without ships
        send_to_player(player_num, "Opponent's board:")
        send_board_to_player(player_num, opponent_board, False)
        
        # Player's turn to fire
        send_to_player(player_num, "Your turn! Enter a coordinate to fire at (e.g., 'B5'):")
        send_to_player(other_player, "Opponent's turn. Please wait...")
        
        # Get player's move
        fire_coord = recv_from_player(player_num)
        if fire_coord.lower() == 'quit':
            send_to_player(player_num, "You forfeited the game.")
            send_to_player(other_player, "Your opponent forfeited. You win!")
            return False
            
        try:
            row, col = parse_coordinate(fire_coord)
            result, sunk_name = opponent_board.fire_at(row, col)
            
            # Notify both players of the result
            if result == 'hit':
                if sunk_name:
                    send_to_player(player_num, f"HIT! You sank their {sunk_name}!")
                    send_to_player(other_player, f"Your {sunk_name} was sunk!")
                else:
                    send_to_player(player_num, "HIT!")
                    send_to_player(other_player, f"Your ship at {fire_coord} was hit!")
                
                # Check if this player won
                if opponent_board.all_ships_sunk():
                    send_to_player(player_num, "Congratulations! You've sunk all your opponent's ships. You win!")
                    send_to_player(other_player, "All your ships have been sunk. Game over!")
                    return False
            elif result == 'miss':
                send_to_player(player_num, "MISS!")
                send_to_player(other_player, f"Your opponent fired at {fire_coord} and missed.")
            elif result == 'already_shot':
                send_to_player(player_num, "You've already fired at that location. Try again.")
                # Return None to indicate we should retry with the same player
                return None
        except ValueError as e:
            send_to_player(player_num, f"Invalid input: {e}")
            # Return None to indicate we should retry with the same player
            return None
        
        # Return True to indicate successful turn completion
        return True
    
    while True:
        if current_player == 1:
            result = handle_player_turn(1, board1, board2)
        else:
            result = handle_player_turn(2, board2, board1)
        
        # Check the result of the turn
        if result is False:
            # Game ended (someone quit or won)
            break
        elif result is None:
            # Invalid move, retry with the same player
            continue
        else:
            # Valid move, switch to the other player
            current_player = 3 - current_player