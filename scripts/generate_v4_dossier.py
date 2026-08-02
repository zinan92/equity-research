#!/usr/bin/env python3
"""Unified V4 whole-dossier generator/package entry point."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product"))

from v4_dossier_generator import generate_v4_dossier  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("ticker")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--completed-markdown", type=Path)
    parser.add_argument("--evidence-manifest", type=Path)
    parser.add_argument("--official-sample", type=Path)
    parser.add_argument("--narrative-receipt", type=Path)
    parser.add_argument("--financial-receipt", type=Path)
    parser.add_argument("--round7-dossier", type=Path, help="canonical Round 7 receipt JSON")
    parser.add_argument("--round7-markdown", type=Path, help="canonical Round 7 Markdown")
    parser.add_argument("--round7-profile", type=Path, help="canonical issuer profile")
    args = parser.parse_args()
    receipt = generate_v4_dossier(
        ticker=args.ticker,
        output_dir=args.output_dir,
        completed_markdown_path=args.completed_markdown,
        evidence_manifest_path=args.evidence_manifest,
        official_sample_path=args.official_sample,
        narrative_receipt_path=args.narrative_receipt,
        financial_receipt_path=args.financial_receipt,
        round7_dossier_path=args.round7_dossier,
        round7_markdown_path=args.round7_markdown,
        round7_profile_path=args.round7_profile,
    )
    print(receipt["output_path"])
    print(receipt["generation_mode"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
