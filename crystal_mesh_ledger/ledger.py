from __future__ import annotations

import json
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Literal

import blake3
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

GENESIS_PARENT = "GENESIS"
SyncStatus = Literal["already_in_sync", "applied_blocks", "remote_behind", "conflict"]
TxType = Literal["create_wallet", "mint", "transfer"]
WalletRole = Literal["user", "founder", "builder", "gateway", "watcher"]
TokenClass = Literal["mesh_credit", "founder_marker", "builder_marker", "receipt"]
CrystalRegion = Literal["none", "left", "right", "both", "shape_mismatch"]
VALID_WALLET_ROLES: set[str] = {"user", "founder", "builder", "gateway", "watcher"}
VALID_TOKEN_CLASSES: set[str] = {
    "mesh_credit",
    "founder_marker",
    "builder_marker",
    "receipt",
}


class LedgerError(ValueError):
    """Raised when a reference-ledger operation is invalid."""


def canonical_json(data: Any) -> bytes:
    return json.dumps(
        data,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def blake3_hex(data: bytes) -> str:
    return blake3.blake3(data).hexdigest()


def _fold_byte(left: int, right: int, head: int) -> int:
    return blake3.blake3(
        b"crystal-mesh-ledger-fold-v0" + bytes([head, left, right])
    ).digest()[0]


def _leaf_root(payload: bytes) -> tuple[int, ...]:
    digest = blake3.blake3(payload).digest()
    return tuple(digest[index] for index in range(8))


CrystalRootFn = Callable[[list[bytes]], tuple[int, ...]]


def _balanced_crystal_root(leaves: list[bytes]) -> tuple[int, ...]:
    if not leaves:
        return (0, 0, 0, 0, 0, 0, 0, 0)
    roots = [_leaf_root(leaf) for leaf in leaves]
    while len(roots) > 1:
        next_roots: list[tuple[int, ...]] = []
        for index in range(0, len(roots), 2):
            left = roots[index]
            if index + 1 >= len(roots):
                next_roots.append(left)
                continue
            right = roots[index + 1]
            next_roots.append(
                tuple(_fold_byte(left[head], right[head], head) for head in range(8))
            )
        roots = next_roots
    return roots[0]


def disabled_crystal_root(leaves: list[bytes]) -> tuple[int, ...]:
    return (0, 0, 0, 0, 0, 0, 0, 0)


@dataclass(frozen=True)
class KeyPair:
    private_key_hex: str
    public_key_hex: str

    @classmethod
    def from_seed(cls, seed: str) -> KeyPair:
        private_key = Ed25519PrivateKey.from_private_bytes(
            blake3.blake3(seed.encode("utf-8")).digest()
        )
        private_bytes = private_key.private_bytes(
            encoding=Encoding.Raw,
            format=PrivateFormat.Raw,
            encryption_algorithm=NoEncryption(),
        )
        public_bytes = private_key.public_key().public_bytes(
            encoding=Encoding.Raw,
            format=PublicFormat.Raw,
        )
        return cls(private_key_hex=private_bytes.hex(), public_key_hex=public_bytes.hex())

    @property
    def private_key(self) -> Ed25519PrivateKey:
        return Ed25519PrivateKey.from_private_bytes(bytes.fromhex(self.private_key_hex))

    def sign(self, payload: bytes) -> str:
        return self.private_key.sign(payload).hex()


def verify_signature(public_key_hex: str, payload: bytes, signature_hex: str) -> bool:
    public_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex))
    try:
        public_key.verify(bytes.fromhex(signature_hex), payload)
    except InvalidSignature:
        return False
    return True


