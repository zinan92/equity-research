#!/usr/bin/env python3
"""Run the M2 official-PDF financial-sequence batch into ignored runtime state."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product"))
from data_core.e4_financial_sequence_batch import run_financial_sequence_batch  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", type=Path, default=ROOT / "product" / "runtime" / "e4-financial-sequences")
    parser.add_argument("--delay", type=float, default=1.0)
    args = parser.parse_args()
    result = run_financial_sequence_batch(args.runtime_root, delay_seconds=args.delay)
    print(json.dumps({"path": result["path"], "counts": result["receipt"]["counts"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
