# CRYSTAL_MESH_LEDGER.v0

Status: reference spec draft.

## Purpose

Define a small durable-ledger frame family for local-first mesh transports.

The goal is not to replace chat. The goal is to add an optional state channel
that can survive partitions and reconnects without silently merging divergent
histories.

```text
chat layer:
  ephemeral human messages

ledger layer:
  replayable signed state events
  wallet/token payloads
  compact head beacons
  Crystal region hints
  suffix repair
  fork-hold witnesses
```

## Design Rule

```text
Crystal localizes; hash anchors prove.
```

Crystal roots are compact structural routing signals. BLAKE3 hashes and
Ed25519 signatures bind the reference ledger data.

## Frame Families

### commitment_beacon

Advertise a local ledger head without flooding the chain.

```text
magic:           4 bytes  "CB00"
schema:          1 byte
block_count:     4 bytes  uint32
chain_crystal:   8 bytes
state_crystal:   8 bytes
blake3_head:    32 bytes
peer_id:         8 bytes
```

Total: `65` bytes.

Purpose:

```text
cheap head comparison
one BLE packet at 244-byte payload budget
enough information to decide whether to request sync
```

### witness_request

Request proof or repair at a known mismatch height.

```text
magic:            4 bytes  "WR00"
mismatch_height:  4 bytes  uint32
request_nonce:    4 bytes  uint32
```

Total: `12` bytes.

### crystal_region_hint

Return a coarse Crystal routing hint for equal-length conflicting heads.

```text
magic:           4 bytes  "CH00"
schema:          1 byte
block_count:     4 bytes  uint32
split_height:    4 bytes  uint32
left_crystal:    8 bytes
right_crystal:   8 bytes
```

Total: `29` bytes.

Purpose:

```text
decide which half differs before exchanging a full hash list
make Crystal load-bearing in the fork-localization gate
fail the kill test when Crystal is disabled
```

Boundary:

```text
This is coarse left/right localization, not a full bisection protocol yet.
This is not evidence that the 8-byte root pair alone is error-locating.
```

### block_repair

Ship the missing block suffix from the first missing height.

Current reference payload:

```text
compact binary block sequence
```

Boundary:

```text
This is a reference codec, not a final transport binding.
It currently round-trips signed blocks and feeds normal block validation.
See docs/COMPACT_WIRE_CODEC_V0.md.
```

### witness_response

Return compact divergence or block witness bytes.

Current reference payloads:

```text
compact binary divergence witness
compact binary block witness
```

Boundary:

```text
The compact divergence witness carries both conflicting signed blocks.
It is still not a full production dispute game or consensus proof.
See docs/COMPACT_WIRE_CODEC_V0.md.
```

## Sync State Machine

```text
Active
  receive peer beacon
  compare local head and peer head

If peer extends local:
  MissingSuffix
  request block_repair from local block_count
  do not require a full block-hash manifest
  validate and apply blocks
  require the final head and Crystal roots to match the advertised head
  return Active

If local extends peer:
  RemoteBehind
  do not push unless peer requests

If histories differ before the shorter chain tip:
  ConflictHeld
  request crystal_region_hint
  localize coarse fork region
  request witness at first mismatch height
  do not auto-merge
  wait for policy or human resolution
```

Required fork behavior:

```text
same-prefix fork -> conflict
conflict -> zero auto-applied blocks
conflict -> Crystal region hint localizes left/right region
conflict -> disabling Crystal makes region localization fail
conflict -> mismatch height recorded
conflict -> witness request targets mismatch height
```

## BitChat Mapping

This spec is transport-neutral. A BitChat-style mapping should be optional:

```text
broadcast:
  low-TTL commitment_beacon

unicast/private channel:
  witness_request
  witness_response
  block_repair

Nostr or HTTP fallback:
  signed head manifests
  large repair/witness blobs if BLE is too thin
```

Do not require BitChat to become a blockchain application. Treat the ledger as
an optional app-layer frame family.

## Identity

Reference ledger events are signed by Ed25519 keys.

Potential BitChat integration should bind a ledger key to the chat identity by
explicit signed manifest, QR verification, or an equivalent out-of-band flow.
Do not assume BitChat transport keys and ledger validator keys are identical
until the integration code is inspected.

## Wallet And Token Payload

The reference ledger includes a deliberately small wallet/token model. Wallets
carry consensus-visible roles, and tokens carry consensus-visible classes.

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

This preserves the original Crystal wallet/token direction while keeping the BLE
mesh claim narrow. The wallet/token details are specified in
`docs/CRYSTAL_WALLETS_TOKENS_V0.md`.

## Current Acceptance Gates

The cloneable simulation must show:

```text
compact beacon is one BLE packet
Crystal region hint is one BLE packet
witness request is one BLE packet
catch-up applies missing blocks
catch-up uses zero full-hash-manifest bytes
catch-up repair is smaller than full-chain resend
fork returns conflict
Crystal localizes the fork to a coarse region
Crystal kill test flips when the root function is disabled
fork does not auto-merge
mismatch height is stable
packet counts include fragment headers
oversized witness/repair payloads are not hidden
repair/witness packet targets pass for the current fixture
```

## Localization Gradient Result

The repo also includes a root-pair localization-gradient harness:

```text
scripts/run_crystal_localization_gradient.py
results/crystal_localization_gradient.json
results/crystal_localization_gradient.md
```

Current result:

```text
balanced_crystal hamming MI:   0.036261 bits
sequential_crystal hamming MI: 0.036343 bits
truncated BLAKE3 null MI:      0.036847 bits
signal over null:              0.0 bits
```

Interpretation:

```text
The current Crystal roots do not beat the truncated-hash null as a root-pair
divergence-position signal.
```

## Non-Claims

This spec does not currently claim:

```text
real BLE networking
BitChat integration
production consensus
adversarial mesh security
financial settlement safety
global finality
Merkle replacement
root-pair error-location
```

## Next Wire Hardening

```text
compact block repair:
  implemented as reference binary codec

compact witness response:
  compact block witness implemented
  compact divergence witness implemented
  still not a production dispute game

interactive region bisection:
  use Crystal region hints recursively
  avoid full O(n) block-hash manifests
  stop at exact mismatch height

transport harness:
  two terminal peers
  then real BLE adapter
```
