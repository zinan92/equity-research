#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "product"))
from data_core.e4_narrative_batch import run_narrative_batch  # noqa: E402
parser = argparse.ArgumentParser(); parser.add_argument("financial_sequence", type=Path); parser.add_argument("--runtime-root", type=Path, default=ROOT / "product" / "runtime" / "e4-l2-narratives"); parser.add_argument("--delay", type=float, default=1.0)
args = parser.parse_args(); result = run_narrative_batch(args.financial_sequence, args.runtime_root, delay_seconds=args.delay); print(json.dumps({"path": result["path"], "counts": result["receipt"]["counts"]}, ensure_ascii=False))
