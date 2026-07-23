#!/usr/bin/env python3
"""Run the #112 periodic-source validation against an external expectation set.

The expectation input is intentionally supplied at runtime.  It lets N1-6 use
the locally archived benchmark as an audit oracle without committing benchmark
text, grades, scores, or company dossiers into the product repository.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PRODUCT = ROOT / "product"
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from data_core import (  # noqa: E402
    EASTMONEY_BUSINESS_COMPOSITION_SOURCE,
    FetchRequest,
    RecordDomain,
    SourceChoice,
    build_eastmoney_periodic_runtime,
    collect_eastmoney_earnings_calendar_async,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize_segment_name(value: str) -> str:
    return re.sub(r"[\s\-_/、，,（）()]+", "", value).lower()


def _read_expectations(path: Path) -> tuple[str, list[dict[str, Any]]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("report_period"), str):
        raise ValueError("expectation file requires report_period")
    companies = value.get("companies")
    if not isinstance(companies, list) or not companies:
        raise ValueError("expectation file requires a non-empty companies list")
    for item in companies:
        if not isinstance(item, dict) or not isinstance(item.get("ticker"), str):
            raise ValueError("each expectation requires ticker")
        names = item.get("expected_segment_names")
        if not isinstance(names, list) or not all(isinstance(name, str) and name.strip() for name in names):
            raise ValueError("each expectation requires non-empty expected_segment_names")
    return value["report_period"], companies


async def validate(report_period: str, companies: list[dict[str, Any]]) -> dict[str, Any]:
    runtime = build_eastmoney_periodic_runtime()
    company_results: list[dict[str, Any]] = []
    total_expected = 0
    total_matched = 0
    for index, company in enumerate(companies, start=1):
        ticker = company["ticker"]
        request = FetchRequest.create(
            request_id=f"n1-2-segment-validation-{index}-{ticker}",
            domain=RecordDomain.FUNDAMENTAL,
            entity_key=ticker,
            parameters={"kind": "business_composition"},
        )
        outcome = await runtime.run(
            request, (SourceChoice(EASTMONEY_BUSINESS_COMPOSITION_SOURCE, "primary"),)
        )
        expected = {_normalize_segment_name(name) for name in company["expected_segment_names"]}
        observed = {
            _normalize_segment_name(str(record.payload["segment_name"]))
            for record in outcome.records
            if record.payload.get("segment_category") == "product"
        }
        matched = len(expected.intersection(observed))
        total_expected += len(expected)
        total_matched += matched
        company_results.append(
            {
                "ticker": ticker,
                "status": outcome.status,
                "expected_segment_count": len(expected),
                "matched_segment_count": matched,
                "match_rate": matched / len(expected),
                "accepted_records": len(outcome.records),
                "raw_hashes": [
                    attempt.raw.raw_hash for attempt in outcome.attempts if attempt.raw is not None
                ],
                "source_urls": [
                    attempt.raw.source_url for attempt in outcome.attempts if attempt.raw is not None
                ],
            }
        )
    calendar = await collect_eastmoney_earnings_calendar_async(report_period, runtime=runtime)
    calendar_tickers = {record.payload["ticker"] for record in calendar.records}
    expected_tickers = {company["ticker"].upper() for company in companies}
    calendar_missing = sorted(expected_tickers - calendar_tickers)
    segment_match_rate = total_matched / total_expected if total_expected else 0.0
    return {
        "schema_version": "eastmoney-periodic-validation-v1",
        "observed_at": _utc_now(),
        "report_period": report_period,
        "companies_checked": len(companies),
        "segment_match_rate": segment_match_rate,
        "segment_threshold": 0.9,
        "calendar": {
            "status": calendar.status,
            "publishable": calendar.publishable,
            "total_pages": calendar.total_pages,
            "expected_ticker_count": len(expected_tickers),
            "missing_ticker_count": len(calendar_missing),
            "missing_tickers": calendar_missing,
            "raw_hashes": [
                attempt.raw.raw_hash
                for outcome in calendar.outcomes
                for attempt in outcome.attempts
                if attempt.raw is not None
            ],
        },
        "passed": (
            segment_match_rate >= 0.9
            and calendar.publishable
            and not calendar_missing
        ),
        "companies": company_results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expectations", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    report_period, companies = _read_expectations(args.expectations)
    result = asyncio.run(validate(report_period, companies))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(args.out)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
