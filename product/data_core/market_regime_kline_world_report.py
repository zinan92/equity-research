"""Versioned white vertical report for the K-line World Model.

The renderer is intentionally separate from the installed pilot newsletter.
It projects one exact S1 context and one exact S2 model artifact, renders every
input that influenced the model, and never calls a broker or mutates a portfolio.
"""

from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from html import escape
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo
import json
import math
import os
import tempfile

from .market_regime_kline_world_context import (
    KlineWorldContextError,
    KlineWorldContextStore,
    SERIES_ORDER,
    validate_kline_world_context,
)
from .market_regime_kline_world_model import (
    KlineWorldModelError,
    KlineWorldModelStore,
    validate_world_model_artifact,
)


SCHEMA_VERSION = "market-regime-kline-world-report-v1"
RENDERER_VERSION = "market-regime-kline-world-report-renderer-v3"
REPORT_ID_PREFIX = "market-regime-kline-world-report:"
SHANGHAI = ZoneInfo("Asia/Shanghai")

POSTURE_ZH = {"attack": "进攻", "wait": "等待", "defense": "防守", "unknown": "未知"}
POSTURE_EN = {"attack": "ATTACK", "wait": "WAIT", "defense": "DEFENSE", "unknown": "UNKNOWN"}
ACTION_ZH = {
    "buy": "买入",
    "add": "增加配置",
    "reduce": "降低配置",
    "avoid": "回避",
    "hedge": "对冲",
    "hold_cash": "持有现金",
    "wait": "等待",
    "rotate": "轮动至",
}
HORIZON_ZH = {"days": "数日", "weeks": "数周", "one_to_three_months": "1–3 个月"}
TARGET_ZH = {
    "cash": "现金",
    "growth_style": "成长风格",
    "dividend_style": "红利风格",
    "precious_metals": "贵金属",
    "energy": "能源",
    "duration": "久期资产",
}
CLAIM_ZH = {"observed": "已观察", "inferred": "模型推断"}
CONFIDENCE_ZH = {"high": "高", "medium": "中", "low": "低"}


