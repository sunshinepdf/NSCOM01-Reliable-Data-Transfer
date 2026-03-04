# NSCOM01 – Reliable Data Transfer over UDP

**Machine Project 1 | NSCOM01**
*Khyle Villorente and Raina Helaga*

A Python implementation of a custom reliable file-transfer protocol built on top of UDP. The protocol provides in-order delivery, error detection via CRC-32 checksums, session management, and optional simulation of adverse network conditions (packet loss, corruption, session mismatch) for testing purposes.

---

## Project Structure

| File | Description |
|------|-------------|
| `client.py` | Client-side logic – connects to the server, sends commands, and drives file uploads/downloads through an interactive menu. |
| `server.py` | Server-side logic – listens for incoming connections, handles handshake, and serves upload/download requests. |
| `engine.py` | Core reliable-transfer engine – `send_file` and `receive_file` with stop-and-wait ARQ, retransmissions, and FIN/FIN-ACK teardown. |
| `protocol.py` | Packet definition – header layout, packing/unpacking, CRC-32 checksum, packet-type enumerations, factory helpers, and a coloured logger. |
| `config.py` | Shared configuration – IP, port, chunk size, timeout, retry limits, and simulation flags. |

---

## Protocol Overview

### Packet Types

| Code | Type | Purpose |
|------|------|---------|
| 1 | `SYN` | Initiate connection or file-transfer command |
| 2 | `SYN-ACK` | Acknowledge connection / confirm transfer parameters |
| 3 | `DATA` | Carry a file chunk |
| 4 | `ACK` | Acknowledge a received DATA packet |
| 5 | `FIN` | Signal end of file |
| 6 | `FIN-ACK` | Acknowledge end of file |
| 7 | `ERROR` | Report an error (see error codes below) |

### Error Codes

| Code | Meaning |
|------|---------|
| 1 | `FILE_NOT_FOUND` |
| 2 | `SESSION_MISMATCH` |
| 3 | `CHECKSUM_FAILURE` |
| 4 | `UNKNOWN_PACKET_TYPE` |
| 5 | `CONNECTION_TIMEOUT` |

### Packet Header Format (11 bytes)

```
 ┌──────────┬────────────┬─────────────────┬────────────────┬──────────┐
 │  Type    │ Session ID │  Sequence Num   │ Payload Length │ Checksum │
 │  1 byte  │  2 bytes   │    4 bytes      │   2 bytes      │  2 bytes │
 └──────────┴────────────┴─────────────────┴────────────────┴──────────┘
```

Checksum is a CRC-32 digest of the full packet (header + payload) truncated to 16 bits.

---

## Configuration (`config.py`)

| Setting | Default | Description |
|---------|---------|-------------|
| `SERVER_IP` | `127.0.0.1` | Server bind address |
| `SERVER_PORT` | `5000` | Server UDP port |
| `CHUNK_SIZE` | `1024` | Bytes per DATA packet |
| `TIMEOUT` | `2.0` s | Socket receive timeout |
| `MAX_RETRIES` | `5` | Max retransmission attempts |
| `SIMULATE_LOSS` | `False` | Randomly drop outgoing packets |
| `SIMULATE_CORRUPTION` | `False` | Randomly corrupt the checksum field |
| `SIMULATE_MISMATCH` | `False` | Spoof the session ID to trigger mismatch errors |
| `FAILURE_RATE` | `0.3` | Probability of triggering the active simulation (30 %) |

---

## Getting Started

### Prerequisites

- Python 3.8 or newer (no third-party libraries required)

### Run the Server

```bash
python server.py
```

The server binds to `SERVER_IP:SERVER_PORT` as defined in `config.py` and waits for connections.

**Server runtime controls** (type while the server is running):

| Command | Effect |
|---------|--------|
| `loss` | Toggle packet-loss simulation |
| `corrupt` | Toggle checksum-corruption simulation |
| `mismatch` | Toggle session-mismatch simulation |
| `status` | Print current simulation flags |
| `help` | Show available commands |

### Run the Client

```bash
python client.py
```

Connect to a specific server:

```bash
python client.py -s <server_ip> -p <port>
```

After connecting, the interactive menu is shown:

```
=========================
      CLIENT MENU
=========================
1. Download File
2. Upload File
3. Exit
4. [DEMO] Toggle Packet Loss
5. [DEMO] Toggle Corruption
6. [DEMO] Toggle Session Mismatch
```

---

## Transfer Flow

### Upload (client → server)

1. Client sends `SYN` with payload `UPLOAD|<filename>|<filesize>`.
2. Server validates the session and replies with `SYN-ACK`.
3. Client sends file in `CHUNK_SIZE`-byte `DATA` packets; server replies with `ACK` for each.
4. Client sends `FIN`; server replies with `FIN-ACK` to complete the transfer.

### Download (server → client)

1. Client sends `SYN` with payload `DOWNLOAD|<filename>|0`.
2. Server checks that the file exists and replies with `SYN-ACK` carrying the file size.
3. Server sends file in `DATA` packets; client replies with `ACK` for each.
4. Server sends `FIN`; client replies with `FIN-ACK`.
5. Client saves the file as `downloaded_<filename>`.

---

## Demo / Testing

Toggle any simulation flag from either the client menu (options 4–6) or the server console. The `FAILURE_RATE` in `config.py` controls how often faults are injected.

- **Packet Loss** – demonstrates retransmission and timeout recovery.
- **Checksum Corruption** – demonstrates error detection and re-request logic.
- **Session Mismatch** – demonstrates session-validation and error-packet handling.