@dataclass(frozen=True)
class Transaction:
    tx_type: TxType
    sender_public_key: str
    nonce: int
    pre_state_hash: str
    body: dict[str, Any]
    signature: str
    tx_id: str

    @staticmethod
    def signing_dict(
        *,
        body: dict[str, Any],
        nonce: int,
        pre_state_hash: str,
        sender_public_key: str,
        tx_type: TxType,
    ) -> dict[str, Any]:
        return {
            "body": deepcopy(body),
            "nonce": nonce,
            "pre_state_hash": pre_state_hash,
            "sender_public_key": sender_public_key,
            "tx_type": tx_type,
        }

    @classmethod
    def signed(
        cls,
        *,
        body: dict[str, Any],
        nonce: int,
        pre_state_hash: str,
        sender: KeyPair,
        tx_type: TxType,
    ) -> Transaction:
        payload = canonical_json(
            cls.signing_dict(
                body=body,
                nonce=nonce,
                pre_state_hash=pre_state_hash,
                sender_public_key=sender.public_key_hex,
                tx_type=tx_type,
            )
        )
        signature = sender.sign(payload)
        tx_id = blake3_hex(canonical_json({"payload": json.loads(payload), "sig": signature}))
        return cls(
            body=deepcopy(body),
            nonce=nonce,
            pre_state_hash=pre_state_hash,
            sender_public_key=sender.public_key_hex,
            signature=signature,
            tx_id=tx_id,
            tx_type=tx_type,
        )

    def payload(self) -> bytes:
        return canonical_json(
            self.signing_dict(
                body=self.body,
                nonce=self.nonce,
                pre_state_hash=self.pre_state_hash,
                sender_public_key=self.sender_public_key,
                tx_type=self.tx_type,
            )
        )

    def verify(self) -> None:
        if self.nonce < 1:
            raise LedgerError("transaction nonce must be positive")
        if not verify_signature(self.sender_public_key, self.payload(), self.signature):
            raise LedgerError("transaction signature invalid")
        expected = blake3_hex(
            canonical_json({"payload": json.loads(self.payload()), "sig": self.signature})
        )
        if self.tx_id != expected:
            raise LedgerError("transaction id mismatch")

    def to_dict(self) -> dict[str, Any]:
        return {
            "body": deepcopy(self.body),
            "nonce": self.nonce,
            "pre_state_hash": self.pre_state_hash,
            "sender_public_key": self.sender_public_key,
            "signature": self.signature,
            "tx_id": self.tx_id,
            "tx_type": self.tx_type,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Transaction:
        tx_type = str(data["tx_type"])
        if tx_type not in {"create_wallet", "mint", "transfer"}:
            raise LedgerError(f"unsupported transaction type: {tx_type}")
        return cls(
            body=deepcopy(data["body"]),
            nonce=int(data["nonce"]),
            pre_state_hash=str(data["pre_state_hash"]),
            sender_public_key=str(data["sender_public_key"]),
            signature=str(data["signature"]),
            tx_id=str(data["tx_id"]),
            tx_type=tx_type,  # type: ignore[arg-type]
        )


@dataclass
class WorldState:
    wallets: dict[str, str] = field(default_factory=dict)
    wallet_roles: dict[str, str] = field(default_factory=dict)
    tokens: dict[str, str] = field(default_factory=dict)
    token_classes: dict[str, str] = field(default_factory=dict)
    nonces: dict[str, int] = field(default_factory=dict)

    def clone(self) -> WorldState:
        return WorldState.from_dict(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "nonces": dict(sorted(self.nonces.items())),
            "token_classes": dict(sorted(self.token_classes.items())),
            "tokens": dict(sorted(self.tokens.items())),
            "wallet_roles": dict(sorted(self.wallet_roles.items())),
            "wallets": dict(sorted(self.wallets.items())),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorldState:
        wallets = {str(key): str(value) for key, value in data.get("wallets", {}).items()}
        tokens = {str(key): str(value) for key, value in data.get("tokens", {}).items()}
        wallet_roles = {
            str(key): str(value) for key, value in data.get("wallet_roles", {}).items()
        }
        token_classes = {
            str(key): str(value) for key, value in data.get("token_classes", {}).items()
        }
        for wallet_id in wallets:
            wallet_roles.setdefault(wallet_id, "user")
        for token_id in tokens:
            token_classes.setdefault(token_id, "mesh_credit")
        unknown_roles = set(wallet_roles.values()) - VALID_WALLET_ROLES
        if unknown_roles:
            raise LedgerError(f"unsupported wallet roles: {sorted(unknown_roles)}")
        unknown_classes = set(token_classes.values()) - VALID_TOKEN_CLASSES
        if unknown_classes:
            raise LedgerError(f"unsupported token classes: {sorted(unknown_classes)}")
        return cls(
            nonces={str(key): int(value) for key, value in data.get("nonces", {}).items()},
            token_classes=token_classes,
            tokens=tokens,
            wallet_roles=wallet_roles,
            wallets=wallets,
        )

    @property
    def state_hash(self) -> str:
        return blake3_hex(canonical_json(self.to_dict()))

    @property
    def crystal_root(self) -> tuple[int, ...]:
        leaves = [
            canonical_json(
                {
                    "kind": "wallet",
                    "owner": owner,
                    "role": self.wallet_roles.get(wallet_id, "user"),
                    "wallet_id": wallet_id,
                }
            )
            for wallet_id, owner in sorted(self.wallets.items())
        ]
        leaves.extend(
            canonical_json(
                {
                    "class": self.token_classes.get(token_id, "mesh_credit"),
                    "kind": "token",
                    "token_id": token_id,
                    "wallet_id": wallet_id,
                }
            )
            for token_id, wallet_id in sorted(self.tokens.items())
        )
        return _balanced_crystal_root(leaves)

    def next_nonce(self, public_key_hex: str) -> int:
        return self.nonces.get(public_key_hex, 0) + 1

    def apply_transaction(self, tx: Transaction, *, check_pre_state: bool = True) -> None:
        tx.verify()
        if check_pre_state and tx.pre_state_hash != self.state_hash:
            raise LedgerError("transaction pre-state mismatch")
        expected_nonce = self.next_nonce(tx.sender_public_key)
        if tx.nonce != expected_nonce:
            raise LedgerError(f"invalid nonce: expected {expected_nonce}, got {tx.nonce}")

        if tx.tx_type == "create_wallet":
            wallet_id = str(tx.body["wallet_id"])
            owner = str(tx.body["owner_public_key"])
            wallet_role = str(tx.body.get("wallet_role", "user"))
            if owner != tx.sender_public_key:
                raise LedgerError("wallet owner must sign wallet creation")
            if wallet_role not in VALID_WALLET_ROLES:
                raise LedgerError("unsupported wallet role")
            if wallet_id in self.wallets:
                raise LedgerError("wallet already exists")
            self.wallets[wallet_id] = owner
            self.wallet_roles[wallet_id] = wallet_role
        elif tx.tx_type == "mint":
            wallet_id = str(tx.body["wallet_id"])
            token_id = str(tx.body["token_id"])
            token_class = str(tx.body.get("token_class", "mesh_credit"))
            if wallet_id not in self.wallets:
                raise LedgerError("mint target wallet missing")
            if self.wallets[wallet_id] != tx.sender_public_key:
                raise LedgerError("mint signer must own target wallet")
            if token_class not in VALID_TOKEN_CLASSES:
                raise LedgerError("unsupported token class")
            if token_id in self.tokens:
                raise LedgerError("token already exists")
            self.tokens[token_id] = wallet_id
            self.token_classes[token_id] = token_class
        elif tx.tx_type == "transfer":
            token_id = str(tx.body["token_id"])
            from_wallet = str(tx.body["from_wallet"])
            to_wallet = str(tx.body["to_wallet"])
            if token_id not in self.tokens:
                raise LedgerError("token missing")
            if from_wallet not in self.wallets or to_wallet not in self.wallets:
                raise LedgerError("transfer wallet missing")
            if self.tokens[token_id] != from_wallet:
                raise LedgerError("token not in claimed source wallet")
            if self.wallets[from_wallet] != tx.sender_public_key:
                raise LedgerError("transfer signer must own source wallet")
            self.tokens[token_id] = to_wallet
        else:
            raise LedgerError("unsupported transaction type")
        self.nonces[tx.sender_public_key] = tx.nonce


@dataclass(frozen=True)
class Block:
    height: int
    parent_hash: str
    pre_state_hash: str
    post_state_hash: str
    post_state_crystal: str
    transactions: tuple[Transaction, ...]
    producer_public_key: str
    producer_signature: str
    block_hash: str

    @staticmethod
    def signing_dict(
        *,
        height: int,
        parent_hash: str,
        post_state_crystal: str,
        post_state_hash: str,
        pre_state_hash: str,
        producer_public_key: str,
        transactions: tuple[Transaction, ...],
    ) -> dict[str, Any]:
        return {
            "height": height,
            "parent_hash": parent_hash,
            "post_state_crystal": post_state_crystal,
            "post_state_hash": post_state_hash,
            "pre_state_hash": pre_state_hash,
            "producer_public_key": producer_public_key,
            "transactions": [tx.to_dict() for tx in transactions],
        }

    @classmethod
    def seal(
        cls,
        *,
        height: int,
        parent_hash: str,
        post_state: WorldState,
        pre_state_hash: str,
        producer: KeyPair,
        transactions: tuple[Transaction, ...],
    ) -> Block:
        body = cls.signing_dict(
            height=height,
            parent_hash=parent_hash,
            post_state_crystal=bytes(post_state.crystal_root).hex(),
            post_state_hash=post_state.state_hash,
            pre_state_hash=pre_state_hash,
            producer_public_key=producer.public_key_hex,
            transactions=transactions,
        )
        signature = producer.sign(canonical_json(body))
        block_hash = blake3_hex(canonical_json({"body": body, "sig": signature}))
        return cls(
            block_hash=block_hash,
            height=height,
            parent_hash=parent_hash,
            post_state_crystal=bytes(post_state.crystal_root).hex(),
            post_state_hash=post_state.state_hash,
            pre_state_hash=pre_state_hash,
            producer_public_key=producer.public_key_hex,
            producer_signature=signature,
            transactions=transactions,
        )

    def body(self) -> dict[str, Any]:
        return self.signing_dict(
            height=self.height,
            parent_hash=self.parent_hash,
            post_state_crystal=self.post_state_crystal,
            post_state_hash=self.post_state_hash,
            pre_state_hash=self.pre_state_hash,
            producer_public_key=self.producer_public_key,
            transactions=self.transactions,
        )

    def verify(self) -> None:
        if not self.transactions:
            raise LedgerError("block must contain at least one transaction")
        if not verify_signature(
            self.producer_public_key,
            canonical_json(self.body()),
            self.producer_signature,
        ):
            raise LedgerError("block producer signature invalid")
        expected = blake3_hex(canonical_json({"body": self.body(), "sig": self.producer_signature}))
        if self.block_hash != expected:
            raise LedgerError("block hash mismatch")

    def to_dict(self) -> dict[str, Any]:
        return {
            "block_hash": self.block_hash,
            "height": self.height,
            "parent_hash": self.parent_hash,
            "post_state_crystal": self.post_state_crystal,
            "post_state_hash": self.post_state_hash,
            "pre_state_hash": self.pre_state_hash,
            "producer_public_key": self.producer_public_key,
            "producer_signature": self.producer_signature,
            "transactions": [tx.to_dict() for tx in self.transactions],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Block:
        return cls(
            block_hash=str(data["block_hash"]),
            height=int(data["height"]),
            parent_hash=str(data["parent_hash"]),
            post_state_crystal=str(data["post_state_crystal"]),
            post_state_hash=str(data["post_state_hash"]),
            pre_state_hash=str(data["pre_state_hash"]),
            producer_public_key=str(data["producer_public_key"]),
            producer_signature=str(data["producer_signature"]),
            transactions=tuple(Transaction.from_dict(item) for item in data["transactions"]),
        )


@dataclass(frozen=True)
class ChainSummary:
    block_count: int
    head_hash: str
    state_hash: str
    state_crystal: str
    chain_crystal: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "block_count": self.block_count,
            "chain_crystal": self.chain_crystal,
            "head_hash": self.head_hash,
            "state_crystal": self.state_crystal,
            "state_hash": self.state_hash,
        }


@dataclass(frozen=True)
class CrystalRegionHint:
    block_count: int
    split_height: int
    left_crystal: str
    right_crystal: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "block_count": self.block_count,
            "left_crystal": self.left_crystal,
            "right_crystal": self.right_crystal,
            "split_height": self.split_height,
        }


@dataclass(frozen=True)
class SyncResult:
    status: SyncStatus
    reason: str
    applied_blocks: int
    local_before: ChainSummary
    local_after: ChainSummary
    remote: ChainSummary

    def to_dict(self) -> dict[str, Any]:
        return {
            "applied_blocks": self.applied_blocks,
            "local_after": self.local_after.to_dict(),
            "local_before": self.local_before.to_dict(),
            "reason": self.reason,
            "remote": self.remote.to_dict(),
            "status": self.status,
        }


def first_divergence_height(local_hashes: list[str], remote_hashes: list[str]) -> int | None:
    common = min(len(local_hashes), len(remote_hashes))
    for height in range(common):
        if local_hashes[height] != remote_hashes[height]:
            return height
    if len(local_hashes) != len(remote_hashes):
        return common
    return None


def crystal_region_hint_for_hashes(
    block_hashes: list[str],
    *,
    root_fn: CrystalRootFn = _balanced_crystal_root,
) -> CrystalRegionHint:
    split_height = (len(block_hashes) + 1) // 2
    left = [bytes.fromhex(block_hash) for block_hash in block_hashes[:split_height]]
    right = [bytes.fromhex(block_hash) for block_hash in block_hashes[split_height:]]
    return CrystalRegionHint(
        block_count=len(block_hashes),
        left_crystal=bytes(root_fn(left)).hex(),
        right_crystal=bytes(root_fn(right)).hex(),
        split_height=split_height,
    )


def compare_crystal_region_hints(
    local: CrystalRegionHint,
    remote: CrystalRegionHint,
) -> CrystalRegion:
    if (
        local.block_count != remote.block_count
        or local.split_height != remote.split_height
    ):
        return "shape_mismatch"
    left_differs = local.left_crystal != remote.left_crystal
    right_differs = local.right_crystal != remote.right_crystal
    if left_differs and right_differs:
        return "both"
    if left_differs:
        return "left"
    if right_differs:
        return "right"
    return "none"


@dataclass
class Chain:
    state: WorldState = field(default_factory=WorldState)
    blocks: list[Block] = field(default_factory=list)

    @property
    def block_count(self) -> int:
        return len(self.blocks)

    @property
    def head_hash(self) -> str:
        return self.blocks[-1].block_hash if self.blocks else GENESIS_PARENT

    def block_hashes(self) -> list[str]:
        return [block.block_hash for block in self.blocks]

    @property
    def chain_crystal(self) -> tuple[int, ...]:
        leaves = [bytes.fromhex(block.block_hash) for block in self.blocks]
        return _balanced_crystal_root(leaves)

    def crystal_region_hint(
        self,
        *,
        root_fn: CrystalRootFn = _balanced_crystal_root,
    ) -> CrystalRegionHint:
        return crystal_region_hint_for_hashes(self.block_hashes(), root_fn=root_fn)

    def summary(self) -> ChainSummary:
        return ChainSummary(
            block_count=self.block_count,
            chain_crystal=bytes(self.chain_crystal).hex(),
            head_hash=self.head_hash,
            state_crystal=bytes(self.state.crystal_root).hex(),
            state_hash=self.state.state_hash,
        )

    def make_transaction(
        self,
        *,
        body: dict[str, Any],
        sender: KeyPair,
        tx_type: TxType,
    ) -> Transaction:
        return Transaction.signed(
            body=body,
            nonce=self.state.next_nonce(sender.public_key_hex),
            pre_state_hash=self.state.state_hash,
            sender=sender,
            tx_type=tx_type,
        )

    def make_create_wallet_tx(
        self,
        *,
        owner: KeyPair,
        wallet_id: str,
        wallet_role: WalletRole = "user",
    ) -> Transaction:
        return self.make_transaction(
            body={
                "owner_public_key": owner.public_key_hex,
                "wallet_id": wallet_id,
                "wallet_role": wallet_role,
            },
            sender=owner,
            tx_type="create_wallet",
        )

    def make_mint_tx(
        self,
        *,
        owner: KeyPair,
        token_class: TokenClass = "mesh_credit",
        token_id: str,
        wallet_id: str,
    ) -> Transaction:
        return self.make_transaction(
            body={
                "token_class": token_class,
                "token_id": token_id,
                "wallet_id": wallet_id,
            },
            sender=owner,
            tx_type="mint",
        )

    def make_transfer_tx(
        self,
        *,
        from_wallet: str,
        owner: KeyPair,
        to_wallet: str,
        token_id: str,
    ) -> Transaction:
        return self.make_transaction(
            body={
                "from_wallet": from_wallet,
                "to_wallet": to_wallet,
                "token_id": token_id,
            },
            sender=owner,
            tx_type="transfer",
        )

    def seal_transactions(self, producer: KeyPair, transactions: list[Transaction]) -> Block:
        if not transactions:
            raise LedgerError("cannot seal empty block")
        pre_state_hash = self.state.state_hash
        for index, tx in enumerate(transactions):
            self.state.apply_transaction(tx, check_pre_state=index == 0)
        block = Block.seal(
            height=len(self.blocks),
            parent_hash=self.head_hash,
            post_state=self.state,
            pre_state_hash=pre_state_hash,
            producer=producer,
            transactions=tuple(transactions),
        )
        block.verify()
        self.blocks.append(block)
        return block

    def apply_block(self, block: Block) -> None:
        block.verify()
        if block.height != len(self.blocks):
            raise LedgerError("unexpected block height")
        if block.parent_hash != self.head_hash:
            raise LedgerError("block parent mismatch")
        if block.pre_state_hash != self.state.state_hash:
            raise LedgerError("block pre-state mismatch")
        next_state = self.state.clone()
        for index, tx in enumerate(block.transactions):
            next_state.apply_transaction(tx, check_pre_state=index == 0)
        if block.post_state_hash != next_state.state_hash:
            raise LedgerError("block post-state mismatch")
        if block.post_state_crystal != bytes(next_state.crystal_root).hex():
            raise LedgerError("block post-state crystal mismatch")
        self.state = next_state
        self.blocks.append(block)

    def export_blocks_from(self, start_height: int) -> list[dict[str, Any]]:
        return [block.to_dict() for block in self.blocks[start_height:]]

    def manifest(self) -> dict[str, Any]:
        return {
            "block_hashes": self.block_hashes(),
            "summary": self.summary().to_dict(),
        }

    def sync_from_remote(
        self,
        manifest: dict[str, Any],
        exported_blocks: list[dict[str, Any]],
    ) -> SyncResult:
        local_before = self.summary()
        remote_summary = ChainSummary(**manifest["summary"])
        remote_hashes = [str(item) for item in manifest["block_hashes"]]

        if local_before.head_hash == remote_summary.head_hash:
            status: SyncStatus = "already_in_sync"
            reason = "heads already match"
            return SyncResult(
                applied_blocks=0,
                local_after=self.summary(),
                local_before=local_before,
                reason=reason,
                remote=remote_summary,
                status=status,
            )

        local_hashes = self.block_hashes()
        mismatch = first_divergence_height(local_hashes, remote_hashes)
        if mismatch is not None and mismatch < min(len(local_hashes), len(remote_hashes)):
            return SyncResult(
                applied_blocks=0,
                local_after=self.summary(),
                local_before=local_before,
                reason=f"histories diverge at height {mismatch}",
                remote=remote_summary,
                status="conflict",
            )
        if len(local_hashes) > len(remote_hashes):
            return SyncResult(
                applied_blocks=0,
                local_after=self.summary(),
                local_before=local_before,
                reason="remote history is a prefix of local",
                remote=remote_summary,
                status="remote_behind",
            )

        expected_missing = len(remote_hashes) - len(local_hashes)
        if len(exported_blocks) != expected_missing:
            raise LedgerError(f"expected {expected_missing} repair blocks")
        applied = 0
        for payload in exported_blocks:
            self.apply_block(Block.from_dict(payload))
            applied += 1
        return SyncResult(
            applied_blocks=applied,
            local_after=self.summary(),
            local_before=local_before,
            reason="remote history extended local prefix",
            remote=remote_summary,
            status="applied_blocks",
        )

    def sync_from_remote_head(
        self,
        *,
        exported_blocks: list[dict[str, Any]],
        remote_block_count: int,
        remote_chain_crystal: str,
        remote_head_hash: str,
        remote_state_crystal: str,
    ) -> SyncResult:
        local_before = self.summary()
        remote_summary = ChainSummary(
            block_count=remote_block_count,
            chain_crystal=remote_chain_crystal,
            head_hash=remote_head_hash,
            state_crystal=remote_state_crystal,
            state_hash="",
        )
        if local_before.head_hash == remote_head_hash:
            return SyncResult(
                applied_blocks=0,
                local_after=self.summary(),
                local_before=local_before,
                reason="heads already match",
                remote=remote_summary,
                status="already_in_sync",
            )
        if self.block_count > remote_block_count:
            return SyncResult(
                applied_blocks=0,
                local_after=self.summary(),
                local_before=local_before,
                reason="remote history is shorter than local",
                remote=remote_summary,
                status="remote_behind",
            )
        if self.block_count == remote_block_count:
            return SyncResult(
                applied_blocks=0,
                local_after=self.summary(),
                local_before=local_before,
                reason="same-height heads differ",
                remote=remote_summary,
                status="conflict",
            )

        expected_missing = remote_block_count - self.block_count
        if len(exported_blocks) != expected_missing:
            raise LedgerError(f"expected {expected_missing} repair blocks")
        candidate = Chain(state=self.state.clone(), blocks=list(self.blocks))
        applied = 0
        for payload in exported_blocks:
            candidate.apply_block(Block.from_dict(payload))
            applied += 1
        local_after = candidate.summary()
        if local_after.head_hash != remote_head_hash:
            raise LedgerError("repair did not reach advertised remote head")
        if local_after.chain_crystal != remote_chain_crystal:
            raise LedgerError("repair did not reach advertised chain crystal")
        if local_after.state_crystal != remote_state_crystal:
            raise LedgerError("repair did not reach advertised state crystal")
        self.state = candidate.state
        self.blocks = candidate.blocks
        return SyncResult(
            applied_blocks=applied,
            local_after=self.summary(),
            local_before=local_before,
            reason="remote head extended local prefix without hash-list manifest",
            remote=remote_summary,
            status="applied_blocks",
        )

    @classmethod
    def from_blocks(cls, blocks: list[Block]) -> Chain:
        chain = cls()
        for block in blocks:
            chain.apply_block(block)
        return chain

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Chain:
        return cls.from_blocks([Block.from_dict(item) for item in data["blocks"]])

    def to_dict(self) -> dict[str, Any]:
        return {
            "blocks": [block.to_dict() for block in self.blocks],
            "state": self.state.to_dict(),
            "summary": self.summary().to_dict(),
        }


def block_witness_payload(chain: Chain, height: int) -> bytes:
    if not 0 <= height < chain.block_count:
        raise LedgerError("block witness height out of range")
    block = chain.blocks[height]
    payload = {
        "block": block.to_dict(),
        "boundary": "reference block witness bytes; not a compact production proof",
        "chain_head": chain.head_hash,
        "height": height,
        "schema": "crystal.mesh_ledger.block_witness.v0",
    }
    return canonical_json(payload)


def divergence_witness_payload(local: Chain, remote: Chain, mismatch_height: int) -> bytes:
    if not 0 <= mismatch_height < min(local.block_count, remote.block_count):
        raise LedgerError("divergence witness height out of range")
    payload = {
        "boundary": "reference divergence witness bytes; not fork choice or consensus",
        "local_block": local.blocks[mismatch_height].to_dict(),
        "local_head": local.head_hash,
        "mismatch_height": mismatch_height,
        "remote_block": remote.blocks[mismatch_height].to_dict(),
        "remote_head": remote.head_hash,
        "same_parent": local.blocks[mismatch_height].parent_hash
        == remote.blocks[mismatch_height].parent_hash,
        "schema": "crystal.mesh_ledger.divergence_witness.v0",
    }
    return canonical_json(payload)
