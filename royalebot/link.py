"""The PC end of the game link's socket.

``adb forward`` brings the link's port to this PC. Each message is a 4-byte little-endian
length and a msgpack map with a "kind": "hello" (once), "frame" (a RoyaleViser Frame under
"frame") or "event". This side sends "play" messages the same way; each one gets a
"play_result" event back.
"""

from __future__ import annotations

import socket
import struct
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import msgspec

from .policy import REFUSED_PACKAGES, Refused

LINK_PORT = 27125
MAX_MESSAGE = 8 << 20


@dataclass
class Message:
    kind: str
    body: dict[str, Any]


class GameLink:
    def __init__(self, host: str = "127.0.0.1", port: int = LINK_PORT, timeout: float = 10.0):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.settimeout(timeout)
        self._decoder = msgspec.msgpack.Decoder()
        self.hello: dict[str, Any] = {}

    def close(self) -> None:
        self.sock.close()

    def _recv_exact(self, n: int) -> bytes:
        chunks = bytearray()
        while len(chunks) < n:
            chunk = self.sock.recv(n - len(chunks))
            if not chunk:
                raise ConnectionError("the game link closed the connection")
            chunks += chunk
        return bytes(chunks)

    def read_raw(self) -> bytes:
        (size,) = struct.unpack("<I", self._recv_exact(4))
        if size > MAX_MESSAGE:
            raise ConnectionError(f"message of {size} bytes is too large")
        return self._recv_exact(size)

    def read(self) -> Message:
        body = self._decoder.decode(self.read_raw())
        if not isinstance(body, dict) or "kind" not in body:
            raise ConnectionError("malformed message from the game link")
        return Message(body["kind"], body)

    def handshake(self) -> dict[str, Any]:
        """Read and check the hello. Refuses the official game by package name."""
        msg = self.read()
        if msg.kind != "hello":
            raise ConnectionError(f"expected hello, got {msg.kind}")
        hello = msg.body
        if hello.get("package") in REFUSED_PACKAGES:
            raise Refused("The game link reports the official game. RoyaleBot does not work with it.")
        self.hello = hello
        return hello

    @property
    def can_play(self) -> bool:
        """True when the game link accepts plays."""
        return bool(self.hello.get("can_play")) and self.hello.get("protocol") == "royalebot/1"

    def send(self, body: dict[str, Any]) -> None:
        data = msgspec.msgpack.encode(body)
        self.sock.sendall(struct.pack("<I", len(data)) + data)

    def send_play(self, play_id: int, hand_slot: int, x: int, y: int, tick: int) -> None:
        """Ask the game link to play the card in ``hand_slot`` at (x, y), wire units (1000 per
        tile). ``tick`` is the frame the decision was made on; stale plays are refused."""
        self.send({"kind": "play", "id": int(play_id), "slot": int(hand_slot), "x": int(x), "y": int(y),
                   "tick": int(tick)})

    def messages(self) -> Iterator[Message]:
        while True:
            yield self.read()


def frame_bytes(message: Message) -> bytes:
    """The Frame inside a "frame" message, re-encoded for royaleviser.model.decode_frame."""
    return msgspec.msgpack.encode(message.body["frame"])
