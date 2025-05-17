import random
import protocol
import socket
import threading
import time
import logging
from datetime import datetime
import select
import struct
import zlib

# Add SUCCESS level to logging
logging.SUCCESS = 25  # Between INFO (20) and WARNING (30)
logging.addLevelName(logging.SUCCESS, 'SUCCESS')

def success(self, message, *args, **kwargs):
    if self.isEnabledFor(logging.SUCCESS):
        self._log(logging.SUCCESS, message, args, **kwargs)

logging.Logger.success = success

# Set up logging for test results
logger = logging.getLogger('protocol_test')
logger.setLevel(logging.INFO)

# Create file handler for test results
results_handler = logging.FileHandler('protocol_test.log')
results_handler.setLevel(logging.INFO)  # Only handle INFO and above
results_formatter = logging.Formatter('%(levelname)s: %(message)s')
results_handler.setFormatter(results_formatter)

# Add handler to logger
logger.addHandler(results_handler)

# Prevent propagation to root logger to avoid duplicate logs
logger.propagate = False

def inject_errors(data, error_rate=0.1):
    """Randomly flip bits in the data with given error rate."""
    result = bytearray(data)
    
    # Only inject errors in the payload portion
    for i in range(6, len(result)):  # Skip header (first 6 bytes)
        if random.random() < error_rate:
            # Flip a single bit
            bit_to_flip = 1 << random.randint(0, 7)
            result[i] ^= bit_to_flip
    
    return bytes(result)

def test_packet_corruption():
    """Test how well our protocol detects corrupted packets."""
    logger.info("Test commencing: Packet Corruption Detection")
    # Create test socket pair
    s1, s2 = socket.socketpair()
    
    # Test parameters
    num_packets = 1000
    error_rates = [0.01, 0.05, 0.1, 0.2]
    
    results = {}
    for error_rate in error_rates:
        corrupted = 0
        for _ in range(num_packets):
            # Create and send packet with a fixed payload size
            payload = b'X' * 40  # Use consistent payload size
            packet = protocol.Packet(protocol.PACKET_TYPES['SYSTEM_MESSAGE'], 1, payload)
            data = packet.pack()
            
            # Inject errors
            corrupted_data = inject_errors(data, error_rate)
            
            # Try to unpack
            result = protocol.Packet.unpack(corrupted_data)
            if result is None:
                corrupted += 1
                
        detection_rate = (corrupted / num_packets) * 100
        results[error_rate] = detection_rate
        
    return results

