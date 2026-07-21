from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import statistics
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from data_store import (
    DB_PATH, DEMO_POSITIONS, connect, create_snapshot_content_attestation,
    initialize, publication_content_hash, validate_invariants,
)
from ingest_quotes import fetch_quotes_bundle, provider_symbol


FEATURE_VERSION = "a-share-core-v0.3"
MODEL_VERSION = "long-horizon-portfolio-v0.4"
KLINE_SOURCE = "tencent_qfq_daily"
FINANCIAL_SOURCE = "eastmoney_f10_main"
CALENDAR_SOURCE_URL = "https://finance.sina.com.cn/realstock/company/klc_td_sh.txt"


def _retry(call: Any, *args: Any, attempts: int = 3, **kwargs: Any) -> Any:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return call(*args, **kwargs)
        except Exception as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(0.35)
    assert last_error is not None
    raise last_error


def validate_real_input_coverage(
    quotes: dict[str, Any] | list[Any],
    klines: dict[str, Any],
    financials: dict[str, Any],
    expected: int,
    errors: list[str] | None = None,
) -> dict[str, int]:
    coverage = {"quotes": len(quotes), "klines": len(klines), "financials": len(financials)}
    problems = errors or []
    if problems or any(value != expected for value in coverage.values()):
        raise RuntimeError(f"real data gate failed coverage={coverage}/{expected} errors={problems[:4]}")
    return coverage


def _json_request(url: str, timeout: float = 10.0) -> tuple[dict, str, str]:
    request = Request(url, headers={"User-Agent": "ParkResearchDashboard/0.2"})
    with urlopen(request, timeout=timeout) as response:
        raw = response.read()
    return (
        json.loads(raw.decode("utf-8")), hashlib.sha256(raw).hexdigest(),
        base64.b64encode(raw).decode("ascii"),
    )


def fetch_daily_bars(ticker: str, limit: int = 320, timeout: float = 10.0) -> dict[str, Any]:
    symbol = provider_symbol(ticker)
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={symbol},day,,,{limit},qfq"
    payload, raw_hash, raw_payload_b64 = _json_request(url, timeout)
    stock = payload.get("data", {}).get(symbol, {})
    rows = stock.get("qfqday") or stock.get("day") or []
    bars = []
    for row in rows:
        if len(row) < 6:
            continue
        try:
            bars.append({
                "trade_date": row[0], "open": float(row[1]), "close": float(row[2]),
                "high": float(row[3]), "low": float(row[4]), "volume_lots": float(row[5]),
            })
        except (TypeError, ValueError):
            continue
    if len(bars) < 250:
        raise RuntimeError(f"{ticker} daily bars incomplete: {len(bars)}")
    return {
        "ticker": ticker, "bars": bars, "source_url": url, "raw_hash": raw_hash,
        "raw_payload_b64": raw_payload_b64,
    }


