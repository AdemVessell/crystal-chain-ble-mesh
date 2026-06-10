# CrystalChain BLE Mesh

Reference packet for a local-first CrystalChain mesh ledger over BLE-sized
transports.

This repository tests one narrow claim:

```text
offline/local-first peers can advertise compact heads, detect divergence, hold
conflict, use a compact Crystal region hint, and repair a missing suffix under
BLE-style packet budgets.
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
  wallet roles and token classes
  BLAKE3 state/block anchors
  8-byte Crystal-style structural roots
  compact binary repair/witness codecs
  compact BLE frame accounting

scripts/run_crystal_mesh_ledger_sim.py
  cloneable simulation runner

docs/CRYSTAL_MESH_LEDGER_V0.md
  frame layouts, state machine, BitChat mapping, and non-claims

docs/CRYSTAL_WALLETS_TOKENS_V0.md
  founder/builder wallet roles, token classes, and token non-claims

docs/AUDIT_HARDENING_RESPONSE_V0.md
  accepted audit findings, fixes, and still-open hardening gaps

docs/CRYSTAL_LOCALIZATION_GRADIENT_V0.md
  root-pair divergence-position signal test against truncated-hash null

docs/COMPACT_WIRE_CODEC_V0.md
  binary repair/witness codec layout and current packet results

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
  A requests the missing suffix without a full hash-list manifest
  A applies the repair and reaches B's head

fork-hold:
  peers share a prefix
  both seal conflicting blocks at the same height
  sync returns conflict
  a 29-byte Crystal region hint localizes the fork to the right half
  disabling Crystal makes that region-localization gate fail
  no automatic merge occurs
  witness request targets the mismatch height
```

The report includes:

```text
65-byte compact beacons
29-byte Crystal region hints
12-byte witness requests
BLE packet counts at 244-byte payload budget, including 4-byte fragment headers
zero hash-manifest bytes on catch-up
repair-vs-full-chain byte comparison
divergence and block witness byte counts
root-pair localization-gradient result against a truncated-hash null
aspirational packet targets now passing for the current fixture
```

The current localization-gradient result is negative: the tested Crystal root
functions do not beat the truncated-hash null as a root-pair position signal.
The load-bearing Crystal claim in this packet is the explicit 29-byte region
hint, not hidden error-location in the 8-byte root pair.

## Wallet And Token Scope

The runnable reference ledger includes signed wallet and token state:

```text
wallet roles:
  user
  founder
  builder
  gateway
  watcher

token classes:
  mesh_credit
  founder_marker
  builder_marker
  receipt
```

This is enough to test the original Crystal wallet/token shape as replayable mesh
ledger state. It is not a launched coin, fungible balance system, investment
product, or production settlement layer. See
[`docs/CRYSTAL_WALLETS_TOKENS_V0.md`](docs/CRYSTAL_WALLETS_TOKENS_V0.md).

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
1. recursive region bisection beyond the current left/right hint
2. randomized fork/churn property scenarios
3. two-terminal peer demo
4. real BLE adapter
5. optional BitChat extension proposal
```

Do not pitch this as a blockchain replacement. Pitch it as:

```text
offline durable state repair under BLE packet limits
```