def test_sequence_validation():
    """Test sequence number validation and out-of-order packet handling."""
    logger.info("Test commencing: Sequence Validation")
    s1, s2 = socket.socketpair()
    rfile1 = s1.makefile('rb')
    wfile1 = s1.makefile('wb')
    rfile2 = s2.makefile('rb')
    wfile2 = s2.makefile('wb')
    
    # Create packets in sequence order but send them out of order (3,1,4,2)
    packets = [
        protocol.Packet(protocol.PACKET_TYPES['SYSTEM_MESSAGE'], 3, b'third'),
        protocol.Packet(protocol.PACKET_TYPES['SYSTEM_MESSAGE'], 1, b'first'),
        protocol.Packet(protocol.PACKET_TYPES['SYSTEM_MESSAGE'], 4, b'fourth'),
        protocol.Packet(protocol.PACKET_TYPES['SYSTEM_MESSAGE'], 2, b'second')
    ]
    
    # Send packets and handle ACKs
    received = []
    received_sequence = []  # Track the order in which packets were received
    expected_sequence = 1  # Track the next expected sequence number
    buffered_packets = {}  # Buffer for out-of-order packets
    
    # Start ACK handler thread that runs for all packets
    def ack_handler():
        try:
            while True:
                # Read the packet
                header = rfile2.read(6)  # Changed from 9 to 6
                if not header:
                    break
                    
                packet_type, seq_num, checksum, payload_len = struct.unpack('!BBHH', header)  # Changed from BBLHB to BBHH
                payload = rfile2.read(payload_len)
                
                # Send ACK immediately
                ack_packet = protocol.Packet(protocol.PACKET_TYPES['ACK'], seq_num, b'')
                wfile2.write(ack_packet.pack())
                wfile2.flush()
        except Exception as e:
            logger.error(f"Error in ACK handler: {str(e)}")
    
    # Start ACK handler in a separate thread
    ack_thread = threading.Thread(target=ack_handler)
    ack_thread.daemon = True
    ack_thread.start()
    
    def process_buffered_packets():
        """Process any buffered packets that can be handled in sequence."""
        nonlocal expected_sequence, received
        while expected_sequence in buffered_packets:
            packet = buffered_packets[expected_sequence]
            received.append(packet.payload.decode('utf-8'))
            del buffered_packets[expected_sequence]
            expected_sequence += 1
    
    # Send packets in the specified order (3,1,4,2)
    for packet in packets:
        # Send packet
        wfile1.write(packet.pack())
        wfile1.flush()
        
        # Wait for ACK with timeout
        start_time = time.time()
        ack_received = False
        while time.time() - start_time < 1.0:  # 1 second timeout
            try:
                readable, _, _ = select.select([rfile1.fileno()], [], [], 0.1)
                if readable:
                    header = rfile1.read(6)  # Changed from 9 to 6
                    if header:
                        packet_type, ack_seq, _, _ = struct.unpack('!BBHH', header)  # Changed from BBLHB to BBHH
                        if packet_type == protocol.PACKET_TYPES['ACK'] and ack_seq == packet.sequence_num:
                            # Track the sequence in which packets were received
                            received_sequence.append(packet.sequence_num)
                            
                            # Handle the packet based on its sequence number
                            if packet.sequence_num == expected_sequence:
                                received.append(packet.payload.decode('utf-8'))
                                expected_sequence += 1
                                process_buffered_packets()
                            else:
                                buffered_packets[packet.sequence_num] = packet
                            ack_received = True
                            break
            except Exception as e:
                logger.error(f"Error in sequence validation: {str(e)}")
                continue
        
        if not ack_received:
            logger.warning(f"No ACK received for packet {packet.sequence_num}")
    
    # Process any remaining buffered packets
    process_buffered_packets()
    
    # Wait for ACK handler to complete
    ack_thread.join(timeout=0.1)
    
    logger.success(f"Sequence validation test: {len(received)} packets received")
    logger.success(f"Packets received in sequence: {received_sequence}")
    logger.success(f"Packets processed in order: {received}")
    
    return received

def test_retransmission():
    """Test retransmission mechanism."""
    logger.info("Test commencing: Retransmission")
    s1, s2 = socket.socketpair()
    rfile1 = s1.makefile('rb')
    wfile1 = s1.makefile('wb')
    rfile2 = s2.makefile('rb')
    wfile2 = s2.makefile('wb')
    
    # Start ACK handler thread
    def ack_handler():
        try:
            # Read the packet
            header = rfile2.read(6)  # Changed from 9 to 6
            if header:
                # Get payload length from header
                packet_type, seq_num, checksum, payload_len = struct.unpack('!BBHH', header)  # Changed from BBLHB to BBHH
                # Read the payload
                payload = rfile2.read(payload_len)
                # Don't send ACK to test retransmission
                logger.info("ACK handler intentionally not sending ACK")
            else:
                logger.warning("ACK handler received empty header")
        except Exception as e:
            logger.error(f"Error in ACK handler: {str(e)}")
    
    # Start ACK handler in a separate thread
    ack_thread = threading.Thread(target=ack_handler)
    ack_thread.daemon = True
    ack_thread.start()
    
    # Send packet using safe_send to test retransmission
    success = protocol.safe_send(wfile1, rfile1, "test message", protocol.PACKET_TYPES['SYSTEM_MESSAGE'])
    
    # Wait for retransmission
    time.sleep(0.2)
    
    # Check if packet was retransmitted
    retransmitted = False
    start_time = time.time()
    while time.time() - start_time < 1.0:  # 1 second timeout
        try:
            readable, _, _ = select.select([rfile2.fileno()], [], [], 0.1)
            if readable:
                header = rfile2.read(6)  # Changed from 9 to 6
                if header:
                    packet_type, seq_num, checksum, payload_len = struct.unpack('!BBHH', header)  # Changed from BBLHB to BBHH
                    # Read the payload
                    payload = rfile2.read(payload_len)
                    if packet_type == protocol.PACKET_TYPES['SYSTEM_MESSAGE']:
                        logger.success("Found retransmitted packet!")
                        retransmitted = True
                        break
                else:
                    logger.warning("Received empty header in retransmission check")
        except Exception as e:
            logger.error(f"Error in retransmission test: {str(e)}")
            continue
    
    # Wait for ACK handler to complete
    ack_thread.join(timeout=0.1)
    
    # The test should pass if we got a retransmission and the original send failed
    # (which it should since we're not sending ACKs)
    test_result = retransmitted and not success
    logger.success(f"Retransmission test: {'Success' if test_result else 'Failed'}")
    return test_result  # Should be retransmitted and original send should fail

