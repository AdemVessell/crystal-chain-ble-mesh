# Crystal Mesh Ledger BLE Sim Transcript

Run: `crystal_mesh_ledger_sim`
Status: `passed`
Generated: `2026-06-10T19:02:39.529578+00:00`
BLE payload budget: `244` bytes/packet
Compact beacon size: `65` bytes

## Catch-Up

- Status: `applied_blocks`
- Applied blocks: `2`
- Repair wire bytes: `2260`
- Repair BLE packets: `10`
- Naive full-chain bytes: `4956`
- Repair beats full-chain resend: `True`

## Fork Hold

- Status: `conflict`
- Hold conflict: `True`
- Mismatch height: `2`
- Same parent at mismatch: `True`
- Divergence witness wire: `2635` bytes
- Divergence witness BLE packets: `11`
- Block witness wire: `1361` bytes
- Block witness BLE packets: `6`

## Transcript

| Scenario | Family | Label | Wire | BLE Pkts | OK |
|---|---|---|---:|---:|---|
| catch_up | `commitment_beacon` | alpha advertises lagging head | `65` | `1` | `True` |
| catch_up | `commitment_beacon` | beta advertises extended head | `65` | `1` | `True` |
| catch_up | `block_repair` | beta ships missing block suffix | `2260` | `10` | `True` |
| fork_hold | `commitment_beacon` | alpha beacon at fork head | `65` | `1` | `True` |
| fork_hold | `commitment_beacon` | beta beacon at fork head | `65` | `1` | `True` |
| fork_hold | `witness_request` | alpha requests divergence witness | `12` | `1` | `True` |
| fork_hold | `witness_response` | beta returns reference divergence witness | `2635` | `11` | `True` |
| fork_hold | `witness_response` | beta returns reference block witness | `1361` | `6` | `True` |

- Total BLE packets: `32`
- Beacon BLE packets: `4`

## Gates

- all_steps_accepted: `True`
- beacons_are_one_packet: `True`
- catch_up_applied_blocks: `True`
- catch_up_heads_match: `True`
- catch_up_repair_beats_full_chain: `True`
- fork_held_without_auto_merge: `True`
- fork_mismatch_height_is_2: `True`
- witness_request_is_one_packet: `True`

## Aspirational Targets

- block_witness_le_3_packets: `False`
- divergence_witness_le_3_packets: `False`
- repair_le_5_packets: `False`

## Boundary

Simulated BLE-sized transport only. Frames are fragmented by payload budget but not sent over real radio. Crystal localizes; BLAKE3 and Ed25519 anchors bind the reference ledger data.

This is a cloneable reference simulation, not real BLE networking, BitChat integration, production consensus, or adversarial mesh security.
