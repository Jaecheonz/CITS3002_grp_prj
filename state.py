from enum import Enum, auto

# Server state management
class ServerState(Enum):
    IDLE          = auto()   # waiting for first player of a brand-new game
    COUNTDOWN     = auto()   # 2 players present, countdown running
    SETUP         = auto()   # place ships phase in game
    IN_GAME       = auto()   # game_in_progress == True
    POST_GAME     = auto()   # cleaning up after a game, no new connections

server_state = ServerState.IDLE