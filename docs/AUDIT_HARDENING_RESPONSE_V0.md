# AUDIT_HARDENING_RESPONSE.v0

Status: local hardening response after two external model audits.

## Accepted Findings

The audits found real issues in the first public packet:

```text
Crystal roots were carried but not load-bearing in sync decisions.
Catch-up depended on an uncounted O(n) block-hash manifest.
Fragment accounting ignored the 4-byte fragment header.
Odd-leaf Crystal folding duplicated the final leaf.
Witness and repair payloads are still oversized canonical JSON.
```

These were valid findings. The repo should not claim full Crystal-localized mesh
sync from the first packet.

## Fixed In This Hardening Pass

```text
fragment accounting:
  4-byte fragment headers now fit inside the 244-byte payload budget
  tests assert emitted fragments never exceed the payload budget

catch-up:
  sync_from_remote_head applies a missing suffix from the advertised head
  no full block-hash manifest is required for catch-up
  final head, chain Crystal, and state Crystal must match the advertised head

fork hold:
  same-height differing heads still return conflict
  no auto-merge path was added

Crystal load-bearing gate:
  crystal_region_hint is a 29-byte one-packet frame
  it compares left/right Crystal region roots for equal-length conflicting heads
  the simulation localizes the current fork to the right region
  disabling Crystal makes that region-localization gate fail

localization-gradient harness:
  root-pair divergence-position signal is tested against truncated BLAKE3
  current balanced and sequential Crystal roots do not beat the null
  this negative is published in results/crystal_localization_gradient.md

Crystal fold:
  odd leaves are promoted instead of duplicated
  tests reject the previous [A,B,C] vs [A,B,C,C] ambiguity

compact codecs:
  block repair now uses a compact binary block sequence
  block witness now uses a compact binary block witness
  divergence witness now carries both conflicting compact blocks
  the prior packet targets now pass in the current fixture
```

## Current Result

The current claim is now narrower and stronger:

```text
Crystal provides a coarse region-localization hint.
BLAKE3 and Ed25519 still bind and prove the ledger data.
Catch-up repair no longer relies on a full hash-list manifest.
Repair and witness payloads no longer rely on canonical JSON in the measured sim.
Root-pair distance alone is not claimed as an error-locating signal.
```

This is still not a full production sync protocol.

## Still Open

```text
recursive Crystal bisection to exact mismatch height
witness request authentication / replay binding
true B4/table-fold comparison if the hardware-floor claim is revisited
real BLE transport
packet loss, reorder, duplicate, and partition tests
adversarial mesh security
production consensus or financial settlement safety
```

## Reviewer Guidance

The right hostile check is now:

```text
Run the simulation.
Confirm hash_manifest_wire_bytes is 0.
Confirm crystal_region is right.
Confirm crystal_disabled_region is none.
Confirm crystal_kill_test_flips is true.
Confirm root-pair localization gradient does not beat the hash null.
Confirm all emitted fragments are <=244 bytes.
Confirm repair_le_5_packets, block_witness_le_3_packets, and
divergence_witness_le_3_packets are true for the current fixture.
```
