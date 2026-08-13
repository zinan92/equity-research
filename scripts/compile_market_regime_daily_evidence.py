#!/usr/bin/env python3
"""Compile or verify the local Market Regime Daily Evidence Pack v1."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
PRODUCT = ROOT / "product"
sys.path.insert(0, str(PRODUCT))

from data_core.market_regime_daily_evidence import (  # noqa: E402
    SCHEMA_VERSION,
    MarketRegimeDailyEvidenceError,
    MarketRegimeDailyEvidenceStore,
)


def summary(pack: dict, *, output_root: Path) -> dict:
    return {
        "schema_version": pack.get("schema_version"),
        "pack_id": pack.get("pack_id"),
        "quality": pack.get("quality"),
        "coverage": pack.get("coverage"),
        "time": pack.get("time"),
        "contradiction_candidate_count": len(pack.get("contradiction_candidates") or []),
        "output_root": str(output_root),
        "publication_eligible": False,
        "action_eligible": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    default_daily = Path(
        os.getenv("PARK_MARKET_REGIME_ROOT", PRODUCT / "runtime" / "market-regime")
    )
    parser.add_argument("--daily-root", type=Path, default=default_daily)
    parser.add_argument(
        "--macro-root",
        type=Path,
        default=Path(
            os.getenv("PARK_MARKET_REGIME_MACRO_ROOT", default_daily / "macro")
        ),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path(
            os.getenv(
                "PARK_MARKET_REGIME_DAILY_EVIDENCE_ROOT",
                default_daily / "daily-v2" / "evidence-packs",
            )
        ),
    )
    parser.add_argument("--status", action="store_true", help="Verify latest pack; do not compile")
    args = parser.parse_args()
    daily_root = args.daily_root.expanduser().resolve()
    macro_root = args.macro_root.expanduser().resolve()
    output_root = args.output_root.expanduser().resolve()
    store = MarketRegimeDailyEvidenceStore(daily_root, macro_root, output_root)
    if args.status:
        latest_exists = (output_root / "latest.json").exists()
        try:
            pack = store.latest()
        except MarketRegimeDailyEvidenceError as exc:
            print(
                json.dumps(
                    {
                        "schema_version": SCHEMA_VERSION,
                        "quality": "unavailable",
                        "output_root": str(output_root),
                        "reason": str(exc),
                        "publication_eligible": False,
                        "action_eligible": False,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 2 if latest_exists else 0
    else:
        pack = store.compile_latest()
    print(json.dumps(summary(pack, output_root=output_root), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
