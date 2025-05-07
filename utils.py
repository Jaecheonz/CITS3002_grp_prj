# utils.py

def calculate_checksum(packet_bytes: bytes) -> int:
    """Calculate a simple sum-based checksum over packet_bytes."""
    return sum(packet_bytes) % (2**32)

def add_checksum(packet_without_checksum: bytes) -> bytes:
    """Given a packet without checksum, returns packet with checksum appended."""
    checksum = calculate_checksum(packet_without_checksum)
    # checksum is 4 bytes, big-endian
    return packet_without_checksum + checksum.to_bytes(4, 'big')

def verify_checksum(full_packet: bytes) -> bool:
    """Verify the checksum of a received packet."""
    if len(full_packet) < 4:
        return False  # Packet too small to have checksum

    received_checksum = int.from_bytes(full_packet[-4:], 'big')
    data_without_checksum = full_packet[:-4]
    calculated_checksum = calculate_checksum(data_without_checksum)
    return received_checksum == calculated_checksum

def strip_checksum(full_packet: bytes) -> bytes:
    """Removes the checksum and returns only the data."""
    return full_packet[:-4]