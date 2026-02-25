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

# Python Library imports
import socket
import os
import random
import struct
import config

# Local imports
from protocol import (
    Packet, ErrorCode, Logger,
    create_ack_packet, create_error_packet, 
    create_data_packet, create_fin_packet,
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
            current_payload = raw_bytes
            
            if config.SIMULATE_CORRUPTION and random.random() < config.FAILURE_RATE:
                Logger.demo(f"Corrupting Checksum for Seq {packet.sequence_number}...")
                list_bytes = list(raw_bytes)
                list_bytes[10] = (list_bytes[10] + 1) % 256 
                current_payload = bytes(list_bytes)

            elif config.SIMULATE_MISMATCH and random.random() < config.FAILURE_RATE:
                Logger.demo("Spoofing Session ID to trigger MISMATCH...")
                malicious_packet = Packet(packet.packet_type, 9999, packet.sequence_number, packet.payload)
                current_payload = malicious_packet.pack()

            if config.SIMULATE_LOSS and random.random() < config.FAILURE_RATE:
                Logger.demo(f"Dropping Packet Seq {packet.sequence_number}...")
            
            else:
                Logger.sent(packet)
                sock.sendto(current_payload, target_addr)
            
            response_data, addr = sock.recvfrom(4096) # Sets buffer size to 4096 to accommodate larger packets
            # Ignore packets from unexpected sources
            if addr != target_addr: continue
            
            response_packet = Packet.unpack(response_data) # Unpack the response packet and validate it
            # Ignore malformed packets that fail unpacking or checksum validation
            if not response_packet: continue 

            if response_packet.session_id != packet.session_id:
                Logger.warn(
                    f"Session mismatch in response (expected {packet.session_id}, got {response_packet.session_id}). Ignoring packet."
                )
                continue
            
            Logger.received(response_packet)
            
            # Handle different error response types based on the original packet type and the response packet type
            if response_packet.is_error():
                err_code = response_packet.payload[0]
                err_msg = {1: "FILE NOT FOUND", 2: "SESSION MISMATCH", 3: "CHECKSUM ERROR", 4: "UNKNOWN PACKET TYPE", 5: "CONNECTION TIMEOUT"}.get(err_code, "UNKNOWN")
                if err_code == ErrorCode.CHECKSUM_FAILURE:
                    retries += 1
                    Logger.warn(f"Remote reported checksum failure. Retrying packet... ({retries}/{MAX_RETRIES})")
                    continue

                Logger.error(f"Remote returned Error: {err_msg}")
                return False
            
            # Validates if the response packet is the expected acknowledgment for a SYN packet.
            if packet.is_syn() and response_packet.is_syn_ack():
                Logger.info(f"Received SYN-ACK for Session ID: {response_packet.session_id}")
                Logger.received(response_packet)
                return response_packet
            
            # Validates if the response packet is the expected acknowledgment for a FIN packet.
            if packet.is_fin() and response_packet.is_fin_ack():
                Logger.info(f"Received FIN-ACK for Session ID: {response_packet.session_id}")
                Logger.received(response_packet)
                return response_packet
            
            # Validates if the response packet is the expected acknowledgment for a DATA packet, matching the sequence number.
            if (packet.is_data() or packet.is_ack()) and response_packet.is_ack():
                if response_packet.sequence_number == packet.sequence_number:
                    Logger.info(f"Received ACK for Seq: {response_packet.sequence_number}")
                    Logger.received(response_packet)    
                    return response_packet
            else:
                continue
        
        # Handles timeouts and connection errors, incrementing the retry count and printing informative messages for debugging and user feedback.
        except socket.timeout:
            retries += 1
            Logger.warn(f"Timeout occurred while waiting for ACK. Retrying... ({retries}/{MAX_RETRIES})")
       
        # Catches Windows ICMP "Port Unreachable" error
        except ConnectionResetError:
            retries += 1
            Logger.warn(f"Connection refused (Server offline?). Retrying... ({retries}/{MAX_RETRIES})")
            
    print(f"XX Maximum retries reached. Connection lost.") 
    return None

# Helper function to send an error packet to the peer in case of critical failures, such as file not found or connection timeout.
def send_abort(sock, session_id, error_code, target_addr):
    Logger.error(f"Aborting connection, Sending ABORT (Error Code: {error_code})")
    error_packet = create_error_packet(session_id, error_code)
    sock.sendto(error_packet.pack(), target_addr)


# Function to manage the process of sending a file in chunks, including connection setup and teardown. 
def send_file(sock, filename, session_id, target_addr):
    # Checks prior to file transfer to ensure the file exists locally, providing immediate feedback and sending an error packet to the peer if the file is not found.
    if not os.path.exists(filename):
        Logger.error(f"File '{filename}' not found. Aborting.")
        send_abort(sock, session_id, ErrorCode.FILE_NOT_FOUND, target_addr)
        return False
    
    Logger.info(f"Sending file: {filename} to {target_addr}")
    seq_number = 1
    
    # Reads the file in chunks and sends each chunk as a DATA packet, implementing reliable sending with acknowledgment and retry logic. 
    # If any chunk fails to send after maximum retries, the function aborts the transfer and sends an error packet to the peer.
    with open(filename, "rb") as f:
        while chunk:= f.read(CHUNK_SIZE): 
            data_packet = create_data_packet(session_id, seq_number, chunk)
           
           # Sends the DATA packet reliably, checking for acknowledgment and handling retries. 
           # If the packet fails to send after maximum retries, the transfer is aborted.
            if not send_reliable(sock, data_packet, target_addr):
               Logger.error(f"Failed to send chunk Seq: {seq_number} after max retries. Aborting transfer.")
               send_abort(sock, session_id, ErrorCode.CONNECTION_TIMEOUT, target_addr)
               return False
            
            seq_number += 1
            
    Logger.info(f"File transfer completed successfully. Total packets sent: {seq_number - 1}")
       
    # After sending all data chunks, sends a FIN packet to signal the end of the file transfer, and waits for a FIN-ACK response to confirm successful connection termination. 
    fin_packet = create_fin_packet(session_id, seq_number)
        
    if not send_reliable(sock, fin_packet, target_addr):
        Logger.error(f"Failed to send FIN packet.")
        return False 
        
    Logger.info(f"File '{filename}' transferred successfully.")
    return True

# Function to manage the process of receiving a file, including acknowledgment of received packets and handling connection termination.
def receive_file(sock, save_filename, session_id, expected_addr):
    Logger.info(f"Receiving file from {expected_addr}, saving file as '{save_filename}'...")
    
    expected_seq = 1
    retries = 0
    sock.settimeout(TIMEOUT)
    
    file_opened = False
    f = None
    
    try:
        while True:
            try:
                data, sender_addr = sock.recvfrom(4096)
                if sender_addr != expected_addr: continue 
                
                packet = Packet.unpack(data)
                
                # Ignore malformed packets that fail unpacking or checksum validation
                if not packet:
                    if len(data) >= Packet.HEADER_SIZE:
                        try:
                            header = data[:Packet.HEADER_SIZE]
                            packet_type, parsed_session_id, sequence_number, payload_length, checksum = struct.unpack(Packet.HEADER_FORMAT, header)

                            if len(data) >= Packet.HEADER_SIZE + payload_length:
                                payload = data[Packet.HEADER_SIZE:Packet.HEADER_SIZE + payload_length]
                                probe_packet = Packet(packet_type, parsed_session_id, sequence_number, payload)

                                if probe_packet.calculate_checksum() != checksum:
                                    Logger.warn(f"Checksum failure detected for Seq: {sequence_number}. Packet dropped.")
                                    checksum_error = create_error_packet(session_id, ErrorCode.CHECKSUM_FAILURE)
                                    Logger.sent(checksum_error)
                                    sock.sendto(checksum_error.pack(), expected_addr)
                        except Exception:
                            pass

                    continue
                
                Logger.received(packet)

                # Validate session ID to ensure the packet belongs to the current transfer session. 
                # If there is a mismatch, send an error packet back to the sender and ignore the packet.
                if packet.session_id != session_id:
                    Logger.warn(
                        f"Session mismatch in incoming packet (expected {session_id}, got {packet.session_id}). Packet dropped."
                    )
                    mismatch_error = create_error_packet(session_id, ErrorCode.SESSION_MISMATCH)
                    Logger.sent(mismatch_error)
                    sock.sendto(mismatch_error.pack(), expected_addr)
                    continue
                
                # Handle error packets received from the sender, logging the error message and aborting the reception if a critical error is reported.
                if packet.is_error():
                    err_code = packet.payload[0]
                    err_msg = {1: "FILE NOT FOUND", 2: "SESSION MISMATCH", 3: "CHECKSUM ERROR", 4: "UNKNOWN PACKET TYPE", 5: "CONNECTION TIMEOUT"}.get(err_code, "UNKNOWN")
                    Logger.error(f"Received error from sender: {err_msg}")
                    return False
                
                # If the packet is a DATA packet, check if it is the expected sequence number. 
                # If it is a duplicate (sequence number less than expected), resend the ACK for that sequence number.
                if packet.sequence_number < expected_seq:
                    ack_packet = create_ack_packet(session_id, packet.sequence_number)
                    Logger.sent(ack_packet)
                    sock.sendto(ack_packet.pack(), expected_addr)
                    continue
                
                # If the packet is a DATA packet with the expected sequence number, write the payload to the file, send an ACK for that sequence number, and increment the expected sequence number.
                if packet.is_data() and packet.sequence_number == expected_seq:
                    ack_packet = create_ack_packet(session_id, expected_seq)
                    sock.sendto(ack_packet.pack(), expected_addr)
                    
                    if not file_opened:
                        f = open(save_filename, "wb")
                        file_opened = True
                        
                    f.write(packet.payload)
                    Logger.received(packet)
                
                    expected_seq += 1
                    retries = 0
                    continue
                
                # If the packet is a FIN packet with the expected sequence number, send a FIN-ACK to confirm successful reception of the entire file and end the transfer session.
                if packet.is_fin() and packet.sequence_number == expected_seq:
                    Logger.info(f"Received FIN packet. Sending FIN-ACK and ending file transfer.")
                    fin_ack_packet = create_fin_ack_packet(session_id, expected_seq)
                    sock.sendto(fin_ack_packet.pack(), expected_addr)
                    return True
           
           # Handle unexpected packets that do not match the expected sequence number or packet type, sending appropriate error responses and ignoring the packets.     
            except socket.timeout:
                retries += 1
                if retries > MAX_RETRIES:
                    Logger.error(f"Maximum retries reached while waiting for packet. Aborting reception.")
                    send_abort(sock, session_id, ErrorCode.CONNECTION_TIMEOUT, expected_addr)
                    if file_opened:
                        f.close()
                        os.remove(save_filename)
                    return False
                
                if expected_seq > 1:
                    Logger.warn(f"Timeout waiting for Seq: {expected_seq}. Retrying... ({retries}/{MAX_RETRIES})")
                    ack_packet = create_ack_packet(session_id, expected_seq - 1)
                    sock.sendto(ack_packet.pack(), expected_addr)
    finally:
        if file_opened and not f.closed:
            f.close()