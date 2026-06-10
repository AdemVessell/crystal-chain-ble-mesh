from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import blake3

from .compact import (
    decode_compact_block_sequence,
    decode_compact_block_witness,
    decode_compact_divergence_witness,
    encode_compact_block_sequence,
    encode_compact_block_witness,
    encode_compact_divergence_witness,
)
from .ledger import (
    Chain,
    KeyPair,
    block_witness_payload,
    canonical_json,
    compare_crystal_region_hints,
    disabled_crystal_root,
    divergence_witness_payload,
    first_divergence_height,
)
from .wire import (
    BITCHAT_GCS_BUDGET_BYTES,
    DEFAULT_BLE_PAYLOAD_BYTES,
    LEGACY_BLE_PAYLOAD_BYTES,
    ble_packet_count,
    encode_compact_beacon,
    encode_crystal_region_hint,
    encode_witness_request,
    transmit_frame,
)

RUN_ID = "crystal_mesh_ledger_sim"
SCHEMA = "crystal.mesh_ledger.sim_report.v0"
DETERMINISTIC_GENERATED_AT = "2026-06-10T00:00:00+00:00"


@dataclass(frozen=True)
class SimStep:
    scenario: str
    label: str
    family: str
    wire_bytes: int
    ble_packets: int
    payload_bytes: int
    accepted: bool
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "ble_packets": self.ble_packets,
            "detail": self.detail,
            "family": self.family,
            "label": self.label,
            "payload_bytes": self.payload_bytes,
            "scenario": self.scenario,
            "wire_bytes": self.wire_bytes,
        }


def _peer_id(name: str) -> bytes:
    return (name.encode("utf-8") + b"\x00" * 8)[:8]


def _blake3_region_root(leaves: list[bytes]) -> tuple[int, ...]:
    if not leaves:
        return (0, 0, 0, 0, 0, 0, 0, 0)
    hasher = blake3.blake3(b"crystal-region-hint-null-v0")
    for leaf in leaves:
        hasher.update(len(leaf).to_bytes(4, "big"))
        hasher.update(leaf)
    return tuple(hasher.digest()[:8])


def _beacon_frame(chain: Chain, peer_name: str) -> bytes:
    summary = chain.summary()
    return encode_compact_beacon(
        blake3_head=bytes.fromhex(summary.head_hash),
        block_count=summary.block_count,
        chain_crystal=bytes.fromhex(summary.chain_crystal),
        peer_id=_peer_id(peer_name),
        state_crystal=bytes.fromhex(summary.state_crystal),
    )


def _base_chain() -> tuple[Chain, KeyPair, KeyPair, KeyPair, KeyPair]:
    producer = KeyPair.from_seed("mesh-ledger-producer")
    alice = KeyPair.from_seed("mesh-ledger-alice")
    bob = KeyPair.from_seed("mesh-ledger-bob")
    carol = KeyPair.from_seed("mesh-ledger-carol")
    chain = Chain()
    chain.seal_transactions(
        producer,
        [
            chain.make_create_wallet_tx(owner=alice, wallet_id="alice"),
            chain.make_create_wallet_tx(owner=bob, wallet_id="bob"),
            chain.make_create_wallet_tx(owner=carol, wallet_id="carol"),
        ],
    )
    chain.seal_transactions(
        producer,
        [
            chain.make_mint_tx(
                owner=alice,
                token_id="MESH_TOKEN",
                wallet_id="alice",
            )
        ],
    )
    return chain, producer, alice, bob, carol


def _record_step(
    steps: list[SimStep],
    *,
    accepted: bool,
    detail: str,
    family: str,
    frame: bytes,
    label: str,
    payload_bytes: int,
    scenario: str,
) -> None:
    tx = transmit_frame(label, frame, payload_bytes=payload_bytes)
    steps.append(
        SimStep(
            accepted=accepted,
            ble_packets=tx.ble_packets,
            detail=detail,
            family=family,
            label=label,
            payload_bytes=payload_bytes,
            scenario=scenario,
            wire_bytes=tx.wire_bytes,
        )
    )


def _naive_full_chain_bytes(chain: Chain) -> int:
    return len(
        canonical_json(
            {
                "blocks": chain.export_blocks_from(0),
                "manifest": chain.manifest(),
            }
        )
    )


