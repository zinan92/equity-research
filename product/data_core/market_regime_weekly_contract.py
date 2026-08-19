"""Canonical Weekly CandleResponse and 17-asset registry contract.

This module is the narrow boundary between a future datafeed adapter and the
existing Weekly runtime.  It intentionally validates envelopes without making
provider requests or rendering charts.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
import math
from typing import Any, Mapping

from .market_regime_weekly_source import CANONICAL_REGISTRY as SOURCE_REGISTRY, CONTEXT_4H_KEYS as SOURCE_CONTEXT_4H_KEYS


CANDLE_RESPONSE_SCHEMA_VERSION = "kline-candles-v1"
WEEKLY_CANDLE_CONTRACT_VERSION = "market-regime-weekly-candle-contract-v1"
WEEKLY_ASSET_REGISTRY_VERSION = "market-regime-weekly-asset-registry-v1"
WEEKLY_TIMEFRAMES = ("daily", "weekly")
CONTEXT_4H_KEYS = SOURCE_CONTEXT_4H_KEYS
_STATUSES = frozenset({"ready", "unavailable", "blocked"})
_SERIES_KINDS = frozenset({"price", "rate_level", "spread"})
_CACHE_POLICIES = frozenset({"allow", "bypass", "require"})
_QUALITY_POLICIES = frozenset({"standard", "strict"})


class WeeklyCandleContractError(ValueError):
    """CandleResponse or registry contract failed closed."""


_DATAFEED_METADATA = {
    "dxy": ("index", "datafeed:yahoo_finance_index", "dxy_index_not_broad_dollar"),
    "us2y": ("macro", "datafeed:fred_public_csv_macro", "treasury_yield_not_bond_price"),
    "us10y": ("macro", "datafeed:fred_public_csv_macro", "treasury_yield_not_bond_price"),
    "us2s10s": ("macro", "datafeed:fred_public_csv_macro", "treasury_curve_spread_not_bond_price"),
    "sp500": ("index", "datafeed:yahoo_finance_index", "price_index"),
    "nasdaq": ("index", "datafeed:yahoo_finance_index", "price_index"),
    "us_dividend": ("etf", "datafeed:yahoo_finance_etf", "price_etf"),
    "vix": ("index", "datafeed:yahoo_finance_index", "price_index"),
    "bitcoin": ("crypto", "datafeed:binance_spot_public", "price_crypto"),
    "shanghai": ("index", "datafeed:tushare_pro", "price_index"),
    "star50": ("index", "datafeed:tushare_pro", "price_index"),
    "china_dividend": ("index", "datafeed:tushare_pro", "price_index"),
    "nikkei": ("index", "datafeed:yahoo_finance_index", "price_index"),
    "kospi": ("index", "datafeed:yahoo_finance_index", "price_index"),
    "wti": ("commodity", "datafeed:yahoo_finance_futures", "price_continuous_future"),
    "gold": ("commodity", "datafeed:yahoo_finance_futures", "price_continuous_future"),
    "silver": ("commodity", "datafeed:yahoo_finance_futures", "price_continuous_future"),
}


WEEKLY_ASSET_REGISTRY: dict[str, dict[str, Any]] = {}
for _key, _legacy in SOURCE_REGISTRY.items():
    _entry = dict(_legacy)
    _entry["asset_class"], _entry["source_id"], _entry["semantic_role"] = _DATAFEED_METADATA[_key]
    _entry["series_kind"] = "spread" if _key == "us2s10s" else _legacy["series_kind"]
    _entry["allowed_timeframes"] = WEEKLY_TIMEFRAMES + (("four_hour",) if _key in CONTEXT_4H_KEYS else ())
    WEEKLY_ASSET_REGISTRY[_key] = _entry


def _timestamp(value: Any, *, field: str) -> datetime:
    try:
        if isinstance(value, (int, float)):
            parsed = datetime.fromtimestamp(float(value), timezone.utc)
        else:
            text = str(value or "")
            if len(text) == 10 and text[4] == "-" and text[7] == "-":
                parsed = datetime.combine(date.fromisoformat(text), datetime.min.time(), tzinfo=timezone.utc)
            else:
                parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (TypeError, ValueError, OverflowError) as exc:
        raise WeeklyCandleContractError(f"{field}_invalid") from exc
    if parsed.tzinfo is None:
        raise WeeklyCandleContractError(f"{field}_requires_timezone")
    return parsed.astimezone(timezone.utc)


def _finite(value: Any, *, field: str) -> float:
    if isinstance(value, bool):
        raise WeeklyCandleContractError(f"{field}_invalid")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise WeeklyCandleContractError(f"{field}_invalid") from exc
    if not math.isfinite(parsed):
        raise WeeklyCandleContractError(f"{field}_invalid")
    return parsed


def _non_empty_string(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WeeklyCandleContractError(f"{field}_missing")
    return value.strip()


def _validate_bar(row: Any, *, index: int, series_kind: str, cutoff: datetime | None) -> None:
    if not isinstance(row, Mapping):
        raise WeeklyCandleContractError(f"bar_{index}_invalid")
    stamp = _timestamp(row.get("timestamp"), field=f"bar_{index}_timestamp")
    if cutoff is not None and stamp > cutoff:
        raise WeeklyCandleContractError("bar_after_cutoff")
    open_value = _finite(row.get("open"), field=f"bar_{index}_open")
    high = _finite(row.get("high"), field=f"bar_{index}_high")
    low = _finite(row.get("low"), field=f"bar_{index}_low")
    close = _finite(row.get("close"), field=f"bar_{index}_close")
    volume = _finite(row.get("volume", 0), field=f"bar_{index}_volume")
    if volume < 0:
        raise WeeklyCandleContractError("bar_volume_negative")
    if high < max(open_value, close):
        raise WeeklyCandleContractError("bar_high_invalid")
    if low > min(open_value, close):
        raise WeeklyCandleContractError("bar_low_invalid")
    if series_kind in {"rate_level", "spread"}:
        value = _finite(row.get("value"), field=f"bar_{index}_value")
        if any(abs(item - value) > 1e-12 for item in (open_value, high, low, close)):
            raise WeeklyCandleContractError("rate_bar_ohlc_value_mismatch")


def validate_weekly_candle_response(response: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one canonical Weekly response and return a detached mapping."""

    if not isinstance(response, Mapping):
        raise WeeklyCandleContractError("response_invalid")
    result = dict(response)
    if result.get("schema_version") != CANDLE_RESPONSE_SCHEMA_VERSION:
        raise WeeklyCandleContractError("schema_version_invalid")
    if result.get("weekly_contract_version") != WEEKLY_CANDLE_CONTRACT_VERSION:
        raise WeeklyCandleContractError("weekly_contract_version_invalid")
    key = _non_empty_string(result.get("asset_key"), field="asset_key")
    spec = WEEKLY_ASSET_REGISTRY.get(key)
    if spec is None:
        raise WeeklyCandleContractError("asset_key_unknown")
    for field in ("canonical_symbol", "asset_class", "series_kind", "unit", "price_basis", "semantic_role"):
        if result.get(field) != spec[field]:
            raise WeeklyCandleContractError(f"registry_{field}_mismatch")
    timeframe = _non_empty_string(result.get("timeframe"), field="timeframe")
    if timeframe not in spec["allowed_timeframes"]:
        raise WeeklyCandleContractError("timeframe_not_allowed")
    status = _non_empty_string(result.get("status"), field="status")
    if status not in _STATUSES:
        raise WeeklyCandleContractError("status_invalid")
    if result.get("cache_policy") not in _CACHE_POLICIES:
        raise WeeklyCandleContractError("cache_policy_invalid")
    if result.get("quality_policy") not in _QUALITY_POLICIES:
        raise WeeklyCandleContractError("quality_policy_invalid")
    if result.get("fallback_policy") != "none":
        raise WeeklyCandleContractError("fallback_policy_invalid")
    if type(result.get("is_synthetic")) is not bool:
        raise WeeklyCandleContractError("synthetic_flag_invalid")
    if status == "ready" and result["is_synthetic"]:
        raise WeeklyCandleContractError("synthetic_ready_forbidden")
    quality_flags = result.get("quality_flags")
    access_issues = result.get("access_issues")
    if not isinstance(quality_flags, list) or not all(isinstance(item, str) and item.strip() for item in quality_flags):
        raise WeeklyCandleContractError("quality_flags_invalid")
    if not isinstance(access_issues, list) or not all(isinstance(item, str) and item.strip() for item in access_issues):
        raise WeeklyCandleContractError("access_issues_invalid")
    source_identity = result.get("source_identity")
    if status == "ready":
        if not isinstance(source_identity, Mapping) or not any(isinstance(value, str) and value.strip() for value in source_identity.values()):
            raise WeeklyCandleContractError("source_identity_missing")
        for field in ("provider", "source_mode", "requested_source", "selected_source", "served_from"):
            _non_empty_string(result.get(field), field=field)
    elif source_identity is not None and not isinstance(source_identity, Mapping):
        raise WeeklyCandleContractError("source_identity_invalid")
    if result.get("execution_venue") is not False:
        raise WeeklyCandleContractError("execution_venue_forbidden")
    if result.get("fresh") is not None and type(result.get("fresh")) is not bool:
        raise WeeklyCandleContractError("fresh_invalid")
    if status == "ready" and result.get("fresh") is False:
        raise WeeklyCandleContractError("stale_ready_forbidden")
    for field in ("age_seconds", "max_age_seconds"):
        if result.get(field) is not None and _finite(result[field], field=field) < 0:
            raise WeeklyCandleContractError(f"{field}_invalid")
    if status == "ready" and result.get("age_seconds") is not None and result.get("max_age_seconds") is not None and float(result["age_seconds"]) > float(result["max_age_seconds"]):
        raise WeeklyCandleContractError("stale_ready_forbidden")
    if status == "ready" and result.get("latest_timestamp") is None:
        raise WeeklyCandleContractError("latest_timestamp_missing")
    cutoff = _timestamp(result["cutoff_at"], field="cutoff_at") if result.get("cutoff_at") is not None else None
    bars = result.get("bars")
    if not isinstance(bars, list):
        raise WeeklyCandleContractError("bars_invalid")
    if status == "ready" and not bars:
        raise WeeklyCandleContractError("ready_bars_missing")
    if status != "ready" and bars:
        raise WeeklyCandleContractError("unavailable_bars_present")
    previous: datetime | None = None
    for index, row in enumerate(bars):
        stamp = _timestamp(row.get("timestamp") if isinstance(row, Mapping) else None, field=f"bar_{index}_timestamp")
        if previous is not None and stamp <= previous:
            raise WeeklyCandleContractError("bars_not_strictly_ordered")
        _validate_bar(row, index=index, series_kind=spec["series_kind"], cutoff=cutoff)
        previous = stamp
    if status == "ready" and result.get("latest_timestamp") is not None:
        latest = _timestamp(result["latest_timestamp"], field="latest_timestamp")
        if previous is None or latest != previous:
            raise WeeklyCandleContractError("latest_timestamp_mismatch")
    if status != "ready" and not _non_empty_string(result.get("reject_reason"), field="reject_reason"):
        raise WeeklyCandleContractError("unavailable_reason_missing")
    return result


