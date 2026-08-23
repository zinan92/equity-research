"""Typed bridge from Weekly CandleResponse to the standard-kline adapter.

This module does not fetch data or render a browser.  It freezes the exact
renderer input and options so the later snapshot port can call the pinned
standard-kline package without reinterpreting Weekly source semantics.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from .market_regime_weekly_contract import WeeklyCandleContractError, validate_weekly_candle_response


STANDARD_KLINE_REPOSITORY = "zinan92/standard-kline"
STANDARD_KLINE_VERSION = "0.1.0"
STANDARD_KLINE_COMMIT = "07acafa79e72af10d17b5a10b7bb11625fd709c2"
STANDARD_KLINE_RENDERER = f"{STANDARD_KLINE_REPOSITORY}@{STANDARD_KLINE_COMMIT}"

STANDARD_KLINE_OPTIONS: dict[str, Any] = {
    "appearance": "light",
    "candleDirection": "green-up-red-down",
    "hollowUp": True,
    "filledDown": True,
    "showVolume": True,
    "indicators": {
        "ema": [50],
        "macd": {"fastPeriod": 12, "slowPeriod": 26, "signalPeriod": 9},
    },
}


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _render_mode(series_kind: Any) -> str:
    return "line" if str(series_kind or "") in {"rate_level", "spread"} else "candles"


def standard_kline_options_for_response(response: Mapping[str, Any]) -> dict[str, Any]:
    """Return detached, immutable-by-convention options for one response."""

    if not isinstance(response, Mapping):
        raise WeeklyCandleContractError("standard_kline_response_invalid")
    options = {**STANDARD_KLINE_OPTIONS}
    options["indicators"] = {**STANDARD_KLINE_OPTIONS["indicators"]}
    options["renderMode"] = _render_mode(response.get("series_kind"))
    if options["renderMode"] == "line":
        options["lineColor"] = "#526779"
        options["lineWidth"] = 2
    return options


def build_standard_kline_payload(
    response: Mapping[str, Any],
    *,
    provisional_bar: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Project one validated Weekly CandleResponse into standard-kline input.

    The source envelope remains the authority.  For a rate/spread response the
    JS adapter reads the level from each candle's ``value``/``close`` and uses
    ``LineSeries``; this bridge never manufactures equal-value OHLC rows.
    """

    validated = validate_weekly_candle_response(response)
    bars = [dict(item) for item in validated.get("bars") or []]
    if provisional_bar is not None:
        if provisional_bar.get("close_status") != "provisional" or provisional_bar.get("is_partial") is not True:
            raise WeeklyCandleContractError("provisional_bar_metadata_invalid")
        bars.append(dict(provisional_bar))
    payload = {
        "schema_version": validated["schema_version"],
        "status": validated["status"],
        "ticker": validated["canonical_symbol"],
        "symbol": validated["canonical_symbol"],
        "asset_class": validated["asset_class"],
        "series_kind": validated["series_kind"],
        "render_mode": _render_mode(validated["series_kind"]),
        "unit": validated["unit"],
        "price_basis": validated["price_basis"],
        "semantic_role": validated["semantic_role"],
        "timeframe": validated["timeframe"],
        "cutoff_at": validated.get("cutoff_at"),
        "provider": validated.get("provider", ""),
        "source_mode": validated.get("source_mode", ""),
        "quality_flags": list(validated.get("quality_flags") or []),
        "is_synthetic": validated["is_synthetic"],
        "served_from": validated.get("served_from", ""),
        "fresh": validated.get("fresh"),
        "latest_timestamp": validated.get("latest_timestamp"),
        "age_seconds": validated.get("age_seconds"),
        "max_age_seconds": validated.get("max_age_seconds"),
        "access_issues": list(validated.get("access_issues") or []),
        "reject_reason": validated.get("reject_reason"),
        "source_identity": dict(validated.get("source_identity") or {}),
        "candle_response_hash": _digest(validated),
        "provisional_candle_hash": _digest(provisional_bar) if provisional_bar is not None else None,
        "candles": bars,
        "provisional_candle": provisional_bar is not None,
        "renderer": STANDARD_KLINE_RENDERER,
        "renderer_version": STANDARD_KLINE_VERSION,
        "renderer_options": standard_kline_options_for_response(validated),
    }
    return payload


__all__ = [
    "STANDARD_KLINE_COMMIT",
    "STANDARD_KLINE_OPTIONS",
    "STANDARD_KLINE_RENDERER",
    "STANDARD_KLINE_REPOSITORY",
    "STANDARD_KLINE_VERSION",
    "build_standard_kline_payload",
    "standard_kline_options_for_response",
]
