#!/usr/bin/env python3
"""Optional live contract probe for #112; it is intentionally not a CI test.

Run one company F10 fetch and one complete calendar-period fetch.  The script
writes a receipt for both success and failure; a provider outage returns zero
unless ``--strict`` is requested, so CI never treats provider availability as
product correctness.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRODUCT = ROOT / "product"
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from data_core import (  # noqa: E402
    EASTMONEY_BUSINESS_COMPOSITION_SOURCE,
    FetchRequest,
    MemoryAttemptSink,
    RecordDomain,
    SourceChoice,
    build_eastmoney_periodic_runtime,
    collect_eastmoney_earnings_calendar_async,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


async def probe(ticker: str, report_period: str) -> dict[str, object]:
    sink = MemoryAttemptSink()
    runtime = build_eastmoney_periodic_runtime(authority_sink=sink)
    business = FetchRequest.create(
        request_id=f"periodic-probe-business-{ticker}",
        domain=RecordDomain.FUNDAMENTAL, entity_key=ticker,
        parameters={"kind": "business_composition"},
    )
    business_outcome, calendar_collection = await asyncio.gather(
        runtime.run(business, (SourceChoice(EASTMONEY_BUSINESS_COMPOSITION_SOURCE, "primary"),)),
        collect_eastmoney_earnings_calendar_async(report_period, runtime=runtime),
    )
    return {
        "schema_version": "eastmoney-periodic-live-probe-v1",
        "observed_at": utc_now(),
        "ticker": ticker,
        "report_period": report_period,
        "outcomes": [
            {
                "source_key": outcome.selected_source or attempt.choice.source_key,
                "status": outcome.status,
                "publishable": outcome.publishable,
                "accepted_records": len(outcome.records),
                "attempts": [
                    {
                        "status": item.status,
                        "error": item.error,
                        "raw_hash": item.raw.raw_hash if item.raw else None,
                        "source_url": item.raw.source_url if item.raw else None,
                        "known_at": item.raw.known_at if item.raw else None,
                    }
                    for item in outcome.attempts
                ],
            }
            for outcome in (business_outcome,)
            for attempt in [outcome.attempts[-1]]
        ],
        "calendar": {
            "status": calendar_collection.status,
            "publishable": calendar_collection.publishable,
            "total_pages": calendar_collection.total_pages,
            "accepted_records": len(calendar_collection.records),
            "attempts": [
                {
                    "status": attempt.status,
                    "error": attempt.error,
                    "raw_hash": attempt.raw.raw_hash if attempt.raw else None,
                    "source_url": attempt.raw.source_url if attempt.raw else None,
                    "known_at": attempt.raw.known_at if attempt.raw else None,
                }
                for outcome in calendar_collection.outcomes
                for attempt in outcome.attempts
            ],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", default="300750.SZ")
    parser.add_argument("--report-period", default="2026-06-30")
    parser.add_argument("--out", type=Path, default=ROOT / "evidence" / "eastmoney-periodic-live-probe.json")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    receipt = asyncio.run(probe(args.ticker, args.report_period))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(args.out)
    success = (
        all(item["status"] == "success" for item in receipt["outcomes"])
        and receipt["calendar"]["status"] == "success"
    )
    return 0 if success or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
