"""Strict HTTP client and source bridge for the datafeed-backed Weekly run."""

from __future__ import annotations

from datetime import date, datetime, timedelta
import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from .market_regime_weekly_contract import (
    CANDLE_RESPONSE_SCHEMA_VERSION,
    WEEKLY_ASSET_REGISTRY,
    WEEKLY_CANDLE_CONTRACT_VERSION,
    WeeklyCandleContractError,
    build_unavailable_candle_response,
    validate_weekly_candle_response,
)
from .market_regime_weekly_source import build_weekly_source_snapshot


TIMEFRAME_TO_DATAFEED = {"daily": "1d", "weekly": "1w", "four_hour": "4h"}
ASSET_TICKERS = {
    "dxy": "DX-Y.NYB",
    "us2y": "DGS2",
    "us10y": "DGS10",
    "us2s10s": "T10Y2Y",
    "sp500": "^GSPC",
    "nasdaq": "^IXIC",
    "us_dividend": "SCHD",
    "vix": "^VIX",
    "bitcoin": "BTC",
    "shanghai": "000001.SH",
    "star50": "000688.SH",
    "china_dividend": "000015.SH",
    "nikkei": "^N225",
    "kospi": "^KS11",
    "wti": "WTI",
    "gold": "GOLD",
    "silver": "SILVER",
}


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def datafeed_request_for_asset(asset_key: str, timeframe: str) -> dict[str, Any]:
    spec = WEEKLY_ASSET_REGISTRY.get(asset_key)
    if spec is None:
        raise ValueError("asset_key_unknown")
    if timeframe not in spec["allowed_timeframes"]:
        raise ValueError("timeframe_not_allowed")
    return {
        "asset_key": asset_key,
        "asset_class": spec["asset_class"],
        "ticker": ASSET_TICKERS[asset_key],
        "timeframe": TIMEFRAME_TO_DATAFEED[timeframe],
        "source_id": spec["source_id"],
        "api_source": spec["source_id"].removeprefix("datafeed:"),
        "canonical_symbol": spec["canonical_symbol"],
        "series_kind": spec["series_kind"],
        "unit": spec["unit"],
        "price_basis": spec["price_basis"],
        "semantic_role": spec["semantic_role"],
    }


def _unavailable(asset_key: str, timeframe: str, reason: str) -> dict[str, Any]:
    return build_unavailable_candle_response(asset_key, timeframe, reason[:180])


