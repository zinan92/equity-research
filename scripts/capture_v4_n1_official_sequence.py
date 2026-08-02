#!/usr/bin/env python3
"""Capture a bounded real official filing sequence for one V4 issuer.

The output is runtime-only.  It contains immutable document/page identities and
typed gaps, never raw PDFs or generated judgment prose.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product"))

from data_core.official_filings import OfficialHttpTransport  # noqa: E402
from data_core.v4_n1_official_evidence import PERIODS, capture_financial_periods  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--period", action="append", dest="periods")
    args = parser.parse_args()

    periods = tuple(args.periods or PERIODS)
    transport = OfficialHttpTransport(
        timeout_seconds=5.0,
        max_attempts=3,
        base_delay_seconds=0.2,
        max_delay_seconds=1.0,
        jitter=lambda _low, _high: 0.0,
        min_request_interval_seconds=0.5,
    )
    receipt = capture_financial_periods(args.ticker, periods, transport=transport)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    path = args.out_dir / f"financial-sequence-{receipt['receipt_hash'][:16]}.json"
    path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.out_dir / "financial-sequence-latest.json").write_text(
        json.dumps({"receipt": path.name, "receipt_hash": receipt["receipt_hash"], "ticker": args.ticker.upper()}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"ticker": args.ticker.upper(), "path": str(path), "counts": receipt["counts"], "receipt_hash": receipt["receipt_hash"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
