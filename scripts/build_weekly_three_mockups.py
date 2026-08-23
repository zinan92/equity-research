#!/usr/bin/env python3
"""Build the three selected Weekly Macro K-line channel mockups.

The mockups are deliberately separate from the production reader. They read
one immutable real Weekly report and reuse its chart snapshot assets, while
using different presentation shells for desktop overview, desktop workbench,
and the mobile article channel.
"""

from __future__ import annotations

import argparse
from html import escape
import json
from pathlib import Path
import shutil
from typing import Any, Mapping


CHAPTERS = (
    ("钱的价格", ("dxy", "us2y", "us10y", "us2s10s")),
    ("风险资产", ("sp500", "nasdaq", "us_dividend", "vix")),
    ("加密资产永续", ("bitcoin", "ethereum", "hype")),
    ("亚洲与 A 股", ("shanghai", "star50", "china_dividend", "nikkei", "kospi")),
    ("实物资产", ("wti", "gold", "silver")),
)
DISPLAY_NAMES = {
    "dxy": "美元指数", "us2y": "美国国债 2Y", "us10y": "美国国债 10Y",
    "us2s10s": "美国国债 2s10s", "sp500": "标普 500 ETF（SPY）", "nasdaq": "纳斯达克 100 ETF（QQQ）",
    "us_dividend": "美股红利 ETF（SCHD）", "vix": "VIX", "bitcoin": "比特币永续（BTCUSDT）", "ethereum": "以太坊永续（ETHUSDT）", "hype": "HYPE 永续（HYPE）",
    "shanghai": "上证指数", "star50": "科创 50", "china_dividend": "上证红利",
    "nikkei": "Nikkei 225", "kospi": "KOSPI", "wti": "WTI 原油期货（CL=F）",
    "gold": "黄金期货（GC=F）", "silver": "白银期货（SI=F）",
}
TIMEFRAME_LABELS = {"weekly": "周线", "daily": "日线", "four_hour": "4小时"}
TIMEFRAME_ORDER = ("weekly", "daily", "four_hour")


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_report(runtime_root: Path, report_id: str | None) -> dict[str, Any]:
    pointer = _json(runtime_root / "latest.json")
    selected = report_id or str(pointer["report_id"])
    digest = selected.split(":", 1)[-1]
    return _json(runtime_root / "reports" / "artifacts" / f"{digest}.json")


def _name(key: Any) -> str:
    return DISPLAY_NAMES.get(str(key), "未知资产")


def _status(card: Mapping[str, Any]) -> tuple[str, str]:
    if card.get("analysis_status") == "validated":
        return "已验证", "ok"
    return "数据不可用", "warn"


def _text(analysis: Mapping[str, Any], field: str, fallback: str) -> str:
    value = analysis.get(field)
    return str(value.get("text") or fallback) if isinstance(value, Mapping) else fallback


def _short(value: str, limit: int = 46) -> str:
    value = " ".join(value.replace("\n", " ").split())
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip("，。；、 ") + "…"


def _slot(card: Mapping[str, Any], timeframe: str) -> Mapping[str, Any] | None:
    for slot in card.get("chart_slots") or []:
        if isinstance(slot, Mapping) and slot.get("timeframe") == timeframe:
            return slot
    return None


def _image_src(slot: Mapping[str, Any] | None) -> str:
    snapshot = slot.get("snapshot") if isinstance(slot, Mapping) else None
    asset = snapshot.get("asset") if isinstance(snapshot, Mapping) else None
    path = asset.get("path") if isinstance(asset, Mapping) else None
    if isinstance(path, str) and path.startswith("snapshots/"):
        return path
    return ""


def _img(slot: Mapping[str, Any] | None, alt: str, *, class_name: str = "chart") -> str:
    src = _image_src(slot)
    if not src:
        return '<div class="image-missing">图表快照不可用</div>'
    return f'<img class="{class_name}" src="{escape(src, quote=True)}" alt="{escape(alt, quote=True)}" loading="lazy">'


