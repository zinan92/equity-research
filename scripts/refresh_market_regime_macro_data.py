#!/usr/bin/env python3
"""Refresh or inspect the local-only Market Regime macro-factor authority."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
PRODUCT = ROOT / "product"
sys.path.insert(0, str(PRODUCT))

from data_core.market_regime_macro_data import (  # noqa: E402
    MACRO_FACTORS,
    MarketRegimeMacroDataError,
    MarketRegimeMacroDataStore,
)


def _summary(snapshot: dict, *, root: Path) -> dict:
    factors = snapshot.get("factors") or []
    return {
        "schema_version": snapshot.get("schema_version"),
        "run_id": snapshot.get("run_id"),
        "quality": snapshot.get("quality", "unavailable"),
        "factor_count": snapshot.get("factor_count", len(factors)),
        "factors": [
            {
                "key": (item.get("factor") or {}).get("key"),
                "quality": item.get("quality"),
                "last_completed_session": item.get("last_completed_session"),
                "value": item.get("value"),
                "level_unit": item.get("level_unit")
                or (item.get("factor") or {}).get("level_unit"),
                "refresh_status": item.get("refresh_status", "accepted"),
            }
            for item in factors
        ],
        "root": str(root),
        "license": snapshot.get("license"),
        "publication_eligible": snapshot.get("publication_eligible", False),
        "action_eligible": snapshot.get("action_eligible", False),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Refresh frozen DXY and U.S. Treasury macro evidence"
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(
            os.getenv(
                "PARK_MARKET_REGIME_MACRO_ROOT",
                PRODUCT / "runtime" / "market-regime" / "macro",
            )
        ),
        help="Runtime evidence root (default: product/runtime/market-regime/macro)",
    )
    parser.add_argument("--factor", action="append", choices=[item.key for item in MACRO_FACTORS])
    parser.add_argument("--status", action="store_true", help="Read and verify latest; do not collect")
    parser.add_argument("--deployment-mode", choices=("local_prototype", "private_beta", "public"))
    parser.add_argument(
        "--license-status",
        choices=("local_evaluation_only", "commercial_rights_approved", "disabled"),
    )
    parser.add_argument("--license-reference")
    args = parser.parse_args()
    runtime_root = args.root.expanduser().resolve()
    store = MarketRegimeMacroDataStore(runtime_root)

    if args.status:
        latest_exists = (runtime_root / "latest.json").exists()
        try:
            snapshot = store.latest()
        except MarketRegimeMacroDataError as exc:
            print(
                json.dumps(
                    {
                        "schema_version": "market-regime-macro-data-v1",
                        "quality": "unavailable",
                        "factor_count": 0,
                        "root": str(runtime_root),
                        "reason": str(exc),
                        "publication_eligible": False,
                        "action_eligible": False,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            # An unused runtime is a truthful informational state. Once a
            # latest pointer exists, any verification failure is corruption and
            # must fail automation rather than masquerade as ordinary absence.
            return 2 if latest_exists else 0
    else:
        snapshot = store.refresh(
            factor_keys=args.factor,
            deployment_mode=args.deployment_mode,
            license_status=args.license_status,
            license_reference=args.license_reference,
        )

    print(json.dumps(_summary(snapshot, root=runtime_root), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
