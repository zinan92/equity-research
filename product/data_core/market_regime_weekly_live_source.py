"""Real-data adapter for the Weekly one-shot runtime.

This adapter is intentionally local-evaluation-only.  It first consumes the
validated Daily/Macro/Bitcoin authorities already on the machine, then uses
same-window Yahoo Finance client-normalized data only where an authority has
no current series or where the five approved 4H context series are needed.
No prior-week artifact is substituted for a missing current source.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote
from urllib.request import Request, urlopen

from .market_regime_data import MarketRegimeDataStore
from .market_regime_kline_newsletter import BitcoinDailyStore
from .market_regime_macro_data import MarketRegimeMacroDataStore
from .market_regime_weekly_source import (
    CANONICAL_REGISTRY,
    CONTEXT_4H_KEYS,
    build_weekly_source_snapshot_from_authorities,
)


YF_DAILY_SYMBOLS = {
    "sp500": "^GSPC",
    "nasdaq": "^IXIC",
    "us_dividend": "SCHD",
}
YF_CONTEXT_SYMBOLS = {
    "dxy": "DX-Y.NYB",
    "bitcoin": "BTC-USD",
    "wti": "CL=F",
    "gold": "GC=F",
    "silver": "SI=F",
}


class WeeklyLiveSourceError(RuntimeError):
    """Live source could not be normalized without inventing data."""


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _download_yahoo_chart(symbol: str, *, interval: str, period: str) -> list[dict[str, Any]]:
    encoded = quote(symbol, safe="^=")
    last_error: BaseException | None = None
    for host in ("query2.finance.yahoo.com", "query1.finance.yahoo.com"):
        url = f"https://{host}/v8/finance/chart/{encoded}?interval={interval}&range={period}&events=history&includeAdjustedClose=false"
        try:
            request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(request, timeout=45) as response:
                payload = json.loads(response.read().decode("utf-8"))
            result = (payload.get("chart") or {}).get("result") or []
            if not result:
                raise WeeklyLiveSourceError(f"source_empty:{symbol}:{interval}")
            chart = result[0]
            timestamps = chart.get("timestamp") or []
            quote_rows = ((chart.get("indicators") or {}).get("quote") or [{}])[0]
            rows: list[dict[str, Any]] = []
            for index, epoch in enumerate(timestamps):
                values = {field: (quote_rows.get(field) or [None] * len(timestamps))[index] for field in ("open", "high", "low", "close")}
                if any(value is None for value in values.values()):
                    continue
                timestamp = datetime.fromtimestamp(float(epoch), timezone.utc)
                floats = {field: float(value) for field, value in values.items()}
                rows.append({"date": timestamp.date().isoformat(), **floats} if interval == "1d" else {"timestamp": timestamp.isoformat().replace("+00:00", "Z"), **floats})
            if rows:
                return rows
            raise WeeklyLiveSourceError(f"source_rows_empty:{symbol}:{interval}")
        except Exception as exc:  # pragma: no cover - provider dependent
            last_error = exc
    raise WeeklyLiveSourceError(f"source_transport_failed:{symbol}:{interval}") from last_error


def _download(symbol: str, *, interval: str, period: str) -> tuple[list[dict[str, Any]], str]:
    yfinance_error: BaseException | None = None
    try:
        import yfinance as yf
    except ImportError as exc:  # pragma: no cover - environment dependent
        yfinance_error = exc
        frame = None
    else:
        try:
            frame = yf.download(symbol, period=period, interval=interval, auto_adjust=False, progress=False, threads=False)
        except Exception as exc:  # pragma: no cover - provider dependent
            yfinance_error = exc
            frame = None
    if frame is None or len(frame) == 0:
        return _download_yahoo_chart(symbol, interval=interval, period=period), "yahoo_chart"
    if getattr(frame.columns, "nlevels", 1) > 1:
        try:
            frame = frame.xs(symbol, axis=1, level=-1)
        except (KeyError, ValueError):
            frame.columns = frame.columns.get_level_values(0)
    frame.columns = [str(item).lower() for item in frame.columns]
    required = {"open", "high", "low", "close"}
    if not required.issubset(set(frame.columns)):
        raise WeeklyLiveSourceError(f"source_ohlc_missing:{symbol}:{interval}")
    result: list[dict[str, Any]] = []
    for stamp, row in frame.iterrows():
        values = {field: row.get(field) for field in required}
        if any(value is None for value in values.values()):
            continue
        try:
            floats = {field: float(value) for field, value in values.items()}
        except (TypeError, ValueError):
            continue
        if any(value != value for value in floats.values()):
            continue
        timestamp = stamp.to_pydatetime() if hasattr(stamp, "to_pydatetime") else stamp
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        timestamp = timestamp.astimezone(timezone.utc)
        if interval == "1d":
            result.append({"date": timestamp.date().isoformat(), **floats})
        else:
            result.append({"timestamp": timestamp.isoformat().replace("+00:00", "Z"), **floats})
    if not result:
        try:
            return _download_yahoo_chart(symbol, interval=interval, period=period), "yahoo_chart"
        except WeeklyLiveSourceError as exc:
            raise WeeklyLiveSourceError(f"source_rows_empty:{symbol}:{interval}") from (yfinance_error or exc)
    return result, "yfinance"


def _identity(symbol: str, interval: str, points: list[Mapping[str, Any]], provider: str) -> dict[str, Any]:
    return {
        "provider": provider,
        "symbol": symbol,
        "interval": interval,
        "capture": "client_normalized",
        "normalized_sha256": _digest(points),
    }


def _fallback_daily_instrument(key: str, symbol: str, points: list[dict[str, Any]], provider: str) -> dict[str, Any]:
    registry = CANONICAL_REGISTRY[key]
    return {
        "instrument": {
            "key": key,
            "canonical_symbol": registry["canonical_symbol"],
            "exchange_timezone": registry["timezone"],
            "unit": registry["unit"],
            "price_basis": registry["price_basis"],
        },
        "bars": points,
        "bar_count": len(points),
        "quality": "fresh",
        "data_kind": "real",
        "source_identity": _identity(symbol, "1d", points, provider),
        "publication_eligible": False,
        "action_eligible": False,
    }


def _fill_missing_daily(daily: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(daily))
    items = {str(item.get("instrument", {}).get("key")): item for item in result.get("instruments", []) if isinstance(item, Mapping)}
    for key, symbol in YF_DAILY_SYMBOLS.items():
        current = items.get(key)
        if isinstance(current, Mapping) and current.get("bars") and current.get("quality") != "unavailable":
            continue
        try:
            points, provider = _download(symbol, interval="1d", period="5y")
        except WeeklyLiveSourceError:
            continue
        replacement = _fallback_daily_instrument(key, symbol, points, provider)
        if current is None:
            result.setdefault("instruments", []).append(replacement)
        else:
            for index, item in enumerate(result["instruments"]):
                if item is current or item.get("instrument", {}).get("key") == key:
                    result["instruments"][index] = replacement
                    break
        items[key] = replacement
    return result


def _fill_missing_bitcoin(bitcoin: Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(bitcoin, Mapping) and bitcoin.get("bars"):
        return dict(bitcoin)
    symbol = "BTC-USD"
    points, provider = _download(symbol, interval="1d", period="5y")
    registry = CANONICAL_REGISTRY["bitcoin"]
    return {
        "bitcoin_id": f"market-regime-kline-bitcoin:{_digest(points)}",
        "bars": points,
        "quality": "fresh",
        "data_kind": "real",
        "instrument": {"key": "bitcoin", **registry},
        "source_identity": _identity(symbol, "1d", points, provider),
        "publication_eligible": False,
        "action_eligible": False,
    }


def load_live_weekly_source_snapshot(
    *,
    daily_root: Path | str,
    macro_root: Path | str,
    bitcoin_root: Path | str,
    week_end: date,
    cutoff_at: datetime,
) -> dict[str, Any]:
    """Load one real-data Weekly snapshot from current local authorities."""

    daily = _fill_missing_daily(MarketRegimeDataStore(daily_root).latest())
    macro = MarketRegimeMacroDataStore(macro_root).latest()
    bitcoin = _fill_missing_bitcoin(BitcoinDailyStore(bitcoin_root).latest())
    hourly: dict[str, list[dict[str, Any]]] = {}
    hourly_identity: dict[str, dict[str, Any]] = {}
    for key in CONTEXT_4H_KEYS:
        try:
            hourly[key], provider = _download(YF_CONTEXT_SYMBOLS[key], interval="1h", period="60d")
            hourly_identity[key] = _identity(YF_CONTEXT_SYMBOLS[key], "1h", hourly[key], provider)
        except WeeklyLiveSourceError:
            # A context timeframe can be unavailable without making the
            # completed weekly/daily source stale or inventing a substitute.
            continue
    snapshot = build_weekly_source_snapshot_from_authorities(
        daily_snapshot=daily,
        macro_snapshot=macro,
        bitcoin_artifact=bitcoin,
        week_end=week_end,
        cutoff_at=cutoff_at,
        week_count=156,
        require_all=True,
        hourly_points_by_key=hourly,
        hourly_source_identity_by_key=hourly_identity,
    )
    snapshot["data_kind"] = "real"
    snapshot["source_policy"] = {
        "local_authorities": True,
        "same_window_yfinance_completion": True,
        "stale_fallback": False,
        "publication_eligible": False,
        "context_4h_keys": list(CONTEXT_4H_KEYS),
    }
    return snapshot
