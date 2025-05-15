import struct
import zlib
import select
import threading
import logging
from datetime import datetime
import time

# Get a separate logger instance for errors
logger = logging.getLogger('protocol_errors')

# Add file handler for errors and warnings
error_handler = logging.FileHandler('protocol_errors.log')
error_handler.setLevel(logging.WARNING)  # Handle WARNING and above
error_formatter = logging.Formatter('%(levelname)s: %(message)s')
error_handler.setFormatter(error_formatter)
logger.addHandler(error_handler)

# Prevent propagation to root logger to avoid duplicate logs
logger.propagate = False

# Constants
INACTIVITY_TIMEOUT = 30  # Default timeout, can be overridden
MAX_RETRIES = 3
RETRY_DELAY = 0.1  # 100ms delay between retries

# Packet types
PACKET_TYPES = {
    'GAME_UPDATE': 1,
    'PLAYER_MOVE': 2,
    'BOARD_UPDATE': 3,
    'CHAT_MESSAGE': 4,
    'SYSTEM_MESSAGE': 5,
    'RETRANSMISSION_REQUEST': 6,  # New packet type for retransmission requests
    'ACK': 7  # New packet type for acknowledgments
}

# Sequence number generator
_sequence_num = 0
_sequence_lock = threading.Lock()

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
        self.checksum = self._calculate_checksum()
        self.timestamp = datetime.now()
    
    def _calculate_checksum(self):
        # Simple CRC32 over the packet data
        # Format: [type(1B)][seq(1B)][payload_len(2B)][padding(1B)][payload]
        header = struct.pack('!BBHB',
            self.packet_type,
            self.sequence_num,
            len(self.payload),
            0  # Padding byte
        )
        
        # Calculate CRC32 over header + payload
        return zlib.crc32(header + self.payload)
    
    def pack(self):
        # Pack the packet into a binary format
        # Format: [type(1B)][seq(1B)][checksum(4B)][payload_len(2B)][padding(1B)][payload]
        header = struct.pack('!BBLHB',
            self.packet_type,
            self.sequence_num,
            self.checksum,
            len(self.payload),
            0  # Padding byte
        )
        return header + self.payload
    
    @classmethod
    def unpack(cls, data):
        try:
            # Verify minimum packet length
            if len(data) < 9:
                logger.warning("Packet too short for valid checksum verification")
                return None
                
            # Unpack header
            header = struct.unpack('!BBLHB', data[:9])
            packet_type, sequence_num, checksum, payload_len, _ = header
            
            # Verify payload length
            if len(data) < 9 + payload_len:
                logger.warning(f"Packet payload length mismatch. Expected {payload_len} bytes but got {len(data) - 9}")
                return None
            
            # Extract payload
            payload = data[9:9+payload_len]
            
            # Create temporary packet for checksum verification
            temp_packet = cls(packet_type, sequence_num, payload)
            
            # Verify checksum
            if temp_packet.checksum != checksum:
                logger.warning(f"Checksum mismatch for packet {sequence_num}. Expected {checksum}, got {temp_packet.checksum}")
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
        
        # Try to send with retries
        for attempt in range(MAX_RETRIES):
            wfile.write(packed_data)
            wfile.flush()
            
            # Wait for ACK
            if wait_for_ack(rfile, packet.sequence_num):
                return True
                
            logger.warning(f"Retransmission attempt {attempt + 1} for packet {packet.sequence_num}")
            time.sleep(RETRY_DELAY)
            
        logger.error(f"Failed to send packet {packet.sequence_num} after {MAX_RETRIES} attempts")
        return False
    except Exception as e:
        logger.error(f"Error sending packet: {str(e)}")
        return False

def safe_recv(rfile, wfile, timeout=INACTIVITY_TIMEOUT):
    """Safely receive a message with sequence validation and retransmission requests."""
    try:
        # Use select to check if data is available with timeout
        readable, _, _ = select.select([rfile.fileno()], [], [], timeout)
        if not readable:
            return None  # Timeout occurred
            
        # Read header first (9 bytes)
        header = rfile.read(9)
        if not header or len(header) < 9:
            logger.warning("Received incomplete header during packet reception")
            return None
            
        # Unpack header to get payload length
        try:
            _, _, _, payload_len, _ = struct.unpack('!BBLHB', header)
        except struct.error as e:
            logger.error(f"Failed to unpack header during packet reception: {str(e)}")
            return None
        
        # Read payload
        payload = rfile.read(payload_len)
        if not payload or len(payload) < payload_len:
            logger.warning(f"Received incomplete payload. Expected {payload_len} bytes but got {len(payload) if payload else 0}")
            return None
            
        # Combine header and payload for unpacking
        packet = Packet.unpack(header + payload)
        if packet is None:
            # Request retransmission
            logger.warning("Requesting retransmission due to packet validation failure")
            request_retransmission(wfile)
            return None
            
        # Send ACK
        send_ack(wfile, packet.sequence_num)
        
        return packet.payload.decode('utf-8')
    except Exception as e:
        logger.error(f"Error receiving packet: {str(e)}")
        return None

def wait_for_ack(rfile, sequence_num, timeout=1.0):
    """Wait for an acknowledgment packet."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            readable, _, _ = select.select([rfile.fileno()], [], [], 0.1)
            if readable:
                header = rfile.read(9)
                if not header:
                    continue
                    
                packet_type, ack_seq, _, _, _ = struct.unpack('!BBLHB', header)
                if packet_type == PACKET_TYPES['ACK'] and ack_seq == sequence_num:
                    return True
        except Exception as e:
            logger.error(f"Error waiting for ACK: {str(e)}")
            continue
    return False

def send_ack(wfile, sequence_num):
    """Send an acknowledgment packet."""
    try:
        ack_packet = Packet(PACKET_TYPES['ACK'], sequence_num, b'')
        wfile.write(ack_packet.pack())
        wfile.flush()
    except Exception as e:
        logger.error(f"Error sending ACK: {str(e)}")

def request_retransmission(wfile):
    """Send a retransmission request."""
    try:
        retry_packet = Packet(PACKET_TYPES['RETRANSMISSION_REQUEST'], next_sequence_num(), b'')
        wfile.write(retry_packet.pack())
        wfile.flush()
    except Exception as e:
        logger.error(f"Error requesting retransmission: {str(e)}")
