"""Cross-market market-price history adapter and explicit field-source policy.

Historical OHLC is deliberately separate from point-in-time valuation: a daily
bar cannot prove historical market cap, PE, PB, or PEG.  Those values remain
snapshot fields with their own sources or an explicit gap.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import json
import re
import time
from typing import Any, Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .contracts import RawCapture, RecordDomain, RecordEnvelope, SourceManifest
from .ingestion import FetchRequest, FetchedPayload

YAHOO_CHART_SOURCE = "yahoo_chart_cross_market_v1"
YAHOO_SNAPSHOT_SOURCE = "yahoo_snapshot_cross_market_v1"
YAHOO_FX_SOURCE = "yahoo_fx_history_v1"
SEC_COMPANY_FACTS_SOURCE = "sec_company_facts_pit_v1"

MARKET_FIELD_SOURCES = {
    "price": {"A": ("tencent_quote", "eastmoney_quote"), "HK": ("yahoo_chart", "sina_hk"), "US": ("yahoo_chart",), "JP": ("yahoo_chart",)},
    "chg": {"A": ("tencent_quote", "eastmoney_quote"), "HK": ("yahoo_chart",), "US": ("yahoo_chart",), "JP": ("yahoo_chart",)},
    "mcap": {"A": ("eastmoney_quote", "tencent_quote"), "HK": ("yahoo_snapshot",), "US": ("yahoo_snapshot",), "JP": ("yahoo_snapshot",)},
    "mcap_usd": {"A": ("eastmoney_quote_plus_fx",), "HK": ("yahoo_snapshot_plus_fx",), "US": ("yahoo_snapshot",), "JP": ("yahoo_snapshot_plus_fx",)},
    "pe": {"A": ("eastmoney_quote", "tencent_quote"), "HK": ("yahoo_snapshot",), "US": ("yahoo_snapshot",), "JP": ("yahoo_snapshot",)},
    "pb": {"A": ("eastmoney_quote", "tencent_quote"), "HK": ("yahoo_snapshot",), "US": ("yahoo_snapshot",), "JP": ("yahoo_snapshot",)},
    "peg": {"A": ("derived_pe_growth",), "HK": ("yahoo_snapshot", "derived_pe_growth"), "US": ("yahoo_snapshot", "derived_pe_growth"), "JP": ("yahoo_snapshot", "derived_pe_growth")},
}

HISTORICAL_MARKET_FIELD_POLICY: dict[str, dict[str, dict[str, Any]]] = {
    "price": {
        "A": {"primary": "tencent_quote", "fallback": "eastmoney_quote", "confidence": "high"},
        "HK": {"primary": "yahoo_chart", "fallback": "sina_hk", "confidence": "high"},
        "US": {"primary": "yahoo_chart", "fallback": None, "confidence": "high"},
        "JP": {"primary": "yahoo_chart", "fallback": None, "confidence": "high"},
    },
    "chg": {
        market: {
            "primary": policy["primary"],
            "fallback": policy["fallback"],
            "confidence": "high",
            "derivation": "same-source consecutive closes",
        }
        for market, policy in {
            "A": {"primary": "tencent_quote", "fallback": "eastmoney_quote"},
            "HK": {"primary": "yahoo_chart", "fallback": "sina_hk"},
            "US": {"primary": "yahoo_chart", "fallback": None},
            "JP": {"primary": "yahoo_chart", "fallback": None},
        }.items()
    },
    "mcap": {
        "A": {"primary": "canonical_a_share_snapshot", "fallback": "official_shares_x_price", "confidence": "medium"},
        "HK": {"primary": "exchange_or_issuer_shares_x_price", "fallback": None, "confidence": "medium", "gap": "PIT share-count adapter"},
        "US": {"primary": "sec_companyfacts_shares_x_yahoo_close", "fallback": "issuer_filing_shares_x_price", "confidence": "medium"},
        "JP": {"primary": "exchange_or_issuer_shares_x_price", "fallback": None, "confidence": "medium", "gap": "PIT share-count adapter"},
    },
    "mcap_usd": {
        market: {
            "primary": "same_date_local_mcap_plus_frozen_fx" if market != "US" else "sec_companyfacts_shares_x_yahoo_close",
            "fallback": None,
            "confidence": "medium",
            "gap": None if market == "US" else "same-date PIT local market cap",
        }
        for market in ("A", "HK", "US", "JP")
    },
    "pe": {
        "A": {"primary": "PIT_market_cap_divided_by_CNINFO_TTM_income", "fallback": "provider_same_date_snapshot", "confidence": "medium"},
        "HK": {"primary": "PIT_market_cap_divided_by_issuer_TTM_income", "fallback": "provider_same_date_snapshot", "confidence": "medium", "gap": "PIT filing normalizer"},
        "US": {"primary": "PIT_market_cap_divided_by_SEC_GAAP_TTM_income", "fallback": "provider_same_date_snapshot", "confidence": "medium"},
        "JP": {"primary": "PIT_market_cap_divided_by_issuer_TTM_income", "fallback": "provider_same_date_snapshot", "confidence": "medium", "gap": "PIT filing normalizer"},
    },
    "pb": {
        "A": {"primary": "PIT_market_cap_divided_by_CNINFO_equity", "fallback": "provider_same_date_snapshot", "confidence": "medium"},
        "HK": {"primary": "PIT_market_cap_divided_by_issuer_equity", "fallback": "provider_same_date_snapshot", "confidence": "medium", "gap": "PIT filing normalizer"},
        "US": {"primary": "PIT_market_cap_divided_by_SEC_equity", "fallback": "provider_same_date_snapshot", "confidence": "medium"},
        "JP": {"primary": "PIT_market_cap_divided_by_issuer_equity", "fallback": "provider_same_date_snapshot", "confidence": "medium", "gap": "PIT filing normalizer"},
    },
    "peg": {
        market: {
            "primary": "PE_divided_by_versioned_growth_estimate",
            "fallback": "PE_divided_by_PIT_TTM_growth",
            "confidence": "low",
            "gap": "benchmark growth basis undisclosed; definitions must not be mixed",
        }
        for market in ("A", "HK", "US", "JP")
    },
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
    error: Exception | None = None
    for attempt in range(3):
        try:
            request = Request(url, headers={"User-Agent": "ParkResearchDashboard/0.4"})
            with urlopen(request, timeout=20) as response:
                return response.read()
        except Exception as exc:
            error = exc
            if attempt < 2:
                time.sleep(0.5 * (2**attempt))
    raise RuntimeError(f"market source fetch failed after 3 attempts: {error}") from error


def _sec_http_get(url: str) -> bytes:
    """Polite SEC fetch with a declared agent and bounded transient retries."""

    error: Exception | None = None
    for attempt in range(3):
        try:
            request = Request(
                url,
                headers={
                    "User-Agent": "ParkEquityResearch/1.0 research-agent",
                    "Accept-Encoding": "identity",
                },
            )
            with urlopen(request, timeout=30) as response:
                return response.read()
        except Exception as exc:  # urllib wraps TLS EOF and HTTP failures differently
            error = exc
            if attempt < 2:
                time.sleep(0.5 * (2**attempt))
    raise RuntimeError(f"SEC companyfacts fetch failed after 3 attempts: {error}") from error


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


class YahooFxAdapter:
    """Freeze a same-date USD conversion rate without substituting today's FX."""

    def __init__(self, *, http_get=_http_get) -> None:
        self.http_get = http_get
        self.manifest = SourceManifest(
            source_key=YAHOO_FX_SOURCE,
            domain_scope=RecordDomain.MARKET.value,
            authority_tier="supplementary_only",
            provider_version="yahoo-chart-2026-07",
            schema_version="yahoo-fx-bars-v1",
            license_status="configured_internal_use",
            source_url="https://query1.finance.yahoo.com/v8/finance/chart/",
            quality_flags=("historical_fx", "usd_per_local_currency", "same_date_required"),
        )

    async def fetch(self, request: FetchRequest) -> FetchedPayload:
        currency = str(request.entity_key or "").strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", currency) or currency == "USD":
            raise ValueError("FX entity_key must be a non-USD ISO-style currency")
        start = int(request.parameters["period1"])
        end = int(request.parameters["period2"])
        if end <= start:
            raise ValueError("period2 must be later than period1")
        symbol = f"{currency}USD=X"
        url = self.manifest.source_url + symbol + "?" + urlencode(
            {"period1": start, "period2": end, "interval": "1d", "events": "history"}
        )
        body = await asyncio.to_thread(self.http_get, url)
        now = _utc_now()
        return FetchedPayload(body, url, now, now, "application/json", data_kind="real")

    def parse(
        self, request: FetchRequest, fetched: FetchedPayload, raw: RawCapture
    ) -> Iterable[RecordEnvelope]:
        currency = str(request.entity_key).strip().upper()
        payload = json.loads(fetched.body.decode("utf-8"))
        result = ((payload.get("chart") or {}).get("result") or [None])[0]
        if not isinstance(result, dict):
            raise ValueError("Yahoo FX response has no result")
        timestamps = result.get("timestamp") or []
        quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
        closes = quote.get("close") or []
        records = []
        for timestamp, close in zip(timestamps, closes):
            if not isinstance(close, (int, float)) or isinstance(close, bool) or close <= 0:
                continue
            trade_date = datetime.fromtimestamp(timestamp, timezone.utc).date().isoformat()
            records.append(
                RecordEnvelope.accepted(
                    domain=RecordDomain.MARKET,
                    entity_key=f"FX:{currency}:USD:{trade_date}",
                    payload={
                        "instrument_id": f"FX:{currency}:USD",
                        "observed_at": fetched.known_at,
                        "metric": "usd_per_local_currency",
                        "value": float(close),
                        "unit": f"USD/{currency}",
                        "trade_date": trade_date,
                        "currency": currency,
                        "historical_reconstruction_eligible": True,
                    },
                    manifest=self.manifest,
                    raw=raw,
                )
            )
        if not records:
            raise ValueError("Yahoo FX response has no usable daily closes")
        return tuple(records)


