# Crystal Localization Gradient

Run: `crystal_localization_gradient_v0`
Samples: `8192`
Chain length: `128`
Height bins: `16`

## Mutual Information

| Family | MI hamming bits | MI equal-lanes bits | Mean hamming | Mean equal lanes |
|---|---:|---:|---:|---:|
| `balanced_crystal` | `0.036261` | `0.017352` | `31.9021` | `0.0632` |
| `blake3_trunc64_null` | `0.036847` | `0.003361` | `31.9766` | `0.0326` |
| `sequential_crystal` | `0.036343` | `0.002103` | `31.9705` | `0.028` |

## Interpretation

- Best family: `blake3_trunc64_null`
- Best hamming MI: `0.036847` bits
- Truncated-hash null hamming MI: `0.036847` bits
- Signal over null: `0.0` bits

## Boundary

This measures root-pair distance as a possible divergence-position signal. It does not test recursive region hints, compact codecs, real BLE, or security.
