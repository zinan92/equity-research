#!/usr/bin/env python3
"""Compile and deliver one Daily cross-asset K-line thesis."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

PRODUCT = Path(__file__).resolve().parents[1] / "product"
sys.path.insert(0, str(PRODUCT))

from data_core.market_regime_daily_analysis import DailyAnalysisStore  # noqa: E402
from data_core.market_regime_daily_thesis import (  # noqa: E402
    DailyThesisDeliveryStore,
    DeepSeekDailyThesisProvider,
    compile_daily_thesis,
    validate_daily_analysis_bundle,
)


def _defaults() -> tuple[Path, Path, Path, Path]:
    home = Path.home()
    runtime = Path(os.getenv("PARK_KLINE_DAILY_RUNTIME", home / "Library" / "Application Support" / "ParkKlineDaily" / "runtime"))
    output = Path(os.getenv("PARK_KLINE_DAILY_OUTPUT", home / "Desktop" / "K线日报"))
    archive = Path(os.getenv("PARK_KLINE_DAILY_ARCHIVE", home / "park-hands" / "007_kline daily newsletter"))
    key = Path(os.getenv("DEEPSEEK_API_KEY_FILE", home / "park-hands" / "_secrets" / "deepseek-key"))
    return runtime, output, archive, key


def main() -> int:
    runtime_default, output_default, archive_default, key_default = _defaults()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path, default=runtime_default)
    parser.add_argument("--output-root", type=Path, default=output_default)
    parser.add_argument("--archive-root", type=Path, default=archive_default)
    parser.add_argument("--key-file", type=Path, default=key_default)
    parser.add_argument("--no-llm", action="store_true")
    args = parser.parse_args()

    analysis = validate_daily_analysis_bundle(DailyAnalysisStore(args.runtime_root.expanduser().resolve() / "analysis").latest())
    provider = None if args.no_llm or not args.key_file.expanduser().is_file() else DeepSeekDailyThesisProvider(args.key_file.expanduser())
    thesis = compile_daily_thesis(analysis, provider)
    receipt = DailyThesisDeliveryStore(
        runtime_root=args.runtime_root.expanduser().resolve(),
        output_root=args.output_root.expanduser().resolve(),
        archive_root=args.archive_root.expanduser().resolve(),
    ).publish(thesis, analysis)
    print(json.dumps({"state": "completed", "generation_status": thesis.get("generation_status"), "failure_code": thesis.get("failure_code"), "delivery_id": receipt["delivery_id"], "archive_path": receipt["archive_path"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
