"""Reader-facing Variant B Weekly Macro report projection."""

from __future__ import annotations

import html
import json
import hashlib
from typing import Any, Mapping

from .market_regime_weekly_features import FEATURE_PARAMETERS, FEATURE_SCHEMA_VERSION, WeeklyFeatureError, build_timeframe_features
from .market_regime_weekly_source import CANONICAL_REGISTRY, CONTEXT_4H_KEYS, DISPLAY_NAMES, SCHEMA_VERSION as SOURCE_SCHEMA, WEEKLY_KEYS


SCHEMA_VERSION = "market-regime-weekly-report-v3"
RENDERER_VERSION = "market-regime-weekly-report-renderer-v9"
REPORT_ID_PREFIX = "market-regime-weekly-report:"
CHAPTERS = (
    ("money_price", "钱的价格", ("dxy", "us2y", "us10y", "us2s10s")),
    ("risk_assets", "风险资产", ("sp500", "nasdaq", "us_dividend", "vix", "bitcoin")),
    ("asia_a_share", "亚洲与 A 股", ("shanghai", "star50", "china_dividend", "nikkei", "kospi")),
    ("real_assets", "实物资产", ("wti", "gold", "silver")),
)


class WeeklyReportError(ValueError):
    """Weekly report projection or reader contract failed closed."""


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


def _chart_slot(key: str, timeframe: str, series: Mapping[str, Any], *, cutoff_at: Any = None) -> dict[str, Any]:
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
            "unit": series.get("unit"),
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
        "kind": feature.get("chart_kind", "line" if series.get("series_kind") == "rate_level" else "price"),
        "unit": series.get("unit"),
        "status": feature.get("status", "unavailable"),
        "points": feature.get("points", []),
        "feature": feature,
        "x_labels": feature.get("x_labels", []),
        "y_labels": feature.get("y_labels", []),
        "current": feature.get("current"),
        "high": feature.get("high"),
        "low": feature.get("low"),
    }


