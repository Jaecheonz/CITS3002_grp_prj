import struct
import select
import threading
import logging
from datetime import datetime
import time

# Get a separate logger instance for errors
logger = logging.getLogger('protocol_errors')

# Add file handler for errors and warnings
error_handler = logging.FileHandler('protocol_errors.log')
error_handler.setLevel(logging.INFO)  # Changed from WARNING to INFO to include all levels
error_formatter = logging.Formatter('%(levelname)s: %(message)s')
error_handler.setFormatter(error_formatter)
logger.addHandler(error_handler)

# Set logger level to INFO to ensure all messages are captured
logger.setLevel(logging.INFO)

# Prevent propagation to root logger to avoid duplicate logs
logger.propagate = False

# Constants
INACTIVITY_TIMEOUT = 30  # Default timeout, can be overridden
MAX_RETRIES = 2  # Reduced from 3 to 2
RETRY_DELAY = 0.05  # Reduced from 0.1 to 0.05

# Packet types
PACKET_TYPES = {
    'GAME_UPDATE': 1,
    'PLAYER_MOVE': 2,
    'BOARD_UPDATE': 3,
    'CHAT_MESSAGE': 4,
    'SYSTEM_MESSAGE': 5,
    'RETRANSMISSION_REQUEST': 6,
    'ACK': 7,
    'GAME_STATE': 8  # New packet type for critical game state messages
}

# Sequence number generator
_sequence_num = 0
_sequence_lock = threading.Lock()
sent_packets = {}
from Cryptodome.Cipher import AES
from Cryptodome.Util import Counter

# NOTE: Key exchange is assumed to be handled out-of-band. All peers share SHARED_SECRET_KEY securely in advance.
SHARED_SECRET_KEY = b'ThisIsASecretKey1234567890123456'  # 32 bytes

class ReplayWindow:
    def __init__(self, size=64):
        self.window_size = size
        self.latest_seq = -1
        self.bitmask = 0  # Bitmask for seen-and-ACKed packets
        self.pending = set()  # Set of sequence numbers pending ACK

    def mark_acknowledged(self, seq):
        """Call this when a packet has been acknowledged (e.g., you sent an ACK)."""
        offset = (self.latest_seq - seq) % 256
        if offset < self.window_size:
            self.bitmask |= (1 << offset)
        self.pending.discard(seq)

    def is_replay(self, seq):
        """Returns True if this is a replay and not a retransmission."""
        if seq in self.pending:
            # It's a retransmission of something still pending ACK — allow it
            return False

        diff = (seq - self.latest_seq) % 256
        if diff == 0:
            return True  # exact same sequence number — possible true replay
        elif diff < 128:  # newer packet
            if diff >= self.window_size:
                self.bitmask = 1 << 0  # reset bitmask
            else:
                self.bitmask <<= diff
                self.bitmask |= 1
            self.latest_seq = seq
            self.pending.add(seq)
            return False
        else:  # older packet
            offset = (self.latest_seq - seq) % 256
            if offset >= self.window_size:
                return True  # too old
            if (self.bitmask >> offset) & 1:
                return True  # already seen and acknowledged
            if seq in self.pending:
                return False  # Retransmission of pending
            if offset < self.window_size and ((self.bitmask >> offset) & 1):
                return False  # Already processed, but re-ACK
            return True  # untracked old packet = suspicious

replay_window = ReplayWindow()

def is_replay(seq):
    return replay_window.is_replay(seq)

def get_cipher(sequence_num):
    iv_int = int.from_bytes(b'\x00' * 15 + bytes([sequence_num]), 'big')  # Use sequence_num as IV suffix
    ctr = Counter.new(128, initial_value=iv_int)
    return AES.new(SHARED_SECRET_KEY, AES.MODE_CTR, counter=ctr)

def encrypt_payload(payload, sequence_num):
    cipher = get_cipher(sequence_num)
    return cipher.encrypt(payload)

def decrypt_payload(payload, sequence_num):
    cipher = get_cipher(sequence_num)
    return cipher.decrypt(payload)

