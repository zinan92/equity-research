#!/usr/bin/env python3
"""Merge bounded one-issuer official sequence receipts by period."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product"))

from data_core.v4_n1_official_evidence import merge_financial_receipts  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    receipts = [json.loads(path.read_text(encoding="utf-8")) for path in args.inputs]
    merged = merge_financial_receipts(receipts)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ticker": merged["cohort"][0], "out": str(args.out), "counts": merged["counts"], "receipt_hash": merged["receipt_hash"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
