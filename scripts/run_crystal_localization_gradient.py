#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from crystal_mesh_ledger.localization import (  # noqa: E402
    build_localization_report,
    markdown_localization_report,
)

RESULTS_DIR = ROOT / "results"


def write_outputs(report: dict) -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    (RESULTS_DIR / "crystal_localization_gradient.json").write_text(
        encoded,
        encoding="utf-8",
    )
    (RESULTS_DIR / "crystal_localization_gradient.md").write_text(
        markdown_localization_report(report),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the Crystal root localization-gradient experiment",
    )
    parser.add_argument("--bins", type=int, default=16)
    parser.add_argument("--chain-length", type=int, default=128)
    parser.add_argument("--samples", type=int, default=8192)
    parser.add_argument("--write-report", action="store_true")
    args = parser.parse_args()

    report = build_localization_report(
        bins=args.bins,
        chain_length=args.chain_length,
        samples=args.samples,
    )
    if args.write_report:
        write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

