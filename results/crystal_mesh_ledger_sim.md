# Crystal Mesh Ledger BLE Sim Transcript

Run: `crystal_mesh_ledger_sim`
Status: `passed`
Generated: `2026-06-10T20:00:45.648750+00:00`
BLE payload budget: `244` bytes/packet
Compact beacon size: `65` bytes

## Catch-Up

- Status: `applied_blocks`
- Applied blocks: `2`
- Repair wire bytes: `677`
- Repair BLE packets: `3`
- Hash manifest wire bytes: `0`
- Reference JSON repair wire bytes: `2288`
- Naive full-chain bytes: `5047`
- Repair beats full-chain resend: `True`

## Fork Hold

- Status: `conflict`
- Hold conflict: `True`
- Mismatch height: `2`
- Same parent at mismatch: `True`
- Crystal region: `right`
- Crystal disabled region: `none`
- Crystal kill test flips: `True`
- Crystal region hint wire: `29` bytes
- Crystal region hint BLE packets: `1`
- Divergence witness wire: `686` bytes
- Divergence witness BLE packets: `3`
- Reference JSON divergence witness wire: `2635` bytes
- Block witness wire: `344` bytes
- Block witness BLE packets: `2`
- Reference JSON block witness wire: `1361` bytes

## Transcript

| Scenario | Family | Label | Wire | BLE Pkts | OK |
|---|---|---|---:|---:|---|
| catch_up | `commitment_beacon` | alpha advertises lagging head | `65` | `1` | `True` |
| catch_up | `commitment_beacon` | beta advertises extended head | `65` | `1` | `True` |
| catch_up | `block_repair` | beta ships missing block suffix | `677` | `3` | `True` |
| fork_hold | `commitment_beacon` | alpha beacon at fork head | `65` | `1` | `True` |
| fork_hold | `commitment_beacon` | beta beacon at fork head | `65` | `1` | `True` |
| fork_hold | `crystal_region_hint` | beta returns Crystal region hint | `29` | `1` | `True` |
| fork_hold | `witness_request` | alpha requests divergence witness | `12` | `1` | `True` |
| fork_hold | `witness_response` | beta returns compact divergence witness | `686` | `3` | `True` |
| fork_hold | `witness_response` | beta returns compact block witness | `344` | `2` | `True` |

- Total BLE packets: `14`
- Beacon BLE packets: `4`

## Gates

- all_steps_accepted: `True`
- beacons_are_one_packet: `True`
- catch_up_applied_blocks: `True`
- catch_up_heads_match: `True`
- catch_up_uses_no_hash_manifest: `True`
- catch_up_repair_beats_full_chain: `True`
- crystal_kill_test_flips: `True`
- crystal_region_localizes_fork: `True`
- fork_held_without_auto_merge: `True`
- fork_mismatch_height_is_2: `True`
- region_hint_is_one_packet: `True`
- witness_request_is_one_packet: `True`

## Aspirational Targets

- block_witness_le_3_packets: `True`
- divergence_witness_le_3_packets: `True`
- repair_le_5_packets: `True`

## Boundary

Simulated BLE-sized transport only. Frames are fragmented by payload budget but not sent over real radio. Crystal localizes; BLAKE3 and Ed25519 anchors bind the reference ledger data.

This is a cloneable reference simulation, not real BLE networking, BitChat integration, production consensus, or adversarial mesh security.
