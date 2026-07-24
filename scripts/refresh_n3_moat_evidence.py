#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product"))
from data_core.n3_moat_evidence import collect_moat_batch
if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--runtime-root", type=Path, default=ROOT / "product" / "runtime" / "n3-moat-evidence")
    result = collect_moat_batch(parser.parse_args().runtime_root)
    print(json.dumps({"path": result["path"], "receipt_hash": result["receipt"]["receipt_hash"], "counts": result["receipt"]["counts"]}, ensure_ascii=False, sort_keys=True))
