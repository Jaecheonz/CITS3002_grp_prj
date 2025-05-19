# Protocol Specification

## Overview
This protocol implements a reliable, secure communication system for the Battleship game. It uses TCP as the underlying transport layer and adds custom reliability, security, and error detection mechanisms.

## Packet Structure
Each packet consists of a header and payload:

### Header (6 bytes)
- Packet Type (1 byte): Identifies the type of message
- Sequence Number (1 byte): Ensures ordered delivery and used for IV generation
- Checksum (2 bytes): Simple sum-based checksum for error detection
- Payload Length (2 bytes): Length of the encrypted payload in bytes

### Payload (variable length)
- Encrypted message content
- For string messages, automatically encoded to UTF-8 before encryption
- Minimum packet length: 6 bytes (header only)
- Maximum payload length: Limited by TCP MTU

### Binary Format
- Header: [type(1B)][seq(1B)][checksum(2B)][payload_len(2B)]
- Payload: [encrypted_data]
- All multi-byte fields use network byte order (big-endian)
- Checksum calculated on: header (without checksum) + encrypted payload

## Packet Types
1. GAME_UPDATE (1): General game state updates
2. PLAYER_MOVE (2): Player input/actions
3. BOARD_UPDATE (3): Board display updates
4. CHAT_MESSAGE (4): Chat messages
5. SYSTEM_MESSAGE (5): System notifications
6. RETRANSMISSION_REQUEST (6): Request for packet resend
7. ACK (7): Acknowledgment of received packet
8. GAME_STATE (8): Critical game state messages

## Security Implementation

### Encryption
- Algorithm: AES-CTR (Counter mode)
- Key: 32-byte shared secret key (SHARED_SECRET_KEY)
- IV Generation: 15 zero bytes + sequence number
- Implementation: Uses PyCryptodome's AES implementation
- Note: Key exchange is assumed to be handled out-of-band

### Replay Protection
- Window Size: 64 packets
- Implementation: ReplayWindow class
- Features:
  - Bitmask tracking of seen packets
  - Pending ACK tracking
  - Window slides on new packets
  - Special handling for retransmissions
  - Automatic cleanup of old packets
- Sequence Number Handling:
  - New packets: diff < 128 from latest
  - Old packets: diff >= 128 from latest
  - Bitmask shifts left by diff for new packets
  - Bitmask resets when diff >= window_size
  - Pending set tracks unacknowledged packets

## Sequence Number Management
- Range: 8-bit (0-255)
- Wrapping: Automatic at 256
- Thread Safety: Uses _sequence_lock for thread-safe generation
- Usage:
  - Packet ordering
  - IV generation for encryption
  - Replay protection

## Error Detection and Handling

### Checksum Mechanism
- Type: Simple sum-based
- Size: 2 bytes (modulo 65536)
- Coverage: All packet fields (type, sequence, length, payload)
- Verification: Performed during packet unpacking

### Error Handling Policy
1. Corrupted Packets:
   - Detected via checksum verification
   - Automatically discarded
   - Retransmission requested
   - Logged to protocol_errors.log
   - Struct errors handled separately
   - Minimum length verification (6 bytes)
   - Payload length verification

2. Out-of-Sequence Packets:
   - Detected via sequence numbers
   - Handled by retransmission mechanism
   - Ensures ordered delivery

3. Timeout Handling:
   - Default timeout: 30 seconds (INACTIVITY_TIMEOUT)
   - Maximum retries: 2 attempts (MAX_RETRIES)
   - Retry delay: 0.05 seconds (RETRY_DELAY)
   - Special handling for critical packets

## Message Type-Specific Handling

### PLAYER_MOVE Packets
- Timeout: 1.0 seconds
- Post-ACK delay: 0.05 seconds
- Special retry handling
- Requires ACK before proceeding

### Turn Transition Messages
- Detected by content: "It's your turn" or "Waiting for Player"
- Timeout: 1.0 seconds
- Post-ACK delay: 0.1 seconds
- Special retry handling

### Regular Messages
- Timeout: 0.5 seconds
- Post-ACK delay: 0.05 seconds
- Standard retry mechanism

### Critical Messages (GAME_STATE)
- Higher priority handling
- Extended retry window
- Maximum 3 retry attempts
- Guaranteed delivery attempt

## Logging System
- File: protocol_errors.log
- Level: INFO
- Format: '%(levelname)s: %(message)s'
- Features:
  - Separate logger instance
  - File handler for errors and warnings
  - Timestamps included
  - Sequence numbers logged
  - No propagation to root logger

## Packet Storage and Cleanup
- Storage: sent_packets dictionary
- Key: sequence number
- Value: Packet object
- Cleanup:
  - Automatic removal of old packets
  - Condition: (current_seq - old_seq) % 256 > window_size
  - Maintains only necessary packets for retransmission

## Connection Management
- Transport: TCP
- File Objects: Binary mode (rb/wb)
- Features:
  - Automatic reconnection handling
  - Connection state tracking
  - Graceful termination
  - Non-blocking I/O with select
  - Immediate flush after writes
  - Controlled polling intervals
  - File object cleanup on errors

## Packet Class Implementation
- Fields:
  - packet_type: Message type identifier
  - sequence_num: Unique sequence number
  - payload: Original message content
  - encrypted_payload: Encrypted message content
  - checksum: Error detection value
  - timestamp: Creation time (datetime)
- Methods:
  - _calculate_checksum(): Computes checksum
  - pack(): Serializes to binary format
  - unpack(): Deserializes from binary format

## Performance Considerations
- Minimal overhead in normal operation
- Efficient retransmission mechanism
- Thread-safe operations
- Controlled polling intervals
- Automatic cleanup of old packets
- Optimized for game state synchronization
- Very rarely, may be unable to recover severely corrupted packets