def next_sequence_num():
    """Get the next sequence number in a thread-safe way."""
    global _sequence_num
    with _sequence_lock:
        _sequence_num = (_sequence_num + 1) % 256  # Wrap around at 256
        return _sequence_num

class Packet:
    def __init__(self, packet_type, sequence_num, payload):
        self.packet_type = packet_type
        self.sequence_num = sequence_num
        self.payload = payload
        self.encrypted_payload = encrypt_payload(payload, sequence_num)
        self.checksum = self._calculate_checksum()
        self.timestamp = datetime.now()
    
    def _calculate_checksum(self):
        """Calculate a simple sum-based checksum."""
        # Format: [type(1B)][seq(1B)][payload_len(2B)][payload]
        header = struct.pack('!BBHH',
            self.packet_type,
            self.sequence_num,
            0,  # placeholder for checksum during calculation
            len(self.encrypted_payload)
        )
        
        # Calculate sum of all bytes
        total = sum(header + self.encrypted_payload)
        # Take modulo 65536 to keep checksum to 2 bytes
        return total % 65536
    
    def pack(self):
        # Pack the packet into a binary format
        # Format: [type(1B)][seq(1B)][checksum(2B)][payload_len(2B)][payload]
        header = struct.pack('!BBHH',
            self.packet_type,
            self.sequence_num,
            self.checksum,
            len(self.encrypted_payload)
        )
        return header + self.encrypted_payload
    
    @classmethod
    def unpack(cls, data):
        try:
            # Verify minimum packet length
            if len(data) < 6:  # 6 bytes for header (type, seq, checksum, payload_len)
                logger.warning("Packet too short for valid checksum verification")
                return None
                
            # Unpack header
            header = struct.unpack('!BBHH', data[:6])
            packet_type, sequence_num, received_checksum, payload_len = header
            
            # Verify payload length
            if len(data) < 6 + payload_len:
                logger.warning(f"Packet payload length mismatch. Expected {payload_len} bytes but got {len(data) - 6}")
                return None
            
            # Extract payload
            encrypted_payload = data[6:6+payload_len]
            payload = decrypt_payload(encrypted_payload, sequence_num)

            
            # Create temporary packet for checksum verification
            temp_packet = cls(packet_type, sequence_num, payload)
            
            # Verify checksum
            if temp_packet.checksum != received_checksum:
                logger.warning(f"Checksum mismatch for packet {sequence_num}. Expected {received_checksum}, got {temp_packet.checksum}")
                return None
            
            return temp_packet
        except struct.error as e:
            logger.error(f"Invalid packet format during checksum verification: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Error during packet unpacking and checksum verification: {str(e)}")
            return None

