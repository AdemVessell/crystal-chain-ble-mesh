# COMPACT_WIRE_CODEC.v0

Status: reference binary codec.

## Purpose

Replace the first packet's canonical JSON repair and witness payloads with
measured binary frames that round-trip back into normal ledger validation.

This codec is not a final BLE transport binding. It is the current executable
wire format used by the simulation.

## Implemented Frames

```text
compact block:
  magic:                4 bytes  "BK00"
  schema:               1 byte
  height:               4 bytes
  parent_hash:          32 bytes
  pre_state_hash:       32 bytes
  post_state_hash:      32 bytes
  post_state_crystal:   8 bytes
  producer_public_key:  32 bytes
  producer_signature:   64 bytes
  tx_count:             1 byte
  typed transactions:   variable
```

Transaction payloads keep enough data to reconstruct the signed transaction
payload and recompute the transaction id. Transaction `pre_state_hash` is
inherited from the block pre-state in this reference codec.

```text
block repair:
  magic:      4 bytes  "BR00"
  schema:     1 byte
  count:      2 bytes
  blocks:     length-prefixed compact blocks

block witness:
  magic:      4 bytes  "BW00"
  schema:     1 byte
  block:      length-prefixed compact block

divergence witness:
  magic:       4 bytes  "DW00"
  schema:      1 byte
  height:      4 bytes
  same_parent: 1 byte
  local:       length-prefixed compact block
  remote:      length-prefixed compact block
```

## Current Packet Results

At a `244` byte BLE payload budget with a `4` byte fragment header included:

```text
repair:             677 bytes / 3 packets
block witness:      344 bytes / 2 packets
divergence witness: 686 bytes / 3 packets
```

The previous JSON reference sizes remain in the report for comparison:

```text
repair JSON:             2288 bytes
block witness JSON:      1361 bytes
divergence witness JSON: 2635 bytes
```

## Non-Claims

```text
not a final production codec
not authenticated witness-request/response binding
not a complete dispute game
not real BLE transport
not compression-optimal
```

## Next Codec Gates

```text
1. Bind witness responses to request nonce and peer/session context.
2. Add malformed-frame tests and fuzz/property cases.
3. Decide whether multi-transaction blocks need per-transaction pre-state fields
   or a stricter block construction rule.
4. Measure codec behavior across randomized fork heights and chain sizes.
```

