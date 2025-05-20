# Battleship Online - Usage Instructions

## Requirements

- **Python 3.8+**
- **pycryptodomex** library
  Install with:
  ```
  pip install pycryptodomex
  ```

---

## Running the Server

1. Open a terminal.
2. Navigate to the project directory.
3. Start the server:
   ```
   python server.py
   ```
   - The server listens on `127.0.0.1:5000` by default.

---

## Running the Client

1. Open a new terminal for each player or spectator.
2. Navigate to the project directory.
3. Start the client:
   ```
   python client.py
   ```
   - The first two clients to connect are players; others are spectators.
   - Players will be prompted to place ships (randomly or manually).
   - Type `quit` to leave the game at any point during the GAME PHASE or POST GAME PHASE.

---

## Testing the Protocol

To run protocol tests and see logs:
```
python test_protocol.py
```
Results are saved in `protocol_test.log`.
Error logs are printed to `protocol_errors.log`, it may get really bloated after long testing periods, please clear it out once in a while
- This is to prevent lagging or issues occurring in the game due to the lag
---

## Notes
- Always fire after the initial 20s prompt has been sent, or any timer prompt in general, firing before it will not cause the game to break, it just might not be processed, so you will have to re-enter the same coordinate again. You will see the next prompt, usually at 10s, if you choose to wait for a new prompt to then fire. Do not worry, as long as you see the client message, you are still connected and the game can run fine.
- If you see errors about the port being in use, make sure no other process is using port 5000, or change the port in `server.py` and `client.py`.
- If a player disconnects, the game will pause and wait for the reconnection.
- Spectators can join during the game start countdown or during the game phase to view the game boards and enter the "waiting list" for them to be promoted when the original players quit.
- Sometimes, the game will freeze, this is due to severe packet corruption. Restarting the server for a new game will fix this issue.
- If you feel the game is freezing, wait for the Client message, as long as that arrives, the game is completely fine, else restart the server as above.
- We have used a very simple sum based checksum, but corruption can be VERY severe occasionally. We humbly request the tester to restart the server when it occurs.
- We can guarantee the game works as intended, as shown in the demo video, but the corruptions that happen really rarely due to implementing the checksum are unavoidable
- Thank you for having so much patience with our test files
---
