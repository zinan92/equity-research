#!/usr/bin/env python3
"""Build CATL/Moutai V4 outputs from official-source evidence packages."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product"))

from v4_official_adapter import adapt_official_sample, write_official_outputs  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--ticker", action="append", required=True)
    args = parser.parse_args()
    rows = {}
    for ticker in args.ticker:
        rows[ticker] = adapt_official_sample(
            ticker=ticker,
            sample_path=ROOT / "docs" / "dossier-production" / "samples" / f"{ticker}-v1.md",
            narrative_receipt_path=ROOT / "artifacts" / "evidence" / f"{ticker}-official-narrative-evidence.json",
            financial_receipt_path=ROOT / "artifacts" / "evidence" / f"{ticker}-financial-page-evidence.json",
        )
    receipt = write_official_outputs(rows, args.output_dir)
    print(receipt)
    return 0 if receipt["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