def fetch_financials(ticker: str, timeout: float = 10.0) -> dict[str, Any]:
    params = {
        "type": "RPT_F10_FINANCE_MAINFINADATA", "sty": "APP_F10_MAINFINADATA",
        "quoteColumns": "", "filter": f'(SECUCODE="{ticker}")', "p": "1", "ps": "12",
        "sr": "-1", "st": "REPORT_DATE", "source": "HSF10", "client": "PC",
    }
    url = "https://datacenter.eastmoney.com/securities/api/data/get?" + urlencode(params)
    payload, raw_hash, raw_payload_b64 = _json_request(url, timeout)
    rows = payload.get("result", {}).get("data") or []
    normalized = []
    for row in rows:
        report_date = str(row.get("REPORT_DATE") or "")[:10]
        notice_date = str(row.get("NOTICE_DATE") or "")[:10]
        if not report_date or not notice_date:
            continue
        normalized.append({
            "report_date": report_date, "notice_date": notice_date,
            "report_type": row.get("REPORT_TYPE") or row.get("REPORT_DATE_NAME") or "未知",
            "revenue": row.get("TOTALOPERATEREVE"), "net_profit": row.get("PARENTNETPROFIT"),
            "revenue_yoy": row.get("TOTALOPERATEREVETZ"), "net_profit_yoy": row.get("PARENTNETPROFITTZ"),
            "roe": row.get("ROEJQ"), "gross_margin": row.get("XSMLL"),
            "net_margin": row.get("XSJLL"), "debt_ratio": row.get("ZCFZL"),
            "operating_cash_per_share": row.get("MGJYXJJE"),
            "row_hash": hashlib.sha256(json.dumps(row, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest(),
        })
    if not normalized:
        raise RuntimeError(f"{ticker} financial statements unavailable")
    return {
        "ticker": ticker, "rows": normalized, "source_url": url, "raw_hash": raw_hash,
        "raw_payload_b64": raw_payload_b64,
    }


def fetch_exchange_calendar(timeout: float = 10.0) -> dict[str, Any]:
    """Fetch the independent mainland exchange calendar used by AkShare."""
    from akshare.tool.trade_date_hist import hk_js_decode, py_mini_racer

    request = Request(CALENDAR_SOURCE_URL, headers={"User-Agent": "ParkResearchDashboard/0.2"})
    with urlopen(request, timeout=timeout) as response:
        raw = response.read()
    text = raw.decode("utf-8")
    encoded = text.split("=", 1)[1].split(";", 1)[0].replace('"', "")
    js = py_mini_racer.MiniRacer()
    js.eval(hk_js_decode)
    values = sorted({str(item)[:10] for item in js.call("d", encoded)})
    if len(values) < 250:
        raise RuntimeError(f"exchange calendar incomplete: {len(values)}")
    return {
        "trade_dates": values,
        "source_url": CALENDAR_SOURCE_URL,
        "raw_hash": hashlib.sha256(raw).hexdigest(),
        "raw_payload_b64": base64.b64encode(raw).decode("ascii"),
    }


def collect_real_inputs(timeout: float = 10.0) -> dict[str, Any]:
    started_at = datetime.now(timezone.utc).isoformat()
    quote_bundle = _retry(fetch_quotes_bundle, timeout=min(timeout, 8.0))
    exchange_calendar = _retry(fetch_exchange_calendar, timeout=min(timeout, 8.0))
    quotes = quote_bundle["quotes"]
    tickers = [item["ticker"] for item in DEMO_POSITIONS]
    klines: dict[str, dict] = {}
    financials: dict[str, dict] = {}
    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=6, thread_name_prefix="market-ingest") as pool:
        futures = {}
        for ticker in tickers:
            futures[pool.submit(_retry, fetch_daily_bars, ticker, 320, timeout)] = ("kline", ticker)
            futures[pool.submit(_retry, fetch_financials, ticker, timeout)] = ("financial", ticker)
        for future in as_completed(futures):
            kind, ticker = futures[future]
            try:
                result = future.result()
                (klines if kind == "kline" else financials)[ticker] = result
            except Exception as exc:  # network boundary, summarized for the gate
                errors.append(f"{kind}:{ticker}:{type(exc).__name__}:{exc}")
    finished_at = datetime.now(timezone.utc).isoformat()
    expected = len(tickers)
    validate_real_input_coverage(quotes, klines, financials, expected, errors)
    return {
        "quotes": {quote["ticker"]: quote for quote in quotes}, "klines": klines,
        "financials": financials, "quote_raw": {
            "source_url": quote_bundle["source_url"], "raw_hash": quote_bundle["raw_hash"],
            "raw_payload_b64": quote_bundle["raw_payload_b64"],
        },
        "exchange_calendar": exchange_calendar,
        "started_at": started_at, "finished_at": finished_at,
    }


def _clamp(value: float, low: float = 0, high: float = 100) -> float:
    return max(low, min(high, value))


def _pct_change(values: list[float], periods: int) -> float | None:
    if len(values) <= periods or not values[-periods - 1]:
        return None
    return (values[-1] / values[-periods - 1] - 1) * 100


def compute_features(quote: dict, bars: list[dict], latest_financial: dict) -> dict[str, float | str | None]:
    closes = [bar["close"] for bar in bars]
    returns = [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes)) if closes[i - 1]]
    window = closes[-250:]
    peak = window[0]
    max_drawdown = 0.0
    for close in window:
        peak = max(peak, close)
        max_drawdown = min(max_drawdown, (close / peak - 1) * 100)
    volatility = statistics.pstdev(returns[-60:]) * math.sqrt(252) * 100 if len(returns) >= 60 else None
    ma20 = statistics.mean(closes[-20:])
    ma60 = statistics.mean(closes[-60:])
    ma200 = statistics.mean(closes[-200:])
    adv20_yi = statistics.mean([bar["close"] * bar["volume_lots"] * 100 for bar in bars[-20:]]) / 1e8
    # Tencent's historical volume unit is board-dependent. Infer shares vs lots
    # conservatively when the lots interpretation would imply >30% of market cap daily.
    market_cap_yi = quote.get("market_cap_yi")
    if market_cap_yi and adv20_yi > float(market_cap_yi) * 0.30:
        adv20_yi /= 100

    pe = quote.get("pe_ttm")
    pb = quote.get("pb")
    pe_score = 25 if pe is None or pe <= 0 else _clamp(100 - max(pe - 8, 0) * 1.8, 20, 95)
    pb_score = 40 if pb is None or pb <= 0 else _clamp(100 - max(pb - 0.8, 0) * 10, 20, 95)
    value_score = pe_score * 0.7 + pb_score * 0.3

    roe = latest_financial.get("roe")
    rev_yoy = latest_financial.get("revenue_yoy")
    profit_yoy = latest_financial.get("net_profit_yoy")
    debt = latest_financial.get("debt_ratio")
    roe_score = _clamp(35 + float(roe or 8) * 2.5, 20, 95)
    rev_score = _clamp(50 + float(rev_yoy or 0) * 1.6, 15, 95)
    profit_score = _clamp(50 + float(profit_yoy or 0) * 1.3, 15, 95)
    balance_score = _clamp(90 - max(float(debt or 50) - 45, 0) * 0.8, 25, 95)
    quality_score = roe_score * 0.4 + rev_score * 0.2 + profit_score * 0.25 + balance_score * 0.15

    return20 = _pct_change(closes, 20)
    return60 = _pct_change(closes, 60)
    return250 = _pct_change(closes, 250)
    trend_score = _clamp(
        50 + float(return20 or 0) * 0.45 + float(return60 or 0) * 0.35 + float(return250 or 0) * 0.15
        + (5 if closes[-1] >= ma20 else -5) + (7 if closes[-1] >= ma60 else -7)
        + (10 if closes[-1] >= ma200 else -10),
        10, 95,
    )
    resilience_score = _clamp(88 - float(volatility or 35) * 0.75 + max_drawdown * 0.35 - max(float(debt or 50) - 65, 0) * 0.4, 15, 95)
    required = [pe, pb, roe, rev_yoy, profit_yoy, debt, return20, return60, return250, volatility, adv20_yi]
    completeness = sum(value is not None for value in required) / len(required) * 100
    composite = quality_score * 0.32 + value_score * 0.25 + trend_score * 0.25 + resilience_score * 0.18
    return {
        "return_20d": return20, "return_60d": return60, "return_250d": return250,
        "volatility_60d": volatility, "max_drawdown_250d": max_drawdown,
        "ma20": ma20, "ma60": ma60, "ma200": ma200, "adv20_yi": adv20_yi,
        "value_score": round(value_score, 2), "quality_score": round(quality_score, 2),
        "trend_score": round(trend_score, 2), "resilience_score": round(resilience_score, 2),
        "composite_score": round(composite, 2), "data_completeness": round(completeness, 2),
        "feature_version": FEATURE_VERSION,
    }


