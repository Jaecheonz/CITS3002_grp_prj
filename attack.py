import socket

# Simulate an attacker resending a captured packet
REPLAY_PACKET = b'\x01\x02\x05\x03\x04\xA1'  # Example valid packet (modify to match your real format)
TARGET_IP = "127.0.0.1"
TARGET_PORT = 5000

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.sendto(REPLAY_PACKET, (TARGET_IP, TARGET_PORT))
print("Replayed captured packet.")
