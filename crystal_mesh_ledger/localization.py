from __future__ import annotations

import math
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

import blake3

from .ledger import _balanced_crystal_root, _fold_byte, _leaf_root, canonical_json

RootFn = Callable[[list[bytes]], bytes]


def _digest(label: str) -> bytes:
    return blake3.blake3(label.encode("utf-8")).digest()


def _root_bytes(root: tuple[int, ...]) -> bytes:
    return bytes(root)


def balanced_crystal_root_bytes(leaves: list[bytes]) -> bytes:
    return _root_bytes(_balanced_crystal_root(leaves))


def sequential_crystal_root_bytes(leaves: list[bytes]) -> bytes:
    root = (0, 0, 0, 0, 0, 0, 0, 0)
    for leaf in leaves:
        leaf_root = _leaf_root(leaf)
        root = tuple(_fold_byte(root[index], leaf_root[index], index) for index in range(8))
    return _root_bytes(root)


def blake3_trunc64_root_bytes(leaves: list[bytes]) -> bytes:
    if not leaves:
        return b"\x00" * 8
    payload = canonical_json(
        {
            "leaf_count": len(leaves),
            "leaves": [leaf.hex() for leaf in leaves],
        }
    )
    return blake3.blake3(payload).digest()[:8]


def hamming_bits(left: bytes, right: bytes) -> int:
    if len(left) != len(right):
        raise ValueError("roots must have equal length")
    return sum((a ^ b).bit_count() for a, b in zip(left, right, strict=True))


def equal_lanes(left: bytes, right: bytes) -> int:
    if len(left) != len(right):
        raise ValueError("roots must have equal length")
    return sum(a == b for a, b in zip(left, right, strict=True))


def mutual_information_bits(xs: Iterable[Any], ys: Iterable[Any]) -> float:
    pairs = list(zip(xs, ys, strict=True))
    if not pairs:
        return 0.0
    n = len(pairs)
    x_counts = Counter(x for x, _y in pairs)
    y_counts = Counter(y for _x, y in pairs)
    pair_counts = Counter(pairs)
    mi = 0.0
    for (x, y), count in pair_counts.items():
        p_xy = count / n
        p_x = x_counts[x] / n
        p_y = y_counts[y] / n
        mi += p_xy * math.log2(p_xy / (p_x * p_y))
    return mi


@dataclass(frozen=True)
class LocalizationSample:
    divergence_height: int
    height_bin: int
    hamming_bits: int
    equal_lanes: int


