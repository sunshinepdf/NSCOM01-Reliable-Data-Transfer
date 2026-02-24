"""
NSCOM01 - Machine Project 1
Implementation of Reliable Data Transfer over UDP
Khyle Villorente and Raina Helaga

This module implements the core logic for reliable data transfer over UDP, including:
    1. send_reliable: A function that handles the sending of packets with retry logic
    2. send_abort: A helper function to send an error packet to the peer in case of critical failures
    3. send_file: A function that manages the process of sending a file in chunks, including connection setup and teardown
    4. receive_file: A function that manages the process of receiving a file, including acknowledgment of received packets and handling connection termination.
    
The functions in this module are designed to be used by both the Client and Server modules, abstracting away the common logic for reliable communication and file transfer. 
The module relies on the Packet class and related constants defined in protocol.py, as well as configuration parameters from config.py.
"""

# Library imports
import socket
import os

# Local imports
from protocol import (
    Packet, ErrorCode, create_ack_packet,
    create_error_packet, create_data_packet, create_fin_packet,
    create_fin_ack_packet
)
from config import CHUNK_SIZE, TIMEOUT, MAX_RETRIES

# Function to send a packet reliably, with retry logic and error handling
def send_reliable(sock, packet, target_addr):
    
    raw_bytes = packet.pack()
    retries = 0
    sock.settimeout(TIMEOUT)
    
    # Loop to handle retries in case of timeouts or connection issues
    while retries < MAX_RETRIES:
        try:
            print(f"-> Sending packet: {packet}") 
            sock.sendto(raw_bytes, target_addr)
            
            response_data, addr = sock.recvfrom(4096) # Sets buffer size to 4096 to accommodate larger packets
            response_packet = Packet.unpack(response_data) # Unpack the response packet and validate it
            
            # Ignore packets from unexpected sources
            if addr != target_addr: continue
            
            # Ignore malformed packets that fail unpacking or checksum validation
            if not response_packet: continue 
            
            # Handle different error response types based on the original packet type and the response packet type
            if response_packet.is_error():
                print(f"XX Remote returned Error Code: {response_packet.payload[0]}")
                return None
            
            # Validates if the response packet is the expected acknowledgment for a SYN packet.
            if packet.is_syn() and response_packet.is_syn_ack():
                print(f"<- Received SYN-ACK! Session ID: {response_packet.session_id}")
                return response_packet
            
            # Validates if the response packet is the expected acknowledgment for a FIN packet.
            if packet.is_fin() and response_packet.is_fin_ack():
                print(f"<- Received FIN-ACK! Connection terminated successfully.")
                return response_packet
            
            # Validates if the response packet is the expected acknowledgment for a DATA packet, matching the sequence number.
            if (packet.is_data() or packet.is_ack()) and response_packet.is_ack():
                if response_packet.sequence_number == packet.sequence_number:
                    print(f"<- Received ACK for Seq: {response_packet.sequence_number}")
                    return response_packet
            else:
                continue
        
        # Handles timeouts and connection errors, incrementing the retry count and printing informative messages for debugging and user feedback.
        except socket.timeout:
            retries += 1
            print(f"!! Timeout occurred while waiting for ACK. Retrying... ({retries}/{MAX_RETRIES})")
       
        # Catches Windows ICMP "Port Unreachable" error
        except ConnectionResetError:
            retries += 1
            print(f"!! Connection refused (Server offline?). Retrying... ({retries}/{MAX_RETRIES})")
            
    print(f"XX Maximum retries reached. Connection lost.") 
    return None

# Helper function to send an error packet to the peer in case of critical failures, such as file not found or connection timeout.
def send_abort(sock, session_id, error_code, target_addr):
    print(f"XX Aborting connection, Sending ABORT (Error Code: {error_code})")
    error_packet = create_error_packet(session_id, error_code)
    sock.sendto(error_packet.pack(), target_addr)

