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
import time

# Local imports
from engine import send_reliable, send_file, receive_file
from protocol import Packet, create_syn_packet
from config import SERVER_IP, SERVER_PORT, TIMEOUT


def discover_server(port, retries=3, wait_time=0.5):
    
    # Broadcast a DISCOVER SYN to find an active server
    # Tries 3 times, waits 0.5 seconds between retries 
    
    broadcast_addr = ("255.255.255.255", port)

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.settimeout(TIMEOUT)

        discover_packet = create_syn_packet(session_id=0, sequence_number=0, payload=b"DISCOVER")

        for attempt in range(1, retries + 1):
            print(f"-> Broadcasting handshake request... Attempt {attempt}...")
            s.sendto(discover_packet.pack(), broadcast_addr)

            try:
                data, addr = s.recvfrom(4096)
                pkt = Packet.unpack(data)
                if pkt and pkt.is_syn_ack():
                    print(f"-> Server found at {addr[0]}:{addr[1]}")
                    return (addr[0], addr[1])
            except socket.timeout:
                time.sleep(wait_time)

    print("XX No active server found.")
    return None


def do_handshake(sock, server_addr, command, filename):
    
    # Sends SYN with payload: 'UPLOAD|filename' or 'DOWNLOAD|filename'
    # Returns session_id if successful, else None
    
    syn_payload = f"{command.upper()}|{filename}".encode("utf-8")
    syn_packet = create_syn_packet(session_id=0, sequence_number=0, payload=syn_payload)

    print("-> Initiating Handshake (Sending SYN)...")
    syn_ack_packet = send_reliable(sock, syn_packet, server_addr)

    if not syn_ack_packet:
        print("XX Handshake failed. Server unresponsive or connection refused.")
        return None

    if syn_ack_packet.is_error():
        print(f"XX Server rejected connection. Error Code: {syn_ack_packet.payload[0]}")
        return None

    print(f"-> Handshake successful! Assigned Session ID: {syn_ack_packet.session_id}")
    return syn_ack_packet.session_id


def run_single_command(sock, server_addr, command, filename):
    
    # Runs one upload/download command, CLI mode
    
    if command == "upload" and not os.path.exists(filename):
        print(f"XX Error: Local file '{filename}' does not exist.")
        return False

    session_id = do_handshake(sock, server_addr, command, filename)
    if session_id is None:
        return False

    if command == "upload":
        return send_file(sock, filename, session_id, server_addr)

    # download
    save_name = f"downloaded_{filename}"
    return receive_file(sock, save_name, session_id, server_addr)


def menu_loop(sock, server_addr):
    
    # Menu mode: user can upload/download multiple times
    # Each request does its own handshake 
    
    while True:
        print("\n====== CLIENT MENU ======")
        print("1. Download File")
        print("2. Upload File")
        print("3. Exit")
        choice = input("Choose option: ").strip()

        if choice == "1":
            fname = input("Enter filename to download: ").strip()
            if not fname:
                print("XX Invalid filename.")
                continue

            ok = run_single_command(sock, server_addr, "download", fname)
            print("-> Download done." if ok else "XX Download failed.")

        elif choice == "2":
            path = input("Enter filepath to upload: ").strip()
            if not path:
                print("XX Invalid filepath.")
                continue

            ok = run_single_command(sock, server_addr, "upload", path)
            print("-> Upload done." if ok else "XX Upload failed.")

        elif choice == "3":
            print("-> Exiting client.")
            break

        else:
            print("XX Invalid option.")

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
    parser.add_argument("command", nargs="?", choices=["upload", "download"], help="Action to perform")
    parser.add_argument("filename", nargs="?", help="Name of the file to transfer")

    args = parser.parse_args()

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(TIMEOUT)

        if args.command and args.filename:
            server_addr = (socket.gethostbyname(args.server), args.port)

            print(f"-> Starting client. Target Server: {server_addr}")
            print(f"-> Action: {args.command.upper()} | File: {args.filename}")

            ok = run_single_command(sock, server_addr, args.command, args.filename)

            if ok:
                print("\n-> Client finished successfully.")
            else:
                print("\nXX Client aborted due to errors.")
            return

        # Otherwise, run menu mode + optional DISCOVER
        print("-> No command given. Running menu mode.")
        server_addr = discover_server(args.port)

        if not server_addr:
            sys.exit(1)

        print(f"-> Connected Target Server: {server_addr}")
        menu_loop(sock, server_addr)


if __name__ == "__main__":
    main()
            

    