def _fact_duration(row: dict[str, Any]) -> int | None:
    try:
        return (date.fromisoformat(str(row["end"])) - date.fromisoformat(str(row["start"]))).days
    except (KeyError, TypeError, ValueError):
        return None


def _eligible_fact_rows(
    rows: Iterable[dict[str, Any]], as_of: date
) -> list[dict[str, Any]]:
    by_period: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        filed = str(row.get("filed") or "")
        end = str(row.get("end") or "")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", filed) or not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}", end
        ):
            continue
        if date.fromisoformat(filed) > as_of or date.fromisoformat(end) > as_of:
            continue
        if isinstance(row.get("val"), bool) or not isinstance(row.get("val"), (int, float)):
            continue
        # Keep the filing form in the identity. A later proxy statement may
        # repeat a 10-K value; replacing the 10-K row with DEF 14A would erase
        # the annual fact needed for point-in-time TTM reconstruction.
        key = (
            str(row.get("start") or ""),
            end,
            str(row.get("form") or "").upper(),
        )
        existing = by_period.get(key)
        if existing is None or str(existing.get("filed")) < filed:
            by_period[key] = dict(row)
    return list(by_period.values())


def _concept_rows(
    document: dict[str, Any],
    candidates: tuple[tuple[str, str, tuple[str, ...]], ...],
    as_of: date,
    *,
    preserve_history: bool = False,
) -> tuple[list[dict[str, Any]], str, str, str] | None:
    facts = document.get("facts") or {}
    for taxonomy, concept, units in candidates:
        unit_map = (((facts.get(taxonomy) or {}).get(concept) or {}).get("units") or {})
        for unit in units:
            raw_rows = [row for row in unit_map.get(unit) or () if isinstance(row, dict)]
            eligible = _eligible_fact_rows(raw_rows, as_of)
            if eligible:
                return (raw_rows if preserve_history else eligible), taxonomy, concept, unit
    return None


