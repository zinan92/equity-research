#!/usr/bin/env python3
"""Compile Tier-C Context Pack model bindings from frozen E4 receipts."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product"))
from data_core.e4_context_pack_models import compile_context_pack_models  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("partial", type=Path)
    parser.add_argument("market", type=Path)
    parser.add_argument("sell_side_matrix", type=Path)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = compile_context_pack_models(args.partial, args.market, args.sell_side_matrix, as_of=args.as_of)
    args.out.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"path": str(args.out), "counts": result["counts"], "receipt_hash": result["receipt_hash"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
