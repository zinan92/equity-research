#!/usr/bin/env python3
"""Run the N3-S5 real company-dossier batch into ignored runtime storage."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product"))

from data_core.n3_dossier_batch import run_checkpointed_batch  # noqa: E402


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", type=Path, default=ROOT / "product" / "runtime" / "n3-s5-dossiers")
    parser.add_argument("--resume", type=Path, help="A prior receipt from the exact same selected citation set")
    args = parser.parse_args()
    prior = json.loads(args.resume.read_text(encoding="utf-8")) if args.resume else None
    receipt, path = run_checkpointed_batch(args.runtime_root, prior_receipt=prior)
    print(json.dumps({"path": str(path), "receipt_hash": receipt["receipt_hash"], "counts": receipt["counts"], "truth_boundary": receipt["truth_boundary"]}, ensure_ascii=False, sort_keys=True))
