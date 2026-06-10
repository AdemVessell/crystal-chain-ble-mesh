from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from .ledger import (
    Chain,
    KeyPair,
    block_witness_payload,
    canonical_json,
    divergence_witness_payload,
    first_divergence_height,
)
from .wire import (
    BITCHAT_GCS_BUDGET_BYTES,
    DEFAULT_BLE_PAYLOAD_BYTES,
    LEGACY_BLE_PAYLOAD_BYTES,
    ble_packet_count,
    encode_compact_beacon,
    encode_witness_request,
    transmit_frame,
)

RUN_ID = "crystal_mesh_ledger_sim"
SCHEMA = "crystal.mesh_ledger.sim_report.v0"


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
    repair_blocks = source.export_blocks_from(repair_start_height)
    repair_wire = canonical_json({"blocks": repair_blocks})
    sync_result = lagging.sync_from_remote(source.manifest(), repair_blocks)
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
        "naive_full_chain_bytes": naive_full_chain_bytes,
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

    sync_result = branch_a.sync_from_remote(branch_b.manifest(), [])
    mismatch_height = first_divergence_height(branch_a.block_hashes(), branch_b.block_hashes())
    hold_conflict = sync_result.status == "conflict" and sync_result.applied_blocks == 0
    if mismatch_height is None:
        raise AssertionError("fork fixture did not diverge")

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

    divergence_wire = divergence_witness_payload(branch_a, branch_b, mismatch_height)
    _record_step(
        steps,
        accepted=True,
        detail=f"mismatch_height={mismatch_height}",
        family="witness_response",
        frame=divergence_wire,
        label="beta returns reference divergence witness",
        payload_bytes=payload_bytes,
        scenario=scenario,
    )

    block_wire = block_witness_payload(branch_b, mismatch_height)
    _record_step(
        steps,
        accepted=True,
        detail=f"height={mismatch_height}",
        family="witness_response",
        frame=block_wire,
        label="beta returns reference block witness",
        payload_bytes=payload_bytes,
        scenario=scenario,
    )

    return {
        "auto_merge_allowed": False,
        "block_witness_ble_packets": ble_packet_count(len(block_wire), payload_bytes=payload_bytes),
        "block_witness_wire_bytes": len(block_wire),
        "divergence_witness_ble_packets": ble_packet_count(
            len(divergence_wire),
            payload_bytes=payload_bytes,
        ),
        "divergence_witness_wire_bytes": len(divergence_wire),
        "hold_conflict": hold_conflict,
        "mismatch_height": mismatch_height,
        "naive_full_chain_bytes": _naive_full_chain_bytes(branch_b),
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
        "catch_up_repair_beats_full_chain": bool(catch_up["repair_beats_full_chain"]),
        "fork_held_without_auto_merge": bool(fork_hold["hold_conflict"]),
        "fork_mismatch_height_is_2": fork_hold["mismatch_height"] == 2,
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
            "budget but not sent over real radio. Crystal localizes; BLAKE3 and "
            "Ed25519 anchors bind the reference ledger data."
        ),
        "catch_up": catch_up,
        "fork_hold": fork_hold,
        "gates": gates,
        "generated_at": datetime.now(UTC).isoformat(),
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
        f"- Naive full-chain bytes: `{catch_up['naive_full_chain_bytes']}`",
        f"- Repair beats full-chain resend: `{catch_up['repair_beats_full_chain']}`",
        "",
        "## Fork Hold",
        "",
        f"- Status: `{fork['status']}`",
        f"- Hold conflict: `{fork['hold_conflict']}`",
        f"- Mismatch height: `{fork['mismatch_height']}`",
        f"- Same parent at mismatch: `{fork['same_parent']}`",
        f"- Divergence witness wire: `{fork['divergence_witness_wire_bytes']}` bytes",
        f"- Divergence witness BLE packets: `{fork['divergence_witness_ble_packets']}`",
        f"- Block witness wire: `{fork['block_witness_wire_bytes']}` bytes",
        f"- Block witness BLE packets: `{fork['block_witness_ble_packets']}`",
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
