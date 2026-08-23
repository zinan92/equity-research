"""Weekly source-history and honest multi-timeframe aggregation primitives.

This first slice deliberately consumes already captured rows. Collection and
runtime promotion are separate stories; the public seams here are deterministic
aggregation and a typed source snapshot.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping
from zoneinfo import ZoneInfo


SCHEMA_VERSION = "market-regime-weekly-source-history-v1"
REGISTRY_VERSION = "market-regime-weekly-tradeable-registry-v2"

WEEKLY_KEYS = (
    "dxy",
    "us2y",
    "us10y",
    "us2s10s",
    "sp500",
    "nasdaq",
    "us_dividend",
    "vix",
    "bitcoin",
    "ethereum",
    "hype",
    "shanghai",
    "star50",
    "china_dividend",
    "nikkei",
    "kospi",
    "wti",
    "gold",
    "silver",
)
# Cash-market instruments (ETFs and listed equities) stay on daily/weekly
# context. Four-hour context is reserved for the continuous futures/perpetual
# instruments where that timeframe is part of the tradeable contract.
CONTEXT_4H_KEYS = ("bitcoin", "ethereum", "hype", "wti", "gold", "silver")
RATE_KEYS = ("us2y", "us10y", "us2s10s")
DISPLAY_NAMES = {
    "dxy": "美元 ETF（UUP）", "us2y": "美国国债 2Y", "us10y": "美国国债 10Y", "us2s10s": "美国国债 2s10s",
    "sp500": "标普 500 ETF（SPY）", "nasdaq": "纳斯达克 100 ETF（QQQ）", "us_dividend": "美股红利 ETF（SCHD）", "vix": "VIX", "bitcoin": "BTC 永续（Hyperliquid）", "ethereum": "ETH 永续（Hyperliquid）", "hype": "HYPE 永续（Hyperliquid）",
    "shanghai": "上证指数", "star50": "科创 50", "china_dividend": "上证红利", "nikkei": "Nikkei 225", "kospi": "KOSPI",
    "wti": "WTI 原油期货（CL=F）", "gold": "黄金期货（GC=F）", "silver": "白银期货（SI=F）",
}


class WeeklySourceHistoryError(ValueError):
    """The weekly source or timeframe aggregation contract failed closed."""


CANONICAL_REGISTRY: dict[str, dict[str, Any]] = {
    "dxy": {"canonical_symbol": "UUP", "series_kind": "price", "timezone": "America/New_York", "unit": "USD/share", "price_basis": "provider_unadjusted_trade_price", "instrument_type": "ETF", "venue": "Yahoo Finance", "anchor_hour": 0, "four_hour_bucket_timezone": "UTC", "four_hour_anchor_hour": 0, "four_hour_anchor_minute": 0},
    "us2y": {"canonical_symbol": "Treasury:2 Yr", "series_kind": "rate_level", "timezone": "America/New_York", "unit": "percent", "price_basis": "official_treasury_par_yield"},
    "us10y": {"canonical_symbol": "Treasury:10 Yr", "series_kind": "rate_level", "timezone": "America/New_York", "unit": "percent", "price_basis": "official_treasury_par_yield"},
    "us2s10s": {"canonical_symbol": "Treasury:10 Yr-Treasury:2 Yr", "series_kind": "spread", "timezone": "America/New_York", "unit": "basis points", "price_basis": "derived_same_date_official_treasury"},
    "sp500": {"canonical_symbol": "SPY", "series_kind": "price", "timezone": "America/New_York", "unit": "USD/share", "price_basis": "provider_unadjusted_trade_price", "instrument_type": "ETF", "venue": "NYSE Arca"},
    "nasdaq": {"canonical_symbol": "QQQ", "series_kind": "price", "timezone": "America/New_York", "unit": "USD/share", "price_basis": "provider_unadjusted_trade_price", "instrument_type": "ETF", "venue": "Nasdaq"},
    "us_dividend": {"canonical_symbol": "SCHD", "series_kind": "price", "timezone": "America/New_York", "unit": "USD/share", "price_basis": "provider_unadjusted_trade_price", "instrument_type": "ETF", "venue": "NYSE Arca"},
    "vix": {"canonical_symbol": "^VIX", "series_kind": "price", "timezone": "America/Chicago", "unit": "index points", "price_basis": "provider_unadjusted_index_level"},
    "bitcoin": {"canonical_symbol": "BTC", "series_kind": "price", "timezone": "UTC", "unit": "USD/coin", "price_basis": "provider_perpetual_futures", "instrument_type": "USDC 永续", "venue": "Hyperliquid", "anchor_hour": 0, "four_hour_bucket_timezone": "UTC", "four_hour_anchor_hour": 0, "four_hour_anchor_minute": 0},
    "ethereum": {"canonical_symbol": "ETH", "series_kind": "price", "timezone": "UTC", "unit": "USD/coin", "price_basis": "provider_perpetual_futures", "instrument_type": "USDC 永续", "venue": "Hyperliquid", "anchor_hour": 0, "four_hour_bucket_timezone": "UTC", "four_hour_anchor_hour": 0, "four_hour_anchor_minute": 0},
    "hype": {"canonical_symbol": "HYPE", "series_kind": "price", "timezone": "UTC", "unit": "USD/token", "price_basis": "provider_perpetual_futures", "instrument_type": "USDC 永续", "venue": "Hyperliquid", "anchor_hour": 0, "four_hour_bucket_timezone": "UTC", "four_hour_anchor_hour": 0, "four_hour_anchor_minute": 0},
    "shanghai": {"canonical_symbol": "000001.SH", "series_kind": "price", "timezone": "Asia/Shanghai", "unit": "index points", "price_basis": "provider_unadjusted_index_level"},
    "star50": {"canonical_symbol": "000688.SH", "series_kind": "price", "timezone": "Asia/Shanghai", "unit": "index points", "price_basis": "provider_unadjusted_index_level"},
    "china_dividend": {"canonical_symbol": "000015.SH", "series_kind": "price", "timezone": "Asia/Shanghai", "unit": "index points", "price_basis": "provider_unadjusted_index_level"},
    "nikkei": {"canonical_symbol": "^N225", "series_kind": "price", "timezone": "Asia/Tokyo", "unit": "index points", "price_basis": "provider_unadjusted_index_level"},
    "kospi": {"canonical_symbol": "^KS11", "series_kind": "price", "timezone": "Asia/Seoul", "unit": "index points", "price_basis": "provider_unadjusted_index_level"},
    "wti": {"canonical_symbol": "CL=F", "series_kind": "price", "timezone": "America/New_York", "unit": "USD/barrel", "price_basis": "provider_continuous_front_month_unadjusted", "instrument_type": "连续期货", "venue": "Yahoo Finance", "anchor_hour": 18, "four_hour_bucket_timezone": "UTC", "four_hour_anchor_hour": 0, "four_hour_anchor_minute": 0},
    "gold": {"canonical_symbol": "GC=F", "series_kind": "price", "timezone": "America/New_York", "unit": "USD/troy ounce", "price_basis": "provider_continuous_front_month_unadjusted", "instrument_type": "连续期货", "venue": "Yahoo Finance", "anchor_hour": 18, "four_hour_bucket_timezone": "UTC", "four_hour_anchor_hour": 0, "four_hour_anchor_minute": 0},
    "silver": {"canonical_symbol": "SI=F", "series_kind": "price", "timezone": "America/New_York", "unit": "USD/troy ounce", "price_basis": "provider_continuous_front_month_unadjusted", "instrument_type": "连续期货", "venue": "Yahoo Finance", "anchor_hour": 18, "four_hour_bucket_timezone": "UTC", "four_hour_anchor_hour": 0, "four_hour_anchor_minute": 0},
}


def _parse_date(value: Any) -> date:
    try:
        return date.fromisoformat(str(value))
    except (KeyError, TypeError, ValueError) as exc:
        raise WeeklySourceHistoryError("weekly_point_date_invalid") from exc


def _parse_timestamp(value: Any) -> datetime:
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value), timezone.utc)
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError, OverflowError) as exc:
        raise WeeklySourceHistoryError("four_hour_timestamp_invalid") from exc
    if parsed.tzinfo is None:
        raise WeeklySourceHistoryError("four_hour_timestamp_requires_timezone")
    return parsed.astimezone(timezone.utc)


def _week_start(week_end: date, weeks_back: int) -> date:
    return week_end - timedelta(days=week_end.weekday() + 7 * weeks_back)


def _validate_key(key: str) -> dict[str, Any]:
    if key not in CANONICAL_REGISTRY:
        raise WeeklySourceHistoryError(f"unknown_weekly_key:{key}")
    return CANONICAL_REGISTRY[key]


def _validate_metadata(series: Mapping[str, Any], registry: Mapping[str, Any], *, key: str) -> None:
    for field in ("canonical_symbol", "series_kind", "timezone", "unit", "price_basis"):
        supplied = series.get(field)
        if supplied is not None and str(supplied) != str(registry.get(field)):
            raise WeeklySourceHistoryError(f"weekly_registry_mismatch:{key}:{field}")


def _merge_source_identity(item: Mapping[str, Any], *extra_keys: str, fallback_run_id: Any = None) -> dict[str, Any]:
    identity = dict(item.get("source_identity") or {}) if isinstance(item.get("source_identity"), Mapping) else {}
    for key in extra_keys:
        value = item.get(key)
        if value is not None:
            identity[key] = value
    if "run_id" not in identity and fallback_run_id:
        identity["run_id"] = fallback_run_id
    return identity


def _live_as_of(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        if isinstance(value, datetime):
            parsed = value
        else:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise WeeklySourceHistoryError("live_as_of_invalid") from exc
    if parsed.tzinfo is None:
        raise WeeklySourceHistoryError("live_as_of_requires_timezone")
    return parsed.astimezone(timezone.utc)


def build_provisional_weekly_bar(
    points: list[Mapping[str, Any]],
    *,
    live_as_of: datetime,
    week_start: date | None = None,
    completed_week_end: date | None = None,
) -> dict[str, Any] | None:
    """Build an explicitly provisional current-week OHLC bar.

    This bar is a reader/chart context only. Completed-week aggregation and
    all historical features continue to use confirmed Friday bars.
    """

    as_of = _live_as_of(live_as_of)
    if as_of is None:
        raise WeeklySourceHistoryError("live_as_of_missing")
    start = week_start or (as_of.date() - timedelta(days=as_of.weekday()))
    selected: list[Mapping[str, Any]] = []
    for raw in points:
        if not isinstance(raw, Mapping):
            continue
        stamp_value = raw.get("timestamp") or raw.get("date")
        try:
            if isinstance(stamp_value, str) and len(stamp_value) == 10:
                stamp = datetime.combine(date.fromisoformat(stamp_value), time.min, tzinfo=timezone.utc)
            else:
                stamp = _parse_timestamp(stamp_value)
        except WeeklySourceHistoryError:
            continue
        if start <= stamp.date() <= as_of.date() and stamp <= as_of:
            selected.append(raw)
    if not selected:
        return None
    selected.sort(key=lambda row: str(row.get("timestamp") or row.get("date") or ""))
    if completed_week_end is not None:
        latest_value = selected[-1].get("timestamp") or selected[-1].get("date")
        latest_date = _parse_timestamp(latest_value).date() if isinstance(latest_value, str) and len(latest_value) > 10 else _parse_date(latest_value)
        if latest_date <= completed_week_end:
            return None
    try:
        opens = [float(row["open"]) for row in selected]
        highs = [float(row["high"]) for row in selected]
        lows = [float(row["low"]) for row in selected]
        closes = [float(row["close"]) for row in selected]
        volumes = [float(row.get("volume", 0) or 0) for row in selected]
    except (KeyError, TypeError, ValueError) as exc:
        raise WeeklySourceHistoryError("provisional_ohlc_invalid") from exc
    if not all(math.isfinite(value) for value in (*opens, *highs, *lows, *closes, *volumes)):
        raise WeeklySourceHistoryError("provisional_ohlc_non_finite")
    return {
        "date": start.isoformat(),
        "timestamp": start.isoformat(),
        "period_start": start.isoformat(),
        "as_of": as_of.isoformat().replace("+00:00", "Z"),
        "open": opens[0],
        "high": max(highs),
        "low": min(lows),
        "close": closes[-1],
        "volume": sum(volumes),
        "close_status": "provisional",
        "close_source": "latest_upstream_close",
        "is_partial": True,
    }


def aggregate_weekly_series(
    series: Mapping[str, Any],
    *,
    week_end: date,
    week_count: int = 156,
) -> dict[str, Any]:
    """Aggregate normalized daily rows into completed weekly bins."""

    if week_count <= 0:
        raise WeeklySourceHistoryError("weekly_count_invalid")
    if week_end.weekday() != 4:
        raise WeeklySourceHistoryError("week_end_must_be_friday")
    key = str(series.get("key") or "")
    registry = _validate_key(key)
    _validate_metadata(series, registry, key=key)
    kind = str(series.get("series_kind") or registry["series_kind"])
    if kind not in {"price", "rate_level", "spread"}:
        raise WeeklySourceHistoryError(f"weekly_series_kind_invalid:{key}")
    points = list(series.get("points") or [])
    by_date: dict[date, Mapping[str, Any]] = {}
    for raw in points:
        if not isinstance(raw, Mapping):
            raise WeeklySourceHistoryError(f"weekly_point_invalid:{key}")
        session = _parse_date(raw.get("date"))
        if session > week_end or session.weekday() >= 5:
            continue
        target_iso = week_end.isocalendar()
        session_iso = session.isocalendar()
        if week_end >= date.today() and (session_iso.year, session_iso.week) == (target_iso.year, target_iso.week):
            continue
        if session in by_date:
            raise WeeklySourceHistoryError(f"weekly_duplicate_session:{key}:{session.isoformat()}")
        by_date[session] = raw

    output: list[dict[str, Any]] = []
    missing: list[str] = []
    for weeks_back in range(week_count - 1, -1, -1):
        start = _week_start(week_end, weeks_back)
        end = start + timedelta(days=4)
        rows = [raw for session, raw in sorted(by_date.items()) if start <= session <= end]
        if not rows:
            missing.append(end.isoformat())
            continue
        last_session = max(_parse_date(raw.get("date")) for raw in rows)
        if kind in {"rate_level", "spread"}:
            if any(raw.get("value") is None for raw in rows):
                raise WeeklySourceHistoryError(f"weekly_rate_value_missing:{key}")
            output.append({"date": last_session.isoformat(), "value": float(rows[-1]["value"])})
            continue
        _ = [_validated_ohlcv(raw, f"weekly:{key}") for raw in rows]
        item = {
            "date": last_session.isoformat(),
            "open": float(rows[0]["open"]),
            "high": max(float(raw["high"]) for raw in rows),
            "low": min(float(raw["low"]) for raw in rows),
            "close": float(rows[-1]["close"]),
        }
        if any("volume" in raw for raw in rows):
            item["volume"] = sum(float(raw.get("volume", 0)) for raw in rows)
        output.append(item)
    status = "complete" if not missing else ("short_history" if output else "unavailable")
    display_points = [dict(raw) for session, raw in sorted(by_date.items()) if session <= week_end]
    return {
        "key": key,
        "canonical_symbol": registry["canonical_symbol"],
        "series_kind": kind,
        "timezone": str(series.get("timezone") or registry["timezone"]),
        "unit": str(series.get("unit") or registry["unit"]),
        "price_basis": str(series.get("price_basis") or registry["price_basis"]),
        "status": status,
        "week_end": week_end.isoformat(),
        "required_weekly_bins": week_count,
        "weekly_bin_count": len(output),
        "missing_week_ends": missing,
        "points": output,
        "daily_points": display_points,
        "actual_first_session": output[0]["date"] if output else None,
        "actual_last_session": output[-1]["date"] if output else None,
        "quality": str(series.get("quality") or "unknown"),
        "data_kind": str(series.get("data_kind") or "fixture"),
        "daily_status": series.get("daily_status"),
        "source_identity": series.get("source_identity"),
        "reject_reason": series.get("reject_reason") or series.get("daily_reject_reason"),
        "access_issues": list(series.get("access_issues") or series.get("daily_access_issues") or []),
        "rights": series.get("rights"),
    }


def aggregate_4h_series(
    series: Mapping[str, Any],
    *,
    cutoff_at: datetime,
) -> dict[str, Any]:
    """Aggregate complete hourly rows into fixed, session-anchored 4H bars."""

    key = str(series.get("key") or "")
    registry = _validate_key(key)
    if key not in CONTEXT_4H_KEYS:
        raise WeeklySourceHistoryError(f"context_4h_not_allowed:{key}")
    _validate_metadata(series, registry, key=key)
    if cutoff_at.tzinfo is None:
        raise WeeklySourceHistoryError("four_hour_cutoff_requires_timezone")
    try:
        zone = ZoneInfo(str(series.get("timezone") or registry["timezone"]))
        anchor_hour = int(series.get("anchor_hour", registry.get("anchor_hour", 0)))
    except (KeyError, TypeError, ValueError) as exc:
        raise WeeklySourceHistoryError("four_hour_anchor_invalid") from exc
    if not 0 <= anchor_hour < 24:
        raise WeeklySourceHistoryError("four_hour_anchor_invalid")
    cutoff_utc = cutoff_at.astimezone(timezone.utc)
    grouped: dict[datetime, list[tuple[datetime, Mapping[str, Any]]]] = {}
    for raw in series.get("points") or []:
        if not isinstance(raw, Mapping):
            raise WeeklySourceHistoryError("four_hour_raw_row_invalid")
        stamp = _parse_timestamp(raw.get("timestamp"))
        if stamp + timedelta(hours=1) > cutoff_utc:
            continue
        if stamp.minute != 0 or stamp.second != 0 or stamp.microsecond != 0:
            raise WeeklySourceHistoryError("four_hour_raw_timestamp_not_on_hour")
        local = stamp.astimezone(zone)
        session_date = local.date() if local.hour >= anchor_hour else local.date() - timedelta(days=1)
        anchor = datetime.combine(session_date, time(anchor_hour), tzinfo=zone)
        elapsed_hours = int((local - anchor).total_seconds() // 3600)
        bucket = anchor + timedelta(hours=(elapsed_hours // 4) * 4)
        grouped.setdefault(bucket, []).append((stamp, raw))

    output: list[dict[str, Any]] = []
    dropped: list[str] = []
    for bucket, rows in sorted(grouped.items()):
        rows.sort(key=lambda item: item[0])
        stamps = [stamp for stamp, _ in rows]
        if len(rows) != 4 or any(right - left != timedelta(hours=1) for left, right in zip(stamps, stamps[1:])):
            dropped.append(bucket.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"))
            continue
        values = [raw for _, raw in rows]
        validated = [_validated_ohlcv(raw, f"four_hour:{key}") for raw in values]
        item = {
            "start_at": bucket.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "duration_hours": 4,
            "open": validated[0][0],
            "high": max(item[1] for item in validated),
            "low": min(item[2] for item in validated),
            "close": validated[-1][3],
        }
        if any("volume" in raw for raw in values):
            item["volume"] = sum(float(raw.get("volume", 0)) for raw in values)
        output.append(item)
    return {
        "key": key,
        "canonical_symbol": registry["canonical_symbol"],
        "timezone": zone.key,
        "anchor_hour": anchor_hour,
        "status": "complete" if output else "unavailable",
        "cutoff_at": cutoff_utc.isoformat().replace("+00:00", "Z"),
        "points": output,
        "dropped_incomplete_buckets": dropped,
        "source_identity": series.get("source_identity"),
        "quality": series.get("quality"),
        "data_kind": series.get("data_kind"),
        "reject_reason": series.get("reject_reason"),
        "access_issues": list(series.get("access_issues") or []),
    }


def _validated_ohlcv(raw: Mapping[str, Any], context: str) -> tuple[float, float, float, float, float]:
    try:
        values = (
            float(raw["open"]),
            float(raw["high"]),
            float(raw["low"]),
            float(raw["close"]),
            float(raw.get("volume", 0)),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise WeeklySourceHistoryError(f"{context}_ohlc_invalid") from exc
    if not all(math.isfinite(value) for value in values):
        raise WeeklySourceHistoryError(f"{context}_ohlc_non_finite")
    open_value, high_value, low_value, close_value, volume = values
    if high_value < max(open_value, close_value) or low_value > min(open_value, close_value):
        raise WeeklySourceHistoryError(f"{context}_ohlc_invariant")
    if volume < 0:
        raise WeeklySourceHistoryError(f"{context}_volume_negative")
    return values


def build_public_4h_context(
    series: Mapping[str, Any],
    *,
    cutoff_at: datetime,
) -> dict[str, Any]:
    """Pass through public 4H bars after validating their typed transform.

    ``aggregate_4h_series`` is intentionally reserved for raw hourly authority
    inputs.  A datafeed response already labelled ``4h`` must never be fed
    through that hourly bucketizer a second time.
    """

    key = str(series.get("key") or "")
    registry = _validate_key(key)
    if key not in CONTEXT_4H_KEYS:
        raise WeeklySourceHistoryError(f"context_4h_not_allowed:{key}")
    if cutoff_at.tzinfo is None:
        raise WeeklySourceHistoryError("four_hour_cutoff_requires_timezone")
    raw_timeframe = str(series.get("raw_timeframe") or "")
    origin = str(series.get("timeframe_origin") or "")
    aggregation = series.get("aggregation")
    if raw_timeframe not in {"1h", "4h"} or origin not in {"native", "aggregated"} or not isinstance(aggregation, Mapping):
        raise WeeklySourceHistoryError("four_hour_transform_metadata_invalid")
    if raw_timeframe == "4h":
        if (
            origin != "native"
            or aggregation.get("kind") != "none"
            or aggregation.get("rule") != "native_passthrough"
        ):
            raise WeeklySourceHistoryError("four_hour_native_metadata_invalid")
    elif (
        origin != "aggregated"
        or aggregation.get("kind") != "ohlc_resample"
        or aggregation.get("rule") != "fixed_4h"
        or aggregation.get("input_timeframe") != "1h"
    ):
        raise WeeklySourceHistoryError("four_hour_aggregation_metadata_invalid")

    expected_zone_name = str(registry.get("four_hour_bucket_timezone") or registry["timezone"])
    expected_anchor_hour = int(registry.get("four_hour_anchor_hour", registry.get("anchor_hour", 0)))
    expected_anchor_minute = int(registry.get("four_hour_anchor_minute", 0))
    if raw_timeframe == "1h" and any(
        field not in aggregation for field in ("bucket_timezone", "anchor_hour", "anchor_minute")
    ):
        raise WeeklySourceHistoryError("four_hour_anchor_metadata_missing")
    try:
        anchor_hour = int(aggregation.get("anchor_hour", expected_anchor_hour))
        anchor_minute = int(aggregation.get("anchor_minute", expected_anchor_minute))
        bucket_zone = ZoneInfo(str(aggregation.get("bucket_timezone") or expected_zone_name))
    except (KeyError, TypeError, ValueError) as exc:
        raise WeeklySourceHistoryError("four_hour_anchor_invalid") from exc
    if not 0 <= anchor_hour < 24 or not 0 <= anchor_minute < 60:
        raise WeeklySourceHistoryError("four_hour_anchor_invalid")
    if (
        bucket_zone.key != expected_zone_name
        or anchor_hour != expected_anchor_hour
        or anchor_minute != expected_anchor_minute
    ):
        raise WeeklySourceHistoryError("four_hour_registry_anchor_mismatch")

    cutoff_utc = cutoff_at.astimezone(timezone.utc)
    points: list[dict[str, Any]] = []
    previous: datetime | None = None
    for raw in series.get("points") or []:
        if not isinstance(raw, Mapping):
            raise WeeklySourceHistoryError("four_hour_public_bar_invalid")
        stamp = _parse_timestamp(raw.get("timestamp") or raw.get("start_at"))
        if stamp + timedelta(hours=4) > cutoff_utc:
            continue
        local = stamp.astimezone(bucket_zone)
        if local.minute != anchor_minute or (local.hour - anchor_hour) % 4 != 0:
            raise WeeklySourceHistoryError("four_hour_timestamp_not_on_anchor")
        if previous is not None and stamp <= previous:
            raise WeeklySourceHistoryError("four_hour_public_bars_not_strictly_ordered")
        previous = stamp
        try:
            open_value = float(raw["open"])
            high_value = float(raw["high"])
            low_value = float(raw["low"])
            close_value = float(raw["close"])
            volume = float(raw.get("volume", 0))
        except (KeyError, TypeError, ValueError) as exc:
            raise WeeklySourceHistoryError("four_hour_public_ohlc_invalid") from exc
        if high_value < max(open_value, close_value) or low_value > min(open_value, close_value):
            raise WeeklySourceHistoryError("four_hour_public_ohlc_invariant")
        if volume < 0:
            raise WeeklySourceHistoryError("four_hour_public_volume_negative")
        if not all(math.isfinite(value) for value in (open_value, high_value, low_value, close_value, volume)):
            raise WeeklySourceHistoryError("four_hour_public_ohlc_non_finite")
        points.append(
            {
                "start_at": stamp.isoformat().replace("+00:00", "Z"),
                "duration_hours": 4,
                "open": open_value,
                "high": high_value,
                "low": low_value,
                "close": close_value,
                "volume": volume,
            }
        )

    dropped_raw = aggregation.get("dropped_incomplete_buckets")
    if dropped_raw is None:
        dropped_buckets: list[str] = []
        dropped_count = 0
    elif isinstance(dropped_raw, int) and not isinstance(dropped_raw, bool) and dropped_raw >= 0:
        # The canonical datafeed reports a count; older local aggregators
        # reported the individual bucket timestamps. Preserve both forms
        # without trying to manufacture timestamps from a count.
        dropped_buckets = []
        dropped_count = dropped_raw
    elif isinstance(dropped_raw, list) and all(isinstance(item, str) and item.strip() for item in dropped_raw):
        dropped_buckets = list(dropped_raw)
        dropped_count = len(dropped_buckets)
    else:
        raise WeeklySourceHistoryError("four_hour_drop_metadata_invalid")

    return {
        "key": key,
        "canonical_symbol": registry["canonical_symbol"],
        "timezone": str(series.get("timezone") or registry["timezone"]),
        "anchor_hour": aggregation.get("anchor_hour", registry.get("anchor_hour", 0)),
        "anchor_minute": aggregation.get("anchor_minute", 0),
        "status": "complete" if points else "unavailable",
        "cutoff_at": cutoff_utc.isoformat().replace("+00:00", "Z"),
        "points": points,
        "dropped_incomplete_buckets": dropped_buckets,
        "dropped_incomplete_bucket_count": dropped_count,
        "source_identity": series.get("source_identity"),
        "quality": series.get("quality"),
        "data_kind": series.get("data_kind"),
        "reject_reason": series.get("reject_reason"),
        "access_issues": list(series.get("access_issues") or []),
        "raw_timeframe": raw_timeframe,
        "timeframe_origin": origin,
        "aggregation": dict(aggregation),
    }


def _unavailable_4h_context(
    series: Mapping[str, Any],
    *,
    cutoff_at: datetime,
    reason: str,
) -> dict[str, Any]:
    key = str(series.get("key") or "")
    registry = _validate_key(key)
    cutoff_utc = cutoff_at.astimezone(timezone.utc)
    return {
        "key": key,
        "canonical_symbol": registry["canonical_symbol"],
        "timezone": str(series.get("timezone") or registry["timezone"]),
        "anchor_hour": registry.get("four_hour_anchor_hour", registry.get("anchor_hour", 0)),
        "anchor_minute": registry.get("four_hour_anchor_minute", 0),
        "status": "unavailable",
        "cutoff_at": cutoff_utc.isoformat().replace("+00:00", "Z"),
        "points": [],
        "dropped_incomplete_buckets": [],
        "source_identity": series.get("source_identity"),
        "quality": "unavailable",
        "data_kind": series.get("data_kind"),
        "raw_timeframe": series.get("raw_timeframe"),
        "timeframe_origin": series.get("timeframe_origin"),
        "aggregation": dict(series.get("aggregation") or {}),
        "reject_reason": reason,
        "access_issues": [reason],
    }


def build_weekly_source_snapshot(
    series_by_key: Mapping[str, Mapping[str, Any]],
    *,
    week_end: date,
    cutoff_at: datetime | None = None,
    week_count: int = 156,
    require_all: bool = False,
    weekly_points_by_key: Mapping[str, list[Mapping[str, Any]] | None] | None = None,
    live_as_of: datetime | None = None,
) -> dict[str, Any]:
    """Build the typed timeframe snapshot consumed by later compiler stories."""

    unknown = sorted(set(series_by_key) - set(WEEKLY_KEYS))
    if unknown:
        raise WeeklySourceHistoryError(f"unknown_weekly_key:{unknown[0]}")
    missing = [key for key in WEEKLY_KEYS if key not in series_by_key]
    if require_all and missing:
        raise WeeklySourceHistoryError(f"weekly_series_missing:{missing[0]}")
    result: dict[str, Any] = {}
    for key, source in series_by_key.items():
        enriched = {**source, "key": key}
        try:
            weekly = aggregate_weekly_series(enriched, week_end=week_end, week_count=week_count)
        except (KeyError, TypeError, ValueError, WeeklySourceHistoryError) as error:
            registry = _validate_key(key)
            weekly = aggregate_weekly_series(
                {
                    "key": key,
                    "series_kind": registry["series_kind"],
                    "timezone": registry["timezone"],
                    "unit": registry["unit"],
                    "price_basis": registry["price_basis"],
                    "points": [],
                    "data_kind": source.get("data_kind"),
                    "source_identity": source.get("source_identity"),
                },
                week_end=week_end,
                week_count=week_count,
            )
            weekly["reject_reason"] = str(error)
            weekly["access_issues"] = [str(error)]
        if weekly_points_by_key is not None and key in weekly_points_by_key:
            external_points = weekly_points_by_key[key]
            if not external_points:
                weekly.update({"status": "unavailable", "points": [], "weekly_bin_count": 0, "missing_week_ends": [], "weekly_gap_count": 0, "weekly_source_identity": enriched.get("weekly_source_identity")})
                weekly.update({
                    "reject_reason": enriched.get("weekly_reject_reason"),
                    "access_issues": list(enriched.get("weekly_access_issues") or []),
                })
            else:
                external = aggregate_weekly_series(
                    {**enriched, "points": external_points},
                    week_end=week_end,
                    week_count=week_count,
                )
                weekly.update({
                    # The canonical datafeed's ready 1W response is already
                    # exchange-calendar aware. A full-market holiday week is
                    # not a missing provider response, so preserve the
                    # authoritative ready status while retaining the gap
                    # metadata for audit/display.
                    "status": (
                        "unavailable"
                        if not external["points"]
                        else "complete" if enriched.get("weekly_status") == "ready" else external["status"]
                    ),
                    "points": external["points"],
                    "weekly_bin_count": external["weekly_bin_count"],
                    "missing_week_ends": external["missing_week_ends"],
                    "weekly_gap_count": len(external["missing_week_ends"]),
                    "actual_first_session": external["actual_first_session"],
                    "actual_last_session": external["actual_last_session"],
                    "weekly_source_identity": enriched.get("weekly_source_identity"),
                    "weekly_quality": enriched.get("weekly_quality", enriched.get("quality")),
                    "weekly_quality_flags": enriched.get("weekly_quality_flags", []),
                    "weekly_fresh": enriched.get("weekly_fresh"),
                    "weekly_data_kind": enriched.get("weekly_data_kind", enriched.get("data_kind")),
                })
        if live_as_of is not None and enriched.get("partial_points"):
            partial = build_provisional_weekly_bar(
                list(enriched.get("partial_points") or []),
                live_as_of=live_as_of,
                completed_week_end=week_end,
            )
            if partial is not None:
                weekly["current_week"] = partial
        if key in CONTEXT_4H_KEYS and enriched.get("hourly_points") is not None:
            cutoff = cutoff_at or datetime.combine(week_end, time(23, 59, 59), tzinfo=timezone.utc)
            hourly_input = {
                **enriched,
                "points": enriched.get("hourly_points"),
                "source_identity": enriched.get("hourly_source_identity") or enriched.get("source_identity"),
                "quality": enriched.get("hourly_quality", enriched.get("quality")),
                "data_kind": enriched.get("hourly_data_kind", enriched.get("data_kind")),
                "reject_reason": enriched.get("hourly_reject_reason"),
                "access_issues": list(enriched.get("hourly_access_issues") or []),
            }
            try:
                if enriched.get("hourly_status") == "ready" and enriched.get("hourly_raw_timeframe") is None:
                    raise WeeklySourceHistoryError("four_hour_transform_metadata_missing")
                if enriched.get("hourly_raw_timeframe") is not None:
                    weekly["context_4h"] = build_public_4h_context(
                        {
                            **hourly_input,
                            "raw_timeframe": enriched.get("hourly_raw_timeframe"),
                            "timeframe_origin": enriched.get("hourly_timeframe_origin"),
                            "aggregation": enriched.get("hourly_aggregation"),
                        },
                        cutoff_at=cutoff,
                    )
                else:
                    weekly["context_4h"] = aggregate_4h_series(
                        hourly_input,
                        cutoff_at=cutoff,
                    )
            except (KeyError, WeeklySourceHistoryError) as error:
                weekly["context_4h"] = _unavailable_4h_context(
                    hourly_input,
                    cutoff_at=cutoff,
                    reason=str(error),
                )
        result[key] = weekly
    statuses = [item["status"] for item in result.values()]
    daily_incomplete = any(
        item.get("daily_status") not in {None, "ready", "complete", "short_history"}
        for item in result.values()
    )
    # Every declared 4H context asset must have an explicit context envelope.
    # A missing envelope is an unavailable source, not an implicit success.
    context_incomplete = any(
        not isinstance(result.get(key, {}).get("context_4h"), Mapping)
        or result[key]["context_4h"].get("status") != "complete"
        for key in CONTEXT_4H_KEYS
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "registry_version": REGISTRY_VERSION,
        "week_end": week_end.isoformat(),
        "cutoff_at": (cutoff_at or datetime.combine(week_end, time(23, 59, 59), tzinfo=timezone.utc)).astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "live_as_of": live_as_of.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if live_as_of else None,
        "status": "complete" if not missing and all(status == "complete" for status in statuses) and not daily_incomplete and not context_incomplete else "partial",
        "missing_series": missing,
        "series": result,
    }


def build_weekly_source_snapshot_from_authorities(
    *,
    daily_snapshot: Mapping[str, Any],
    macro_snapshot: Mapping[str, Any],
    bitcoin_artifact: Mapping[str, Any],
    week_end: date,
    cutoff_at: datetime | None = None,
    week_count: int = 156,
    require_all: bool = True,
    hourly_points_by_key: Mapping[str, list[Mapping[str, Any]]] | None = None,
    hourly_source_identity_by_key: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Project existing validated authorities into the Weekly source seam."""

    series: dict[str, dict[str, Any]] = {}
    for item in daily_snapshot.get("instruments") or []:
        instrument = item.get("instrument") if isinstance(item, Mapping) else None
        if not isinstance(instrument, Mapping):
            raise WeeklySourceHistoryError("daily_authority_instrument_missing")
        key = str(instrument.get("key") or "")
        if key not in WEEKLY_KEYS:
            raise WeeklySourceHistoryError(f"unknown_weekly_key:{key}")
        series[key] = {
            "series_kind": "price",
            "timezone": instrument.get("exchange_timezone"),
            "unit": instrument.get("unit"),
            "price_basis": instrument.get("price_basis"),
            "quality": item.get("quality"),
            "data_kind": item.get("data_kind", daily_snapshot.get("data_kind", "real")),
            "source_identity": _merge_source_identity(item, "run_id", "normalized_artifact", fallback_run_id=daily_snapshot.get("run_id")),
            "rights": {
                "publication_eligible": item.get("publication_eligible", False),
            },
            "points": list(item.get("bars") or []),
        }
    for factor in macro_snapshot.get("factors") or []:
        spec = factor.get("factor") if isinstance(factor, Mapping) else None
        if not isinstance(spec, Mapping):
            raise WeeklySourceHistoryError("macro_authority_factor_missing")
        key = str(spec.get("key") or "")
        if key not in RATE_KEYS and key != "dxy":
            continue
        points = factor.get("bars") if key == "dxy" else factor.get("observations")
        if key == "dxy":
            normalized = list(points or [])
        else:
            normalized = [
                {"date": row.get("date"), "value": row.get("value")}
                for row in points or []
            ]
        level_unit = "index points" if key == "dxy" else ("basis points" if key == "us2s10s" else factor.get("level_unit", "percent"))
        price_basis = (
            "provider_unadjusted_index_level"
            if key == "dxy"
            else ("derived_same_date_official_treasury" if key == "us2s10s" else "official_treasury_par_yield")
        )
        series[key] = {
            "series_kind": "price" if key == "dxy" else ("spread" if key == "us2s10s" else "rate_level"),
            "timezone": "America/New_York",
            "unit": level_unit,
            "price_basis": price_basis,
            "quality": factor.get("quality"),
            "data_kind": factor.get("data_kind", macro_snapshot.get("data_kind", "real")),
            "source_identity": _merge_source_identity(factor, "run_id", "factor_id", "artifact", fallback_run_id=macro_snapshot.get("run_id")),
            "rights": {
                "publication_eligible": factor.get("publication_eligible", False),
            },
            "points": normalized,
        }
    if isinstance(bitcoin_artifact, Mapping):
        series["bitcoin"] = {
            "series_kind": "price",
            "timezone": "UTC",
            "unit": "USD/coin",
            "price_basis": "provider_unadjusted_trade_price",
            "quality": bitcoin_artifact.get("quality"),
            "data_kind": bitcoin_artifact.get("data_kind", "real"),
            "source_identity": _merge_source_identity(bitcoin_artifact, "bitcoin_id"),
            "rights": {
                "publication_eligible": bitcoin_artifact.get("publication_eligible", False),
            },
            "points": list(bitcoin_artifact.get("bars") or []),
        }
    snapshot = build_weekly_source_snapshot(
        series,
        week_end=week_end,
        cutoff_at=cutoff_at,
        week_count=week_count,
        require_all=require_all,
    )
    if hourly_points_by_key:
        # The source authority owns the raw hourly capture; aggregation remains
        # in the same deterministic path as other 4H context bars.
        for key, points in hourly_points_by_key.items():
            if key not in snapshot.get("series", {}) or key not in CONTEXT_4H_KEYS:
                continue
            enriched = {
                **series[key],
                "key": key,
                "points": list(points),
            }
            snapshot["series"][key]["context_4h"] = aggregate_4h_series(
                enriched,
                cutoff_at=cutoff_at or datetime.combine(week_end, time(23, 59, 59), tzinfo=timezone.utc),
            )
            hourly_identity = (hourly_source_identity_by_key or {}).get(key)
            if isinstance(hourly_identity, Mapping) and hourly_identity:
                snapshot["series"][key]["context_4h"]["source_identity"] = dict(hourly_identity)
    snapshot["authority_inputs"] = {
        "daily_run_id": daily_snapshot.get("run_id"),
        "macro_run_id": macro_snapshot.get("run_id"),
        "bitcoin_id": bitcoin_artifact.get("bitcoin_id"),
    }
    return snapshot


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (_canonical_json(value) + "\n").encode("utf-8")


