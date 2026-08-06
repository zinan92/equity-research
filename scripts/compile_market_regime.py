#!/usr/bin/env python3
"""Compile the latest frozen OHLC snapshot into a deterministic regime receipt."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
PRODUCT = ROOT / "product"
sys.path.insert(0, str(PRODUCT))

from data_core.market_regime_model import MarketRegimeAnalysisStore  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(os.getenv("PARK_MARKET_REGIME_ROOT", PRODUCT / "runtime" / "market-regime")),
        help="Runtime evidence root containing latest.json",
    )
    args = parser.parse_args()
    analysis = MarketRegimeAnalysisStore(args.root).compile_latest()
    dimensions = analysis["dimensions"]
    print(
        json.dumps(
            {
                "analysis_id": analysis["analysis_id"],
                "data_kind": analysis["data_kind"],
                "status": analysis["status"],
                "confidence": analysis["confidence"],
                "verdict_as_of": analysis["verdict_as_of"],
                "risk": dimensions["risk"]["label"],
                "posture": dimensions["posture"]["label"],
                "style": dimensions["style"]["label"],
                "leader": dimensions["leadership"]["leader"],
                "leadership_state": dimensions["leadership"]["state"],
                "scenario": analysis["scenario"]["code"],
                "what_is_going_on": analysis["what_is_going_on"],
                "truth_boundary": analysis["truth_boundary"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
