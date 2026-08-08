#!/usr/bin/env python3
"""Run one verified intraday cycle or keep its 15-minute target loop alive."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
PRODUCT = ROOT / "product"
sys.path.insert(0, str(PRODUCT))

from market_regime_runtime import (  # noqa: E402
    ALLOWED_INTRADAY_INTERVAL_MINUTES,
    MarketRegimeIntradayRuntime,
    configured_intraday_interval_minutes,
    market_regime_root,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=market_regime_root())
    parser.add_argument(
        "--interval-minutes",
        type=int,
        choices=ALLOWED_INTRADAY_INTERVAL_MINUTES,
    )
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    runtime = MarketRegimeIntradayRuntime(
        args.root,
        interval_minutes=configured_intraday_interval_minutes(args.interval_minutes),
    )
    if args.once:
        result = runtime.cycle()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("state") in {"idle", "stopped"} else 2
    print(
        json.dumps(
            {
                "status": "starting",
                "root": str(runtime.root),
                "target_interval_minutes": runtime.interval_minutes,
                "allowed_intervals": list(ALLOWED_INTRADAY_INTERVAL_MINUTES),
                "tick_or_websocket_realtime": False,
                "stop_switch": str(runtime.stop_path),
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
