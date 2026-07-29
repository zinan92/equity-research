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
from data_core.e4_official_evidence_batch import load_real_identity_tickers  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", type=Path, default=ROOT / "product" / "runtime" / "e4-financial-sequences")
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--identity-receipt", type=Path, help="Real security-master receipt; selects its first --max-tickers canonical identities")
    parser.add_argument("--max-tickers", type=int, default=100)
    args = parser.parse_args()
    if not 1 <= args.max_tickers <= 100:
        parser.error("--max-tickers must be 1-100")
    tickers = None
    if args.identity_receipt:
        tickers = load_real_identity_tickers(args.identity_receipt, required=args.max_tickers)
    kwargs = {"delay_seconds": args.delay}
    if tickers is not None:
        kwargs["tickers"] = tickers
    result = run_financial_sequence_batch(args.runtime_root, **kwargs)
    print(json.dumps({"path": result["path"], "counts": result["receipt"]["counts"], "identity_receipt": str(args.identity_receipt) if args.identity_receipt else None}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