def build_unavailable_candle_response(asset_key: str, timeframe: str, reason: str) -> dict[str, Any]:
    spec = WEEKLY_ASSET_REGISTRY.get(asset_key)
    if spec is None:
        raise WeeklyCandleContractError("asset_key_unknown")
    response = {
        "schema_version": CANDLE_RESPONSE_SCHEMA_VERSION,
        "weekly_contract_version": WEEKLY_CANDLE_CONTRACT_VERSION,
        "asset_key": asset_key,
        **{field: spec[field] for field in ("canonical_symbol", "asset_class", "series_kind", "unit", "price_basis")},
        "semantic_role": spec["semantic_role"],
        "timeframe": timeframe,
        "status": "unavailable",
        "provider": "",
        "source_mode": "",
        "requested_source": "",
        "selected_source": "",
        "cache_policy": "bypass",
        "quality_policy": "strict",
        "fallback_policy": "none",
        "quality_flags": [],
        "is_synthetic": False,
        "served_from": "",
        "fresh": None,
        "latest_timestamp": None,
        "age_seconds": None,
        "max_age_seconds": None,
        "execution_venue": False,
        "reject_reason": reason,
        "access_issues": [reason],
        "source_identity": {},
        "bars": [],
    }
    return validate_weekly_candle_response(response)