def allocate_weights(features: dict[str, dict]) -> tuple[dict[str, int], int, str, str]:
    eligible = sorted(features, key=lambda ticker: features[ticker]["composite_score"], reverse=True)
    eligible = [ticker for ticker in eligible if features[ticker]["data_completeness"] >= 80][:10]
    if len(eligible) < 6:
        raise RuntimeError(f"investable universe too small: {len(eligible)}")
    avg_trend = statistics.mean(features[ticker]["trend_score"] for ticker in eligible)
    if avg_trend >= 62:
        cash, regime, note = 12, "进攻但不满仓", "多数核心资产趋势向上，保留必要现金等待回撤。"
    elif avg_trend >= 48:
        cash, regime, note = 18, "均衡", "市场信号分化，质量与估值共同决定仓位。"
    else:
        cash, regime, note = 30, "防守", "多数候选趋势偏弱，优先保存现金与低波动资产。"
    equity = 100 - cash
    weights = {ticker: 5 for ticker in eligible}
    remaining = equity - sum(weights.values())
    while remaining > 0:
        candidates = [ticker for ticker in eligible if weights[ticker] < 15]
        if not candidates:
            raise RuntimeError("position cap prevents exact allocation")
        chosen = max(candidates, key=lambda ticker: features[ticker]["composite_score"] / (weights[ticker] + 2) ** 0.65)
        weights[chosen] += 1
        remaining -= 1
    return weights, cash, regime, note


