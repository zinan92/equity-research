#!/usr/bin/env python3
"""Compile one Daily per-asset analysis bundle from the latest source bundle."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

PRODUCT = Path(__file__).resolve().parents[1] / "product"
sys.path.insert(0, str(PRODUCT))

from data_core.market_regime_daily_analysis import (  # noqa: E402
    DailyAnalysisError,
    DailyAnalysisStore,
    DeepSeekDailyAssetProvider,
    build_daily_analysis_bundle,
)
from data_core.market_regime_daily_snapshots import DailyChartSnapshotPort  # noqa: E402
from data_core.market_regime_daily_source import DailySourceStore  # noqa: E402


def _defaults() -> tuple[Path, Path, Path]:
    home = Path.home()
    runtime = Path(
        os.getenv(
            "PARK_KLINE_DAILY_RUNTIME",
            home / "Library" / "Application Support" / "ParkKlineDaily" / "runtime",
        )
    )
    output = Path(os.getenv("PARK_KLINE_DAILY_OUTPUT", runtime / "output"))
    key = Path(os.getenv("DEEPSEEK_API_KEY_FILE", home / "park-hands" / "_secrets" / "deepseek-key"))
    return runtime, output, key


def main() -> int:
    runtime_default, output_default, key_default = _defaults()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path, default=runtime_default)
    parser.add_argument("--output-root", type=Path, default=output_default)
    parser.add_argument("--key-file", type=Path, default=key_default)
    parser.add_argument("--no-llm", action="store_true")
    parser.add_argument("--no-snapshots", action="store_true")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()

    runtime_root = args.runtime_root.expanduser().resolve()
    store = DailyAnalysisStore(runtime_root / "analysis")
    if args.status:
        try:
            latest = store.latest()
        except DailyAnalysisError as exc:
            print(json.dumps({"state": "unavailable", "error": str(exc)}, ensure_ascii=False, indent=2))
            return 2
        print(json.dumps({"state": "ready", "bundle_id": latest["bundle_id"], "analysis_status": latest["analysis_status"], "cutoff_at": latest["cutoff_at"]}, ensure_ascii=False, indent=2))
        return 0

    source = DailySourceStore(runtime_root / "source").latest()
    provider = None
    if not args.no_llm and args.key_file.expanduser().is_file():
        provider = DeepSeekDailyAssetProvider(args.key_file.expanduser())
    provider_factory = (lambda _request: provider) if provider is not None else None
    snapshot_port = None if args.no_snapshots else DailyChartSnapshotPort(runtime_root=runtime_root, output_root=args.output_root.expanduser().resolve())
    bundle = build_daily_analysis_bundle(source, provider_factory=provider_factory, snapshot_port=snapshot_port)
    pointer = store.publish(bundle)
    print(json.dumps({"state": "completed", "bundle_id": bundle["bundle_id"], "analysis_status": bundle["analysis_status"], "assets": len(bundle["assets"]), "pointer": pointer}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
