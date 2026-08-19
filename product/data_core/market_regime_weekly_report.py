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


SCHEMA_VERSION = "market-regime-weekly-report-v6"
RENDERER_VERSION = "market-regime-weekly-report-renderer-v12"
REPORT_ID_PREFIX = "market-regime-weekly-report:"
CHAPTERS = (
    ("money_price", "钱的价格", ("dxy", "us2y", "us10y", "us2s10s")),
    ("risk_assets", "风险资产", ("sp500", "nasdaq", "us_dividend", "vix", "bitcoin")),
    ("asia_a_share", "亚洲与 A 股", ("shanghai", "star50", "china_dividend", "nikkei", "kospi")),
    ("real_assets", "实物资产", ("wti", "gold", "silver")),
)


class WeeklyReportError(ValueError):
    """Weekly report projection or reader contract failed closed."""


_STANDARD_KLINE_JS_PATH = Path(__file__).resolve().parents[1] / "vendor" / "standard-kline.f6c1bd4.js"


def _standard_kline_js() -> str:
    try:
        source = _STANDARD_KLINE_JS_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        raise WeeklyReportError("standard_kline_asset_missing") from exc
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


def _chart_slot(
    key: str,
    timeframe: str,
    series: Mapping[str, Any],
    *,
    candle_response: Mapping[str, Any] | None = None,
    cutoff_at: Any = None,
) -> dict[str, Any]:
    standard_kline = None
    if isinstance(candle_response, Mapping):
        try:
            standard_kline = build_standard_kline_payload(candle_response)
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
        "renderer": standard_kline.get("renderer") if isinstance(standard_kline, Mapping) else None,
        "renderer_options": standard_kline.get("renderer_options") if isinstance(standard_kline, Mapping) else standard_kline_options_for_response({"series_kind": (candle_response or series).get("series_kind")}),
    }


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
        odds_valid = False
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
            try:
                odds_value = analysis.get("odds")
                structure_value = analysis.get("structure")
                odds_timeframe = odds_value.get("timeframe") if isinstance(odds_value, Mapping) else None
                timeframe_structure = structure_value.get("timeframes", {}).get(odds_timeframe) if isinstance(structure_value, Mapping) and isinstance(structure_value.get("timeframes"), Mapping) else None
                timeframe_evidence = timeframe_structure.get("evidence_ids", []) if isinstance(timeframe_structure, Mapping) else []
                allowed_evidence_ids = {str(item) for item in timeframe_evidence if isinstance(item, str)}
                allowed_feature_ids = {str(item) for item in allowed_evidence_ids if item.startswith("feature:")}
                validate_odds(odds_value, allowed_feature_ids=allowed_feature_ids, allowed_evidence_ids=allowed_evidence_ids)
                odds_valid = True
            except WeeklyOddsError:
                odds_valid = False
        if (
            not isinstance(analysis, Mapping)
            or analysis.get("generation_status") != "model_generated_unreviewed"
            or not isinstance(analysis.get("position"), Mapping)
            or not isinstance(analysis.get("structure"), Mapping)
            or not theory_valid
            or not odds_valid
            or not analysis_identity_valid
        ):
            analysis_status = "analysis_unavailable"
            failure_code = (analysis or {}).get("failure_code", "analysis_missing")
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
                "summary": {
                    "order": ["position", "structure", "odds", "synthesis", "theoretical_implication"],
                    "position": unavailable_position,
                    "structure": unavailable_structure,
                    "odds": unavailable_odds,
                    "synthesis": unavailable_synthesis,
                    "theoretical_implication": unavailable_theory,
                },
            }
        else:
            analysis_status = "validated"
            analysis_view = {
                "status": analysis_status,
                "analysis_id": analysis.get("analysis_id"),
                "weekly": analysis.get("weekly"),
                "daily": analysis.get("daily"),
                "four_hour": analysis.get("four_hour"),
                "position": analysis.get("position"),
                "structure": analysis.get("structure"),
                "odds": analysis.get("odds"),
                "synthesis": analysis.get("synthesis"),
                "agreement": analysis.get("agreement"),
                "confirmation": analysis.get("confirmation"),
                "invalidation": analysis.get("invalidation"),
                "opportunity_state": analysis.get("opportunity_state"),
                "rationale": analysis.get("rationale"),
                "theoretical_implication": analysis.get("theoretical_implication"),
                "summary": {
                    "order": ["position", "structure", "odds", "synthesis", "theoretical_implication"],
                    "position": analysis.get("position"),
                    "structure": analysis.get("structure"),
                    "odds": analysis.get("odds"),
                    "synthesis": analysis.get("synthesis"),
                    "theoretical_implication": analysis.get("theoretical_implication"),
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
            "display_name": DISPLAY_NAMES[key],
            "series_kind": series.get("series_kind"),
            "quality": series.get("quality", "unknown"),
            "analysis_status": analysis_status,
            "analysis": analysis_view,
            "chart_slots": slots,
        })
    core = {
        "schema_version": SCHEMA_VERSION,
        "renderer_version": RENDERER_VERSION,
        "week_end": source_snapshot.get("week_end"),
        "cutoff_at": source_snapshot.get("cutoff_at"),
        "source_status": source_snapshot.get("status"),
        "cards": cards,
        "chart_slots": chart_slots,
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


def render_weekly_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        f"# 宏观 K 线周报｜{report.get('week_end')}",
        "",
        "> 模型生成、未经人工复核；仅限本地评估；不自动执行交易。",
        "",
        f"周末日期：{report.get('week_end')} · 分析截止：{report.get('week_end')} · 先完成全部资产分析，再进行机会排序。",
        "",
    ]
    for _, chapter, keys in CHAPTERS:
        lines.extend([f"## {chapter}", ""])
        for key in keys:
            card = next(item for item in report["cards"] if item["asset_key"] == key)
            analysis = card["analysis"]
            lines.extend([f"### {card['display_name']}", ""])
            position = analysis.get("position") if isinstance(analysis, Mapping) else None
            structure = analysis.get("structure") if isinstance(analysis, Mapping) else None
            if isinstance(position, Mapping) or isinstance(structure, Mapping):
                lines.extend([f"**位置**：{(position or {}).get('text', '不可用。') if isinstance(position, Mapping) else '不可用。'}", f"**结构**：{(structure or {}).get('text', '不可用。') if isinstance(structure, Mapping) else '不可用。'}", ""])
            odds = analysis.get("odds") if isinstance(analysis, Mapping) else None
            lines.extend([f"**赔率**：{_odds_reader_text(odds)}", ""])
            for tf, label in (("weekly", "周线"), ("daily", "日线"), ("four_hour", "4小时")):
                statement = analysis.get(tf) if isinstance(analysis, Mapping) else None
                if statement:
                    lines.extend([f"**{label}**：{statement.get('text')}", ""])
                elif tf == "four_hour" and key in CONTEXT_4H_KEYS:
                    lines.extend(["**4小时**：当前4小时上下文不可用。", ""])
            synthesis = analysis.get("synthesis") if isinstance(analysis, Mapping) else None
            lines.extend([f"**多周期结论**：{(synthesis or {}).get('text', '当前分析不可用。')}", ""])
            implication = analysis.get("theoretical_implication") if isinstance(analysis, Mapping) else None
            lines.extend([f"**这意味着什么（机制解释）**：{(implication or {}).get('text', '当前机制解释不可用。')}", ""])
    lines.extend(["## 本周机会排序", ""])
    for row in (report.get("ranking") or {}).get("ordered_assets") or []:
        key = str(row.get("asset_key") or "")
        lines.append(f"- {DISPLAY_NAMES.get(key, key)}：{_ranking_status_label(row.get('status'))}")
    return "\n".join(lines) + "\n"


