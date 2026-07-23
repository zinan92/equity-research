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
YAHOO_SNAPSHOT_SOURCE = "yahoo_snapshot_cross_market_v1"

MARKET_FIELD_SOURCES = {
    "price": {"A": ("tencent_quote", "eastmoney_quote"), "HK": ("yahoo_chart", "sina_hk"), "US": ("yahoo_chart",), "JP": ("yahoo_chart",)},
    "chg": {"A": ("tencent_quote", "eastmoney_quote"), "HK": ("yahoo_chart",), "US": ("yahoo_chart",), "JP": ("yahoo_chart",)},
    "mcap": {"A": ("eastmoney_quote", "tencent_quote"), "HK": ("yahoo_snapshot",), "US": ("yahoo_snapshot",), "JP": ("yahoo_snapshot",)},
    "mcap_usd": {"A": ("eastmoney_quote_plus_fx",), "HK": ("yahoo_snapshot_plus_fx",), "US": ("yahoo_snapshot",), "JP": ("yahoo_snapshot_plus_fx",)},
    "pe": {"A": ("eastmoney_quote", "tencent_quote"), "HK": ("yahoo_snapshot",), "US": ("yahoo_snapshot",), "JP": ("yahoo_snapshot",)},
    "pb": {"A": ("eastmoney_quote", "tencent_quote"), "HK": ("yahoo_snapshot",), "US": ("yahoo_snapshot",), "JP": ("yahoo_snapshot",)},
    "peg": {"A": ("derived_pe_growth",), "HK": ("yahoo_snapshot", "derived_pe_growth"), "US": ("yahoo_snapshot", "derived_pe_growth"), "JP": ("yahoo_snapshot", "derived_pe_growth")},
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
        # Yahoo uses a four-character Hong Kong display symbol (0700.HK),
        # while our canonical identifier preserves five-digit securities codes.
        yahoo_symbol = raw.split(".", 1)[0].lstrip("0").zfill(4) + ".HK"
        return GlobalInstrument(ticker, "HK", yahoo_symbol, f"HK:{ticker}", "HKD")
    if re.fullmatch(r"\d{4}\.T", raw):
        return GlobalInstrument(raw, "JP", raw, f"JP:{raw}", "JPY")
    if re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,14}", raw):
        return GlobalInstrument(raw, "US", raw.replace(".", "-"), f"US:{raw}", "USD")
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


def _yfinance_snapshot(symbol: str) -> dict[str, Any]:
    """Read Yahoo fields through yfinance without persisting a hidden wire body.

    Yahoo's unauthenticated quote endpoints currently return 401 in this runtime,
    while yfinance maintains the cookie/crumb handshake.  The adapter therefore
    records a *client-normalized* source body and marks it as such rather than
    pretending that it captured Yahoo's original HTTP response.
    """
    try:
        import yfinance as yf
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError("yfinance is required for Yahoo snapshot collection") from exc
    ticker = yf.Ticker(symbol)
    fast = dict(ticker.fast_info or {})
    info = dict(ticker.info or {})
    return {
        "currency": fast.get("currency") or info.get("currency"),
        "last_price": fast.get("lastPrice") or info.get("regularMarketPrice"),
        "previous_close": fast.get("previousClose") or info.get("regularMarketPreviousClose"),
        "market_cap": fast.get("marketCap") or info.get("marketCap"),
        "pe_ttm": info.get("trailingPE"),
        "pb": info.get("priceToBook"),
        "peg_trailing": info.get("trailingPegRatio"),
    }


class YahooSnapshotAdapter:
    """Point-in-time price and valuation snapshot for HK, US, and Japan.

    This is deliberately not used to reconstruct a historical valuation.  A
    snapshot is only valid at ``known_at``; historical fields stay missing until
    an archival source is introduced.
    """

    def __init__(self, *, snapshot_getter=_yfinance_snapshot) -> None:
        self.snapshot_getter = snapshot_getter
        self.manifest = SourceManifest(
            source_key=YAHOO_SNAPSHOT_SOURCE, domain_scope=RecordDomain.MARKET.value,
            authority_tier="supplementary_only", provider_version="yfinance-yahoo-2026-07",
            schema_version="yahoo-client-normalized-snapshot-v1", license_status="configured_internal_use",
            source_url="https://finance.yahoo.com/quote/",
            quality_flags=("cross_market_snapshot", "client_normalized_capture", "not_historical_valuation"),
        )

    async def fetch(self, request: FetchRequest) -> FetchedPayload:
        instrument = normalize_global_ticker(request.entity_key)
        snapshot = await asyncio.to_thread(self.snapshot_getter, instrument.yahoo_symbol)
        if not isinstance(snapshot, dict):
            raise ValueError("Yahoo snapshot getter must return an object")
        now = _utc_now()
        # This is the exact normalized payload consumed by the product.  It is
        # hashable/auditable but explicitly not represented as an original wire capture.
        body = json.dumps({"symbol": instrument.yahoo_symbol, "snapshot": snapshot}, ensure_ascii=False, sort_keys=True).encode("utf-8")
        return FetchedPayload(body, self.manifest.source_url + instrument.yahoo_symbol, now, now, "application/json", data_kind="real")

    def parse(self, request: FetchRequest, fetched: FetchedPayload, raw: RawCapture) -> Iterable[RecordEnvelope]:
        instrument = normalize_global_ticker(request.entity_key)
        document = json.loads(fetched.body.decode("utf-8"))
        snapshot = document.get("snapshot") or {}
        currency = str(snapshot.get("currency") or instrument.currency).upper()
        observed_at = fetched.known_at
        values: list[tuple[str, Any, str]] = [
            ("price", snapshot.get("last_price"), f"{currency}/share"),
            ("market_cap", snapshot.get("market_cap"), currency),
            ("pe_ttm", snapshot.get("pe_ttm"), "x"),
            ("pb", snapshot.get("pb"), "x"),
            ("peg_trailing", snapshot.get("peg_trailing"), "x"),
        ]
        previous_close = snapshot.get("previous_close")
        last_price = snapshot.get("last_price")
        if isinstance(previous_close, (int, float)) and previous_close and isinstance(last_price, (int, float)):
            values.append(("change_pct", (float(last_price) / float(previous_close) - 1.0) * 100.0, "%"))
        if currency == "USD" and snapshot.get("market_cap") is not None:
            values.append(("market_cap_usd", snapshot["market_cap"], "USD"))
        records = []
        for metric, value, unit in values:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            records.append(RecordEnvelope.accepted(
                domain=RecordDomain.MARKET,
                entity_key=f"{instrument.instrument_id}:snapshot:{metric}:{observed_at}",
                payload={"instrument_id": instrument.instrument_id, "observed_at": observed_at,
                         "metric": metric, "value": float(value), "unit": unit,
                         "ticker": instrument.ticker, "market": instrument.market,
                         "currency": currency, "historical_reconstruction_eligible": False},
                manifest=self.manifest, raw=raw,
            ))
        if not records:
            raise ValueError("Yahoo snapshot response has no usable market fields")
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