def _latest_instant_fact(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    return max(rows, key=lambda row: (str(row.get("end")), str(row.get("filed"))))


def _ttm_income(
    rows: Iterable[dict[str, Any]], as_of: date
) -> tuple[float, tuple[dict[str, Any], ...], str] | None:
    eligible = _eligible_fact_rows(rows, as_of)
    annual = [
        row
        for row in eligible
        if str(row.get("form") or "").upper() in {"10-K", "10-K/A", "20-F", "20-F/A"}
        and (_fact_duration(row) or 0) >= 300
    ]
    if not annual:
        return None
    base = max(annual, key=lambda row: (str(row.get("end")), str(row.get("filed"))))
    base_value = float(base["val"])
    base_form = str(base.get("form") or "").upper()
    if base_form.startswith("20-F"):
        return base_value, (base,), "annual_only_foreign_issuer"

    interim = [
        row
        for row in eligible
        if str(row.get("form") or "").upper() in {"10-Q", "10-Q/A"}
        and 40 <= (_fact_duration(row) or 0) <= 300
        and str(row.get("end")) > str(base.get("end"))
    ]
    if not interim:
        return base_value, (base,), "latest_annual"
    current = max(interim, key=lambda row: (str(row.get("end")), _fact_duration(row) or 0))
    current_end = date.fromisoformat(str(current["end"]))
    current_duration = _fact_duration(current) or 0
    comparables = [
        row
        for row in eligible
        if row is not current
        and str(row.get("form") or "").upper() in {"10-Q", "10-Q/A"}
        and abs((_fact_duration(row) or 0) - current_duration) <= 20
        and 330
        <= (current_end - date.fromisoformat(str(row.get("end")))).days
        <= 400
    ]
    if not comparables:
        return base_value, (base,), "latest_annual_missing_comparable_interim"
    prior = min(
        comparables,
        key=lambda row: abs(
            (current_end - date.fromisoformat(str(row.get("end")))).days - 365
        ),
    )
    return base_value + float(current["val"]) - float(prior["val"]), (
        base,
        current,
        prior,
    ), "annual_plus_current_ytd_minus_prior_ytd"


def sec_point_in_time_inputs(
    document: dict[str, Any], as_of_value: str
) -> dict[str, Any]:
    """Extract filed-before-as-of valuation inputs from one SEC companyfacts body."""

    as_of = date.fromisoformat(as_of_value)
    shares_match = _concept_rows(
        document,
        (
            ("dei", "EntityCommonStockSharesOutstanding", ("shares",)),
            ("ifrs-full", "NumberOfSharesOutstanding", ("shares",)),
        ),
        as_of,
    )
    equity_match = _concept_rows(
        document,
        (
            ("us-gaap", "StockholdersEquity", ("USD",)),
            (
                "us-gaap",
                "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
                ("USD",),
            ),
            ("ifrs-full", "Equity", ("USD", "EUR", "GBP", "JPY")),
            (
                "ifrs-full",
                "EquityAttributableToOwnersOfParent",
                ("USD", "EUR", "GBP", "JPY"),
            ),
        ),
        as_of,
    )
    income_match = _concept_rows(
        document,
        (
            ("us-gaap", "NetIncomeLoss", ("USD",)),
            ("us-gaap", "NetIncomeLossAvailableToCommonStockholdersBasic", ("USD",)),
            ("ifrs-full", "ProfitLoss", ("USD", "EUR", "GBP", "JPY")),
            (
                "ifrs-full",
                "ProfitLossAttributableToOwnersOfParent",
                ("USD", "EUR", "GBP", "JPY"),
            ),
        ),
        as_of,
        preserve_history=True,
    )
    output: dict[str, Any] = {
        "as_of": as_of_value,
        "entity_name": str(document.get("entityName") or ""),
        "cik": str(document.get("cik") or ""),
        "gaps": [],
    }
    if shares_match is None:
        output["gaps"].append("shares_outstanding")
    else:
        rows, taxonomy, concept, unit = shares_match
        row = _latest_instant_fact(rows)
        output["shares_outstanding"] = {
            "value": float(row["val"]),
            "unit": unit,
            "taxonomy": taxonomy,
            "concept": concept,
            "end": row["end"],
            "filed": row["filed"],
            "form": row.get("form"),
            "accession": row.get("accn"),
        }
    if equity_match is None:
        output["gaps"].append("stockholders_equity")
    else:
        rows, taxonomy, concept, unit = equity_match
        row = _latest_instant_fact(rows)
        output["stockholders_equity"] = {
            "value": float(row["val"]),
            "unit": unit,
            "taxonomy": taxonomy,
            "concept": concept,
            "end": row["end"],
            "filed": row["filed"],
            "form": row.get("form"),
            "accession": row.get("accn"),
        }
    if income_match is None:
        output["gaps"].append("ttm_net_income")
    else:
        rows, taxonomy, concept, unit = income_match
        current = _ttm_income(rows, as_of)
        prior = _ttm_income(rows, as_of - timedelta(days=365))
        if current is None:
            output["gaps"].append("ttm_net_income")
        else:
            value, inputs, method = current
            item: dict[str, Any] = {
                "value": value,
                "unit": unit,
                "taxonomy": taxonomy,
                "concept": concept,
                "method": method,
                "inputs": [
                    {
                        key: row.get(key)
                        for key in ("start", "end", "filed", "form", "accn", "val")
                    }
                    for row in inputs
                ],
            }
            if prior is not None and prior[0] != 0:
                item["growth_pct"] = (value / prior[0] - 1.0) * 100.0
                item["prior_ttm_value"] = prior[0]
            else:
                output["gaps"].append("ttm_net_income_growth")
            output["ttm_net_income"] = item
    return output


class SecCompanyFactsAdapter:
    """Official point-in-time fundamentals for reconstructing US valuations."""

    def __init__(self, *, http_get=_sec_http_get) -> None:
        self.http_get = http_get
        self.manifest = SourceManifest(
            source_key=SEC_COMPANY_FACTS_SOURCE,
            domain_scope=RecordDomain.FUNDAMENTAL.value,
            authority_tier="official",
            provider_version="sec-companyfacts-2026-07",
            schema_version="sec-pit-valuation-inputs-v1",
            license_status="public_disclosure_internal_use",
            source_url="https://data.sec.gov/api/xbrl/companyfacts/",
            quality_flags=("filed_before_as_of", "official_fundamentals", "no_bar_valuation"),
        )

    async def fetch(self, request: FetchRequest) -> FetchedPayload:
        cik = str(request.parameters.get("cik") or "").strip()
        if not re.fullmatch(r"\d{1,10}", cik):
            raise ValueError("SEC companyfacts request requires numeric cik")
        date.fromisoformat(str(request.parameters["as_of"]))
        url = self.manifest.source_url + f"CIK{int(cik):010d}.json"
        body = await asyncio.to_thread(self.http_get, url)
        now = _utc_now()
        return FetchedPayload(body, url, now, now, "application/json", data_kind="real")

    def parse(
        self, request: FetchRequest, fetched: FetchedPayload, raw: RawCapture
    ) -> Iterable[RecordEnvelope]:
        document = json.loads(fetched.body.decode("utf-8"))
        inputs = sec_point_in_time_inputs(document, str(request.parameters["as_of"]))
        records = []
        for metric in ("shares_outstanding", "stockholders_equity", "ttm_net_income"):
            item = inputs.get(metric)
            if not isinstance(item, dict):
                continue
            input_rows = item.get("inputs") or ()
            filed_at = max(
                [str(row.get("filed") or "") for row in input_rows]
                + [str(item.get("filed") or "")]
            )
            report_period = max(
                [str(row.get("end") or "") for row in input_rows]
                + [str(item.get("end") or inputs["as_of"])]
            )
            records.append(
                RecordEnvelope.accepted(
                    domain=RecordDomain.FUNDAMENTAL,
                    entity_key=f"US:{request.entity_key}:pit:{inputs['as_of']}:{metric}",
                    payload={
                        "instrument_id": f"US:{request.entity_key}",
                        "report_period": report_period,
                        "announced_at": filed_at + "T00:00:00Z",
                        "metric": metric,
                        "value": item["value"],
                        "unit": item["unit"],
                        "as_of": inputs["as_of"],
                        "source_filed_at": filed_at,
                        "calculation": item,
                        "historical_reconstruction_eligible": True,
                    },
                    manifest=self.manifest,
                    raw=raw,
                )
            )
        if not records:
            raise ValueError("SEC companyfacts has no usable PIT valuation inputs")
        return tuple(records)


def derive_historical_valuation(
    price: float,
    inputs: dict[str, Any],
    *,
    usd_per_financial_currency: float = 1.0,
) -> dict[str, Any]:
    """Derive same-date valuation from price plus filed-before-date fundamentals."""

    gaps = list(inputs.get("gaps") or ())
    shares = inputs.get("shares_outstanding")
    income = inputs.get("ttm_net_income")
    equity = inputs.get("stockholders_equity")
    if not isinstance(shares, dict):
        return {"values": {}, "gaps": sorted(set(gaps + ["market_cap"]))}
    if str(shares.get("form") or "").upper().startswith(("20-F", "6-K")):
        return {
            "values": {},
            "gaps": sorted(set(gaps + ["adr_ratio_missing"])),
            "policy": "foreign-issuer ordinary shares are not multiplied by an ADR price",
        }
    market_cap_usd = float(price) * float(shares["value"])
    values: dict[str, float] = {
        "mcap": market_cap_usd / 100_000_000.0,
        "mcap_usd": market_cap_usd / 100_000_000.0,
    }
    if isinstance(income, dict):
        income_usd = float(income["value"]) * float(usd_per_financial_currency)
        if income_usd > 0:
            values["pe"] = market_cap_usd / income_usd
            growth = income.get("growth_pct")
            if isinstance(growth, (int, float)) and growth > 0:
                values["peg"] = values["pe"] / float(growth)
            else:
                gaps.append("peg_non_positive_or_missing_growth")
        else:
            gaps.append("pe_non_positive_income")
    else:
        gaps.append("pe_missing_income")
    if isinstance(equity, dict):
        equity_usd = float(equity["value"]) * float(usd_per_financial_currency)
        if equity_usd > 0:
            values["pb"] = market_cap_usd / equity_usd
        else:
            gaps.append("pb_non_positive_equity")
    else:
        gaps.append("pb_missing_equity")
    return {
        "values": values,
        "gaps": sorted(set(gaps)),
        "method": "price_x_sec_shares; ratios_use_filed_before_as_of_sec_facts",
        "definitions": {
            "mcap": "close_price_x_SEC_cover_page_shares",
            "pe": "market_cap_divided_by_SEC_GAAP_TTM_net_income",
            "pb": "market_cap_divided_by_SEC_stockholders_equity",
            "peg": "PE_divided_by_SEC_GAAP_TTM_net_income_growth_percent",
        },
    }


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