# Function to manage the process of sending a file in chunks, including connection setup and teardown. 
def send_file(sock, filename, session_id, target_addr):
    # Checks prior to file transfer to ensure the file exists locally, providing immediate feedback and sending an error packet to the peer if the file is not found.
    if not os.path.exists(filename):
        print(f"XX Error: File '{filename}' not found. Aborting.")
        send_abort(sock, session_id, ErrorCode.FILE_NOT_FOUND, target_addr)
        return False
    
    print(f"-> Starting file transfer: {filename} to {target_addr}...")
    seq_number = 1
    
    # Reads the file in chunks and sends each chunk as a DATA packet, implementing reliable sending with acknowledgment and retry logic. 
    # If any chunk fails to send after maximum retries, the function aborts the transfer and sends an error packet to the peer.
    with open(filename, "rb") as f:
        while chunk:= f.read(CHUNK_SIZE): 
            data_packet = create_data_packet(session_id, seq_number, chunk)
           
           # Sends the DATA packet reliably, checking for acknowledgment and handling retries. 
           # If the packet fails to send after maximum retries, the transfer is aborted.
            if not send_reliable(sock, data_packet, target_addr):
               print(f"XX Failed to send chunk Seq: {seq_number} after max retries. Aborting transfer.")
               send_abort(sock, session_id, ErrorCode.CONNECTION_TIMEOUT, target_addr)
               return False
            
            seq_number += 1
            
    print(f"-> File transfer completed successfully. Total packets sent: {seq_number - 1}")
       
    # After sending all data chunks, sends a FIN packet to signal the end of the file transfer, and waits for a FIN-ACK response to confirm successful connection termination. 
    fin_packet = create_fin_packet(session_id, seq_number)
        
    if not send_reliable(sock, fin_packet, target_addr):
        print(f"XX Failed to send FIN packet. Forcing connection termination.")
        return True 
        
    print(f"-> File '{filename}' transferred and connection terminated.")
    return True

# Function to manage the process of receiving a file, including acknowledgment of received packets and handling connection termination.
def receive_file(sock, save_filename, session_id, expected_addr):
    print(f"-> Receving file from {expected_addr}, saving file as '{save_filename}'...")
    
    expected_seq = 1
    retries = 0
    sock.settimeout(TIMEOUT)
    
    # Receives packets in a loop, validating the source address and packet integrity, and acknowledging received DATA packets.
    # If a packet is received out of order, the receiver will resend an ACK for the last correctly received sequence number to prompt the sender to retransmit the missing packet.
    with open(save_filename, "wb") as f:
        while True:
            try:
                data, sender_addr = sock.recvfrom(4096) # Sets buffer size to 4096 to accommodate larger packets
                
                if sender_addr != expected_addr: continue # Ignore packets from unexpected sources
                
                packet = Packet.unpack(data)
                
                if not packet: continue # Ignore malformed packets that fail unpacking or checksum validation
                
                # Handles error packets received from the sender, printing the error code and aborting the reception process.
                if packet.is_error():
                    print(f"XX Received error from sender. Error Code: {packet.payload[0]}.")
                    return False
                
                # If a packet is received with a sequence number less than the expected sequence number, it means the sender did not receive the ACK for that packet.
                # In this case, the receiver will resend an ACK for the last correctly received sequence number
                if packet.sequence_number < expected_seq:
                    ack_packet = create_ack_packet(session_id, packet.sequence_number)
                    sock.sendto(ack_packet.pack(), expected_addr)
                    continue
                
                # Handles valid DATA packets that match the expected sequence number, acknowledging receipt and writing the payload to the file.
                if packet.is_data() and packet.sequence_number == expected_seq:
                    ack_packet = create_ack_packet(session_id, expected_seq)
                    sock.sendto(ack_packet.pack(), expected_addr)
                    
                    f.write(packet.payload)
                    print(f"<- Received DATA Seq: {expected_seq} ({len(packet.payload)} bytes)")
                
                    expected_seq += 1
                    retries = 0
                    continue
                
                # Handles FIN packets that match the expected sequence number, sending a FIN-ACK response and closing the connection gracefully.
                if packet.is_fin() and packet.sequence_number == expected_seq:
                    print(f"<- Received FIN packet. Sending FIN-ACK and closing connection.")
                    fin_ack_packet = create_fin_ack_packet(session_id, expected_seq)
                    sock.sendto(fin_ack_packet.pack(), expected_addr)
                    return True
                
            # Handles timeouts while waiting for packets, implementing retry logic and sending an error packet to the sender if the maximum number of retries is reached without receiving the expected packet.    
            except socket.timeout:
                retries += 1
                
                # If the receiver has been waiting for a packet for too long, it assumes the connection has been lost and sends an error packet to the sender to abort the transfer.
                if retries > MAX_RETRIES:
                    print(f"XX Maximum retries reached while waiting for packet. Aborting reception.")
                    send_abort(sock, session_id, ErrorCode.CONNECTION_TIMEOUT, expected_addr)
                    return False
                
                # If the receiver is waiting for a packet with a sequence number greater than 1, it means it has already received some packets and is waiting for the next one.
                # In this case, the receiver will resend an ACK for the last correctly received sequence number. 
                if expected_seq > 1:
                    print(f"!! Timeout waiting for Seq: {expected_seq}. Retrying... ({retries}/{MAX_RETRIES})")
                    ack_packet = create_ack_packet(session_id, expected_seq - 1)
                    sock.sendto(ack_packet.pack(), expected_addr)