def _digest(value: Mapping[str, Any]) -> str:
    import hashlib

    return hashlib.sha256(_json_bytes(value)).hexdigest()


def _write_immutable(path: Path, encoded: bytes) -> str:
    import hashlib

    path.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(encoded).hexdigest()
    if path.exists():
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise WeeklySourceHistoryError("immutable_artifact_conflict")
        return digest
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return digest


def _write_atomic(path: Path, encoded: bytes) -> None:
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


class WeeklySourceHistoryStore:
    """Immutable Weekly source snapshot store; no network or LLM side effects."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).expanduser().resolve()

    def publish(self, snapshot: Mapping[str, Any]) -> dict[str, Any]:
        if snapshot.get("schema_version") != SCHEMA_VERSION:
            raise WeeklySourceHistoryError("weekly_snapshot_schema_invalid")
        identity_core = {
            key: snapshot.get(key)
            for key in ("schema_version", "registry_version", "week_end", "cutoff_at", "live_as_of", "status", "missing_series", "series", "data_kind", "quality", "authority_inputs", "source_policy")
        }
        snapshot_id = f"market-regime-weekly-source:{_digest(identity_core)}"
        artifact = {"snapshot_id": snapshot_id, "identity_core": identity_core, **identity_core}
        digest = snapshot_id.split(":", 1)[1]
        artifact_path = f"artifacts/{digest}.json"
        receipt_path = f"receipts/{digest}.json"
        artifact_ref = {"path": artifact_path, "sha256": _write_immutable(self.root / artifact_path, _json_bytes(artifact))}
        receipt = {
            "schema_version": SCHEMA_VERSION,
            "event": "completed",
            "snapshot_id": snapshot_id,
            "artifact": artifact_ref,
        }
        receipt_ref = {"path": receipt_path, "sha256": _write_immutable(self.root / receipt_path, _json_bytes(receipt))}
        state = {
            "schema_version": SCHEMA_VERSION,
            "snapshot_id": snapshot_id,
            "artifact": artifact_ref,
            "receipt": receipt_ref,
        }
        _write_atomic(self.root / "latest.json", _json_bytes(state))
        self.latest()
        return state

    def load(self, snapshot_id: str) -> dict[str, Any]:
        """Verify and load one immutable source artifact by its canonical ID."""

        prefix = "market-regime-weekly-source:"
        if not isinstance(snapshot_id, str) or not snapshot_id.startswith(prefix):
            raise WeeklySourceHistoryError("weekly_identity_invalid")
        digest = snapshot_id.removeprefix(prefix)
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise WeeklySourceHistoryError("weekly_identity_invalid")
        artifact_relative = f"artifacts/{digest}.json"
        receipt_relative = f"receipts/{digest}.json"
        artifact_path = (self.root / artifact_relative).resolve()
        receipt_path = (self.root / receipt_relative).resolve()
        if self.root not in artifact_path.parents or self.root not in receipt_path.parents:
            raise WeeklySourceHistoryError("weekly_reference_path_escape")
        try:
            artifact_bytes = artifact_path.read_bytes()
            receipt_bytes = receipt_path.read_bytes()
        except FileNotFoundError as exc:
            raise WeeklySourceHistoryError("weekly_artifact_unavailable") from exc
        import hashlib
        try:
            artifact = json.loads(artifact_bytes)
            receipt = json.loads(receipt_bytes)
        except json.JSONDecodeError as exc:
            raise WeeklySourceHistoryError("weekly_artifact_json_invalid") from exc
        if not isinstance(artifact, dict) or artifact.get("snapshot_id") != snapshot_id:
            raise WeeklySourceHistoryError("weekly_artifact_identity_invalid")
        identity_core = artifact.get("identity_core")
        if not isinstance(identity_core, Mapping) or snapshot_id != f"{prefix}{_digest(identity_core)}":
            raise WeeklySourceHistoryError("weekly_identity_mismatch")
        artifact_ref = receipt.get("artifact") if isinstance(receipt, Mapping) else None
        expected_receipt = {"schema_version": SCHEMA_VERSION, "event": "completed", "snapshot_id": snapshot_id, "artifact": artifact_ref}
        if receipt != expected_receipt or not isinstance(artifact_ref, Mapping):
            raise WeeklySourceHistoryError("weekly_receipt_identity_mismatch")
        if receipt_bytes != _json_bytes(receipt):
            raise WeeklySourceHistoryError("weekly_receipt_encoding_mismatch")
        if artifact_ref.get("path") != artifact_relative or artifact_ref.get("sha256") != hashlib.sha256(artifact_bytes).hexdigest():
            raise WeeklySourceHistoryError("weekly_receipt_artifact_mismatch")
        return {key: artifact.get(key) for key in ("snapshot_id", "week_end", "cutoff_at", "status", "missing_series", "series", "data_kind", "quality", "authority_inputs", "source_policy")}

    def latest(self) -> dict[str, Any]:
        try:
            state = json.loads((self.root / "latest.json").read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            raise WeeklySourceHistoryError("weekly_latest_unavailable") from exc
        required = {"schema_version", "snapshot_id", "artifact", "receipt"}
        if not isinstance(state, dict) or set(state) != required or state["schema_version"] != SCHEMA_VERSION:
            raise WeeklySourceHistoryError("weekly_latest_invalid")
        snapshot_id = str(state["snapshot_id"] or "")
        digest = snapshot_id.removeprefix("market-regime-weekly-source:")
        if len(digest) != 64:
            raise WeeklySourceHistoryError("weekly_identity_invalid")
        artifact_ref = state["artifact"]
        receipt_ref = state["receipt"]
        if not isinstance(artifact_ref, dict) or not isinstance(receipt_ref, dict):
            raise WeeklySourceHistoryError("weekly_reference_invalid")
        artifact_relative = str(artifact_ref.get("path") or "")
        receipt_relative = str(receipt_ref.get("path") or "")
        artifact_path = (self.root / artifact_relative).resolve()
        receipt_path = (self.root / receipt_relative).resolve()
        if self.root not in artifact_path.parents or self.root not in receipt_path.parents:
            raise WeeklySourceHistoryError("weekly_reference_path_escape")
        if artifact_relative != f"artifacts/{digest}.json" or receipt_relative != f"receipts/{digest}.json":
            raise WeeklySourceHistoryError("weekly_reference_path_invalid")
        try:
            artifact_bytes = artifact_path.read_bytes()
            receipt_bytes = receipt_path.read_bytes()
        except FileNotFoundError as exc:
            raise WeeklySourceHistoryError("weekly_artifact_unavailable") from exc
        import hashlib

        if hashlib.sha256(artifact_bytes).hexdigest() != artifact_ref.get("sha256"):
            raise WeeklySourceHistoryError("artifact_hash_mismatch")
        if hashlib.sha256(receipt_bytes).hexdigest() != receipt_ref.get("sha256"):
            raise WeeklySourceHistoryError("receipt_hash_mismatch")
        try:
            artifact = json.loads(artifact_bytes)
            receipt = json.loads(receipt_bytes)
        except json.JSONDecodeError as exc:
            raise WeeklySourceHistoryError("weekly_artifact_json_invalid") from exc
        if not isinstance(artifact, dict) or artifact.get("snapshot_id") != snapshot_id:
            raise WeeklySourceHistoryError("weekly_artifact_identity_invalid")
        if artifact.get("identity_core") is not None and snapshot_id != f"market-regime-weekly-source:{_digest(artifact['identity_core'])}":
            raise WeeklySourceHistoryError("weekly_identity_mismatch")
        if receipt != {"schema_version": SCHEMA_VERSION, "event": "completed", "snapshot_id": snapshot_id, "artifact": artifact_ref}:
            raise WeeklySourceHistoryError("weekly_receipt_identity_mismatch")
        return {**state, **{key: artifact.get(key) for key in ("week_end", "cutoff_at", "status", "missing_series", "series", "data_kind", "quality", "authority_inputs", "source_policy")}}
