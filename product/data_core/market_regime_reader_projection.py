"""Shared reader-facing projection for Daily and Weekly K-line editions."""

from __future__ import annotations

import html
import re
from typing import Any, Mapping


TIMEFRAME_LABELS = {
    "weekly": "周线",
    "daily": "日线",
    "four_hour": "4小时",
    "thirty_minute": "30分钟",
}
TIMEFRAME_ORDER = ("weekly", "daily", "four_hour", "thirty_minute")
SNAPSHOT_PATH_RE = re.compile(r"^snapshots/[A-Za-z0-9._-]+\.png$")
UNIT_LABELS = {
    "index points": "指数点",
    "percent": "%",
    "basis points": "基点",
    "USD/share": "美元/份",
    "USD/coin": "美元/枚",
    "USD/barrel": "美元/桶",
    "USD/troy ounce": "美元/金衡盎司",
}


def _text(value: Any, default: str) -> str:
    if isinstance(value, Mapping) and str(value.get("text") or "").strip():
        return str(value["text"]).strip()
    return default


def _analysis_output(analysis: Mapping[str, Any]) -> Mapping[str, Any]:
    nested = analysis.get("output")
    return nested if isinstance(nested, Mapping) else analysis


def _snapshot_path(snapshot: Any, prefix: str = "snapshots/") -> str | None:
    if not isinstance(snapshot, Mapping) or not isinstance(snapshot.get("asset"), Mapping):
        return None
    path = str(snapshot["asset"].get("path") or "")
    if not SNAPSHOT_PATH_RE.fullmatch(path):
        return None
    clean_prefix = prefix.rstrip("/")
    filename = path.removeprefix("snapshots/")
    return f"{clean_prefix}/{filename}" if clean_prefix else filename


def _instrument_caption(instrument: Mapping[str, Any] | None) -> str:
    if not isinstance(instrument, Mapping):
        return ""
    parts = [
        str(instrument.get(key) or "").strip()
        for key in ("ticker", "canonical_symbol", "instrument_type", "venue")
    ]
    seen: list[str] = []
    for part in parts:
        if part and part not in seen:
            seen.append(part)
    return " · ".join(seen)


def _position_structure(analysis: Mapping[str, Any]) -> tuple[Mapping[str, Any] | None, Mapping[str, Any] | None]:
    output = _analysis_output(analysis)
    deterministic = output.get("deterministic") if isinstance(output.get("deterministic"), Mapping) else {}
    position = output.get("position") if isinstance(output.get("position"), Mapping) else deterministic.get("position")
    structure = output.get("structure") if isinstance(output.get("structure"), Mapping) else deterministic.get("structure")
    return position if isinstance(position, Mapping) else None, structure if isinstance(structure, Mapping) else None