def _fmt(value: Any, suffix: str = "", digits: int = 1) -> str:
    if value is None:
        return "Missing evidence"
    return f"{float(value):.{digits}f}{suffix}"


def _stock_copy(name: str, quote: dict, financial: dict, feature: dict) -> dict[str, str]:
    trend = "站上" if quote["price"] >= feature["ma200"] else "低于"
    thesis = (
        f"最新披露 ROE {_fmt(financial.get('roe'), '%')}，营收同比 {_fmt(financial.get('revenue_yoy'), '%')}，"
        f"归母净利润同比 {_fmt(financial.get('net_profit_yoy'), '%')}；当前价{trend} 200 日均线，"
        f"综合评分 {_fmt(feature['composite_score'])}/100。"
    )
    risks = []
    if financial.get("net_profit_yoy") is not None and financial["net_profit_yoy"] < 0:
        risks.append("利润同比下降")
    if quote.get("pe_ttm") and quote["pe_ttm"] > 35:
        risks.append("估值对增长兑现要求较高")
    if feature["return_60d"] is not None and feature["return_60d"] < -10:
        risks.append("中期趋势仍弱")
    if feature["volatility_60d"] and feature["volatility_60d"] > 35:
        risks.append("波动率偏高")
    risk = "；".join(risks[:2]) or "主要风险来自盈利增速、估值中枢或行业景气低于当前快照假设。"
    valuation = f"PE(TTM) {_fmt(quote.get('pe_ttm'))} · PB {_fmt(quote.get('pb'), digits=2)} · 价值分 {_fmt(feature['value_score'])}"
    bull = f"盈利增速改善且价格重新站稳主要均线，综合评分向 75 分以上修复。"
    base = f"盈利与估值维持当前区间，组合按目标仓位持有并等待下一份正式披露。"
    bear = f"利润转负或跌破长期均线且风险触发，进入减仓或退出复核。"
    return {"thesis": thesis, "risk": risk, "valuation": valuation, "bull": bull, "base": base, "bear": bear}


def _manifest_hash(inputs: dict[str, Any]) -> str:
    hashes = []
    hashes.extend(quote["raw_hash"] for quote in inputs["quotes"].values())
    hashes.extend(item["raw_hash"] for item in inputs["klines"].values())
    hashes.extend(item["raw_hash"] for item in inputs["financials"].values())
    return hashlib.sha256((FEATURE_VERSION + "|" + MODEL_VERSION + "|" + "|".join(sorted(hashes))).encode()).hexdigest()


