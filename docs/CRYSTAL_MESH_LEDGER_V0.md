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
  compact head beacons
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

### block_repair

Ship the missing block suffix from the first missing height.

Current reference payload:

```text
canonical JSON block list
```

Boundary:

```text
This is intentionally not the final wire codec.
The next hardening target is compact binary block repair.
```

### witness_response

Return reference divergence or block witness bytes.

Current reference payloads:

```text
canonical JSON divergence witness
canonical JSON block witness
```

Boundary:

```text
This is useful for packet accounting and state-machine validation.
It is not yet a compact production witness codec.
```

## Sync State Machine

```text
Active
  receive peer beacon
  compare local head and peer head

If peer extends local:
  MissingSuffix
  request block_repair from local block_count
  validate and apply blocks
  return Active

If local extends peer:
  RemoteBehind
  do not push unless peer requests

If histories differ before the shorter chain tip:
  ConflictHeld
  request witness at first mismatch height
  do not auto-merge
  wait for policy or human resolution
```

Required fork behavior:

```text
same-prefix fork -> conflict
conflict -> zero auto-applied blocks
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

## Current Acceptance Gates

The cloneable simulation must show:

```text
compact beacon is one BLE packet
witness request is one BLE packet
catch-up applies missing blocks
catch-up repair is smaller than full-chain resend
fork returns conflict
fork does not auto-merge
mismatch height is stable
packet counts are reported
oversized witness/repair payloads are not hidden
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
```

## Next Wire Hardening

```text
compact block repair:
  binary block header
  transaction count
  typed transaction bodies
  signatures
  optional compression

compact witness response:
  height
  local block hash
  remote block hash
  parent hash
  compact proof bytes
  anchor digest

transport harness:
  two terminal peers
  then real BLE adapter
```
