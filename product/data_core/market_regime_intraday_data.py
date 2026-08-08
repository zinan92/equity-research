"""Replayable Yahoo 5-minute authority for Market Regime Live v1.

This module stops at normalized intraday evidence.  It does not score an
overlay, publish an API, schedule itself, make a forecast or place an order.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, time, timedelta, timezone
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import quote
from uuid import uuid4
from zoneinfo import ZoneInfo

from .market_regime_data import (
    HttpCapture,
    LicenseDecision,
    SourceCaptureError,
    http_get_capture,
    license_decision,
)


SCHEMA_VERSION = "market-regime-intraday-data-v1"
REGISTRY_VERSION = "market-regime-intraday-registry-v2"
BAR_SECONDS = 300
COMPLETION_GRACE_SECONDS = 30
LIVE_CANDIDATE_MAX_AGE_SECONDS = 15 * 60
DEFAULT_MAX_SILENCE_SECONDS = 96 * 60 * 60
MAX_TENCENT_QUOTE_SKEW_SECONDS = 120
SESSION_STATES = frozenset(
    {"pre", "open", "lunch_break", "post", "maintenance", "closed", "unknown"}
)
FRESHNESS_STATES = frozenset({"live_candidate", "delayed", "stale", "unavailable"})

YAHOO_QUERY1_BASE = "https://query1.finance.yahoo.com/v8/finance/chart/"
YAHOO_QUERY2_BASE = "https://query2.finance.yahoo.com/v8/finance/chart/"
TENCENT_QUOTE_BASE = "https://qt.gtimg.cn/q="
TENCENT_M5_BASE = "https://ifzq.gtimg.cn/appstock/app/kline/mkline?param="


class MarketRegimeIntradayDataError(RuntimeError):
    """Intraday data violated its frozen authority contract."""


@dataclass(frozen=True)
class IntradayInstrumentSpec:
    key: str
    display_name: str
    provider_symbol: str
    canonical_symbol: str
    asset_type: str
    currency: str
    exchange_timezone: str
    session_kind: str
    price_basis: str
    role: str
    proxy_for: str | None = None
    min_completed_bars: int = 2
    max_expected_silence_seconds: int = DEFAULT_MAX_SILENCE_SECONDS
    provider: str = "yahoo_chart"


YAHOO_INSTRUMENTS: tuple[IntradayInstrumentSpec, ...] = (
    IntradayInstrumentSpec("sp500_cash", "S&P 500 cash index", "^GSPC", "^GSPC", "price_index", "USD", "America/New_York", "us_cash", "provider_unadjusted_index_level", "cash_confirmation"),
    IntradayInstrumentSpec("nasdaq_cash", "Nasdaq Composite cash index", "^IXIC", "^IXIC", "price_index", "USD", "America/New_York", "us_cash", "provider_unadjusted_index_level", "cash_confirmation"),
    IntradayInstrumentSpec("sp500_futures_proxy", "E-mini S&P 500 futures proxy", "ES=F", "ES=F", "continuous_future", "USD", "America/New_York", "us_future", "provider_continuous_front_month_unadjusted", "proxy", "us_large_cap_risk_appetite"),
    IntradayInstrumentSpec("nasdaq100_futures_proxy", "E-mini Nasdaq-100 futures proxy", "NQ=F", "NQ=F", "continuous_future", "USD", "America/New_York", "us_future", "provider_continuous_front_month_unadjusted", "proxy", "us_growth_risk_appetite"),
    IntradayInstrumentSpec("wti", "WTI continuous future", "CL=F", "CL=F", "continuous_future", "USD", "America/New_York", "commodity_future", "provider_continuous_front_month_unadjusted", "market_signal"),
    IntradayInstrumentSpec("gold", "Gold continuous future", "GC=F", "GC=F", "continuous_future", "USD", "America/New_York", "commodity_future", "provider_continuous_front_month_unadjusted", "market_signal"),
    IntradayInstrumentSpec("silver", "Silver continuous future", "SI=F", "SI=F", "continuous_future", "USD", "America/New_York", "commodity_future", "provider_continuous_front_month_unadjusted", "market_signal"),
    IntradayInstrumentSpec("kospi", "KOSPI cash index", "^KS11", "^KS11", "price_index", "KRW", "Asia/Seoul", "korea_cash", "provider_unadjusted_index_level", "cash_confirmation"),
    IntradayInstrumentSpec("nikkei", "Nikkei 225 cash index", "^N225", "^N225", "price_index", "JPY", "Asia/Tokyo", "japan_cash", "provider_unadjusted_index_level", "cash_confirmation"),
    IntradayInstrumentSpec("vix", "VIX cash volatility index", "^VIX", "^VIX", "volatility_index", "USD", "America/Chicago", "vix_cash", "provider_unadjusted_index_level", "risk_evidence"),
    IntradayInstrumentSpec("us_dividend", "Schwab US Dividend Equity ETF", "SCHD", "SCHD", "etf", "USD", "America/New_York", "us_cash", "provider_unadjusted_trade_price", "style_evidence"),
)
TENCENT_INSTRUMENTS: tuple[IntradayInstrumentSpec, ...] = (
    IntradayInstrumentSpec("shanghai", "SSE Composite cash index", "sh000001", "000001.SH", "price_index", "CNY", "Asia/Shanghai", "a_share_cash", "provider_unadjusted_index_level", "cash_confirmation", provider="tencent_quote_m5"),
    IntradayInstrumentSpec("star50", "STAR 50 cash index", "sh000688", "000688.SH", "price_index", "CNY", "Asia/Shanghai", "a_share_cash", "provider_unadjusted_index_level", "cash_confirmation", provider="tencent_quote_m5"),
    IntradayInstrumentSpec("china_dividend", "SSE Dividend cash index", "sh000015", "000015.SH", "price_index", "CNY", "Asia/Shanghai", "a_share_cash", "provider_unadjusted_index_level", "style_evidence", provider="tencent_quote_m5"),
)
INTRADAY_INSTRUMENTS = (*YAHOO_INSTRUMENTS, *TENCENT_INSTRUMENTS)
INSTRUMENT_BY_KEY = {item.key: item for item in INTRADAY_INSTRUMENTS}
if len(INSTRUMENT_BY_KEY) != len(INTRADAY_INSTRUMENTS):  # pragma: no cover
    raise RuntimeError("intraday instrument keys must be unique")
if INSTRUMENT_BY_KEY["sp500_cash"].canonical_symbol == INSTRUMENT_BY_KEY["sp500_futures_proxy"].canonical_symbol:  # pragma: no cover
    raise RuntimeError("cash and futures identities must remain distinct")
if INSTRUMENT_BY_KEY["nasdaq_cash"].canonical_symbol == INSTRUMENT_BY_KEY["nasdaq100_futures_proxy"].canonical_symbol:  # pragma: no cover
    raise RuntimeError("Nasdaq cash and futures identities must remain distinct")


def registry_payload() -> dict[str, Any]:
    payload = {
        "schema_version": REGISTRY_VERSION,
        "providers": ["yahoo_chart", "tencent_quote_m5"],
        "interval": "5m",
        "range": "5d",
        "instruments": [asdict(item) for item in INTRADAY_INSTRUMENTS],
        "hard_invariants": [
            "^GSPC != ES=F",
            "^IXIC != NQ=F",
            "NQ=F is a Nasdaq-100 futures proxy, not Nasdaq Composite",
            "cross-identity price splicing is forbidden",
        ],
        "authority_tier": "supplementary_only",
        "publication_eligible": False,
    }
    payload["registry_sha256"] = sha256(_canonical(payload)).hexdigest()
    return payload


def _canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise MarketRegimeIntradayDataError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _finite(value: Any, *, field: str) -> float:
    if isinstance(value, bool):
        raise SourceCaptureError(f"{field} is not numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise SourceCaptureError(f"{field} is not numeric") from exc
    if not math.isfinite(number):
        raise SourceCaptureError(f"{field} is not finite")
    return number


def _bounded_excerpt(body: bytes, limit: int = 320) -> str | None:
    if not body:
        return None
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        text = body.decode("gb18030", errors="replace")
    return " ".join(text.replace("\x00", " ").split())[:limit]


def yahoo_urls(spec: IntradayInstrumentSpec) -> tuple[str, str]:
    symbol = quote(spec.provider_symbol, safe="")
    suffix = f"{symbol}?interval=5m&range=5d"
    return YAHOO_QUERY1_BASE + suffix, YAHOO_QUERY2_BASE + suffix


def tencent_quote_url(specs: Iterable[IntradayInstrumentSpec]) -> str:
    selected = list(specs)
    symbols = [item.provider_symbol for item in selected]
    if not symbols or any(item.provider != "tencent_quote_m5" for item in selected):
        raise MarketRegimeIntradayDataError("Tencent quote batch requires fixed Tencent instruments")
    return TENCENT_QUOTE_BASE + ",".join(symbols)


def tencent_m5_url(spec: IntradayInstrumentSpec) -> str:
    if spec.provider != "tencent_quote_m5":
        raise MarketRegimeIntradayDataError("Tencent m5 requires a fixed Tencent instrument")
    return f"{TENCENT_M5_BASE}{spec.provider_symbol},m5,,320"


def parse_tencent_quote_batch(
    capture: HttpCapture,
    specs: Iterable[IntradayInstrumentSpec],
) -> dict[str, dict[str, Any]]:
    expected = {item.provider_symbol: item for item in specs}
    if capture.status_code != 200:
        raise SourceCaptureError(f"Tencent quote HTTP status {capture.status_code}", capture=capture)
    if capture.content_type != "text/html":
        raise SourceCaptureError(
            f"Tencent quote content type {capture.content_type or 'missing'}", capture=capture
        )
    try:
        text = capture.body.decode("gb18030")
    except UnicodeDecodeError as exc:
        raise SourceCaptureError("Tencent quote is not valid GB18030", capture=capture) from exc
    parsed: dict[str, dict[str, Any]] = {}
    pattern = re.compile(r'^v_(sh\d{6})="(.*)";$')
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = pattern.fullmatch(line)
        if match is None:
            raise SourceCaptureError("Tencent quote line shape mismatch", capture=capture)
        symbol, raw_fields = match.groups()
        if symbol not in expected or symbol in parsed:
            raise SourceCaptureError("Tencent quote symbol identity mismatch", capture=capture)
        fields = raw_fields.split("~")
        if len(fields) <= 30 or fields[2] != symbol[2:]:
            raise SourceCaptureError("Tencent quote field identity mismatch", capture=capture)
        try:
            quote_at = datetime.strptime(fields[30], "%Y%m%d%H%M%S").replace(
                tzinfo=ZoneInfo("Asia/Shanghai")
            )
        except (ValueError, TypeError) as exc:
            raise SourceCaptureError("Tencent quote timestamp mismatch", capture=capture) from exc
        parsed[symbol] = {
            "provider_symbol": symbol,
            "name": fields[1],
            "code": fields[2],
            "price": _finite(fields[3], field=f"{symbol}.quote_price"),
            "previous_close": _finite(fields[4], field=f"{symbol}.previous_close"),
            "open": _finite(fields[5], field=f"{symbol}.quote_open"),
            "quote_at": quote_at,
        }
    if set(parsed) != set(expected):
        missing = sorted(set(expected) - set(parsed))
        raise SourceCaptureError(
            f"Tencent quote batch missing: {', '.join(missing)}", capture=capture
        )
    return parsed


def _parse_tencent_market_state(raw: str) -> tuple[datetime, str | None]:
    parts = str(raw).split("|")
    try:
        observed = datetime.strptime(parts[0], "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=ZoneInfo("Asia/Shanghai")
        )
    except (ValueError, IndexError) as exc:
        raise SourceCaptureError("Tencent market-state timestamp mismatch") from exc
    state = None
    for token in parts[1:]:
        fields = token.split("_", 2)
        if len(fields) >= 2 and fields[0] == "SH":
            state = fields[1].lower()
            break
    return observed, state


def classify_tencent_session(
    observed_at: datetime,
    *,
    quote_at: datetime,
    market_observed_at: datetime,
    market_state: str | None,
) -> str:
    current = observed_at.astimezone(ZoneInfo("Asia/Shanghai"))
    local_clock = current.timetz().replace(tzinfo=None)
    if current.weekday() >= 5:
        return "closed"
    current_date = current.date()
    if quote_at.date() < current_date:
        return "unknown" if market_state == "open" else "closed"
    if time(9, 0) <= local_clock < time(9, 30):
        return "pre"
    if time(9, 30) <= local_clock < time(11, 30) or time(13, 0) <= local_clock < time(15, 0):
        quote_age = abs((current - quote_at.astimezone(ZoneInfo("Asia/Shanghai"))).total_seconds())
        market_age = abs(
            (current - market_observed_at.astimezone(ZoneInfo("Asia/Shanghai"))).total_seconds()
        )
        return (
            "open"
            if market_state == "open"
            and quote_age <= LIVE_CANDIDATE_MAX_AGE_SECONDS
            and market_age <= LIVE_CANDIDATE_MAX_AGE_SECONDS
            else "unknown"
        )
    if time(11, 30) <= local_clock < time(13, 0):
        return "lunch_break" if market_state in {"close", "break", None} else "unknown"
    if time(15, 0) <= local_clock < time(18, 0):
        return "post"
    return "closed"


def _provider_periods(meta: Mapping[str, Any]) -> dict[str, tuple[datetime, datetime]]:
    current = meta.get("currentTradingPeriod")
    if not isinstance(current, Mapping):
        return {}
    result: dict[str, tuple[datetime, datetime]] = {}
    for name in ("pre", "regular", "post"):
        value = current.get(name)
        if not isinstance(value, Mapping):
            continue
        try:
            start = datetime.fromtimestamp(int(value["start"]), tz=timezone.utc)
            end = datetime.fromtimestamp(int(value["end"]), tz=timezone.utc)
        except (KeyError, TypeError, ValueError, OSError):
            continue
        if end > start:
            result[name] = (start, end)
    return result


def classify_yahoo_session(
    spec: IntradayInstrumentSpec,
    observed_at: datetime,
    meta: Mapping[str, Any],
) -> str:
    """Classify one asset; provider periods are required to assert open."""

    current = observed_at.astimezone(timezone.utc)
    local = current.astimezone(ZoneInfo(spec.exchange_timezone))
    weekday = local.weekday()
    local_clock = local.timetz().replace(tzinfo=None)

    if spec.session_kind in {"us_future", "commodity_future"}:
        if weekday == 5 or (weekday == 6 and local_clock < time(18, 0)):
            return "closed"
        if weekday == 4 and local_clock >= time(17, 0):
            return "closed"
        if time(17, 0) <= local_clock < time(18, 0):
            return "maintenance"
    elif weekday >= 5:
        return "closed"

    if spec.session_kind == "japan_cash" and time(11, 30) <= local_clock < time(12, 30):
        return "lunch_break"

    periods = _provider_periods(meta)
    for name, state in (("pre", "pre"), ("regular", "open"), ("post", "post")):
        period = periods.get(name)
        if period and period[0] <= current < period[1]:
            return state
    if periods:
        return "closed"
    return "unknown"


def _parse_yahoo(capture: HttpCapture) -> tuple[Mapping[str, Any], list[int], Mapping[str, list[Any]]]:
    if capture.status_code != 200:
        raise SourceCaptureError(f"Yahoo HTTP status {capture.status_code}", capture=capture)
    if capture.content_type != "application/json":
        raise SourceCaptureError(f"Yahoo content type {capture.content_type or 'missing'}", capture=capture)
    try:
        payload = json.loads(capture.body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SourceCaptureError("Yahoo response is not valid JSON", capture=capture) from exc
    try:
        chart = payload["chart"]
        if chart.get("error") is not None:
            raise SourceCaptureError("Yahoo chart returned an error", capture=capture)
        result = chart["result"]
        if not isinstance(result, list) or len(result) != 1:
            raise SourceCaptureError("Yahoo chart result cardinality mismatch", capture=capture)
        row = result[0]
        meta = row["meta"]
        timestamps = row["timestamp"]
        quotes = row["indicators"]["quote"]
        if not isinstance(meta, Mapping) or not isinstance(timestamps, list):
            raise TypeError
        if not isinstance(quotes, list) or len(quotes) != 1 or not isinstance(quotes[0], Mapping):
            raise TypeError
    except (KeyError, TypeError) as exc:
        raise SourceCaptureError("Yahoo chart shape mismatch", capture=capture) from exc
    return meta, timestamps, quotes[0]


def normalize_yahoo_capture(
    spec: IntradayInstrumentSpec,
    capture: HttpCapture,
    *,
    observed_at: datetime,
    received_at: datetime,
) -> dict[str, Any]:
    """Normalize one fixed Yahoo identity into completed 5-minute bars."""

    observed = observed_at.astimezone(timezone.utc)
    received = received_at.astimezone(timezone.utc)
    if received > observed:
        raise MarketRegimeIntradayDataError("observed_at cannot precede received_at")
    meta, timestamps, quote_rows = _parse_yahoo(capture)
    if meta.get("symbol") != spec.provider_symbol:
        raise SourceCaptureError("Yahoo symbol identity mismatch", capture=capture)
    if meta.get("currency") != spec.currency:
        raise SourceCaptureError("Yahoo currency identity mismatch", capture=capture)
    if meta.get("exchangeTimezoneName") != spec.exchange_timezone:
        raise SourceCaptureError("Yahoo timezone identity mismatch", capture=capture)
    fields = {name: quote_rows.get(name) for name in ("open", "high", "low", "close")}
    if any(not isinstance(values, list) or len(values) != len(timestamps) for values in fields.values()):
        raise SourceCaptureError("Yahoo OHLC array length mismatch", capture=capture)
    volumes = quote_rows.get("volume")
    if volumes is not None and (not isinstance(volumes, list) or len(volumes) != len(timestamps)):
        raise SourceCaptureError("Yahoo volume array length mismatch", capture=capture)

    bars: list[dict[str, Any]] = []
    dropped_all_null: list[str] = []
    dropped_internal_all_null: list[str] = []
    dropped_trailing_all_null: list[str] = []
    dropped_unfinished: list[str] = []
    previous_timestamp: int | None = None
    for index, raw_timestamp in enumerate(timestamps):
        if isinstance(raw_timestamp, bool):
            raise SourceCaptureError("Yahoo timestamp is not an integer", capture=capture)
        try:
            timestamp = int(raw_timestamp)
        except (TypeError, ValueError) as exc:
            raise SourceCaptureError("Yahoo timestamp is not an integer", capture=capture) from exc
        if previous_timestamp is not None and timestamp <= previous_timestamp:
            raise SourceCaptureError("Yahoo timestamps are duplicate or unordered", capture=capture)
        previous_timestamp = timestamp
        start = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        end = start + timedelta(seconds=BAR_SECONDS)
        raw_values = [fields[name][index] for name in ("open", "high", "low", "close")]
        if all(value is None for value in raw_values):
            if volumes is not None and volumes[index] not in (None, 0, 0.0):
                raise SourceCaptureError("Yahoo all-null OHLC has non-zero volume", capture=capture)
            instant = _iso(start)
            dropped_all_null.append(instant)
            later_has_prices = any(
                not all(fields[name][later] is None for name in ("open", "high", "low", "close"))
                for later in range(index + 1, len(timestamps))
            )
            if later_has_prices:
                dropped_internal_all_null.append(instant)
            else:
                dropped_trailing_all_null.append(instant)
            continue
        if any(value is None for value in raw_values):
            raise SourceCaptureError("Yahoo bar is partially null", capture=capture)
        if start > observed:
            raise SourceCaptureError("Yahoo bar starts in the future", capture=capture)
        if end + timedelta(seconds=COMPLETION_GRACE_SECONDS) > observed:
            dropped_unfinished.append(_iso(start))
            continue
        open_price, high, low, close = [
            _finite(value, field=f"bar[{index}].{name}")
            for name, value in zip(("open", "high", "low", "close"), raw_values)
        ]
        if low > min(open_price, close, high) or high < max(open_price, close, low):
            raise SourceCaptureError("Yahoo OHLC containment failed", capture=capture)
        volume = None
        if volumes is not None and volumes[index] is not None:
            volume = _finite(volumes[index], field=f"bar[{index}].volume")
            if volume < 0:
                raise SourceCaptureError("Yahoo volume is negative", capture=capture)
        bars.append(
            {
                "provider_timestamp": timestamp,
                "started_at": _iso(start),
                "ended_at": _iso(end),
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
            }
        )
    if len(bars) < spec.min_completed_bars:
        raise SourceCaptureError(
            f"Yahoo completed bar count {len(bars)} below {spec.min_completed_bars}",
            capture=capture,
        )
    latest_start = datetime.fromtimestamp(bars[-1]["provider_timestamp"], tz=timezone.utc)
    age_seconds = max(0, int((observed - latest_start).total_seconds()))
    session_state = classify_yahoo_session(spec, observed, meta)
    if session_state == "open" and age_seconds <= LIVE_CANDIDATE_MAX_AGE_SECONDS:
        freshness = "live_candidate"
    elif age_seconds <= spec.max_expected_silence_seconds:
        freshness = "delayed"
    else:
        freshness = "stale"
    return {
        "schema_version": SCHEMA_VERSION,
        "instrument": asdict(spec),
        "interval": "5m",
        "timestamp_semantics": "interval_start",
        "bars": bars,
        "bar_count": len(bars),
        "provider_timestamp": _iso(latest_start),
        "last_completed_bar_end_at": bars[-1]["ended_at"],
        "last_completed_session": latest_start.astimezone(ZoneInfo(spec.exchange_timezone)).date().isoformat(),
        "observed_at": _iso(observed),
        "received_at": _iso(received),
        "age_seconds": age_seconds,
        "current_age_seconds": age_seconds,
        "session_state": session_state,
        "freshness": freshness,
        "dropped_all_null_bars": dropped_all_null,
        "dropped_internal_all_null_bars": dropped_internal_all_null,
        "dropped_trailing_all_null_bars": dropped_trailing_all_null,
        "dropped_unfinished_bars": dropped_unfinished,
        "provider_session_periods": {
            name: {"start": _iso(start), "end": _iso(end)}
            for name, (start, end) in _provider_periods(meta).items()
        },
        "publication_eligible": False,
        "action_eligible": False,
    }


def normalize_tencent_captures(
    spec: IntradayInstrumentSpec,
    quote_row: Mapping[str, Any],
    m5_capture: HttpCapture,
    *,
    observed_at: datetime,
    received_at: datetime,
) -> dict[str, Any]:
    if spec.provider != "tencent_quote_m5":
        raise MarketRegimeIntradayDataError("Tencent normalizer received a non-Tencent identity")
    observed = observed_at.astimezone(timezone.utc)
    received = received_at.astimezone(timezone.utc)
    if received > observed:
        raise MarketRegimeIntradayDataError("observed_at cannot precede received_at")
    if quote_row.get("provider_symbol") != spec.provider_symbol or quote_row.get("code") != spec.provider_symbol[2:]:
        raise SourceCaptureError("Tencent quote/m5 identity mismatch", capture=m5_capture)
    if m5_capture.status_code != 200:
        raise SourceCaptureError(
            f"Tencent m5 HTTP status {m5_capture.status_code}", capture=m5_capture
        )
    if m5_capture.content_type not in {"text/html", "application/json"}:
        raise SourceCaptureError(
            f"Tencent m5 content type {m5_capture.content_type or 'missing'}",
            capture=m5_capture,
        )
    if not m5_capture.body.lstrip().startswith(b"{"):
        raise SourceCaptureError("Tencent m5 body is not JSON-shaped", capture=m5_capture)
    try:
        payload = json.loads(m5_capture.body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SourceCaptureError("Tencent m5 response is not valid JSON", capture=m5_capture) from exc
    try:
        if payload.get("code") != 0:
            raise SourceCaptureError("Tencent m5 returned a provider error", capture=m5_capture)
        data = payload["data"]
        if not isinstance(data, Mapping) or set(data) != {spec.provider_symbol}:
            raise SourceCaptureError("Tencent m5 symbol identity mismatch", capture=m5_capture)
        instrument = data[spec.provider_symbol]
        rows = instrument["m5"]
        quote_payload = instrument["qt"]
        embedded_quote = quote_payload[spec.provider_symbol]
        market_values = quote_payload["market"]
        if not isinstance(rows, list) or not isinstance(embedded_quote, list):
            raise TypeError
        if not isinstance(market_values, list) or len(market_values) != 1:
            raise TypeError
    except (KeyError, TypeError) as exc:
        raise SourceCaptureError("Tencent m5 response shape mismatch", capture=m5_capture) from exc
    if len(embedded_quote) <= 30 or embedded_quote[2] != spec.provider_symbol[2:]:
        raise SourceCaptureError("Tencent embedded quote identity mismatch", capture=m5_capture)
    try:
        embedded_quote_at = datetime.strptime(embedded_quote[30], "%Y%m%d%H%M%S").replace(
            tzinfo=ZoneInfo("Asia/Shanghai")
        )
    except (ValueError, TypeError) as exc:
        raise SourceCaptureError("Tencent embedded quote timestamp mismatch", capture=m5_capture) from exc
    quote_at = quote_row.get("quote_at")
    if not isinstance(quote_at, datetime) or quote_at.tzinfo is None:
        raise SourceCaptureError("Tencent batch quote timestamp mismatch", capture=m5_capture)
    if quote_at.astimezone(timezone.utc) > observed + timedelta(seconds=60):
        raise SourceCaptureError("Tencent batch quote timestamp is in the future", capture=m5_capture)
    if embedded_quote_at.astimezone(timezone.utc) > observed + timedelta(seconds=60):
        raise SourceCaptureError("Tencent embedded quote timestamp is in the future", capture=m5_capture)
    if abs((embedded_quote_at - quote_at).total_seconds()) > MAX_TENCENT_QUOTE_SKEW_SECONDS:
        raise SourceCaptureError("Tencent batch/m5 quote timestamp conflict", capture=m5_capture)
    try:
        market_observed_at, market_state = _parse_tencent_market_state(str(market_values[0]))
    except SourceCaptureError as exc:
        raise SourceCaptureError(str(exc), capture=m5_capture) from exc
    if market_observed_at.astimezone(timezone.utc) > observed + timedelta(seconds=60):
        raise SourceCaptureError("Tencent market-state timestamp is in the future", capture=m5_capture)

    bars: list[dict[str, Any]] = []
    dropped_unfinished: list[str] = []
    previous: datetime | None = None
    zone = ZoneInfo("Asia/Shanghai")
    for index, row in enumerate(rows):
        if not isinstance(row, list) or len(row) < 6:
            raise SourceCaptureError("Tencent m5 row shape mismatch", capture=m5_capture)
        try:
            ended = datetime.strptime(str(row[0]), "%Y%m%d%H%M").replace(tzinfo=zone)
        except ValueError as exc:
            raise SourceCaptureError("Tencent m5 timestamp mismatch", capture=m5_capture) from exc
        ended_utc = ended.astimezone(timezone.utc)
        if previous is not None and ended_utc <= previous:
            raise SourceCaptureError("Tencent m5 timestamps are duplicate or unordered", capture=m5_capture)
        previous = ended_utc
        if ended_utc > observed:
            raise SourceCaptureError("Tencent m5 bar ends in the future", capture=m5_capture)
        if ended_utc + timedelta(seconds=COMPLETION_GRACE_SECONDS) > observed:
            dropped_unfinished.append(_iso(ended_utc))
            continue
        open_price = _finite(row[1], field=f"bar[{index}].open")
        close = _finite(row[2], field=f"bar[{index}].close")
        high = _finite(row[3], field=f"bar[{index}].high")
        low = _finite(row[4], field=f"bar[{index}].low")
        volume = _finite(row[5], field=f"bar[{index}].volume")
        if low > min(open_price, close, high) or high < max(open_price, close, low):
            raise SourceCaptureError("Tencent m5 OHLC containment failed", capture=m5_capture)
        if volume < 0:
            raise SourceCaptureError("Tencent m5 volume is negative", capture=m5_capture)
        bars.append(
            {
                "provider_timestamp": int(ended_utc.timestamp()),
                "started_at": _iso(ended_utc - timedelta(seconds=BAR_SECONDS)),
                "ended_at": _iso(ended_utc),
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
            }
        )
    if len(bars) < spec.min_completed_bars:
        raise SourceCaptureError(
            f"Tencent completed bar count {len(bars)} below {spec.min_completed_bars}",
            capture=m5_capture,
        )
    latest_end = datetime.fromtimestamp(bars[-1]["provider_timestamp"], tz=timezone.utc)
    age_seconds = max(0, int((observed - latest_end).total_seconds()))
    session_state = classify_tencent_session(
        observed,
        quote_at=quote_at,
        market_observed_at=market_observed_at,
        market_state=market_state,
    )
    if session_state == "open" and age_seconds <= LIVE_CANDIDATE_MAX_AGE_SECONDS:
        freshness = "live_candidate"
    elif age_seconds <= spec.max_expected_silence_seconds:
        freshness = "delayed"
    else:
        freshness = "stale"
    return {
        "schema_version": SCHEMA_VERSION,
        "instrument": asdict(spec),
        "interval": "5m",
        "timestamp_semantics": "interval_end",
        "bars": bars,
        "bar_count": len(bars),
        "provider_timestamp": _iso(latest_end),
        "last_completed_bar_end_at": _iso(latest_end),
        "last_completed_session": latest_end.astimezone(zone).date().isoformat(),
        "observed_at": _iso(observed),
        "received_at": _iso(received),
        "age_seconds": age_seconds,
        "current_age_seconds": age_seconds,
        "session_state": session_state,
        "freshness": freshness,
        "quote_at": _iso(quote_at),
        "embedded_quote_at": _iso(embedded_quote_at),
        "provider_market_observed_at": _iso(market_observed_at),
        "provider_market_state": market_state,
        "dropped_all_null_bars": [],
        "dropped_internal_all_null_bars": [],
        "dropped_trailing_all_null_bars": [],
        "dropped_unfinished_bars": dropped_unfinished,
        "provider_session_periods": {},
        "source_quality_flags": ["provider_declares_text_html_for_json"]
        if m5_capture.content_type == "text/html"
        else [],
        "publication_eligible": False,
        "action_eligible": False,
    }


def _write_exclusive(path: Path, body: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(body)
        handle.flush()
        os.fsync(handle.fileno())
    return sha256(body).hexdigest()


def _write_json_exclusive(path: Path, payload: Mapping[str, Any]) -> str:
    return _write_exclusive(path, _canonical(payload))


def _write_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    encoded = _canonical(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as exc:
        raise MarketRegimeIntradayDataError(f"invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise MarketRegimeIntradayDataError(f"JSON object required: {path}")
    return value


def _read_bound_artifact(root: Path, reference: Mapping[str, Any]) -> dict[str, Any]:
    relative = str(reference.get("path") or "")
    expected_hash = str(reference.get("sha256") or "")
    target = (root / relative).resolve()
    if root not in target.parents or not relative.startswith("intraday/"):
        raise MarketRegimeIntradayDataError("intraday artifact path escapes runtime root")
    try:
        encoded = target.read_bytes()
    except FileNotFoundError as exc:
        raise MarketRegimeIntradayDataError("intraday artifact is missing") from exc
    if sha256(encoded).hexdigest() != expected_hash:
        raise MarketRegimeIntradayDataError("intraday artifact hash mismatch")
    try:
        payload = json.loads(encoded)
    except json.JSONDecodeError as exc:
        raise MarketRegimeIntradayDataError("intraday artifact is not JSON") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
        raise MarketRegimeIntradayDataError("intraday artifact schema mismatch")
    return payload


def _run_id(now: datetime) -> str:
    return f"market-regime-intraday-{now:%Y%m%dT%H%M%SZ}-{uuid4().hex[:8]}"


class MarketRegimeIntradayDataStore:
    """Serial intraday collector with immutable raw/normalized evidence and last-good."""

    def __init__(
        self,
        root: Path | str,
        *,
        http_get: Callable[[str], HttpCapture] = http_get_capture,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.root = Path(root).expanduser().resolve()
        self.http_get = http_get
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._live_transport = http_get is http_get_capture

    def _source_receipt(
        self,
        capture: HttpCapture,
        *,
        raw_relative: str | None,
        received_at: datetime,
        endpoint: str,
        accepted: bool,
        reason: str | None,
    ) -> dict[str, Any]:
        return {
            **capture.receipt(raw_path=raw_relative),
            "endpoint": endpoint,
            "received_at": _iso(received_at),
            "accepted": accepted,
            "reason": reason,
            "bounded_raw_excerpt": _bounded_excerpt(capture.body) if not accepted else None,
        }

    def refresh(
        self,
        *,
        instrument_keys: Iterable[str] | None = None,
        now: datetime | None = None,
        run_id: str | None = None,
        deployment_mode: str | None = None,
        license_status: str | None = None,
        license_reference: str | None = None,
    ) -> dict[str, Any]:
        if (now is not None or run_id is not None) and self._live_transport:
            raise MarketRegimeIntradayDataError(
                "clock/run overrides require an injected fixture transport"
            )
        current = (now or self.clock()).astimezone(timezone.utc)
        identity = run_id or _run_id(current)
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", identity) is None:
            raise MarketRegimeIntradayDataError("run_id contains unsafe characters")
        decision: LicenseDecision = license_decision(
            deployment_mode=deployment_mode,
            license_status=license_status,
            license_reference=license_reference,
            private_preview=False,
        )
        selected = list(instrument_keys or [item.key for item in INTRADAY_INSTRUMENTS])
        if not selected or len(selected) != len(set(selected)):
            raise MarketRegimeIntradayDataError("instrument_keys must be non-empty and unique")
        unknown = [key for key in selected if key not in INSTRUMENT_BY_KEY]
        if unknown:
            raise MarketRegimeIntradayDataError(
                f"unknown intraday instruments: {', '.join(unknown)}"
            )
        tencent_specs = [
            INSTRUMENT_BY_KEY[key]
            for key in selected
            if INSTRUMENT_BY_KEY[key].provider == "tencent_quote_m5"
        ]
        tencent_quote_capture: HttpCapture | None = None
        tencent_quote_received_at: datetime | None = None
        tencent_quote_raw_relative: str | None = None
        tencent_quote_rows: dict[str, dict[str, Any]] = {}
        tencent_quote_error: str | None = None
        results: list[dict[str, Any]] = []
        snapshot_items: list[dict[str, Any]] = []
        pending_pointers: list[tuple[str, dict[str, Any]]] = []
        for key in selected:
            spec = INSTRUMENT_BY_KEY[key]
            attempts: list[dict[str, Any]] = []
            accepted_artifact: dict[str, Any] | None = None
            selected_endpoint: str | None = None
            if spec.provider == "yahoo_chart":
                for endpoint, url in zip(("query1", "query2"), yahoo_urls(spec)):
                    capture = self.http_get(url)
                    received_at = current if now is not None else self.clock().astimezone(timezone.utc)
                    suffix = ".json" if capture.content_type == "application/json" else ".bin"
                    raw_relative = None
                    if capture.body:
                        raw_relative = f"intraday/raw/{identity}/{key}-{endpoint}{suffix}"
                        _write_exclusive(self.root / raw_relative, capture.body)
                    try:
                        normalized = normalize_yahoo_capture(
                            spec,
                            capture,
                            observed_at=current if now is not None else received_at,
                            received_at=received_at,
                        )
                    except (SourceCaptureError, MarketRegimeIntradayDataError) as exc:
                        attempts.append(
                            self._source_receipt(
                                capture,
                                raw_relative=raw_relative,
                                received_at=received_at,
                                endpoint=endpoint,
                                accepted=False,
                                reason=str(exc),
                            )
                        )
                        continue
                    attempts.append(
                        self._source_receipt(
                            capture,
                            raw_relative=raw_relative,
                            received_at=received_at,
                            endpoint=endpoint,
                            accepted=True,
                            reason=None,
                        )
                    )
                    selected_endpoint = endpoint
                    accepted_artifact = {
                        **normalized,
                        "run_id": identity,
                        "provider": "yahoo_chart",
                        "selected_endpoint": endpoint,
                        "source_attempts": attempts,
                        "license": decision.as_json(),
                        "data_kind": "real" if self._live_transport else "fixture",
                        "refresh_status": "accepted",
                    }
                    break
            elif spec.provider == "tencent_quote_m5":
                if tencent_quote_capture is None:
                    quote_url = tencent_quote_url(tencent_specs)
                    tencent_quote_capture = self.http_get(quote_url)
                    tencent_quote_received_at = (
                        current if now is not None else self.clock().astimezone(timezone.utc)
                    )
                    if tencent_quote_capture.body:
                        tencent_quote_raw_relative = (
                            f"intraday/raw/{identity}/tencent-quote-batch.bin"
                        )
                        _write_exclusive(
                            self.root / tencent_quote_raw_relative,
                            tencent_quote_capture.body,
                        )
                    try:
                        tencent_quote_rows = parse_tencent_quote_batch(
                            tencent_quote_capture, tencent_specs
                        )
                    except SourceCaptureError as exc:
                        tencent_quote_error = str(exc)
                if tencent_quote_received_at is None:
                    raise MarketRegimeIntradayDataError("Tencent quote batch was not timestamped")
                quote_ok = tencent_quote_error is None
                attempts.append(
                    self._source_receipt(
                        tencent_quote_capture,
                        raw_relative=tencent_quote_raw_relative,
                        received_at=tencent_quote_received_at,
                        endpoint="tencent_quote_batch",
                        accepted=quote_ok,
                        reason=tencent_quote_error,
                    )
                )
                if quote_ok:
                    m5_url = tencent_m5_url(spec)
                    m5_capture = self.http_get(m5_url)
                    received_at = current if now is not None else self.clock().astimezone(timezone.utc)
                    suffix = ".json" if m5_capture.content_type == "application/json" else ".bin"
                    raw_relative = None
                    if m5_capture.body:
                        raw_relative = f"intraday/raw/{identity}/{key}-tencent-m5{suffix}"
                        _write_exclusive(self.root / raw_relative, m5_capture.body)
                    try:
                        normalized = normalize_tencent_captures(
                            spec,
                            tencent_quote_rows[spec.provider_symbol],
                            m5_capture,
                            observed_at=current if now is not None else received_at,
                            received_at=received_at,
                        )
                    except (SourceCaptureError, MarketRegimeIntradayDataError) as exc:
                        attempts.append(
                            self._source_receipt(
                                m5_capture,
                                raw_relative=raw_relative,
                                received_at=received_at,
                                endpoint="tencent_m5",
                                accepted=False,
                                reason=str(exc),
                            )
                        )
                    else:
                        attempts.append(
                            self._source_receipt(
                                m5_capture,
                                raw_relative=raw_relative,
                                received_at=received_at,
                                endpoint="tencent_m5",
                                accepted=True,
                                reason=None,
                            )
                        )
                        selected_endpoint = "tencent_m5"
                        accepted_artifact = {
                            **normalized,
                            "run_id": identity,
                            "provider": "tencent_quote_m5",
                            "selected_endpoint": selected_endpoint,
                            "source_attempts": attempts,
                            "license": decision.as_json(),
                            "data_kind": "real" if self._live_transport else "fixture",
                            "refresh_status": "accepted",
                        }
            else:  # pragma: no cover - registry invariant
                raise MarketRegimeIntradayDataError(
                    f"unsupported intraday provider: {spec.provider}"
                )
            if accepted_artifact is not None:
                relative = f"intraday/normalized/{identity}/{key}.json"
                artifact_hash = _write_json_exclusive(self.root / relative, accepted_artifact)
                reference = {
                    "path": relative,
                    "sha256": artifact_hash,
                    "schema_version": SCHEMA_VERSION,
                }
                pointer = {
                    "schema_version": SCHEMA_VERSION,
                    "instrument_key": key,
                    "run_id": identity,
                    "normalized_artifact": reference,
                }
                pending_pointers.append((key, pointer))
                item = {**accepted_artifact, "normalized_artifact": reference}
                snapshot_items.append(item)
                results.append(
                    {
                        "key": key,
                        "status": "accepted",
                        "selected_endpoint": selected_endpoint,
                        "freshness": item["freshness"],
                        "session_state": item["session_state"],
                        "normalized_artifact": reference,
                        "source_attempts": attempts,
                    }
                )
                continue
            failure = {
                "key": key,
                "status": "rejected",
                "reason": attempts[-1]["reason"] if attempts else "no source attempt",
                "source_attempts": attempts,
            }
            results.append(failure)
            latest_pointer = _read_json(
                self.root / "intraday" / "instruments" / key / "latest-good.json"
            )
            if latest_pointer is None:
                snapshot_items.append(
                    {
                        "schema_version": SCHEMA_VERSION,
                        "instrument": asdict(spec),
                        "bars": [],
                        "bar_count": 0,
                        "provider_timestamp": None,
                        "observed_at": _iso(current),
                        "received_at": None,
                        "age_seconds": None,
                        "current_age_seconds": None,
                        "session_state": "unknown",
                        "freshness": "unavailable",
                        "refresh_status": "rejected",
                        "refresh_failure": failure,
                        "publication_eligible": False,
                        "action_eligible": False,
                    }
                )
                continue
            reference = latest_pointer.get("normalized_artifact") or {}
            latest = _read_bound_artifact(self.root, reference)
            if (
                latest_pointer.get("instrument_key") != key
                or (latest.get("instrument") or {}).get("key") != key
            ):
                raise MarketRegimeIntradayDataError("intraday latest-good identity mismatch")
            provider_time = _instant(str(latest["provider_timestamp"]))
            current_age = max(0, int((current - provider_time).total_seconds()))
            fallback_freshness = (
                "delayed"
                if current_age <= spec.max_expected_silence_seconds
                else "stale"
            )
            snapshot_items.append(
                {
                    **latest,
                    "normalized_artifact": reference,
                    "last_good_original_freshness": latest.get("freshness"),
                    "current_age_seconds": current_age,
                    "freshness": fallback_freshness,
                    "refresh_status": "rejected",
                    "refresh_failure": failure,
                }
            )

        accepted_count = sum(item["status"] == "accepted" for item in results)
        usable_count = sum(bool(item.get("bars")) for item in snapshot_items)
        quality = "complete" if accepted_count == len(selected) else "partial" if usable_count else "unavailable"
        completed_at = current if now is not None else self.clock().astimezone(timezone.utc)
        snapshot_core: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "run_id": identity,
            "generated_at": _iso(completed_at),
            "quality": quality,
            "instrument_count": len(selected),
            "accepted_count": accepted_count,
            "rejected_count": len(selected) - accepted_count,
            "registry_sha256": registry_payload()["registry_sha256"],
            "license": decision.as_json(),
            "data_kind": "real" if self._live_transport else "fixture",
            "publication_eligible": False,
            "action_eligible": False,
            "instruments": snapshot_items,
        }
        snapshot_hash = sha256(_canonical(snapshot_core)).hexdigest()
        snapshot = {**snapshot_core, "snapshot_id": f"market-regime-intraday-snapshot:{snapshot_hash}"}
        snapshot_relative = f"intraday/snapshots/{snapshot_hash}.json"
        snapshot_file_hash = _write_json_exclusive(self.root / snapshot_relative, snapshot)
        receipt = {
            "schema_version": SCHEMA_VERSION,
            "run_id": identity,
            "generated_at": _iso(completed_at),
            "results": results,
            "snapshot": {
                "path": snapshot_relative,
                "sha256": snapshot_file_hash,
                "snapshot_id": snapshot["snapshot_id"],
            },
            "quality": quality,
        }
        _write_json_exclusive(self.root / "intraday" / "runs" / f"{identity}.json", receipt)
        for key, pointer in pending_pointers:
            _write_atomic(
                self.root / "intraday" / "instruments" / key / "latest-good.json",
                pointer,
            )
        _write_atomic(
            self.root / "intraday" / "latest.json",
            {
                "schema_version": SCHEMA_VERSION,
                "run_id": identity,
                "snapshot_id": snapshot["snapshot_id"],
                "snapshot": {"path": snapshot_relative, "sha256": snapshot_file_hash},
            },
        )
        return snapshot

    def latest(self) -> dict[str, Any]:
        pointer = _read_json(self.root / "intraday" / "latest.json")
        if pointer is None or pointer.get("schema_version") != SCHEMA_VERSION:
            raise MarketRegimeIntradayDataError("intraday latest snapshot is unavailable")
        snapshot = _read_bound_artifact(self.root, pointer.get("snapshot") or {})
        core = {key: value for key, value in snapshot.items() if key != "snapshot_id"}
        identity = sha256(_canonical(core)).hexdigest()
        if (
            snapshot.get("snapshot_id") != f"market-regime-intraday-snapshot:{identity}"
            or pointer.get("snapshot_id") != snapshot.get("snapshot_id")
            or pointer.get("run_id") != snapshot.get("run_id")
        ):
            raise MarketRegimeIntradayDataError("intraday snapshot identity mismatch")
        return snapshot