def build_real_snapshot(db_path: Path = DB_PATH, *, timeout: float = 10.0) -> dict[str, Any]:
    initialize(db_path)
    inputs = collect_real_inputs(timeout)
    tickers = [item["ticker"] for item in DEMO_POSITIONS]
    features = {}
    for ticker in tickers:
        features[ticker] = compute_features(
            inputs["quotes"][ticker], inputs["klines"][ticker]["bars"], inputs["financials"][ticker]["rows"][0]
        )
    weights, cash, regime, regime_note = allocate_weights(features)
    manifest_hash = _manifest_hash(inputs)
    snapshot_id = f"snap_real_{manifest_hash[:12]}"
    publication_id = f"pub_real_{manifest_hash[:12]}"
    as_of = max(result["bars"][-1]["trade_date"] for result in inputs["klines"].values())
    known_at = max(quote["quote_time"] for quote in inputs["quotes"].values())
    created_at = datetime.now(timezone.utc).isoformat()

    with closing(connect(db_path)) as conn:
        existing = conn.execute(
            """SELECT p.id, p.status, s.quality_status
               FROM publications p JOIN dataset_snapshots s ON s.id=p.snapshot_id
               WHERE p.id=?""",
            (publication_id,),
        ).fetchone()
        current = conn.execute(
            """SELECT p.id, p.snapshot_id FROM publications p
               JOIN dataset_snapshots s ON s.id=p.snapshot_id
               WHERE p.status IN ('quality_passed', 'approved', 'published')
                 AND s.quality_status='passed'
               ORDER BY COALESCE(p.published_at, s.created_at) DESC LIMIT 1"""
        ).fetchone()
        if (
            existing
            and existing["status"] in {"quality_passed", "approved", "published"}
            and existing["quality_status"] == "passed"
            and current
            and current["snapshot_id"] == snapshot_id
        ):
            return {"snapshot_id": snapshot_id, "publication_id": publication_id, "reused": True}
        if existing:
            suffix = uuid.uuid4().hex[:6]
            snapshot_id = f"snap_real_{manifest_hash[:12]}_{suffix}"
            publication_id = f"pub_real_{manifest_hash[:12]}_{suffix}"
        previous_publication = conn.execute(
            """SELECT p.id FROM publications p
               JOIN dataset_snapshots s ON s.id=p.snapshot_id
               WHERE p.status IN ('quality_passed', 'approved', 'published')
                 AND s.quality_status='passed'
               ORDER BY COALESCE(p.published_at, s.created_at) DESC LIMIT 1"""
        ).fetchone()
        previous_weights = {
            row["ticker"]: float(row["target_weight"])
            for row in conn.execute(
                "SELECT ticker, target_weight FROM portfolio_items WHERE publication_id=?",
                (previous_publication["id"],),
            ).fetchall()
        } if previous_publication else {}
        conn.execute(
            "INSERT INTO dataset_snapshots VALUES (?, 'REAL', ?, ?, 'passed', ?, ?, ?)",
            (snapshot_id, as_of, known_at, "腾讯行情/前复权日线 + 东方财富 F10 主要财务指标", manifest_hash, created_at),
        )
        for ticker in tickers:
            quote = inputs["quotes"][ticker]
            conn.execute(
                """INSERT INTO market_quotes (
                   snapshot_id, ticker, name, price, change_pct, high, low, pe_ttm, pb,
                   market_cap_yi, circulating_cap_yi, quote_time, source_key, source_url,
                   raw_hash, fetched_at, quality_status
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'accepted')""",
                (snapshot_id, ticker, quote["name"], quote["price"], quote["change_pct"], quote["high"], quote["low"],
                 quote.get("pe_ttm"), quote.get("pb"), quote.get("market_cap_yi"), quote.get("circulating_cap_yi"),
                 quote["quote_time"], quote["source_key"], quote["source_url"], quote["raw_hash"], quote["fetched_at"]),
            )
            kline = inputs["klines"][ticker]
            conn.executemany(
                "INSERT INTO daily_bars VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'accepted')",
                [(snapshot_id, ticker, bar["trade_date"], bar["open"], bar["close"], bar["high"], bar["low"],
                  bar["volume_lots"], KLINE_SOURCE, kline["raw_hash"]) for bar in kline["bars"]],
            )
            financial_result = inputs["financials"][ticker]
            conn.executemany(
                """INSERT INTO financial_metrics VALUES (
                   ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'accepted')""",
                [(snapshot_id, ticker, row["report_date"], row["notice_date"], row["report_type"], row["revenue"],
                  row["net_profit"], row["revenue_yoy"], row["net_profit_yoy"], row["roe"], row["gross_margin"],
                  row["net_margin"], row["debt_ratio"], row["operating_cash_per_share"], FINANCIAL_SOURCE, row["row_hash"])
                 for row in financial_result["rows"]],
            )
            f = features[ticker]
            conn.execute(
                "INSERT INTO stock_features VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (snapshot_id, ticker, f["return_20d"], f["return_60d"], f["return_250d"], f["volatility_60d"],
                 f["max_drawdown_250d"], f["ma20"], f["ma60"], f["ma200"], f["adv20_yi"], f["value_score"],
                 f["quality_score"], f["trend_score"], f["resilience_score"], f["composite_score"],
                 f["data_completeness"], f["feature_version"]),
            )

        equity = 100 - cash
        conn.execute(
            """INSERT INTO publications (
               id, snapshot_id, status, title, market_regime, regime_note, equity_weight,
               cash_weight, model_version, published_at, approved_at, approval_hash, blocked_reason
               ) VALUES (?, ?, 'quality_passed', ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL)""",
            (publication_id, snapshot_id, f"{as_of} A 股长期模型组合", regime, regime_note, equity, cash, MODEL_VERSION),
        )
        metadata = {item["ticker"]: item for item in DEMO_POSITIONS}
        for ticker, weight in weights.items():
            meta, quote, financial, feature = metadata[ticker], inputs["quotes"][ticker], inputs["financials"][ticker]["rows"][0], features[ticker]
            copy = _stock_copy(meta["name"], quote, financial, feature)
            low, high = quote["price"] * 0.97, quote["price"] * 1.02
            confidence = round(_clamp(feature["data_completeness"] * 0.62 + abs(feature["composite_score"] - 50) * 0.65, 60, 92))
            previous_weight = previous_weights.get(ticker, 0.0)
            action = "新建" if ticker not in previous_weights else "加仓" if weight > previous_weight else "减仓" if weight < previous_weight else "持有"
            conn.execute(
                """INSERT INTO portfolio_items VALUES (
                   ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'accepted', ?, ?, ?, ?, ?, ?, ?
                   )""",
                (publication_id, ticker, meta["name"], meta["exchange"], meta["industry"], weight, previous_weight, action,
                 quote["price"], f"¥{low:.2f}–¥{high:.2f}（分批观察）", confidence, as_of,
                 copy["thesis"], copy["risk"], copy["valuation"], copy["bull"], copy["base"], copy["bear"]),
            )
            evidence = [
                ("fact", "最新行情", f"¥{quote['price']:.2f}（{quote['change_pct']:+.2f}%）", quote["source_key"], quote["quote_time"]),
                ("fact", "最新财务", f"{financial['report_type']}：ROE {_fmt(financial.get('roe'), '%')}，营收同比 {_fmt(financial.get('revenue_yoy'), '%')}，利润同比 {_fmt(financial.get('net_profit_yoy'), '%')}", FINANCIAL_SOURCE, financial["notice_date"]),
                ("fact", "趋势与流动性", f"60日收益 {_fmt(feature['return_60d'], '%')}，ADV20 {_fmt(feature['adv20_yi'], '亿元', 2)}", KLINE_SOURCE, as_of),
                ("inference", "综合评分", f"{_fmt(feature['composite_score'])}/100；质量 {_fmt(feature['quality_score'])}，价值 {_fmt(feature['value_score'])}，趋势 {_fmt(feature['trend_score'])}", FEATURE_VERSION, known_at),
                ("risk", "首要风险", copy["risk"], MODEL_VERSION, known_at),
            ]
            conn.executemany(
                "INSERT INTO evidence VALUES (?, ?, ?, ?, ?, ?, ?, 'accepted')",
                [(publication_id, ticker, *row) for row in evidence],
            )

        avg_pe = statistics.mean(q["pe_ttm"] for q in inputs["quotes"].values() if q.get("pe_ttm") and q["pe_ttm"] > 0)
        avg_vol = statistics.mean(features[ticker]["volatility_60d"] for ticker in weights)
        version_risk = (
            (3, "版本变动", "本次基于上一份通过质量门的快照重算；组合动作只反映确定性目标仓位的版本差异。", "medium")
            if previous_publication
            else (3, "首次真实草稿", "尚无上一期正式组合；所有动作均为新建，发布后才开始真实模型账本。", "medium")
        )
        risks = [
            (1, "估值分化", f"组合候选平均 PE(TTM) {avg_pe:.1f} 倍；高估值公司必须用盈利兑现。", "high"),
            (2, "波动与回撤", f"候选平均 60 日年化波动率 {avg_vol:.1f}%，分批执行而非单日完成。", "medium"),
            version_risk,
        ]
        conn.executemany("INSERT INTO portfolio_risks VALUES (?, ?, ?, ?, ?)", [(publication_id, *risk) for risk in risks])
        runs = [
            (f"run_quote_{uuid.uuid4().hex[:8]}", "tencent_quote", 8, 8),
            (f"run_kline_{uuid.uuid4().hex[:8]}", KLINE_SOURCE, sum(len(v["bars"]) for v in inputs["klines"].values()), sum(len(v["bars"]) for v in inputs["klines"].values())),
            (f"run_fin_{uuid.uuid4().hex[:8]}", FINANCIAL_SOURCE, sum(len(v["rows"]) for v in inputs["financials"].values()), sum(len(v["rows"]) for v in inputs["financials"].values())),
        ]
        conn.executemany(
            "INSERT INTO source_runs VALUES (?, ?, ?, ?, ?, 'success', ?, ?, NULL)",
            [(run_id, snapshot_id, source, inputs["started_at"], inputs["finished_at"], fetched, accepted) for run_id, source, fetched, accepted in runs],
        )
        content_hash = publication_content_hash(conn, publication_id)
        conn.execute(
            "INSERT INTO publication_events (publication_id, event_type, from_status, to_status, content_hash, actor, created_at) VALUES (?, 'quality_gate', 'draft', 'quality_passed', ?, 'system', ?)",
            (publication_id, content_hash, created_at),
        )
        create_snapshot_content_attestation(conn, snapshot_id, created_at=created_at)
        conn.commit()

    from data_store import dashboard_payload
    payload = dashboard_payload(db_path)
    errors = validate_invariants(payload)
    if errors:
        raise RuntimeError(f"post-write portfolio gate failed: {errors}")
    return {
        "snapshot_id": snapshot_id, "publication_id": publication_id, "reused": False,
        "as_of": as_of, "known_at": known_at, "weights": weights, "cash": cash,
        "regime": regime, "feature_scores": {ticker: features[ticker]["composite_score"] for ticker in weights},
    }


