"""Strict HTTP client and source bridge for the datafeed-backed Weekly run."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo
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
    "shanghai": "sh000001",
    "star50": "sh000688",
    "china_dividend": "sh000015",
    "nikkei": "^N225",
    "kospi": "^KS11",
    "wti": "CL=F",
    "gold": "GC=F",
    "silver": "SI=F",
}
EXPECTED_PROVIDER_SYMBOLS = {
    "us2y": "2 Yr",
    "us10y": "10 Yr",
    "us2s10s": "10 Yr-2 Yr",
}
EXPLICIT_FALLBACK_SOURCES = {
    "shanghai": ("sina_index",),
    "star50": ("sina_index",),
    "china_dividend": ("sina_index",),
}


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def datafeed_request_for_asset(asset_key: str, timeframe: str) -> dict[str, Any]:
    spec = WEEKLY_ASSET_REGISTRY.get(asset_key)
    if spec is None:
        raise ValueError("asset_key_unknown")
    if timeframe not in spec["allowed_timeframes"]:
        raise ValueError("timeframe_not_allowed")
    fallback_sources = list(EXPLICIT_FALLBACK_SOURCES.get(asset_key, ()))
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
        "fallback_policy": "explicit" if fallback_sources else "none",
        "fallback_sources": fallback_sources,
    }


def _unavailable(
    asset_key: str,
    timeframe: str,
    reason: str,
    *,
    payload: Any = None,
) -> dict[str, Any]:
    response = build_unavailable_candle_response(asset_key, timeframe, reason[:180])
    spec = WEEKLY_ASSET_REGISTRY[asset_key]
    response.update(
        {
            "requested_source": spec["source_id"].removeprefix("datafeed:"),
            "source_mode": spec["source_id"].removeprefix("datafeed:"),
            "fallback_policy": spec.get("fallback_policy", "none"),
            "fallback_sources": list(spec.get("fallback_sources", [])),
        }
    )
    detail = payload.get("detail") if isinstance(payload, Mapping) else payload
    metadata = detail if isinstance(detail, Mapping) else payload if isinstance(payload, Mapping) else {}
    for field in ("provider", "source_mode", "provider_symbol", "selected_source", "selection_reason", "raw_timeframe", "timeframe_origin", "served_from"):
        value = metadata.get(field)
        if isinstance(value, str) and value.strip():
            response[field] = value
    attempted = metadata.get("attempted_sources")
    if isinstance(attempted, list) and all(isinstance(item, str) and item.strip() for item in attempted):
        response["attempted_sources"] = attempted
    aggregation = metadata.get("aggregation")
    if isinstance(aggregation, Mapping):
        response["aggregation"] = dict(aggregation)
    source_identity = metadata.get("source_identity")
    if isinstance(source_identity, Mapping):
        response["source_identity"] = {
            **dict(response.get("source_identity") or {}),
            **dict(source_identity),
        }
    if metadata.get("reject_reason"):
        response["upstream_reject_reason"] = str(metadata["reject_reason"])
    access_issues = metadata.get("access_issues")
    if isinstance(access_issues, list) and all(isinstance(item, str) and item.strip() for item in access_issues):
        response["access_issues"] = list(access_issues)
    quality_flags = metadata.get("quality_flags")
    if isinstance(quality_flags, list) and all(isinstance(item, str) and item.strip() for item in quality_flags):
        response["quality_flags"] = list(quality_flags)
    response["source_identity"] = {
        **dict(response.get("source_identity") or {}),
        **(
            {"provider": response["provider"]}
            if isinstance(response.get("provider"), str) and response["provider"]
            else {}
        ),
        **(
            {"provider_symbol": response["provider_symbol"]}
            if isinstance(response.get("provider_symbol"), str) and response["provider_symbol"]
            else {}
        ),
        "response_sha256": _digest({"payload": payload, "reason": reason}),
    }
    return validate_weekly_candle_response(response)


def _parse_public_timestamp(value: Any) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError) as exc:
        raise WeeklyCandleContractError("four_hour_timestamp_invalid") from exc
    if parsed.tzinfo is None:
        raise WeeklyCandleContractError("four_hour_timestamp_requires_timezone")
    return parsed.astimezone(timezone.utc)


def _validate_public_4h_metadata(
    asset_key: str,
    payload: Mapping[str, Any],
    candles: list[Mapping[str, Any]],
) -> dict[str, Any]:
    """Validate the typed public 4H seam before it reaches Weekly aggregation."""

    raw_timeframe = payload.get("raw_timeframe")
    origin = payload.get("timeframe_origin")
    aggregation = payload.get("aggregation")
    if raw_timeframe not in {"1h", "4h"}:
        raise WeeklyCandleContractError("four_hour_raw_timeframe_invalid")
    if origin not in {"native", "aggregated"} or not isinstance(aggregation, Mapping):
        raise WeeklyCandleContractError("four_hour_transform_metadata_invalid")
    if raw_timeframe == "4h":
        if (
            origin != "native"
            or aggregation.get("kind") != "none"
            or aggregation.get("rule") != "native_passthrough"
        ):
            raise WeeklyCandleContractError("four_hour_native_metadata_invalid")
    else:
        if (
            origin != "aggregated"
            or aggregation.get("kind") != "ohlc_resample"
            or aggregation.get("rule") != "fixed_4h"
            or aggregation.get("input_timeframe") != "1h"
        ):
            raise WeeklyCandleContractError("four_hour_aggregation_metadata_invalid")
    registry = WEEKLY_ASSET_REGISTRY[asset_key]
    expected_zone_name = str(registry.get("four_hour_bucket_timezone") or registry["timezone"])
    expected_anchor_hour = int(registry.get("four_hour_anchor_hour", registry.get("anchor_hour", 0)))
    expected_anchor_minute = int(registry.get("four_hour_anchor_minute", 0))
    if raw_timeframe == "1h" and any(
        field not in aggregation for field in ("bucket_timezone", "anchor_hour", "anchor_minute")
    ):
        raise WeeklyCandleContractError("four_hour_anchor_metadata_missing")
    try:
        anchor_hour = int(aggregation.get("anchor_hour", expected_anchor_hour))
        anchor_minute = int(aggregation.get("anchor_minute", expected_anchor_minute))
        zone = ZoneInfo(str(aggregation.get("bucket_timezone") or expected_zone_name))
    except (KeyError, TypeError, ValueError) as exc:
        raise WeeklyCandleContractError("four_hour_anchor_invalid") from exc
    if not 0 <= anchor_hour < 24 or not 0 <= anchor_minute < 60:
        raise WeeklyCandleContractError("four_hour_anchor_invalid")
    if (
        zone.key != expected_zone_name
        or anchor_hour != expected_anchor_hour
        or anchor_minute != expected_anchor_minute
    ):
        raise WeeklyCandleContractError("four_hour_registry_anchor_mismatch")
    previous: datetime | None = None
    for row in candles:
        if not isinstance(row, Mapping):
            raise WeeklyCandleContractError("four_hour_candle_invalid")
        stamp = _parse_public_timestamp(row.get("timestamp"))
        local = stamp.astimezone(zone)
        if local.minute != anchor_minute or (local.hour - anchor_hour) % 4 != 0:
            raise WeeklyCandleContractError("four_hour_timestamp_not_on_anchor")
        if previous is not None and stamp <= previous:
            raise WeeklyCandleContractError("four_hour_bars_not_strictly_ordered")
        previous = stamp
    return {
        "raw_timeframe": raw_timeframe,
        "timeframe_origin": origin,
        "aggregation": dict(aggregation),
    }


class WeeklyDatafeedClient:
    """A strict datafeed client with only declared A-share fallback sources."""

    def __init__(self, *, base_url: str = "http://127.0.0.1:8100", timeout: float = 45.0, opener: Callable[..., Any] | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.opener = opener or (lambda request, timeout: urlopen(request, timeout=timeout))

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
        query: list[tuple[str, str]] = [
            ("timeframe", request_spec["timeframe"]),
            ("source", request_spec["api_source"]),
            ("cache_policy", "bypass"),
            ("quality", "strict"),
            ("fallback_policy", request_spec["fallback_policy"]),
            ("limit", str(limit)),
        ]
        query.extend(("fallback_sources", source) for source in request_spec["fallback_sources"])
        if start:
            query.append(("start", start))
        if end:
            query.append(("end", end))
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
            return _unavailable(
                asset_key,
                timeframe,
                f"datafeed_http:{status}:{detail or 'error'}",
                payload=payload,
            )
        try:
            return self._convert_response(asset_key, timeframe, payload)
        except (WeeklyCandleContractError, TypeError, ValueError) as exc:
            return _unavailable(
                asset_key,
                timeframe,
                f"datafeed_contract:{str(exc)}",
                payload=payload,
            )

    def _convert_response(self, asset_key: str, timeframe: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        request_spec = datafeed_request_for_asset(asset_key, timeframe)
        if not isinstance(payload, Mapping):
            raise WeeklyCandleContractError("datafeed_payload_invalid")
        expected_provider_symbol = EXPECTED_PROVIDER_SYMBOLS.get(asset_key, request_spec["ticker"])
        if payload.get("ticker") not in {request_spec["ticker"], expected_provider_symbol}:
            raise WeeklyCandleContractError("datafeed_ticker_mismatch")
        if asset_key in EXPECTED_PROVIDER_SYMBOLS and payload.get("provider_symbol") != expected_provider_symbol:
            raise WeeklyCandleContractError("datafeed_provider_symbol_mismatch")
        if payload.get("asset_class") != request_spec["asset_class"]:
            raise WeeklyCandleContractError("datafeed_asset_class_mismatch")
        if payload.get("timeframe") != request_spec["timeframe"]:
            raise WeeklyCandleContractError("datafeed_timeframe_mismatch")
        allowed_sources = [request_spec["api_source"], *request_spec["fallback_sources"]]
        requested_source = payload.get("requested_source")
        selected_source = payload.get("selected_source")
        if requested_source != request_spec["api_source"] or selected_source not in allowed_sources:
            raise WeeklyCandleContractError("datafeed_source_mismatch")
        if payload.get("cache_policy") != "bypass" or payload.get("quality_policy") != "strict" or payload.get("fallback_policy") != request_spec["fallback_policy"]:
            raise WeeklyCandleContractError("datafeed_policy_mismatch")
        attempted_sources = payload.get("attempted_sources")
        if not isinstance(attempted_sources, list) or not all(isinstance(item, str) for item in attempted_sources):
            raise WeeklyCandleContractError("datafeed_attempted_sources_invalid")
        selected_index = allowed_sources.index(selected_source)
        if attempted_sources != allowed_sources[: selected_index + 1]:
            raise WeeklyCandleContractError("datafeed_attempted_sources_mismatch")
        if selected_index > 0 and payload.get("selection_reason") != "explicit_fallback":
            raise WeeklyCandleContractError("datafeed_fallback_reason_missing")
        if payload.get("data_kind") in {"cached", "fixture"}:
            raise WeeklyCandleContractError("data_kind_not_publishable")
        # If the upstream envelope carries semantic identity, it is
        # authoritative input to validate, never a field we silently
        # relabel from the local request registry.  Older datafeed responses
        # may omit these optional fields, in which case the request mapping
        # remains the explicit local source of truth.
        for field in ("canonical_symbol", "series_kind", "unit", "price_basis", "semantic_role"):
            if field in payload and payload.get(field) != request_spec[field]:
                raise WeeklyCandleContractError(f"datafeed_{field}_mismatch")
        reject_reason = payload.get("reject_reason")
        candles = payload.get("candles")
        status = "ready" if not reject_reason and isinstance(candles, list) and candles else "unavailable"
        four_hour_metadata = None
        if request_spec["timeframe"] == "4h" and status == "ready":
            four_hour_metadata = _validate_public_4h_metadata(asset_key, payload, candles)
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
            if request_spec["timeframe"] == "4h":
                bar["duration_hours"] = 4
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
            "provider_symbol": payload.get("provider_symbol", expected_provider_symbol),
            "source_mode": payload.get("source_mode", request_spec["api_source"]),
            "requested_source": payload.get("requested_source", request_spec["api_source"]),
            "selected_source": payload.get("selected_source", request_spec["api_source"]),
            "selection_reason": payload.get("selection_reason", "requested_or_default"),
            "attempted_sources": list(payload.get("attempted_sources") or [request_spec["api_source"]]),
            "cache_policy": payload.get("cache_policy", "bypass"),
            "quality_policy": payload.get("quality_policy", "strict"),
            "fallback_policy": payload.get("fallback_policy", request_spec["fallback_policy"]),
            "fallback_sources": list(request_spec["fallback_sources"]),
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
                **(
                    dict(payload.get("source_identity"))
                    if isinstance(payload.get("source_identity"), Mapping)
                    else {}
                ),
                "provider": payload.get("provider", ""),
                "source_mode": payload.get("source_mode", request_spec["api_source"]),
                "provider_symbol": payload.get("provider_symbol", request_spec["ticker"]),
                "response_sha256": _digest(payload),
            },
            "data_kind": "real",
            "bars": bars if status == "ready" else [],
        }
        if request_spec["timeframe"] == "4h" and four_hour_metadata:
            response.update(four_hour_metadata)
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


def _quality_for_source(response: Mapping[str, Any]) -> str:
    if response.get("status") != "ready":
        return "unavailable"
    fresh = response.get("fresh")
    if fresh is True:
        return "fresh"
    if fresh is False:
        return "stale"
    return "unknown"


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
        daily_data_kind = daily.get("data_kind") or "real"
        item: dict[str, Any] = {
            "key": asset_key,
            "canonical_symbol": spec["canonical_symbol"],
            "series_kind": legacy_kind,
            "timezone": spec["timezone"],
            "unit": spec["unit"],
            "price_basis": spec["price_basis"],
            "status": "complete" if daily.get("status") == "ready" else "unavailable",
            "daily_status": daily.get("status"),
            "daily_reject_reason": daily.get("reject_reason"),
            "daily_access_issues": list(daily.get("access_issues") or []),
            "quality": _quality_for_source(daily),
            "data_kind": daily_data_kind,
            "source_identity": dict(source_identity),
            "weekly_source_identity": dict(weekly.get("source_identity") or {}),
            "weekly_status": weekly.get("status"),
            "weekly_reject_reason": weekly.get("reject_reason"),
            "weekly_access_issues": list(weekly.get("access_issues") or []),
            "weekly_quality": _quality_for_source(weekly),
            "weekly_quality_flags": list(weekly.get("quality_flags") or []),
            "weekly_fresh": weekly.get("fresh"),
            "weekly_data_kind": weekly.get("data_kind") or daily_data_kind,
            "points": _bar_for_source(daily, spec["series_kind"]),
        }
        weekly_points_by_key[asset_key] = _bar_for_source(weekly, spec["series_kind"]) if weekly.get("status") == "ready" else None
        if isinstance(weekly.get("source_identity"), Mapping) and weekly["source_identity"].get("response_sha256"):
            item["source_identity"]["weekly_response_sha256"] = weekly["source_identity"]["response_sha256"]
        if "four_hour" in spec["allowed_timeframes"]:
            hourly = client.fetch(asset_key, "four_hour", start=(date.fromisoformat(week_end) - timedelta(days=60)).isoformat(), end=end, limit=1000)
            item["hourly_points"] = [
                {"timestamp": row["timestamp"], "open": row["open"], "high": row["high"], "low": row["low"], "close": row["close"], "volume": row.get("volume", 0)}
                for row in hourly.get("bars") or []
            ]
            item["hourly_raw_timeframe"] = hourly.get("raw_timeframe")
            item["hourly_timeframe_origin"] = hourly.get("timeframe_origin")
            item["hourly_aggregation"] = dict(hourly.get("aggregation") or {})
            item["hourly_status"] = hourly.get("status")
            item["hourly_source_identity"] = dict(hourly.get("source_identity") or {})
            item["hourly_reject_reason"] = hourly.get("reject_reason")
            item["hourly_access_issues"] = list(hourly.get("access_issues") or [])
            item["hourly_quality"] = _quality_for_source(hourly)
            item["hourly_data_kind"] = hourly.get("data_kind") or item["data_kind"]
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
    snapshot["source_policy"] = {
        "datafeed": True,
        "cache_policy": "bypass",
        "quality": "strict",
        "fallback_policy": "explicit_for_declared_a_share_indices",
        "fallback_sources": dict(EXPLICIT_FALLBACK_SOURCES),
    }
    return snapshot
