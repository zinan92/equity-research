"""Evidence-preserving daily OHLC authority for the market-regime product.

This module intentionally stops at frozen market data.  It does not score a
regime, write investment prose, or publish a recommendation.  The two
unauthenticated provider endpoints are allowed only for a local evaluation
prototype unless an operator supplies an explicit commercial-rights receipt.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Any, Iterable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import uuid4
from zoneinfo import ZoneInfo


SCHEMA_VERSION = "market-regime-data-v1"
LOCAL_EVALUATION = "local_evaluation_only"
COMMERCIAL_RIGHTS_APPROVED = "commercial_rights_approved"
DISABLED = "disabled"
LICENSE_STATUSES = frozenset({LOCAL_EVALUATION, COMMERCIAL_RIGHTS_APPROVED, DISABLED})
DEPLOYMENT_MODES = frozenset({"local_prototype", "private_beta", "public"})

YAHOO_CHART_URL = "https://query2.finance.yahoo.com/v8/finance/chart/"
TENCENT_KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
YAHOO_TERMS_URL = "https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html"
YAHOO_DEVELOPER_GUIDELINES_URL = "https://legal.yahoo.com/us/en/yahoo/guidelines/ydn/index.html"
TENCENT_LEGAL_URL = "https://www.tencent.com/legal-statement/"

SAFE_RESPONSE_HEADERS = frozenset(
    {
        "cache-control",
        "content-length",
        "content-type",
        "date",
        "etag",
        "expires",
        "last-modified",
        "server",
        "via",
        "x-cache",
        "x-request-id",
        "x-yahoo-request-id",
    }
)


class MarketRegimeDataError(RuntimeError):
    """The market-regime data contract failed closed."""


class LicenseGateError(MarketRegimeDataError):
    """The configured deployment is not permitted by the license gate."""


class SourceCaptureError(MarketRegimeDataError):
    """A provider response or normalized bar set violated the contract."""

    def __init__(self, reason: str, *, capture: "HttpCapture | None" = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.capture = capture


@dataclass(frozen=True)
class InstrumentSpec:
    key: str
    display_name: str
    category: str
    role: str
    provider: str
    provider_symbol: str
    canonical_symbol: str
    asset_type: str
    currency: str
    unit: str
    exchange_timezone: str
    session_close: str
    price_basis: str
    min_history: int = 120
    preferred_history: int = 200
    max_provider_silence_hours: int = 240

    @property
    def is_primary_chart(self) -> bool:
        return self.role == "primary_chart"


INSTRUMENTS: tuple[InstrumentSpec, ...] = (
    InstrumentSpec("sp500", "S&P 500", "us_equity", "primary_chart", "yahoo_chart", "^GSPC", "^GSPC", "price_index", "USD", "index points", "America/New_York", "16:00", "provider_unadjusted_index_level"),
    InstrumentSpec("nasdaq", "Nasdaq Composite", "us_equity", "primary_chart", "yahoo_chart", "^IXIC", "^IXIC", "price_index", "USD", "index points", "America/New_York", "16:00", "provider_unadjusted_index_level"),
    InstrumentSpec("shanghai", "上证指数", "a_share", "primary_chart", "tencent_kline", "sh000001", "000001.SH", "price_index", "CNY", "index points", "Asia/Shanghai", "15:00", "provider_unadjusted_index_level"),
    InstrumentSpec("star50", "科创 50", "a_share", "primary_chart", "tencent_kline", "sh000688", "000688.SH", "price_index", "CNY", "index points", "Asia/Shanghai", "15:00", "provider_unadjusted_index_level"),
    InstrumentSpec("wti", "WTI 原油", "commodity", "primary_chart", "yahoo_chart", "CL=F", "CL=F", "continuous_future", "USD", "USD/barrel", "America/New_York", "17:00", "provider_continuous_front_month_unadjusted"),
    InstrumentSpec("gold", "黄金", "commodity", "primary_chart", "yahoo_chart", "GC=F", "GC=F", "continuous_future", "USD", "USD/troy ounce", "America/New_York", "17:00", "provider_continuous_front_month_unadjusted"),
    InstrumentSpec("silver", "白银", "commodity", "primary_chart", "yahoo_chart", "SI=F", "SI=F", "continuous_future", "USD", "USD/troy ounce", "America/New_York", "17:00", "provider_continuous_front_month_unadjusted"),
    InstrumentSpec("kospi", "KOSPI", "asia_equity", "primary_chart", "yahoo_chart", "^KS11", "^KS11", "price_index", "KRW", "index points", "Asia/Seoul", "15:30", "provider_unadjusted_index_level"),
    InstrumentSpec("nikkei", "Nikkei 225", "asia_equity", "primary_chart", "yahoo_chart", "^N225", "^N225", "price_index", "JPY", "index points", "Asia/Tokyo", "15:30", "provider_unadjusted_index_level"),
    InstrumentSpec("vix", "VIX", "risk_probe", "evidence_probe", "yahoo_chart", "^VIX", "^VIX", "volatility_index", "USD", "index points", "America/Chicago", "15:15", "provider_unadjusted_index_level"),
    InstrumentSpec("china_dividend", "上证红利", "style_probe", "evidence_probe", "tencent_kline", "sh000015", "000015.SH", "price_index", "CNY", "index points", "Asia/Shanghai", "15:00", "provider_unadjusted_index_level"),
    InstrumentSpec("us_dividend", "Schwab US Dividend Equity ETF", "style_probe", "evidence_probe", "yahoo_chart", "SCHD", "SCHD", "etf", "USD", "USD/share", "America/New_York", "16:00", "provider_unadjusted_trade_price"),
)
INSTRUMENT_BY_KEY: dict[str, InstrumentSpec] = {item.key: item for item in INSTRUMENTS}
if len(INSTRUMENT_BY_KEY) != len(INSTRUMENTS):  # pragma: no cover - import invariant
    raise RuntimeError("market-regime instrument keys must be unique")
if sum(item.is_primary_chart for item in INSTRUMENTS) != 9:  # pragma: no cover
    raise RuntimeError("market-regime contract must contain exactly nine primary charts")


@dataclass(frozen=True)
class LicenseDecision:
    deployment_mode: str
    license_status: str
    license_reference: str | None
    allowed: bool
    verified_for_publication: bool
    boundary: str

    def as_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ParsedProviderPayload:
    rows: tuple[dict[str, Any], ...]
    provider_observed_at: datetime
    scheduled_session_end: datetime | None


@dataclass(frozen=True)
class HttpCapture:
    method: str
    requested_url: str
    final_url: str
    status_code: int | None
    response_headers: tuple[tuple[str, str], ...]
    dropped_header_names: tuple[str, ...]
    redirect_chain: tuple[str, ...]
    body: bytes
    fetched_at: str
    error: str | None = None

    @property
    def raw_sha256(self) -> str | None:
        return sha256(self.body).hexdigest() if self.body else None

    @property
    def content_type(self) -> str | None:
        values = dict(self.response_headers)
        raw = values.get("content-type")
        return raw.split(";", 1)[0].strip().lower() if raw else None

    def receipt(self, *, raw_path: str | None = None) -> dict[str, Any]:
        return {
            "method": self.method,
            "requested_url": self.requested_url,
            "final_url": self.final_url,
            "status_code": self.status_code,
            "content_type": self.content_type,
            "response_headers": dict(self.response_headers),
            "dropped_header_names": list(self.dropped_header_names),
            "redirect_chain": list(self.redirect_chain),
            "raw_sha256": self.raw_sha256,
            "raw_bytes": len(self.body),
            "raw_path": raw_path,
            "fetched_at": self.fetched_at,
            "error": self.error,
        }


class _CaptureRedirectHandler(HTTPRedirectHandler):
    def __init__(self) -> None:
        super().__init__()
        self.locations: list[str] = []

    def redirect_request(self, req: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> Request | None:
        self.locations.append(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (_canonical_json(value) + "\n").encode("utf-8")


def _safe_headers(headers: Mapping[str, str] | Any) -> tuple[tuple[tuple[str, str], ...], tuple[str, ...]]:
    normalized: dict[str, str] = {}
    dropped: set[str] = set()
    for name, value in headers.items():
        key = str(name).strip().lower()
        clean = " ".join(str(value).replace("\r", " ").replace("\n", " ").split())
        if key in SAFE_RESPONSE_HEADERS and clean:
            normalized[key] = clean
        elif key:
            dropped.add(key)
    return tuple(sorted(normalized.items())), tuple(sorted(dropped))


def http_get_capture(url: str, *, timeout: float = 20.0) -> HttpCapture:
    """Issue one raw GET and preserve response identity without cookie headers."""

    fetched_at = _iso_utc(_utc_now())
    redirect_handler = _CaptureRedirectHandler()
    opener = build_opener(redirect_handler)
    request = Request(
        url,
        method="GET",
        headers={"User-Agent": "ParkMarketRegimeLocalPrototype/1.0", "Accept": "application/json"},
    )
    try:
        with opener.open(request, timeout=timeout) as response:
            body = response.read()
            safe, dropped = _safe_headers(response.headers)
            final_url = response.geturl()
            chain = tuple([url, *redirect_handler.locations])
            if chain[-1] != final_url:
                chain = (*chain, final_url)
            return HttpCapture("GET", url, final_url, int(response.status), safe, dropped, chain, body, fetched_at)
    except HTTPError as exc:
        body = exc.read()
        safe, dropped = _safe_headers(exc.headers)
        final_url = exc.geturl() or url
        chain = tuple([url, *redirect_handler.locations])
        if chain[-1] != final_url:
            chain = (*chain, final_url)
        return HttpCapture("GET", url, final_url, int(exc.code), safe, dropped, chain, body, fetched_at, f"HTTPError: {exc.reason}")
    except (URLError, TimeoutError, OSError) as exc:
        return HttpCapture("GET", url, url, None, (), (), (url,), b"", fetched_at, f"{type(exc).__name__}: {exc}")


def license_decision(
    *,
    deployment_mode: str | None = None,
    license_status: str | None = None,
    license_reference: str | None = None,
    private_preview: bool | None = None,
) -> LicenseDecision:
    mode = (deployment_mode or os.getenv("PARK_MARKET_REGIME_DEPLOYMENT_MODE") or "local_prototype").strip()
    status = (license_status or os.getenv("PARK_MARKET_DATA_LICENSE_STATUS") or LOCAL_EVALUATION).strip()
    reference = (license_reference if license_reference is not None else os.getenv("PARK_MARKET_DATA_LICENSE_REFERENCE"))
    reference = reference.strip() if isinstance(reference, str) and reference.strip() else None
    preview = (os.getenv("PARK_PRIVATE_PREVIEW", "0") == "1") if private_preview is None else private_preview
    if mode not in DEPLOYMENT_MODES:
        raise LicenseGateError(f"unsupported deployment mode: {mode}")
    if status not in LICENSE_STATUSES:
        raise LicenseGateError(f"unsupported market-data license status: {status}")
    if preview and mode == "local_prototype":
        mode = "private_beta"
    if status == DISABLED:
        raise LicenseGateError("market-data collection is disabled")
    if mode in {"private_beta", "public"}:
        raise LicenseGateError(
            "private-beta/public use remains disabled until a provider/scope/deployment-bound license receipt verifier is implemented"
        )
    if mode == "local_prototype" and status == COMMERCIAL_RIGHTS_APPROVED and not reference:
        raise LicenseGateError("commercial_rights_approved requires a license reference")
    if status == LOCAL_EVALUATION:
        return LicenseDecision(
            mode,
            status,
            None,
            True,
            False,
            "Park local evaluation only; not verified for commercial use, private beta, publication, or redistribution.",
        )
    return LicenseDecision(
        mode,
        status,
        reference,
        True,
        False,
        "Operator-attested reference only; not machine-verified and grants no publication or redistribution eligibility.",
    )


def instrument_registry_payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "primary_chart_count": 9,
        "evidence_probe_count": 3,
        "instruments": [asdict(item) for item in INSTRUMENTS],
        "sources": {
            "yahoo_chart": {
                "authority_tier": "supplementary_only",
                "license_status": "unverified_for_commercial_redistribution",
                "endpoint": YAHOO_CHART_URL,
                "terms": [YAHOO_TERMS_URL, YAHOO_DEVELOPER_GUIDELINES_URL],
            },
            "tencent_kline": {
                "authority_tier": "supplementary_only",
                "license_status": "unverified_for_commercial_redistribution",
                "endpoint": TENCENT_KLINE_URL,
                "terms": [TENCENT_LEGAL_URL],
            },
        },
    }


def _provider_url(spec: InstrumentSpec) -> str:
    if spec.provider == "yahoo_chart":
        symbol = quote(spec.provider_symbol, safe="^=")
        return f"{YAHOO_CHART_URL}{symbol}?interval=1d&range=1y&events=div%2Csplits"
    if spec.provider == "tencent_kline":
        return f"{TENCENT_KLINE_URL}?param={spec.provider_symbol},day,,,260,"
    raise SourceCaptureError(f"unsupported provider: {spec.provider}")


def _parse_session_close(spec: InstrumentSpec, trade_date: date) -> datetime:
    hour, minute = (int(part) for part in spec.session_close.split(":"))
    return datetime.combine(trade_date, time(hour, minute), tzinfo=ZoneInfo(spec.exchange_timezone))


def _number(value: Any, *, field: str) -> float:
    if value is None or isinstance(value, bool):
        raise SourceCaptureError(f"bar {field} is null or non-numeric")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise SourceCaptureError(f"bar {field} is non-numeric") from exc
    if not math.isfinite(result):
        raise SourceCaptureError(f"bar {field} is non-finite")
    return result


def _validate_bar(spec: InstrumentSpec, row: Mapping[str, Any]) -> dict[str, Any]:
    try:
        trade_date = date.fromisoformat(str(row["date"]))
    except (KeyError, ValueError) as exc:
        raise SourceCaptureError("bar date must be ISO-8601") from exc
    open_price = _number(row.get("open"), field="open")
    high = _number(row.get("high"), field="high")
    low = _number(row.get("low"), field="low")
    close = _number(row.get("close"), field="close")
    if high < low or high < max(open_price, close) or low > min(open_price, close):
        raise SourceCaptureError(f"bar OHLC range is inverted on {trade_date.isoformat()}")
    if spec.key != "wti" and min(open_price, high, low, close) <= 0:
        raise SourceCaptureError(f"bar price must be positive on {trade_date.isoformat()}")
    volume_raw = row.get("volume")
    volume = None if volume_raw is None else _number(volume_raw, field="volume")
    if volume is not None and volume < 0:
        raise SourceCaptureError(f"bar volume must not be negative on {trade_date.isoformat()}")
    return {
        "date": trade_date.isoformat(),
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


def _parse_yahoo(spec: InstrumentSpec, capture: HttpCapture) -> ParsedProviderPayload:
    try:
        payload = json.loads(capture.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SourceCaptureError("Yahoo response is not valid UTF-8 JSON", capture=capture) from exc
    chart = payload.get("chart") if isinstance(payload, dict) else None
    if not isinstance(chart, dict) or chart.get("error"):
        raise SourceCaptureError(f"Yahoo chart returned an error: {(chart or {}).get('error')}", capture=capture)
    results = chart.get("result") or []
    if len(results) != 1 or not isinstance(results[0], dict):
        raise SourceCaptureError("Yahoo chart must contain exactly one result", capture=capture)
    result = results[0]
    meta = result.get("meta") or {}
    actual_symbol = str(meta.get("symbol") or "").upper()
    if actual_symbol != spec.provider_symbol.upper():
        raise SourceCaptureError(
            f"Yahoo symbol mismatch: expected {spec.provider_symbol}, got {actual_symbol or 'missing'}",
            capture=capture,
        )
    actual_currency = str(meta.get("currency") or "").upper()
    if actual_currency != spec.currency:
        raise SourceCaptureError(
            f"Yahoo currency mismatch: expected {spec.currency}, got {actual_currency or 'missing'}",
            capture=capture,
        )
    actual_timezone = str(meta.get("exchangeTimezoneName") or "")
    if actual_timezone != spec.exchange_timezone:
        raise SourceCaptureError(
            f"Yahoo timezone mismatch: expected {spec.exchange_timezone}, got {actual_timezone or 'missing'}",
            capture=capture,
        )
    try:
        provider_observed_at = datetime.fromtimestamp(
            int(meta["regularMarketTime"]), timezone.utc
        )
    except (KeyError, TypeError, ValueError, OSError) as exc:
        raise SourceCaptureError("Yahoo regularMarketTime is missing or invalid", capture=capture) from exc
    regular_period = (meta.get("currentTradingPeriod") or {}).get("regular") or {}
    try:
        scheduled_session_end = datetime.fromtimestamp(int(regular_period["end"]), timezone.utc)
    except (KeyError, TypeError, ValueError, OSError) as exc:
        raise SourceCaptureError(
            "Yahoo current regular-session end is missing or invalid", capture=capture
        ) from exc
    timestamps = result.get("timestamp") or []
    quote_rows = ((result.get("indicators") or {}).get("quote") or [])
    if len(quote_rows) != 1 or not isinstance(quote_rows[0], dict):
        raise SourceCaptureError("Yahoo chart quote arrays are missing", capture=capture)
    quote_row = quote_rows[0]
    arrays = {name: quote_row.get(name) or [] for name in ("open", "high", "low", "close")}
    if not timestamps or any(len(values) != len(timestamps) for values in arrays.values()):
        raise SourceCaptureError("Yahoo OHLC arrays do not align with timestamps", capture=capture)
    volumes = quote_row.get("volume")
    if volumes is not None and len(volumes) != len(timestamps):
        raise SourceCaptureError("Yahoo volume array does not align with timestamps", capture=capture)
    zone = ZoneInfo(spec.exchange_timezone)
    rows = []
    for index, timestamp in enumerate(timestamps):
        try:
            trade_date = datetime.fromtimestamp(int(timestamp), zone).date().isoformat()
        except (TypeError, ValueError, OSError) as exc:
            raise SourceCaptureError("Yahoo timestamp is invalid", capture=capture) from exc
        rows.append(
            {
                "date": trade_date,
                "open": arrays["open"][index],
                "high": arrays["high"][index],
                "low": arrays["low"][index],
                "close": arrays["close"][index],
                "volume": None if volumes is None else volumes[index],
            }
        )
    return ParsedProviderPayload(tuple(rows), provider_observed_at, scheduled_session_end)


def _parse_tencent(spec: InstrumentSpec, capture: HttpCapture) -> ParsedProviderPayload:
    try:
        payload = json.loads(capture.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SourceCaptureError("Tencent response is not valid UTF-8 JSON", capture=capture) from exc
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict) or spec.provider_symbol not in data:
        raise SourceCaptureError(
            f"Tencent symbol mismatch: expected response key {spec.provider_symbol}", capture=capture
        )
    stock = data[spec.provider_symbol]
    if not isinstance(stock, dict):
        raise SourceCaptureError("Tencent symbol payload must be an object", capture=capture)
    if stock.get("qfqday"):
        raise SourceCaptureError("Tencent returned adjusted qfqday rows for an unadjusted index contract", capture=capture)
    raw_rows = stock.get("day") or []
    if not isinstance(raw_rows, list) or not raw_rows:
        raise SourceCaptureError("Tencent daily OHLC rows are missing", capture=capture)
    quote_rows = (stock.get("qt") or {}).get(spec.provider_symbol) or []
    provider_timestamp = quote_rows[30] if isinstance(quote_rows, list) and len(quote_rows) > 30 else None
    try:
        provider_observed_at = datetime.strptime(str(provider_timestamp), "%Y%m%d%H%M%S").replace(
            tzinfo=ZoneInfo(spec.exchange_timezone)
        ).astimezone(timezone.utc)
    except (TypeError, ValueError) as exc:
        raise SourceCaptureError("Tencent quote timestamp is missing or invalid", capture=capture) from exc
    rows = []
    for raw in raw_rows:
        if not isinstance(raw, list) or len(raw) < 5:
            raise SourceCaptureError("Tencent OHLC row has an invalid shape", capture=capture)
        rows.append(
            {
                "date": str(raw[0])[:10],
                "open": raw[1],
                "close": raw[2],
                "high": raw[3],
                "low": raw[4],
                "volume": raw[5] if len(raw) > 5 and raw[5] not in ("", None) else None,
            }
        )
    return ParsedProviderPayload(tuple(rows), provider_observed_at, None)


def normalize_capture(
    spec: InstrumentSpec,
    capture: HttpCapture,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = (now or _utc_now()).astimezone(timezone.utc)
    if capture.error and capture.status_code is None:
        raise SourceCaptureError(f"source request failed: {capture.error}", capture=capture)
    if capture.status_code is None or not 200 <= capture.status_code < 300:
        raise SourceCaptureError(f"source HTTP status is not successful: {capture.status_code}", capture=capture)
    tencent_mislabeled_json = (
        spec.provider == "tencent_kline"
        and capture.content_type == "text/html"
        and capture.body.lstrip().startswith(b"{")
    )
    if capture.content_type != "application/json" and not tencent_mislabeled_json:
        raise SourceCaptureError(
            f"source Content-Type must be application/json, got {capture.content_type or 'missing'}",
            capture=capture,
        )
    if not capture.body:
        raise SourceCaptureError("source response body is empty", capture=capture)
    parsed = _parse_yahoo(spec, capture) if spec.provider == "yahoo_chart" else _parse_tencent(spec, capture)
    if parsed.provider_observed_at > current + timedelta(minutes=5):
        raise SourceCaptureError("provider observation is dated after the capture clock", capture=capture)
    raw_rows = parsed.rows
    bars: list[dict[str, Any]] = []
    dropped_unfinished: list[str] = []
    dropped_empty: list[str] = []
    seen: set[str] = set()
    prior: str | None = None
    local_today = current.astimezone(ZoneInfo(spec.exchange_timezone)).date()
    for raw_row in raw_rows:
        empty_ohlc = [raw_row.get(field) is None for field in ("open", "high", "low", "close")]
        if all(empty_ohlc):
            dropped_empty.append(str(raw_row.get("date") or "unknown"))
            continue
        trade_date = str(raw_row.get("date") or "")
        try:
            trade_day = date.fromisoformat(trade_date)
        except ValueError as exc:
            raise SourceCaptureError("daily bar date is invalid", capture=capture) from exc
        if trade_day > local_today:
            raise SourceCaptureError(f"daily bar is dated in the future: {trade_date}", capture=capture)
        if trade_date in seen:
            raise SourceCaptureError(f"duplicate daily bar: {trade_date}", capture=capture)
        if prior is not None and trade_date <= prior:
            raise SourceCaptureError(f"daily bars are not strictly ascending at {trade_date}", capture=capture)
        seen.add(trade_date)
        prior = trade_date
        close_at = _parse_session_close(spec, trade_day).astimezone(timezone.utc)
        if current < close_at + timedelta(minutes=20):
            dropped_unfinished.append(trade_date)
            continue
        # Provider daily bars can be internally inconsistent while the current
        # session is still forming (for example, a live close briefly above a
        # lagging high). Completed sessions remain fully validated.
        bar = _validate_bar(spec, raw_row)
        bars.append(bar)
    if len(bars) < spec.min_history:
        raise SourceCaptureError(
            f"completed daily history is too short: {len(bars)} < {spec.min_history}", capture=capture
        )
    last_date = date.fromisoformat(bars[-1]["date"])
    last_close = _parse_session_close(spec, last_date).astimezone(timezone.utc)
    age_hours = max(0.0, (current - last_close).total_seconds() / 3600)
    provider_zone = ZoneInfo(spec.exchange_timezone)
    provider_local_date = parsed.provider_observed_at.astimezone(provider_zone).date()
    if provider_local_date < last_date:
        raise SourceCaptureError("provider observation predates the latest daily bar", capture=capture)
    provider_silence_hours = max(
        0.0, (current - parsed.provider_observed_at).total_seconds() / 3600
    )
    missing_expected_session: str | None = None
    observed_session_close = _parse_session_close(spec, provider_local_date).astimezone(timezone.utc)
    if (
        provider_local_date > last_date
        and current >= observed_session_close + timedelta(minutes=20)
    ):
        missing_expected_session = provider_local_date.isoformat()
    if (
        parsed.scheduled_session_end is not None
        and current >= parsed.scheduled_session_end + timedelta(minutes=20)
    ):
        scheduled_date = parsed.scheduled_session_end.astimezone(provider_zone).date()
        if scheduled_date > last_date:
            missing_expected_session = scheduled_date.isoformat()
    if missing_expected_session is not None:
        quality = "partial"
    elif provider_silence_hours > spec.max_provider_silence_hours:
        quality = "stale"
    elif len(bars) < spec.preferred_history:
        quality = "partial"
    else:
        quality = "fresh"
    return {
        "schema_version": SCHEMA_VERSION,
        "instrument": asdict(spec),
        "bars": bars,
        "bar_count": len(bars),
        "last_completed_session": bars[-1]["date"],
        "last_completed_close_at": _iso_utc(last_close),
        "quality": quality,
        "age_hours": round(age_hours, 2),
        "provider_observed_at": _iso_utc(parsed.provider_observed_at),
        "provider_silence_hours": round(provider_silence_hours, 2),
        "scheduled_session_end": (
            _iso_utc(parsed.scheduled_session_end) if parsed.scheduled_session_end else None
        ),
        "missing_expected_session": missing_expected_session,
        "dropped_unfinished_sessions": dropped_unfinished,
        "dropped_empty_provider_sessions": dropped_empty,
        "source_quality_flags": ["provider_declares_text_html_for_json"] if tencent_mislabeled_json else [],
        "price_basis": spec.price_basis,
    }


def _bounded_excerpt(body: bytes, *, limit: int = 400) -> str | None:
    if not body:
        return None
    text = body[: max(limit * 4, limit)].decode("utf-8", errors="replace")
    text = " ".join(text.split())
    return text[:limit] if text else None


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = _json_bytes(payload)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _write_bytes_exclusive_atomic(path: Path, encoded: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return sha256(encoded).hexdigest()


def _write_json_exclusive(path: Path, payload: Mapping[str, Any]) -> str:
    return _write_bytes_exclusive_atomic(path, _json_bytes(payload))


def _write_raw_exclusive(path: Path, body: bytes) -> None:
    _write_bytes_exclusive_atomic(path, body)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    if not isinstance(payload, dict):
        raise MarketRegimeDataError(f"runtime JSON must be an object: {path}")
    return payload


def _read_bound_artifact(root: Path, reference: Mapping[str, Any]) -> dict[str, Any]:
    relative = str(reference.get("path") or "")
    expected_hash = str(reference.get("sha256") or "")
    if not relative or len(expected_hash) != 64:
        raise MarketRegimeDataError("normalized artifact reference is incomplete")
    target = (root / relative).resolve()
    if root not in target.parents:
        raise MarketRegimeDataError("normalized artifact path escapes runtime root")
    try:
        encoded = target.read_bytes()
    except FileNotFoundError as exc:
        raise MarketRegimeDataError(f"normalized artifact is missing: {relative}") from exc
    if sha256(encoded).hexdigest() != expected_hash:
        raise MarketRegimeDataError(f"normalized artifact hash mismatch: {relative}")
    try:
        payload = json.loads(encoded)
    except json.JSONDecodeError as exc:
        raise MarketRegimeDataError(f"normalized artifact is not JSON: {relative}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
        raise MarketRegimeDataError(f"normalized artifact schema mismatch: {relative}")
    return payload


def _run_id(now: datetime) -> str:
    stamp = now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"market-regime-{stamp}-{uuid4().hex[:12]}"


def _overall_quality(items: Iterable[Mapping[str, Any]]) -> str:
    materialized = list(items)
    qualities = [str(item.get("quality") or "unavailable") for item in materialized]
    if not qualities or all(value == "unavailable" for value in qualities):
        return "unavailable"
    if (
        any(item.get("refresh_status") == "rejected" for item in materialized)
        or "unavailable" in qualities
        or "stale" in qualities
        or "partial" in qualities
    ):
        return "partial"
    return "fresh"


class MarketRegimeDataStore:
    """One-shot, serial collector with immutable raw/run evidence and latest-good."""

    def __init__(self, root: Path | str, *, http_get=http_get_capture) -> None:
        self.root = Path(root).expanduser().resolve()
        self.http_get = http_get
        self._live_transport = http_get is http_get_capture

    def refresh(
        self,
        *,
        now: datetime | None = None,
        instrument_keys: Iterable[str] | None = None,
        deployment_mode: str | None = None,
        license_status: str | None = None,
        license_reference: str | None = None,
        private_preview: bool | None = None,
    ) -> dict[str, Any]:
        if now is not None and self._live_transport:
            raise MarketRegimeDataError(
                "clock overrides are permitted only with an injected offline/fixture transport"
            )
        current = (now or _utc_now()).astimezone(timezone.utc)
        decision = license_decision(
            deployment_mode=deployment_mode,
            license_status=license_status,
            license_reference=license_reference,
            private_preview=private_preview,
        )
        selected_keys = list(instrument_keys or [item.key for item in INSTRUMENTS])
        if not selected_keys or len(selected_keys) != len(set(selected_keys)):
            raise MarketRegimeDataError("instrument_keys must be a non-empty unique list")
        unknown = [key for key in selected_keys if key not in INSTRUMENT_BY_KEY]
        if unknown:
            raise MarketRegimeDataError(f"unknown market-regime instruments: {', '.join(unknown)}")
        run_id = _run_id(current)
        started = {
            "schema_version": SCHEMA_VERSION,
            "event": "started",
            "run_id": run_id,
            "started_at": _iso_utc(current),
            "instrument_keys": selected_keys,
            "license": decision.as_json(),
        }
        _write_json_exclusive(self.root / "run-events" / run_id / "000-started.json", started)
        results: list[dict[str, Any]] = []
        snapshot_items: list[dict[str, Any]] = []
        pending_latest_pointers: list[tuple[str, dict[str, Any]]] = []
        for key in selected_keys:
            spec = INSTRUMENT_BY_KEY[key]
            capture: HttpCapture | None = None
            raw_relative: str | None = None
            try:
                capture = self.http_get(_provider_url(spec))
                if capture.body:
                    suffix = ".json" if capture.content_type == "application/json" else ".bin"
                    raw_relative = f"raw/{run_id}/{key}{suffix}"
                    _write_raw_exclusive(self.root / raw_relative, capture.body)
                normalized = normalize_capture(spec, capture, now=current)
                source_receipt = capture.receipt(raw_path=raw_relative)
                frozen_artifact = {
                    **normalized,
                    "run_id": run_id,
                    "generated_at": _iso_utc(_utc_now()),
                    "source": source_receipt,
                    "license": decision.as_json(),
                    "data_kind": "real",
                    "publication_eligible": False,
                }
                normalized_relative = f"normalized/{run_id}/{key}.json"
                normalized_hash = _write_json_exclusive(
                    self.root / normalized_relative, frozen_artifact
                )
                artifact_reference = {
                    "path": normalized_relative,
                    "sha256": normalized_hash,
                    "schema_version": SCHEMA_VERSION,
                }
                latest_pointer = {
                    "schema_version": SCHEMA_VERSION,
                    "instrument_key": key,
                    "run_id": run_id,
                    "normalized_artifact": artifact_reference,
                }
                pending_latest_pointers.append((key, latest_pointer))
                results.append(
                    {
                        "key": key,
                        "status": "accepted",
                        "quality": normalized["quality"],
                        "source": source_receipt,
                        "normalized_artifact": artifact_reference,
                    }
                )
                snapshot_items.append(
                    {**frozen_artifact, "normalized_artifact": artifact_reference}
                )
            except Exception as exc:
                if not isinstance(exc, (MarketRegimeDataError, ValueError, OSError)):
                    exc = MarketRegimeDataError(f"unexpected {type(exc).__name__}: {exc}")
                if isinstance(exc, SourceCaptureError) and exc.capture is not None:
                    capture = exc.capture
                source_receipt = capture.receipt(raw_path=raw_relative) if capture else None
                failure = {
                    "key": key,
                    "status": "rejected",
                    "quality": "unavailable",
                    "reason": str(exc),
                    "source": source_receipt,
                    "bounded_raw_excerpt": _bounded_excerpt(capture.body) if capture else None,
                }
                results.append(failure)
                latest_pointer = _read_json(
                    self.root / "instruments" / key / "latest-good.json"
                )
                if latest_pointer is not None:
                    reference = latest_pointer.get("normalized_artifact") or {}
                    latest = _read_bound_artifact(self.root, reference)
                    snapshot_items.append(
                        {
                            **latest,
                            "normalized_artifact": reference,
                            "refresh_status": "rejected",
                            "refresh_failure": failure,
                        }
                    )
                else:
                    snapshot_items.append(
                        {
                            "schema_version": SCHEMA_VERSION,
                            "instrument": asdict(spec),
                            "bars": [],
                            "bar_count": 0,
                            "quality": "unavailable",
                            "refresh_status": "rejected",
                            "refresh_failure": failure,
                            "publication_eligible": False,
                        }
                    )
        completed_at = _iso_utc(_utc_now())
        receipt = {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "started_at": _iso_utc(current),
            "completed_at": completed_at,
            "license": decision.as_json(),
            "registry_sha256": sha256(_canonical_json(instrument_registry_payload()).encode("utf-8")).hexdigest(),
            "results": results,
            "accepted_count": sum(item["status"] == "accepted" for item in results),
            "rejected_count": sum(item["status"] == "rejected" for item in results),
        }
        _write_json_exclusive(self.root / "runs" / f"{run_id}.json", receipt)
        _write_json_exclusive(
            self.root / "run-events" / run_id / "001-completed.json",
            {"schema_version": SCHEMA_VERSION, "event": "completed", **receipt},
        )
        for key, pointer in pending_latest_pointers:
            _write_json_atomic(
                self.root / "instruments" / key / "latest-good.json", pointer
            )
        snapshot = {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "generated_at": completed_at,
            "verdict_as_of": None,
            "analysis_status": "not_computed",
            "quality": _overall_quality(snapshot_items),
            "license": decision.as_json(),
            "instrument_count": len(snapshot_items),
            "instruments": snapshot_items,
            "refresh_receipt": f"runs/{run_id}.json",
        }
        _write_json_atomic(self.root / "latest.json", snapshot)
        return snapshot

    def latest(self) -> dict[str, Any]:
        payload = _read_json(self.root / "latest.json")
        if payload is None:
            raise MarketRegimeDataError("market-regime latest snapshot is unavailable")
        if payload.get("schema_version") != SCHEMA_VERSION:
            raise MarketRegimeDataError("market-regime latest snapshot schema mismatch")
        for item in payload.get("instruments") or []:
            reference = item.get("normalized_artifact") if isinstance(item, dict) else None
            if not reference:
                if isinstance(item, dict) and item.get("quality") == "unavailable":
                    continue
                raise MarketRegimeDataError("market-regime snapshot item lacks normalized artifact")
            frozen = _read_bound_artifact(self.root, reference)
            projected = {
                key: value
                for key, value in item.items()
                if key not in {"normalized_artifact", "refresh_status", "refresh_failure"}
            }
            if _canonical_json(projected) != _canonical_json(frozen):
                raise MarketRegimeDataError("market-regime snapshot copy differs from normalized artifact")
        return payload