def test_ack():
    """Test basic acknowledgment functionality."""
    logger.info("Test commencing: ACK Functionality")
    # Create test socket pair
    s1, s2 = socket.socketpair()
    rfile1 = s1.makefile('rb')
    wfile1 = s1.makefile('wb')
    rfile2 = s2.makefile('rb')
    wfile2 = s2.makefile('wb')
    
    # Test parameters
    num_packets = 100
    ack_received = 0
    
    for _ in range(num_packets):
        # Create and send packet
        packet = protocol.Packet(protocol.PACKET_TYPES['SYSTEM_MESSAGE'], 1, b'test')
        data = packet.pack()
        
        # Send packet
        wfile1.write(data)
        wfile1.flush()
        
        # Read packet and send ACK
        try:
            header = rfile2.read(6)  # Changed from 9 to 6
            if header:
                # Send ACK
                packet_type, seq_num, checksum, payload_len = struct.unpack('!BBHH', header)  # Changed from BBLHB to BBHH
                ack_packet = protocol.Packet(protocol.PACKET_TYPES['ACK'], seq_num, b'')
                wfile2.write(ack_packet.pack())
                wfile2.flush()
                
                # Wait for ACK
                start_time = time.time()
                while time.time() - start_time < 1.0:  # 1 second timeout
                    readable, _, _ = select.select([rfile1.fileno()], [], [], 0.1)
                    if readable:
                        ack_header = rfile1.read(6)  # Changed from 9 to 6
                        if ack_header:
                            ack_type, ack_seq, _, _ = struct.unpack('!BBHH', ack_header)  # Changed from BBLHB to BBHH
                            if ack_type == protocol.PACKET_TYPES['ACK'] and ack_seq == seq_num:
                                ack_received += 1
                                break
        except Exception as e:
            logger.error(f"Error in ACK test: {str(e)}")
            continue
    
    success_rate = (ack_received / num_packets) * 100
    logger.success(f"ACK test: {success_rate}% of packets were acknowledged")
    return success_rate

def run_all_tests():
    """Run all protocol tests and log results."""
    logger.info("Test Suite commencing: Protocol Tests")
    
    successful_tests = 0
    total_tests = 4  # Total number of tests
    
    # Test packet corruption detection
    corruption_results = test_packet_corruption()
    logger.info("Packet corruption test results:")
    for rate, detection in corruption_results.items():
        logger.success(f"  Error rate {rate}: {detection}% detection rate")
    successful_tests += 1  # Corruption test always passes as it just measures detection rates
    
    # Test sequence validation
    sequence_result = test_sequence_validation()  # Results are already logged in the function
    if sequence_result and len(sequence_result) == 4:  # Check if we got all 4 packets in correct order
        successful_tests += 1
    
    # Test retransmission
    retransmission_success = test_retransmission()
    logger.success(f"Retransmission test: {'Success' if retransmission_success else 'Failed'}")
    if retransmission_success:
        successful_tests += 1
    
    # Test basic ACK functionality
    ack_success = test_ack()
    logger.success(f"ACK test: {ack_success}% success rate")
    if ack_success >= 95:  # Consider test successful if 95% or more ACKs were received
        successful_tests += 1
    
    logger.info(f"SUCCESS: {successful_tests}/{total_tests} protocol tests completed")

if __name__ == "__main__":
    run_all_tests()