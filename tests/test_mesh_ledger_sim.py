from __future__ import annotations

from crystal_mesh_ledger import Chain, KeyPair, build_report
from crystal_mesh_ledger.wire import (
    DEFAULT_BLE_PAYLOAD_BYTES,
    decode_compact_beacon,
    decode_witness_request,
    encode_compact_beacon,
    encode_witness_request,
    fragment_frame,
)


def test_compact_beacon_is_65_bytes_and_one_packet() -> None:
    frame = encode_compact_beacon(
        blake3_head=b"\x11" * 32,
        block_count=7,
        chain_crystal=b"\x22" * 8,
        peer_id=b"peer1234",
        state_crystal=b"\x33" * 8,
    )

    decoded = decode_compact_beacon(frame)

    assert len(frame) == 65
    assert len(fragment_frame(frame, payload_bytes=DEFAULT_BLE_PAYLOAD_BYTES)) == 1
    assert decoded["block_count"] == 7
    assert decoded["chain_crystal"] == "22" * 8
    assert decoded["state_crystal"] == "33" * 8


def test_witness_request_is_12_bytes_and_round_trips() -> None:
    frame = encode_witness_request(mismatch_height=2, request_nonce=123)

    decoded = decode_witness_request(frame)

    assert len(frame) == 12
    assert decoded["mismatch_height"] == 2
    assert decoded["request_nonce"] == 123


def test_signed_chain_sync_holds_conflict() -> None:
    producer = KeyPair.from_seed("test-producer")
    alice = KeyPair.from_seed("test-alice")
    bob = KeyPair.from_seed("test-bob")
    chain = Chain()
    chain.seal_transactions(
        producer,
        [
            chain.make_create_wallet_tx(owner=alice, wallet_id="alice"),
            chain.make_create_wallet_tx(owner=bob, wallet_id="bob"),
        ],
    )
    peer = Chain.from_dict(chain.to_dict())

    chain.seal_transactions(
        producer,
        [
            chain.make_mint_tx(owner=alice, token_id="T", wallet_id="alice"),
        ],
    )
    result = peer.sync_from_remote(chain.manifest(), chain.export_blocks_from(peer.block_count))

    assert result.status == "applied_blocks"
    assert peer.head_hash == chain.head_hash


def test_simulation_report_is_sober_and_passes_required_gates() -> None:
    report = build_report()

    assert report["ok"] is True
    assert report["gates"]["catch_up_repair_beats_full_chain"] is True
    assert report["gates"]["fork_held_without_auto_merge"] is True
    assert report["gates"]["fork_mismatch_height_is_2"] is True
    assert report["sync"]["beacon_wire_bytes"] == 65
    assert report["catch_up"]["repair_wire_bytes"] > 0
    assert report["fork_hold"]["divergence_witness_wire_bytes"] > 0
