#!/usr/bin/env python3
"""Run bounded E4 sell-side evidence collection into ignored runtime storage."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product"))
from data_core.e4_sell_side_evidence_batch import run_sell_side_evidence_batch  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("identity_receipt", type=Path); parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--max-tickers", type=int, default=100); parser.add_argument("--delay", type=float, default=1.0); parser.add_argument("--max-reports", type=int, default=1)
    args = parser.parse_args()
    result = run_sell_side_evidence_batch(args.identity_receipt, args.runtime_root, max_tickers=args.max_tickers, inter_ticker_delay_seconds=args.delay, max_reports_per_ticker=args.max_reports)
    print(json.dumps({"path": result["path"], "counts": result["receipt"]["counts"], "truth_boundary": result["receipt"]["truth_boundary"]}, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
