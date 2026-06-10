from __future__ import annotations

import pytest

from crystal_mesh_ledger import Chain, KeyPair, LedgerError, build_report
from crystal_mesh_ledger.compact import (
    decode_compact_block_sequence,
    decode_compact_block_witness,
    decode_compact_divergence_witness,
    encode_compact_block_sequence,
    encode_compact_block_witness,
    encode_compact_divergence_witness,
)
from crystal_mesh_ledger.ledger import _balanced_crystal_root
from crystal_mesh_ledger.localization import (
    build_localization_report,
    mutual_information_bits,
)
from crystal_mesh_ledger.wire import (
    DEFAULT_BLE_PAYLOAD_BYTES,
    decode_compact_beacon,
    decode_crystal_region_hint,
    decode_witness_request,
    encode_compact_beacon,
    encode_crystal_region_hint,
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


def test_fragment_frames_keep_header_inside_payload_budget() -> None:
    frame = b"x" * 961
    fragments = fragment_frame(frame, payload_bytes=DEFAULT_BLE_PAYLOAD_BYTES)

    assert len(fragments) == 5
    assert all(len(fragment) <= DEFAULT_BLE_PAYLOAD_BYTES for fragment in fragments)


def test_crystal_region_hint_is_29_bytes_and_round_trips() -> None:
    frame = encode_crystal_region_hint(
        block_count=4,
        left_crystal=b"\x44" * 8,
        right_crystal=b"\x55" * 8,
        split_height=2,
    )

    decoded = decode_crystal_region_hint(frame)

    assert len(frame) == 29
    assert len(fragment_frame(frame, payload_bytes=DEFAULT_BLE_PAYLOAD_BYTES)) == 1
    assert decoded["block_count"] == 4
    assert decoded["left_crystal"] == "44" * 8
    assert decoded["right_crystal"] == "55" * 8
    assert decoded["split_height"] == 2


def test_odd_leaf_crystal_fold_does_not_duplicate_last_leaf() -> None:
    a = b"A" * 32
    b = b"B" * 32
    c = b"C" * 32

    assert _balanced_crystal_root([a, b, c]) != _balanced_crystal_root([a, b, c, c])


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


def test_count_only_catch_up_needs_no_hash_manifest() -> None:
    producer = KeyPair.from_seed("test-count-only-producer")
    alice = KeyPair.from_seed("test-count-only-alice")
    bob = KeyPair.from_seed("test-count-only-bob")
    source = Chain()
    source.seal_transactions(
        producer,
        [
            source.make_create_wallet_tx(owner=alice, wallet_id="alice"),
            source.make_create_wallet_tx(owner=bob, wallet_id="bob"),
        ],
    )
    lagging = Chain.from_dict(source.to_dict())
    source.seal_transactions(
        producer,
        [
            source.make_mint_tx(owner=alice, token_id="T", wallet_id="alice"),
        ],
    )
    source_summary = source.summary()

    result = lagging.sync_from_remote_head(
        exported_blocks=source.export_blocks_from(lagging.block_count),
        remote_block_count=source_summary.block_count,
        remote_chain_crystal=source_summary.chain_crystal,
        remote_head_hash=source_summary.head_hash,
        remote_state_crystal=source_summary.state_crystal,
    )

    assert result.status == "applied_blocks"
    assert result.reason == "remote head extended local prefix without hash-list manifest"
    assert lagging.head_hash == source.head_hash


def test_compact_block_sequence_round_trips_and_validates() -> None:
    producer = KeyPair.from_seed("test-compact-producer")
    alice = KeyPair.from_seed("test-compact-alice")
    bob = KeyPair.from_seed("test-compact-bob")
    source = Chain()
    source.seal_transactions(
        producer,
        [
            source.make_create_wallet_tx(owner=alice, wallet_id="alice"),
            source.make_create_wallet_tx(owner=bob, wallet_id="bob"),
        ],
    )
    lagging = Chain.from_dict(source.to_dict())
    source.seal_transactions(
        producer,
        [
            source.make_mint_tx(owner=alice, token_id="T", wallet_id="alice"),
        ],
    )
    source.seal_transactions(
        producer,
        [
            source.make_transfer_tx(
                from_wallet="alice",
                owner=alice,
                to_wallet="bob",
                token_id="T",
            )
        ],
    )
    frame = encode_compact_block_sequence(source.blocks[lagging.block_count :])
    decoded = decode_compact_block_sequence(frame)
    summary = source.summary()

    result = lagging.sync_from_remote_head(
        exported_blocks=[block.to_dict() for block in decoded],
        remote_block_count=summary.block_count,
        remote_chain_crystal=summary.chain_crystal,
        remote_head_hash=summary.head_hash,
        remote_state_crystal=summary.state_crystal,
    )

    assert result.status == "applied_blocks"
    assert lagging.summary() == source.summary()
    assert len(fragment_frame(frame, payload_bytes=DEFAULT_BLE_PAYLOAD_BYTES)) <= 5


def test_compact_witnesses_round_trip() -> None:
    producer = KeyPair.from_seed("test-compact-witness-producer")
    alice = KeyPair.from_seed("test-compact-witness-alice")
    bob = KeyPair.from_seed("test-compact-witness-bob")
    carol = KeyPair.from_seed("test-compact-witness-carol")
    common = Chain()
    common.seal_transactions(
        producer,
        [
            common.make_create_wallet_tx(owner=alice, wallet_id="alice"),
            common.make_create_wallet_tx(owner=bob, wallet_id="bob"),
            common.make_create_wallet_tx(owner=carol, wallet_id="carol"),
        ],
    )
    common.seal_transactions(
        producer,
        [
            common.make_mint_tx(owner=alice, token_id="T", wallet_id="alice"),
        ],
    )
    left = Chain.from_dict(common.to_dict())
    right = Chain.from_dict(common.to_dict())
    left.seal_transactions(
        producer,
        [
            left.make_transfer_tx(
                from_wallet="alice",
                owner=alice,
                to_wallet="bob",
                token_id="T",
            )
        ],
    )
    right.seal_transactions(
        producer,
        [
            right.make_transfer_tx(
                from_wallet="alice",
                owner=alice,
                to_wallet="carol",
                token_id="T",
            )
        ],
    )

    block_frame = encode_compact_block_witness(right.blocks[2])
    assert decode_compact_block_witness(block_frame).block_hash == right.blocks[2].block_hash
    assert len(fragment_frame(block_frame, payload_bytes=DEFAULT_BLE_PAYLOAD_BYTES)) <= 3

    divergence_frame = encode_compact_divergence_witness(left.blocks[2], right.blocks[2])
    decoded_left, decoded_right, same_parent = decode_compact_divergence_witness(
        divergence_frame
    )
    assert decoded_left.block_hash == left.blocks[2].block_hash
    assert decoded_right.block_hash == right.blocks[2].block_hash
    assert same_parent is True
    assert len(fragment_frame(divergence_frame, payload_bytes=DEFAULT_BLE_PAYLOAD_BYTES)) <= 3


def test_count_only_catch_up_rejects_forked_suffix() -> None:
    producer = KeyPair.from_seed("test-forked-suffix-producer")
    alice = KeyPair.from_seed("test-forked-suffix-alice")
    bob = KeyPair.from_seed("test-forked-suffix-bob")
    carol = KeyPair.from_seed("test-forked-suffix-carol")
    common = Chain()
    common.seal_transactions(
        producer,
        [
            common.make_create_wallet_tx(owner=alice, wallet_id="alice"),
            common.make_create_wallet_tx(owner=bob, wallet_id="bob"),
            common.make_create_wallet_tx(owner=carol, wallet_id="carol"),
        ],
    )
    common.seal_transactions(
        producer,
        [
            common.make_mint_tx(owner=alice, token_id="T", wallet_id="alice"),
        ],
    )
    local = Chain.from_dict(common.to_dict())
    fork = Chain.from_dict(common.to_dict())
    local.seal_transactions(
        producer,
        [
            local.make_transfer_tx(
                from_wallet="alice",
                owner=alice,
                to_wallet="bob",
                token_id="T",
            )
        ],
    )
    fork.seal_transactions(
        producer,
        [
            fork.make_transfer_tx(
                from_wallet="alice",
                owner=alice,
                to_wallet="carol",
                token_id="T",
            )
        ],
    )
    fork.seal_transactions(
        producer,
        [
            fork.make_mint_tx(owner=alice, token_id="FORK_EXTRA", wallet_id="alice"),
        ],
    )
    fork_summary = fork.summary()

    with pytest.raises(LedgerError, match="block parent mismatch"):
        local.sync_from_remote_head(
            exported_blocks=fork.export_blocks_from(local.block_count),
            remote_block_count=fork_summary.block_count,
            remote_chain_crystal=fork_summary.chain_crystal,
            remote_head_hash=fork_summary.head_hash,
            remote_state_crystal=fork_summary.state_crystal,
        )


def test_count_only_catch_up_does_not_commit_lied_head() -> None:
    producer = KeyPair.from_seed("test-lied-head-producer")
    alice = KeyPair.from_seed("test-lied-head-alice")
    source = Chain()
    source.seal_transactions(
        producer,
        [
            source.make_create_wallet_tx(owner=alice, wallet_id="alice"),
        ],
    )
    lagging = Chain.from_dict(source.to_dict())
    source.seal_transactions(
        producer,
        [
            source.make_mint_tx(owner=alice, token_id="T", wallet_id="alice"),
        ],
    )
    source_summary = source.summary()
    before = lagging.summary()

    with pytest.raises(LedgerError, match="repair did not reach advertised remote head"):
        lagging.sync_from_remote_head(
            exported_blocks=source.export_blocks_from(lagging.block_count),
            remote_block_count=source_summary.block_count,
            remote_chain_crystal=source_summary.chain_crystal,
            remote_head_hash="00" * 32,
            remote_state_crystal=source_summary.state_crystal,
        )

    assert lagging.summary() == before


def test_crystal_region_hint_localizes_and_kill_test_flips() -> None:
    report = build_report()

    assert report["fork_hold"]["crystal_region"] == "right"
    assert report["fork_hold"]["crystal_disabled_region"] == "none"
    assert report["fork_hold"]["crystal_kill_test_flips"] is True


def test_localization_gradient_harness_is_deterministic() -> None:
    left = build_localization_report(samples=128, chain_length=32, bins=8)
    right = build_localization_report(samples=128, chain_length=32, bins=8)

    assert left == right
    assert left["families"]["blake3_trunc64_null"]["mi_bits_hamming"] >= 0
    assert "balanced_crystal" in left["families"]
    assert "sequential_crystal" in left["families"]


def test_mutual_information_sanity() -> None:
    assert mutual_information_bits(["a", "a", "b", "b"], ["x", "x", "y", "y"]) == 1.0
    assert mutual_information_bits(["a", "a", "b", "b"], ["x", "x", "x", "x"]) == 0.0


def test_wallet_roles_and_token_classes_are_bound_in_state() -> None:
    producer = KeyPair.from_seed("test-role-producer")
    founder = KeyPair.from_seed("test-founder")
    builder = KeyPair.from_seed("test-builder")
    outsider = KeyPair.from_seed("test-outsider")
    chain = Chain()

    chain.seal_transactions(
        producer,
        [
            chain.make_create_wallet_tx(
                owner=founder,
                wallet_id="founder:adem",
                wallet_role="founder",
            ),
            chain.make_create_wallet_tx(
                owner=builder,
                wallet_id="builder:ble-adapter",
                wallet_role="builder",
            ),
        ],
    )

    assert chain.state.wallet_roles["founder:adem"] == "founder"
    assert chain.state.wallet_roles["builder:ble-adapter"] == "builder"

    with pytest.raises(LedgerError, match="mint signer must own target wallet"):
        chain.seal_transactions(
            producer,
            [
                chain.make_mint_tx(
                    owner=outsider,
                    token_id="mesh-credit:bad-mint",
                    wallet_id="founder:adem",
                )
            ],
        )

    chain.seal_transactions(
        producer,
        [
            chain.make_mint_tx(
                owner=founder,
                token_class="mesh_credit",
                token_id="mesh-credit:genesis",
                wallet_id="founder:adem",
            )
        ],
    )

    assert chain.state.token_classes["mesh-credit:genesis"] == "mesh_credit"
    assert chain.state.tokens["mesh-credit:genesis"] == "founder:adem"

    with pytest.raises(LedgerError, match="transfer signer must own source wallet"):
        chain.seal_transactions(
            producer,
            [
                chain.make_transfer_tx(
                    from_wallet="founder:adem",
                    owner=builder,
                    to_wallet="builder:ble-adapter",
                    token_id="mesh-credit:genesis",
                )
            ],
        )

    chain.seal_transactions(
        producer,
        [
            chain.make_transfer_tx(
                from_wallet="founder:adem",
                owner=founder,
                to_wallet="builder:ble-adapter",
                token_id="mesh-credit:genesis",
            )
        ],
    )

    assert chain.state.tokens["mesh-credit:genesis"] == "builder:ble-adapter"
    assert Chain.from_dict(chain.to_dict()).summary() == chain.summary()


def test_simulation_report_is_sober_and_passes_required_gates() -> None:
    report = build_report()

    assert report["ok"] is True
    assert report["gates"]["catch_up_repair_beats_full_chain"] is True
    assert report["gates"]["catch_up_uses_no_hash_manifest"] is True
    assert report["gates"]["crystal_region_localizes_fork"] is True
    assert report["gates"]["crystal_kill_test_flips"] is True
    assert report["gates"]["fork_held_without_auto_merge"] is True
    assert report["gates"]["fork_mismatch_height_is_2"] is True
    assert report["gates"]["region_hint_is_one_packet"] is True
    assert report["sync"]["beacon_wire_bytes"] == 65
    assert report["catch_up"]["hash_manifest_wire_bytes"] == 0
    assert report["catch_up"]["repair_wire_bytes"] > 0
    assert report["fork_hold"]["divergence_witness_wire_bytes"] > 0
    assert report["aspirational_targets"]["repair_le_5_packets"] is True
    assert report["aspirational_targets"]["block_witness_le_3_packets"] is True
    assert report["aspirational_targets"]["divergence_witness_le_3_packets"] is True
