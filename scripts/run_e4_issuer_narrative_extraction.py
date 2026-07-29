#!/usr/bin/env python3
"""Capture one issuer's latest official annual-report narrative receipt."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product"))

from data_core.e4_catl_financial_history import OfficialReport  # noqa: E402
from data_core.e4_narrative_evidence import capture_issuer_narrative  # noqa: E402
from run_e4_model_judgments import _financial_facts, _verify_receipt  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("financial_receipt", type=Path)
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    ticker = args.ticker.upper()
    source_bytes = args.financial_receipt.read_bytes()
    financial = json.loads(source_bytes)
    _verify_receipt(financial, kind="financial")
    facts = _financial_facts(financial, ticker)
    annual = [
        fact
        for fact in facts
        if str(fact.get("report_period") or "").endswith("FY")
        and str(fact.get("source_url") or "").startswith(
            "https://static.cninfo.com.cn/"
        )
        and fact.get("document_id")
        and fact.get("raw_hash")
    ]
    if not annual:
        raise ValueError("no official annual-report identity for requested ticker")
    latest_period = max(str(fact["report_period"]) for fact in annual)
    selected = next(
        fact
        for fact in annual
        if str(fact["report_period"]) == latest_period
    )
    document_id = str(selected["document_id"])
    report = OfficialReport(
        latest_period,
        document_id,
        str(selected["source_url"]),
        ticker=ticker,
    )
    receipt = capture_issuer_narrative(
        ticker,
        [report],
        expected_raw_hashes={document_id: str(selected["raw_hash"])},
        source_financial_receipt_sha256=hashlib.sha256(source_bytes).hexdigest(),
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "out": str(args.out),
                "receipt_id": receipt["receipt_id"],
                "ticker": ticker,
                "period": latest_period,
                "reports": receipt["reports"],
                "coverage": receipt["coverage"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
