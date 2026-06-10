# CrystalChain BLE Mesh

Reference packet for a local-first CrystalChain mesh ledger over BLE-sized
transports.

This repository tests one narrow claim:

```text
offline/local-first peers can advertise compact heads, detect divergence, hold
conflict, and request only the needed repair segment under BLE-style packet
budgets.
```

It is designed as a public, cloneable next step after the CrystalDefi open-core
research packet.

## Why This Exists

CrystalDefi proved useful discipline:

```text
Crystal localizes; hash anchors prove.
```

That rule fits BLE/local mesh better than Ethereum rollup fraud proofs. Mesh
peers have tiny packet budgets, partial views, partition/reconnect behavior, and
no room for heavyweight dispute games. A compact head beacon plus targeted
repair is a more natural product test.

## What This Repo Contains

```text
crystal_mesh_ledger/
  minimal signed reference ledger
  BLAKE3 state/block anchors
  8-byte Crystal-style structural roots
  compact BLE frame accounting

scripts/run_crystal_mesh_ledger_sim.py
  cloneable simulation runner

docs/CRYSTAL_MESH_LEDGER_V0.md
  frame layouts, state machine, BitChat mapping, and non-claims

results/
  generated JSON and Markdown transcripts
```

## Quick Start

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
make test
make sim
```

Generated files:

```text
results/crystal_mesh_ledger_sim.json
results/crystal_mesh_ledger_sim.md
```

## Current Evidence

The simulation covers:

```text
catch-up:
  peer A is behind
  peer B advertises a newer head
  A requests only the missing suffix
  A applies the repair and reaches B's head

fork-hold:
  peers share a prefix
  both seal conflicting blocks at the same height
  sync returns conflict
  no automatic merge occurs
  witness request targets the mismatch height
```

The report includes:

```text
65-byte compact beacons
12-byte witness requests
BLE packet counts at 244-byte payload budget
repair-vs-full-chain byte comparison
divergence and block witness byte counts
failed aspirational targets when payloads are still too large
```

## BitChat Relationship

BitChat-style transports are a good target because they already provide:

```text
Bluetooth mesh transport
multi-hop relay
fragmentation
private channels
internet fallback through Nostr
```

This repo does not integrate with BitChat yet.

The intended shape is an optional application-layer ledger frame:

```text
BitChat carries bytes.
CrystalChain interprets ledger frames.
Crystal routes repair.
BLAKE3 and Ed25519 bind the data.
```

## Non-Claims

This repository does not prove:

```text
real BLE networking
BitChat integration
production mesh consensus
adversarial mesh security
financial settlement safety
Merkle replacement
global blockchain finality
```

## Next Gates

```text
1. compact block-repair codec
2. compact divergence-witness codec
3. two-terminal peer demo
4. real BLE adapter
5. optional BitChat extension proposal
```

Do not pitch this as a blockchain replacement. Pitch it as:

```text
offline durable state repair under BLE packet limits
```
