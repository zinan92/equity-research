#!/usr/bin/env python3
"""Refresh the local-only market-regime OHLC snapshot once."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
PRODUCT = ROOT / "product"
sys.path.insert(0, str(PRODUCT))

from data_core.market_regime_data import (  # noqa: E402
    INSTRUMENTS,
    MarketRegimeDataStore,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh frozen daily OHLC for the market-regime page")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(os.getenv("PARK_MARKET_REGIME_ROOT", PRODUCT / "runtime" / "market-regime")),
        help="Runtime evidence root (default: product/runtime/market-regime)",
    )
    parser.add_argument("--instrument", action="append", choices=[item.key for item in INSTRUMENTS])
    parser.add_argument("--deployment-mode", choices=("local_prototype", "private_beta", "public"))
    parser.add_argument("--license-status", choices=("local_evaluation_only", "commercial_rights_approved", "disabled"))
    parser.add_argument("--license-reference")
    args = parser.parse_args()
    snapshot = MarketRegimeDataStore(args.root).refresh(
        instrument_keys=args.instrument,
        deployment_mode=args.deployment_mode,
        license_status=args.license_status,
        license_reference=args.license_reference,
    )
    print(
        json.dumps(
            {
                "run_id": snapshot["run_id"],
                "quality": snapshot["quality"],
                "instrument_count": snapshot["instrument_count"],
                "root": str(args.root.expanduser().resolve()),
                "license": snapshot["license"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
