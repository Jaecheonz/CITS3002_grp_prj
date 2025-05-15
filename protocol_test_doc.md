# Protocol Specification

## Packet Structure
Each packet consists of a header and payload:

### Header (9 bytes)
- Packet Type (1 byte): Identifies the type of message
- Sequence Number (1 byte): Ensures ordered delivery
- Checksum (4 bytes): CRC-32 checksum for error detection
- Payload Length (2 bytes): Length of the payload in bytes

### Payload (variable length)
- The actual message content
- For string messages, automatically adds newline if missing

## Packet Types
1. GAME_UPDATE: General game state updates
2. PLAYER_MOVE: Player input/actions
3. BOARD_UPDATE: Board display updates
4. CHAT_MESSAGE: Chat messages
5. SYSTEM_MESSAGE: System notifications
6. RETRANSMISSION_REQUEST: Request for packet resend
7. ACK: Acknowledgment of received packet

## Checksum Mechanism
- Uses CRC-32 (zlib.crc32)
- Calculated on: packet type + sequence number + payload
- 4-byte checksum provides strong error detection
- Detects:
  - Bit flips
  - Missing bytes
  - Corrupted data
  - Out-of-order packets

## Error Handling Policy
1. Corrupted Packets:
   - Detected via checksum verification
   - Automatically discarded
   - Retransmission requested
   - Logged for monitoring

2. Out-of-Sequence Packets:
   - Detected via sequence numbers
   - Handled by retransmission mechanism
   - Ensures ordered delivery

3. Timeout Handling:
   - Configurable timeout period
   - Automatic retransmission on timeout
   - Maximum retry attempts

4. Logging:
   - All protocol errors logged
   - Includes timestamps and sequence numbers
   - Helps with debugging and monitoring

## Performance Characteristics
- Tested with various error rates
- High detection rate for corrupted packets
- Efficient retransmission mechanism
- Minimal overhead in normal operation