def run_catch_up_scenario(steps: list[SimStep], *, payload_bytes: int) -> dict[str, Any]:
    scenario = "catch_up"
    source, producer, alice, _bob, _carol = _base_chain()
    lagging = Chain.from_blocks(source.blocks[:1])

    source.seal_transactions(
        producer,
        [
            source.make_transfer_tx(
                from_wallet="alice",
                owner=alice,
                to_wallet="bob",
                token_id="MESH_TOKEN",
            )
        ],
    )

    _record_step(
        steps,
        accepted=True,
        detail=f"height={lagging.block_count}",
        family="commitment_beacon",
        frame=_beacon_frame(lagging, "peer_alpha"),
        label="alpha advertises lagging head",
        payload_bytes=payload_bytes,
        scenario=scenario,
    )
    _record_step(
        steps,
        accepted=True,
        detail=f"height={source.block_count}",
        family="commitment_beacon",
        frame=_beacon_frame(source, "peer_beta"),
        label="beta advertises extended head",
        payload_bytes=payload_bytes,
        scenario=scenario,
    )

    repair_start_height = lagging.block_count
    repair_source_blocks = source.blocks[repair_start_height:]
    reference_json_wire = canonical_json({"blocks": source.export_blocks_from(repair_start_height)})
    repair_wire = encode_compact_block_sequence(repair_source_blocks)
    repair_blocks = [block.to_dict() for block in decode_compact_block_sequence(repair_wire)]
    source_summary = source.summary()
    sync_result = lagging.sync_from_remote_head(
        exported_blocks=repair_blocks,
        remote_block_count=source_summary.block_count,
        remote_chain_crystal=source_summary.chain_crystal,
        remote_head_hash=source_summary.head_hash,
        remote_state_crystal=source_summary.state_crystal,
    )
    _record_step(
        steps,
        accepted=sync_result.status == "applied_blocks",
        detail=sync_result.reason,
        family="block_repair",
        frame=repair_wire,
        label="beta ships missing block suffix",
        payload_bytes=payload_bytes,
        scenario=scenario,
    )
    naive_full_chain_bytes = _naive_full_chain_bytes(source)
    return {
        "applied_blocks": sync_result.applied_blocks,
        "heads_match_after_sync": lagging.head_hash == source.head_hash,
        "hash_manifest_wire_bytes": 0,
        "naive_full_chain_bytes": naive_full_chain_bytes,
        "reference_json_repair_wire_bytes": len(reference_json_wire),
        "repair_beats_full_chain": len(repair_wire) < naive_full_chain_bytes,
        "repair_ble_packets": ble_packet_count(len(repair_wire), payload_bytes=payload_bytes),
        "repair_wire_bytes": len(repair_wire),
        "status": sync_result.status,
    }