def project_daily_asset(asset: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize one Daily analysis asset into the shared reader shape."""

    analysis = asset.get("analysis") if isinstance(asset.get("analysis"), Mapping) else {}
    output = _analysis_output(analysis)
    request = asset.get("request") if isinstance(asset.get("request"), Mapping) else {}
    frames = request.get("timeframes") if isinstance(request.get("timeframes"), Mapping) else {}
    snapshots = asset.get("snapshots") if isinstance(asset.get("snapshots"), Mapping) else {}
    periods: list[dict[str, Any]] = []
    for timeframe in TIMEFRAME_ORDER:
        if timeframe not in frames:
            continue
        frame = frames[timeframe] if isinstance(frames[timeframe], Mapping) else {}
        statement = output.get(timeframe)
        status = str(frame.get("status") or "unavailable")
        periods.append(
            {
                "timeframe": timeframe,
                "label": TIMEFRAME_LABELS[timeframe],
                "status": status,
                "text": _text(
                    statement,
                    "当前分析不可用；图表状态已保留。" if status == "ready" else "本周期数据暂缺；未将其视为横盘。",
                ),
                "snapshot": snapshots.get(timeframe),
                "unit": frame.get("unit"),
                "is_provisional": bool(frame.get("is_provisional", False)),
                "latest_timestamp": frame.get("latest_timestamp"),
            }
        )
    position, structure = _position_structure(analysis)
    return {
        "asset_key": asset.get("asset_key"),
        "display_name": asset.get("display_name") or asset.get("asset_key"),
        "instrument_caption": _instrument_caption(asset.get("instrument") if isinstance(asset.get("instrument"), Mapping) else None),
        "analysis_status": "validated" if analysis.get("generation_status") == "model_generated_unreviewed" else "analysis_unavailable",
        "periods": periods,
        "position": position,
        "structure": structure,
        "odds": output.get("odds"),
        "synthesis": output.get("synthesis"),
        "market_meaning": output.get("market_meaning") or output.get("theoretical_implication"),
    }


def project_weekly_card(card: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize one Weekly report card into the shared reader shape."""

    analysis = card.get("analysis") if isinstance(card.get("analysis"), Mapping) else {}
    periods: list[dict[str, Any]] = []
    slots = card.get("chart_slots") if isinstance(card.get("chart_slots"), list) else []
    by_timeframe = {
        str(slot.get("timeframe")): slot
        for slot in slots
        if isinstance(slot, Mapping) and slot.get("timeframe")
    }
    for timeframe in TIMEFRAME_ORDER:
        slot = by_timeframe.get(timeframe)
        if not isinstance(slot, Mapping):
            continue
        status = str(slot.get("status") or "ready")
        periods.append(
            {
                "timeframe": timeframe,
                "label": TIMEFRAME_LABELS[timeframe],
                "status": status,
                "text": _text(
                    analysis.get(timeframe),
                    "当前分析不可用；图表状态已保留。" if status == "ready" else "本周期数据暂缺；未将其视为横盘。",
                ),
                "snapshot": slot.get("snapshot"),
                "unit": slot.get("unit"),
                "is_provisional": bool(slot.get("provisional_candle")),
                "latest_timestamp": slot.get("latest_timestamp"),
            }
        )
    instrument = card.get("instrument") if isinstance(card.get("instrument"), Mapping) else None
    return {
        "asset_key": card.get("asset_key"),
        "display_name": card.get("display_name") or card.get("asset_key"),
        "instrument_caption": _instrument_caption(instrument),
        "analysis_status": card.get("analysis_status") or "analysis_unavailable",
        "periods": periods,
        "position": analysis.get("position"),
        "structure": analysis.get("structure"),
        "odds": analysis.get("odds"),
        "synthesis": analysis.get("synthesis"),
        "market_meaning": analysis.get("theoretical_implication"),
    }


def _summary_text(value: Any, default: str) -> str:
    return _text(value, default)


def render_reader_asset_markdown(projection: Mapping[str, Any], *, snapshot_prefix: str = "snapshots/") -> str:
    """Render a shared asset card for Markdown/article surfaces."""

    lines = [f"### {projection.get('display_name') or projection.get('asset_key')}"]
    caption = str(projection.get("instrument_caption") or "").strip()
    if caption:
        lines.append(f"标的：{caption}")
    lines.append("")
    for period in projection.get("periods") or []:
        if not isinstance(period, Mapping):
            continue
        href = _snapshot_path(period.get("snapshot"), snapshot_prefix)
        if href:
            lines.extend([f"![{projection.get('display_name')}｜{period.get('label')} K 线图]({href})", ""])
        elif period.get("status") != "ready":
            lines.extend([f"图表暂缺：{period.get('text')}", ""])
        lines.extend([f"**{period.get('label')}**：{period.get('text')}", ""])
    position = projection.get("position")
    structure = projection.get("structure")
    odds = projection.get("odds")
    if isinstance(position, Mapping):
        lines.append(f"**位置**：{_text(position, '位置：不可用。')}")
    if isinstance(structure, Mapping):
        lines.append(f"**结构**：{_text(structure, '结构：不可用。')}")
    lines.append(f"**赔率**：{_text(odds, '赔率尚未形成。')}")
    lines.extend(
        [
            f"**综合结论**：{_summary_text(projection.get('synthesis'), '当前多周期分析不可用。')}",
            f"**市场含义**：{_summary_text(projection.get('market_meaning'), '当前机制解释不可用。')}",
            "",
        ]
    )
    return "\n".join(lines)


def render_reader_asset_html(projection: Mapping[str, Any], *, snapshot_prefix: str = "snapshots/") -> str:
    """Render a shared asset card fragment for static HTML."""

    display_name = html.escape(str(projection.get("display_name") or projection.get("asset_key") or "资产"))
    caption = html.escape(str(projection.get("instrument_caption") or ""))
    periods: list[str] = []
    for period in projection.get("periods") or []:
        if not isinstance(period, Mapping):
            continue
        href = _snapshot_path(period.get("snapshot"), snapshot_prefix)
        if href:
            chart = f'<img src="{html.escape(href, quote=True)}" alt="{display_name}｜{html.escape(str(period.get("label") or ""))} K 线图">'
        else:
            chart = f'<div class="chart-unavailable">{html.escape(str(period.get("text") or "本周期数据暂缺。"))}</div>'
        unit = UNIT_LABELS.get(str(period.get("unit") or ""), str(period.get("unit") or ""))
        unit_label = f" · 单位：{html.escape(unit)}" if unit else ""
        periods.append(
            f'<figure class="timeframe" data-timeframe="{html.escape(str(period.get("timeframe") or ""), quote=True)}"><div><b>{html.escape(str(period.get("label") or ""))}</b><div class="snapshot-frame">{chart}</div><figcaption>EMA50 · MACD(12,26,9){unit_label}</figcaption></div><p>{html.escape(str(period.get("text") or ""))}</p></figure>'
        )
    position = html.escape(_text(projection.get("position"), "位置：不可用。"))
    structure = html.escape(_text(projection.get("structure"), "结构：不可用。"))
    odds = html.escape(_text(projection.get("odds"), "赔率尚未形成。"))
    synthesis = html.escape(_summary_text(projection.get("synthesis"), "当前多周期分析不可用。"))
    meaning = html.escape(_summary_text(projection.get("market_meaning"), "当前机制解释不可用。"))
    asset_key = html.escape(str(projection.get("asset_key") or ""), quote=True)
    status_label = {"validated": "已验证", "analysis_unavailable": "分析不可用"}.get(str(projection.get("analysis_status")), "状态待确认")
    return (
        f'<section class="asset-pane reader-asset" id="asset-{asset_key}" data-pane="{asset_key}" data-asset-key="{asset_key}" data-timeframes="{len(periods)}" data-summary-order="位置,结构,赔率,多周期结论,机制解释">'
        f'<header><div><h2>{display_name}</h2>{f"<small>标的：{caption}</small>" if caption else ""}</div><small>{status_label}</small></header>'
        f'{"".join(periods)}'
        f'<div class="summary-dimensions"><div><b>位置</b><p>{position}</p></div><div><b>结构</b><p>{structure}</p></div><div><b>赔率</b><p>{odds}</p></div></div>'
        f'<div class="synthesis"><b>综合结论与市场含义</b><p>{synthesis}</p><p>{meaning}</p></div></section>'
    )


__all__ = [
    "TIMEFRAME_LABELS",
    "TIMEFRAME_ORDER",
    "project_daily_asset",
    "project_weekly_card",
    "render_reader_asset_html",
    "render_reader_asset_markdown",
]