def build_weekly_report(
    source_snapshot: Mapping[str, Any],
    analyses: Mapping[str, Mapping[str, Any]],
    ranking: Mapping[str, Any],
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
        if (
            not isinstance(analysis, Mapping)
            or analysis.get("generation_status") != "model_generated_unreviewed"
            or not isinstance(analysis.get("position"), Mapping)
            or not isinstance(analysis.get("structure"), Mapping)
        ):
            analysis_status = "analysis_unavailable"
            failure_code = (analysis or {}).get("failure_code", "analysis_missing")
            if isinstance(analysis, Mapping) and analysis.get("generation_status") == "model_generated_unreviewed" and failure_code == "analysis_missing":
                failure_code = "position_structure_missing"
            analysis_view: dict[str, Any] = {"status": analysis_status, "failure_code": failure_code}
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
                "synthesis": analysis.get("synthesis"),
                "agreement": analysis.get("agreement"),
                "confirmation": analysis.get("confirmation"),
                "invalidation": analysis.get("invalidation"),
                "opportunity_state": analysis.get("opportunity_state"),
                "rationale": analysis.get("rationale"),
            }
        timeframes = ["weekly", "daily"] + (["four_hour"] if key in CONTEXT_4H_KEYS else [])
        slots = [_chart_slot(key, tf, series, cutoff_at=source_snapshot.get("cutoff_at")) for tf in timeframes]
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
        f"WEEK_END：{report.get('week_end')} · 分析截止：{report.get('week_end')} · 先完成全部资产分析，再进行机会排序。",
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
            for tf, label in (("weekly", "周线"), ("daily", "日线"), ("four_hour", "4小时")):
                statement = analysis.get(tf) if isinstance(analysis, Mapping) else None
                if statement:
                    lines.extend([f"**{label}**：{statement.get('text')}", ""])
                elif tf == "four_hour" and key in CONTEXT_4H_KEYS:
                    lines.extend(["**4H**：当前 Context 不可用。", ""])
            synthesis = analysis.get("synthesis") if isinstance(analysis, Mapping) else None
            lines.extend([f"**多周期结论**：{(synthesis or {}).get('text', '当前分析不可用。')}", ""])
    lines.extend(["## 本周机会排序", ""])
    for row in (report.get("ranking") or {}).get("ordered_assets") or []:
        lines.append(f"- {row.get('asset_key')}：{row.get('status')}")
    return "\n".join(lines) + "\n"


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
                    f'<article class="timeframe"><div><b>{label}</b><canvas data-chart="{_escape(slot["slot_id"])}" data-kind="{_escape(slot["kind"])}"></canvas><small class="chart-legend">EMA50 · MACD(12,26,9){(" · 单位：" + _escape(_unit_label(slot.get("unit")))) if slot.get("unit") else ""}</small></div><p>{_escape(text)}</p></article>'
                )
            synthesis = analysis.get("synthesis") if isinstance(analysis, Mapping) else None
            summary = (synthesis or {}).get("text") if isinstance(synthesis, Mapping) else "当前多周期分析不可用。"
            position = analysis.get("position") if isinstance(analysis, Mapping) else None
            structure = analysis.get("structure") if isinstance(analysis, Mapping) else None
            dimensions = ""
            if isinstance(position, Mapping) or isinstance(structure, Mapping):
                position_text = (position or {}).get("text", "位置：不可用。") if isinstance(position, Mapping) else "位置：不可用。"
                structure_text = (structure or {}).get("text", "结构：不可用。") if isinstance(structure, Mapping) else "结构：不可用。"
                dimensions = f'<div class="summary-dimensions"><div><b>位置</b><p>{_escape(position_text)}</p></div><div><b>结构</b><p>{_escape(structure_text)}</p></div></div>'
            pane_parts.append(
                f'<section class="asset-pane" data-pane="{_escape(key)}" data-timeframes="{len(rows)}"><header><h2>{_escape(card["display_name"])}</h2><small>{_escape(str(card["analysis_status"]))}</small></header>{"".join(rows)}{dimensions}<div class="synthesis"><b>多周期结论</b><p>{_escape(summary)}</p></div></section>'
            )
    ranking_rows = "".join(f'<li><strong>{_escape(str(row.get("asset_key")))}</strong> · {_escape(str(row.get("status")))}</li>' for row in (report.get("ranking") or {}).get("ordered_assets") or [])
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>宏观 K 线周报｜{_escape(report.get("week_end"))}</title><style>
:root{{--ink:#17201b;--muted:#68736b;--faint:#9aa39c;--line:#dedfd8;--paper:#fffefa;--canvas:#f1efe9;--green:#187b51;--red:#c94640;--navy:#3f586e;--font-display:"Avenir Next","SF Pro Display",-apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;--font-body:-apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif}}*{{box-sizing:border-box}}html,body{{margin:0;background:var(--canvas);color:var(--ink);font-family:var(--font-body)}}main{{width:min(1240px,100%);margin:auto;background:var(--paper);min-height:100vh}}.top{{padding:20px 34px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;gap:12px}}.top b{{font-family:var(--font-display);letter-spacing:.04em;font-weight:650}}.top span{{font-size:10px;border:1px solid var(--line);padding:5px 8px;color:var(--muted)}}.hero{{padding:44px 34px;border-bottom:1px solid var(--line);background:#f5f7f1}}.hero h1{{font-family:var(--font-display);font-size:72px;font-weight:650;letter-spacing:-.035em;color:var(--navy);margin:14px 0}}.hero p{{color:var(--muted);line-height:1.7}}.body{{display:grid;grid-template-columns:190px 1fr;gap:22px;padding:34px}}nav{{position:sticky;top:16px;align-self:start;border:1px solid var(--line);background:#fff;padding:14px}}nav h4{{font-size:9px;color:var(--green);margin:12px 0 4px}}nav button{{display:block;width:100%;border:0;border-bottom:1px solid #f0f0eb;background:#fff;text-align:left;padding:7px 3px;color:var(--muted);cursor:pointer}}nav button.active{{color:var(--green);font-weight:700}}.asset-pane{{display:none;border:1px solid var(--line);background:#fff}}.asset-pane.active{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));align-items:stretch}}.asset-pane[data-timeframes="2"].active{{grid-template-columns:repeat(2,minmax(0,1fr))}}.asset-pane>header{{grid-column:1/-1;display:flex;justify-content:space-between;padding:17px;border-bottom:1px solid var(--line)}}.asset-pane h2{{font-family:var(--font-display);font-size:27px;font-weight:650;letter-spacing:-.02em;margin:0}}.asset-pane header small{{color:var(--faint)}}.timeframe{{display:flex;flex-direction:column;gap:12px;padding:16px;border-right:1px solid var(--line);border-bottom:1px solid var(--line)}}.timeframe b{{display:block;color:var(--green);font-size:10px;letter-spacing:.12em;margin-bottom:7px}}canvas{{display:block;width:100%;height:230px;background:#fcfcf8;border:1px solid #eceee8}}.chart-legend{{display:block;margin-top:5px;color:var(--faint);font-size:10px}}.timeframe p{{font-family:var(--font-body);font-size:17px;line-height:1.75;letter-spacing:.01em;margin:0}}.summary-dimensions{{grid-column:1/-1;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;padding:14px 16px;background:#f7f9f5;border-bottom:1px solid var(--line)}}.summary-dimensions>div{{border-left:3px solid var(--green);padding-left:10px}}.summary-dimensions b{{font-size:10px;color:var(--green);letter-spacing:.1em}}.summary-dimensions p{{font-family:var(--font-body);font-size:15px;line-height:1.55;margin:4px 0}}.synthesis{{grid-column:1/-1;padding:17px;background:#edf3ef}}.synthesis b{{font-size:10px;color:var(--green);letter-spacing:.1em}}.synthesis p{{font-family:var(--font-body);font-size:18px;font-weight:500;line-height:1.65;letter-spacing:.01em;margin:6px 0}}.ranking{{padding:34px;background:#f5f3ed}}.ranking h2{{font-family:var(--font-display);font-weight:650;letter-spacing:-.02em;font-size:30px}}.ranking li{{display:inline-block;margin:4px 12px 4px 0}}footer{{padding:25px 34px;color:var(--faint);font-size:10px}}footer code{{word-break:break-all}}@media(max-width:760px){{.top,.hero,.body,.ranking{{padding:20px 18px}}.top{{display:block}}.top span{{display:inline-block;margin-top:8px}}.hero h1{{font-size:55px}}.body{{display:block}}nav{{position:static;display:flex;overflow:auto;gap:6px;margin-bottom:15px}}nav h4{{display:none}}nav button{{min-width:max-content;border:1px solid var(--line);padding:7px 9px}}.asset-pane[data-timeframes="2"].active,.asset-pane[data-timeframes="3"].active{{grid-template-columns:1fr}}.timeframe{{border-right:0}}.summary-dimensions{{grid-template-columns:1fr}}.timeframe p{{font-size:17px}}}}
</style></head><body><main><header class="top"><b>宏观 K 线周报</b><span>模型生成、未经人工复核 · 本地评估 · 无自动执行</span></header><section class="hero"><h1>本周宏观图谱</h1><p>WEEK_END {_escape(report.get("week_end"))} · 先逐一阅读全部资产，再看机会排序。</p></section><section class="body"><nav>{"".join(nav_parts)}</nav><div>{"".join(pane_parts)}</div></section><section class="ranking"><h2>本周机会排序</h2><p>排序位于全部资产之后；数据或分析不可用的资产保留其状态，不会被伪装成等待或回避。</p><ul>{ranking_rows}</ul></section><footer>模型生成、未经人工复核；仅限本地评估；不读取 Finance Daily Newsletter；不连接经纪账户或执行交易。<code>{_escape(report.get("report_id"))}</code></footer></main><script type="application/json" id="report-data">{report_json}</script><script>const R=JSON.parse(document.getElementById('report-data').textContent);function draw(c){{const slot=R.chart_slots.find(x=>x.slot_id===c.dataset.chart),rows=slot?.points||[],feature=slot?.feature||{{}},r=c.getBoundingClientRect(),d=devicePixelRatio||1,w=Math.max(40,r.width),h=Math.max(40,r.height),p={{l:42,r:46,t:14,b:30}},priceBottom=Math.max(90,Math.floor(h*.70)),macdTop=priceBottom+10,macdBottom=h-p.b;c.width=w*d;c.height=h*d;const x=c.getContext('2d');x.setTransform(d,0,0,d,0,0);x.clearRect(0,0,w,h);if(!rows.length)return;const raw=rows.flatMap(v=>slot.kind==='line'?[Number(v.value)]:[Number(v.high),Number(v.low)]).filter(Number.isFinite);if(!raw.length)return;let lo=Math.min(...raw),hi=Math.max(...raw);if(lo===hi){{lo-=1;hi+=1}}const y=v=>p.t+(hi-v)/(hi-lo)*(priceBottom-p.t),step=(w-p.l-p.r)/Math.max(rows.length,1);x.strokeStyle='#e7ebe5';x.lineWidth=1;for(let i=0;i<4;i++){{const py=p.t+i*(priceBottom-p.t)/3;x.beginPath();x.moveTo(p.l,py);x.lineTo(w-p.r,py);x.stroke()}}(feature.y_labels||[]).forEach(t=>{{const value=Number(t.value);if(!Number.isFinite(value))return;const py=y(value);x.fillStyle='#87918b';x.font='9px -apple-system,sans-serif';x.textAlign='right';x.fillText(String(t.label),p.l-6,py+3)}});x.textAlign='left';if(slot.kind==='line'){{x.strokeStyle='#526779';x.lineWidth=1.7;x.beginPath();rows.forEach((v,i)=>{{const value=Number(v.value);if(!Number.isFinite(value))return;const px=p.l+(i+.5)*step,py=y(value);i?x.lineTo(px,py):x.moveTo(px,py)}});x.stroke()}}else{{rows.forEach((v,i)=>{{const o=Number(v.open),cl=Number(v.close),hh=Number(v.high),ll=Number(v.low),px=p.l+(i+.5)*step,bw=Math.max(1,Math.min(7,step*.62));if(![o,cl,hh,ll].every(Number.isFinite))return;const color=cl>=o?'#187b51':'#c94640';x.strokeStyle=color;x.fillStyle=color;x.lineWidth=1;x.beginPath();x.moveTo(px,y(hh));x.lineTo(px,y(ll));x.stroke();const top=Math.min(y(o),y(cl)),height=Math.max(1,Math.abs(y(o)-y(cl)));if(cl>=o)x.strokeRect(px-bw/2,top,bw,height);else x.fillRect(px-bw/2,top,bw,height)}})}}function drawLine(field,color,scale){{x.strokeStyle=color;x.lineWidth=1.5;x.beginPath();let started=false;rows.forEach((v,i)=>{{const value=Number(v[field]);if(!Number.isFinite(value))return;const px=p.l+(i+.5)*step,py=scale(value);if(started)x.lineTo(px,py);else{{x.moveTo(px,py);started=true}}}});if(started)x.stroke()}}drawLine('ema50','#d8892f',y);const macdValues=rows.flatMap(v=>[Number(v.macd),Number(v.macd_signal),Number(v.macd_histogram)]).filter(Number.isFinite);if(macdValues.length){{const abs=Math.max(...macdValues.map(v=>Math.abs(v)),1e-9),my=v=>macdTop+(abs-v)/(2*abs)*(macdBottom-macdTop);x.strokeStyle='#dfe5e0';x.beginPath();x.moveTo(p.l,my(0));x.lineTo(w-p.r,my(0));x.stroke();rows.forEach((v,i)=>{{const hist=Number(v.macd_histogram);if(!Number.isFinite(hist))return;const px=p.l+(i+.5)*step,bw=Math.max(1,Math.min(7,step*.62)),zero=my(0),top=my(Math.max(0,hist)),bottom=my(Math.min(0,hist));x.fillStyle=hist>=0?'#4b9d77':'#d46b65';x.fillRect(px-bw/2,top,bw,Math.max(1,bottom-top))}});const macdY=v=>my(v);drawLine('macd','#187b51',macdY);drawLine('macd_signal','#c47a29',macdY);x.fillStyle='#87918b';x.font='9px -apple-system,sans-serif';x.textAlign='left';x.fillText('MACD',p.l,macdTop+9)}}(feature.x_labels||[]).forEach(item=>{{const index=Math.min(rows.length-1,Math.max(0,Number(item.index))),px=p.l+(index+.5)*step;x.fillStyle='#87918b';x.font='9px -apple-system,sans-serif';x.textAlign='center';x.fillText(String(item.label),px,h-7)}});const markers=[['高',feature.high?.value,'#87918b'],['当前',feature.current?.value,'#187b51'],['低',feature.low?.value,'#87918b']];markers.forEach(([label,value,color])=>{{const number=Number(value);if(!Number.isFinite(number))return;const py=y(number);x.fillStyle=color;x.font='9px -apple-system,sans-serif';x.textAlign='right';x.fillText(label+' '+String(value),w-4,py+3)}});x.textAlign='left'}}function active(k){{document.querySelectorAll('[data-pane]').forEach(x=>x.classList.toggle('active',x.dataset.pane===k));document.querySelectorAll('[data-asset-nav]').forEach(x=>x.classList.toggle('active',x.dataset.assetNav===k));document.querySelectorAll('[data-pane="'+k+'"] canvas').forEach(draw)}}const first=document.querySelector('[data-pane]')?.dataset.pane;document.querySelectorAll('[data-asset-nav]').forEach(b=>b.addEventListener('click',()=>active(b.dataset.assetNav)));active(first);</script></body></html>'''
