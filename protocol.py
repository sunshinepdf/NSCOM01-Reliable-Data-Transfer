"""
NSCOM01 - Machine Project 1
Implementation of Reliable Data Transfer over UDP
Khyle Villorente and Raina Helaga

This module defines the packet structure and packing/unpacking logic for 
the custom reliable file transfer protocol. 

This module includes the following:
    1. PacketType: An enumeration of packet types used in the protocol.
    2. ErrorCode: An enumeration of error codes for signaling issues during communication.
    3. Packet: The main class representing the structure of the protocol packet, including methods for packing and unpacking data. 
               Checksum validation and helper methods are also included.
    4. Factory functions: For creating different types of packets and simplify the process of generating packets in the Client and Server code.
    
"""

# Python Library imports
import struct
import zlib

class PacketType:
    SYN = 1         # Connection initiation
    SYN_ACK = 2     # Connection acknowledgment
    DATA = 3        # Data packet for file transfer
    ACK = 4         # Acknowledgment for received data packets
    FIN = 5         # Connection termination
    FIN_ACK = 6     # Acknowledgment for connection termination
    ERROR = 7       # Error packet for signaling issues (e.g., checksum failure, invalid session)


class ErrorCode:
    FILE_NOT_FOUND = 1      # Requested file does not exist on the server
    SESSION_MISMATCH = 2    # Session ID in the packet does not match any active session on the server 
    CHECKSUM_FAILURE = 3    # Checksum validation failed, indicating potential data corruption
    UNKNOWN_PACKET_TYPE = 4 # Received a packet with an unrecognized type
    CONNECTION_TIMEOUT = 5  # No response received within the expected time frame, indicating a potential connection issue

class Colors:
    BLUE = '\033[94m'    # Outgoing
    GREEN = '\033[92m'   # Incoming
    YELLOW = '\033[93m'  # Warning/Retry
    RED = '\033[91m'     # Error
    CYAN = '\033[96m'    # System/Handshake
    MAGENTA = '\033[95m' # Demo simulation alerts
    RESET = '\033[0m'

class Logger:
    @staticmethod
    def sent(packet):
        """Standard format for outgoing packets"""
        print(f"{Colors.BLUE}<-- Sent:     {packet.log_str()}{Colors.RESET}")

    @staticmethod
    def received(packet):
        """Standard format for incoming packets"""
        print(f"{Colors.GREEN}--> Received: {packet.log_str()}{Colors.RESET}")

    @staticmethod
    def info(msg):
        print(f"{Colors.CYAN}[INFO] {msg}{Colors.RESET}")

    @staticmethod
    def demo(msg):
        print(f"{Colors.MAGENTA}[DEMO] {msg}{Colors.RESET}")

    @staticmethod
    def warn(msg):
        print(f"{Colors.YELLOW}[WARN] {msg}{Colors.RESET}")

    @staticmethod
    def error(msg):
        print(f"{Colors.RED}[FAIL] {msg}{Colors.RESET}")
    
