# CRYSTAL_LOCALIZATION_GRADIENT.v0

Status: deterministic negative result.

## Question

Does comparing two 8-byte roots reveal useful information about where two
histories diverged?

This is separate from the current `crystal_region_hint` frame. The region hint
is explicit: it sends left/right Crystal subroots. This experiment asks whether
the root pair alone has a position-information gradient.

## Method

The harness generates deterministic forked histories:

```text
chain_length: 128
samples: 8192
height_bins: 16
divergence_height: uniform by sample index
```

For each sample, it computes the root pair and measures:

```text
hamming distance between 8-byte roots
equal byte lanes between 8-byte roots
mutual information between divergence-height bin and root-pair signal
```

Families tested:

```text
balanced_crystal
sequential_crystal
blake3_trunc64_null
```

The truncated BLAKE3 root is the null. A load-bearing gradient should beat that
null by multiple bits, not by sampling bias.

## Result

The current run does not show a useful root-pair localization gradient.

```text
balanced_crystal hamming MI:   0.036261 bits
sequential_crystal hamming MI: 0.036343 bits
truncated BLAKE3 null MI:      0.036847 bits
signal over null:              0.0 bits
```

Generated files:

```text
results/crystal_localization_gradient.json
results/crystal_localization_gradient.md
```

## Interpretation

This is a useful negative result.

It means the current Crystal root functions should not be claimed to localize
divergence position from root-pair distance alone. In this experiment they behave
like the truncated-hash null.

The current system-level claim remains:

```text
An explicit compact region-hint frame can be used for coarse localization.
BLAKE3 and Ed25519 bind the data.
Fork-hold and manifest-free repair are tested by the ledger simulation.
```

The current digest-attribution result is also narrow:

```text
The Crystal-style digest in the region-hint fixture is not proven uniquely
necessary; a truncated-BLAKE3 hash-null digest localizes that fixture
identically.
```

The stronger hypothesis remains unproved:

```text
An 8-byte root pair alone carries multiple useful bits of divergence-position
information.
```

## Next Scientific Gates

```text
1. Treat root-pair localization gradient as negative for the current fold.
2. Keep recursive explicit region hints as the practical protocol path.
3. Only revisit the gradient if a true table-based B4 fold is restored and can
   be compared against the same truncated-hash null.
4. Do not claim root-pair error-location unless signal-over-null clears by
   multiple bits on this harness.
```
