#!/usr/bin/env python3
"""Generate one real-data Weekly Macro K-line report.

This is intentionally a manual one-shot entry point.  It does not install or
modify a scheduler and it never reads the Finance Daily Newsletter.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sys


PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT))

from data_core.market_regime_weekly_datafeed import WeeklyDatafeedClient, load_datafeed_weekly_source_snapshot  # noqa: E402
from data_core.market_regime_weekly_provider import (  # noqa: E402
    DeepSeekWeeklyAssetProvider,
    DeepSeekWeeklyRankingProvider,
)
from data_core.market_regime_weekly_runtime import WeeklyMacroRuntime, WeeklyRuntimeError  # noqa: E402


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("--now requires a timezone")
    return parsed.astimezone(timezone.utc)


def _parse_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one real-data Weekly Macro K-line report")
    home = Path.home()
    app_support = home / "Library" / "Application Support"
    parser.add_argument("--now", help="UTC-aware ISO timestamp; live run normally omits this")
    parser.add_argument("--week-end", help="completed Friday YYYY-MM-DD; defaults to previous Friday")
    parser.add_argument("--datafeed-url", default="http://127.0.0.1:8100")
    parser.add_argument("--runtime-root", type=Path, default=app_support / "ParkWeeklyMacroKline" / "runtime")
    parser.add_argument("--output-root", type=Path, default=home / "Desktop" / "宏观K线周报")
    parser.add_argument("--key-file", type=Path, default=home / "park-hands" / "_secrets" / "deepseek-key")
    parser.add_argument("--model", default="deepseek-v4-flash")
    args = parser.parse_args()
    now = _parse_datetime(args.now)
    week_end = _parse_date(args.week_end)
    if not args.key_file.is_file():
        print(json.dumps({"status": "blocked", "code": "deepseek_key_missing"}, ensure_ascii=False))
        return 2

    datafeed_client = WeeklyDatafeedClient(base_url=args.datafeed_url)
    source_loader = lambda *, week_end, cutoff_at: load_datafeed_weekly_source_snapshot(
        datafeed_client,
        week_end=week_end.isoformat(),
        cutoff_at=cutoff_at.isoformat().replace("+00:00", "Z"),
    )
    runtime = WeeklyMacroRuntime(
        source_loader=source_loader,
        asset_provider=DeepSeekWeeklyAssetProvider(args.key_file, model=args.model),
        ranking_provider=DeepSeekWeeklyRankingProvider(args.key_file, model=args.model),
        runtime_root=args.runtime_root,
        output_root=args.output_root,
    )
    try:
        result = runtime.run_once(now=now, week_end=week_end)
    except WeeklyRuntimeError as exc:
        print(json.dumps({"status": "failed", "code": str(exc)}, ensure_ascii=False))
        return 1
    report = result["report"]
    print(json.dumps({
        "status": "completed",
        "week_end": report.get("week_end"),
        "report_id": report.get("report_id"),
        "html": str(args.output_root / "latest.html"),
        "markdown": str(args.output_root / "latest.md"),
        "chart_slots": len(report.get("chart_slots") or []),
        "assets": len(report.get("cards") or []),
        "analysis_unavailable": sum(card.get("analysis_status") != "validated" for card in report.get("cards") or []),
        "ranking_status": (report.get("ranking") or {}).get("generation_status"),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
