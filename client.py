"""
NSCOM01 - Machine Project 1
Implementation of Reliable Data Transfer over UDP
Khyle Villorente and Raina Helaga

This module implements the client-side logic for the reliable file transfer protocol over UDP.
The client is responsible for initiating the connection with the server, sending or receiving files based on user commands, and handling the termination of the connection.

The client performs the following steps:
    1. Parses command-line arguments to determine the server address, port, command (upload/download), and filename.
    2. Initiates a handshake with the server by sending a SYN packet containing the command and filename, and waits for a SYN-ACK response to confirm the connection and obtain the session ID.
    3. Depending on the command, either sends the file to the server (upload) or receives the file from the server (download) using reliable data transfer functions that handle acknowledgments and retransmissions.
    4. After the file transfer is complete, checks the success status and prints a final message indicating whether the transfer finished successfully or was aborted due to errors.

The client relies on the Packet class and related constants defined in protocol.py, as well as configuration parameters from config.py.
"""

import socket
import argparse
import sys
import os
import config

from engine import send_file, receive_file
from protocol import Packet, PacketType, Logger, create_syn_packet

def connect_to_server(sock, server_addr):
    Logger.info(f"Connecting to {server_addr}...")
    syn = create_syn_packet(session_id=0, sequence_number=0, payload=b"CONNECT")
    retries = 0
    
    while retries < config.MAX_RETRIES:
        sock.sendto(syn.pack(), server_addr)
        try:
            data, _ = sock.recvfrom(4096)
            packet = Packet.unpack(data)
            
            Logger.received(packet)
            
            if packet and packet.packet_type == PacketType.SYN_ACK:
                Logger.info(f"Connected Successfully! Assigned Session ID: {packet.session_id}")
                return packet.session_id
        except socket.timeout:
            retries += 1
            Logger.warn(f"Timeout waiting for connection. Retrying... ({retries}/{config.MAX_RETRIES})")
            
    return None

def run_single_command(sock, server_addr, session_id, command, filename):
    Logger.info(f"Starting File Transfer (Sending SYN for {command.upper()})...")
    
    file_size = 0
    if command == "upload":
        if not os.path.exists(filename):
            Logger.error(f"File {filename} does not exist.")
            return False
        file_size = os.path.getsize(filename)

    payload_str = f"{command.upper()}|{filename}|{file_size}"
    syn_packet = create_syn_packet(session_id, 0, payload_str.encode("utf-8"))
    
    retries = 0
    syn_ack_packet = None

    while retries < config.MAX_RETRIES:
        sock.sendto(syn_packet.pack(), server_addr)
        try:
            data, addr = sock.recvfrom(4096)
            if addr != server_addr: continue
            
            packet = Packet.unpack(data)
            if not packet: continue
            
            if packet.is_error():
                err_code = packet.payload[0]
                err_msg = {
                    1: "FILE NOT FOUND", 
                    2: "SESSION MISMATCH", 
                    3: "CHECKSUM ERROR",
                    4: "UNKNOWN PACKET TYPE",
                    5: "CONNECTION TIMEOUT"
                }.get(err_code, f"UNKNOWN ERROR ({err_code})")
                
                Logger.error(f"Server returned Error: {err_msg}")
                return False
                
            if packet.packet_type == PacketType.SYN_ACK:
                if packet.session_id != session_id:
                    Logger.warn(
                        f"Ignoring SYN-ACK with mismatched session (expected {session_id}, got {packet.session_id})."
                    )
                    continue
                syn_ack_packet = packet
                break
        except socket.timeout:
            retries += 1
            Logger.warn(f"Timeout waiting for SYN-ACK. Retrying... ({retries}/{config.MAX_RETRIES})")

    if not syn_ack_packet:
        Logger.error(f"Handshake failed. Transfer cancelled.")
        return False

    if command == "upload":
        return send_file(sock, filename, session_id, server_addr)
    elif command == "download":
        server_filesize = int(syn_ack_packet.payload.decode("utf-8")) if syn_ack_packet.payload else 0
        Logger.info(f"Server reports file size: {server_filesize} bytes")
        save_name = f"downloaded_{filename}"
        return receive_file(sock, save_name, session_id, server_addr)