def safe_send(wfile, rfile, message, packet_type=PACKET_TYPES['SYSTEM_MESSAGE']):
    """Safely send a message to a client using our custom protocol with retransmission."""
    try:
        # Convert message to bytes if it's a string
        if isinstance(message, str):
            payload = message.encode('utf-8')
        else:
            payload = message

        # Create and send packet
        packet = Packet(packet_type, next_sequence_num(), payload)
        packed_data = packet.pack()
        sent_packets[packet.sequence_num] = packet
        # For PLAYER_MOVE packets, we need to ensure we get an ACK before proceeding
        if packet_type == PACKET_TYPES['PLAYER_MOVE']:
            wfile.write(packed_data)
            wfile.flush()
            # Wait for ACK with a longer timeout for moves
            if wait_for_ack(rfile, wfile, packet.sequence_num, timeout=1.0):
                time.sleep(0.05)  # Small delay after successful ACK
                return True
            logger.warning(f"Failed to get ACK for PLAYER_MOVE packet {packet.sequence_num}")
            for seq in list(sent_packets):
                if (packet.sequence_num - seq) % 256 > replay_window.window_size:
                    del sent_packets[seq]
            return False

        # For turn transition messages, we need to be extra careful
        if isinstance(message, str) and ("It's your turn" in message or "Waiting for Player" in message):
            wfile.write(packed_data)
            wfile.flush()
            # Wait for ACK with a longer timeout for turn transitions
            if wait_for_ack(rfile, wfile, packet.sequence_num, timeout=1.0):
                time.sleep(0.1)  # Longer delay for turn transitions
                return True
            logger.warning(f"Failed to get ACK for turn transition message")
            for seq in list(sent_packets):
                if (packet.sequence_num - seq) % 256 > replay_window.window_size:
                    del sent_packets[seq]
            return False

        # For all other packets, retry up to MAX_RETRIES
        attempt = 0
        last_error = None
        while attempt < MAX_RETRIES:
            try:
                wfile.write(packed_data)
                wfile.flush()

                # Wait for ACK with a reasonable timeout
                if wait_for_ack(rfile, wfile, packet.sequence_num, timeout=0.5):
                    time.sleep(0.05)  # Small delay after successful ACK
                    for seq in list(sent_packets):
                        if (packet.sequence_num - seq) % 256 > replay_window.window_size:
                            del sent_packets[seq]
                    return True

                # Log retransmission and continue trying
                attempt += 1
                logger.warning(f"Retransmission attempt {attempt} for packet {packet.sequence_num} - No ACK received")
                if last_error:
                    logger.warning(f"Last error encountered: {last_error}")
                time.sleep(RETRY_DELAY)

            except Exception as e:
                last_error = str(e)
                logger.error(f"Error during send attempt {attempt + 1} for packet {packet.sequence_num}: {str(e)}")
                attempt += 1
                time.sleep(RETRY_DELAY)
                continue

        logger.error(f"Failed to receive ACK for packet {packet.sequence_num} after {MAX_RETRIES} attempts")
        for seq in list(sent_packets):
            if (packet.sequence_num - seq) % 256 > replay_window.window_size:
                del sent_packets[seq]
        return False

    except Exception as e:
        logger.error(f"Fatal error sending packet: {str(e)}")
        for seq in list(sent_packets):
            if (packet.sequence_num - seq) % 256 > replay_window.window_size:
                del sent_packets[seq]
        return False

def safe_recv(rfile, wfile, timeout=INACTIVITY_TIMEOUT):
    """Safely receive a message with sequence validation and retransmission requests."""
    try:
        # Use select to check if data is available with timeout
        readable, _, _ = select.select([rfile.fileno()], [], [], timeout)
        if not readable:
            return None  # Timeout occurred
            
        # Read header first (6 bytes)
        header = rfile.read(6)
        if not header or len(header) < 6:
            logger.warning("Received incomplete header during packet reception")
            return None
            
        # Unpack header to get payload length
        try:
            packet_type, sequence_num, received_checksum, payload_len = struct.unpack('!BBHH', header)
        except struct.error as e:
            logger.error(f"Failed to unpack header during packet reception: {str(e)}")
            return None
        
        # For ACK packets, we know they have no payload
        if packet_type == PACKET_TYPES['ACK']:
            return None
            
        # Read payload for non-ACK packets
        payload = rfile.read(payload_len)
        if not payload or len(payload) < payload_len:
            logger.warning(f"Received incomplete payload. Expected {payload_len} bytes but got {len(payload) if payload else 0}")
            return None
            
        # Combine header and payload for unpacking
        packet = Packet.unpack(header + payload)
        if packet is None:
            # Only request retransmission for non-ACK packets
            if packet_type != PACKET_TYPES['ACK']:
                logger.warning("Requesting retransmission due to packet validation failure")
                request_retransmission(wfile, sequence_num)
            return None
            
        # Replay protection
        if is_replay(packet.sequence_num):
            logger.warning(f"Replay attack detected: duplicate or old sequence number {packet.sequence_num}")
            if packet.packet_type == PACKET_TYPES['RETRANSMISSION_REQUEST']:
                if packet.payload:
                    missing_seq = struct.unpack('!B', packet.payload[:1])[0]
                    if missing_seq in sent_packets:
                        retry_packet = sent_packets[missing_seq]
                        try:
                            wfile.write(retry_packet.pack())
                            wfile.flush()
                            logger.info(f"Retransmitted packet {missing_seq}")
                        except Exception as e:
                            logger.error(f"Failed to retransmit packet {missing_seq}: {str(e)}")
                return None

        # Send ACK for all non-ACK packets
        if packet.packet_type != PACKET_TYPES['ACK']:
            send_ack(wfile, packet.sequence_num)
        
        # Don't process ACK packets as messages
        if packet.packet_type == PACKET_TYPES['ACK']:
            return None
            
        return packet.payload.decode('utf-8')
    except Exception as e:
        logger.error(f"Error receiving packet: {str(e)}")
        return None

