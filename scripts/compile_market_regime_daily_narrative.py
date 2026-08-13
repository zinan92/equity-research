#!/usr/bin/env python3
"""Compile or verify the local Market Regime Daily Narrative v1."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
PRODUCT = ROOT / "product"
sys.path.insert(0, str(PRODUCT))

from data_core.market_regime_daily_evidence import MarketRegimeDailyEvidenceStore  # noqa: E402
from data_core.market_regime_daily_narrative import (  # noqa: E402
    SCHEMA_VERSION,
    DeepSeekNarrativeProvider,
    MarketRegimeDailyNarrativeError,
    MarketRegimeDailyNarrativeStore,
)


def summary(artifact: dict, *, output_root: Path) -> dict:
    return {
        "schema_version": artifact.get("schema_version"),
        "narrative_id": artifact.get("narrative_id"),
        "pack_id": artifact.get("pack_id"),
        "generation_status": artifact.get("generation_status"),
        "posture": (artifact.get("output") or {}).get("posture"),
        "output_root": str(output_root),
        "publication_eligible": False,
        "action_eligible": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    default_daily = Path(
        os.getenv("PARK_MARKET_REGIME_ROOT", PRODUCT / "runtime" / "market-regime")
    )
    default_evidence = default_daily / "daily-v2" / "evidence-packs"
    parser.add_argument("--daily-root", type=Path, default=default_daily)
    parser.add_argument(
        "--macro-root",
        type=Path,
        default=Path(os.getenv("PARK_MARKET_REGIME_MACRO_ROOT", default_daily / "macro")),
    )
    parser.add_argument(
        "--evidence-root",
        type=Path,
        default=Path(os.getenv("PARK_MARKET_REGIME_DAILY_EVIDENCE_ROOT", default_evidence)),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path(
            os.getenv(
                "PARK_MARKET_REGIME_DAILY_NARRATIVE_ROOT",
                default_daily / "daily-v2" / "narratives",
            )
        ),
    )
    parser.add_argument("--key-file", type=Path)
    parser.add_argument("--model", default=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro"))
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()
    output_root = args.output_root.expanduser().resolve()
    evidence_store = MarketRegimeDailyEvidenceStore(
        args.daily_root, args.macro_root, args.evidence_root
    )
    store = MarketRegimeDailyNarrativeStore(evidence_store, output_root)
    if args.status:
        latest_exists = (output_root / "state.json").exists()
        try:
            artifact = store.latest()
        except MarketRegimeDailyNarrativeError as exc:
            print(
                json.dumps(
                    {
                        "schema_version": SCHEMA_VERSION,
                        "status": "unavailable",
                        "reason": str(exc),
                        "output_root": str(output_root),
                        "publication_eligible": False,
                        "action_eligible": False,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 2 if latest_exists else 0
    else:
        key_file = args.key_file
        if key_file is None:
            configured = os.getenv("DEEPSEEK_API_KEY_FILE")
            key_file = Path(configured).expanduser() if configured else None
        provider = (
            DeepSeekNarrativeProvider(key_file=key_file.resolve(), model=args.model)
            if key_file is not None and key_file.is_file()
            else None
        )
        artifact = store.compile_latest(provider)
    print(json.dumps(summary(artifact, output_root=output_root), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
