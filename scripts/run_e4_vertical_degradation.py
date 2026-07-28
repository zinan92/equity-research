#!/usr/bin/env python3
"""Capture three current official filings and run B6 -> C1 -> degradation."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "product")]

from data_core.e4_page_level_filing_facts import FilingFactSource, extract_page_level_facts
from data_core.e4_vertical_degradation import E4_VERTICAL_DEGRADATION_SCHEMA_VERSION, compile_vertical_degradation
from data_core.official_filings import sync_exchange_filings

TICKERS = ("300750.SZ", "600519.SH", "000001.SZ")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", required=True, type=Path)
    args = parser.parse_args(); args.runtime_root.mkdir(parents=True, exist_ok=True)
    rows = []
    for ticker in TICKERS:
        batch = sync_exchange_filings(ticker, financial_reports_only=True, max_documents=1, max_discovery_pages=3, limit=30)
        if not batch.documents:
            rows.append({"ticker": ticker, "status": "missing", "reason": "no_official_financial_report"}); continue
        document_id, outcome = next(iter(batch.documents.items()))
        attempt = next((item for item in reversed(outcome.attempts) if item.raw and item.fetched), None)
        record = outcome.records[0] if outcome.records else None
        if attempt is None or record is None:
            rows.append({"ticker": ticker, "status": "missing", "reason": "official_document_raw_capture_missing"}); continue
        raw = attempt.fetched.body; raw_hash = hashlib.sha256(raw).hexdigest()
        if raw_hash != attempt.raw.raw_hash:
            rows.append({"ticker": ticker, "status": "missing", "reason": "official_document_hash_mismatch"}); continue
        published = str(record.payload.get("published_at") or "")[:4]
        title = str(record.payload.get("title") or "")
        period = (published + "年度") if "年度报告" in title else (published + "年第一季度")
        source = FilingFactSource(ticker, str(document_id), raw_hash, attempt.raw.source_url, period)
        facts = extract_page_level_facts(source, raw)
        if not facts:
            rows.append({"ticker": ticker, "status": "missing", "reason": "no_consolidated_statement_page_fact"}); continue
        rows.append({"ticker": ticker, "status": "available", "result": compile_vertical_degradation(
            ticker, facts, known_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        )})
    payload = {"schema_version": E4_VERTICAL_DEGRADATION_SCHEMA_VERSION, "data_kind": "real", "rows": rows}
    path = args.runtime_root / "vertical-degradation.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
