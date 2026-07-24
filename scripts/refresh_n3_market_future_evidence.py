#!/usr/bin/env python3
"""Collect runtime-only N3 issuer-disclosed market-future observations."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product"))

from data_core.n3_market_future_evidence import collect_market_future_batch  # noqa: E402


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", type=Path, required=True)
    args = parser.parse_args()
    result = collect_market_future_batch(args.runtime_root)
    print(json.dumps({"path": result["path"], "counts": result["receipt"]["counts"]}, ensure_ascii=False, sort_keys=True))
