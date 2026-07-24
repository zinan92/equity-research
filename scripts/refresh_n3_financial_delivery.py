#!/usr/bin/env python3
"""Collect runtime-only N3 PIT financial-delivery input receipts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product"))

from data_core.n3_financial_delivery import run_financial_delivery_batch  # noqa: E402


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", type=Path, default=ROOT / "product" / "runtime" / "n3-financial-delivery")
    parser.add_argument("--collector-timeout-seconds", type=float, default=30.0)
    args = parser.parse_args()
    result = run_financial_delivery_batch(args.runtime_root, collector_timeout_seconds=args.collector_timeout_seconds)
    print(json.dumps({"path": result["path"], "receipt_hash": result["receipt"]["receipt_hash"], "counts": result["receipt"]["counts"]}, ensure_ascii=False, sort_keys=True))