def _height_bin(divergence_height: int, *, bins: int, chain_length: int) -> int:
    return min((divergence_height * bins) // chain_length, bins - 1)


def _sample_chains(*, chain_length: int, sample_index: int) -> tuple[list[bytes], list[bytes], int]:
    divergence_height = sample_index % chain_length
    base = [
        _digest(f"crystal-localization-gradient-v0|{sample_index}|base|{height}")
        for height in range(chain_length)
    ]
    fork = [
        base[height]
        if height < divergence_height
        else _digest(f"crystal-localization-gradient-v0|{sample_index}|fork|{height}")
        for height in range(chain_length)
    ]
    return base, fork, divergence_height


def family_samples(
    root_fn: RootFn,
    *,
    bins: int,
    chain_length: int,
    samples: int,
) -> list[LocalizationSample]:
    output: list[LocalizationSample] = []
    for sample_index in range(samples):
        base, fork, divergence_height = _sample_chains(
            chain_length=chain_length,
            sample_index=sample_index,
        )
        left = root_fn(base)
        right = root_fn(fork)
        output.append(
            LocalizationSample(
                divergence_height=divergence_height,
                equal_lanes=equal_lanes(left, right),
                hamming_bits=hamming_bits(left, right),
                height_bin=_height_bin(
                    divergence_height,
                    bins=bins,
                    chain_length=chain_length,
                ),
            )
        )
    return output


def summarize_samples(samples: list[LocalizationSample]) -> dict[str, Any]:
    if not samples:
        raise ValueError("samples must not be empty")
    bins = sorted({sample.height_bin for sample in samples})
    hamming_by_bin = {
        str(bin_id): round(
            sum(sample.hamming_bits for sample in samples if sample.height_bin == bin_id)
            / sum(1 for sample in samples if sample.height_bin == bin_id),
            4,
        )
        for bin_id in bins
    }
    equal_lanes_by_bin = {
        str(bin_id): round(
            sum(sample.equal_lanes for sample in samples if sample.height_bin == bin_id)
            / sum(1 for sample in samples if sample.height_bin == bin_id),
            4,
        )
        for bin_id in bins
    }
    height_bins = [sample.height_bin for sample in samples]
    hamming_values = [sample.hamming_bits for sample in samples]
    equal_lane_values = [sample.equal_lanes for sample in samples]
    return {
        "equal_lanes_by_height_bin": equal_lanes_by_bin,
        "mi_bits_equal_lanes": round(
            mutual_information_bits(height_bins, equal_lane_values),
            6,
        ),
        "mi_bits_hamming": round(
            mutual_information_bits(height_bins, hamming_values),
            6,
        ),
        "mean_equal_lanes": round(sum(equal_lane_values) / len(samples), 4),
        "mean_hamming_bits": round(sum(hamming_values) / len(samples), 4),
        "mean_hamming_bits_by_height_bin": hamming_by_bin,
    }


def build_localization_report(
    *,
    bins: int = 16,
    chain_length: int = 128,
    samples: int = 8192,
) -> dict[str, Any]:
    if chain_length < 2:
        raise ValueError("chain_length must be at least 2")
    if bins < 2:
        raise ValueError("bins must be at least 2")
    if samples < chain_length:
        raise ValueError("samples must be at least chain_length")

    families: dict[str, RootFn] = {
        "balanced_crystal": balanced_crystal_root_bytes,
        "blake3_trunc64_null": blake3_trunc64_root_bytes,
        "sequential_crystal": sequential_crystal_root_bytes,
    }
    family_results = {
        name: summarize_samples(
            family_samples(
                root_fn,
                bins=bins,
                chain_length=chain_length,
                samples=samples,
            )
        )
        for name, root_fn in families.items()
    }
    null_mi = family_results["blake3_trunc64_null"]["mi_bits_hamming"]
    best_family = max(
        family_results,
        key=lambda name: family_results[name]["mi_bits_hamming"],
    )
    best_mi = family_results[best_family]["mi_bits_hamming"]
    return {
        "boundary": (
            "This measures root-pair distance as a possible divergence-position signal. "
            "It does not test recursive region hints, compact codecs, real BLE, or security."
        ),
        "chain_length": chain_length,
        "families": family_results,
        "height_bins": bins,
        "interpretation": {
            "best_family_by_hamming_mi": best_family,
            "best_hamming_mi_bits": best_mi,
            "null_hamming_mi_bits": null_mi,
            "signal_over_null_bits": round(best_mi - null_mi, 6),
            "threshold_note": (
                "A useful routing signal would need to clear the truncated-hash null by "
                "multiple bits, not merely sampling bias."
            ),
        },
        "run_id": "crystal_localization_gradient_v0",
        "samples": samples,
        "schema": "crystal.mesh_ledger.localization_gradient.v0",
    }


def markdown_localization_report(report: dict[str, Any]) -> str:
    lines = [
        "# Crystal Localization Gradient",
        "",
        f"Run: `{report['run_id']}`",
        f"Samples: `{report['samples']}`",
        f"Chain length: `{report['chain_length']}`",
        f"Height bins: `{report['height_bins']}`",
        "",
        "## Mutual Information",
        "",
        "| Family | MI hamming bits | MI equal-lanes bits | Mean hamming | Mean equal lanes |",
        "|---|---:|---:|---:|---:|",
    ]
    for family, values in report["families"].items():
        lines.append(
            f"| `{family}` | `{values['mi_bits_hamming']}` | "
            f"`{values['mi_bits_equal_lanes']}` | `{values['mean_hamming_bits']}` | "
            f"`{values['mean_equal_lanes']}` |"
        )
    interpretation = report["interpretation"]
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            f"- Best family: `{interpretation['best_family_by_hamming_mi']}`",
            f"- Best hamming MI: `{interpretation['best_hamming_mi_bits']}` bits",
            f"- Truncated-hash null hamming MI: `{interpretation['null_hamming_mi_bits']}` bits",
            f"- Signal over null: `{interpretation['signal_over_null_bits']}` bits",
            "",
            "## Boundary",
            "",
            report["boundary"],
            "",
        ]
    )
    return "\n".join(lines)
