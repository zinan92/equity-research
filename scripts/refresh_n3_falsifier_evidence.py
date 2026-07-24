#!/usr/bin/env python3
"""Collect runtime-only N3 company falsifier evidence from cited official PDFs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product"))

from data_core.n3_falsifier_evidence import collect_falsifier_batch  # noqa: E402


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", type=Path, default=ROOT / "product" / "runtime" / "n3-falsifier-evidence")
    args = parser.parse_args()
    result = collect_falsifier_batch(args.runtime_root)
    print(json.dumps({"path": result["path"], "receipt_hash": result["receipt"]["receipt_hash"], "counts": result["receipt"]["counts"]}, ensure_ascii=False, sort_keys=True))
