"""Reader-facing Variant B Weekly Macro report projection."""

from __future__ import annotations

import html
import json
import hashlib
from typing import Any, Mapping

from .market_regime_weekly_source import CANONICAL_REGISTRY, CONTEXT_4H_KEYS, DISPLAY_NAMES, SCHEMA_VERSION as SOURCE_SCHEMA, WEEKLY_KEYS


SCHEMA_VERSION = "market-regime-weekly-report-v1"
RENDERER_VERSION = "market-regime-weekly-report-renderer-v2"
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


def _chart_slot(key: str, timeframe: str, series: Mapping[str, Any]) -> dict[str, Any]:
    if timeframe == "weekly":
        points = series.get("points") or []
    elif timeframe == "daily":
        points = series.get("daily_points") or []
    else:
        points = (series.get("context_4h") or {}).get("points") or []
    return {
        "slot_id": f"{key}:{timeframe}",
        "asset_key": key,
        "timeframe": timeframe,
        "kind": "line" if series.get("series_kind") == "rate_level" else "price",
        "status": "complete" if points else "unavailable",
        "points": points,
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
        if not isinstance(analysis, Mapping) or analysis.get("generation_status") != "model_generated_unreviewed":
            analysis_status = "analysis_unavailable"
            analysis_view: dict[str, Any] = {"status": analysis_status, "failure_code": (analysis or {}).get("failure_code", "analysis_missing")}
        else:
            analysis_status = "validated"
            analysis_view = {
                "status": analysis_status,
                "analysis_id": analysis.get("analysis_id"),
                "weekly": analysis.get("weekly"),
                "daily": analysis.get("daily"),
                "four_hour": analysis.get("four_hour"),
                "synthesis": analysis.get("synthesis"),
                "agreement": analysis.get("agreement"),
                "confirmation": analysis.get("confirmation"),
                "invalidation": analysis.get("invalidation"),
                "opportunity_state": analysis.get("opportunity_state"),
                "rationale": analysis.get("rationale"),
            }
        timeframes = ["weekly", "daily"] + (["four_hour"] if key in CONTEXT_4H_KEYS else [])
        slots = [_chart_slot(key, tf, series) for tf in timeframes]
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
            for tf, label in (("weekly", "周线"), ("daily", "日线"), ("four_hour", "4H")):
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
                    f'<article class="timeframe"><div><b>{label}</b><canvas data-chart="{_escape(slot["slot_id"])}" data-kind="{_escape(slot["kind"])}"></canvas></div><p>{_escape(text)}</p></article>'
                )
            synthesis = analysis.get("synthesis") if isinstance(analysis, Mapping) else None
            summary = (synthesis or {}).get("text") if isinstance(synthesis, Mapping) else "当前多周期分析不可用。"
            pane_parts.append(
                f'<section class="asset-pane" data-pane="{_escape(key)}"><header><h2>{_escape(card["display_name"])}</h2><small>{_escape(str(card["analysis_status"]))}</small></header>{"".join(rows)}<div class="synthesis"><b>多周期结论</b><p>{_escape(summary)}</p></div></section>'
            )
    ranking_rows = "".join(f'<li><strong>{_escape(str(row.get("asset_key")))}</strong> · {_escape(str(row.get("status")))}</li>' for row in (report.get("ranking") or {}).get("ordered_assets") or [])
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>宏观 K 线周报｜{_escape(report.get("week_end"))}</title><style>
:root{{--ink:#17201b;--muted:#68736b;--faint:#9aa39c;--line:#dedfd8;--paper:#fffefa;--canvas:#f1efe9;--green:#187b51;--red:#c94640;--navy:#3f586e}}*{{box-sizing:border-box}}html,body{{margin:0;background:var(--canvas);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif}}main{{width:min(1240px,100%);margin:auto;background:var(--paper);min-height:100vh}}.top{{padding:20px 34px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;gap:12px}}.top b{{letter-spacing:.08em}}.top span{{font-size:10px;border:1px solid var(--line);padding:5px 8px;color:var(--muted)}}.hero{{padding:44px 34px;border-bottom:1px solid var(--line);background:#f5f7f1}}.hero h1{{font-family:Georgia,"Songti SC",serif;font-size:72px;font-weight:500;color:var(--navy);margin:14px 0}}.hero p{{color:var(--muted);line-height:1.7}}.body{{display:grid;grid-template-columns:190px 1fr;gap:22px;padding:34px}}nav{{position:sticky;top:16px;align-self:start;border:1px solid var(--line);background:#fff;padding:14px}}nav h4{{font-size:9px;color:var(--green);margin:12px 0 4px}}nav button{{display:block;width:100%;border:0;border-bottom:1px solid #f0f0eb;background:#fff;text-align:left;padding:7px 3px;color:var(--muted);cursor:pointer}}nav button.active{{color:var(--green);font-weight:700}}.asset-pane{{display:none;border:1px solid var(--line);background:#fff}}.asset-pane.active{{display:block}}.asset-pane>header{{display:flex;justify-content:space-between;padding:17px;border-bottom:1px solid var(--line)}}.asset-pane h2{{font-family:Georgia,"Songti SC",serif;font-size:27px;font-weight:500;margin:0}}.asset-pane header small{{color:var(--faint)}}.timeframe{{display:grid;grid-template-columns:1.3fr .7fr;gap:18px;padding:16px;border-bottom:1px solid var(--line)}}.timeframe b{{display:block;color:var(--green);font-size:10px;letter-spacing:.12em;margin-bottom:7px}}canvas{{display:block;width:100%;height:150px;background:#fcfcf8;border:1px solid #eceee8}}.timeframe p{{font-family:Georgia,"Songti SC",serif;font-size:18px;line-height:1.6;margin:0}}.synthesis{{padding:17px;background:#edf3ef}}.synthesis b{{font-size:10px;color:var(--green);letter-spacing:.1em}}.synthesis p{{font-family:Georgia,"Songti SC",serif;font-size:19px;line-height:1.5;margin:6px 0}}.ranking{{padding:34px;background:#f5f3ed}}.ranking h2{{font-family:Georgia,"Songti SC",serif;font-weight:500;font-size:30px}}.ranking li{{display:inline-block;margin:4px 12px 4px 0}}footer{{padding:25px 34px;color:var(--faint);font-size:10px}}@media(max-width:760px){{.top,.hero,.body,.ranking{{padding:20px 18px}}.top{{display:block}}.top span{{display:inline-block;margin-top:8px}}.hero h1{{font-size:55px}}.body{{display:block}}nav{{position:static;display:flex;overflow:auto;gap:6px;margin-bottom:15px}}nav h4{{display:none}}nav button{{min-width:max-content;border:1px solid var(--line);padding:7px 9px}}.timeframe{{grid-template-columns:1fr}}.timeframe p{{font-size:17px}}}}
</style></head><body><main><header class="top"><b>宏观 K 线周报</b><span>模型生成、未经人工复核 · 本地评估 · 无自动执行</span></header><section class="hero"><h1>本周宏观图谱</h1><p>WEEK_END {_escape(report.get("week_end"))} · 先逐一阅读全部资产，再看机会排序。</p></section><section class="body"><nav>{"".join(nav_parts)}</nav><div>{"".join(pane_parts)}</div></section><section class="ranking"><h2>本周机会排序</h2><p>排序位于全部资产之后；数据或分析不可用的资产保留其状态，不会被伪装成等待或回避。</p><ul>{ranking_rows}</ul></section><footer>模型生成、未经人工复核；仅限本地评估；不读取 Finance Daily Newsletter；不连接经纪账户或执行交易。<code>{_escape(report.get("report_id"))}</code></footer></main><script type="application/json" id="report-data">{report_json}</script><script>const R=JSON.parse(document.getElementById('report-data').textContent);function draw(c){{const slot=R.chart_slots.find(x=>x.slot_id===c.dataset.chart),rows=(slot?.points||[]).slice(-80),r=c.getBoundingClientRect(),d=devicePixelRatio||1,w=Math.max(20,r.width),h=Math.max(20,r.height),p={{l:8,r:8,t:12,b:18}};c.width=w*d;c.height=h*d;const x=c.getContext('2d');x.setTransform(d,0,0,d,0,0);x.clearRect(0,0,w,h);x.strokeStyle='#e7ebe5';x.lineWidth=1;for(let i=1;i<4;i++){{x.beginPath();x.moveTo(0,i*h/4);x.lineTo(w,i*h/4);x.stroke()}}if(!rows.length)return;const values=rows.flatMap(v=>slot.kind==='line'?[Number(v.value)]:[Number(v.high),Number(v.low)]).filter(Number.isFinite);if(!values.length)return;let lo=Math.min(...values),hi=Math.max(...values);if(lo===hi){{lo-=1;hi+=1}}const y=v=>p.t+(hi-v)/(hi-lo)*(h-p.t-p.b),step=(w-p.l-p.r)/Math.max(rows.length,1);if(slot.kind==='line'){{x.strokeStyle='#526779';x.lineWidth=1.7;x.beginPath();rows.forEach((v,i)=>{{const px=p.l+(i+.5)*step,py=y(Number(v.value));i?x.lineTo(px,py):x.moveTo(px,py)}});x.stroke()}}else{{rows.forEach((v,i)=>{{const o=Number(v.open),cl=Number(v.close),hh=Number(v.high),ll=Number(v.low),px=p.l+(i+.5)*step,bw=Math.max(1.5,Math.min(8,step*.58)),up=cl>=o;color=up?'#187b51':'#c94640';x.strokeStyle=color;x.fillStyle=color;x.lineWidth=1;x.beginPath();x.moveTo(px,y(hh));x.lineTo(px,y(ll));x.stroke();const top=Math.min(y(o),y(cl)),height=Math.max(1,Math.abs(y(o)-y(cl)));if(up){{x.strokeRect(px-bw/2,top,bw,height)}}else{{x.fillRect(px-bw/2,top,bw,height)}}}})}}x.fillStyle='#9aa39c';x.font='9px -apple-system,sans-serif';const first=rows[0].date||rows[0].start_at||'',last=rows.at(-1).date||rows.at(-1).start_at||'';x.fillText(first,p.l,h-4);x.textAlign='right';x.fillText(last,w-p.r,h-4);x.textAlign='left'}}function active(k){{document.querySelectorAll('[data-pane]').forEach(x=>x.classList.toggle('active',x.dataset.pane===k));document.querySelectorAll('[data-asset-nav]').forEach(x=>x.classList.toggle('active',x.dataset.assetNav===k));document.querySelectorAll('[data-pane="'+k+'"] canvas').forEach(draw)}}const first=document.querySelector('[data-pane]')?.dataset.pane;document.querySelectorAll('[data-asset-nav]').forEach(b=>b.addEventListener('click',()=>active(b.dataset.assetNav)));active(first);</script></body></html>'''
