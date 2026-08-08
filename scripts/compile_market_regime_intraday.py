#!/usr/bin/env python3
"""Compile the verified structural/intraday inputs into one local overlay."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
PRODUCT = ROOT / "product"
sys.path.insert(0, str(PRODUCT))

from data_core.market_regime_intraday_model import (  # noqa: E402
    MarketRegimeIntradayOverlayStore,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(
            os.getenv(
                "PARK_MARKET_REGIME_ROOT",
                PRODUCT / "runtime" / "market-regime",
            )
        ),
        help="Runtime root containing verified daily analysis and intraday inputs",
    )
    args = parser.parse_args()
    receipt = MarketRegimeIntradayOverlayStore(args.root).compile_latest()
    overlay = receipt["overlay"]
    print(
        json.dumps(
            {
                "overlay_id": overlay["overlay_id"],
                "generated_at": overlay["generated_at"],
                "relation": overlay["relation"],
                "material_change": overlay["material_change"],
                "a_share_tape": overlay["a_share_tape"],
                "cross_asset": overlay["cross_asset"],
                "top_drivers": overlay["top_drivers"],
                "watch_conditions": overlay["watch_conditions"],
                "history_appended": receipt["history_appended"],
                "history_sequence": receipt["sequence"],
                "history_id": receipt["history_id"],
                "truth_boundary": overlay["truth_boundary"],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
