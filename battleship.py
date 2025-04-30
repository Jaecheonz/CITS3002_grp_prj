# battleship.py
# Contains core data structures and logic for Battleship, including:
# - Board class for storing ship positions, hits, misses
# - Utility function parse_coordinate for translating e.g. 'B5' -> (row, col)

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
            player_wfiles[player_idx].write(msg + '\n')
            player_wfiles[player_idx].flush()
            return True
        except (BrokenPipeError, ConnectionError, ConnectionResetError) as e:
            print(f"[ERROR] Failed to send message to Player {player_idx + 1}: {e}\n\n")
            # Remove disconnected player from active players
            if player_idx in active_players:  # Check if player is still in the list
                active_players.remove(player_idx)
                eliminated_players.add(player_idx)
                # Notify other players about the disconnection
                for idx in active_players:
                    try:
                        player_wfiles[idx].write(f"Player {player_idx + 1} disconnected from the game.\n")
                        player_wfiles[idx].flush()
                    except:
                        pass  # If this also fails, it will be caught next time
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
    
    def recv_from_player(player_idx):
        # Receive input from a player.
        try:
            return player_rfiles[player_idx].readline().strip()
        except ConnectionError:
            raise ConnectionResetError(f"[INFO] Player {player_idx + 1} disconnected\n\n")
    
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
    
    # Define a function to handle ship placement for any player
    def setup_player_ships(player_idx):
        nonlocal setup_success
        
        try:
            player_board = boards[player_idx]
            placement = recv_from_player(player_idx)
            
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
                send_board_to_player(player_idx, player_idx, player_board, True)  # Show player their board with ships
                
            elif placement.upper() == 'MANUAL':
                # Handle manual placement
                send_to_player(player_idx, "[INFO] Placing ships manually:")
                for ship_name, ship_size in SHIPS:
                    placed = False
                    while not placed:
                        send_board_to_player(player_idx, player_idx, player_board, True)  # Always show the current state
                        send_to_player(player_idx, f"Placing {ship_name} (size {ship_size}). Enter starting coordinate and orientation (e.g., 'A1 H' or 'B5 V'):")
                        try:
                            placement = recv_from_player(player_idx)
                            if placement.lower() == 'quit':
                                send_to_player(player_idx, "[INFO] You forfeited during setup.\n\n")
                                send_to_all_players(f"[INFO] Player {player_idx + 1} forfeited during setup.\n\n", exclude_idx=player_idx)
                                
                                # Mark this player as not successful
                                setup_success[player_idx] = False
                                
                                # Set this player's ready event
                                player_ready_events[player_idx].set()
                                return False
                            
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
                                placed = True
                            else:
                                send_to_player(player_idx, "[TIP] Cannot place ship there. Try again.")
                        except ValueError as e:
                            send_to_player(player_idx, f"[TIP] Invalid input: {e}")
                        except ConnectionResetError:
                            # Player disconnected during ship placement
                            send_to_all_players(f"[INFO] Player {player_idx + 1} disconnected during setup.\n\n", exclude_idx=player_idx)
                            
                            # Mark this player as not successful
                            setup_success[player_idx] = False
                            
                            # Set this player's ready event
                            player_ready_events[player_idx].set()
                            return False
                
                # Show final board after all ships placed
                send_board_to_player(player_idx, player_idx, player_board, True)
            
            else:
                # Invalid placement option - ask player to try again
                send_to_player(player_idx, "[TIP] Invalid option. Please type 'RANDOM' for random placement or 'MANUAL' for manual placement.")
                # Recursively call the function again to get valid input
                return setup_player_ships(player_idx)
            
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
        send_to_player(idx, f"GAME PHASE: All ships have been placed. Game is starting with {len(active_players)} players!\n")
    
    # Initialise player states
    current_player_idx = 0  # Index into active_players list
    eliminated_players = set()
    
    def handle_player_turn(player_idx):
        # Handle a player's turn.
        # Args:
        #     player_idx: Index of the player whose turn it is
        # Returns:
        #     True: Turn completed successfully
        #     False: Game should end
        #     None: Invalid move, retry
        nonlocal active_players, eliminated_players
        
        try:
            # First, show the player their own board with ships
            send_to_player(player_idx, "Your board:")
            send_board_to_player(player_idx, player_idx, boards[player_idx], True)
            
            # Show all opponent boards
            for opponent_idx in active_players:
                if opponent_idx != player_idx:
                    send_to_player(player_idx, f"Player {opponent_idx + 1}'s board:")
                    send_board_to_player(player_idx, opponent_idx, boards[opponent_idx], False)
                    
            # Let other players know whose turn it is
            for idx in active_players:
                if idx != player_idx:
                    send_to_player(idx, f"[INFO] Player {player_idx + 1}'s turn. Please wait...\n")
            
            # Player's turn to fire
            send_to_player(player_idx, "[INFO] Your turn!\n\n [TIP] Enter a coordinate and player number to fire at (e.g., 'B5 3' to fire at B5 on Player 3's board):")
            
            # Get player's move
            fire_input = recv_from_player(player_idx)
            if fire_input.lower() == 'quit':
                send_to_all_players(f"[INFO] Player {player_idx + 1} forfeited.\n", exclude_idx=player_idx)
                
                # Remove player from active list (with check to prevent the bug)
                if player_idx in active_players:  # Check if player is still in the list
                    active_players.remove(player_idx)
                    eliminated_players.add(player_idx)
                
                # Check if only one player remains
                if len(active_players) <= 1:
                    if active_players:
                        winner_idx = active_players[0]
                        send_to_player(winner_idx, "[INFO] You are the last player standing. You win!")
                    return False
                return True
            
            try:
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
        result = handle_player_turn(current_idx)
        
        # Check the result of the turn
        if result is False:
            # Game ended
            break
        elif result is None:
            # Invalid move, retry with the same player
            continue
        else:
            # Additional check for active players after a successful turn
            if len(active_players) <= 1:
                # Game ended - only one or zero players left
                if active_players:
                    winner_idx = active_players[0]
                    send_to_player(winner_idx, "[INFO] You are the last player standing. You win!\n\n")
                break
            
            # Move to the next player
            current_player_idx = (current_player_idx + 1) % len(active_players)
    # Game has ended, notify any remaining players
    for idx in active_players:
        send_to_player(idx, "[INFO] Game has ended.\n")

# Helper function to initialise the game with n players
def initialise_multiplayer_game(n_players, socket_list):
    # Initialise a multiplayer game with n players.
    # Args:
    #     n_players: Number of players
    #     socket_list: List of connected client sockets
    if len(socket_list) < n_players:
        raise ValueError("[INFO] Not enough connected clients\n\n")
    
    player_rfiles = []
    player_wfiles = []
    
    # Set up file objects for each player
    for i in range(n_players):
        client_socket = socket_list[i]
        rfile = client_socket.makefile('r')
        wfile = client_socket.makefile('w')
        player_rfiles.append(rfile)
        player_wfiles.append(wfile)
    
    # Start the game
    run_multiplayer_game_online(player_rfiles, player_wfiles)