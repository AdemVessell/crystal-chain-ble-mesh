from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Any

DEFAULT_BLE_PAYLOAD_BYTES = 244
LEGACY_BLE_PAYLOAD_BYTES = 182
BITCHAT_GCS_BUDGET_BYTES = 400

BEACON_MAGIC = b"CB00"
BEACON_SCHEMA = 0
WITNESS_REQUEST_MAGIC = b"WR00"


def ble_packet_count(byte_count: int, *, payload_bytes: int = DEFAULT_BLE_PAYLOAD_BYTES) -> int:
    if byte_count < 0:
        raise ValueError("byte_count must be non-negative")
    if payload_bytes < 1:
        raise ValueError("payload_bytes must be positive")
    if byte_count == 0:
        return 0
    return (byte_count + payload_bytes - 1) // payload_bytes


def fragment_frame(frame: bytes, *, payload_bytes: int = DEFAULT_BLE_PAYLOAD_BYTES) -> list[bytes]:
    if not frame:
        return []
    chunks: list[bytes] = []
    total = ble_packet_count(len(frame), payload_bytes=payload_bytes)
    offset = 0
    index = 0
    while offset < len(frame):
        chunk = frame[offset : offset + payload_bytes]
        header = struct.pack(">BBH", index, total, len(chunk))
        chunks.append(header + chunk)
        offset += payload_bytes
        index += 1
    return chunks


@dataclass(frozen=True)
class BLETransmission:
    label: str
    wire_bytes: int
    ble_packets: int
    payload_bytes: int
    fragmented: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "ble_packets": self.ble_packets,
            "fragmented": self.fragmented,
            "label": self.label,
            "payload_bytes": self.payload_bytes,
            "wire_bytes": self.wire_bytes,
        }


def transmit_frame(
    label: str,
    frame: bytes,
    *,
    payload_bytes: int = DEFAULT_BLE_PAYLOAD_BYTES,
) -> BLETransmission:
    packets = ble_packet_count(len(frame), payload_bytes=payload_bytes)
    return BLETransmission(
        ble_packets=packets,
        fragmented=packets > 1,
        label=label,
        payload_bytes=payload_bytes,
        wire_bytes=len(frame),
    )


def encode_compact_beacon(
    *,
    block_count: int,
    chain_crystal: bytes,
    state_crystal: bytes,
    blake3_head: bytes,
    peer_id: bytes,
) -> bytes:
    if len(chain_crystal) != 8 or len(state_crystal) != 8:
        raise ValueError("Crystal roots must be 8 bytes")
    if len(blake3_head) != 32:
        raise ValueError("BLAKE3 head must be 32 bytes")
    if len(peer_id) != 8:
        raise ValueError("peer_id must be 8 bytes")
    if not 0 <= block_count <= 0xFFFFFFFF:
        raise ValueError("block_count must fit uint32")
    return (
        BEACON_MAGIC
        + struct.pack(">B", BEACON_SCHEMA)
        + struct.pack(">I", block_count)
        + chain_crystal
        + state_crystal
        + blake3_head
        + peer_id
    )


def decode_compact_beacon(frame: bytes) -> dict[str, Any]:
    if len(frame) != 65:
        raise ValueError("compact beacon must be exactly 65 bytes")
    magic = frame[:4]
    if magic != BEACON_MAGIC:
        raise ValueError("unknown beacon magic")
    schema = frame[4]
    block_count = struct.unpack(">I", frame[5:9])[0]
    return {
        "blake3_head": frame[25:57].hex(),
        "block_count": block_count,
        "chain_crystal": frame[9:17].hex(),
        "peer_id": frame[57:65].hex(),
        "schema": schema,
        "state_crystal": frame[17:25].hex(),
    }


def encode_witness_request(*, mismatch_height: int, request_nonce: int) -> bytes:
    if not 0 <= mismatch_height <= 0xFFFFFFFF:
        raise ValueError("mismatch_height must fit uint32")
    if not 0 <= request_nonce <= 0xFFFFFFFF:
        raise ValueError("request_nonce must fit uint32")
    return WITNESS_REQUEST_MAGIC + struct.pack(">II", mismatch_height, request_nonce)


def decode_witness_request(frame: bytes) -> dict[str, Any]:
    if len(frame) != 12:
        raise ValueError("witness request must be exactly 12 bytes")
    if frame[:4] != WITNESS_REQUEST_MAGIC:
        raise ValueError("unknown witness request magic")
    mismatch_height, request_nonce = struct.unpack(">II", frame[4:12])
    return {
        "mismatch_height": mismatch_height,
        "request_nonce": request_nonce,
    }
