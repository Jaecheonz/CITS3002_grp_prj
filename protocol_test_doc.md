# Protocol Specification

## Packet Structure
Each packet consists of a header and payload:

### Header (6 bytes)
- Packet Type (1 byte): Identifies the type of message
- Sequence Number (1 byte): Ensures ordered delivery
- Checksum (2 bytes): Simple sum-based checksum for error detection
- Payload Length (2 bytes): Length of the payload in bytes

### Payload (variable length)
- The actual message content
- For string messages, automatically encoded to UTF-8

## Packet Types
1. GAME_UPDATE (1): General game state updates
2. PLAYER_MOVE (2): Player input/actions
3. BOARD_UPDATE (3): Board display updates
4. CHAT_MESSAGE (4): Chat messages
5. SYSTEM_MESSAGE (5): System notifications
6. RETRANSMISSION_REQUEST (6): Request for packet resend
7. ACK (7): Acknowledgment of received packet
8. GAME_STATE (8): Critical game state messages

## Checksum Mechanism
- Uses a simple sum-based checksum
- Calculated on: packet type + sequence number + payload length + payload
- 2-byte checksum (modulo 65536)
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
   - Default timeout: 30 seconds
   - Maximum retries: 2 attempts
   - Retry delay: 0.05 seconds
   - Special handling for critical packets (GAME_STATE)

4. Critical Message Handling:
   - GAME_STATE packets have priority
   - Special timeout handling for critical messages
   - Automatic retransmission for failed critical messages
   - Maximum 3 retry attempts for critical messages

5. Logging:
   - All protocol errors logged to 'protocol_errors.log'
   - Includes timestamps and sequence numbers
   - Helps with debugging and monitoring

## Performance Characteristics
- Tested with various error rates
- High detection rate for corrupted packets
- Efficient retransmission mechanism
- Minimal overhead in normal operation
- Special handling for critical game state messages
- Thread-safe sequence number generation
