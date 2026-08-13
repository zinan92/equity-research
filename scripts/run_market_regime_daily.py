#!/usr/bin/env python3
"""Run or inspect the downstream Market Regime Daily v2 runtime."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
PRODUCT = ROOT / "product"
sys.path.insert(0, str(PRODUCT))

from market_regime_daily_runtime import (  # noqa: E402
    ALLOWED_INTERVAL_HOURS,
    MarketRegimeDailyRuntime,
    configured_daily_interval_hours,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--interval-hours", type=int, choices=ALLOWED_INTERVAL_HOURS)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--health", action="store_true")
    args = parser.parse_args()
    runtime = MarketRegimeDailyRuntime(
        args.root,
        interval_hours=configured_daily_interval_hours(args.interval_hours),
    )
    if args.health:
        print(json.dumps(runtime.health(), ensure_ascii=False, indent=2))
        return 0
    if args.once:
        result = runtime.cycle()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("state") == "idle" else 2
    print(
        json.dumps(
            {
                "status": "starting",
                "root": str(runtime.root),
                "interval_hours": runtime.interval_hours,
                "allowed_intervals": list(ALLOWED_INTERVAL_HOURS),
                "downstream_of": "market-regime-structural-cycle",
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    try:
        runtime.run_forever()
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
