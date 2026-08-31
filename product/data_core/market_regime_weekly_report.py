"""Reader-facing Variant B Weekly Macro report projection."""

from __future__ import annotations

import html
import json
import hashlib
from pathlib import Path
from typing import Any, Mapping

from .market_regime_weekly_features import FEATURE_PARAMETERS, FEATURE_SCHEMA_VERSION, WeeklyFeatureError, build_timeframe_features
from .market_regime_weekly_asset_analysis import ANALYSIS_ID_PREFIX
from .market_regime_weekly_mechanisms import mechanism_for_asset, validate_theoretical_statement
from .market_regime_weekly_odds import WeeklyOddsError, validate_odds
from .market_regime_weekly_source import CANONICAL_REGISTRY, CONTEXT_4H_KEYS, DISPLAY_NAMES, SCHEMA_VERSION as SOURCE_SCHEMA, WEEKLY_KEYS
from .market_regime_weekly_contract import WeeklyCandleContractError
from .market_regime_weekly_standard_kline import build_standard_kline_payload, standard_kline_options_for_response
from .market_regime_weekly_position_structure import POSITION_STATES, STRUCTURE_STATES
from .market_regime_reader_projection import project_weekly_card, render_reader_asset_html, render_reader_asset_markdown, render_reader_article


SCHEMA_VERSION = "market-regime-weekly-report-v8-tradeable-assets"
RENDERER_VERSION = "market-regime-weekly-report-renderer-v15"
REPORT_ID_PREFIX = "market-regime-weekly-report:"
CHAPTERS = (
    ("money_price", "钱的价格", ("dxy", "us2y", "us10y", "us2s10s")),
    ("risk_assets", "风险资产", ("sp500", "nasdaq", "us_dividend", "vix")),
    ("crypto", "加密资产永续", ("bitcoin", "ethereum", "hype")),
    ("asia_a_share", "亚洲与 A 股", ("shanghai", "star50", "china_dividend", "nikkei", "kospi")),
    ("real_assets", "实物资产", ("wti", "gold", "silver")),
)


class WeeklyReportError(ValueError):
    """Weekly report projection or reader contract failed closed."""


_STANDARD_KLINE_JS_PATH = Path(__file__).resolve().parents[1] / "vendor" / "standard-kline.07acafa7.js"
_LIGHTWEIGHT_CHARTS_JS_PATH = Path(__file__).resolve().parents[1] / "vendor" / "lightweight-charts.5.2.0.standalone.js"


def _standard_kline_js() -> str:
    try:
        source = _STANDARD_KLINE_JS_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        raise WeeklyReportError("standard_kline_asset_missing") from exc
    return source.replace("</script>", "<\\/script>")


def _lightweight_charts_js() -> str:
    try:
        source = _LIGHTWEIGHT_CHARTS_JS_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        raise WeeklyReportError("lightweight_charts_asset_missing") from exc
    return source.replace("</script>", "<\\/script>")


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _escape(value: Any) -> str:
    return html.escape(str(value), quote=True)


UNIT_LABELS = {
    "index points": "指数点",
    "percent": "%",
    "basis points": "基点",
    "USD/share": "美元/份",
    "USD/coin": "美元/枚",
    "USD/barrel": "美元/桶",
    "USD/troy ounce": "美元/金衡盎司",
}


def _unit_label(value: Any) -> str:
    return UNIT_LABELS.get(str(value or ""), str(value or ""))


def _odds_reader_text(value: Mapping[str, Any] | None) -> str:
    if not isinstance(value, Mapping):
        return "赔率尚未形成。"
    text = str(value.get("text") or "赔率尚未形成。")
    if value.get("state") == "not_ready":
        return text
    direction = {"long": "做多", "short": "做空"}.get(str(value.get("direction")), str(value.get("direction")))
    return f"{text} 触发/入场参考 {value.get('entry_reference')}，止损 {value.get('stop')}，目标 {value.get('target')}（{direction}）。"


def _status_label(value: Any) -> str:
    return {"validated": "已验证", "analysis_unavailable": "分析不可用", "model_generated_unreviewed": "模型生成·未复核"}.get(str(value), str(value))


def _ranking_status_label(value: Any) -> str:
    return {"participate": "参与", "wait": "等待", "avoid": "回避", "unavailable": "不可用"}.get(str(value), str(value))


def _display_name(asset_key: Any) -> str:
    """Return a reader-safe label without leaking an internal registry key."""

    return DISPLAY_NAMES.get(str(asset_key or ""), "未知资产")


def _instrument_caption(card: Mapping[str, Any]) -> str:
    instrument = card.get("instrument") if isinstance(card, Mapping) else None
    if not isinstance(instrument, Mapping):
        return ""
    ticker = str(instrument.get("ticker") or "").strip()
    instrument_type = str(instrument.get("instrument_type") or "").strip()
    venue = str(instrument.get("venue") or "").strip()
    parts = [part for part in (ticker, instrument_type, venue) if part]
    return " · ".join(parts)


