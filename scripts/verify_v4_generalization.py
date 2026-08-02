#!/usr/bin/env python3
"""Build the M2 three-company V4 replay receipt and reader index."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product"))

from v4_dossier_replay import build_reader_index, build_replay_receipt, replay_sample  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", action="append", required=True, help="TICKER|INDUSTRY|PATH")
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    args = parser.parse_args()
    rows = []
    for value in args.sample:
        ticker, industry, raw_path = value.split("|", 2)
        rows.append(replay_sample(ticker=ticker, industry=industry, path=Path(raw_path)))
    receipt = build_replay_receipt(rows)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.index.parent.mkdir(parents=True, exist_ok=True)
    args.index.write_text(build_reader_index(receipt), encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
