from __future__ import annotations

from typing import Any


AS_OF = "2026-07-17"
KNOWN_AT = "2026-07-17T16:30:00+08:00"


# Deterministic acceptance fixtures. They exercise market structure and PIT edge
# cases; they are never labelled as live or production data.
INSTRUMENTS: tuple[dict[str, Any], ...] = (
    {"ticker": "600519.SH", "name": "贵州茅台", "exchange": "SSE", "board": "MAIN", "industry": "食品饮料", "case": "normal"},
    {"ticker": "600036.SH", "name": "招商银行", "exchange": "SSE", "board": "MAIN", "industry": "银行", "case": "normal"},
    {"ticker": "600900.SH", "name": "长江电力", "exchange": "SSE", "board": "MAIN", "industry": "公用事业", "case": "ex_rights"},
    {"ticker": "601088.SH", "name": "中国神华", "exchange": "SSE", "board": "MAIN", "industry": "煤炭", "case": "normal"},
    {"ticker": "000333.SZ", "name": "美的集团", "exchange": "SZSE", "board": "MAIN", "industry": "家用电器", "case": "normal"},
    {"ticker": "000001.SZ", "name": "平安银行", "exchange": "SZSE", "board": "MAIN", "industry": "银行", "case": "financial_revision"},
    {"ticker": "300750.SZ", "name": "宁德时代", "exchange": "SZSE", "board": "CHINEXT", "industry": "电力设备", "case": "normal"},
    {"ticker": "300059.SZ", "name": "东方财富", "exchange": "SZSE", "board": "CHINEXT", "industry": "非银金融", "case": "suspended"},
    {"ticker": "688036.SH", "name": "传音控股", "exchange": "SSE", "board": "STAR", "industry": "消费电子", "case": "normal"},
    {"ticker": "688981.SH", "name": "中芯国际", "exchange": "SSE", "board": "STAR", "industry": "半导体", "case": "normal"},
    {"ticker": "830799.BJ", "name": "艾融软件", "exchange": "BSE", "board": "BSE", "industry": "软件服务", "case": "normal"},
    {"ticker": "920002.BJ", "name": "万达轴承", "exchange": "BSE", "board": "BSE", "industry": "机械设备", "case": "normal"},
)


def fixture_payload() -> dict[str, Any]:
    instruments = []
    bars = []
    statuses = []
    factors = []
    actions = []
    financials = []
    for index, item in enumerate(INSTRUMENTS, start=1):
        instrument_id = f"CN:{item['ticker']}"
        instruments.append({
            **item,
            "instrument_id": instrument_id,
            "listed_at": f"20{10 + index % 10:02d}-01-01",
        })
        suspended = item["case"] == "suspended"
        statuses.append({
            "instrument_id": instrument_id,
            "trade_date": AS_OF,
            "trading_status": "suspended" if suspended else "normal",
        })
        factor = 0.92 if item["case"] == "ex_rights" else 1.0
        factors.append({"instrument_id": instrument_id, "trade_date": AS_OF, "factor": factor, "version": 1})
        if not suspended:
            close = float(20 + index * 7)
            bars.append({
                "instrument_id": instrument_id,
                "trade_date": AS_OF,
                "open": close - 1,
                "high": close + 2,
                "low": close - 2,
                "close": close,
                "volume": float(1_000_000 + index * 10_000),
                "amount": close * float(1_000_000 + index * 10_000),
                "adjustment_version": 1,
            })
        if item["case"] == "ex_rights":
            actions.append({
                "action_id": "action:600900:20260717:cash_dividend:v1",
                "instrument_id": instrument_id,
                "action_type": "cash_dividend",
                "ex_date": AS_OF,
                "announced_at": "2026-06-30T18:00:00+08:00",
                "version": 1,
                "details": {"cash_per_share": 0.82},
            })
        revisions = (1, 2) if item["case"] == "financial_revision" else (1,)
        for revision in revisions:
            financials.append({
                "fact_id": f"fact:{item['ticker']}:20260331:revenue:r{revision}",
                "instrument_id": instrument_id,
                "report_date": "2026-03-31",
                "announced_at": f"2026-04-{20 + revision:02d}T18:00:00+08:00",
                "revision": revision,
                "metric_key": "revenue",
                "metric_value": float(index * 1_000_000_000 + revision * 10_000),
                "unit": "CNY",
            })
    return {
        "fixture": True,
        "as_of": AS_OF,
        "known_at": KNOWN_AT,
        "instruments": instruments,
        "calendar": [
            {"exchange": exchange, "trade_date": AS_OF, "is_open": 1, "previous_open_date": "2026-07-16"}
            for exchange in ("SSE", "SZSE", "BSE")
        ],
        "statuses": statuses,
        "factors": factors,
        "actions": actions,
        "bars": bars,
        "financials": financials,
    }