def wait_for_ack(rfile, wfile, sequence_num, timeout=0.5):
    """Wait for an acknowledgment packet."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            readable, _, _ = select.select([rfile.fileno()], [], [], 0.1)
            if readable:
                # Read and process all available packets
                while True:
                    header = rfile.read(6)
                    if not header:
                        logger.warning(f"No header received while waiting for ACK of packet {sequence_num} - Connection may be closed")
                        return False
                        
                    try:
                        packet_type, ack_seq, _, payload_len = struct.unpack('!BBHH', header)
                        
                        # For ACK packets, check if it matches our sequence
                        if packet_type == PACKET_TYPES['ACK']:
                            if (ack_seq % 256) == (sequence_num % 256):
                                replay_window.mark_acknowledged(sequence_num)
                                return True
                            continue  # Keep waiting for our ACK
                        
                        # For non-ACK packets, read the payload and process it
                        if payload_len > 0:
                            payload = rfile.read(payload_len)
                            if not payload:
                                logger.warning(f"Failed to read payload of {payload_len} bytes - Connection may be closed")
                                return False
                            
                            # Send ACK for any non-ACK packet we receive
                            send_ack(wfile, ack_seq)
                            
                            # For critical packets like GAME_STATE, we should not wait indefinitely
                            if packet_type == PACKET_TYPES['GAME_STATE']:
                                logger.warning(f"Received critical GAME_STATE packet while waiting for ACK of {sequence_num}")
                                # If we've waited more than half the timeout, return False to allow retransmission
                                if time.time() - start_time > timeout / 2:
                                    logger.warning(f"Timeout threshold reached while waiting for ACK of {sequence_num}")
                                    return False
                            
                            # For PLAYER_MOVE packets, we should be more lenient
                            if packet_type == PACKET_TYPES['PLAYER_MOVE']:
                                logger.warning(f"Received PLAYER_MOVE packet while waiting for ACK of {sequence_num}")
                                # Continue waiting for our original ACK
                                continue
                            
                            # For other packet types, just log and continue
                            continue
                    except struct.error as e:
                        logger.warning(f"Failed to unpack header while waiting for ACK of packet {sequence_num}: {str(e)}")
                        break
        except Exception as e:
            logger.error(f"Error waiting for ACK of packet {sequence_num}: {str(e)}")
            continue
    logger.warning(f"Timeout waiting for ACK of packet {sequence_num}")
    return False

def send_ack(wfile, sequence_num):
    """Send an acknowledgment packet."""
    try:
        ack_packet = Packet(PACKET_TYPES['ACK'], sequence_num, b'')
        wfile.write(ack_packet.pack())
        wfile.flush()
    except Exception as e:
        logger.error(f"Error sending ACK: {str(e)}")

def request_retransmission(wfile, missing_seq):
    """Send a retransmission request for a specific sequence number."""
    try:
        # Payload contains the sequence number being requested (1 byte)
        payload = struct.pack('!B', missing_seq)
        retry_packet = Packet(PACKET_TYPES['RETRANSMISSION_REQUEST'], next_sequence_num(), payload)
        wfile.write(retry_packet.pack())
        wfile.flush()
        logger.info(f"Requested retransmission for seq={missing_seq}")
    except Exception as e:
        logger.error(f"Error requesting retransmission: {str(e)}")

