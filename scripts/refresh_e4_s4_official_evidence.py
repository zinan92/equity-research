#!/usr/bin/env python3
"""Create a polite, runtime-only official-filing evidence batch for E4-S4."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product"))

from data_core.e4_official_evidence_batch import run_official_evidence_batch  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture one official financial-report PDF per real E4 identity")
    parser.add_argument("identity_receipt", type=Path)
    parser.add_argument("--runtime-root", type=Path, default=ROOT / "product" / "runtime" / "e4-s4-official-evidence")
    parser.add_argument("--max-tickers", type=int, default=100)
    parser.add_argument("--delay", type=float, default=1.0, help="seconds between ticker requests")
    args = parser.parse_args()
    result = run_official_evidence_batch(args.identity_receipt, args.runtime_root, max_tickers=args.max_tickers, inter_ticker_delay_seconds=args.delay)
    receipt = result["receipt"]
    print(json.dumps({"status": "captured", "path": result["path"], "counts": receipt["counts"], "truth_boundary": receipt["truth_boundary"]}, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
