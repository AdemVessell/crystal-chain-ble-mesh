from __future__ import annotations

import struct
from typing import Any

from .ledger import (
    GENESIS_PARENT,
    Block,
    LedgerError,
    TokenClass,
    Transaction,
    TxType,
    WalletRole,
    blake3_hex,
    canonical_json,
)

COMPACT_BLOCK_MAGIC = b"BK00"
COMPACT_BLOCK_SCHEMA = 0
COMPACT_BLOCK_SEQUENCE_MAGIC = b"BR00"
COMPACT_BLOCK_WITNESS_MAGIC = b"BW00"
COMPACT_DIVERGENCE_WITNESS_MAGIC = b"DW00"

TX_TYPE_IDS: dict[TxType, int] = {
    "create_wallet": 0,
    "mint": 1,
    "transfer": 2,
}
TX_TYPES_BY_ID = {value: key for key, value in TX_TYPE_IDS.items()}

WALLET_ROLE_IDS: dict[WalletRole, int] = {
    "user": 0,
    "founder": 1,
    "builder": 2,
    "gateway": 3,
    "watcher": 4,
}
WALLET_ROLES_BY_ID = {value: key for key, value in WALLET_ROLE_IDS.items()}

TOKEN_CLASS_IDS: dict[TokenClass, int] = {
    "mesh_credit": 0,
    "founder_marker": 1,
    "builder_marker": 2,
    "receipt": 3,
}
TOKEN_CLASSES_BY_ID = {value: key for key, value in TOKEN_CLASS_IDS.items()}


def _pack_u8(value: int) -> bytes:
    if not 0 <= value <= 0xFF:
        raise LedgerError("value must fit uint8")
    return struct.pack(">B", value)


def _pack_u16(value: int) -> bytes:
    if not 0 <= value <= 0xFFFF:
        raise LedgerError("value must fit uint16")
    return struct.pack(">H", value)


def _pack_u32(value: int) -> bytes:
    if not 0 <= value <= 0xFFFFFFFF:
        raise LedgerError("value must fit uint32")
    return struct.pack(">I", value)


def _read_exact(frame: bytes, offset: int, size: int) -> tuple[bytes, int]:
    end = offset + size
    if end > len(frame):
        raise LedgerError("compact frame truncated")
    return frame[offset:end], end


def _read_u8(frame: bytes, offset: int) -> tuple[int, int]:
    raw, offset = _read_exact(frame, offset, 1)
    return raw[0], offset


def _read_u16(frame: bytes, offset: int) -> tuple[int, int]:
    raw, offset = _read_exact(frame, offset, 2)
    return struct.unpack(">H", raw)[0], offset


def _read_u32(frame: bytes, offset: int) -> tuple[int, int]:
    raw, offset = _read_exact(frame, offset, 4)
    return struct.unpack(">I", raw)[0], offset


def _pack_varstr(value: str) -> bytes:
    raw = value.encode("utf-8")
    return _pack_u16(len(raw)) + raw


def _read_varstr(frame: bytes, offset: int) -> tuple[str, int]:
    size, offset = _read_u16(frame, offset)
    raw, offset = _read_exact(frame, offset, size)
    return raw.decode("utf-8"), offset


def _hash_to_bytes(value: str) -> bytes:
    if value == GENESIS_PARENT:
        return b"\x00" * 32
    raw = bytes.fromhex(value)
    if len(raw) != 32:
        raise LedgerError("hash must be 32 bytes")
    return raw


def _bytes_to_hash(value: bytes, *, height: int | None = None) -> str:
    if len(value) != 32:
        raise LedgerError("hash bytes must be 32 bytes")
    if height == 0 and value == b"\x00" * 32:
        return GENESIS_PARENT
    return value.hex()


def _tx_id_for(
    tx_type: TxType,
    sender_public_key: str,
    nonce: int,
    pre_state_hash: str,
    body: dict[str, Any],
    signature: str,
) -> str:
    payload = Transaction.signing_dict(
        body=body,
        nonce=nonce,
        pre_state_hash=pre_state_hash,
        sender_public_key=sender_public_key,
        tx_type=tx_type,
    )
    return blake3_hex(canonical_json({"payload": payload, "sig": signature}))


def encode_compact_transaction(tx: Transaction) -> bytes:
    if tx.tx_type not in TX_TYPE_IDS:
        raise LedgerError(f"unsupported transaction type: {tx.tx_type}")
    frame = bytearray()
    frame.extend(_pack_u8(TX_TYPE_IDS[tx.tx_type]))
    frame.extend(bytes.fromhex(tx.sender_public_key))
    frame.extend(_pack_u32(tx.nonce))
    frame.extend(bytes.fromhex(tx.signature))

    if tx.tx_type == "create_wallet":
        wallet_role = tx.body.get("wallet_role", "user")
        if wallet_role not in WALLET_ROLE_IDS:
            raise LedgerError("unsupported wallet role")
        frame.extend(_pack_varstr(str(tx.body["wallet_id"])))
        frame.extend(_pack_u8(WALLET_ROLE_IDS[wallet_role]))
    elif tx.tx_type == "mint":
        token_class = tx.body.get("token_class", "mesh_credit")
        if token_class not in TOKEN_CLASS_IDS:
            raise LedgerError("unsupported token class")
        frame.extend(_pack_varstr(str(tx.body["wallet_id"])))
        frame.extend(_pack_varstr(str(tx.body["token_id"])))
        frame.extend(_pack_u8(TOKEN_CLASS_IDS[token_class]))
    elif tx.tx_type == "transfer":
        frame.extend(_pack_varstr(str(tx.body["from_wallet"])))
        frame.extend(_pack_varstr(str(tx.body["to_wallet"])))
        frame.extend(_pack_varstr(str(tx.body["token_id"])))
    else:
        raise LedgerError("unsupported transaction type")
    return bytes(frame)


