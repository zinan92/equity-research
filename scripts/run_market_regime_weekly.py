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


PRODUCT = Path(__file__).resolve().parents[1] / "product"
sys.path.insert(0, str(PRODUCT))

from data_core.market_regime_weekly_datafeed import WeeklyDatafeedClient, load_datafeed_weekly_source_snapshot  # noqa: E402
from data_core.market_regime_weekly_provider import (  # noqa: E402
    ASSET_SYSTEM_PROMPT,
    DeepSeekWeeklyAssetProvider,
    DeepSeekWeeklyRankingProvider,
    RANKING_SYSTEM_PROMPT,
)
from data_core.market_regime_weekly_asset_analysis import validate_asset_analysis  # noqa: E402
from data_core.market_regime_weekly_ranking import validate_ranking_output  # noqa: E402
from data_core.market_regime_llm_provider import CodexCliProvider, ValidatedFallbackProvider  # noqa: E402
from data_core.market_regime_weekly_runtime import WeeklyMacroRuntime, WeeklyRuntimeError  # noqa: E402
from data_core.market_regime_weekly_snapshots import PlaywrightWeeklyChartSnapshotPort  # noqa: E402


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("--now requires a timezone")
    return parsed.astimezone(timezone.utc)


def _parse_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def build_weekly_runtime(*, datafeed_url: str, runtime_root: Path, output_root: Path, key_file: Path, model: str, codex_model: str | None):
    """Build the independent Weekly K-line runtime used by CLI and delivery."""

    datafeed_client = WeeklyDatafeedClient(base_url=datafeed_url)
    source_loader = lambda *, week_end, cutoff_at, live_as_of=None: load_datafeed_weekly_source_snapshot(
        datafeed_client,
        week_end=week_end.isoformat(),
        cutoff_at=cutoff_at.isoformat().replace("+00:00", "Z"),
        live_as_of=live_as_of,
    )
    deepseek_asset = DeepSeekWeeklyAssetProvider(key_file, model=model) if key_file.is_file() else None
    deepseek_ranking = DeepSeekWeeklyRankingProvider(key_file, model=model) if key_file.is_file() else None
    return WeeklyMacroRuntime(
        source_loader=source_loader,
        asset_provider=ValidatedFallbackProvider(
            primary=deepseek_asset,
            fallback=CodexCliProvider(system_prompt=ASSET_SYSTEM_PROMPT, model=codex_model),
            validator=validate_asset_analysis,
            fallback_attempts=1,
        ),
        ranking_provider=ValidatedFallbackProvider(
            primary=deepseek_ranking,
            fallback=CodexCliProvider(system_prompt=RANKING_SYSTEM_PROMPT, model=codex_model),
            validator=validate_ranking_output,
            fallback_attempts=1,
        ),
        runtime_root=runtime_root,
        output_root=output_root,
        chart_snapshot_port=PlaywrightWeeklyChartSnapshotPort(runtime_root=runtime_root, output_root=output_root),
    )


def run_weekly_runtime(*, now: datetime | None = None, week_end: date | None = None, datafeed_url: str = "http://127.0.0.1:8100", runtime_root: Path, output_root: Path, key_file: Path, model: str = "deepseek-v4-flash", codex_model: str | None = None):
    runtime = build_weekly_runtime(
        datafeed_url=datafeed_url,
        runtime_root=runtime_root,
        output_root=output_root,
        key_file=key_file,
        model=model,
        codex_model=codex_model,
    )
    return runtime.run_once(now=now, week_end=week_end)


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
    parser.add_argument("--codex-model", default=None)
    args = parser.parse_args()
    now = _parse_datetime(args.now)
    week_end = _parse_date(args.week_end)
    try:
        result = run_weekly_runtime(
            now=now,
            week_end=week_end,
            datafeed_url=args.datafeed_url,
            runtime_root=args.runtime_root,
            output_root=args.output_root,
            key_file=args.key_file,
            model=args.model,
            codex_model=args.codex_model,
        )
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
        "chart_snapshots": sum(1 for slot in report.get("chart_slots") or [] if isinstance(slot, dict) and isinstance(slot.get("snapshot"), dict)),
        "assets": len(report.get("cards") or []),
        "analysis_unavailable": sum(card.get("analysis_status") != "validated" for card in report.get("cards") or []),
        "ranking_status": (report.get("ranking") or {}).get("generation_status"),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
