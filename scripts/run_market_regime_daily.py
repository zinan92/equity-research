#!/usr/bin/env python3
"""Run or inspect the canonical Daily K-line Newsletter runtime."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

PRODUCT = Path(__file__).resolve().parents[1] / "product"
sys.path.insert(0, str(PRODUCT))

from data_core.market_regime_daily_runtime import DailyKlineRuntime, DailyRuntimeError  # noqa: E402


def _defaults() -> tuple[Path, Path, Path, Path, str]:
    home = Path.home()
    return (
        Path(os.getenv("PARK_KLINE_DAILY_RUNTIME", home / "Library" / "Application Support" / "ParkKlineDaily" / "runtime")),
        Path(os.getenv("PARK_KLINE_DAILY_OUTPUT", home / "Desktop" / "K线日报")),
        Path(os.getenv("PARK_KLINE_DAILY_ARCHIVE", home / "park-hands" / "007_kline daily newsletter")),
        Path(os.getenv("DEEPSEEK_API_KEY_FILE", home / "park-hands" / "_secrets" / "deepseek-key")),
        os.getenv("PARK_DATAFEED_URL", "http://127.0.0.1:8100"),
    )


def main() -> int:
    runtime_default, output_default, archive_default, key_default, datafeed_default = _defaults()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path, default=runtime_default)
    parser.add_argument("--output-root", type=Path, default=output_default)
    parser.add_argument("--archive-root", type=Path, default=archive_default)
    parser.add_argument("--key-file", type=Path, default=key_default)
    parser.add_argument("--datafeed-url", default=datafeed_default)
    parser.add_argument("--no-llm", action="store_true")
    parser.add_argument("--no-snapshots", action="store_true")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()
    runtime = DailyKlineRuntime(
        runtime_root=args.runtime_root,
        output_root=args.output_root,
        archive_root=args.archive_root,
        key_file=args.key_file,
        datafeed_url=args.datafeed_url,
        no_llm=args.no_llm,
        no_snapshots=args.no_snapshots,
    )
    if args.status:
        print(json.dumps(runtime.status(), ensure_ascii=False, indent=2))
        return 0
    try:
        result = runtime.run_once()
    except DailyRuntimeError as exc:
        print(json.dumps({"state": "failed", "error": str(exc), "status": runtime.status()}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps({"state": "completed", "service_health": result.get("service_health"), "source_status": result["source"].get("source_status"), "analysis_status": result["analysis"].get("analysis_status"), "thesis_status": result["thesis"].get("generation_status"), "delivery_id": result["delivery"].get("delivery_id"), "archive": result["delivery"].get("archive")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
