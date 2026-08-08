#!/usr/bin/env python3
"""Refresh the local-only Yahoo 5-minute Market Regime snapshot once."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
PRODUCT = ROOT / "product"
sys.path.insert(0, str(PRODUCT))

from data_core.market_regime_intraday_data import (  # noqa: E402
    YAHOO_INSTRUMENTS,
    MarketRegimeIntradayDataStore,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(os.getenv("PARK_MARKET_REGIME_ROOT", PRODUCT / "runtime" / "market-regime")),
    )
    parser.add_argument(
        "--instrument",
        action="append",
        choices=[item.key for item in YAHOO_INSTRUMENTS],
        help="repeat to limit the frozen registry; default refreshes all Yahoo identities",
    )
    parser.add_argument(
        "--deployment-mode",
        choices=("local_prototype", "private_beta", "public"),
        default="local_prototype",
    )
    parser.add_argument(
        "--license-status",
        choices=("local_evaluation_only", "commercial_rights_approved", "disabled"),
        default="local_evaluation_only",
    )
    parser.add_argument("--license-reference")
    args = parser.parse_args()
    snapshot = MarketRegimeIntradayDataStore(args.root).refresh(
        instrument_keys=args.instrument,
        deployment_mode=args.deployment_mode,
        license_status=args.license_status,
        license_reference=args.license_reference,
    )
    print(
        json.dumps(
            {
                "schema_version": snapshot["schema_version"],
                "run_id": snapshot["run_id"],
                "snapshot_id": snapshot["snapshot_id"],
                "quality": snapshot["quality"],
                "accepted_count": snapshot["accepted_count"],
                "rejected_count": snapshot["rejected_count"],
                "root": str(args.root.expanduser().resolve()),
                "publication_eligible": snapshot["publication_eligible"],
                "action_eligible": snapshot["action_eligible"],
                "instruments": [
                    {
                        "key": item["instrument"]["key"],
                        "session_state": item["session_state"],
                        "freshness": item["freshness"],
                        "provider_timestamp": item["provider_timestamp"],
                        "current_age_seconds": item["current_age_seconds"],
                        "refresh_status": item.get("refresh_status"),
                    }
                    for item in snapshot["instruments"]
                ],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
