#!/usr/bin/env python3
"""Fetch and publish one canonical Daily K-line source bundle."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

PRODUCT = Path(__file__).resolve().parents[1] / "product"
sys.path.insert(0, str(PRODUCT))

from data_core.market_regime_daily_source import (  # noqa: E402
    DEFAULT_LIMIT,
    DailyDatafeedClient,
    DailySourceError,
    DailySourceStore,
    build_daily_source_bundle,
)


def _defaults() -> tuple[Path, str]:
    home = Path.home()
    return (
        Path(
            os.getenv(
                "PARK_KLINE_DAILY_RUNTIME",
                home / "Library" / "Application Support" / "ParkKlineDaily" / "runtime",
            )
        ),
        os.getenv("PARK_DATAFEED_URL", "http://127.0.0.1:8100"),
    )


def main() -> int:
    runtime_default, datafeed_default = _defaults()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path, default=runtime_default)
    parser.add_argument("--datafeed-url", default=datafeed_default)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()

    store = DailySourceStore(args.runtime_root.expanduser().resolve() / "source")
    if args.status:
        try:
            latest = store.latest()
        except DailySourceError as exc:
            print(json.dumps({"state": "unavailable", "error": str(exc)}, ensure_ascii=False, indent=2))
            return 2
        print(
            json.dumps(
                {
                    "state": "ready",
                    "bundle_id": latest["bundle_id"],
                    "generated_at": latest["generated_at"],
                    "source_status": latest["source_status"],
                    "coverage": latest["coverage"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    client = DailyDatafeedClient(base_url=args.datafeed_url, timeout=args.timeout)
    bundle = build_daily_source_bundle(client, limit=args.limit, max_workers=args.workers)
    pointer = store.publish(bundle)
    print(
        json.dumps(
            {
                "state": "completed",
                "bundle_id": bundle["bundle_id"],
                "source_status": bundle["source_status"],
                "coverage": bundle["coverage"],
                "pointer": pointer,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
