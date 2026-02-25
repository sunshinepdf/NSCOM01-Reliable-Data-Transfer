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
# Python Library imports
import socket
import argparse
import sys
import os
import config

# Local imports
from engine import send_file, receive_file
from protocol import Packet, PacketType, Logger, create_syn_packet

# Function for connecting to the server and performing the handshake
def connect_to_server(sock, server_addr):
    
    Logger.info(f"Connecting to {server_addr}...")
    syn = create_syn_packet(session_id=0, sequence_number=0, payload=b"CONNECT")
    retries = 0
    
    # Attempt to connect and perform handshake with retries
    while retries < config.MAX_RETRIES:
        sock.sendto(syn.pack(), server_addr)
        try:
            data, _ = sock.recvfrom(4096)
            packet = Packet.unpack(data)
            
            Logger.received(packet)
            
            # Check if we received a SYN-ACK with a valid session ID
            if packet and packet.packet_type == PacketType.SYN_ACK:
                Logger.info(f"Connected Successfully! Assigned Session ID: {packet.session_id}")
                return packet.session_id
            
        # Handle timeouts and retry logic    
        except socket.timeout:
            retries += 1
            Logger.warn(f"Timeout waiting for connection. Retrying... ({retries}/{config.MAX_RETRIES})")
            
    return None

# Function to handle the menu loop for user commands and file transfers
def run_single_command(sock, server_addr, session_id, command, filename):
    
    Logger.info(f"Starting File Transfer (Sending SYN for {command.upper()})...")
    
    file_size = 0
    
    # For uploads, the program checks if the file exists and get its size before sending the SYN packet to the server.
    # For downloads, the SYN is just sent and the client waits for the SYN-ACK from the server. 
    if command == "upload":
        if not os.path.exists(filename):
            Logger.error(f"File {filename} does not exist.")
            return False
        file_size = os.path.getsize(filename)

    # The payload of the SYN packet includes the command, filename, and file size (for uploads) in a structured format.
    payload_str = f"{command.upper()}|{filename}|{file_size}"
    syn_packet = create_syn_packet(session_id, 0, payload_str.encode("utf-8"))
    
    retries = 0
    syn_ack_packet = None

    # The client will send the SYN packet and wait for a SYN-ACK response from the server. 
    # If it does not receive a response within the timeout period, it will retry sending the SYN packet up to a maximum number of retries defined in the configuration. 
    # If it receives a SYN-ACK, it will proceed with the file transfer based on the command (upload or download). 
    # If it fails to receive a SYN-ACK after all retries, it will log an error and return False to indicate that the transfer was aborted.
    while retries < config.MAX_RETRIES:
        sock.sendto(syn_packet.pack(), server_addr)
        try:
            data, addr = sock.recvfrom(4096)
            if addr != server_addr: continue # Ignore packets from unknown sources
            
            packet = Packet.unpack(data)
            if not packet: continue # Ignore malformed packets
            
            if packet.is_error(): # Handle error packets from the server
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
            
            # Check if we received a SYN-ACK with the correct session ID  
            if packet.packet_type == PacketType.SYN_ACK:
                if packet.session_id != session_id:
                    Logger.warn(
                        f"Ignoring SYN-ACK with mismatched session (expected {session_id}, got {packet.session_id})."
                    )
                    continue
                syn_ack_packet = packet
                break
        
        # Handle timeouts and retry logic
        except socket.timeout:
            retries += 1
            Logger.warn(f"Timeout waiting for SYN-ACK. Retrying... ({retries}/{config.MAX_RETRIES})")

    # If we exhausted all retries without receiving a valid SYN-ACK, log an error and return False to indicate that the transfer was aborted.
    if not syn_ack_packet:
        Logger.error(f"Handshake failed. Transfer cancelled.")
        return False

    # If we received a valid SYN-ACK, we proceed with the file transfer based on the command.
    if command == "upload":
        return send_file(sock, filename, session_id, server_addr)
    
    elif command == "download":
        server_filesize = int(syn_ack_packet.payload.decode("utf-8")) if syn_ack_packet.payload else 0
        Logger.info(f"Server reports file size: {server_filesize} bytes")
        save_name = f"downloaded_{filename}"
        return receive_file(sock, save_name, session_id, server_addr)

# Function to display the menu and handle user input for file transfer commands
def menu_loop(sock, server_addr, session_id):
    transfer_success = True
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
            transfer_success = run_single_command(sock, server_addr, session_id, "download", filename)
        elif choice == "2":
            filename = input("Enter filename to upload: ").strip()
            transfer_success = run_single_command(sock, server_addr, session_id, "upload", filename)
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
    
    return transfer_success

# Function to discover the server on the local network using a broadcast message
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

# Main function to parse command-line arguments, establish connection with the server, and start the menu loop for file transfers
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

        transfer_success = menu_loop(sock, server_addr, active_session_id)

        if transfer_success:
            print("\n-> Client finished successfully.")
        else:
            print("\nXX Client aborted due to errors.")
            
if __name__ == "__main__":
    main()