class Packet:
    # Header Format: ! - Network byte order (big-endian)
    #                B - Packet Type (1 byte)
    #                H - Session ID (2 bytes)
    #                I - Sequence Number (4 bytes)
    #                H - Payload Length (2 bytes)
    #                H - Checksum (2 bytes)
    HEADER_FORMAT = "!BHIHH"
    HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
    
    # Packet Structure Initialization
    def __init__(self, packet_type, session_id, sequence_number, payload=b""):
        self.packet_type = packet_type
        self.session_id = session_id
        self.sequence_number = sequence_number
        self.payload = payload
        self.checksum = 0
    
    # Checksum Calculation using CRC32, truncated to 16 bits
    def calculate_checksum(self):
        content = struct.pack(self.HEADER_FORMAT,
                              self.packet_type,
                              self.session_id,
                              self.sequence_number,
                              len(self.payload),
                              0) + self.payload
        return zlib.crc32(content) & 0xFFFF
    
    # Pack the packet into bytes for transmission
    def pack(self):
        self.checksum = self.calculate_checksum()
        header = struct.pack(self.HEADER_FORMAT,
                             self.packet_type,
                             self.session_id,
                             self.sequence_number,
                             len(self.payload),
                             self.checksum)
        return header + self.payload
    
    # Unpack bytes into a Packet object, validating the header and payload
    @classmethod
    def unpack(cls, data: bytes):
        if len(data) < cls.HEADER_SIZE:
           return None # Not enough data to unpack the header, indicating a malformed packet
       
        header = data[: cls.HEADER_SIZE]
        packet_type, session_id, sequence_number, payload_length, checksum = struct.unpack(cls.HEADER_FORMAT, header)
        
        if len(data) < cls.HEADER_SIZE + payload_length:
            return None # Payload length specified in the header does not match the actual data length, indicating a truncated packet
        
        payload = data[cls.HEADER_SIZE:cls.HEADER_SIZE + payload_length]
        packet = cls(packet_type, session_id, sequence_number, payload)
        packet.checksum = checksum
        
        if packet.calculate_checksum() != checksum:
            return None # Checksum validation failed, indicating potential data corruption during transmission
        
        return packet
    
    # Helper methods to identify packet types 
    # These methods allow for easy checking of the packet type without directly comparing the packet_type attribute every time in the Client and Server code.
    def is_syn (self): return self.packet_type == PacketType.SYN
    def is_syn_ack (self): return self.packet_type == PacketType.SYN_ACK
    def is_data (self): return self.packet_type == PacketType.DATA
    def is_ack (self): return self.packet_type == PacketType.ACK
    def is_fin (self): return self.packet_type == PacketType.FIN
    def is_fin_ack (self): return self.packet_type == PacketType.FIN_ACK
    def is_error (self): return self.packet_type == PacketType.ERROR
    
    # String representation for debugging purposes
    def __str__(self):
        type_names = { 1: "SYN", 2: "SYN-ACK", 3: "DATA", 4: "ACK", 5: "FIN", 6: "FIN-ACK", 7: "ERROR" }
        t_name = type_names.get(self.packet_type, "UNKNOWN")
        return f"Packet[{t_name}] SessionID:{self.session_id} | SeqNum: {self.sequence_number}| Size: {len(self.payload)} | Checksum: {self.checksum}"

    def log_str(self):
        type_names = { 
            1: "SYN", 2: "SYN-ACK", 3: "DATA", 4: "ACK", 
            5: "FIN", 6: "FIN-ACK", 7: "ERROR" 
        }
        t_name = type_names.get(self.packet_type, "UNKNOWN")
        
        # --- Standardized Feedback Logic ---
        if self.packet_type == PacketType.SYN:
            feedback = f"REQ: {self.payload.decode('utf-8') if self.payload else 'CONNECT'}"
        
        elif self.packet_type == PacketType.SYN_ACK:
            feedback = "Handshake Accepted"
        
        elif self.packet_type == PacketType.DATA:
            feedback = f"Content: {len(self.payload)} bytes"
        
        elif self.packet_type == PacketType.ACK:
            feedback = f"Confirming Seq {self.sequence_number}"
        
        elif self.packet_type == PacketType.FIN:
            feedback = "End of File reached"
        
        elif self.packet_type == PacketType.FIN_ACK:
            feedback = "Termination Confirmed"
            
        elif self.packet_type == PacketType.ERROR:
            err_code = self.payload[0] if self.payload else 0
            err_msg = {1: "FILE_NOT_FOUND", 2: "SESSION_MISMATCH", 3: "CHECKSUM ERROR", 4: "UNKNOWN PACKET TYPE", 5: "CONNECTION TIMEOUT"}.get(err_code, "UNKNOWN")
            feedback = f"!!! ERROR: {err_msg} !!!"
        
        else:
            feedback = "No Payload"

        # Format: [SID: 101 | SEQ: 5 | TYPE: DATA] -> Content: 1024 bytes
        return f"[SID: {self.session_id:03} | SEQ: {self.sequence_number:02} | {t_name:7}] -> {feedback}"
    
# Factory functions for creating different types of packets. 
def create_syn_packet(session_id, sequence_number, payload=b""):
    return Packet(PacketType.SYN, session_id, sequence_number, payload)

def create_syn_ack_packet(session_id, sequence_number, payload=b""):
    return Packet(PacketType.SYN_ACK, session_id, sequence_number, payload)

def create_data_packet(session_id, sequence_number, payload):
    return Packet(PacketType.DATA, session_id, sequence_number, payload)
    
def create_ack_packet(session_id, sequence_number):
    return Packet(PacketType.ACK, session_id, sequence_number)

def create_fin_packet(session_id, sequence_number):
    return Packet(PacketType.FIN, session_id, sequence_number)

def create_fin_ack_packet(session_id, sequence_number):
    return Packet(PacketType.FIN_ACK, session_id, sequence_number)

def create_error_packet(session_id, error_code):
    return Packet(PacketType.ERROR, session_id, 0, payload=bytes([error_code]))