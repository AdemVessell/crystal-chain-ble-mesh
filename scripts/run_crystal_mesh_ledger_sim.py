#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from crystal_mesh_ledger import (  # noqa: E402
    DEFAULT_BLE_PAYLOAD_BYTES,
    build_report,
    markdown_report,
)

RESULTS_DIR = ROOT / "results"


def write_reports(report: dict) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    (RESULTS_DIR / "crystal_mesh_ledger_sim.json").write_text(encoded, encoding="utf-8")
    (RESULTS_DIR / "crystal_mesh_ledger_sim.md").write_text(
        markdown_report(report),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Crystal mesh ledger BLE simulation")
    parser.add_argument("--ble-payload-bytes", type=int, default=DEFAULT_BLE_PAYLOAD_BYTES)
    parser.add_argument("--write-report", action="store_true")
    args = parser.parse_args()

    report = build_report(payload_bytes=args.ble_payload_bytes)
    if args.write_report:
        write_reports(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
