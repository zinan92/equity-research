"""Cross-market market-price history adapter and explicit field-source policy.

Historical OHLC is deliberately separate from point-in-time valuation: a daily
bar cannot prove historical market cap, PE, PB, or PEG.  Those values remain
snapshot fields with their own sources or an explicit gap.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import re
from typing import Any, Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .contracts import RawCapture, RecordDomain, RecordEnvelope, SourceManifest
from .ingestion import FetchRequest, FetchedPayload

YAHOO_CHART_SOURCE = "yahoo_chart_cross_market_v1"

MARKET_FIELD_SOURCES = {
    "price": {"A": ("tencent_quote", "eastmoney_quote"), "HK": ("yahoo_chart", "sina_hk"), "US": ("yahoo_chart",), "JP": ("yahoo_chart",)},
    "chg": {"A": ("tencent_quote", "eastmoney_quote"), "HK": ("yahoo_chart",), "US": ("yahoo_chart",), "JP": ("yahoo_chart",)},
    "mcap": {"A": ("eastmoney_quote", "tencent_quote"), "HK": ("yahoo_snapshot",), "US": ("yahoo_snapshot",), "JP": ("yahoo_snapshot",)},
    "pe": {"A": ("eastmoney_quote", "tencent_quote"), "HK": ("yahoo_snapshot",), "US": ("yahoo_snapshot",), "JP": ("yahoo_snapshot",)},
    "pb": {"A": ("eastmoney_quote", "tencent_quote"), "HK": ("yahoo_snapshot",), "US": ("yahoo_snapshot",), "JP": ("yahoo_snapshot",)},
    "peg": {"A": ("derived_pe_growth",), "HK": ("derived_pe_growth",), "US": ("derived_pe_growth",), "JP": ("derived_pe_growth",)},
}


@dataclass(frozen=True)
class GlobalInstrument:
    ticker: str
    market: str
    yahoo_symbol: str
    instrument_id: str
    currency: str


def normalize_global_ticker(value: str) -> GlobalInstrument:
    raw = str(value or "").strip().upper()
    if re.fullmatch(r"\d{4,5}\.HK", raw):
        ticker = raw.split(".", 1)[0].zfill(5) + ".HK"
        return GlobalInstrument(ticker, "HK", ticker, f"HK:{ticker}", "HKD")
    if re.fullmatch(r"\d{4}\.T", raw):
        return GlobalInstrument(raw, "JP", raw, f"JP:{raw}", "JPY")
    if re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,14}", raw):
        return GlobalInstrument(raw, "US", raw, f"US:{raw}", "USD")
    raise ValueError("supported symbols are US (NVDA), HK (00700.HK), or Japan (7203.T)")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _http_get(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "ParkResearchDashboard/0.4"})
    with urlopen(request, timeout=15) as response:
        return response.read()


class YahooChartAdapter:
    """Polite, one-symbol historical-bar adapter for HK/US/JP validation."""

    def __init__(self, *, http_get=_http_get) -> None:
        self.http_get = http_get
        self.manifest = SourceManifest(
            source_key=YAHOO_CHART_SOURCE, domain_scope=RecordDomain.MARKET.value,
            authority_tier="supplementary_only", provider_version="yahoo-chart-2026-07",
            schema_version="yahoo-chart-bars-v1", license_status="configured_internal_use",
            source_url="https://query1.finance.yahoo.com/v8/finance/chart/",
            quality_flags=("cross_market_history", "valuation_not_inferred_from_bars"),
        )

    async def fetch(self, request: FetchRequest) -> FetchedPayload:
        instrument = normalize_global_ticker(request.entity_key)
        start = int(request.parameters["period1"])
        end = int(request.parameters["period2"])
        if end <= start:
            raise ValueError("period2 must be later than period1")
        url = self.manifest.source_url + instrument.yahoo_symbol + "?" + urlencode({"period1": start, "period2": end, "interval": "1d", "events": "history"})
        body = await asyncio.to_thread(self.http_get, url)
        now = _utc_now()
        return FetchedPayload(body, url, now, now, "application/json", data_kind="real")

    def parse(self, request: FetchRequest, fetched: FetchedPayload, raw: RawCapture) -> Iterable[RecordEnvelope]:
        instrument = normalize_global_ticker(request.entity_key)
        payload = json.loads(fetched.body.decode("utf-8"))
        result = ((payload.get("chart") or {}).get("result") or [None])[0]
        if not isinstance(result, dict):
            raise ValueError("Yahoo chart response has no result")
        timestamps = result.get("timestamp") or []
        quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
        closes = quote.get("close") or []
        records = []
        for timestamp, close in zip(timestamps, closes):
            if close is None:
                continue
            trade_date = datetime.fromtimestamp(timestamp, timezone.utc).date().isoformat()
            records.append(RecordEnvelope.accepted(
                domain=RecordDomain.MARKET,
                entity_key=f"{instrument.instrument_id}:bar:{trade_date}:close",
                payload={"instrument_id": instrument.instrument_id, "observed_at": fetched.known_at,
                         "metric": "daily_close", "value": float(close), "unit": f"{instrument.currency}/share",
                         "trade_date": trade_date, "ticker": instrument.ticker, "market": instrument.market},
                manifest=self.manifest, raw=raw,
            ))
        if not records:
            raise ValueError("Yahoo chart response has no usable daily closes")
        return tuple(records)


def compare_snapshot(expected: dict[str, Any], observed: dict[str, Any]) -> dict[str, Any]:
    """Field-tolerance comparison; absent historical valuation stays absent."""
    tolerances = {"price": 0.005, "mcap": 0.02, "pe": 0.05, "pb": 0.05}
    rows = []
    for field, tolerance in tolerances.items():
        target, actual = expected.get(field), observed.get(field)
        if target in (None, "") or actual in (None, ""):
            rows.append({"field": field, "status": "missing", "tolerance": tolerance})
            continue
        error = abs(float(actual) - float(target)) / max(abs(float(target)), 1e-12)
        rows.append({"field": field, "status": "pass" if error <= tolerance else "outlier", "relative_error": error, "tolerance": tolerance})
    return {"rows": rows, "passed": all(item["status"] != "outlier" for item in rows)}