def decode_compact_transaction(
    frame: bytes,
    offset: int,
    *,
    pre_state_hash: str,
) -> tuple[Transaction, int]:
    tx_type_id, offset = _read_u8(frame, offset)
    tx_type = TX_TYPES_BY_ID.get(tx_type_id)
    if tx_type is None:
        raise LedgerError("unsupported compact transaction type")
    sender_raw, offset = _read_exact(frame, offset, 32)
    nonce, offset = _read_u32(frame, offset)
    signature_raw, offset = _read_exact(frame, offset, 64)
    sender_public_key = sender_raw.hex()
    signature = signature_raw.hex()

    if tx_type == "create_wallet":
        wallet_id, offset = _read_varstr(frame, offset)
        role_id, offset = _read_u8(frame, offset)
        wallet_role = WALLET_ROLES_BY_ID.get(role_id)
        if wallet_role is None:
            raise LedgerError("unsupported compact wallet role")
        body = {
            "owner_public_key": sender_public_key,
            "wallet_id": wallet_id,
            "wallet_role": wallet_role,
        }
    elif tx_type == "mint":
        wallet_id, offset = _read_varstr(frame, offset)
        token_id, offset = _read_varstr(frame, offset)
        class_id, offset = _read_u8(frame, offset)
        token_class = TOKEN_CLASSES_BY_ID.get(class_id)
        if token_class is None:
            raise LedgerError("unsupported compact token class")
        body = {
            "token_class": token_class,
            "token_id": token_id,
            "wallet_id": wallet_id,
        }
    elif tx_type == "transfer":
        from_wallet, offset = _read_varstr(frame, offset)
        to_wallet, offset = _read_varstr(frame, offset)
        token_id, offset = _read_varstr(frame, offset)
        body = {
            "from_wallet": from_wallet,
            "to_wallet": to_wallet,
            "token_id": token_id,
        }
    else:
        raise LedgerError("unsupported compact transaction type")

    return (
        Transaction(
            body=body,
            nonce=nonce,
            pre_state_hash=pre_state_hash,
            sender_public_key=sender_public_key,
            signature=signature,
            tx_id=_tx_id_for(tx_type, sender_public_key, nonce, pre_state_hash, body, signature),
            tx_type=tx_type,
        ),
        offset,
    )


def encode_compact_block(block: Block) -> bytes:
    frame = bytearray()
    frame.extend(COMPACT_BLOCK_MAGIC)
    frame.extend(_pack_u8(COMPACT_BLOCK_SCHEMA))
    frame.extend(_pack_u32(block.height))
    frame.extend(_hash_to_bytes(block.parent_hash))
    frame.extend(bytes.fromhex(block.pre_state_hash))
    frame.extend(bytes.fromhex(block.post_state_hash))
    frame.extend(bytes.fromhex(block.post_state_crystal))
    frame.extend(bytes.fromhex(block.producer_public_key))
    frame.extend(bytes.fromhex(block.producer_signature))
    frame.extend(_pack_u8(len(block.transactions)))
    for tx in block.transactions:
        frame.extend(encode_compact_transaction(tx))
    return bytes(frame)


def decode_compact_block(frame: bytes) -> Block:
    offset = 0
    magic, offset = _read_exact(frame, offset, 4)
    if magic != COMPACT_BLOCK_MAGIC:
        raise LedgerError("unknown compact block magic")
    schema, offset = _read_u8(frame, offset)
    if schema != COMPACT_BLOCK_SCHEMA:
        raise LedgerError("unsupported compact block schema")
    height, offset = _read_u32(frame, offset)
    parent_raw, offset = _read_exact(frame, offset, 32)
    pre_state_raw, offset = _read_exact(frame, offset, 32)
    post_state_raw, offset = _read_exact(frame, offset, 32)
    post_crystal_raw, offset = _read_exact(frame, offset, 8)
    producer_raw, offset = _read_exact(frame, offset, 32)
    producer_signature_raw, offset = _read_exact(frame, offset, 64)
    tx_count, offset = _read_u8(frame, offset)
    pre_state_hash = pre_state_raw.hex()
    transactions: list[Transaction] = []
    for _index in range(tx_count):
        tx, offset = decode_compact_transaction(frame, offset, pre_state_hash=pre_state_hash)
        transactions.append(tx)
    if offset != len(frame):
        raise LedgerError("compact block has trailing bytes")
    producer_signature = producer_signature_raw.hex()
    body = Block.signing_dict(
        height=height,
        parent_hash=_bytes_to_hash(parent_raw, height=height),
        post_state_crystal=post_crystal_raw.hex(),
        post_state_hash=post_state_raw.hex(),
        pre_state_hash=pre_state_hash,
        producer_public_key=producer_raw.hex(),
        transactions=tuple(transactions),
    )
    return Block(
        block_hash=blake3_hex(canonical_json({"body": body, "sig": producer_signature})),
        height=height,
        parent_hash=_bytes_to_hash(parent_raw, height=height),
        post_state_crystal=post_crystal_raw.hex(),
        post_state_hash=post_state_raw.hex(),
        pre_state_hash=pre_state_hash,
        producer_public_key=producer_raw.hex(),
        producer_signature=producer_signature,
        transactions=tuple(transactions),
    )


