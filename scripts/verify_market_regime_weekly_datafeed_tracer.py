#!/usr/bin/env python3
"""Smoke-test the representative Weekly canonical datafeed paths.

This is intentionally a live local check, not part of the deterministic unit
suite.  It exercises one representative for each source/timeframe semantic
that the Weekly adapter must understand.
"""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys


PRODUCT = Path(__file__).resolve().parents[1] / "product"
sys.path.insert(0, str(PRODUCT))

from data_core.market_regime_weekly_datafeed import WeeklyDatafeedClient  # noqa: E402


REPRESENTATIVES = (
    ("sp500", "daily", "yahoo_index_daily"),
    ("us2y", "daily", "treasury_daily"),
    ("shanghai", "daily", "ashare_primary_or_explicit_fallback"),
    ("bitcoin", "four_hour", "native_4h"),
    ("gold", "four_hour", "aggregated_1h_to_4h"),
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify representative Weekly datafeed paths")
    parser.add_argument("--datafeed-url", default="http://127.0.0.1:8100")
    parser.add_argument("--limit", type=int, default=6)
    args = parser.parse_args()

    client = WeeklyDatafeedClient(base_url=args.datafeed_url)
    rows: list[dict[str, object]] = []
    failures: list[str] = []
    for asset_key, timeframe, semantic in REPRESENTATIVES:
        response = client.fetch(asset_key, timeframe, limit=args.limit)
        row = {
            "asset_key": asset_key,
            "timeframe": timeframe,
            "semantic": semantic,
            "status": response.get("status"),
            "provider": response.get("provider"),
            "source_mode": response.get("source_mode"),
            "selected_source": response.get("selected_source"),
            "selection_reason": response.get("selection_reason"),
            "raw_timeframe": response.get("raw_timeframe"),
            "timeframe_origin": response.get("timeframe_origin"),
            "aggregation": response.get("aggregation"),
            "bar_count": len(response.get("bars") or []),
            "latest_timestamp": response.get("latest_timestamp"),
            "reject_reason": response.get("reject_reason"),
        }
        rows.append(row)
        if response.get("status") != "ready":
            failures.append(f"{asset_key}:{timeframe}:{response.get('reject_reason')}")
            continue
        if timeframe == "four_hour":
            if not response.get("source_identity"):
                failures.append(f"{asset_key}:{timeframe}:source_identity_missing")
            if asset_key == "bitcoin" and (
                response.get("raw_timeframe") != "4h"
                or response.get("timeframe_origin") != "native"
            ):
                failures.append(f"{asset_key}:{timeframe}:native_metadata_invalid")
            if asset_key == "gold" and (
                response.get("raw_timeframe") != "1h"
                or response.get("timeframe_origin") != "aggregated"
            ):
                failures.append(f"{asset_key}:{timeframe}:aggregation_metadata_invalid")

    print(
        json.dumps(
            {
                "status": "passed" if not failures else "failed",
                "checked_at": date.today().isoformat(),
                "datafeed_url": args.datafeed_url,
                "representative_count": len(rows),
                "failures": failures,
                "rows": rows,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