def run_fork_scenario(steps: list[SimStep], *, payload_bytes: int) -> dict[str, Any]:
    scenario = "fork_hold"
    common, producer, alice, _bob, carol = _base_chain()
    branch_a = Chain.from_dict(common.to_dict())
    branch_b = Chain.from_dict(common.to_dict())
    branch_a.seal_transactions(
        producer,
        [
            branch_a.make_transfer_tx(
                from_wallet="alice",
                owner=alice,
                to_wallet="bob",
                token_id="MESH_TOKEN",
            )
        ],
    )
    branch_a.seal_transactions(
        producer,
        [
            branch_a.make_mint_tx(
                owner=alice,
                token_id="BRANCH_A_RECEIPT",
                wallet_id="alice",
            )
        ],
    )
    branch_b.seal_transactions(
        producer,
        [
            branch_b.make_transfer_tx(
                from_wallet="alice",
                owner=alice,
                to_wallet="carol",
                token_id="MESH_TOKEN",
            )
        ],
    )
    branch_b.seal_transactions(
        producer,
        [
            branch_b.make_mint_tx(
                owner=alice,
                token_id="BRANCH_B_RECEIPT",
                wallet_id="alice",
            )
        ],
    )

    _record_step(
        steps,
        accepted=True,
        detail=f"height={branch_a.block_count}",
        family="commitment_beacon",
        frame=_beacon_frame(branch_a, "peer_alpha"),
        label="alpha beacon at fork head",
        payload_bytes=payload_bytes,
        scenario=scenario,
    )
    _record_step(
        steps,
        accepted=True,
        detail=f"height={branch_b.block_count}",
        family="commitment_beacon",
        frame=_beacon_frame(branch_b, "peer_beta"),
        label="beta beacon at fork head",
        payload_bytes=payload_bytes,
        scenario=scenario,
    )

    branch_b_summary = branch_b.summary()
    sync_result = branch_a.sync_from_remote_head(
        exported_blocks=[],
        remote_block_count=branch_b_summary.block_count,
        remote_chain_crystal=branch_b_summary.chain_crystal,
        remote_head_hash=branch_b_summary.head_hash,
        remote_state_crystal=branch_b_summary.state_crystal,
    )
    mismatch_height = first_divergence_height(branch_a.block_hashes(), branch_b.block_hashes())
    hold_conflict = sync_result.status == "conflict" and sync_result.applied_blocks == 0
    if mismatch_height is None:
        raise AssertionError("fork fixture did not diverge")

    local_hint = branch_a.crystal_region_hint()
    remote_hint = branch_b.crystal_region_hint()
    crystal_region = compare_crystal_region_hints(local_hint, remote_hint)
    disabled_region = compare_crystal_region_hints(
        branch_a.crystal_region_hint(root_fn=disabled_crystal_root),
        branch_b.crystal_region_hint(root_fn=disabled_crystal_root),
    )
    hash_null_region = compare_crystal_region_hints(
        branch_a.crystal_region_hint(root_fn=_blake3_region_root),
        branch_b.crystal_region_hint(root_fn=_blake3_region_root),
    )
    hint_frame = encode_crystal_region_hint(
        block_count=remote_hint.block_count,
        left_crystal=bytes.fromhex(remote_hint.left_crystal),
        right_crystal=bytes.fromhex(remote_hint.right_crystal),
        split_height=remote_hint.split_height,
    )
    _record_step(
        steps,
        accepted=crystal_region == "right",
        detail=f"region={crystal_region}; split_height={remote_hint.split_height}",
        family="crystal_region_hint",
        frame=hint_frame,
        label="beta returns Crystal region hint",
        payload_bytes=payload_bytes,
        scenario=scenario,
    )

    request_frame = encode_witness_request(
        mismatch_height=mismatch_height,
        request_nonce=0xA11CE001,
    )
    _record_step(
        steps,
        accepted=hold_conflict,
        detail=sync_result.reason,
        family="witness_request",
        frame=request_frame,
        label="alpha requests divergence witness",
        payload_bytes=payload_bytes,
        scenario=scenario,
    )

    reference_divergence_wire = divergence_witness_payload(branch_a, branch_b, mismatch_height)
    divergence_wire = encode_compact_divergence_witness(
        branch_a.blocks[mismatch_height],
        branch_b.blocks[mismatch_height],
    )
    decoded_local, decoded_remote, decoded_same_parent = decode_compact_divergence_witness(
        divergence_wire
    )
    if decoded_local.block_hash != branch_a.blocks[mismatch_height].block_hash:
        raise AssertionError("compact divergence local block did not round-trip")
    if decoded_remote.block_hash != branch_b.blocks[mismatch_height].block_hash:
        raise AssertionError("compact divergence remote block did not round-trip")
    _record_step(
        steps,
        accepted=decoded_same_parent,
        detail=f"mismatch_height={mismatch_height}",
        family="witness_response",
        frame=divergence_wire,
        label="beta returns compact divergence witness",
        payload_bytes=payload_bytes,
        scenario=scenario,
    )

    reference_block_wire = block_witness_payload(branch_b, mismatch_height)
    block_wire = encode_compact_block_witness(branch_b.blocks[mismatch_height])
    decoded_block = decode_compact_block_witness(block_wire)
    if decoded_block.block_hash != branch_b.blocks[mismatch_height].block_hash:
        raise AssertionError("compact block witness did not round-trip")
    _record_step(
        steps,
        accepted=True,
        detail=f"height={mismatch_height}",
        family="witness_response",
        frame=block_wire,
        label="beta returns compact block witness",
        payload_bytes=payload_bytes,
        scenario=scenario,
    )

    return {
        "auto_merge_allowed": False,
        "block_witness_ble_packets": ble_packet_count(len(block_wire), payload_bytes=payload_bytes),
        "block_witness_wire_bytes": len(block_wire),
        "crystal_disabled_region": disabled_region,
        "crystal_kill_test_flips": disabled_region != crystal_region,
        "crystal_region": crystal_region,
        "crystal_region_hint_ble_packets": ble_packet_count(
            len(hint_frame),
            payload_bytes=payload_bytes,
        ),
        "crystal_region_hint_wire_bytes": len(hint_frame),
        "divergence_witness_ble_packets": ble_packet_count(
            len(divergence_wire),
            payload_bytes=payload_bytes,
        ),
        "divergence_witness_wire_bytes": len(divergence_wire),
        "hold_conflict": hold_conflict,
        "region_hint_digest_attribution": (
            "explicit region-hint frame is load-bearing; current Crystal fold is "
            "not uniquely required versus truncated BLAKE3 for this fixture"
        ),
        "region_hint_frame_load_bearing": disabled_region != crystal_region,
        "region_hint_hash_null_localizes_identically": hash_null_region == crystal_region,
        "region_hint_hash_null_region": hash_null_region,
        "mismatch_height": mismatch_height,
        "naive_full_chain_bytes": _naive_full_chain_bytes(branch_b),
        "reference_json_block_witness_wire_bytes": len(reference_block_wire),
        "reference_json_divergence_witness_wire_bytes": len(reference_divergence_wire),
        "same_parent": branch_a.blocks[mismatch_height].parent_hash
        == branch_b.blocks[mismatch_height].parent_hash,
        "status": sync_result.status,
    }