class WeeklyDatafeedClient:
    """A no-fallback datafeed HTTP client returning Weekly contract envelopes."""

    def __init__(self, *, base_url: str = "http://127.0.0.1:8100", timeout: float = 45.0, opener: Callable[..., Any] | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.opener = opener or urlopen

    def fetch(
        self,
        asset_key: str,
        timeframe: str,
        *,
        start: str | None = None,
        end: str | None = None,
        limit: int = 600,
    ) -> dict[str, Any]:
        request_spec = datafeed_request_for_asset(asset_key, timeframe)
        query = {
            "timeframe": request_spec["timeframe"],
            "source": request_spec["api_source"],
            "cache_policy": "bypass",
            "quality": "strict",
            "fallback_policy": "none",
            "limit": str(limit),
        }
        if start:
            query["start"] = start
        if end:
            query["end"] = end
        url = f"{self.base_url}/api/candles/{request_spec['asset_class']}/{request_spec['ticker']}?{urlencode(query)}"
        request = Request(url, headers={"Accept": "application/json"}, method="GET")
        try:
            with self.opener(request, self.timeout) as response:
                status = int(getattr(response, "status", getattr(response, "status_code", 200)))
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
            return _unavailable(asset_key, timeframe, f"datafeed_transport:{type(exc).__name__}")
        if status < 200 or status >= 300:
            detail = payload.get("detail") if isinstance(payload, Mapping) else payload
            if isinstance(detail, Mapping):
                detail = detail.get("reject_reason") or detail.get("error") or detail.get("detail")
            return _unavailable(asset_key, timeframe, f"datafeed_http:{status}:{detail or 'error'}")
        try:
            return self._convert_response(asset_key, timeframe, payload)
        except (WeeklyCandleContractError, TypeError, ValueError) as exc:
            return _unavailable(asset_key, timeframe, f"datafeed_contract:{str(exc)}")

    def _convert_response(self, asset_key: str, timeframe: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        request_spec = datafeed_request_for_asset(asset_key, timeframe)
        if not isinstance(payload, Mapping):
            raise WeeklyCandleContractError("datafeed_payload_invalid")
        if payload.get("ticker") != request_spec["ticker"]:
            raise WeeklyCandleContractError("datafeed_ticker_mismatch")
        if payload.get("asset_class") != request_spec["asset_class"]:
            raise WeeklyCandleContractError("datafeed_asset_class_mismatch")
        if payload.get("timeframe") != request_spec["timeframe"]:
            raise WeeklyCandleContractError("datafeed_timeframe_mismatch")
        if payload.get("requested_source") != request_spec["api_source"] or payload.get("selected_source") != request_spec["api_source"]:
            raise WeeklyCandleContractError("datafeed_source_mismatch")
        if payload.get("cache_policy") != "bypass" or payload.get("quality_policy") != "strict" or payload.get("fallback_policy") != "none":
            raise WeeklyCandleContractError("datafeed_policy_mismatch")
        reject_reason = payload.get("reject_reason")
        candles = payload.get("candles")
        status = "ready" if not reject_reason and isinstance(candles, list) and candles else "unavailable"
        bars: list[dict[str, Any]] = []
        for candle in candles or []:
            if not isinstance(candle, Mapping):
                raise WeeklyCandleContractError("datafeed_candle_invalid")
            bar = {
                "timestamp": candle.get("timestamp"),
                "open": candle.get("open"),
                "high": candle.get("high"),
                "low": candle.get("low"),
                "close": candle.get("close"),
                "volume": candle.get("volume", 0),
            }
            if request_spec["series_kind"] in {"rate_level", "spread"}:
                bar["value"] = candle.get("close")
            bars.append(bar)
        response = {
            "schema_version": CANDLE_RESPONSE_SCHEMA_VERSION,
            "weekly_contract_version": WEEKLY_CANDLE_CONTRACT_VERSION,
            "asset_key": asset_key,
            "canonical_symbol": request_spec["canonical_symbol"],
            "asset_class": request_spec["asset_class"],
            "series_kind": request_spec["series_kind"],
            "semantic_role": request_spec["semantic_role"],
            "timeframe": timeframe,
            "unit": request_spec["unit"],
            "price_basis": request_spec["price_basis"],
            "status": status,
            "provider": payload.get("provider", ""),
            "source_mode": payload.get("source_mode", request_spec["api_source"]),
            "requested_source": payload.get("requested_source", request_spec["api_source"]),
            "selected_source": payload.get("selected_source", request_spec["api_source"]),
            "cache_policy": payload.get("cache_policy", "bypass"),
            "quality_policy": payload.get("quality_policy", "strict"),
            "fallback_policy": payload.get("fallback_policy", "none"),
            "quality_flags": list(payload.get("quality_flags") or []),
            "is_synthetic": bool(payload.get("is_synthetic", False)),
            "served_from": payload.get("served_from", "upstream"),
            "fresh": payload.get("fresh"),
            "latest_timestamp": payload.get("latest_timestamp"),
            "age_seconds": payload.get("age_seconds"),
            "max_age_seconds": payload.get("max_age_seconds"),
            "execution_venue": bool(payload.get("execution_venue", False)),
            "reject_reason": reject_reason or None,
            "access_issues": list(payload.get("access_issues") or []),
            "source_identity": {
                "provider": payload.get("provider", ""),
                "source_mode": payload.get("source_mode", request_spec["api_source"]),
                "response_sha256": _digest(payload),
            },
            "bars": bars if status == "ready" else [],
        }
        return validate_weekly_candle_response(response)


def _bar_for_source(response: Mapping[str, Any], series_kind: str) -> list[dict[str, Any]]:
    bars = []
    for row in response.get("bars") or []:
        item = dict(row)
        if series_kind in {"rate_level", "spread"}:
            item = {"date": str(item["timestamp"])[:10], "value": item["value"]}
        else:
            item["date"] = str(item.pop("timestamp"))[:10]
        bars.append(item)
    return bars


def load_datafeed_weekly_source_snapshot(
    client: WeeklyDatafeedClient,
    *,
    week_end: str,
    cutoff_at: str,
) -> dict[str, Any]:
    """Fetch the full Weekly registry through datafeed and build legacy source shape."""

    end = (date.fromisoformat(week_end) + timedelta(days=1)).isoformat()
    start = (date.fromisoformat(week_end) - timedelta(days=900)).isoformat()
    series: dict[str, dict[str, Any]] = {}
    weekly_points_by_key: dict[str, list[Mapping[str, Any]] | None] = {}
    for asset_key, spec in WEEKLY_ASSET_REGISTRY.items():
        daily = client.fetch(asset_key, "daily", start=start, end=end, limit=1000)
        weekly = client.fetch(asset_key, "weekly", start=(date.fromisoformat(week_end) - timedelta(days=365 * 4)).isoformat(), end=end, limit=300)
        source_identity = daily.get("source_identity") if isinstance(daily.get("source_identity"), Mapping) else {}
        legacy_kind = spec["series_kind"]
        item: dict[str, Any] = {
            "key": asset_key,
            "canonical_symbol": spec["canonical_symbol"],
            "series_kind": legacy_kind,
            "timezone": spec["timezone"],
            "unit": spec["unit"],
            "price_basis": spec["price_basis"],
            "status": "complete" if daily.get("status") == "ready" else "unavailable",
            "daily_status": daily.get("status"),
            "quality": "fresh" if daily.get("fresh") is not False else "stale",
            "data_kind": "real",
            "source_identity": dict(source_identity),
            "weekly_source_identity": dict(weekly.get("source_identity") or {}),
            "weekly_status": weekly.get("status"),
            "points": _bar_for_source(daily, spec["series_kind"]),
        }
        weekly_points_by_key[asset_key] = _bar_for_source(weekly, spec["series_kind"]) if weekly.get("status") == "ready" else None
        if isinstance(weekly.get("source_identity"), Mapping) and weekly["source_identity"].get("response_sha256"):
            item["source_identity"]["weekly_response_sha256"] = weekly["source_identity"]["response_sha256"]
        if "four_hour" in spec["allowed_timeframes"]:
            hourly = client.fetch(asset_key, "four_hour", start=(date.fromisoformat(week_end) - timedelta(days=60)).isoformat(), end=end, limit=1000)
            item["hourly_points"] = [
                {"timestamp": row["timestamp"], "open": row["open"], "high": row["high"], "low": row["low"], "close": row["close"]}
                for row in hourly.get("bars") or []
            ]
            item["hourly_source_identity"] = dict(hourly.get("source_identity") or {})
            item["hourly_quality"] = "fresh" if hourly.get("fresh") is not False else "stale"
            item["hourly_data_kind"] = "real"
            item["source_identity"] = {**item["source_identity"], "hourly_response_sha256": hourly.get("source_identity", {}).get("response_sha256")}
        series[asset_key] = item
    snapshot = build_weekly_source_snapshot(
        series,
        week_end=date.fromisoformat(week_end),
        cutoff_at=datetime.fromisoformat(cutoff_at.replace("Z", "+00:00")),
        week_count=156,
        require_all=True,
        weekly_points_by_key=weekly_points_by_key,
    )
    snapshot["data_kind"] = "real"
    snapshot["source_policy"] = {"datafeed": True, "cache_policy": "bypass", "quality": "strict", "fallback_policy": "none"}
    return snapshot
