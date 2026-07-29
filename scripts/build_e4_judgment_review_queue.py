#!/usr/bin/env python3
"""Build a directly reviewable queue from a real E4 judgment receipt."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product"))

from data_core.e4_judgment_review_queue import build_judgment_review_queue


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--wiring", type=Path, help="Optional full C1 wiring receipt for the same ticker")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
    ticker = str(receipt.get("ticker", ""))
    assessments = None
    if args.wiring:
        wiring = json.loads(args.wiring.read_text(encoding="utf-8"))
        row = next((item for item in wiring.get("rows", []) if str(item.get("ticker", "")).upper() == ticker.upper()), None)
        if not row:
            raise ValueError("wiring receipt has no matching ticker")
        assessments = {item["section_id"]: item for item in row["result"]["section_contract"]["sections"]}
    queue = build_judgment_review_queue(receipt, ticker=ticker, section_assessments=assessments)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(queue, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(args.out)


if __name__ == "__main__":
    main()