def _opportunity_projection(
    ranking: Mapping[str, Any] | None,
    cards: Any = None,
) -> dict[str, Any]:
    """Project ranking data into a truthful reader title and row order."""

    fallback_rows: list[dict[str, Any]] = []
    if isinstance(cards, list):
        by_key = {str(card.get("asset_key")): card for card in cards if isinstance(card, Mapping)}
        if set(by_key) == set(WEEKLY_KEYS):
            for key in WEEKLY_KEYS:
                card = by_key[key]
                analysis = card.get("analysis") if isinstance(card.get("analysis"), Mapping) else {}
                state = analysis.get("opportunity_state") if card.get("analysis_status") == "validated" else None
                fallback_rows.append(
                    {
                        "asset_key": key,
                        "status": state if state in {"participate", "wait", "avoid"} else "unavailable",
                        "rank": None,
                        "text": "数据不可用" if state not in {"participate", "wait", "avoid"} else "",
                        "evidence_ids": [],
                    }
                )

    def unordered(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
        return {"title": "机会清单", "ordered": False, "rows": fallback_rows or rows}

    rows = ranking.get("ordered_assets") if isinstance(ranking, Mapping) else None
    if not isinstance(rows, list):
        return unordered([])
    original_rows = [row for row in rows if isinstance(row, Mapping)]
    if not isinstance(ranking, Mapping) or ranking.get("generation_status") != "model_generated_unreviewed":
        return unordered(original_rows)
    by_key: dict[str, Mapping[str, Any]] = {}
    expected = set(WEEKLY_KEYS)
    for row in original_rows:
        key = str(row.get("asset_key") or "")
        if key in by_key or key not in expected:
            return unordered(original_rows)
        by_key[key] = row
    if set(by_key) != expected or len(original_rows) != len(WEEKLY_KEYS):
        return unordered(original_rows)
    ranked: list[Mapping[str, Any]] = []
    unavailable: list[Mapping[str, Any]] = []
    for key in WEEKLY_KEYS:
        row = by_key[key]
        status = str(row.get("status") or "")
        if status == "unavailable":
            if row.get("rank") is not None or row.get("evidence_ids"):
                return unordered(original_rows)
            unavailable.append(row)
            continue
        if status not in {"participate", "wait", "avoid"} or not isinstance(row.get("rank"), int) or row["rank"] < 1:
            return unordered(original_rows)
        ranked.append(row)
    ranks = sorted(int(row["rank"]) for row in ranked)
    if unavailable or not ranked or ranks != list(range(1, len(ranked) + 1)):
        return unordered(original_rows)
    return {"title": "机会排序", "ordered": True, "rows": sorted(ranked, key=lambda row: int(row["rank"])) + unavailable}


def _deterministic_dimensions(analysis: Mapping[str, Any] | None) -> tuple[bool, Mapping[str, Any] | None, Mapping[str, Any] | None, Mapping[str, Any] | None]:
    if not isinstance(analysis, Mapping):
        return False, None, None, None
    position = analysis.get("position")
    structure = analysis.get("structure")
    odds = analysis.get("odds")
    if not isinstance(position, Mapping) or not isinstance(structure, Mapping) or not isinstance(odds, Mapping):
        return False, None, None, None
    if position.get("state") not in POSITION_STATES or structure.get("state") not in STRUCTURE_STATES:
        return False, None, None, None
    if not isinstance(position.get("evidence_ids"), list) or not isinstance(structure.get("evidence_ids"), list):
        return False, None, None, None
    try:
        timeframe = odds.get("timeframe")
        timeframe_structure = structure.get("timeframes", {}).get(timeframe) if isinstance(structure.get("timeframes"), Mapping) else None
        timeframe_evidence = timeframe_structure.get("evidence_ids", []) if isinstance(timeframe_structure, Mapping) else []
        allowed_evidence_ids = {str(item) for item in timeframe_evidence if isinstance(item, str)}
        allowed_feature_ids = {str(item) for item in allowed_evidence_ids if item.startswith("feature:")}
        validate_odds(odds, allowed_feature_ids=allowed_feature_ids, allowed_evidence_ids=allowed_evidence_ids)
    except WeeklyOddsError:
        return False, None, None, None
    return True, position, structure, odds


def _chart_slot(
    key: str,
    timeframe: str,
    series: Mapping[str, Any],
    *,
    candle_response: Mapping[str, Any] | None = None,
    cutoff_at: Any = None,
) -> dict[str, Any]:
    standard_kline = None
    provisional_bar = series.get("current_week") if timeframe == "weekly" else None
    if isinstance(candle_response, Mapping):
        try:
            standard_kline = build_standard_kline_payload(candle_response, provisional_bar=provisional_bar)
            points = list(candle_response.get("bars") or [])
            feature_source = {
                "key": key,
                "series_kind": candle_response.get("series_kind"),
                "unit": candle_response.get("unit"),
                "source_identity": candle_response.get("source_identity"),
                "points": points,
            }
        except WeeklyCandleContractError as exc:
            raise WeeklyReportError(f"standard_kline_response_invalid:{key}:{timeframe}:{exc}") from exc
    else:
        if timeframe == "weekly":
            points = series.get("points") or []
        elif timeframe == "daily":
            points = series.get("daily_points") or []
        else:
            points = (series.get("context_4h") or {}).get("points") or []
        feature_source = {**series, "key": key, "points": points}
    if timeframe == "four_hour" and isinstance(series.get("context_4h"), Mapping):
        context_identity = series["context_4h"].get("source_identity")
        if isinstance(context_identity, Mapping) and context_identity:
            feature_source["source_identity"] = context_identity
    try:
        feature = build_timeframe_features(
            feature_source,
            timeframe=timeframe,
            cutoff_at=cutoff_at,
        )
    except WeeklyFeatureError as exc:
        feature = {
            "schema_version": FEATURE_SCHEMA_VERSION,
            "key": key,
            "timeframe": timeframe,
            "parameters": dict(FEATURE_PARAMETERS),
            "unit": (candle_response or series).get("unit"),
            "status": "unavailable",
            "failure_code": str(exc),
            "source_point_count": 0,
            "points": [],
            "x_labels": [],
            "y_labels": [],
            "current": None,
            "feature_identity": _digest({"key": key, "timeframe": timeframe, "failure_code": str(exc)}),
        }
    return {
        "slot_id": f"{key}:{timeframe}",
        "asset_key": key,
        "timeframe": timeframe,
        "kind": feature.get("chart_kind", "line" if (candle_response or series).get("series_kind") in {"rate_level", "spread"} else "price"),
        "unit": (candle_response or series).get("unit"),
        "status": feature.get("status", "unavailable"),
        "points": feature.get("points", []),
        "feature": feature,
        "x_labels": feature.get("x_labels", []),
        "y_labels": feature.get("y_labels", []),
        "current": feature.get("current"),
        "high": feature.get("high"),
        "low": feature.get("low"),
        "standard_kline": standard_kline,
        "provisional_candle": dict(provisional_bar) if isinstance(provisional_bar, Mapping) else None,
        "renderer": standard_kline.get("renderer") if isinstance(standard_kline, Mapping) else None,
        "renderer_options": standard_kline.get("renderer_options") if isinstance(standard_kline, Mapping) else standard_kline_options_for_response({"series_kind": (candle_response or series).get("series_kind")}),
    }


def _chart_coverage(chart_slots: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Summarize real chart availability without counting model prose."""

    by_timeframe: dict[str, dict[str, int]] = {}
    missing_items: list[dict[str, str]] = []
    ready = 0
    for slot in chart_slots:
        timeframe = str(slot.get("timeframe") or "unknown")
        bucket = by_timeframe.setdefault(timeframe, {"expected": 0, "ready": 0, "missing": 0})
        bucket["expected"] += 1
        if slot.get("status") == "complete":
            bucket["ready"] += 1
            ready += 1
            continue
        bucket["missing"] += 1
        feature = slot.get("feature") if isinstance(slot.get("feature"), Mapping) else {}
        missing_items.append(
            {
                "asset_key": str(slot.get("asset_key") or ""),
                "timeframe": timeframe,
                "reason": str(feature.get("failure_code") or slot.get("status") or "unavailable"),
            }
        )
    expected = len(chart_slots)
    return {
        "expected": expected,
        "ready": ready,
        "missing": expected - ready,
        "ratio": round(ready / expected, 2) if expected else 1.0,
        "by_timeframe": by_timeframe,
        "missing_items": missing_items,
        "definition": "仅统计真实标准 K 线图表槽位；不把模型解释可用性计入图表覆盖率。",
    }


def _chart_coverage_label(coverage: Mapping[str, Any] | None) -> str:
    if not isinstance(coverage, Mapping):
        return "图表覆盖：未提供。"
    expected = int(coverage.get("expected") or 0)
    ready = int(coverage.get("ready") or 0)
    missing = int(coverage.get("missing") or 0)
    by_timeframe = coverage.get("by_timeframe")
    detail = ""
    if isinstance(by_timeframe, Mapping):
        parts = []
        labels = {"weekly": "周线", "daily": "日线", "four_hour": "4 小时"}
        for key in ("weekly", "daily", "four_hour"):
            item = by_timeframe.get(key)
            if isinstance(item, Mapping):
                parts.append(f"{labels[key]} {int(item.get('ready') or 0)}/{int(item.get('expected') or 0)}")
        if parts:
            detail = "（" + " · ".join(parts) + "）"
    return f"图表覆盖：{ready}/{expected}，缺失 {missing} {detail}".strip()


def build_weekly_report(
    source_snapshot: Mapping[str, Any],
    analyses: Mapping[str, Mapping[str, Any]],
    ranking: Mapping[str, Any],
    candle_responses: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    if source_snapshot.get("schema_version") != SOURCE_SCHEMA:
        raise WeeklyReportError("source_schema_invalid")
    source_series = source_snapshot.get("series")
    if not isinstance(source_series, Mapping) or set(source_series) != set(WEEKLY_KEYS):
        raise WeeklyReportError("source_asset_set_invalid")
    cards: list[dict[str, Any]] = []
    chart_slots: list[dict[str, Any]] = []
    for key in WEEKLY_KEYS:
        series = source_series[key]
        if not isinstance(series, Mapping) or series.get("key", key) != key:
            raise WeeklyReportError(f"source_asset_identity_invalid:{key}")
        analysis = analyses.get(key)
        theory_valid = False
        analysis_identity_valid = (
            isinstance(analysis, Mapping)
            and isinstance(analysis.get("analysis_id"), str)
            and analysis["analysis_id"].startswith(ANALYSIS_ID_PREFIX)
        )
        if isinstance(analysis, Mapping):
            try:
                validate_theoretical_statement(
                    analysis.get("theoretical_implication"),
                    set(mechanism_for_asset(key)["mechanism_ids"]),
                )
                theory_valid = True
            except ValueError:
                theory_valid = False
        deterministic_valid, deterministic_position, deterministic_structure, deterministic_odds = _deterministic_dimensions(analysis)
        narrative_valid = (
            isinstance(analysis, Mapping)
            and analysis.get("generation_status") == "model_generated_unreviewed"
            and analysis_identity_valid
            and theory_valid
        )
        failure_code = (analysis or {}).get("failure_code", "analysis_missing")
        if deterministic_valid:
            analysis_status = "validated" if narrative_valid else "analysis_unavailable"
            unavailable_synthesis = {"text": "当前多周期分析不可用。", "evidence_ids": []}
            unavailable_theory = {"text": "当前机制解释不可用。", "evidence_ids": [], "claim_type": "unavailable"}
            synthesis = analysis.get("synthesis") if narrative_valid else unavailable_synthesis
            theory = analysis.get("theoretical_implication") if narrative_valid else unavailable_theory
            analysis_view = {
                "status": analysis_status,
                "failure_code": failure_code if not narrative_valid else None,
                "analysis_id": analysis.get("analysis_id") if isinstance(analysis, Mapping) else None,
                "deterministic_status": "validated",
                "weekly": analysis.get("weekly") if narrative_valid else None,
                "daily": analysis.get("daily") if narrative_valid else None,
                "four_hour": analysis.get("four_hour") if narrative_valid else None,
                "position": deterministic_position,
                "structure": deterministic_structure,
                "odds": deterministic_odds,
                "synthesis": synthesis,
                "agreement": analysis.get("agreement") if narrative_valid else None,
                "confirmation": analysis.get("confirmation") if narrative_valid else None,
                "invalidation": analysis.get("invalidation") if narrative_valid else None,
                "opportunity_state": analysis.get("opportunity_state") if narrative_valid else None,
                "rationale": analysis.get("rationale") if narrative_valid else None,
                "theoretical_implication": theory,
                "provider_status": analysis.get("provider_status") if isinstance(analysis, Mapping) else None,
                "summary": {
                    "order": ["position", "structure", "odds", "synthesis", "theoretical_implication"],
                    "position": deterministic_position,
                    "structure": deterministic_structure,
                    "odds": deterministic_odds,
                    "synthesis": synthesis,
                    "theoretical_implication": theory,
                },
            }
        else:
            analysis_status = "analysis_unavailable"
            if isinstance(analysis, Mapping) and analysis.get("generation_status") == "model_generated_unreviewed" and failure_code == "analysis_missing":
                failure_code = "position_structure_missing"
            unavailable_position = {"state": "unavailable", "text": "位置：当前不可用。", "evidence_ids": []}
            unavailable_structure = {"state": "unknown", "bias": "unknown", "text": "结构：当前不可用。", "evidence_ids": []}
            unavailable_odds = {"schema_version": "market-regime-weekly-odds-v1", "formula_version": "entry-close-boundary-v1", "state": "not_ready", "direction": "none", "timeframe": None, "reason_code": "analysis_unavailable", "evidence_ids": [], "text": "赔率尚未形成：分析证据不可用。"}
            unavailable_synthesis = {"text": "当前多周期分析不可用。", "evidence_ids": []}
            unavailable_theory = {"text": "当前机制解释不可用。", "evidence_ids": [], "claim_type": "unavailable"}
            analysis_view = {
                "status": analysis_status,
                "failure_code": failure_code,
                "position": unavailable_position,
                "structure": unavailable_structure,
                "odds": unavailable_odds,
                "synthesis": unavailable_synthesis,
                "theoretical_implication": unavailable_theory,
                "provider_status": analysis.get("provider_status") if isinstance(analysis, Mapping) else None,
                "summary": {
                    "order": ["position", "structure", "odds", "synthesis", "theoretical_implication"],
                    "position": unavailable_position,
                    "structure": unavailable_structure,
                    "odds": unavailable_odds,
                    "synthesis": unavailable_synthesis,
                    "theoretical_implication": unavailable_theory,
                },
            }
        timeframes = ["weekly", "daily"] + (["four_hour"] if key in CONTEXT_4H_KEYS else [])
        slots = [
            _chart_slot(
                key,
                tf,
                series,
                candle_response=(candle_responses or {}).get(f"{key}:{tf}"),
                cutoff_at=source_snapshot.get("cutoff_at"),
            )
            for tf in timeframes
        ]
        chart_slots.extend(slots)
        cards.append({
            "asset_key": key,
            "display_name": _display_name(key),
            "instrument": {
                "ticker": CANONICAL_REGISTRY[key].get("canonical_symbol"),
                "instrument_type": CANONICAL_REGISTRY[key].get("instrument_type"),
                "venue": CANONICAL_REGISTRY[key].get("venue"),
                "tradable": bool(CANONICAL_REGISTRY[key].get("instrument_type")),
            },
            "series_kind": series.get("series_kind"),
            "quality": series.get("quality", "unknown"),
            "analysis_status": analysis_status,
            "analysis": analysis_view,
            "chart_slots": slots,
        })
    chart_coverage = _chart_coverage(chart_slots)
    core = {
        "schema_version": SCHEMA_VERSION,
        "renderer_version": RENDERER_VERSION,
        "week_end": source_snapshot.get("week_end"),
        "cutoff_at": source_snapshot.get("cutoff_at"),
        "source_snapshot_id": source_snapshot.get("snapshot_id"),
        "source_status": source_snapshot.get("status"),
        "cards": cards,
        "chart_slots": chart_slots,
        "chart_coverage": chart_coverage,
        "ranking": ranking,
        "truth_boundary": {
            "track": "weekly_macro_kline",
            "model_generated_unreviewed": True,
            "local_evaluation_only": True,
            "publication_eligible": False,
            "automatic_execution_eligible": False,
            "broker_access": False,
            "portfolio_mutation": False,
        },
    }
    report_id = f"{REPORT_ID_PREFIX}{_digest(core)}"
    return {"report_id": report_id, "identity_core": core, **core}


def attach_chart_snapshots(
    report: Mapping[str, Any],
    snapshots: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Attach immutable snapshot references and recompute the report identity."""

    if not isinstance(report, Mapping) or not isinstance(report.get("identity_core"), Mapping):
        raise WeeklyReportError("chart_snapshot_report_invalid")
    result = json.loads(_canonical(report))
    core = result["identity_core"]
    known = {str(slot.get("slot_id")) for slot in core.get("chart_slots") or [] if isinstance(slot, Mapping)}
    unknown = sorted(set(str(key) for key in snapshots) - known)
    if unknown:
        raise WeeklyReportError(f"chart_snapshot_slot_unknown:{unknown[0]}")
    for slot in core.get("chart_slots") or []:
        if isinstance(slot, Mapping) and slot.get("slot_id") in snapshots:
            slot["snapshot"] = json.loads(_canonical(snapshots[slot["slot_id"]]))
    for card in core.get("cards") or []:
        if not isinstance(card, Mapping):
            continue
        for slot in card.get("chart_slots") or []:
            if isinstance(slot, Mapping) and slot.get("slot_id") in snapshots:
                slot["snapshot"] = json.loads(_canonical(snapshots[slot["slot_id"]]))
    for key in ("schema_version", "renderer_version", "week_end", "cutoff_at", "source_snapshot_id", "source_status", "cards", "chart_slots", "chart_coverage", "ranking", "truth_boundary"):
        result[key] = core[key]
    result["identity_core"] = core
    result["report_id"] = f"{REPORT_ID_PREFIX}{_digest(core)}"
    return result


def render_weekly_markdown(report: Mapping[str, Any]) -> str:
    opportunity = _opportunity_projection(report.get("ranking"), report.get("cards"))
    lines = [
        f"# 宏观 K 线周报｜{report.get('week_end')}",
        "",
        "> 模型生成、未经人工复核；仅限本地评估；不自动执行交易。",
        "",
        f"周末日期：{report.get('week_end')} · 分析截止：{report.get('week_end')} · 先完成全部资产分析，再查看{opportunity['title']}。",
        _chart_coverage_label(report.get("chart_coverage")),
        "",
    ]
    for _, chapter, keys in CHAPTERS:
        lines.extend([f"## {chapter}", ""])
        for key in keys:
            card = next(item for item in report["cards"] if item["asset_key"] == key)
            lines.append(render_reader_asset_markdown(project_weekly_card(card)))
            lines.append("")
    lines.extend([f"## 本周{opportunity['title']}", ""])
    for row in opportunity["rows"]:
        prefix = f"{row.get('rank')}. " if opportunity["ordered"] and row.get("rank") is not None else ""
        lines.append(f"- {prefix}{_display_name(row.get('asset_key'))}：{_ranking_status_label(row.get('status'))}")
    lines.extend(["", "## 来源与状态", ""])
    unavailable_assets = [
        str(card.get("display_name") or card.get("asset_key"))
        for card in report.get("cards") or []
        if isinstance(card, Mapping) and card.get("analysis_status") != "validated"
    ]
    lines.append(f"- 单资产解释：{len(report.get('cards') or []) - len(unavailable_assets)} 个模型解释，{len(unavailable_assets)} 个代码读数。")
    ranking_status = (report.get("ranking") or {}).get("generation_status") if isinstance(report.get("ranking"), Mapping) else None
    lines.append(f"- 机会排序解释：{'已生成' if ranking_status == 'model_generated_unreviewed' else '未生成'}。")
    dual_failures = [
        name
        for card in report.get("cards") or []
        if isinstance(card, Mapping)
        for name in [str(card.get("display_name") or card.get("asset_key"))]
        if isinstance(card.get("analysis"), Mapping)
        and isinstance(card["analysis"].get("provider_status"), Mapping)
        and card["analysis"]["provider_status"].get("both_failed")
    ]
    if dual_failures:
        lines.append(f"- 模型失败披露：{', '.join(dual_failures)} 的 DeepSeek 与 Codex CLI 均未生成解释。")
    ranking_provider_status = (report.get("ranking") or {}).get("provider_status") if isinstance(report.get("ranking"), Mapping) else None
    if isinstance(ranking_provider_status, Mapping) and ranking_provider_status.get("both_failed"):
        lines.append("- 模型失败披露：DeepSeek 与 Codex CLI 均未生成机会排序解释。")
    return "\n".join(lines) + "\n"


def _reader_html_labels(renderer: Any) -> Any:
    def wrapped(report: Mapping[str, Any], *args: Any, **kwargs: Any) -> str:
        return renderer(report, *args, **kwargs).replace("WEEK_END ", "周末日期 ")
    return wrapped


def _render_standard_kline_document(
    report: Mapping[str, Any],
    nav_parts: list[str],
    pane_parts: list[str],
    ranking_rows: str,
    ranking_title: str = "机会排序",
) -> str:
    """Render the Weekly reader with the pinned standard-kline browser port."""

    report_json = _canonical(report).replace("</", "<\\/")
    standard_kline_js = _standard_kline_js()
    lightweight_charts_js = _lightweight_charts_js()
    css = """
:root{--ink:#17201b;--muted:#68736b;--faint:#9aa39c;--line:#dedfd8;--paper:#fffefa;--canvas:#f1efe9;--green:#187b51;--red:#c94640;--navy:#3f586e;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif}
*{box-sizing:border-box}html,body{margin:0;background:var(--canvas);color:var(--ink);font-family:inherit;overflow-x:hidden}
main{width:min(1240px,100%);margin:auto;background:var(--paper);min-height:100vh}.top{padding:20px 34px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;gap:12px}.top span{font-size:10px;border:1px solid var(--line);padding:5px 8px;color:var(--muted)}
.hero{padding:44px 34px;border-bottom:1px solid var(--line);background:#f5f7f1}.hero h1{font-size:72px;font-weight:650;letter-spacing:-.035em;color:var(--navy);margin:14px 0}.hero p{color:var(--muted);line-height:1.7}
.body{display:grid;grid-template-columns:190px minmax(0,1fr);gap:22px;padding:34px;min-width:0}nav{position:sticky;top:16px;align-self:start;border:1px solid var(--line);background:#fff;padding:14px;min-width:0}nav h4{font-size:9px;color:var(--green);margin:12px 0 4px}nav button{display:block;width:100%;border:0;border-bottom:1px solid #f0f0eb;background:#fff;text-align:left;padding:7px 3px;color:var(--muted);cursor:pointer}nav button.active{color:var(--green);font-weight:700}
.asset-pane{display:none;border:1px solid var(--line);background:#fff;min-width:0;overflow:hidden}.asset-pane.active{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));align-items:stretch}.asset-pane[data-timeframes="2"].active{grid-template-columns:repeat(2,minmax(0,1fr))}.asset-pane>header{grid-column:1/-1;display:flex;justify-content:space-between;padding:17px}.asset-pane h2{font-size:27px;font-weight:650;margin:0}.asset-pane header small{color:var(--faint)}
.timeframe{display:flex;flex-direction:column;gap:12px;padding:16px;border-right:1px solid var(--line);border-bottom:1px solid var(--line);min-width:0;overflow:hidden}.timeframe b{display:block;color:var(--green);font-size:10px;letter-spacing:.12em;margin-bottom:7px}.standard-kline-mount{display:block;width:100%;height:320px;min-width:0;max-width:100%;background:#fffefa;border:1px solid #eceee8;overflow:hidden}.standard-kline-mount .standard-kline-root{min-width:0;max-width:100%;overflow:hidden}.standard-kline-mount .standard-kline-toolbar{min-width:0;max-width:100%;overflow:hidden}.standard-kline-mount .standard-kline-toolbar button{flex:0 0 auto}.standard-kline-mount .standard-kline-source{min-width:0;max-width:58%;overflow:hidden;text-overflow:ellipsis}.chart-legend{display:block;margin-top:5px;color:var(--faint);font-size:10px}.chart-unavailable{height:100%;display:grid;place-items:center;padding:16px;text-align:center;color:#8a6425;background:#fff8ed;font-size:13px;line-height:1.6}.timeframe p{font-size:17px;line-height:1.75;margin:0;overflow-wrap:anywhere}
.summary-dimensions{grid-column:1/-1;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;padding:14px 16px;background:#f7f9f5;border-bottom:1px solid var(--line)}.summary-dimensions>div{border-left:3px solid var(--green);padding-left:10px}.summary-dimensions b{font-size:10px;color:var(--green);letter-spacing:.1em}.summary-dimensions p{font-size:15px;line-height:1.55;margin:4px 0}.synthesis{grid-column:1/-1;padding:17px;background:#edf3ef}.synthesis b{font-size:10px;color:var(--green);letter-spacing:.1em}.synthesis p{font-size:18px;font-weight:500;line-height:1.65;margin:6px 0;overflow-wrap:anywhere}.ranking{padding:34px;background:#f5f3ed}.ranking h2{font-size:30px}footer{padding:25px 34px;color:var(--faint);font-size:10px}footer code{word-break:break-all}
@media(max-width:760px){.top,.hero,.body,.ranking{padding:20px 18px}.top{display:block}.top span{display:inline-block;margin-top:8px}.hero h1{font-size:55px}.body{display:block}nav{position:static;display:flex;overflow:auto;gap:6px;margin-bottom:15px}nav h4{display:none}nav button{min-width:max-content;border:1px solid var(--line);padding:7px 9px}.asset-pane[data-timeframes="2"].active,.asset-pane[data-timeframes="3"].active{grid-template-columns:1fr}.timeframe{border-right:0}.summary-dimensions{grid-template-columns:1fr}.timeframe p{font-size:17px}.standard-kline-mount{height:320px}}
"""
    bootstrap = """
const R=JSON.parse(document.getElementById('report-data').textContent);
function mountPane(pane){if(!pane||pane.dataset.mounted==='true')return;pane.querySelectorAll('[data-chart]').forEach(node=>{const slot=R.chart_slots.find(item=>item.slot_id===node.dataset.chart);const payload=slot?.standard_kline;if(!payload){node.innerHTML='<div class="chart-unavailable">当前标准 K 线输入不可用；保留数据状态，等待新的完整证据。</div>';return}const options={...(slot.renderer_options||{}),trustPolicy:{allowSynthetic:false}};const chart=new StandardKline.StandardKlineChart(node,options);chart.setDatafeedResponse(payload);node._standardKline=chart;});pane.dataset.mounted='true';}
function active(k){document.querySelectorAll('[data-pane]').forEach(x=>x.classList.toggle('active',x.dataset.pane===k));document.querySelectorAll('[data-asset-nav]').forEach(x=>x.classList.toggle('active',x.dataset.assetNav===k));mountPane(document.querySelector('[data-pane="'+k+'"]'));}
document.querySelectorAll('[data-asset-nav]').forEach(button=>button.addEventListener('click',()=>active(button.dataset.assetNav)));const first=document.querySelector('[data-pane]')?.dataset.pane;if(first)active(first);
"""
    document = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>宏观 K 线周报｜{_escape(report.get("week_end"))}</title><style>{css}</style></head><body><main><header class="top"><b>宏观 K 线周报</b><span>模型生成、未经人工复核 · 本地评估 · 无自动执行</span></header><section class="hero"><h1>本周宏观图谱</h1><p>周末日期 {_escape(report.get("week_end"))} · {_escape(_chart_coverage_label(report.get("chart_coverage")))} · 先逐一阅读全部资产，再看机会排序。</p></section><section class="body"><nav>{"".join(nav_parts)}</nav><div>{"".join(pane_parts)}</div></section><section class="ranking"><h2>本周机会排序</h2><p>排序位于全部资产之后；数据或分析不可用的资产保留其状态，不会被伪装成等待或回避。</p><ul>{ranking_rows}</ul></section><footer>模型生成、未经人工复核；仅限本地评估；不读取 Finance Daily Newsletter；不连接经纪账户或执行交易。<code>{_escape(report.get("report_id"))}</code></footer></main><script type="application/json" id="report-data">{report_json}</script><script>{lightweight_charts_js}</script><script>{standard_kline_js}</script><script>{bootstrap}</script></body></html>"""
    if ranking_title != "机会排序":
        document = document.replace("本周机会排序", f"本周{_escape(ranking_title)}")
        document = document.replace(
            "排序位于全部资产之后；数据或分析不可用的资产保留其状态，不会被伪装成等待或回避。",
            "排序证据不可用或不完整；按资产清单展示，不宣称先后顺序。",
        )
    return document


@_reader_html_labels
def render_weekly_interactive_html(report: Mapping[str, Any]) -> str:
    report_json = _canonical(report).replace("</", "<\\/")
    nav_parts: list[str] = []
    pane_parts: list[str] = []
    for _, chapter, keys in CHAPTERS:
        nav_parts.append(f'<h4>{_escape(chapter)}</h4>')
        for key in keys:
            card = next(item for item in report["cards"] if item["asset_key"] == key)
            caption = _instrument_caption(card)
            nav_parts.append(f'<button data-asset-nav="{_escape(key)}">{_escape(card["display_name"])}</button>')
            analysis = card["analysis"]
            rows = []
            for tf, label in (("weekly", "周线"), ("daily", "日线"), ("four_hour", "4小时")):
                slot = next((item for item in card["chart_slots"] if item["timeframe"] == tf), None)
                if slot is None:
                    continue
                statement = analysis.get(tf) if isinstance(analysis, Mapping) else None
                text = (statement or {}).get("text") if isinstance(statement, Mapping) else None
                if not text:
                    text = "当前分析不可用；图表仍保留，等待新的完整证据。"
                snapshot = slot.get("snapshot") if isinstance(slot, Mapping) else None
                snapshot_id = _escape(snapshot.get("snapshot_id")) if isinstance(snapshot, Mapping) and snapshot.get("snapshot_id") else ""
                snapshot_attr = f' data-snapshot-id="{snapshot_id}"' if snapshot_id else ""
                provisional_label = " · 本周进行中 · Close=最新价" if isinstance(slot.get("provisional_candle"), Mapping) else ""
                rows.append(
                    f'<article class="timeframe"><div><b>{label}</b><div class="standard-kline-mount" data-chart="{_escape(slot["slot_id"])}" data-kind="{_escape(slot["kind"])}"{snapshot_attr}></div><small class="chart-legend">EMA50 · MACD(12,26,9){(" · 单位：" + _escape(_unit_label(slot.get("unit")))) if slot.get("unit") else ""}{provisional_label}{(" · 快照 " + snapshot_id) if snapshot_id else ""}</small></div><p>{_escape(text)}</p></article>'
                )
            synthesis = analysis.get("synthesis") if isinstance(analysis, Mapping) else None
            summary = (synthesis or {}).get("text") if isinstance(synthesis, Mapping) else "当前多周期分析不可用。"
            implication = analysis.get("theoretical_implication") if isinstance(analysis, Mapping) else None
            implication_text = (implication or {}).get("text") if isinstance(implication, Mapping) else "当前机制解释不可用。"
            position = analysis.get("position") if isinstance(analysis, Mapping) else None
            structure = analysis.get("structure") if isinstance(analysis, Mapping) else None
            dimensions = ""
            if isinstance(position, Mapping) or isinstance(structure, Mapping):
                position_text = (position or {}).get("text", "位置：不可用。") if isinstance(position, Mapping) else "位置：不可用。"
                structure_text = (structure or {}).get("text", "结构：不可用。") if isinstance(structure, Mapping) else "结构：不可用。"
                dimensions = f'<div class="summary-dimensions"><div><b>位置</b><p>{_escape(position_text)}</p></div><div><b>结构</b><p>{_escape(structure_text)}</p></div></div>'
            odds = analysis.get("odds") if isinstance(analysis, Mapping) else None
            odds_block = f'<div class="odds-summary" style="grid-column:1/-1;padding:14px 16px;background:#fff8ed;border-bottom:1px solid #dedfd8"><b style="font-size:10px;color:#8a6425;letter-spacing:.1em">赔率</b><p style="font-size:15px;line-height:1.6;margin:5px 0;color:#544932">{_escape(_odds_reader_text(odds))}</p></div>'
            pane_parts.append(
                f'<section class="asset-pane" data-pane="{_escape(key)}" data-timeframes="{len(rows)}" data-summary-order="位置,结构,赔率,多周期结论,机制解释"><header><div><h2>{_escape(card["display_name"])}</h2>{f"<small>标的：{_escape(caption)}</small>" if caption else ""}</div><small>{_escape(_status_label(card["analysis_status"]))}</small></header>{"".join(rows)}{dimensions}{odds_block}<div class="synthesis"><b>多周期结论</b><p>{_escape(summary)}</p></div><div class="implication" style="grid-column:1/-1;padding:17px;background:#f7f3ea;border-top:1px solid #dedfd8"><b style="font-size:10px;color:#8a6425;letter-spacing:.1em">这意味着什么 · 机制解释</b><p style="font-size:16px;line-height:1.7;margin:6px 0;color:#544932">{_escape(implication_text)}</p></div></section>'
            )
    opportunity = _opportunity_projection(report.get("ranking"), report.get("cards"))
    ranking_rows = "".join(
        f'<li><strong>{_escape((str(row.get("rank")) + ". ") if opportunity["ordered"] and row.get("rank") is not None else "")}{_escape(_display_name(row.get("asset_key")))}</strong> · {_escape(_ranking_status_label(row.get("status")))}</li>'
        for row in opportunity["rows"]
    )
    return _render_standard_kline_document(report, nav_parts, pane_parts, ranking_rows, opportunity["title"])


def _snapshot_href(snapshot: Mapping[str, Any] | None, snapshot_prefix: str) -> str | None:
    if not isinstance(snapshot, Mapping) or not isinstance(snapshot.get("asset"), Mapping):
        return None
    path = str(snapshot["asset"].get("path") or "")
    if not path.startswith("snapshots/"):
        return None
    filename = path.removeprefix("snapshots/")
    prefix = snapshot_prefix.rstrip("/")
    return f"{prefix}/{filename}" if prefix else filename


@_reader_html_labels
def render_weekly_html(report: Mapping[str, Any], *, snapshot_prefix: str = "snapshots/") -> str:
    """Render the shareable static Weekly reader from immutable snapshots."""

    opportunity = _opportunity_projection(report.get("ranking"), report.get("cards"))
    nav_parts: list[str] = []
    pane_parts: list[str] = []
    for _, chapter, keys in CHAPTERS:
        nav_parts.append(f'<h4>{_escape(chapter)}</h4>')
        for key in keys:
            card = next(item for item in report["cards"] if item["asset_key"] == key)
            display_name = _display_name(card.get("asset_key"))
            nav_parts.append(f'<a data-asset-nav="{_escape(key)}" href="#asset-{_escape(key)}">{_escape(display_name)}</a>')
            pane_parts.append(render_reader_asset_html(project_weekly_card(card), snapshot_prefix=snapshot_prefix))
    ranking_rows = "".join(
        f'<li><strong>{_escape((str(row.get("rank")) + ". ") if opportunity["ordered"] and row.get("rank") is not None else "")}{_escape(_display_name(row.get("asset_key")))}</strong> · {_escape(_ranking_status_label(row.get("status")))}</li>'
        for row in opportunity["rows"]
    )
    css = """
:root{--ink:#17201b;--muted:#68736b;--faint:#8b958d;--line:#dedfd8;--paper:#fffefa;--canvas:#f1efe9;--green:#187b51;--navy:#3f586e;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--canvas);color:var(--ink);font-family:inherit}main{width:min(1240px,100%);margin:auto;background:var(--paper);min-height:100vh}.top{padding:20px 34px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;gap:12px}.top span{font-size:10px;border:1px solid var(--line);padding:5px 8px;color:var(--muted)}.hero{padding:44px 34px;border-bottom:1px solid var(--line);background:#f5f7f1}.hero h1{font-size:72px;font-weight:650;letter-spacing:-.035em;color:var(--navy);margin:14px 0}.hero p{color:var(--muted);line-height:1.7}.body{display:grid;grid-template-columns:190px minmax(0,1fr);gap:22px;padding:34px}nav{position:sticky;top:16px;align-self:start;border:1px solid var(--line);background:#fff;padding:14px}nav h4{font-size:9px;color:var(--green);margin:12px 0 4px}nav a{display:block;border-bottom:1px solid #f0f0eb;padding:7px 3px;color:var(--muted);text-decoration:none}nav a:hover{color:var(--green)}.asset-pane{scroll-margin-top:16px;border:1px solid var(--line);background:#fff;margin-bottom:18px;overflow:hidden}.asset-pane>header{display:flex;justify-content:space-between;padding:17px;border-bottom:1px solid var(--line)}.asset-pane h2{font-size:27px;font-weight:650;margin:0}.asset-pane header small{color:var(--faint)}.timeframe{display:flex;flex-direction:column;gap:12px;padding:16px;border-bottom:1px solid var(--line);margin:0}.timeframe b{display:block;color:var(--green);font-size:10px;letter-spacing:.12em;margin-bottom:7px}.snapshot-frame{width:100%;background:#fffefa;border:1px solid #eceee8;overflow:hidden}.snapshot-frame img{display:block;width:100%;height:auto}.chart-unavailable{min-height:180px;display:grid;place-items:center;padding:16px;text-align:center;color:#8a6425;background:#fff8ed;font-size:13px;line-height:1.6}.timeframe figcaption{display:block;margin-top:5px;color:var(--faint);font-size:10px;word-break:break-word}.timeframe p{font-size:17px;line-height:1.75;margin:0;overflow-wrap:anywhere}.summary-dimensions{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;padding:14px 16px;background:#f7f9f5;border-bottom:1px solid var(--line)}.summary-dimensions>div{border-left:3px solid var(--green);padding-left:10px}.summary-dimensions b{font-size:10px;color:var(--green);letter-spacing:.1em}.summary-dimensions p{font-size:15px;line-height:1.55;margin:4px 0}.synthesis{padding:17px;background:#edf3ef}.synthesis b,.implication b{font-size:10px;color:var(--green);letter-spacing:.1em}.synthesis p,.implication p{font-size:18px;line-height:1.65;margin:6px 0}.implication{padding:17px;background:#f7f3ea;border-top:1px solid var(--line)}.implication b{color:#8a6425}.implication p{font-size:16px;color:#544932}.ranking{padding:34px;background:#f5f3ed}.ranking h2{font-size:30px}.ranking li{margin:8px 0}.ranking p{color:var(--muted)}footer{padding:25px 34px;color:var(--faint);font-size:10px}footer code{word-break:break-all}
@media(max-width:760px){.top,.hero,.body,.ranking{padding:20px 18px}.top{display:block}.top span{display:inline-block;margin-top:8px}.hero h1{font-size:55px}.body{display:block}nav{position:static;display:flex;overflow:auto;gap:6px;margin-bottom:15px}nav h4{display:none}nav a{min-width:max-content;border:1px solid var(--line);padding:7px 9px}.summary-dimensions{grid-template-columns:1fr}.timeframe p{font-size:17px}}
@media(min-width:761px){.snapshot-frame{width:min(100%,600px);margin-inline:auto}.timeframe figcaption{max-width:600px;margin-inline:auto}}
.snapshot-frame img{image-rendering:auto}
"""
    description = "排序位于全部资产之后；数据或分析不可用的资产保留其状态。" if opportunity["ordered"] else "排序证据不可用或不完整；按资产清单展示，不宣称先后顺序。"
    cards = [card for card in report.get("cards") or [] if isinstance(card, Mapping)]
    model_count = sum(1 for card in cards if card.get("analysis_status") == "validated")
    ranking_status = (report.get("ranking") or {}).get("generation_status") if isinstance(report.get("ranking"), Mapping) else None
    dual_failure_names = [
        str(card.get("display_name") or card.get("asset_key"))
        for card in cards
        if isinstance(card.get("analysis"), Mapping)
        and isinstance(card["analysis"].get("provider_status"), Mapping)
        and card["analysis"]["provider_status"].get("both_failed")
    ]
    status_lines = [
        _chart_coverage_label(report.get("chart_coverage")),
        f"单资产解释：{model_count}/{len(cards)} 个模型解释通过；机会排序解释：{'已生成' if ranking_status == 'model_generated_unreviewed' else '未生成'}。",
    ]
    if dual_failure_names:
        status_lines.append(f"模型失败披露：{', '.join(dual_failure_names)} 的 DeepSeek 与 Codex CLI 均未生成解释。")
    ranking_provider_status = (report.get("ranking") or {}).get("provider_status") if isinstance(report.get("ranking"), Mapping) else None
    if isinstance(ranking_provider_status, Mapping) and ranking_provider_status.get("both_failed"):
        status_lines.append("模型失败披露：DeepSeek 与 Codex CLI 均未生成机会排序解释。")
    footer_status = "<br>".join(_escape(line) for line in status_lines)
    return f'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>宏观 K 线周报｜{_escape(report.get("week_end"))}</title><style>{css}</style></head><body><main><header class="top"><b>宏观 K 线周报</b><span>模型生成、未经人工复核 · 本地评估 · 无自动执行</span></header><section class="hero"><h1>本周宏观图谱</h1><p>周末日期 {_escape(report.get("week_end"))} · {_escape(_chart_coverage_label(report.get("chart_coverage")))} · 先逐一阅读全部资产，再看{_escape(opportunity["title"])}。</p></section><section class="body"><nav>{"".join(nav_parts)}</nav><div>{"".join(pane_parts)}</div></section><section class="ranking"><h2>本周{_escape(opportunity["title"])}</h2><p>{_escape(description)}</p><ul>{ranking_rows}</ul></section><footer><div>来源与状态</div>{footer_status}<br>模型生成、未经人工复核；仅限本地评估；不读取 Finance Daily Newsletter；不连接经纪账户或执行交易。<code>{_escape(report.get("report_id"))}</code></footer></main></body></html>'


def render_weekly_article(report: Mapping[str, Any], *, snapshot_prefix: str = "snapshots/") -> dict[str, Any]:
    """Render Weekly cards as the shared Mini Program article payload."""

    projections = [
        project_weekly_card(card)
        for card in report.get("cards") or []
        if isinstance(card, Mapping)
    ]
    return render_reader_article(
        projections,
        title="宏观 K 线周报",
        cutoff_at=str(report.get("week_end") or ""),
        snapshot_prefix=snapshot_prefix,
    )
