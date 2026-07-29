#!/usr/bin/env python3
"""Capture the CATL official-PDF narrative evidence receipt."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from data_core.e4_catl_financial_history import CATL_REPORTS
from data_core.e4_narrative_evidence import capture_catl_narrative, merge_narrative_receipts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("artifacts/evidence/300750.SZ-official-narrative-evidence.json"))
    parser.add_argument("--period", action="append", choices=[report.period for report in CATL_REPORTS])
    parser.add_argument("--from-receipt", action="append", type=Path, help="merge prior real bounded-run receipts")
    args = parser.parse_args()
    if args.from_receipt:
        receipt = merge_narrative_receipts(json.loads(path.read_text(encoding="utf-8")) for path in args.from_receipt)
    else:
        reports = tuple(report for report in CATL_REPORTS if not args.period or report.period in args.period)
        receipt = capture_catl_narrative(reports)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"receipt_id": receipt["receipt_id"], "reports": len(receipt["reports"]), "blocks": len(receipt["blocks"]), "out": str(args.out)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
