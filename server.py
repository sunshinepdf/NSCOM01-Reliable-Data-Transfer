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
import threading
import config

from config import SERVER_IP, SERVER_PORT
from protocol import (
    Packet, ErrorCode, PacketType, Logger,
    create_syn_ack_packet,
    create_error_packet
)
from engine import send_file, receive_file

def server_console_loop():
    print("\n[SERVER CONTROLS]")
    print("Type one of the following anytime:")
    print("  loss      -> toggle packet loss simulation")
    print("  corrupt   -> toggle checksum corruption simulation")
    print("  mismatch  -> toggle session mismatch simulation")
    print("  status    -> show current simulation flags")
    print("  help      -> show controls\n")

    while True:
        try:
            cmd = input().strip().lower()

            if cmd == "loss":
                config.SIMULATE_LOSS = not config.SIMULATE_LOSS
                Logger.demo(f"[SERVER] Packet Loss Simulation: {'ENABLED' if config.SIMULATE_LOSS else 'DISABLED'}")

            elif cmd == "corrupt":
                config.SIMULATE_CORRUPTION = not config.SIMULATE_CORRUPTION
                Logger.demo(
                    f"[SERVER] Checksum Corruption Simulation: {'ENABLED' if config.SIMULATE_CORRUPTION else 'DISABLED'}"
                )

            elif cmd == "mismatch":
                config.SIMULATE_MISMATCH = not config.SIMULATE_MISMATCH
                Logger.demo(f"[SERVER] Session Mismatch Simulation: {'ENABLED' if config.SIMULATE_MISMATCH else 'DISABLED'}")

            elif cmd == "status":
                Logger.info(
                    "[SERVER] Sim Flags -> "
                    f"LOSS={config.SIMULATE_LOSS}, "
                    f"CORRUPT={config.SIMULATE_CORRUPTION}, "
                    f"MISMATCH={config.SIMULATE_MISMATCH}, "
                    f"FAILURE_RATE={config.FAILURE_RATE}"
                )

            elif cmd == "help":
                print("Commands: loss | corrupt | mismatch | status | help")

            elif cmd:
                Logger.warn("Unknown command. Type 'help' for options.")

        except EOFError:
            break
        
        except Exception as e:
            Logger.warn(f"Server control input error: {e}")

def parse_syn_payload(payload):
    
    if payload == b"CONNECT":
        return "CONNECT", None, 0
    if payload == b"DISCONNECT":
        return "DISCONNECT", None, 0
    try:
        text = payload.decode("utf-8")
        parts = text.split("|")

        command = parts[0].strip().upper()
        filename = parts[1].strip() if len(parts) > 1 else ""
        filesize = int(parts[2].strip()) if len(parts) > 2 else 0

        if command not in ["UPLOAD", "DOWNLOAD", "CONNECT"]:
            return None, None, 0
        return command, filename, filesize
    except:
        return None, None, 0

def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((SERVER_IP, SERVER_PORT))
    Logger.info(f"Server started on {SERVER_IP}:{SERVER_PORT}")
    print(f"Waiting for client connections...")

    control_thread = threading.Thread(target=server_console_loop, daemon=True)
    control_thread.start()

    sessions = {}
    used_session_ids = set()

    while True:
        try:
            sock.settimeout(1.0)
            try:
                data, client_addr = sock.recvfrom(4096)
            except socket.timeout:
                continue

            packet = Packet.unpack(data)
            if not packet:
                continue

            if packet.packet_type == PacketType.SYN:
                command, filename, filesize = parse_syn_payload(packet.payload)

                if command == "CONNECT":
                    session_id = random.randint(1000, 9999)
                    while session_id in used_session_ids:
                        session_id = random.randint(1000, 9999)
                        
                    sessions[client_addr] = session_id
                    used_session_ids.add(session_id)
                    
                    syn_ack = create_syn_ack_packet(session_id, 0)
                    Logger.sent(syn_ack)
                    sock.sendto(syn_ack.pack(), client_addr)
                    Logger.info(f"Connection Complete. Client {client_addr} connected. Session: {session_id}")
                    continue
                
                if command == "DISCONNECT":
                    known_session = sessions.get(client_addr)
                    if known_session == packet.session_id:
                        Logger.info(f"Client {client_addr} disconnected. Session {known_session} closed.")
                        sessions.pop(client_addr, None)
                        used_session_ids.discard(packet.session_id)
                        print(f"Waiting for client connections...")
                    continue

                if command in ["UPLOAD", "DOWNLOAD"]:
                    if packet.session_id not in used_session_ids or sessions.get(client_addr) != packet.session_id:
                        Logger.error(f"XX Transfer request from unauthorized session. Sending ERROR.")
                        err_packet = create_error_packet(packet.session_id, ErrorCode.SESSION_MISMATCH)
                        Logger.sent(err_packet)
                        sock.sendto(err_packet.pack(), client_addr)
                        continue

                    session_id = packet.session_id

                    if command == "UPLOAD":
                        Logger.info(f"Agreed on UPLOAD for '{filename}' ({filesize} bytes).")
                        syn_ack = create_syn_ack_packet(session_id, 0)
                        Logger.sent(syn_ack)
                        sock.sendto(syn_ack.pack(), client_addr)

                        ok = receive_file(sock, filename, session_id, client_addr)
                        if ok: Logger.info("Upload complete.")
                        else: Logger.error("Upload failed.")

                        continue

                    if command == "DOWNLOAD":
                        if not os.path.exists(filename):
                            Logger.error(f"XX File '{filename}' not found. Sending ERROR.")
                            err_packet = create_error_packet(session_id, ErrorCode.FILE_NOT_FOUND)
                            Logger.sent(err_packet)
                            sock.sendto(err_packet.pack(), client_addr)

                            continue

                        server_filesize = os.path.getsize(filename)
                        Logger.info(f"Agreed on DOWNLOAD for '{filename}' ({server_filesize} bytes).")
                        
                        syn_ack = create_syn_ack_packet(session_id, 0, str(server_filesize).encode("utf-8"))
                        Logger.sent(syn_ack)
                        sock.sendto(syn_ack.pack(), client_addr)

                        ok = send_file(sock, filename, session_id, client_addr)
                        if ok: Logger.info("Download complete.")
                        else: Logger.error("Download failed.")

                        continue

            known_session = sessions.get(client_addr)
            if known_session is None or packet.session_id != known_session:
                Logger.error(f"XX Session mismatch from {client_addr}. Sending ERROR.")
                err_packet = create_error_packet(packet.session_id, ErrorCode.SESSION_MISMATCH)
                Logger.sent(err_packet)
                sock.sendto(err_packet.pack(), client_addr)
                continue

            Logger.warn(f"!! Unexpected packet from {client_addr}: {packet}")

        except KeyboardInterrupt:
            Logger.info("\n-> Server shutting down (Ctrl+C detected). Goodbye!")
            break
            
        except Exception as e:
            Logger.error(f"!! Server Error: {e}")

if __name__ == "__main__":
    main()