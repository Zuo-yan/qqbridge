#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import socket
import struct
import sys
from pathlib import Path


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] == "'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def recv_exact(sock: socket.socket, length: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < length:
        chunk = sock.recv(length - len(chunks))
        if not chunk:
            raise RuntimeError("OneBot WebSocket closed unexpectedly")
        chunks.extend(chunk)
    return bytes(chunks)


def send_frame(sock: socket.socket, payload: bytes, opcode: int = 1) -> None:
    mask = os.urandom(4)
    length = len(payload)
    header = bytearray([0x80 | opcode])
    if length < 126:
        header.append(0x80 | length)
    elif length < 65536:
        header.append(0x80 | 126)
        header.extend(struct.pack("!H", length))
    else:
        header.append(0x80 | 127)
        header.extend(struct.pack("!Q", length))
    header.extend(mask)
    masked = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
    sock.sendall(bytes(header) + masked)


def receive_frame(sock: socket.socket) -> tuple[int, bytes]:
    first, second = recv_exact(sock, 2)
    opcode = first & 0x0F
    masked = bool(second & 0x80)
    length = second & 0x7F
    if length == 126:
        length = struct.unpack("!H", recv_exact(sock, 2))[0]
    elif length == 127:
        length = struct.unpack("!Q", recv_exact(sock, 8))[0]
    mask = recv_exact(sock, 4) if masked else b""
    payload = recv_exact(sock, length)
    if masked:
        payload = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
    return opcode, payload


def call(host: str, port: int, token: str, action: str, params: dict) -> object:
    sock = socket.create_connection((host, port), timeout=15)
    sock.settimeout(20)
    key = base64.b64encode(os.urandom(16)).decode()
    request = (
        f"GET / HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        f"Authorization: Bearer {token}\r\n"
        "\r\n"
    )
    sock.sendall(request.encode())
    response = bytearray()
    while b"\r\n\r\n" not in response:
        chunk = sock.recv(4096)
        if not chunk:
            raise RuntimeError("OneBot WebSocket handshake failed")
        response.extend(chunk)
        if len(response) > 65536:
            raise RuntimeError("OneBot WebSocket handshake response is too large")
    status = bytes(response).split(b"\r\n", 1)[0]
    if b" 101 " not in status:
        raise RuntimeError(f"OneBot WebSocket rejected the connection: {status.decode(errors='replace')}")

    echo = hashlib.sha256(os.urandom(32)).hexdigest()[:20]
    send_frame(sock, json.dumps({"action": action, "params": params, "echo": echo}).encode())
    fragments = bytearray()
    while True:
        opcode, payload = receive_frame(sock)
        if opcode == 0x9:
            send_frame(sock, payload, opcode=0xA)
            continue
        if opcode == 0x8:
            raise RuntimeError("OneBot WebSocket closed before returning a response")
        if opcode in (0x1, 0x2, 0x0):
            fragments.extend(payload)
            if opcode in (0x1, 0x2) or payload:
                try:
                    message = json.loads(fragments.decode())
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
                fragments.clear()
                if message.get("echo") != echo:
                    continue
                if message.get("status") != "ok" or message.get("retcode", 0) != 0:
                    raise RuntimeError(
                        f"OneBot action failed: retcode={message.get('retcode')} "
                        f"message={message.get('message') or message.get('wording')}"
                    )
                return message.get("data")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--instance", required=True)
    parser.add_argument("--action", default="get_group_list")
    args = parser.parse_args()
    env = load_env(Path(args.instance) / ".env")
    token = env.get("ONEBOT_TOKEN", "")
    if not token:
        raise SystemExit("ONEBOT_TOKEN is not configured")
    data = call("127.0.0.1", int(env.get("ONEBOT_PORT", "3001")), token, args.action, {})
    print(json.dumps(data, ensure_ascii=False))


if __name__ == "__main__":
    main()