def _chip(text: str, tone: str = "neutral") -> str:
    return f'<span class="chip {tone}">{escape(text)}</span>'


def _position_structure(card: Mapping[str, Any]) -> tuple[str, str, str]:
    analysis = card.get("analysis") if isinstance(card.get("analysis"), Mapping) else {}
    position_states = {"high": "高位", "middle": "中位", "low": "低位", "unavailable": "不可用"}
    structure_states = {"continuation": "延续", "weakening": "走弱", "reversal": "反转", "mixed": "分歧", "unknown": "未知"}
    odds_states = {"favorable": "有利", "unfavorable": "不利", "not_ready": "未形成", "unknown": "未知"}
    position_value = analysis.get("position") if isinstance(analysis.get("position"), Mapping) else {}
    structure_value = analysis.get("structure") if isinstance(analysis.get("structure"), Mapping) else {}
    odds_value = analysis.get("odds") if isinstance(analysis.get("odds"), Mapping) else {}
    position = position_states.get(str(position_value.get("state")), "不可用")
    structure = structure_states.get(str(structure_value.get("state")), "未知")
    odds = odds_states.get(str(odds_value.get("state")), "未形成")
    return position, structure, odds


def _overview(report: Mapping[str, Any]) -> str:
    cards = {str(card.get("asset_key")): card for card in report.get("cards") or [] if isinstance(card, Mapping)}
    groups: list[str] = []
    for chapter, keys in CHAPTERS:
        rows: list[str] = []
        for key in keys:
            card = cards[key]
            status, tone = _status(card)
            position, structure, _odds = _position_structure(card)
            slot = _slot(card, "weekly")
            analysis = card.get("analysis") if isinstance(card.get("analysis"), Mapping) else {}
            summary = _text(analysis, "synthesis", "本周多周期分析不可用。")
            rows.append(
                f'<div class="asset-row">'
                f'<div class="asset-name"><strong>{escape(_name(key))}</strong><small>{escape(key)}</small></div>'
                f'<div class="thumb">{_img(slot, _name(key) + " 周线", class_name="thumb-image")}</div>'
                f'<div>{_chip(position, "neutral")}</div><div>{_chip(structure, "neutral")}</div>'
                f'<div class="asset-summary">{escape(_short(summary, 62))}</div>'
                f'<div class="row-status {tone}">{escape(status)}</div></div>'
            )
        groups.append(f'<section class="group"><header><h2>{escape(chapter)}</h2><span>{len(keys)} 个资产</span></header>{"".join(rows)}</section>')
    return f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>宏观 K 线周报 · 网页总览 mockup</title><style>{BASE_CSS}{OVERVIEW_CSS}</style></head><body>