def _source_identity_provider(identity: Mapping[str, Any]) -> str:
    provider = identity.get("provider")
    if isinstance(provider, str) and provider.strip():
        return provider
    return "weekly_authority"


def build_candle_response_from_weekly_series(
    source_snapshot: Mapping[str, Any],
    asset_key: str,
    timeframe: str,
) -> dict[str, Any]:
    """Bridge one existing Weekly source series into the canonical envelope.

    This is a compatibility seam for the current Weekly authority.  The next
    datafeed ticket replaces the bridge's source loader, not its response
    contract.
    """

    spec = WEEKLY_ASSET_REGISTRY.get(asset_key)
    if spec is None:
        raise WeeklyCandleContractError("asset_key_unknown")
    if timeframe not in spec["allowed_timeframes"]:
        raise WeeklyCandleContractError("timeframe_not_allowed")
    series = source_snapshot.get("series", {}).get(asset_key)
    if not isinstance(series, Mapping):
        return build_unavailable_candle_response(asset_key, timeframe, "source_series_missing")
    if timeframe == "weekly":
        points = list(series.get("points") or [])
        series_status = str(series.get("status") or "unavailable")
    elif timeframe == "daily":
        points = list(series.get("daily_points") or [])
        series_status = str(series.get("status") or "unavailable")
    else:
        context = series.get("context_4h")
        points = list(context.get("points") or []) if isinstance(context, Mapping) else []
        series_status = str(context.get("status") or "unavailable") if isinstance(context, Mapping) else "unavailable"
    identity_source = series
    if timeframe == "weekly" and isinstance(series.get("weekly_source_identity"), Mapping):
        # A weekly response must carry the provenance and quality of the
        # upstream 1W request.  The legacy series still owns the daily
        # identity, so do not let it silently relabel the weekly bars.
        identity_source = {
            "source_identity": series["weekly_source_identity"],
            "quality": series.get("weekly_quality", series.get("quality")),
            "quality_flags": series.get("weekly_quality_flags", []),
            "data_kind": series.get("weekly_data_kind", series.get("data_kind")),
            "fresh": series.get("weekly_fresh"),
        }
    if timeframe == "four_hour" and isinstance(series.get("context_4h"), Mapping):
        identity_source = series["context_4h"]
    identity = identity_source.get("source_identity") if isinstance(identity_source.get("source_identity"), Mapping) else None
    if not identity:
        identity = series.get("source_identity") if isinstance(series.get("source_identity"), Mapping) else {}
    data_kind = identity_source.get("data_kind", series.get("data_kind"))
    if data_kind not in {"real", "fixture", "cached"}:
        blocked = build_unavailable_candle_response(asset_key, timeframe, "data_kind_unknown")
        blocked.update({"status": "blocked"})
        return validate_weekly_candle_response(blocked)
    if series_status != "complete" or not points:
        return build_unavailable_candle_response(asset_key, timeframe, f"source_{series_status}")
    if data_kind == "fixture":
        blocked = build_unavailable_candle_response(asset_key, timeframe, "fixture_source_not_publishable")
        blocked.update({"status": "blocked", "is_synthetic": True})
        return validate_weekly_candle_response(blocked)
    bars: list[dict[str, Any]] = []
    for point in points:
        if not isinstance(point, Mapping):
            raise WeeklyCandleContractError("source_bar_invalid")
        timestamp = point.get("date") or point.get("start_at") or point.get("timestamp")
        if spec["series_kind"] in {"rate_level", "spread"}:
            value = _finite(point.get("value"), field="source_value")
            bars.append({"timestamp": timestamp, "open": value, "high": value, "low": value, "close": value, "value": value, "volume": 0})
        else:
            bars.append({
                "timestamp": timestamp,
                "open": point.get("open"),
                "high": point.get("high"),
                "low": point.get("low"),
                "close": point.get("close"),
                "volume": point.get("volume", 0),
            })
    source_mode = "weekly_authority"
    quality_source = identity_source
    quality_flags = quality_source.get("quality_flags", series.get("quality_flags", []))
    if not isinstance(quality_flags, list):
        quality_flags = [quality_flags] if isinstance(quality_flags, str) else []
    else:
        quality_flags = list(quality_flags)
    quality = quality_source.get("quality", series.get("quality"))
    if isinstance(quality, str) and quality.strip() and quality not in quality_flags:
        quality_flags.append(quality)
    fresh_override = quality_source.get("fresh")
    fresh = fresh_override if isinstance(fresh_override, bool) else (
        True if quality == "fresh" else (False if quality in {"stale", "unavailable"} else None)
    )
    latest_timestamp = bars[-1]["timestamp"]
    response = {
        "schema_version": CANDLE_RESPONSE_SCHEMA_VERSION,
        "weekly_contract_version": WEEKLY_CANDLE_CONTRACT_VERSION,
        "asset_key": asset_key,
        **{field: spec[field] for field in ("canonical_symbol", "asset_class", "series_kind", "unit", "price_basis")},
        "semantic_role": spec["semantic_role"],
        "timeframe": timeframe,
        "status": "ready",
        "provider": _source_identity_provider(identity),
        "source_mode": source_mode,
        "requested_source": source_mode,
        "selected_source": source_mode,
        "cache_policy": "require",
        "quality_policy": "standard",
        "fallback_policy": "none",
        "quality_flags": [str(item) for item in quality_flags if isinstance(item, str) and item.strip()],
        "is_synthetic": False,
        "served_from": "cache",
        "fresh": fresh,
        "latest_timestamp": latest_timestamp,
        "age_seconds": None,
        "max_age_seconds": None,
        "execution_venue": False,
        "reject_reason": None,
        "access_issues": [],
        "source_identity": dict(identity),
        "cutoff_at": source_snapshot.get("cutoff_at"),
        "bars": bars,
    }
    return validate_weekly_candle_response(response)


def build_weekly_candle_responses(source_snapshot: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Project the current 17-asset Weekly source snapshot into 39 responses."""

    responses: dict[str, dict[str, Any]] = {}
    for asset_key, spec in WEEKLY_ASSET_REGISTRY.items():
        for timeframe in spec["allowed_timeframes"]:
            response_key = f"{asset_key}:{timeframe}"
            try:
                responses[response_key] = build_candle_response_from_weekly_series(source_snapshot, asset_key, timeframe)
            except WeeklyCandleContractError as exc:
                responses[response_key] = build_unavailable_candle_response(
                    asset_key,
                    timeframe,
                    f"candle_contract_invalid:{str(exc)}",
                )
    return responses
