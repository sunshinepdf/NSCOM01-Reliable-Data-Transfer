"""
NSCOM01 - Machine Project 1
Implementation of Reliable Data Transfer over UDP
Khyle Villorente and Raina Helaga

server.py

This module handles the server side of our reliable UDP file transfer project.
The server does the following:

    1. Waits for a SYN packet from the client to start the handshake.
    2. Creates a session ID and sends back a SYN-ACK to confirm the connection.
    3. If the client chooses UPLOAD, the server receives the file and saves it.
    4. If the client chooses DOWNLOAD, the server sends the requested file.
    5. Sends ERROR packets when needed, when the file does not exist or the session ID is wrong.

This file works together with protocol.py for packet creation and parsing, engine.py for reliable send and receive logic, and config.py for server settings like IP, port, and timeout.

"""

import socket
import os
import random

from config import SERVER_IP, SERVER_PORT, TIMEOUT
from protocol import (
    Packet, ErrorCode,
    create_syn_ack_packet,
    create_error_packet
)
from engine import send_file, receive_file


def parse_syn_payload(payload):
    try:
        text = payload.decode("utf-8")
        parts = text.split("|", 1)

        if len(parts) != 2:
            return None, None

        command = parts[0].strip().upper()
        filename = parts[1].strip()

        if command not in ["UPLOAD", "DOWNLOAD"]:
            return None, None
        if filename == "":
            return None, None

        return command, filename
    except Exception:
        return None, None


def generate_session_id(used_ids):
    while True:
        sid = random.randint(1, 65535)
        if sid not in used_ids:
            return sid


def main():
    server_addr = (SERVER_IP, SERVER_PORT)
    print(f"-> Server starting on {server_addr}")

    sessions = {}
    used_session_ids = set()

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(server_addr)
        sock.settimeout(TIMEOUT)

        while True:
            try:
                data, client_addr = sock.recvfrom(4096)
            except socket.timeout:
                continue

            packet = Packet.unpack(data)
            if not packet:
                continue

            # HANDSHAKE
            if packet.is_syn():
                command, filename = parse_syn_payload(packet.payload)

                if not command:
                    print(f"XX Invalid SYN payload from {client_addr}. Sending ERROR.")
                    err_packet = create_error_packet(0, ErrorCode.UNKNOWN_PACKET_TYPE)
                    sock.sendto(err_packet.pack(), client_addr)
                    continue

                session_id = generate_session_id(used_session_ids)
                used_session_ids.add(session_id)
                sessions[client_addr] = session_id

                print("\n<- SYN received")
                print(f"   From: {client_addr}")
                print(f"   Request: {command} | File: {filename}")
                print(f"   Assigned Session ID: {session_id}")

                syn_ack = create_syn_ack_packet(session_id=session_id, sequence_number=0)
                sock.sendto(syn_ack.pack(), client_addr)
                print("-> Sent SYN-ACK")

                # FILE OPERATION
                if command == "UPLOAD":
                    save_name = f"uploaded_{os.path.basename(filename)}"
                    ok = receive_file(sock, save_name, session_id, client_addr)

                    if ok:
                        print(f"-> Upload complete. Saved as '{save_name}'")
                    else:
                        print("XX Upload failed.")

                    sessions.pop(client_addr, None)
                    used_session_ids.discard(session_id)
                    continue

                if command == "DOWNLOAD":
                    if not os.path.exists(filename):
                        print(f"XX File '{filename}' not found. Sending ERROR.")
                        err_packet = create_error_packet(session_id, ErrorCode.FILE_NOT_FOUND)
                        sock.sendto(err_packet.pack(), client_addr)

                        sessions.pop(client_addr, None)
                        used_session_ids.discard(session_id)
                        continue

                    ok = send_file(sock, filename, session_id, client_addr)

                    if ok:
                        print("-> Download complete.")
                    else:
                        print("XX Download failed.")

                    sessions.pop(client_addr, None)
                    used_session_ids.discard(session_id)
                    continue

            # SESSION CHECK for non-SYN packets
            known_session = sessions.get(client_addr)
            if known_session is None or packet.session_id != known_session:
                print(f"XX Session mismatch from {client_addr}. Sending ERROR.")
                err_packet = create_error_packet(packet.session_id, ErrorCode.SESSION_MISMATCH)
                sock.sendto(err_packet.pack(), client_addr)
                continue

            print(f"!! Unexpected packet from {client_addr}: {packet}")


if __name__ == "__main__":
    main()