def encode_compact_block_sequence(blocks: list[Block]) -> bytes:
    frame = bytearray()
    frame.extend(COMPACT_BLOCK_SEQUENCE_MAGIC)
    frame.extend(_pack_u8(COMPACT_BLOCK_SCHEMA))
    frame.extend(_pack_u16(len(blocks)))
    for block in blocks:
        compact = encode_compact_block(block)
        frame.extend(_pack_u16(len(compact)))
        frame.extend(compact)
    return bytes(frame)


def decode_compact_block_sequence(frame: bytes) -> list[Block]:
    offset = 0
    magic, offset = _read_exact(frame, offset, 4)
    if magic != COMPACT_BLOCK_SEQUENCE_MAGIC:
        raise LedgerError("unknown compact block sequence magic")
    schema, offset = _read_u8(frame, offset)
    if schema != COMPACT_BLOCK_SCHEMA:
        raise LedgerError("unsupported compact block sequence schema")
    count, offset = _read_u16(frame, offset)
    blocks: list[Block] = []
    for _index in range(count):
        size, offset = _read_u16(frame, offset)
        payload, offset = _read_exact(frame, offset, size)
        blocks.append(decode_compact_block(payload))
    if offset != len(frame):
        raise LedgerError("compact block sequence has trailing bytes")
    return blocks


def encode_compact_block_witness(block: Block) -> bytes:
    compact = encode_compact_block(block)
    return (
        COMPACT_BLOCK_WITNESS_MAGIC
        + _pack_u8(COMPACT_BLOCK_SCHEMA)
        + _pack_u16(len(compact))
        + compact
    )


def decode_compact_block_witness(frame: bytes) -> Block:
    offset = 0
    magic, offset = _read_exact(frame, offset, 4)
    if magic != COMPACT_BLOCK_WITNESS_MAGIC:
        raise LedgerError("unknown compact block witness magic")
    schema, offset = _read_u8(frame, offset)
    if schema != COMPACT_BLOCK_SCHEMA:
        raise LedgerError("unsupported compact block witness schema")
    size, offset = _read_u16(frame, offset)
    payload, offset = _read_exact(frame, offset, size)
    if offset != len(frame):
        raise LedgerError("compact block witness has trailing bytes")
    return decode_compact_block(payload)


def encode_compact_divergence_witness(local: Block, remote: Block) -> bytes:
    local_compact = encode_compact_block(local)
    remote_compact = encode_compact_block(remote)
    same_parent = int(local.parent_hash == remote.parent_hash)
    return (
        COMPACT_DIVERGENCE_WITNESS_MAGIC
        + _pack_u8(COMPACT_BLOCK_SCHEMA)
        + _pack_u32(local.height)
        + _pack_u8(same_parent)
        + _pack_u16(len(local_compact))
        + local_compact
        + _pack_u16(len(remote_compact))
        + remote_compact
    )


def decode_compact_divergence_witness(frame: bytes) -> tuple[Block, Block, bool]:
    offset = 0
    magic, offset = _read_exact(frame, offset, 4)
    if magic != COMPACT_DIVERGENCE_WITNESS_MAGIC:
        raise LedgerError("unknown compact divergence witness magic")
    schema, offset = _read_u8(frame, offset)
    if schema != COMPACT_BLOCK_SCHEMA:
        raise LedgerError("unsupported compact divergence witness schema")
    height, offset = _read_u32(frame, offset)
    same_parent_raw, offset = _read_u8(frame, offset)
    local_size, offset = _read_u16(frame, offset)
    local_payload, offset = _read_exact(frame, offset, local_size)
    remote_size, offset = _read_u16(frame, offset)
    remote_payload, offset = _read_exact(frame, offset, remote_size)
    if offset != len(frame):
        raise LedgerError("compact divergence witness has trailing bytes")
    local = decode_compact_block(local_payload)
    remote = decode_compact_block(remote_payload)
    if local.height != height or remote.height != height:
        raise LedgerError("compact divergence witness height mismatch")
    return local, remote, bool(same_parent_raw)