def build_report(*, payload_bytes: int = DEFAULT_BLE_PAYLOAD_BYTES) -> dict[str, Any]:
    steps: list[SimStep] = []
    catch_up = run_catch_up_scenario(steps, payload_bytes=payload_bytes)
    fork_hold = run_fork_scenario(steps, payload_bytes=payload_bytes)
    beacon_packets = sum(step.ble_packets for step in steps if step.family == "commitment_beacon")
    total_packets = sum(step.ble_packets for step in steps)
    gates = {
        "all_steps_accepted": all(step.accepted for step in steps),
        "beacons_are_one_packet": all(
            step.ble_packets == 1 for step in steps if step.family == "commitment_beacon"
        ),
        "catch_up_applied_blocks": catch_up["status"] == "applied_blocks",
        "catch_up_heads_match": bool(catch_up["heads_match_after_sync"]),
        "catch_up_uses_no_hash_manifest": catch_up["hash_manifest_wire_bytes"] == 0,
        "catch_up_repair_beats_full_chain": bool(catch_up["repair_beats_full_chain"]),
        "crystal_kill_test_flips": bool(fork_hold["crystal_kill_test_flips"]),
        "crystal_region_localizes_fork": fork_hold["crystal_region"] == "right",
        "fork_held_without_auto_merge": bool(fork_hold["hold_conflict"]),
        "fork_mismatch_height_is_2": fork_hold["mismatch_height"] == 2,
        "region_hint_is_one_packet": fork_hold["crystal_region_hint_ble_packets"] == 1,
        "witness_request_is_one_packet": all(
            step.ble_packets == 1 for step in steps if step.family == "witness_request"
        ),
    }
    aspirational_targets = {
        "block_witness_le_3_packets": fork_hold["block_witness_ble_packets"] <= 3,
        "divergence_witness_le_3_packets": fork_hold["divergence_witness_ble_packets"] <= 3,
        "repair_le_5_packets": catch_up["repair_ble_packets"] <= 5,
    }
    return {
        "aspirational_targets": aspirational_targets,
        "baseline": {
            "bitchat_gcs_budget_bytes": BITCHAT_GCS_BUDGET_BYTES,
            "legacy_payload_bytes": LEGACY_BLE_PAYLOAD_BYTES,
            "naive_catch_up_full_chain_bytes": catch_up["naive_full_chain_bytes"],
            "naive_fork_full_chain_bytes": fork_hold["naive_full_chain_bytes"],
        },
        "boundary": (
            "Simulated BLE-sized transport only. Frames are fragmented by payload "
            "budget but not sent over real radio. The explicit region-hint frame "
            "localizes the current fixture; BLAKE3 and Ed25519 anchors bind the "
            "reference ledger data."
        ),
        "catch_up": catch_up,
        "fork_hold": fork_hold,
        "gates": gates,
        "generated_at": DETERMINISTIC_GENERATED_AT,
        "ok": all(gates.values()),
        "run_id": RUN_ID,
        "schema": SCHEMA,
        "sync": {
            "beacon_wire_bytes": len(
                encode_compact_beacon(
                    blake3_head=b"\x00" * 32,
                    block_count=0,
                    chain_crystal=b"\x00" * 8,
                    peer_id=b"\x00" * 8,
                    state_crystal=b"\x00" * 8,
                )
            ),
            "ble_payload_bytes": payload_bytes,
            "steps": [step.to_dict() for step in steps],
            "total_beacon_ble_packets": beacon_packets,
            "total_ble_packets": total_packets,
        },
    }