def menu_loop(sock, server_addr, session_id):
    while True:
        print("\n" + "="*25)
        print("      CLIENT MENU")
        print("="*25)
        print("1. Download File")
        print("2. Upload File")
        print("3. Exit")
        print(f"4. [DEMO] Toggle Packet Loss (Current: {config.SIMULATE_LOSS})")
        print(f"5. [DEMO] Toggle Corruption (Current: {config.SIMULATE_CORRUPTION})")
        print(f"6. [DEMO] Toggle Session Mismatch (Current: {config.SIMULATE_MISMATCH})")
        
        choice = input("\nChoose an option: ").strip()

        if choice == "1":
            filename = input("Enter filename to download: ").strip()
            run_single_command(sock, server_addr, session_id, "download", filename)
        elif choice == "2":
            filename = input("Enter filename to upload: ").strip()
            run_single_command(sock, server_addr, session_id, "upload", filename)
        elif choice == "3":
            Logger.info("Disconnecting from server...")
            disconnect_packet = create_syn_packet(session_id, 0, b"DISCONNECT")
            sock.sendto(disconnect_packet.pack(), server_addr)
            
            print("Goodbye!")
            break
        elif choice == "4":
            config.SIMULATE_LOSS = not config.SIMULATE_LOSS
            Logger.demo(f"Packet Loss Simulation is now {'ENABLED' if config.SIMULATE_LOSS else 'DISABLED'}")
        elif choice == "5":
            config.SIMULATE_CORRUPTION = not config.SIMULATE_CORRUPTION
            Logger.demo(f"Checksum Corruption Simulation is now {'ENABLED' if config.SIMULATE_CORRUPTION else 'DISABLED'}")
        elif choice == "6":
            config.SIMULATE_MISMATCH = not config.SIMULATE_MISMATCH
            Logger.demo(f"Session Mismatch Simulation is now {'ENABLED' if config.SIMULATE_MISMATCH else 'DISABLED'}")
        else:
            Logger.warn("Invalid choice.")

def discover_server(port):
    print("-> Discovering server...")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as bsock:
        bsock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        bsock.settimeout(2.0)
        
        discovery_packet = create_syn_packet(0, 0, b"DISCOVER")
        bsock.sendto(discovery_packet.pack(), ("255.255.255.255", port))
        
        try:
            _, addr = bsock.recvfrom(4096)
            return addr
        except socket.timeout:
            return None

def main():
    parser = argparse.ArgumentParser(description="Reliable UDP File Transfer Client")
    
    parser.add_argument(
        "-s", "--server", 
        default=config.SERVER_IP, 
        help=f"Server address"
    )
    
    parser.add_argument(
        "-p", "--port", 
        type=int, 
        default=config.SERVER_PORT, 
        help=f"Server port"
    )
    
    print("[💡 TIP: You can connect to a specific server!]")
    parser.print_usage()
    print("\n")
    
    args = parser.parse_args()
    
    server_addr = (socket.gethostbyname(args.server), args.port)

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(config.TIMEOUT)

        if args.server != "0.0.0.0":
            server_addr = (args.server, args.port)
            Logger.info(f"No specified server, using default server: {server_addr}")
        else:
            server_addr = discover_server(args.port)

        if not server_addr:
            Logger.error(f"Server address not found. Please ensure the server is running and reachable.")
            sys.exit(1)

        active_session_id = connect_to_server(sock, server_addr)
        if not active_session_id:
            Logger.error(f"Failed to establish session with server {server_addr}. Exiting.")
            sys.exit(1)

        menu_loop(sock, server_addr, active_session_id)

        # State 3: Termination - After the file transfer is complete, the client checks the success status and prints a final message indicating whether the transfer finished successfully or was aborted due to errors.
        if transfer_success:
            print("\n-> Client finished successfully.")
        else:
            print("\nXX Client aborted due to errors.")
            
if __name__ == "__main__":
    main()
