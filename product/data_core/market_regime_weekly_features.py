"""Deterministic EMA/MACD and chart-axis context for Weekly K-line cards."""

from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
import math
from typing import Any, Mapping


FEATURE_SCHEMA_VERSION = "market-regime-weekly-features-v1"
FEATURE_PARAMETERS = {"ema_span": 50, "macd_fast": 12, "macd_slow": 26, "macd_signal": 9}


class WeeklyFeatureError(ValueError):
    """A timeframe feature projection failed closed."""


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _timestamp(value: Any) -> datetime:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), timezone.utc)
    text = str(value or "")
    if "T" not in text:
        return datetime.combine(date.fromisoformat(text), datetime.min.time(), tzinfo=timezone.utc)
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise WeeklyFeatureError("feature_timestamp_requires_timezone")
    return parsed.astimezone(timezone.utc)


def _label(point: Mapping[str, Any]) -> str:
    return str(point.get("date") or point.get("start_at") or point.get("timestamp") or "")


def _number(value: Any, *, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise WeeklyFeatureError(f"feature_number_invalid:{field}") from exc
    if not math.isfinite(number):
        raise WeeklyFeatureError(f"feature_number_invalid:{field}")
    return number


def _ema(values: list[float], span: int) -> list[float | None]:
    result: list[float | None] = [None] * len(values)
    if len(values) < span:
        return result
    seed = sum(values[:span]) / span
    result[span - 1] = seed
    alpha = 2.0 / (span + 1)
    for index in range(span, len(values)):
        previous = result[index - 1]
        assert previous is not None
        result[index] = (values[index] - previous) * alpha + previous
    return result


def _round(value: float | None) -> float | None:
    return None if value is None else round(float(value), 8)


def _axis_labels(points: list[Mapping[str, Any]], values: list[float]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not points or not values:
        return [], []
    indices = [0, (len(points) - 1) // 4, (len(points) - 1) // 2, ((len(points) - 1) * 3) // 4, len(points) - 1]
    x_labels: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index in indices:
        label = _label(points[index])
        if not label or label in seen:
            continue
        seen.add(label)
        x_labels.append({"index": index, "label": label})
    low, high = min(values), max(values)
    if low == high:
        ticks = [low]
    else:
        ticks = [low + (high - low) * index / 4 for index in range(5)]
    y_labels = [{"value": _round(value), "label": f"{value:.4f}".rstrip("0").rstrip(".")} for value in ticks]
    return x_labels, y_labels


def build_timeframe_features(
    series: Mapping[str, Any],
    *,
    timeframe: str,
    cutoff_at: datetime | None = None,
) -> dict[str, Any]:
    """Project one immutable timeframe into chart-ready technical context."""

    key = str(series.get("key") or "")
    if not key or timeframe not in {"weekly", "daily", "four_hour"}:
        raise WeeklyFeatureError("feature_identity_invalid")
    raw_points = list(series.get("points") or [])
    if isinstance(cutoff_at, str):
        parsed_cutoff = datetime.fromisoformat(cutoff_at.replace("Z", "+00:00"))
        cutoff_utc = parsed_cutoff.astimezone(timezone.utc)
    else:
        cutoff_utc = cutoff_at.astimezone(timezone.utc) if cutoff_at is not None else None
    source_identity = series.get("source_identity")
    points: list[dict[str, Any]] = []
    for raw in raw_points:
        if not isinstance(raw, Mapping):
            raise WeeklyFeatureError("feature_point_invalid")
        if cutoff_utc is not None and _timestamp(_label(raw)) > cutoff_utc:
            continue
        row = dict(raw)
        if series.get("series_kind") == "rate_level":
            value = _number(raw.get("value"), field="value")
        else:
            value = _number(raw.get("close"), field="close")
        row["_feature_value"] = value
        points.append(row)
    if not points:
        return {
            "schema_version": FEATURE_SCHEMA_VERSION,
            "key": key,
            "timeframe": timeframe,
            "parameters": dict(FEATURE_PARAMETERS),
            "source_identity": source_identity,
            "cutoff_at": cutoff_utc.isoformat().replace("+00:00", "Z") if cutoff_utc else None,
            "status": "unavailable",
            "warmup_required": FEATURE_PARAMETERS["ema_span"],
            "source_point_count": 0,
            "points": [],
            "x_labels": [],
            "y_labels": [],
            "current": None,
            "feature_identity": _digest({"key": key, "timeframe": timeframe, "parameters": FEATURE_PARAMETERS, "source_identity": source_identity, "cutoff_at": cutoff_utc.isoformat().replace("+00:00", "Z") if cutoff_utc else None, "points": []}),
        }

    values = [float(row["_feature_value"]) for row in points]
    ema50 = _ema(values, FEATURE_PARAMETERS["ema_span"])
    fast = _ema(values, FEATURE_PARAMETERS["macd_fast"])
    slow = _ema(values, FEATURE_PARAMETERS["macd_slow"])
    macd_values: list[float | None] = [
        None if fast[index] is None or slow[index] is None else fast[index] - slow[index]
        for index in range(len(values))
    ]
    compact_macd = [value for value in macd_values if value is not None]
    compact_signal = _ema(compact_macd, FEATURE_PARAMETERS["macd_signal"])
    signal: list[float | None] = [None] * len(points)
    first_macd_index = next((index for index, value in enumerate(macd_values) if value is not None), len(points))
    for offset, value in enumerate(compact_signal):
        index = first_macd_index + offset
        if index < len(signal):
            signal[index] = value

    feature_points: list[dict[str, Any]] = []
    for index, row in enumerate(points):
        projected = {key: value for key, value in row.items() if key != "_feature_value"}
        projected.update({
            "ema50": _round(ema50[index]),
            "macd": _round(macd_values[index]),
            "macd_signal": _round(signal[index]),
            "macd_histogram": _round(None if macd_values[index] is None or signal[index] is None else macd_values[index] - signal[index]),
        })
        feature_points.append(projected)

    chart_values = [
        value
        for row, value in zip(points, values)
        for value in ([float(row["low"]), float(row["high"])] if series.get("series_kind") != "rate_level" else [value])
    ]
    x_labels, y_labels = _axis_labels(feature_points, chart_values)
    current = feature_points[-1]
    current_value = values[-1]
    return {
        "schema_version": FEATURE_SCHEMA_VERSION,
        "key": key,
        "timeframe": timeframe,
        "parameters": dict(FEATURE_PARAMETERS),
        "source_identity": source_identity,
        "cutoff_at": cutoff_utc.isoformat().replace("+00:00", "Z") if cutoff_utc else None,
        "status": "complete" if len(points) >= FEATURE_PARAMETERS["ema_span"] else "short_history",
        "warmup_required": FEATURE_PARAMETERS["ema_span"],
        "source_point_count": len(points),
        "chart_kind": "line" if series.get("series_kind") == "rate_level" else "price",
        "points": feature_points,
        "x_labels": x_labels,
        "y_labels": y_labels,
        "current": {"label": _label(current), "value": _round(current_value)},
        "high": {"value": _round(max(chart_values))},
        "low": {"value": _round(min(chart_values))},
        "feature_identity": _digest({"key": key, "timeframe": timeframe, "parameters": FEATURE_PARAMETERS, "source_identity": source_identity, "cutoff_at": cutoff_utc.isoformat().replace("+00:00", "Z") if cutoff_utc else None, "points": feature_points}),
    }