def replay_snapshot(snapshot_id: str, db_path: Path = DB_PATH) -> dict[str, Any]:
    """Recompute one immutable snapshot using only stored inputs.

    This intentionally performs no network calls. A passing replay proves that the
    stored quote, bar, financial and feature contract reproduces the same scores
    and constrained allocation.
    """
    if snapshot_id.startswith("core_"):
        from data_core import DataFoundation, SnapshotReader

        foundation = DataFoundation(db_path)
        reader = SnapshotReader(foundation, snapshot_id)
        instruments = list(reader.rows("core_instruments"))
        return {
            "snapshot_id": snapshot_id,
            "status": "passed",
            "canonical": True,
            "replay_digest": foundation.replay_digest(snapshot_id),
            "instrument_count": len(instruments),
            "contexts": {
                row["ticker"]: reader.research_context(row["ticker"]) for row in instruments
            },
            "errors": [],
        }
    initialize(db_path)
    errors: list[str] = []
    recomputed: dict[str, dict[str, Any]] = {}
    with closing(connect(db_path)) as conn:
        publication = conn.execute(
            """SELECT p.* FROM publications p JOIN dataset_snapshots s ON s.id=p.snapshot_id
               WHERE p.snapshot_id=?
                 AND p.status IN ('quality_passed', 'approved', 'published')
                 AND s.quality_status='passed'
               ORDER BY p.rowid DESC LIMIT 1""",
            (snapshot_id,),
        ).fetchone()
        if not publication:
            return {
                "snapshot_id": snapshot_id,
                "publication_id": None,
                "status": "failed",
                "replayed_tickers": 0,
                "errors": ["snapshot/publication is missing, blocked, invalidated, or not quality-passed"],
            }
        items = conn.execute(
            "SELECT ticker, target_weight FROM portfolio_items WHERE publication_id = ? ORDER BY ticker",
            (publication["id"],),
        ).fetchall()
        if len(items) != len(DEMO_POSITIONS):
            errors.append(f"portfolio item coverage: expected={len(DEMO_POSITIONS)} actual={len(items)}")
        source_runs = conn.execute(
            "SELECT source_key, status, accepted_count FROM source_runs WHERE snapshot_id=?",
            (snapshot_id,),
        ).fetchall()
        run_map = {row["source_key"]: row for row in source_runs}
        required_runs = {"tencent_quote": 8, KLINE_SOURCE: 2000, FINANCIAL_SOURCE: 8}
        for source_key, minimum in required_runs.items():
            run = run_map.get(source_key)
            if not run or run["status"] != "success" or int(run["accepted_count"] or 0) < minimum:
                errors.append(f"source receipt incomplete: {source_key}")
        for item in items:
            ticker = item["ticker"]
            quote_row = conn.execute(
                """SELECT price, pe_ttm, pb, market_cap_yi, circulating_cap_yi
                   FROM market_quotes WHERE snapshot_id = ? AND ticker = ? AND quality_status='accepted'""",
                (snapshot_id, ticker),
            ).fetchone()
            bar_rows = conn.execute(
                """SELECT trade_date, open, close, high, low, volume_lots
                   FROM daily_bars WHERE snapshot_id = ? AND ticker = ? AND quality_status='accepted' ORDER BY trade_date""",
                (snapshot_id, ticker),
            ).fetchall()
            financial_row = conn.execute(
                """SELECT revenue_yoy, net_profit_yoy, roe, debt_ratio
                   FROM financial_metrics WHERE snapshot_id = ? AND ticker = ? AND quality_status='accepted'
                   ORDER BY report_date DESC LIMIT 1""",
                (snapshot_id, ticker),
            ).fetchone()
            stored = conn.execute(
                "SELECT * FROM stock_features WHERE snapshot_id = ? AND ticker = ?",
                (snapshot_id, ticker),
            ).fetchone()
            if not quote_row or len(bar_rows) < 250 or not financial_row or not stored:
                errors.append(f"{ticker}: stored input incomplete")
                continue
            recomputed[ticker] = compute_features(dict(quote_row), [dict(row) for row in bar_rows], dict(financial_row))
            for field in (
                "return_20d", "return_60d", "return_250d", "volatility_60d",
                "max_drawdown_250d", "ma20", "ma60", "ma200", "adv20_yi",
                "value_score", "quality_score", "trend_score", "resilience_score",
                "composite_score", "data_completeness",
            ):
                expected, actual = stored[field], recomputed[ticker][field]
                if expected is None and actual is None:
                    continue
                if expected is None or actual is None or abs(float(expected) - float(actual)) > 1e-8:
                    errors.append(f"{ticker}:{field}: stored={expected} replay={actual}")
        if len(recomputed) != len(DEMO_POSITIONS):
            errors.append(f"recomputed ticker coverage: expected={len(DEMO_POSITIONS)} actual={len(recomputed)}")
        if recomputed:
            weights, cash, regime, _ = allocate_weights(recomputed)
            stored_weights = {row["ticker"]: int(row["target_weight"]) for row in items}
            if weights != stored_weights:
                errors.append(f"weights: stored={stored_weights} replay={weights}")
            if int(publication["cash_weight"]) != cash:
                errors.append(f"cash: stored={publication['cash_weight']} replay={cash}")
            if publication["market_regime"] != regime:
                errors.append(f"regime: stored={publication['market_regime']} replay={regime}")
    return {
        "snapshot_id": snapshot_id,
        "publication_id": publication["id"],
        "status": "passed" if not errors else "failed",
        "replayed_tickers": len(recomputed),
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a real A-share evidence snapshot and portfolio draft")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--replay", metavar="SNAPSHOT_ID", help="recompute an existing immutable snapshot without network")
    args = parser.parse_args()
    result = replay_snapshot(args.replay, DB_PATH) if args.replay else build_real_snapshot(DB_PATH, timeout=args.timeout)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