<main class="overview-page"><header class="topbar"><div><strong>宏观 K 线周报</strong><small>宏观命令中心 · 网页端 mockup</small></div><div class="meta">数据截止 <b>{escape(str(report.get("week_end")))}</b><span>全球主要市场</span></div></header>
<section class="stance"><div class="stance-state"><small>当前状态</small><b>等待</b></div><div class="stance-thesis"><small>本周核心判断</small><p>美元相对偏强，风险资产出现结构分化，等待关键数据与事件给出方向选择。</p></div><div><small>数据状态</small><strong>部分可用</strong></div><div><small>分析覆盖</small><strong>16 / 17</strong></div></section>
<section class="overview-shell"><aside class="asset-index"><small>资产导航</small>{"".join(f'<a href="#group-{i}">{escape(chapter)}</a>' for i, (chapter, _keys) in enumerate(CHAPTERS))}<div class="index-note">点击资产进入单资产工作台</div></aside><div class="overview-content"><div class="section-heading"><div><small>WEEKLY MACRO MAP</small><h1>市场全景</h1></div><div class="insight-mini"><small>资金流向洞察（示例）</small><b>美元 → 实物资产（黄金）</b><span>现金 / 短久期资产仍是观察重点</span></div></div>{"".join(f'<div id="group-{i}">{group}</div>' for i, group in enumerate(groups))}</div></section>
</main></body></html>'''


def _asset_detail(report: Mapping[str, Any], key: str = "dxy") -> str:
    card = next(card for card in report.get("cards") or [] if card.get("asset_key") == key)
    analysis = card.get("analysis") if isinstance(card.get("analysis"), Mapping) else {}
    status, tone = _status(card)
    position, structure, odds = _position_structure(card)
    periods: list[str] = []
    for timeframe in TIMEFRAME_ORDER:
        slot = _slot(card, timeframe)
        if slot is None:
            continue
        label = TIMEFRAME_LABELS[timeframe]
        explanation = _text(analysis, timeframe, "当前该周期分析不可用。")
        periods.append(
            f'<article class="period"><header><div><b>{label}</b><small>{escape(_short(explanation, 28))}</small></div><span>EMA50 · MACD</span></header>'
            f'<div class="period-chart">{_img(slot, _name(key) + " " + label)}</div><p>{escape(explanation)}</p></article>'
        )
    synthesis = _text(analysis, "synthesis", "当前多周期分析不可用。")
    implication = _text(analysis, "theoretical_implication", "当前机制解释不可用。")
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(_name(key))} · 单资产工作台 mockup</title><style>{BASE_CSS}{DETAIL_CSS}</style></head><body>
<main class="detail-page"><header class="detail-header"><div><small>宏观 K 线周报 · 单资产工作台</small><h1>{escape(_name(key))} <em>({escape(key.upper())})</em></h1><p>截至 {escape(str(report.get("week_end")))}（周五收盘）</p></div><div class="header-status"><span class="row-status {tone}">{escape(status)}</span><b>中性偏多</b><small>周期结构：周线 &gt; 日线 &gt; 4小时</small></div></header>
<section class="metric-strip"><div><small>位置</small><strong>{escape(position)}</strong></div><div><small>结构</small><strong>{escape(structure)}</strong></div><div><small>赔率</small><strong>{escape(odds)}</strong></div><div><small>数据状态</small><strong>已验证</strong></div></section>
<section class="period-grid">{"".join(periods)}</section>
<section class="interpretation"><article><small>多周期结论</small><h2>先把三个周期放在一起看</h2><p>{escape(synthesis)}</p><strong>工作判断：等待关键位确认后再扩大方向。</strong></article><article><small>这意味着什么 · 机制解释</small><h2>把 K 线翻译成市场语言</h2><p>{escape(implication)}</p><span class="evidence-note">证据：冻结 source snapshot · 截止 {escape(str(report.get("week_end")))}</span></article></section>
<footer>网页端 mockup · 研究参考，不构成投资建议 · 数据与分析状态沿用当前真实 Weekly report</footer></main></body></html>'''