def _reader_html_labels(renderer: Any) -> Any:
    def wrapped(report: Mapping[str, Any]) -> str:
        return renderer(report).replace("WEEK_END ", "周末日期 ")
    return wrapped


def _render_standard_kline_document(
    report: Mapping[str, Any],
    nav_parts: list[str],
    pane_parts: list[str],
    ranking_rows: str,
) -> str:
    """Render the Weekly reader with the pinned standard-kline browser port."""

    report_json = _canonical(report).replace("</", "<\\/")
    standard_kline_js = _standard_kline_js()
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>宏观 K 线周报｜{_escape(report.get("week_end"))}</title><style>
:root{{--ink:#17201b;--muted:#68736b;--faint:#9aa39c;--line:#dedfd8;--paper:#fffefa;--canvas:#f1efe9;--green:#187b51;--red:#c94640;--navy:#3f586e;--font-display:"Avenir Next","SF Pro Display",-apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;--font-body:-apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif}}*{{box-sizing:border-box}}html,body{{margin:0;background:var(--canvas);color:var(--ink);font-family:var(--font-body)}}main{{width:min(1240px,100%);margin:auto;background:var(--paper);min-height:100vh}}.top{{padding:20px 34px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;gap:12px}}.top b{{font-family:var(--font-display);letter-spacing:.04em;font-weight:650}}.top span{{font-size:10px;border:1px solid var(--line);padding:5px 8px;color:var(--muted)}}.hero{{padding:44px 34px;border-bottom:1px solid var(--line);background:#f5f7f1}}.hero h1{{font-family:var(--font-display);font-size:72px;font-weight:650;letter-spacing:-.035em;color:var(--navy);margin:14px 0}}.hero p{{color:var(--muted);line-height:1.7}}.body{{display:grid;grid-template-columns:190px 1fr;gap:22px;padding:34px}}nav{{position:sticky;top:16px;align-self:start;border:1px solid var(--line);background:#fff;padding:14px}}nav h4{{font-size:9px;color:var(--green);margin:12px 0 4px}}nav button{{display:block;width:100%;border:0;border-bottom:1px solid #f0f0eb;background:#fff;text-align:left;padding:7px 3px;color:var(--muted);cursor:pointer}}nav button.active{{color:var(--green);font-weight:700}}.asset-pane{{display:none;border:1px solid var(--line);background:#fff}}.asset-pane.active{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));align-items:stretch}}.asset-pane[data-timeframes="2"].active{{grid-template-columns:repeat(2,minmax(0,1fr))}}.asset-pane>header{{grid-column:1/-1;display:flex;justify-content:space-between;padding:17px;border-bottom:1px solid var(--line)}}.asset-pane h2{{font-family:var(--font-display);font-size:27px;font-weight:650;letter-spacing:-.02em;margin:0}}.asset-pane header small{{color:var(--faint)}}.timeframe{{display:flex;flex-direction:column;gap:12px;padding:16px;border-right:1px solid var(--line);border-bottom:1px solid var(--line);min-width:0}}.timeframe b{{display:block;color:var(--green);font-size:10px;letter-spacing:.12em;margin-bottom:7px}}.standard-kline-mount{{display:block;width:100%;height:320px;min-width:0;background:#fffefa;border:1px solid #eceee8;overflow:hidden}}.chart-legend{{display:block;margin-top:5px;color:var(--faint);font-size:10px}}.chart-unavailable{{height:100%;display:grid;place-items:center;padding:16px;text-align:center;color:#8a6425;background:#fff8ed;font-size:13px;line-height:1.6}}.timeframe p{{font-family:var(--font-body);font-size:17px;line-height:1.75;letter-spacing:.01em;margin:0}}.summary-dimensions{{grid-column:1/-1;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;padding:14px 16px;background:#f7f9f5;border-bottom:1px solid var(--line)}}.summary-dimensions>div{{border-left:3px solid var(--green);padding-left:10px}}.summary-dimensions b{{font-size:10px;color:var(--green);letter-spacing:.1em}}.summary-dimensions p{{font-family:var(--font-body);font-size:15px;line-height:1.55;margin:4px 0}}.synthesis{{grid-column:1/-1;padding:17px;background:#edf3ef}}.synthesis b{{font-size:10px;color:var(--green);letter-spacing:.1em}}.synthesis p{{font-family:var(--font-body);font-size:18px;font-weight:500;line-height:1.65;letter-spacing:.01em;margin:6px 0}}.ranking{{padding:34px;background:#f5f3ed}}.ranking h2{{font-family:var(--font-display);font-weight:650;letter-spacing:-.02em;font-size:30px}}.ranking li{{display:inline-block;margin:4px 12px 4px 0}}footer{{padding:25px 34px;color:var(--faint);font-size:10px}}footer code{{word-break:break-all}}@media(max-width:760px){{.top,.hero,.body,.ranking{{padding:20px 18px}}.top{{display:block}}.top span{{display:inline-block;margin-top:8px}}.hero h1{{font-size:55px}}.body{{display:block}}nav{{position:static;display:flex;overflow:auto;gap:6px;margin-bottom:15px}}nav h4{{display:none}}nav button{{min-width:max-content;border:1px solid var(--line);padding:7px 9px}}.asset-pane[data-timeframes="2"].active,.asset-pane[data-timeframes="3"].active{{grid-template-columns:1fr}}.timeframe{{border-right:0}}.summary-dimensions{{grid-template-columns:1fr}}.timeframe p{{font-size:17px}}.standard-kline-mount{{height:320px}}}}
</style></head><body><main><header class="top"><b>宏观 K 线周报</b><span>模型生成、未经人工复核 · 本地评估 · 无自动执行</span></header><section class="hero"><h1>本周宏观图谱</h1><p>WEEK_END {_escape(report.get("week_end"))} · 先逐一阅读全部资产，再看机会排序。</p></section><section class="body"><nav>{"".join(nav_parts)}</nav><div>{"".join(pane_parts)}</div></section><section class="ranking"><h2>本周机会排序</h2><p>排序位于全部资产之后；数据或分析不可用的资产保留其状态，不会被伪装成等待或回避。</p><ul>{ranking_rows}</ul></section><footer>模型生成、未经人工复核；仅限本地评估；不读取 Finance Daily Newsletter；不连接经纪账户或执行交易。<code>{_escape(report.get("report_id"))}</code></footer></main><script type="application/json" id="report-data">{report_json}</script><script>{standard_kline_js}</script><script>
const R=JSON.parse(document.getElementById('report-data').textContent);
function mountPane(pane){{if(!pane||pane.dataset.mounted==='true')return;pane.querySelectorAll('[data-chart]').forEach(node=>{{const slot=R.chart_slots.find(item=>item.slot_id===node.dataset.chart);const payload=slot?.standard_kline;if(!payload){{node.innerHTML='<div class="chart-unavailable">当前标准 K 线输入不可用；保留数据状态，等待新的完整证据。</div>';return}}const options={{...(slot.renderer_options||{{}}),trustPolicy:{{allowSynthetic:false}}}};const chart=new StandardKline.StandardKlineChart(node,options);chart.setDatafeedResponse(payload);node._standardKline=chart;}});pane.dataset.mounted='true';}}
function active(k){{document.querySelectorAll('[data-pane]').forEach(x=>x.classList.toggle('active',x.dataset.pane===k));document.querySelectorAll('[data-asset-nav]').forEach(x=>x.classList.toggle('active',x.dataset.assetNav===k));mountPane(document.querySelector('[data-pane="'+k+'"]'));}}
document.querySelectorAll('[data-asset-nav]').forEach(button=>button.addEventListener('click',()=>active(button.dataset.assetNav)));const first=document.querySelector('[data-pane]')?.dataset.pane;if(first)active(first);
</script></body></html>'''


@_reader_html_labels
def render_weekly_html(report: Mapping[str, Any]) -> str:
    report_json = _canonical(report).replace("</", "<\\/")
    nav_parts: list[str] = []
    pane_parts: list[str] = []
    for _, chapter, keys in CHAPTERS:
        nav_parts.append(f'<h4>{_escape(chapter)}</h4>')
        for key in keys:
            card = next(item for item in report["cards"] if item["asset_key"] == key)
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
                rows.append(
                    f'<article class="timeframe"><div><b>{label}</b><div class="standard-kline-mount" data-chart="{_escape(slot["slot_id"])}" data-kind="{_escape(slot["kind"])}"></div><small class="chart-legend">EMA50 · MACD(12,26,9){(" · 单位：" + _escape(_unit_label(slot.get("unit")))) if slot.get("unit") else ""}</small></div><p>{_escape(text)}</p></article>'
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
                f'<section class="asset-pane" data-pane="{_escape(key)}" data-timeframes="{len(rows)}" data-summary-order="位置,结构,赔率,多周期结论,机制解释"><header><h2>{_escape(card["display_name"])}</h2><small>{_escape(_status_label(card["analysis_status"]))}</small></header>{"".join(rows)}{dimensions}{odds_block}<div class="synthesis"><b>多周期结论</b><p>{_escape(summary)}</p></div><div class="implication" style="grid-column:1/-1;padding:17px;background:#f7f3ea;border-top:1px solid #dedfd8"><b style="font-size:10px;color:#8a6425;letter-spacing:.1em">这意味着什么 · 机制解释</b><p style="font-size:16px;line-height:1.7;margin:6px 0;color:#544932">{_escape(implication_text)}</p></div></section>'
            )
    ranking_rows = "".join(f'<li><strong>{_escape(DISPLAY_NAMES.get(str(row.get("asset_key") or ""), str(row.get("asset_key") or "")))}</strong> · {_escape(_ranking_status_label(row.get("status")))}</li>' for row in (report.get("ranking") or {}).get("ordered_assets") or [])
    return _render_standard_kline_document(report, nav_parts, pane_parts, ranking_rows)