class KlineWorldReportError(RuntimeError):
    """An upstream, identity, rendering or immutable-store invariant failed."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (_canonical_json(value) + "\n").encode("utf-8")


def _digest(value: Any) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise KlineWorldReportError("generated_at_timezone_required")
    return value.isoformat().replace("+00:00", "Z")


def _atomic_bytes(path: Path, encoded: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _immutable_bytes(path: Path, encoded: bytes) -> str:
    digest = sha256(encoded).hexdigest()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if path.read_bytes() != encoded:
            raise KlineWorldReportError("immutable_output_conflict")
        return digest
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    return digest


def _finite(value: Any, *, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise KlineWorldReportError(f"invalid_number:{field}") from exc
    if not math.isfinite(number):
        raise KlineWorldReportError(f"invalid_number:{field}")
    return round(number, 6)


def _truth_boundary(generation_status: str) -> dict[str, Any]:
    success = generation_status == "model_generated_unreviewed"
    return {
        "track": "kline_only",
        "finance_newsletter_input": False,
        "local_evaluation_only": True,
        "model_generated_unreviewed": success,
        "investment_advice_allowed": True,
        "contains_investment_advice": success,
        "automatic_execution_eligible": False,
        "broker_access": False,
        "portfolio_mutation": False,
        "publication_eligible": False,
    }


def _reference_index(context: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in context.get("series") or []:
        if not isinstance(item, dict):
            raise KlineWorldReportError("context_series_invalid")
        for reference in (item.get("series_id"), item.get("evidence_id")):
            if reference:
                key = str(reference)
                if key in result:
                    raise KlineWorldReportError("context_reference_duplicate")
                result[key] = {"kind": "series", "value": item}
    for item in context.get("relationships") or []:
        if not isinstance(item, dict) or not item.get("relationship_id"):
            raise KlineWorldReportError("context_relationship_invalid")
        key = str(item["relationship_id"])
        if key in result:
            raise KlineWorldReportError("context_reference_duplicate")
        result[key] = {"kind": "relationship", "value": item}
    return result


def _citation_view(reference_id: str, references: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    entry = references.get(reference_id)
    if not entry:
        raise KlineWorldReportError("report_citation_unknown")
    item = entry["value"]
    if entry["kind"] == "series":
        features = item.get("features") or {}
        rate = item.get("series_type") == "rate_level"
        return {
            "reference_id": reference_id,
            "kind": "series",
            "key": item.get("key"),
            "label": item.get("display_name"),
            "session": item.get("session"),
            "quality": item.get("quality"),
            "metric_label": "20日变化" if not rate else "20日变化",
            "metric_value": features.get("change_20d_bp" if rate else "return_20d_pct"),
            "metric_unit": "basis_points" if rate else "percent_return",
        }
    features = item.get("features") or {}
    return {
        "reference_id": reference_id,
        "kind": "relationship",
        "key": item.get("key"),
        "label": item.get("question"),
        "session": (item.get("points") or [{}])[-1].get("date"),
        "quality": "derived",
        "metric_label": "20日相对变化",
        "metric_value": features.get("relative_change_20d_pct"),
        "metric_unit": "percent_return",
        "leader": features.get("leader_20d"),
    }


def _citations(ids: Any, references: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(ids, list):
        raise KlineWorldReportError("report_citation_shape_invalid")
    normalized = [str(item) for item in ids]
    if len(normalized) != len(set(normalized)):
        raise KlineWorldReportError("report_citation_duplicate")
    return [_citation_view(item, references) for item in normalized]


def _enriched_rows(rows: Any, references: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        raise KlineWorldReportError("report_rows_invalid")
    result = []
    for row in rows:
        if not isinstance(row, dict):
            raise KlineWorldReportError("report_row_invalid")
        result.append({**row, "citations": _citations(row.get("evidence_ids"), references)})
    return result


def _series_projection(item: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    points = item.get("points") or []
    if not isinstance(points, list) or len(points) != 120:
        raise KlineWorldReportError("report_series_history_invalid")
    rate = item.get("series_type") == "rate_level"
    current_field = "value" if rate else "close"
    features = item.get("features") or {}
    change_prefix = "change" if rate else "return"
    change_suffix = "bp" if rate else "pct"
    unit = "basis_points" if rate else "percent_return"
    base = {
        "key": item.get("key"),
        "display_name": item.get("display_name"),
        "role": item.get("role"),
        "series_type": item.get("series_type"),
        "level_unit": item.get("level_unit"),
        "change_unit": unit,
        "session": item.get("session"),
        "close_at": item.get("close_at"),
        "quality": item.get("quality"),
        "series_id": item.get("series_id"),
        "evidence_id": item.get("evidence_id"),
        "level": _finite(points[-1].get(current_field), field=f"{item.get('key')}.level"),
        "change_5d": features.get(f"{change_prefix}_5d_{change_suffix}"),
        "change_20d": features.get(f"{change_prefix}_20d_{change_suffix}"),
        "change_60d": features.get(f"{change_prefix}_60d_{change_suffix}"),
        "trend_60d": features.get("trend_60d"),
    }
    chart = {**base, "chart_type": "line" if rate else "candlestick", "points": points}
    return base, chart


def _relationship_projection(item: Mapping[str, Any], labels: Mapping[str, str]) -> dict[str, Any]:
    features = item.get("features") or {}
    return {
        "relationship_id": item.get("relationship_id"),
        "key": item.get("key"),
        "lhs": item.get("lhs"),
        "lhs_label": labels.get(str(item.get("lhs")), str(item.get("lhs"))),
        "rhs": item.get("rhs"),
        "rhs_label": labels.get(str(item.get("rhs")), str(item.get("rhs"))),
        "question": item.get("question"),
        "semantics": item.get("semantics"),
        "change_5d": features.get("relative_change_5d_pct"),
        "change_20d": features.get("relative_change_20d_pct"),
        "change_60d": features.get("relative_change_60d_pct"),
        "leader_20d": features.get("leader_20d"),
        "leader_label": labels.get(str(features.get("leader_20d")), "均衡"),
        "points": item.get("points"),
    }


def build_world_report(
    *,
    context: Mapping[str, Any],
    world_model: Mapping[str, Any],
    generated_at: datetime,
    allow_fixture: bool = False,
) -> dict[str, Any]:
    """Build a deterministic report projection over exact validated authorities."""
    try:
        context_value = validate_kline_world_context(context)
        model_value = validate_world_model_artifact(world_model, context_value)
    except (KlineWorldContextError, KlineWorldModelError) as exc:
        raise KlineWorldReportError(str(exc)) from exc
    if context_value.get("data_kind") != "real" and not allow_fixture:
        raise KlineWorldReportError("fixture_context_report_forbidden")
    if model_value.get("context_id") != context_value.get("context_id"):
        raise KlineWorldReportError("world_model_context_mismatch")

    generated_iso = _iso(generated_at)
    generated_local = generated_at.astimezone(SHANGHAI)
    references = _reference_index(context_value)
    labels = {str(item["key"]): str(item["display_name"]) for item in context_value["series"]}
    output = model_value.get("output") or {}
    regime_raw = output.get("regime") or {}
    posture = str(regime_raw.get("posture") or "unknown")
    if posture not in POSTURE_ZH:
        raise KlineWorldReportError("report_posture_invalid")

    cross_section: list[dict[str, Any]] = []
    charts: list[dict[str, Any]] = []
    by_key = {str(item.get("key")): item for item in context_value.get("series") or []}
    if list(by_key) != list(SERIES_ORDER):
        raise KlineWorldReportError("report_series_order_invalid")
    for key in SERIES_ORDER:
        row, chart = _series_projection(by_key[key])
        cross_section.append(row)
        charts.append(chart)

    relationships = [
        _relationship_projection(item, labels)
        for item in context_value.get("relationships") or []
    ]
    world_raw = output.get("world_model") or {}
    world_view = {**world_raw, "citations": _citations(world_raw.get("evidence_ids") or [], references)}
    regime_view = {**regime_raw, "citations": _citations(regime_raw.get("evidence_ids") or [], references)}
    flow_map = _enriched_rows(output.get("flow_map") or [], references)
    for row in flow_map:
        row["from_label"] = labels.get(str(row.get("from_key")), str(row.get("from_key")))
        row["to_label"] = labels.get(str(row.get("to_key")), str(row.get("to_key")))
    trade_plan = _enriched_rows(output.get("trade_plan") or [], references)
    for row in trade_plan:
        target = str(row.get("target"))
        row["action_label"] = ACTION_ZH.get(str(row.get("action")), str(row.get("action")))
        row["target_label"] = labels.get(target, TARGET_ZH.get(target, target))
        row["horizon_label"] = HORIZON_ZH.get(str(row.get("horizon")), str(row.get("horizon")))

    generation_status = str(model_value.get("generation_status") or "interpretation_unavailable")
    core = {
        "schema_version": SCHEMA_VERSION,
        "renderer_version": RENDERER_VERSION,
        "report_date": generated_local.date().isoformat(),
        "generated_at": generated_iso,
        "context_id": context_value["context_id"],
        "world_model_id": model_value["world_model_id"],
        "data_kind": context_value["data_kind"],
        "generation_status": generation_status,
        "failure_code": model_value.get("failure_code"),
        "posture": posture,
        "posture_zh": POSTURE_ZH[posture],
        "posture_en": POSTURE_EN[posture],
        "confidence": model_value.get("code_owned_confidence"),
        "time": context_value.get("time"),
        "coverage": context_value.get("coverage"),
        "world_model": world_view,
        "regime": regime_view,
        "flow_map": flow_map,
        "transmission_chain": _enriched_rows(output.get("transmission_chain") or [], references),
        "trade_plan": trade_plan,
        "cross_section": cross_section,
        "relationships": relationships,
        "contradictions": _enriched_rows(output.get("contradictions") or [], references),
        "falsifiers": _enriched_rows(output.get("falsifiers") or [], references),
        "charts": charts,
        "truth_boundary": _truth_boundary(generation_status),
    }
    report_id = f"{REPORT_ID_PREFIX}{_digest(core)}"
    return {"report_id": report_id, "identity_core": core, **core}


def validate_world_report(
    report: Mapping[str, Any],
    *,
    context: Mapping[str, Any],
    world_model: Mapping[str, Any],
    allow_fixture: bool = False,
) -> dict[str, Any]:
    core = report.get("identity_core")
    if not isinstance(core, dict):
        raise KlineWorldReportError("report_identity_core_missing")
    if report.get("report_id") != f"{REPORT_ID_PREFIX}{_digest(core)}":
        raise KlineWorldReportError("report_identity_mismatch")
    if any(report.get(key) != value for key, value in core.items()):
        raise KlineWorldReportError("report_projection_mismatch")
    try:
        generated_at = datetime.fromisoformat(str(core.get("generated_at") or "").replace("Z", "+00:00"))
    except ValueError as exc:
        raise KlineWorldReportError("report_generated_at_invalid") from exc
    expected = build_world_report(
        context=context,
        world_model=world_model,
        generated_at=generated_at,
        allow_fixture=allow_fixture,
    )
    if _canonical_json(report) != _canonical_json(expected):
        raise KlineWorldReportError("report_upstream_projection_mismatch")
    return dict(report)


def _fmt(value: Any, unit: str | None = None) -> str:
    if value is None:
        return "—"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    if unit == "basis_points":
        return f"{number:+.1f} bp"
    if unit == "percent_return":
        return f"{number:+.1f}%"
    if unit == "percent":
        return f"{number:.2f}%"
    if abs(number) >= 1000:
        return f"{number:,.1f}"
    return f"{number:.2f}"


def _cite_html(citations: list[Mapping[str, Any]]) -> str:
    return "".join(
        '<button class="cite" type="button" data-evidence="'
        + escape(str(item.get("reference_id") or ""))
        + '">'
        + escape(str(item.get("label") or item.get("key") or "证据"))
        + " · "
        + escape(_fmt(item.get("metric_value"), str(item.get("metric_unit") or "")))
        + "</button>"
        for item in citations
    )


def render_markdown(report: Mapping[str, Any]) -> str:
    confidence = report.get("confidence") or {}
    evidence_quality = confidence.get("evidence_quality") or {}
    clarity = confidence.get("directional_clarity") or {}
    world = report.get("world_model") or {}
    lines = [
        f"# K 线世界日报｜{report.get('report_date')}",
        "",
        f"## {report.get('posture_zh')} / {report.get('posture_en')}",
        "",
        str(world.get("headline") or ""),
        "",
        str(world.get("synthesis") or ""),
        "",
        f"- 证据质量：{evidence_quality.get('level', '—')} / 覆盖率 {_fmt(evidence_quality.get('coverage_ratio'))}",
        f"- 方向清晰度：{clarity.get('level', '—')} / {_fmt(clarity.get('score'))}",
        "",
        "## 17 张完成日线证据",
        "",
        "完整 OHLC 日线与利率曲线请查看 HTML 版本。",
        "",
        "## 资金迁移地图",
        "",
    ]
    for row in report.get("flow_map") or []:
        lines.append(f"- {row.get('from_label')} → {row.get('to_label')}：{row.get('rationale')}")
    lines.extend(["", "## 世界模型如何传导，以及怎样交易？", "", "### 传导链", ""])
    for index, row in enumerate(report.get("transmission_chain") or [], 1):
        lines.append(f"{index}. [{CLAIM_ZH.get(str(row.get('claim_class')), row.get('claim_class'))}] {row.get('statement')}")
    lines.extend(["", "### 可执行交易建议", ""])
    for row in report.get("trade_plan") or []:
        lines.append(
            f"- **{row.get('action_label')} {row.get('target_label')}**（{row.get('horizon_label')}）："
            f"{row.get('condition')}；{row.get('rationale')}。"
        )
    lines.extend(
        [
            "",
            "## 17 个市场与 12 组相对领导关系",
            "",
            "### 17 个市场观测",
            "",
            "| 市场 | 5日 | 20日 | 60日 |",
            "|---|---:|---:|---:|",
        ]
    )
    for row in report.get("cross_section") or []:
        unit = str(row.get("change_unit") or "")
        lines.append(
            f"| {row.get('display_name')} | {_fmt(row.get('change_5d'), unit)} | "
            f"{_fmt(row.get('change_20d'), unit)} | {_fmt(row.get('change_60d'), unit)} |"
        )
    lines.extend(["", "### 12 组相对领导关系", ""])
    for row in report.get("relationships") or []:
        lines.append(
            f"- {row.get('lhs_label')} / {row.get('rhs_label')}：20日 {_fmt(row.get('change_20d'), 'percent_return')}，"
            f"领导端 {row.get('leader_label')}"
        )
    if report.get("generation_status") != "model_generated_unreviewed":
        lines.extend(["", "本期 LLM 解释未通过验证；只展示同一上下文的冻结市场证据，不复用旧建议。"])
    lines.extend(
        [
            "",
            "---",
            "",
            "模型生成、未经人工复核；包含市场层面的交易建议。仅限本地评估，不可公开分发。",
            "本系统不会自动执行交易，不读取经纪账户，不修改任何持仓。",
            "本日报不读取 Finance Daily Newsletter；两个 Track 仅供人工对照。",
            "",
        ]
    )
    return "\n".join(lines)


def render_html(report: Mapping[str, Any]) -> str:
    posture = str(report.get("posture") or "unknown")
    world = report.get("world_model") or {}
    confidence = report.get("confidence") or {}
    evidence_quality = confidence.get("evidence_quality") or {}
    clarity = confidence.get("directional_clarity") or {}
    flow_html = "".join(
        '<article class="flow-row"><div class="flow-side"><small>离开 / FROM</small><strong>'
        + escape(str(row.get("from_label") or ""))
        + '</strong></div><div class="flow-side destination"><small>流向 / TO</small><strong>'
        + escape(str(row.get("to_label") or ""))
        + '</strong></div><div class="flow-copy"><span class="confidence-word">'
        + escape(CONFIDENCE_ZH.get(str(row.get("confidence")), str(row.get("confidence"))))
        + "置信</span><p>"
        + escape(str(row.get("rationale") or ""))
        + '</p><div class="citations">'
        + _cite_html(row.get("citations") or [])
        + "</div></div></article>"
        for row in report.get("flow_map") or []
    )
    chain_html = "".join(
        '<li><span class="chain-index">'
        + f"{index:02d}"
        + '</span><div><span class="claim '
        + escape(str(row.get("claim_class") or ""))
        + '">'
        + escape(CLAIM_ZH.get(str(row.get("claim_class")), str(row.get("claim_class"))))
        + "</span><p>"
        + escape(str(row.get("statement") or ""))
        + '</p><div class="citations">'
        + _cite_html(row.get("citations") or [])
        + "</div></div></li>"
        for index, row in enumerate(report.get("transmission_chain") or [], 1)
    )
    trade_html = "".join(
        '<article class="trade-row"><header><span>建议 '
        + f"{index:02d}"
        + "</span><strong>"
        + escape(str(row.get("action_label") or ""))
        + " · "
        + escape(str(row.get("target_label") or ""))
        + "</strong><small>"
        + escape(str(row.get("horizon_label") or ""))
        + '</small></header><div class="trade-body"><div><b>执行条件</b><p>'
        + escape(str(row.get("condition") or ""))
        + "</p></div><div><b>为什么</b><p>"
        + escape(str(row.get("rationale") or ""))
        + '</p></div></div><footer><div class="citations">'
        + _cite_html(row.get("citations") or [])
        + "</div></footer></article>"
        for index, row in enumerate(report.get("trade_plan") or [], 1)
    )
    cross_html = "".join(
        '<div class="market-row"><div><strong>'
        + escape(str(row.get("display_name") or row.get("key") or ""))
        + "</strong><small>"
        + escape(str(row.get("session") or ""))
        + " · "
        + escape(str(row.get("quality") or ""))
        + '</small></div><span class="number '
        + ("positive" if float(row.get("change_5d") or 0) >= 0 else "negative")
        + '">'
        + escape(_fmt(row.get("change_5d"), str(row.get("change_unit") or "")))
        + '</span><span class="number">'
        + escape(_fmt(row.get("change_20d"), str(row.get("change_unit") or "")))
        + '</span><span class="number">'
        + escape(_fmt(row.get("change_60d"), str(row.get("change_unit") or "")))
        + "</span></div>"
        for row in report.get("cross_section") or []
    )
    relationship_html = "".join(
        '<article class="relative-row"><div><strong>'
        + escape(str(row.get("lhs_label") or ""))
        + " / "
        + escape(str(row.get("rhs_label") or ""))
        + "</strong><small>20日领导端 · "
        + escape(str(row.get("leader_label") or "均衡"))
        + '</small></div><canvas data-relative="'
        + escape(str(row.get("key") or ""))
        + '" aria-label="相对强弱趋势"></canvas><span class="number">'
        + escape(_fmt(row.get("change_20d"), "percent_return"))
        + "</span></article>"
        for row in report.get("relationships") or []
    )
    chart_html = "".join(
        '<article class="chart-card"><header><div><span>'
        + f"{index:02d}"
        + "</span><h3>"
        + escape(str(chart.get("display_name") or ""))
        + "</h3></div><small>"
        + escape(str(chart.get("session") or ""))
        + " · "
        + escape(str(chart.get("quality") or ""))
        + '</small></header><canvas data-chart="'
        + escape(str(chart.get("key") or ""))
        + '" aria-label="'
        + escape(str(chart.get("display_name") or ""))
        + ' 日线图"></canvas><footer><span>5日 '
        + escape(_fmt(chart.get("change_5d"), str(chart.get("change_unit") or "")))
        + "</span><span>20日 "
        + escape(_fmt(chart.get("change_20d"), str(chart.get("change_unit") or "")))
        + "</span><span>60日 "
        + escape(_fmt(chart.get("change_60d"), str(chart.get("change_unit") or "")))
        + "</span></footer></article>"
        for index, chart in enumerate(report.get("charts") or [], 1)
    )
    status_label = "模型生成 · 未人工复核" if report.get("generation_status") == "model_generated_unreviewed" else "模型解释不可用 · 仅展示证据"
    data_label = "VISUAL QA FIXTURE" if report.get("data_kind") == "fixture" else "LOCAL ONLY"
    unavailable = "" if report.get("generation_status") == "model_generated_unreviewed" else (
        '<div class="unavailable"><strong>本期解释未通过验证</strong><p>冻结行情仍可查看；资金迁移地图与交易建议不会复用旧内容。</p></div>'
    )
    embedded = _canonical_json(report).replace("</", "<\\/")
    return f'''<!doctype html>
<html lang="zh-CN" data-posture="{escape(posture)}">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>K 线世界日报｜{escape(str(report.get("report_date") or ""))}</title>
<style>
:root{{--ink:#151714;--subtle:#5f665f;--faint:#8e958f;--line:#e2e2dc;--paper:#fffefa;--canvas:#f3f1eb;--accent:#a36a16;--accent-deep:#70480d;--accent-wash:#fff2d9;--positive:#177a50;--negative:#cf443c;--observed:#eef2ef;--inferred:#f3eef7;--recommended:#fff0d6}}
html[data-posture="attack"]{{--accent:#197a50;--accent-deep:#0d5a39;--accent-wash:#e2f2e8;--recommended:#e5f5eb}}
html[data-posture="wait"]{{--accent:#b9740d;--accent-deep:#7e4d05;--accent-wash:#fff0d0;--recommended:#fff0d6}}
html[data-posture="defense"]{{--accent:#d4473e;--accent-deep:#9e2c25;--accent-wash:#fde7e4;--recommended:#fde7e4}}
*{{box-sizing:border-box}}html,body{{margin:0;min-width:0;background:var(--canvas);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Noto Sans CJK SC",sans-serif}}body{{overflow-x:hidden}}button{{font:inherit}}main{{width:min(1060px,100%);margin:0 auto;background:var(--paper);min-height:100vh;border-left:1px solid var(--line);border-right:1px solid var(--line)}}
.mast{{height:62px;padding:0 42px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--line);gap:20px}}.brand{{font-size:12px;letter-spacing:.08em}}.brand span{{color:var(--faint);margin-left:10px}}.mast-meta{{display:flex;gap:8px;align-items:center}}.mast-meta span{{font-size:10px;color:var(--subtle);padding:5px 8px;border:1px solid var(--line);background:#fff}}
.hero{{padding:48px 42px 44px 35px;border-bottom:1px solid var(--line);border-left:7px solid var(--accent-wash);display:grid;grid-template-columns:minmax(0,1fr) 210px;gap:48px;align-items:end;background:var(--paper)}}.eyebrow{{font-size:10px;letter-spacing:.2em;color:var(--accent);font-weight:700}}.hero h1{{font-family:"Songti SC","STSong",Georgia,serif;font-size:clamp(86px,11vw,126px);font-weight:500;letter-spacing:-.09em;line-height:.82;margin:20px 0 13px;color:var(--accent)}}.hero-en{{font-size:10px;letter-spacing:.34em;color:var(--accent-deep);font-weight:700}}.headline{{font-family:"Songti SC","STSong",Georgia,serif;font-size:24px;line-height:1.45;margin:30px 0 8px;max-width:720px}}.synthesis{{font-size:14px;line-height:1.8;color:var(--subtle);margin:0;max-width:730px}}.confidence-panel{{border:1px solid var(--line);background:#fff;padding:18px 17px}}.confidence-panel>span{{display:block;font-size:9px;letter-spacing:.16em;color:var(--faint);margin-bottom:12px}}.confidence-metric{{padding:12px 0;border-top:1px solid var(--line)}}.confidence-metric:first-of-type{{border-top:0;padding-top:0}}.confidence-metric small{{display:block;font-size:10px;color:var(--subtle)}}.confidence-metric strong{{display:block;font-family:"Songti SC",Georgia,serif;font-size:30px;color:var(--accent);font-weight:500;margin-top:4px}}.confidence-panel p{{font-size:10px;color:var(--faint);line-height:1.5;margin:7px 0 0}}
.unavailable{{margin:24px 42px 0;padding:18px;border:1px solid var(--accent);background:var(--accent-wash)}}.unavailable p{{margin:6px 0 0;font-size:13px;color:var(--subtle)}}section{{padding:42px;border-bottom:1px solid var(--line)}}.section-head{{display:flex;justify-content:space-between;align-items:baseline;gap:22px;margin-bottom:26px}}.section-title{{display:flex;gap:12px;align-items:center}}.section-title b{{font-family:Georgia,serif;font-size:12px;color:var(--accent);font-weight:500}}.section-title h2{{font-size:14px;margin:0}}.section-head>small{{font-size:10px;color:var(--faint);text-align:right}}.subsection+.subsection{{margin-top:42px;padding-top:34px;border-top:1px solid var(--line)}}.subsection-head{{display:flex;justify-content:space-between;align-items:baseline;gap:18px;margin-bottom:20px}}.subsection-head h3{{font-size:12px;margin:0}}.subsection-head small{{font-size:9px;color:var(--faint);text-align:right}}
.flows{{border-top:1px solid var(--line)}}.flow-row{{display:grid;grid-template-columns:135px 135px minmax(0,1fr);border-bottom:1px solid var(--line);padding:20px 0;gap:20px;align-items:start}}.flow-side small{{display:block;color:var(--faint);font-size:9px;letter-spacing:.12em;margin-bottom:7px}}.flow-side strong{{font-family:"Songti SC",Georgia,serif;font-size:21px;font-weight:500}}.destination strong{{color:var(--accent)}}.flow-copy{{border-left:1px solid var(--line);padding-left:20px}}.confidence-word{{font-size:9px;color:var(--accent);letter-spacing:.12em}}.flow-copy p{{font-size:13px;line-height:1.65;margin:7px 0 0}}
.citations{{display:flex;flex-wrap:wrap;gap:5px;margin-top:9px}}.cite{{border:1px solid var(--line);background:#f7f7f3;color:var(--subtle);font-size:9px;padding:4px 6px;cursor:pointer;border-radius:0}}.cite:hover,.cite:focus-visible{{border-color:var(--accent);color:var(--accent-deep);outline:none}}
.chain{{list-style:none;margin:0;padding:0;max-width:820px}}.chain li{{display:grid;grid-template-columns:34px minmax(0,1fr);gap:18px;padding:0 0 26px;position:relative}}.chain li:not(:last-child)::before{{content:"";position:absolute;top:22px;bottom:3px;left:15px;border-left:1px solid var(--line)}}.chain-index{{font-family:Georgia,serif;color:var(--accent);background:var(--paper);font-size:12px;padding-top:5px;z-index:1}}.claim{{display:inline-block;font-size:9px;letter-spacing:.1em;padding:3px 6px;background:var(--observed);color:#52615a}}.claim.inferred{{background:var(--inferred);color:#6b5479}}.chain p{{font-family:"Songti SC",Georgia,serif;font-size:21px;line-height:1.55;margin:7px 0 0}}
.trade-plan{{border-top:2px solid var(--accent)}}.trade-row{{padding:22px 0;border-bottom:1px solid var(--line)}}.trade-row header{{display:grid;grid-template-columns:70px minmax(0,1fr) auto;gap:14px;align-items:baseline}}.trade-row header span{{font-size:9px;color:var(--accent);letter-spacing:.1em}}.trade-row header strong{{font-family:"Songti SC",Georgia,serif;font-size:22px;font-weight:500}}.trade-row header small{{color:var(--subtle);font-size:11px}}.trade-body{{display:grid;grid-template-columns:1fr 1fr;gap:30px;margin:17px 0 13px;padding-left:84px}}.trade-body b{{font-size:10px;color:var(--faint);font-weight:600}}.trade-body p{{font-size:13px;line-height:1.65;margin:5px 0 0}}.trade-row footer{{display:flex;justify-content:flex-end;gap:18px;align-items:flex-start;padding-left:84px}}.trade-row footer .citations{{margin-top:0;justify-content:flex-end}}
.cross-head,.market-row{{display:grid;grid-template-columns:minmax(155px,1.6fr) repeat(3,minmax(70px,.7fr));gap:14px;align-items:center}}.cross-head{{font-size:9px;color:var(--faint);letter-spacing:.08em;padding:0 0 8px;border-bottom:1px solid var(--line)}}.cross-head span:not(:first-child){{text-align:right}}.market-row{{padding:10px 0;border-bottom:1px solid var(--line)}}.market-row>div{{min-width:0}}.market-row strong{{display:block;font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}.market-row small{{display:block;color:var(--faint);font-size:9px;margin-top:2px}}.number{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11px;text-align:right;font-variant-numeric:tabular-nums}}.positive{{color:var(--positive)}}.negative{{color:var(--negative)}}
.relative-list{{display:grid;grid-template-columns:1fr 1fr;gap:0 30px;border-top:1px solid var(--line)}}.relative-row{{display:grid;grid-template-columns:minmax(130px,1fr) 90px 58px;gap:10px;align-items:center;padding:13px 0;border-bottom:1px solid var(--line)}}.relative-row strong{{display:block;font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}.relative-row small{{display:block;font-size:9px;color:var(--faint);margin-top:3px}}.relative-row canvas{{width:90px;height:30px;display:block}}
.charts{{display:grid;grid-template-columns:1fr 1fr;gap:18px}}.chart-card{{border:1px solid var(--line);background:#fff;padding:15px;min-width:0}}.chart-card header{{display:flex;justify-content:space-between;gap:10px;align-items:baseline}}.chart-card header div{{display:flex;gap:9px;align-items:baseline;min-width:0}}.chart-card header span{{font-size:9px;color:var(--accent)}}.chart-card h3{{font-size:12px;margin:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}.chart-card header small{{font-size:8px;color:var(--faint);white-space:nowrap}}.chart-card>canvas{{width:100%;height:165px;display:block;margin:10px 0}}.chart-card footer{{display:flex;gap:14px;color:var(--subtle);font-size:9px}}
.boundary{{padding:30px 42px 42px;background:#f1efe8;border-bottom:7px solid var(--accent);font-size:10px;line-height:1.8;color:var(--subtle)}}.boundary strong{{color:var(--ink)}}.boundary code{{display:block;margin-top:9px;overflow-wrap:anywhere;word-break:break-all;color:var(--faint)}}
dialog{{width:min(560px,calc(100% - 32px));border:1px solid var(--line);padding:0;background:var(--paper);color:var(--ink);box-shadow:0 22px 70px rgba(20,20,15,.22)}}dialog::backdrop{{background:rgba(20,22,19,.35)}}.evidence-dialog header{{padding:20px 22px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;gap:18px;align-items:start}}.evidence-dialog h3{{font-family:"Songti SC",Georgia,serif;font-size:22px;margin:0}}.evidence-dialog button{{border:1px solid var(--line);background:#fff;padding:5px 9px;cursor:pointer}}.evidence-body{{padding:20px 22px}}.evidence-body dl{{display:grid;grid-template-columns:110px 1fr;gap:8px 14px;margin:0}}.evidence-body dt{{font-size:10px;color:var(--faint)}}.evidence-body dd{{font-size:12px;margin:0;overflow-wrap:anywhere}}
@media(max-width:720px){{main{{border:0}}.mast{{height:auto;min-height:58px;padding:14px 20px;align-items:flex-start}}.brand{{white-space:nowrap}}.brand span{{display:none}}.mast-meta{{flex-wrap:wrap;justify-content:flex-end}}.mast-meta span{{font-size:8px;padding:4px 6px}}.hero{{padding:38px 20px 32px 14px;border-left-width:6px;grid-template-columns:1fr;gap:26px;background:var(--paper)}}.hero h1{{font-size:90px;margin-top:18px}}.headline{{font-size:21px;margin-top:25px}}.synthesis{{font-size:13px}}.confidence-panel{{display:grid;grid-template-columns:1fr 1fr;gap:0 20px}}.confidence-panel>span{{grid-column:1/-1}}.confidence-metric:nth-of-type(2){{border-top:0;padding-top:0}}.confidence-panel p{{grid-column:1/-1}}.unavailable{{margin:18px 20px 0}}section{{padding:34px 20px}}.section-head,.subsection-head{{align-items:flex-start}}.section-head>small,.subsection-head>small{{max-width:140px}}.flow-row{{grid-template-columns:1fr 1fr;gap:13px;padding:18px 0}}.flow-copy{{grid-column:1/-1;border-left:0;border-top:1px solid var(--line);padding:13px 0 0}}.chain p{{font-size:19px}}.trade-row header{{grid-template-columns:62px minmax(0,1fr)}}.trade-row header small{{grid-column:2}}.trade-body{{grid-template-columns:1fr;padding-left:0;gap:13px}}.trade-row footer{{padding-left:0;display:block}}.trade-row footer .citations{{justify-content:flex-start;margin-top:9px}}.cross-head,.market-row{{grid-template-columns:minmax(115px,1.3fr) repeat(3,minmax(54px,.7fr));gap:7px}}.market-row strong{{font-size:11px}}.number{{font-size:9px}}.relative-list,.charts{{grid-template-columns:1fr}}.relative-row{{grid-template-columns:minmax(120px,1fr) 78px 52px}}.relative-row canvas{{width:78px}}.chart-card>canvas{{height:155px}}.boundary{{padding:26px 20px 34px}}}}
@media print{{body{{background:#fff}}main{{width:100%;border:0}}.cite{{color:var(--subtle)}}dialog{{display:none}}}}
</style></head>
<body><main>
<header class="mast"><div class="brand">K 线世界日报 <span>Capital Flow World Model</span></div><div class="mast-meta"><span>{escape(str(report.get("report_date") or ""))}</span><span>{escape(status_label)}</span><span>{escape(data_label)}</span></div></header>
<div class="hero"><div><div class="eyebrow">今日市场姿态 / MARKET POSTURE</div><h1>{escape(str(report.get("posture_zh") or ""))}</h1><div class="hero-en">{escape(str(report.get("posture_en") or ""))}</div><p class="headline">{escape(str(world.get("headline") or ""))}</p><p class="synthesis">{escape(str(world.get("synthesis") or ""))}</p><div class="citations">{_cite_html(world.get("citations") or [])}</div></div><aside class="confidence-panel"><span>代码计算，不由模型改写</span><div class="confidence-metric"><small>证据质量</small><strong>{escape(CONFIDENCE_ZH.get(str(evidence_quality.get("level")), str(evidence_quality.get("level") or "—")))}</strong></div><div class="confidence-metric"><small>方向清晰度</small><strong>{escape(CONFIDENCE_ZH.get(str(clarity.get("level")), str(clarity.get("level") or "—")))}</strong></div><p>覆盖率 {_fmt(evidence_quality.get("coverage_ratio"))} · 清晰度 {_fmt(clarity.get("score"))}</p></aside></div>
{unavailable}
<section id="charts"><div class="section-head"><div class="section-title"><b>01</b><h2>17 张完成日线证据</h2></div><small>价格为 OHLC K 线；收益率与曲线为折线</small></div><div class="charts">{chart_html}</div></section>
<section id="flow-map"><div class="section-head"><div class="section-title"><b>02</b><h2>资金可能正在从哪里，流向哪里？</h2></div><small>相对价格推断，不等于直接资金流测量</small></div><div class="flows">{flow_html}</div></section>
<section id="model-and-trades"><div class="section-head"><div class="section-title"><b>03</b><h2>世界模型如何传导，以及怎样交易？</h2></div><small>推断与建议分层展示</small></div><div class="subsection" id="transmission"><div class="subsection-head"><h3>传导链</h3><small>已观察与模型推断分开标记</small></div><ol class="chain">{chain_html}</ol></div><div class="subsection" id="trade-plan"><div class="subsection-head"><h3>可执行交易建议</h3><small>模型建议 · 未人工复核 · 不自动执行</small></div><div class="trade-plan">{trade_html}</div></div></section>
<section id="market-evidence"><div class="section-head"><div class="section-title"><b>04</b><h2>17 个市场与 12 组相对领导关系</h2></div><small>横截面与相对强弱放在一起看</small></div><div class="subsection" id="cross-section"><div class="subsection-head"><h3>17 个市场观测</h3><small>美债变化统一用 bp</small></div><div class="cross-head"><span>市场</span><span>5日</span><span>20日</span><span>60日</span></div><div>{cross_html}</div></div><div class="subsection" id="relative-leadership"><div class="subsection-head"><h3>12 组相对领导关系</h3><small>标准化相对表现 · 20日领导端</small></div><div class="relative-list">{relationship_html}</div></div></section>
<footer class="boundary"><strong>研究边界：</strong>模型生成、未经人工复核；本页包含市场层面的交易建议。仅限 Park 本地评估，当前数据权利不支持公开分发。<br>系统不会自动执行交易，不读取经纪账户，不修改任何持仓。Finance Daily Newsletter 不是本页输入，两个 Track 只做人工对照。<code>{escape(str(report.get("report_id") or ""))}</code></footer>
</main>
<dialog id="evidence-dialog" class="evidence-dialog"><header><h3 id="evidence-title">证据</h3><button type="button" id="evidence-close">关闭</button></header><div class="evidence-body"><dl id="evidence-fields"></dl></div></dialog>
<script id="report-data" type="application/json">{embedded}</script>
<script>
const REPORT=JSON.parse(document.getElementById('report-data').textContent);
const CSS=getComputedStyle(document.documentElement),UP=CSS.getPropertyValue('--positive').trim(),DOWN=CSS.getPropertyValue('--negative').trim(),ACCENT=CSS.getPropertyValue('--accent').trim(),GRID='#ecece6',TEXT='#767d77';
function fit(canvas){{const r=canvas.getBoundingClientRect(),d=Math.max(1,window.devicePixelRatio||1);canvas.width=Math.round(r.width*d);canvas.height=Math.round(r.height*d);const c=canvas.getContext('2d');c.setTransform(d,0,0,d,0,0);return[c,r.width,r.height]}}
function drawSeries(canvas,chart){{const[c,w,h]=fit(canvas),rows=(chart.points||[]).slice(-70),line=chart.chart_type==='line',values=rows.flatMap(r=>line?[Number(r.value)]:[Number(r.high),Number(r.low)]).filter(Number.isFinite);if(!values.length)return;let lo=Math.min(...values),hi=Math.max(...values);if(hi===lo){{hi+=1;lo-=1}}const p={{l:7,r:7,t:10,b:17}},y=v=>p.t+(hi-v)/(hi-lo)*(h-p.t-p.b),step=(w-p.l-p.r)/Math.max(rows.length,1);c.clearRect(0,0,w,h);c.strokeStyle=GRID;c.lineWidth=1;for(let i=0;i<4;i++){{const yy=p.t+i*(h-p.t-p.b)/3;c.beginPath();c.moveTo(p.l,yy);c.lineTo(w-p.r,yy);c.stroke()}}if(line){{c.strokeStyle=ACCENT;c.lineWidth=1.6;c.beginPath();rows.forEach((r,i)=>{{const x=p.l+(i+.5)*step,yy=y(Number(r.value));i?c.lineTo(x,yy):c.moveTo(x,yy)}});c.stroke()}}else{{rows.forEach((r,i)=>{{const o=Number(r.open),cl=Number(r.close),high=Number(r.high),low=Number(r.low),x=p.l+(i+.5)*step,color=cl>=o?UP:DOWN,width=Math.max(1.2,Math.min(5,step*.58)),top=Math.min(y(o),y(cl)),bodyHeight=Math.max(1,Math.abs(y(o)-y(cl)));c.strokeStyle=color;c.lineWidth=1;c.beginPath();c.moveTo(x,y(high));c.lineTo(x,y(low));c.stroke();if(cl>=o){{c.strokeStyle=UP;c.strokeRect(x-width/2,top,width,bodyHeight)}}else{{c.fillStyle=DOWN;c.fillRect(x-width/2,top,width,bodyHeight)}}}})}}c.fillStyle=TEXT;c.font='8px -apple-system,sans-serif';c.fillText(rows[0]?.date||'',p.l,h-3);c.textAlign='right';c.fillText(rows.at(-1)?.date||'',w-p.r,h-3);c.textAlign='left'}}
function drawRelative(canvas,row){{const[c,w,h]=fit(canvas),points=(row.points||[]).slice(-45),values=points.map(x=>Number(x.relative_index)).filter(Number.isFinite);if(!values.length)return;let lo=Math.min(...values),hi=Math.max(...values);if(hi===lo){{hi+=1;lo-=1}}const x=i=>i/(Math.max(values.length-1,1))*w,y=v=>3+(hi-v)/(hi-lo)*(h-6);c.clearRect(0,0,w,h);c.strokeStyle=ACCENT;c.lineWidth=1.3;c.beginPath();values.forEach((v,i)=>i?c.lineTo(x(i),y(v)):c.moveTo(x(i),y(v)));c.stroke()}}
function redraw(){{for(const canvas of document.querySelectorAll('canvas[data-chart]')){{const chart=REPORT.charts.find(x=>x.key===canvas.dataset.chart);if(chart)drawSeries(canvas,chart)}}for(const canvas of document.querySelectorAll('canvas[data-relative]')){{const row=REPORT.relationships.find(x=>x.key===canvas.dataset.relative);if(row)drawRelative(canvas,row)}}}}
const evidence=new Map();for(const section of [REPORT.world_model,REPORT.regime,...REPORT.flow_map,...REPORT.transmission_chain,...REPORT.trade_plan,...REPORT.contradictions,...REPORT.falsifiers]){{for(const item of section?.citations||[])evidence.set(item.reference_id,item)}}
const dialog=document.getElementById('evidence-dialog'),fields=document.getElementById('evidence-fields'),title=document.getElementById('evidence-title');
document.addEventListener('click',event=>{{const button=event.target.closest('[data-evidence]');if(!button)return;const item=evidence.get(button.dataset.evidence);if(!item)return;title.textContent=item.label||item.key||'证据';const rows=[['引用 ID',item.reference_id],['类型',item.kind],['完成日',item.session||'—'],['质量',item.quality||'—'],[item.metric_label||'指标',`${{item.metric_value??'—'}} ${{item.metric_unit==='basis_points'?'bp':item.metric_unit==='percent_return'?'%':''}}`],['20日领导端',item.leader||'—']];fields.replaceChildren(...rows.flatMap(([key,value])=>{{const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=key;dd.textContent=String(value);return[dt,dd]}}));dialog.showModal()}});
document.getElementById('evidence-close').addEventListener('click',()=>dialog.close());
redraw();let resizeTimer;addEventListener('resize',()=>{{clearTimeout(resizeTimer);resizeTimer=setTimeout(redraw,100)}});
</script></body></html>'''


class KlineWorldReportStore:
    """Publish immutable JSON/HTML/Markdown and atomically advance one pointer."""

    def __init__(
        self,
        context_store: KlineWorldContextStore,
        world_model_store: KlineWorldModelStore,
        root: Path | str,
        output_root: Path | str,
        *,
        allow_fixture: bool = False,
    ) -> None:
        self.context_store = context_store
        self.world_model_store = world_model_store
        self.root = Path(root).expanduser().resolve()
        self.output_root = Path(output_root).expanduser().resolve()
        self.allow_fixture = allow_fixture

    def compile_latest(self, *, generated_at: datetime) -> dict[str, Any]:
        context = self.context_store.latest()
        model = self.world_model_store.latest(expected_context_id=str(context["context_id"]))
        report = build_world_report(
            context=context,
            world_model=model,
            generated_at=generated_at,
            allow_fixture=self.allow_fixture,
        )
        return self.publish(report)

    def publish(self, report: Mapping[str, Any]) -> dict[str, Any]:
        context = self.context_store.latest()
        model = self.world_model_store.latest(expected_context_id=str(context["context_id"]))
        validated = validate_world_report(
            report,
            context=context,
            world_model=model,
            allow_fixture=self.allow_fixture,
        )
        if validated.get("data_kind") != "real" and not self.allow_fixture:
            raise KlineWorldReportError("fixture_report_publication_forbidden")
        digest = str(validated["report_id"]).removeprefix(REPORT_ID_PREFIX)
        report_ref = {"path": f"artifacts/{digest}.json"}
        html_ref = {"path": f"artifacts/{digest}.html"}
        markdown_ref = {"path": f"artifacts/{digest}.md"}
        report_ref["sha256"] = _immutable_bytes(self.root / report_ref["path"], _json_bytes(validated))
        html_ref["sha256"] = _immutable_bytes(self.output_root / html_ref["path"], render_html(validated).encode("utf-8"))
        markdown_ref["sha256"] = _immutable_bytes(self.output_root / markdown_ref["path"], render_markdown(validated).encode("utf-8"))
        receipt = {
            "schema_version": SCHEMA_VERSION,
            "event": "completed",
            "report_id": validated["report_id"],
            "context_id": validated["context_id"],
            "world_model_id": validated["world_model_id"],
            "report": report_ref,
            "html": html_ref,
            "markdown": markdown_ref,
            "truth_boundary": validated["truth_boundary"],
        }
        receipt_ref = {"path": f"receipts/{digest}.json"}
        receipt_ref["sha256"] = _immutable_bytes(self.root / receipt_ref["path"], _json_bytes(receipt))
        state = {
            "schema_version": SCHEMA_VERSION,
            "report_id": validated["report_id"],
            "context_id": validated["context_id"],
            "world_model_id": validated["world_model_id"],
            "report": report_ref,
            "html": html_ref,
            "markdown": markdown_ref,
            "receipt": receipt_ref,
        }
        state_path = self.root / "state.json"
        prior = state_path.read_bytes() if state_path.exists() else None
        _atomic_bytes(state_path, _json_bytes(state))
        try:
            self.latest()
        except Exception:
            if prior is None:
                state_path.unlink(missing_ok=True)
            else:
                _atomic_bytes(state_path, prior)
            raise
        return state

    def latest(self) -> tuple[dict[str, Any], dict[str, Any]]:
        try:
            state = json.loads((self.root / "state.json").read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            raise KlineWorldReportError("report_latest_unavailable") from exc
        required = {"schema_version", "report_id", "context_id", "world_model_id", "report", "html", "markdown", "receipt"}
        if not isinstance(state, dict) or set(state) != required or state.get("schema_version") != SCHEMA_VERSION:
            raise KlineWorldReportError("report_state_invalid")
        report_id = str(state.get("report_id") or "")
        if not report_id.startswith(REPORT_ID_PREFIX):
            raise KlineWorldReportError("report_state_identity_invalid")
        digest = report_id.removeprefix(REPORT_ID_PREFIX)
        expected_paths = {
            "report": (self.root, f"artifacts/{digest}.json"),
            "html": (self.output_root, f"artifacts/{digest}.html"),
            "markdown": (self.output_root, f"artifacts/{digest}.md"),
            "receipt": (self.root, f"receipts/{digest}.json"),
        }
        payloads: dict[str, bytes] = {}
        for key, (base, expected_path) in expected_paths.items():
            reference = state.get(key)
            if not isinstance(reference, dict) or set(reference) != {"path", "sha256"} or reference.get("path") != expected_path:
                raise KlineWorldReportError(f"report_{key}_reference_invalid")
            target = (base / expected_path).resolve()
            if base not in target.parents:
                raise KlineWorldReportError("report_path_escape")
            try:
                payloads[key] = target.read_bytes()
            except FileNotFoundError as exc:
                raise KlineWorldReportError(f"report_{key}_unavailable") from exc
            if sha256(payloads[key]).hexdigest() != reference.get("sha256"):
                raise KlineWorldReportError(f"report_{key}_hash_mismatch")
        try:
            report = json.loads(payloads["report"])
            receipt = json.loads(payloads["receipt"])
        except json.JSONDecodeError as exc:
            raise KlineWorldReportError("report_artifact_invalid") from exc
        context = self.context_store.latest()
        model = self.world_model_store.latest(expected_context_id=str(context["context_id"]))
        validated = validate_world_report(
            report,
            context=context,
            world_model=model,
            allow_fixture=self.allow_fixture,
        )
        expected_receipt = {
            "schema_version": SCHEMA_VERSION,
            "event": "completed",
            "report_id": validated["report_id"],
            "context_id": validated["context_id"],
            "world_model_id": validated["world_model_id"],
            "report": state["report"],
            "html": state["html"],
            "markdown": state["markdown"],
            "truth_boundary": validated["truth_boundary"],
        }
        if receipt != expected_receipt:
            raise KlineWorldReportError("report_receipt_identity_mismatch")
        if state["context_id"] != validated["context_id"] or state["world_model_id"] != validated["world_model_id"]:
            raise KlineWorldReportError("report_source_identity_mismatch")
        if payloads["html"] != render_html(validated).encode("utf-8") or payloads["markdown"] != render_markdown(validated).encode("utf-8"):
            raise KlineWorldReportError("report_render_replay_mismatch")
        return state, validated