def markdown_report(report: dict[str, Any]) -> str:
    sync = report["sync"]
    catch_up = report["catch_up"]
    fork = report["fork_hold"]
    lines = [
        "# Crystal Mesh Ledger BLE Sim Transcript",
        "",
        f"Run: `{report['run_id']}`",
        f"Status: `{'passed' if report['ok'] else 'failed'}`",
        f"Generated: `{report['generated_at']}`",
        f"BLE payload budget: `{sync['ble_payload_bytes']}` bytes/packet",
        f"Compact beacon size: `{sync['beacon_wire_bytes']}` bytes",
        "",
        "## Catch-Up",
        "",
        f"- Status: `{catch_up['status']}`",
        f"- Applied blocks: `{catch_up['applied_blocks']}`",
        f"- Repair wire bytes: `{catch_up['repair_wire_bytes']}`",
        f"- Repair BLE packets: `{catch_up['repair_ble_packets']}`",
        f"- Hash manifest wire bytes: `{catch_up['hash_manifest_wire_bytes']}`",
        f"- Reference JSON repair wire bytes: `{catch_up['reference_json_repair_wire_bytes']}`",
        f"- Naive full-chain bytes: `{catch_up['naive_full_chain_bytes']}`",
        f"- Repair beats full-chain resend: `{catch_up['repair_beats_full_chain']}`",
        "",
        "## Fork Hold",
        "",
        f"- Status: `{fork['status']}`",
        f"- Hold conflict: `{fork['hold_conflict']}`",
        f"- Mismatch height: `{fork['mismatch_height']}`",
        f"- Same parent at mismatch: `{fork['same_parent']}`",
        f"- Crystal region: `{fork['crystal_region']}`",
        f"- Crystal disabled region: `{fork['crystal_disabled_region']}`",
        f"- Crystal kill test flips: `{fork['crystal_kill_test_flips']}`",
        f"- Hash-null region: `{fork['region_hint_hash_null_region']}`",
        "- Hash-null localizes identically: "
        f"`{fork['region_hint_hash_null_localizes_identically']}`",
        f"- Crystal region hint wire: `{fork['crystal_region_hint_wire_bytes']}` bytes",
        f"- Crystal region hint BLE packets: `{fork['crystal_region_hint_ble_packets']}`",
        f"- Divergence witness wire: `{fork['divergence_witness_wire_bytes']}` bytes",
        f"- Divergence witness BLE packets: `{fork['divergence_witness_ble_packets']}`",
        "- Reference JSON divergence witness wire: "
        f"`{fork['reference_json_divergence_witness_wire_bytes']}` bytes",
        f"- Block witness wire: `{fork['block_witness_wire_bytes']}` bytes",
        f"- Block witness BLE packets: `{fork['block_witness_ble_packets']}`",
        "- Reference JSON block witness wire: "
        f"`{fork['reference_json_block_witness_wire_bytes']}` bytes",
        "",
        "## Transcript",
        "",
        "| Scenario | Family | Label | Wire | BLE Pkts | OK |",
        "|---|---|---|---:|---:|---|",
    ]
    for step in sync["steps"]:
        lines.append(
            f"| {step['scenario']} | `{step['family']}` | {step['label']} | "
            f"`{step['wire_bytes']}` | `{step['ble_packets']}` | `{step['accepted']}` |"
        )
    lines.extend(
        [
            "",
            f"- Total BLE packets: `{sync['total_ble_packets']}`",
            f"- Beacon BLE packets: `{sync['total_beacon_ble_packets']}`",
            "",
            "## Gates",
            "",
        ]
    )
    for key, value in report["gates"].items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Aspirational Targets", ""])
    for key, value in report["aspirational_targets"].items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            report["boundary"],
            "",
            "This is a cloneable reference simulation, not real BLE networking, "
            "BitChat integration, production consensus, or adversarial mesh security.",
            "",
        ]
    )
    return "\n".join(lines)
