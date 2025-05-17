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
        """Calculate a simple sum-based checksum."""
        # Format: [type(1B)][seq(1B)][payload_len(2B)][payload]
        header = struct.pack('!BBH',
            self.packet_type,
            self.sequence_num,
            len(self.payload)
        )
        
        # Calculate sum of all bytes
        total = sum(header + self.payload)
        # Take modulo 65536 to keep checksum to 2 bytes
        return total % 65536
    
    def pack(self):
        # Pack the packet into a binary format
        # Format: [type(1B)][seq(1B)][checksum(2B)][payload_len(2B)][payload]
        header = struct.pack('!BBHH',
            self.packet_type,
            self.sequence_num,
            self.checksum,
            len(self.payload)
        )
        return header + self.payload
    
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
            payload = data[6:6+payload_len]
            
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
        
        # For PLAYER_MOVE packets, we need to ensure we get an ACK before proceeding
        if packet_type == PACKET_TYPES['PLAYER_MOVE']:
            logger.info(f"Sending PLAYER_MOVE packet {packet.sequence_num}")
            wfile.write(packed_data)
            wfile.flush()
            # Wait for ACK with a longer timeout for moves
            if wait_for_ack(rfile, wfile, packet.sequence_num, timeout=1.0):
                logger.info(f"PLAYER_MOVE packet {packet.sequence_num} acknowledged")
                time.sleep(0.05)  # Small delay after successful ACK
                return True
            logger.warning(f"Failed to get ACK for PLAYER_MOVE packet {packet.sequence_num}")
            return False
        
        # For turn transition messages, we need to be extra careful
        if "It's your turn" in message or "Waiting for Player" in message:
            wfile.write(packed_data)
            wfile.flush()
            # Wait for ACK with a longer timeout for turn transitions
            if wait_for_ack(rfile, wfile, packet.sequence_num, timeout=1.0):
                logger.info(f"Turn transition message acknowledged")
                time.sleep(0.1)  # Longer delay for turn transitions
                return True
            logger.warning(f"Failed to get ACK for turn transition message")
            return False
        
        # For all other packets, keep trying until we succeed
        attempt = 0
        last_error = None
        while True:
            try:
                # Log packet details before sending
                logger.info(f"Sending packet {packet.sequence_num} (type: {packet_type}, size: {len(packed_data)} bytes)")
                
                wfile.write(packed_data)
                wfile.flush()
                logger.info(f"Successfully wrote packet {packet.sequence_num} to socket")
                
                # Wait for ACK with a reasonable timeout
                if wait_for_ack(rfile, wfile, packet.sequence_num, timeout=0.5):
                    if attempt > 0:
                        logger.info(f"Packet {packet.sequence_num} successfully delivered after {attempt} retries")
                    time.sleep(0.05)  # Small delay after successful ACK
                    return True
                    
                # Log retransmission and continue trying
                attempt += 1
                if attempt % 10 == 0:  # Log every 10 attempts
                    logger.warning(f"Retransmission attempt {attempt} for packet {packet.sequence_num} - No ACK received")
                    if last_error:
                        logger.warning(f"Last error encountered: {last_error}")
                time.sleep(RETRY_DELAY)
                
            except Exception as e:
                last_error = str(e)
                logger.error(f"Error during send attempt {attempt + 1} for packet {packet.sequence_num}: {str(e)}")
                time.sleep(RETRY_DELAY)
                continue
            
    except Exception as e:
        logger.error(f"Fatal error sending packet: {str(e)}")
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
                request_retransmission(wfile)
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
                        logger.info(f"Received packet - type: {packet_type}, seq: {ack_seq}, waiting for ACK of {sequence_num}")
                        
                        # For ACK packets, check if it matches our sequence
                        if packet_type == PACKET_TYPES['ACK']:
                            if (ack_seq % 256) == (sequence_num % 256):
                                logger.info(f"Received matching ACK for packet {sequence_num}")
                                return True
                            logger.info(f"Received ACK for sequence {ack_seq}, waiting for {sequence_num}")
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
                            logger.info(f"Received non-ACK packet of type {packet_type} with {len(payload)} bytes")
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

def request_retransmission(wfile):
    """Send a retransmission request."""
    try:
        retry_packet = Packet(PACKET_TYPES['RETRANSMISSION_REQUEST'], next_sequence_num(), b'')
        wfile.write(retry_packet.pack())
        wfile.flush()
    except Exception as e:
        logger.error(f"Error requesting retransmission: {str(e)}")

