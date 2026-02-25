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

# Local imports
from engine import send_reliable, send_file, receive_file
from protocol import Packet, create_syn_packet
from config import SERVER_IP, SERVER_PORT, TIMEOUT


def main():
    # Initialize argument parser for command-line interface, allowing users to specify server address, port, command (upload/download), and filename. 
    # Provides defaults for server IP and port for ease of testing, while also validating the presence of the local file for upload commands before proceeding with the connection.
    parser = argparse.ArgumentParser(description="Reliable UDP File Transfer Client")

    # Command-line arguments for server address and port, with defaults set to localhost and a predefined port for ease of testing.
    # Can be customized using the -s/--server and -p/--port flags when running the client script or overwriting the defaults in config.py.
    
    parser.add_argument(
        "-s", "--server", 
        default=SERVER_IP, 
        help=f"Server address (default: {SERVER_IP})"
    )
    parser.add_argument(
        "-p", "--port", 
        type=int, 
        default=SERVER_PORT, 
        help=f"Server port (default: {SERVER_PORT})"
    )
    
    # Defines required positional arguments for the command (upload/download) and the filename to be transferred.
    parser.add_argument("command", choices=["upload", "download"], help="Action to perform")
    parser.add_argument("filename", help="Name of the file to transfer")

    args = parser.parse_args()
    
    server_addr = (socket.gethostbyname(args.server), args.port)

    # Checks if the specified file exists locally when the command is 'upload'.
    if args.command == "upload" and not os.path.exists(args.filename):
        print(f"XX Error: Local file '{args.filename}' does not exist.")
        sys.exit(1)

    # Starts the client by printing the target server address and the requested action, including the filename. 
    print(f"-> Starting client. Target Server: {server_addr}")
    print(f"-> Action: {args.command.upper()} | File: {args.filename}")

    # Creates a UDP socket and sets a timeout for receiving responses from the server. 
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(TIMEOUT)

        # State 1: Handshake - The client initiates the connection by sending a SYN packet to the server, containing the command and filename in the payload.
        # Waits for a SYN-ACK response from the server to confirm the connection and extract the assigned session ID for subsequent communication.
        syn_payload = f"{args.command.upper()}|{args.filename}".encode('utf-8')
        syn_packet = create_syn_packet(session_id=0, sequence_number=0, payload=syn_payload)
        
        print("-> Initiating Handshake (Sending SYN)...")
        syn_ack_packet = send_reliable(sock, syn_packet, server_addr)

        if not syn_ack_packet:
            print("XX Handshake failed. Server unresponsive or connection refused.")
            sys.exit(1)

        if syn_ack_packet.is_error():
            print(f"XX Server rejected connection. Error Code: {syn_ack_packet.payload[0]}")
            sys.exit(1)

        session_id = syn_ack_packet.session_id
        print(f"-> Handshake successful! Assigned Session ID: {session_id}")

        # State 2: File Transfer - Depending on the command, the client either sends the file to the server (upload) or receives the file from the server (download).
        # The send_file and receive_file functions handle the reliable data transfer logic, including acknowledgment handling and retransmissions as needed.
        transfer_success = False
        
        if args.command == "upload": # The client initiates an upload by calling the send_file function.
            transfer_success = send_file(sock, args.filename, session_id, server_addr)
            
        elif args.command == "download": # The client initiates a download by calling the receive_file function, specifying a save name for the downloaded file.
            save_name = f"downloaded_{args.filename}"
            transfer_success = receive_file(sock, save_name, session_id, server_addr)

        # State 3: Termination - After the file transfer is complete, the client checks the success status and prints a final message indicating whether the transfer finished successfully or was aborted due to errors.
        if transfer_success:
            print("\n-> Client finished successfully.")
        else:
            print("\nXX Client aborted due to errors.")
            
if __name__ == "__main__":
    main()
    
    