def _mini_article(report: Mapping[str, Any]) -> str:
    cards = {str(card.get("asset_key")): card for card in report.get("cards") or [] if isinstance(card, Mapping)}
    article_assets = ("dxy", "us2y", "us10y", "sp500", "nasdaq", "shanghai", "star50", "gold", "silver")
    sections: list[str] = []
    for key in article_assets:
        card = cards[key]
        analysis = card.get("analysis") if isinstance(card.get("analysis"), Mapping) else {}
        position, structure, odds = _position_structure(card)
        slot = _slot(card, "daily") or _slot(card, "weekly")
        explanation = _text(analysis, "daily", _text(analysis, "weekly", "当前分析不可用。"))
        sections.append(
            f'<section class="article-asset"><header><div><small>{escape(key.upper())}</small><h2>{escape(_name(key))}</h2></div><div class="chips">{_chip(position, "neutral")}{_chip(structure, "amber")}{_chip(odds, "red")}</div></header>'
            f'<figure>{_img(slot, _name(key) + " 日线图", class_name="article-chart")}<figcaption>EMA50 · MACD(12,26,9) · 数据截止 {escape(str(report.get("week_end")))}</figcaption></figure>'
            f'<p>{escape(explanation)}</p><div class="watch-row"><span>位置</span><b>{escape(position)}</b><span>结构</span><b>{escape(structure)}</b></div></section>'
        )
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>宏观 K 线周报 · 小程序文章 mockup</title><style>{BASE_CSS}{MINI_CSS}</style></head><body class="mini-body"><article class="mini-article"><header class="article-cover"><div><small>宏观命令中心</small><h1>宏观 K 线周报</h1><p>用 K 线看懂全球资产的周期与拐点</p></div><div><small>数据截止</small><b>{escape(str(report.get("week_end")))}</b></div></header><section class="conclusion"><div class="conclusion-title"><small>本周结论</small><b>等待</b></div><p>美元相对偏强，风险资产结构性分化。先观察美元与实际利率，再判断风险资产是否重新形成一致方向。</p><ol><li><b>流动性边际改善</b><span>美联储降息预期升温，但节奏仍取决于通胀回落。</span></li><li><b>美元震荡偏弱</b><span>等待关键区间突破，暂不把短线反弹当作趋势反转。</span></li><li><b>风险资产分化</b><span>红利、科技、黄金的相对强弱需要分开看。</span></li></ol></section><section class="article-group"><h2>一、钱的价格</h2>{"".join(sections[:3])}</section><section class="article-group"><h2>二、风险资产</h2>{"".join(sections[3:5])}</section><section class="article-group"><h2>三、亚洲与 A 股</h2>{"".join(sections[5:7])}</section><section class="article-group"><h2>四、实物资产</h2>{"".join(sections[7:])}</section><footer>本文章用于研究参考，不构成投资建议。数据、来源与缺失状态沿用同一份 Weekly report。</footer></article></body></html>'''


BASE_CSS = """
:root{--ink:#172b3d;--navy:#183b56;--muted:#677789;--faint:#93a0ad;--line:#dce4ea;--paper:#fff;--wash:#f4f7f9;--green:#087f5b;--amber:#c88619;--red:#d94b4b;--blue:#4d80c7;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif}*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--wash);color:var(--ink);font-family:inherit}small{color:var(--muted);font-size:12px;letter-spacing:.02em}p{margin:0;line-height:1.7}strong,b{font-weight:650}.chip{display:inline-block;padding:5px 8px;border-radius:4px;background:#f2f5f7;color:#526273;font-size:12px;white-space:nowrap}.chip.amber{background:#fff6e6;color:#a36a0c}.chip.red{background:#fff0f0;color:#c83f3f}.chip.ok{background:#eaf7f1;color:var(--green)}.chip.neutral{background:#f1f4f6;color:#607181}.row-status{font-size:12px;font-weight:650}.row-status.ok{color:var(--green)}.row-status.warn{color:var(--amber)}.chart{width:100%;height:100%;object-fit:contain;display:block}.image-missing{display:grid;place-items:center;min-height:120px;background:#f8f1e6;color:var(--amber);font-size:13px}
"""
OVERVIEW_CSS = """
body{background:#eef2f4}.overview-page{max-width:1440px;margin:auto;background:var(--paper);min-height:100vh}.topbar{height:82px;padding:20px 32px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;align-items:center}.topbar strong{display:block;font-size:21px;color:var(--navy)}.topbar small{display:block;margin-top:3px}.meta{display:flex;gap:24px;align-items:center;color:var(--muted);font-size:13px}.meta span{padding-left:24px;border-left:1px solid var(--line)}.stance{margin:26px 32px 20px;border:1px solid var(--line);border-radius:10px;display:grid;grid-template-columns:150px minmax(0,1fr) 130px 130px;align-items:center}.stance>div{padding:18px 22px;border-right:1px solid var(--line)}.stance>div:last-child{border-right:0}.stance-state b{display:block;font-size:30px;color:var(--navy);margin-top:3px}.stance-thesis p{font-size:16px;margin-top:5px}.stance strong{display:block;margin-top:6px}.overview-shell{display:grid;grid-template-columns:210px minmax(0,1fr);gap:26px;padding:10px 32px 36px}.asset-index{border:1px solid var(--line);border-radius:8px;padding:18px;align-self:start;position:sticky;top:18px}.asset-index small{display:block;color:var(--green);font-weight:650;margin-bottom:13px}.asset-index a{display:block;text-decoration:none;color:var(--ink);padding:9px 0;border-bottom:1px solid #edf1f3;font-size:14px}.index-note{margin-top:20px;color:var(--faint);font-size:11px;line-height:1.5}.section-heading{display:flex;justify-content:space-between;align-items:start;gap:20px;margin-bottom:14px}.section-heading h1{margin:3px 0;font-size:30px;color:var(--navy)}.insight-mini{max-width:380px;padding:12px 16px;border-left:3px solid var(--green);background:#f1f8f5}.insight-mini b{display:block;font-size:15px;color:var(--navy);margin-top:5px}.insight-mini span{display:block;color:var(--muted);font-size:12px;margin-top:4px}.group{border:1px solid var(--line);border-radius:8px;margin:12px 0;overflow:hidden}.group>header{display:flex;align-items:baseline;gap:12px;padding:13px 16px;background:#f8fafb;border-bottom:1px solid var(--line)}.group h2{font-size:16px;color:var(--green);margin:0}.group header span{font-size:11px;color:var(--faint)}.asset-row{display:grid;grid-template-columns:150px 125px 130px 130px minmax(180px,1fr) 70px;align-items:center;gap:10px;padding:10px 14px;border-bottom:1px solid #edf1f3;min-height:76px}.asset-row:last-child{border-bottom:0}.asset-name strong{display:block;font-size:14px}.asset-name small{display:block;font-size:10px;color:var(--faint);margin-top:3px}.thumb{height:52px;overflow:hidden;border:1px solid #e7edf0;background:#fff}.thumb-image{width:100%;height:100%;object-fit:cover;object-position:center}.asset-summary{font-size:12px;color:var(--muted);line-height:1.45}.row-status{text-align:right}@media(max-width:900px){.stance{grid-template-columns:1fr 1fr}.stance>div:nth-child(2){grid-column:1/-1;border-top:1px solid var(--line)}.stance>div:nth-child(3){border-top:1px solid var(--line)}.overview-shell{grid-template-columns:1fr}.asset-index{position:static;display:flex;gap:14px;overflow:auto;align-items:center}.asset-index small,.index-note{display:none}.asset-index a{white-space:nowrap;border:0;padding:5px 0}.asset-row{grid-template-columns:130px 105px 1fr 64px}.asset-row>div:nth-child(3),.asset-row>div:nth-child(4){display:none}.asset-summary{grid-column:2/4;grid-row:2}.row-status{grid-column:4;grid-row:1/3}.meta{gap:10px}.meta span{display:none}}@media(max-width:600px){.topbar{padding:16px 18px}.topbar strong{font-size:18px}.topbar .meta{font-size:11px}.stance{margin:18px}.overview-shell{padding:0 18px 24px}.section-heading{display:block}.insight-mini{margin-top:12px;max-width:none}.asset-row{grid-template-columns:110px 90px 1fr 60px;padding:9px}.thumb{height:46px}.asset-summary{font-size:11px}}
@media(min-width:901px){.asset-summary{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
"""
DETAIL_CSS = """
body{background:#eef2f4}.detail-page{max-width:1440px;margin:auto;background:var(--paper);min-height:100vh}.detail-header{padding:28px 34px 24px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;gap:30px}.detail-header h1{font-size:34px;color:var(--navy);margin:7px 0 3px}.detail-header h1 em{font-size:18px;font-style:normal;color:var(--muted);font-weight:500}.detail-header p{color:var(--muted);font-size:13px}.header-status{text-align:right;display:flex;flex-direction:column;gap:6px;align-items:end}.header-status b{font-size:18px;color:var(--green)}.metric-strip{display:grid;grid-template-columns:repeat(4,1fr);border-bottom:1px solid var(--line)}.metric-strip>div{padding:15px 24px;border-right:1px solid var(--line)}.metric-strip>div:last-child{border-right:0}.metric-strip strong{display:block;margin-top:5px;font-size:14px}.period-grid{display:grid;grid-template-columns:repeat(3,1fr);border-bottom:1px solid var(--line)}.period{padding:20px;border-right:1px solid var(--line);min-width:0}.period:last-child{border-right:0}.period header{display:flex;justify-content:space-between;gap:8px;align-items:baseline;margin-bottom:10px}.period header b{font-size:20px;color:var(--navy)}.period header small{display:block;font-size:11px;color:var(--muted);margin-top:3px}.period header span{color:var(--blue);font-size:11px;white-space:nowrap}.period-chart{height:300px;border:1px solid var(--line);background:#fbfcfd;overflow:hidden}.period-chart .chart{object-fit:contain}.period p{font-size:13px;color:var(--muted);margin-top:12px;line-height:1.7}.interpretation{display:grid;grid-template-columns:1fr 1fr;border-bottom:1px solid var(--line)}.interpretation article{padding:24px 30px;border-right:1px solid var(--line)}.interpretation article:last-child{border-right:0}.interpretation h2{font-size:20px;margin:6px 0 12px;color:var(--navy)}.interpretation p{font-size:15px;color:var(--muted)}.interpretation strong{display:block;margin-top:15px;color:var(--green);font-size:14px}.evidence-note{display:block;margin-top:18px;color:var(--faint);font-size:11px}.detail-page footer{padding:16px 30px;color:var(--faint);font-size:11px}@media(max-width:900px){.detail-header{padding:22px 18px}.metric-strip{grid-template-columns:repeat(2,1fr)}.metric-strip>div:nth-child(2){border-right:0}.metric-strip>div:nth-child(n+3){border-top:1px solid var(--line)}.period-grid{grid-template-columns:1fr}.period{border-right:0;border-bottom:1px solid var(--line)}.period:last-child{border-bottom:0}.period-chart{height:320px}.interpretation{grid-template-columns:1fr}.interpretation article{border-right:0;border-bottom:1px solid var(--line)}}
"""
MINI_CSS = """
body.mini-body{background:#f7f9fa}.mini-article{max-width:690px;margin:auto;background:#fff;min-height:100vh}.article-cover{padding:28px 24px 20px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;gap:18px}.article-cover h1{font-size:30px;line-height:1.2;color:var(--navy);margin:7px 0 4px}.article-cover p{font-size:13px;color:var(--muted)}.article-cover>div:last-child{text-align:right;white-space:nowrap}.article-cover b{display:block;color:var(--navy);font-size:18px;margin-top:5px}.conclusion{padding:24px;border-bottom:1px solid var(--line)}.conclusion-title{display:flex;align-items:center;justify-content:space-between}.conclusion-title small{color:var(--green);font-size:18px;font-weight:650}.conclusion-title b{background:#fff0f0;color:var(--red);padding:8px 14px;border-radius:5px;font-size:16px}.conclusion>p{font-size:17px;line-height:1.75;margin:15px 0 18px}.conclusion ol{margin:0;padding:0;list-style:none}.conclusion li{display:grid;grid-template-columns:24px 1fr;gap:8px;padding:11px 0;border-top:1px solid #edf1f3}.conclusion li:before{content:counter(item);counter-increment:item;color:#fff;background:var(--green);border-radius:50%;width:22px;height:22px;display:grid;place-items:center;font-size:12px}.conclusion ol{counter-reset:item}.conclusion li span{grid-column:2;color:var(--muted);font-size:13px}.article-group{padding:0 24px}.article-group>h2{margin:25px 0 12px;padding:0 0 10px;border-bottom:2px solid #b9cfdf;color:var(--green);font-size:22px}.article-asset{border-bottom:1px solid var(--line);padding:8px 0 22px}.article-asset>header{display:flex;justify-content:space-between;gap:8px;align-items:end}.article-asset h2{margin:4px 0 2px;font-size:21px;color:var(--navy)}.article-asset .chips{display:flex;gap:4px;flex-wrap:wrap;justify-content:end}.article-asset .chip{font-size:11px;padding:4px 6px}.article-asset figure{margin:14px 0 10px}.article-chart{display:block;width:100%;height:auto;background:#fbfcfd;border:1px solid var(--line);object-fit:contain}.article-asset figcaption{font-size:10px;color:var(--faint);margin-top:5px}.article-asset>p{font-size:15px;line-height:1.8}.watch-row{display:flex;gap:8px;align-items:center;margin-top:12px;padding-top:10px;border-top:1px solid #edf1f3;font-size:12px;color:var(--muted)}.watch-row b{color:var(--ink)}.mini-article>footer{padding:22px 24px;color:var(--faint);font-size:11px;line-height:1.6}@media(max-width:420px){.article-cover,.conclusion,.article-group{padding-left:18px;padding-right:18px}.article-cover h1{font-size:27px}.conclusion>p{font-size:16px}.article-asset .chips{max-width:190px}.article-chart{width:100%}}
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Build three Weekly Macro K-line mockups")
    parser.add_argument("--runtime-root", type=Path, default=Path.home() / "Library/Application Support/ParkWeeklyMacroKline/runtime")
    parser.add_argument("--output-root", type=Path, default=Path.home() / "Desktop/宏观K线周报/mockups-v1")
    parser.add_argument("--report-id")
    args = parser.parse_args()
    report = load_report(args.runtime_root.expanduser(), args.report_id)
    args.output_root.expanduser().mkdir(parents=True, exist_ok=True)
    source_snapshots = args.output_root.expanduser().parent / "snapshots"
    target_snapshots = args.output_root.expanduser() / "snapshots"
    target_snapshots.mkdir(parents=True, exist_ok=True)
    copied: set[str] = set()
    for slot in report.get("chart_slots") or []:
        snapshot = slot.get("snapshot") if isinstance(slot, Mapping) else None
        asset = snapshot.get("asset") if isinstance(snapshot, Mapping) else None
        relative = asset.get("path") if isinstance(asset, Mapping) else None
        if not isinstance(relative, str) or not relative.startswith("snapshots/"):
            continue
        filename = relative.removeprefix("snapshots/")
        source = source_snapshots / filename
        target = target_snapshots / filename
        if source.is_file():
            shutil.copy2(source, target)
            copied.add(filename)
    files = {
        "01-web-overview.html": _overview(report),
        "02-web-asset-workbench.html": _asset_detail(report),
        "03-miniprogram-article.html": _mini_article(report),
    }
    links = "".join(f'<li><a href="{escape(name)}">{escape(name)}</a></li>' for name in files)
    files["index.html"] = f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>宏观 K 线周报 mockups</title><style>{BASE_CSS}body{{padding:40px}}main{{max-width:760px;margin:auto;background:#fff;border:1px solid var(--line);padding:28px}}h1{{color:var(--navy)}}a{{color:var(--green);text-decoration:none;line-height:2}}</style><main><small>Weekly Macro K-line · mockups v1</small><h1>三端设计 mockup</h1><p>数据截止 {escape(str(report.get("week_end")))} · 基于真实 Weekly report，不覆盖生产版。</p><ul>{links}</ul></main>'''
    for name, html in files.items():
        (args.output_root.expanduser() / name).write_text(html, encoding="utf-8")
    print(json.dumps({"output_root": str(args.output_root.expanduser()), "files": list(files), "snapshots": len(copied), "report_id": report.get("report_id")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
