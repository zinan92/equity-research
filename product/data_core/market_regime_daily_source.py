"""Canonical Daily K-line source bundle.

This module is the first seam of the Daily K-line Newsletter.  It attempts
the current Weekly universe at daily, four-hour and thirty-minute intervals
through the canonical datafeed HTTP service.  A failed or unsupported slot is
preserved as an explicit unavailable result; no cache, prior report or
undeclared source is promoted.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .market_regime_weekly_contract import WEEKLY_ASSET_REGISTRY
from .market_regime_weekly_datafeed import (
    ASSET_TICKERS,
    EXPLICIT_FALLBACK_SOURCES,
    EXPECTED_PROVIDER_SYMBOLS,
)
from .market_regime_weekly_source import DISPLAY_NAMES, WEEKLY_KEYS


SCHEMA_VERSION = "market-regime-daily-source-bundle-v1"
SOURCE_ID_PREFIX = "market-regime-daily-source:"
DAILY_REGISTRY_VERSION = "market-regime-daily-tradeable-registry-v1"
DAILY_TIMEFRAMES = ("daily", "four_hour", "thirty_minute")
TIMEFRAME_TO_DATAFEED = {
    "daily": "1d",
    "four_hour": "4h",
    "thirty_minute": "30m",
}
DEFAULT_LIMIT = 300


class DailySourceError(RuntimeError):
    """A Daily source bundle or pointer is invalid."""


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (_canonical(value) + "\n").encode("utf-8")


def _finite(value: Any, *, field: str) -> float:
    if isinstance(value, bool):
        raise DailySourceError(f"{field}_invalid")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise DailySourceError(f"{field}_invalid") from exc
    if not math.isfinite(number):
        raise DailySourceError(f"{field}_invalid")
    return number


def _timestamp(value: Any, *, field: str) -> tuple[datetime, str]:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        parsed = datetime.fromtimestamp(float(value), timezone.utc)
    else:
        text = str(value or "").strip()
        try:
            if len(text) == 10 and text[4] == "-" and text[7] == "-":
                parsed = datetime.combine(date.fromisoformat(text), time.min, tzinfo=timezone.utc)
            else:
                parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except (TypeError, ValueError, OverflowError) as exc:
            raise DailySourceError(f"{field}_invalid") from exc
    if parsed.tzinfo is None:
        raise DailySourceError(f"{field}_requires_timezone")
    normalized = parsed.astimezone(timezone.utc).replace(microsecond=0)
    return normalized, normalized.isoformat().replace("+00:00", "Z")


def _request_spec(asset_key: str, timeframe: str) -> dict[str, Any]:
    if asset_key not in WEEKLY_ASSET_REGISTRY:
        raise DailySourceError("asset_key_unknown")
    if timeframe not in DAILY_TIMEFRAMES:
        raise DailySourceError("daily_timeframe_unknown")
    spec = WEEKLY_ASSET_REGISTRY[asset_key]
    source = str(spec["source_id"]).removeprefix("datafeed:")
    return {
        "asset_key": asset_key,
        "asset_class": spec["asset_class"],
        "ticker": ASSET_TICKERS[asset_key],
        "provider_symbol": EXPECTED_PROVIDER_SYMBOLS.get(asset_key, ASSET_TICKERS[asset_key]),
        "timeframe": timeframe,
        "datafeed_timeframe": TIMEFRAME_TO_DATAFEED[timeframe],
        "source": source,
        "fallback_sources": list(EXPLICIT_FALLBACK_SOURCES.get(asset_key, ())),
        "canonical_symbol": spec["canonical_symbol"],
        "series_kind": spec["series_kind"],
        "unit": spec["unit"],
        "price_basis": spec["price_basis"],
        "semantic_role": spec["semantic_role"],
    }


def daily_request_for_asset(asset_key: str, timeframe: str) -> dict[str, Any]:
    """Return the exact request policy for one Daily slot."""

    spec = _request_spec(asset_key, timeframe)
    fallbacks = spec["fallback_sources"]
    return {
        **spec,
        "fallback_policy": "explicit" if fallbacks else "none",
        "request_source": spec["source"],
    }


def _metadata(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        return {}
    result: dict[str, Any] = {}
    detail = payload.get("detail")
    if isinstance(detail, Mapping):
        result.update(detail)
    elif detail is not None:
        result["detail"] = detail
    result.update({key: value for key, value in payload.items() if key != "detail"})
    return result


def _reason(payload: Any, default: str) -> str:
    meta = _metadata(payload)
    for key in ("reject_reason", "detail", "error", "reason"):
        value = meta.get(key)
        if isinstance(value, Mapping):
            value = value.get("detail") or value.get("error") or value.get("reject_reason")
        if value is not None and str(value).strip():
            return str(value).strip()[:240]
    return default


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if isinstance(item, str) and item.strip()]


def _source_identity(meta: Mapping[str, Any], *, response_hash: str, request: Mapping[str, Any]) -> dict[str, Any]:
    identity = dict(meta.get("source_identity") or {}) if isinstance(meta.get("source_identity"), Mapping) else {}
    identity.update(
        {
            "provider": meta.get("provider") or identity.get("provider"),
            "source_mode": meta.get("source_mode") or request["source"],
            "provider_symbol": meta.get("provider_symbol") or request["provider_symbol"],
            "requested_source": meta.get("requested_source") or request["source"],
            "selected_source": meta.get("selected_source") or request["source"],
            "attempted_sources": _string_list(meta.get("attempted_sources")) or [request["source"]],
            "selection_reason": meta.get("selection_reason") or "requested_or_default",
            "response_sha256": response_hash,
        }
    )
    return {key: value for key, value in identity.items() if value is not None}


def _unavailable(
    request: Mapping[str, Any],
    reason: str,
    *,
    payload: Any = None,
    status: int | None = None,
    request_evidence: Mapping[str, Any] | None = None,
    raw_body: bytes | None = None,
) -> dict[str, Any]:
    meta = _metadata(payload)
    payload_hash = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    response_hash = hashlib.sha256(raw_body).hexdigest() if raw_body is not None else payload_hash
    evidence = dict(request_evidence or {})
    if status is not None:
        evidence.setdefault("status", status)
    evidence.setdefault("payload_sha256", payload_hash)
    if raw_body is not None:
        evidence.setdefault("response_body_sha256", response_hash)
    transform = {}
    if meta.get("raw_timeframe") is not None:
        transform["raw_timeframe"] = meta.get("raw_timeframe")
    if meta.get("timeframe_origin") is not None:
        transform["timeframe_origin"] = meta.get("timeframe_origin")
    if isinstance(meta.get("aggregation"), Mapping):
        transform["aggregation"] = dict(meta["aggregation"])
    return {
        "asset_key": request["asset_key"],
        "display_name": DISPLAY_NAMES.get(request["asset_key"], request["asset_key"]),
        "timeframe": request["timeframe"],
        "datafeed_timeframe": request["datafeed_timeframe"],
        "status": "unavailable",
        "bars": [],
        "latest_timestamp": None,
        "provider": meta.get("provider") or "",
        "provider_symbol": meta.get("provider_symbol") or request["provider_symbol"],
        "source_mode": meta.get("source_mode") or request["source"],
        "requested_source": meta.get("requested_source") or request["source"],
        "selected_source": meta.get("selected_source") or request["source"],
        "selection_reason": meta.get("selection_reason") or "requested_or_default",
        "attempted_sources": _string_list(meta.get("attempted_sources")) or [request["source"]],
        "cache_policy": meta.get("cache_policy") or "bypass",
        "quality_policy": meta.get("quality_policy") or "strict",
        "fallback_policy": "explicit" if request["fallback_sources"] else "none",
        "fallback_sources": list(request["fallback_sources"]),
        "served_from": meta.get("served_from") or "upstream",
        "is_synthetic": False,
        "fresh": meta.get("fresh"),
        "completion_state": "unavailable",
        "is_provisional": False,
        "quality_flags": _string_list(meta.get("quality_flags")),
        "access_issues": _string_list(meta.get("access_issues")) or [reason],
        "reason_code": reason[:180],
        "reject_reason": reason[:240],
        "request_evidence": evidence,
        "source_identity": _source_identity(meta, response_hash=response_hash, request=request),
        **transform,
    }


def _completion_state(
    request: Mapping[str, Any],
    bars: list[Mapping[str, Any]],
    meta: Mapping[str, Any],
    *,
    cutoff: datetime,
) -> str:
    declared = str(meta.get("completion_state") or meta.get("bar_completion") or "").strip().lower()
    if declared in {"complete", "provisional", "unknown"}:
        return declared
    if bool(meta.get("is_partial")) or bool(meta.get("provisional")):
        return "provisional"
    # Daily sources expose completed session bars.  Intraday sources may end
    # on an open bucket; infer only that bounded state from the requested
    # interval and preserve the result explicitly for downstream consumers.
    if request["timeframe"] == "daily":
        return "complete"
    last, _ = _timestamp(bars[-1].get("timestamp"), field="completion_timestamp")
    seconds = {"four_hour": 4 * 3600, "thirty_minute": 30 * 60}[request["timeframe"]]
    return "complete" if last.timestamp() + seconds <= cutoff.timestamp() else "provisional"


def _validate_transform(request: Mapping[str, Any], meta: Mapping[str, Any]) -> dict[str, Any]:
    raw = str(meta.get("raw_timeframe") or "")
    origin = str(meta.get("timeframe_origin") or "")
    aggregation = meta.get("aggregation")
    if not raw or origin not in {"native", "aggregated"} or not isinstance(aggregation, Mapping):
        raise DailySourceError("timeframe_transform_metadata_missing")
    if request["timeframe"] == "daily":
        if raw != "1d":
            raise DailySourceError("daily_raw_timeframe_mismatch")
    elif request["timeframe"] == "four_hour":
        if raw == "4h":
            if origin != "native" or aggregation.get("kind") != "none":
                raise DailySourceError("four_hour_native_transform_invalid")
        elif raw == "1h":
            if origin != "aggregated" or aggregation.get("kind") != "ohlc_resample":
                raise DailySourceError("four_hour_aggregation_invalid")
            if aggregation.get("input_timeframe") != "1h":
                raise DailySourceError("four_hour_input_timeframe_invalid")
        else:
            raise DailySourceError("four_hour_raw_timeframe_invalid")
    elif request["timeframe"] == "thirty_minute" and raw != "30m":
        raise DailySourceError("thirty_minute_raw_timeframe_invalid")
    return {
        "raw_timeframe": raw,
        "timeframe_origin": origin,
        "aggregation": dict(aggregation),
    }


def _normalize_bar(row: Any, *, index: int, series_kind: str, cutoff: datetime) -> dict[str, Any]:
    if not isinstance(row, Mapping):
        raise DailySourceError(f"bar_{index}_invalid")
    stamp, iso = _timestamp(row.get("timestamp"), field=f"bar_{index}_timestamp")
    if stamp > cutoff:
        raise DailySourceError("bar_after_cutoff")
    open_value = _finite(row.get("open"), field=f"bar_{index}_open")
    high = _finite(row.get("high"), field=f"bar_{index}_high")
    low = _finite(row.get("low"), field=f"bar_{index}_low")
    close = _finite(row.get("close"), field=f"bar_{index}_close")
    volume = _finite(row.get("volume", 0), field=f"bar_{index}_volume")
    if volume < 0 or high < max(open_value, close) or low > min(open_value, close):
        raise DailySourceError(f"bar_{index}_ohlc_invalid")
    result = {
        "timestamp": iso,
        "open": open_value,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }
    if series_kind in {"rate_level", "spread"}:
        value = _finite(row.get("value", close), field=f"bar_{index}_value")
        if any(abs(item - value) > 1e-12 for item in (open_value, high, low, close)):
            raise DailySourceError(f"bar_{index}_rate_value_mismatch")
        result["value"] = value
    return result


class DailyDatafeedClient:
    """Strict HTTP client for the Daily three-timeframe request matrix."""

    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:8100",
        timeout: float = 15.0,
        opener: Callable[..., Any] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.opener = opener or (lambda request, timeout: urlopen(request, timeout=timeout))

    def _url(self, request: Mapping[str, Any], *, start: str | None, end: str | None, limit: int) -> str:
        fallback_policy = "explicit" if request["fallback_sources"] else "none"
        query: list[tuple[str, str]] = [
            ("timeframe", request["datafeed_timeframe"]),
            ("source", request["source"]),
            ("cache_policy", "bypass"),
            ("quality", "strict"),
            ("fallback_policy", fallback_policy),
            ("limit", str(limit)),
        ]
        query.extend(("fallback_sources", source) for source in request["fallback_sources"])
        if start:
            query.append(("start", start))
        if end:
            query.append(("end", end))
        return (
            f"{self.base_url}/api/candles/{request['asset_class']}/{request['ticker']}?"
            f"{urlencode(query)}"
        )

    def health(self) -> dict[str, Any]:
        """Probe service health separately from the candle request matrix."""

        url = f"{self.base_url}/api/health"
        request = Request(url, headers={"Accept": "application/json"}, method="GET")
        raw_body = b""
        status: int | None = None
        try:
            with self.opener(request, self.timeout) as response:
                status = int(getattr(response, "status", getattr(response, "status_code", 200)))
                raw_body = response.read()
            payload = json.loads(raw_body.decode("utf-8"))
            return {
                "url": url,
                "status": status,
                "service_status": payload.get("status") if isinstance(payload, Mapping) else None,
                "build_sha": payload.get("build_sha") if isinstance(payload, Mapping) else None,
                "registry": payload.get("registry") if isinstance(payload, Mapping) else None,
                "response_body_sha256": hashlib.sha256(raw_body).hexdigest(),
            }
        except HTTPError as exc:
            raw_body = exc.read() if hasattr(exc, "read") else b""
            return {
                "url": url,
                "status": int(getattr(exc, "code", 0) or 0),
                "service_status": None,
                "error": f"http:{exc}",
                "response_body_sha256": hashlib.sha256(raw_body).hexdigest(),
            }
        except (OSError, TimeoutError, UnicodeDecodeError, ValueError) as exc:
            return {
                "url": url,
                "status": status,
                "service_status": None,
                "error": f"{type(exc).__name__}:{exc}",
                "response_body_sha256": hashlib.sha256(raw_body).hexdigest(),
            }

    def fetch(
        self,
        asset_key: str,
        timeframe: str,
        *,
        start: str | None = None,
        end: str | None = None,
        limit: int = DEFAULT_LIMIT,
        cutoff_at: datetime | None = None,
    ) -> dict[str, Any]:
        request = daily_request_for_asset(asset_key, timeframe)
        cutoff = (cutoff_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
        url = self._url(request, start=start, end=end, limit=limit)
        http_request = Request(url, headers={"Accept": "application/json"}, method="GET")
        raw_body = b""
        status: int | None = None
        payload: Any = None
        try:
            with self.opener(http_request, self.timeout) as response:
                status = int(getattr(response, "status", getattr(response, "status_code", 200)))
                raw_body = response.read()
                payload = json.loads(raw_body.decode("utf-8"))
        except HTTPError as exc:
            status = int(getattr(exc, "code", 0) or 0)
            try:
                raw_body = exc.read()
                payload = json.loads(raw_body.decode("utf-8"))
            except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError):
                payload = None
            return _unavailable(
                request,
                f"datafeed_http_{status}:{_reason(payload, str(exc.reason or 'http_error'))}",
                payload=payload,
                status=status,
                request_evidence={"url": url, "method": "GET", "status": status},
                raw_body=raw_body,
            )
        except (URLError, TimeoutError, OSError) as exc:
            return _unavailable(
                request,
                f"datafeed_transport:{type(exc).__name__}",
                request_evidence={"url": url, "method": "GET", "status": None, "error_type": type(exc).__name__},
            )
        except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
            return _unavailable(
                request,
                f"datafeed_response:{type(exc).__name__}",
                request_evidence={
                    "url": url,
                    "method": "GET",
                    "status": status,
                    "response_body_sha256": hashlib.sha256(raw_body).hexdigest(),
                },
                raw_body=raw_body,
            )
        if status is None or status < 200 or status >= 300:
            return _unavailable(
                request,
                f"datafeed_http_{status or 0}:{_reason(payload, 'http_error')}",
                payload=payload,
                status=status,
                request_evidence={"url": url, "method": "GET", "status": status},
                raw_body=raw_body,
            )
        try:
            return self._convert(request, payload, cutoff=cutoff, raw_body=raw_body, url=url, status=status)
        except DailySourceError as exc:
            return _unavailable(
                request,
                f"datafeed_contract:{exc}",
                payload=payload,
                status=status,
                request_evidence={
                    "url": url,
                    "method": "GET",
                    "status": status,
                    "response_body_sha256": hashlib.sha256(raw_body).hexdigest(),
                },
                raw_body=raw_body,
            )

    def _convert(
        self,
        request: Mapping[str, Any],
        payload: Any,
        *,
        cutoff: datetime,
        raw_body: bytes,
        url: str,
        status: int,
    ) -> dict[str, Any]:
        if not isinstance(payload, Mapping):
            raise DailySourceError("payload_invalid")
        meta = _metadata(payload)
        if meta.get("ticker") not in {request["ticker"], request["provider_symbol"]}:
            raise DailySourceError("ticker_mismatch")
        if meta.get("provider_symbol") != request["provider_symbol"]:
            raise DailySourceError("provider_symbol_mismatch")
        if meta.get("asset_class") != request["asset_class"]:
            raise DailySourceError("asset_class_mismatch")
        if meta.get("timeframe") != request["datafeed_timeframe"]:
            raise DailySourceError("timeframe_mismatch")
        allowed_sources = [request["source"], *request["fallback_sources"]]
        if meta.get("requested_source") != request["source"]:
            raise DailySourceError("requested_source_mismatch")
        selected = meta.get("selected_source")
        if selected not in allowed_sources:
            raise DailySourceError("selected_source_mismatch")
        attempted = _string_list(meta.get("attempted_sources"))
        expected_attempted = allowed_sources[: allowed_sources.index(selected) + 1]
        if attempted != expected_attempted:
            raise DailySourceError("attempted_sources_mismatch")
        if meta.get("cache_policy") != "bypass" or meta.get("quality_policy") != "strict":
            raise DailySourceError("strict_policy_mismatch")
        expected_fallback = "explicit" if request["fallback_sources"] else "none"
        if meta.get("fallback_policy") != expected_fallback:
            raise DailySourceError("fallback_policy_mismatch")
        if selected != request["source"] and meta.get("selection_reason") != "explicit_fallback":
            raise DailySourceError("fallback_reason_missing")
        if meta.get("served_from") != "upstream" or meta.get("is_synthetic") is True:
            raise DailySourceError("non_upstream_or_synthetic")
        if meta.get("fresh") is False:
            raise DailySourceError("stale_response")
        for field in ("canonical_symbol", "series_kind", "unit", "price_basis", "semantic_role"):
            if field in meta and meta.get(field) != request[field]:
                raise DailySourceError(f"{field}_mismatch")
        if meta.get("reject_reason"):
            raise DailySourceError(str(meta["reject_reason"]))
        candles = meta.get("candles")
        if not isinstance(candles, list) or not candles:
            raise DailySourceError("candles_missing")
        transform = _validate_transform(request, meta)
        bars: list[dict[str, Any]] = []
        previous: datetime | None = None
        for index, row in enumerate(candles):
            bar = _normalize_bar(row, index=index, series_kind=request["series_kind"], cutoff=cutoff)
            current, _ = _timestamp(bar["timestamp"], field=f"bar_{index}_timestamp")
            if previous is not None and current <= previous:
                raise DailySourceError("bars_not_strictly_ordered")
            previous = current
            bars.append(bar)
        latest = bars[-1]["timestamp"]
        reported_latest = meta.get("latest_timestamp")
        if reported_latest is not None:
            _, reported_iso = _timestamp(reported_latest, field="latest_timestamp")
            if reported_iso != latest:
                raise DailySourceError("latest_timestamp_mismatch")
        response_hash = hashlib.sha256(raw_body).hexdigest()
        identity = _source_identity(meta, response_hash=response_hash, request=request)
        completion_state = _completion_state(request, bars, meta, cutoff=cutoff)
        identity.update(
            {
                "requested_timeframe": request["timeframe"],
                "datafeed_timeframe": request["datafeed_timeframe"],
                "request_url": url,
                "http_status": status,
            }
        )
        return {
            "asset_key": request["asset_key"],
            "display_name": DISPLAY_NAMES.get(request["asset_key"], request["asset_key"]),
            "timeframe": request["timeframe"],
            "datafeed_timeframe": request["datafeed_timeframe"],
            "status": "ready",
            "bars": bars,
            "latest_timestamp": latest,
            "provider": meta.get("provider") or "",
            "provider_symbol": meta.get("provider_symbol") or request["provider_symbol"],
            "source_mode": meta.get("source_mode") or request["source"],
            "requested_source": meta["requested_source"],
            "selected_source": selected,
            "selection_reason": meta.get("selection_reason") or "requested_or_default",
            "attempted_sources": attempted,
            "cache_policy": "bypass",
            "quality_policy": "strict",
            "fallback_policy": expected_fallback,
            "fallback_sources": list(request["fallback_sources"]),
            "served_from": "upstream",
            "is_synthetic": False,
            "fresh": meta.get("fresh"),
            "completion_state": completion_state,
            "is_provisional": completion_state == "provisional",
            "age_seconds": meta.get("age_seconds"),
            "max_age_seconds": meta.get("max_age_seconds"),
            "quality_flags": _string_list(meta.get("quality_flags")),
            "access_issues": _string_list(meta.get("access_issues")),
            "source_identity": identity,
            **transform,
        }


def _immutable_bytes(path: Path, payload: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(payload).hexdigest()
    if path.exists():
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise DailySourceError("immutable_artifact_conflict")
        return digest
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return digest


def _atomic_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def build_daily_source_bundle(
    client: DailyDatafeedClient,
    *,
    generated_at: datetime | None = None,
    limit: int = DEFAULT_LIMIT,
    max_workers: int = 4,
) -> dict[str, Any]:
    """Fetch all 19×3 slots and return a content-addressable bundle."""

    generated = (generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0)
    cutoff_at = generated.isoformat().replace("+00:00", "Z")
    slots_by_asset: dict[str, dict[str, dict[str, Any]]] = {
        asset_key: {} for asset_key in WEEKLY_KEYS
    }
    requests = [(asset_key, timeframe) for asset_key in WEEKLY_KEYS for timeframe in DAILY_TIMEFRAMES]
    worker_count = max(1, min(int(max_workers), len(requests)))
    with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="daily-kline") as pool:
        futures = {
            pool.submit(client.fetch, asset_key, timeframe, limit=limit, cutoff_at=generated): (asset_key, timeframe)
            for asset_key, timeframe in requests
        }
        for future in as_completed(futures):
            asset_key, timeframe = futures[future]
            try:
                slot = future.result()
            except Exception as exc:  # pragma: no cover - defensive boundary
                request = daily_request_for_asset(asset_key, timeframe)
                slot = _unavailable(request, f"collector_exception:{type(exc).__name__}")
            slots_by_asset[asset_key][timeframe] = slot
    assets: list[dict[str, Any]] = []
    ready_count = 0
    unavailable_count = 0
    for asset_key in WEEKLY_KEYS:
        slots = {
            timeframe: slots_by_asset[asset_key][timeframe]
            for timeframe in DAILY_TIMEFRAMES
        }
        for slot in slots.values():
            if slot["status"] == "ready":
                ready_count += 1
            else:
                unavailable_count += 1
        spec = WEEKLY_ASSET_REGISTRY[asset_key]
        assets.append(
            {
                "asset_key": asset_key,
                "display_name": DISPLAY_NAMES.get(asset_key, asset_key),
                "instrument": {
                    "canonical_symbol": spec["canonical_symbol"],
                    "asset_class": spec["asset_class"],
                    "series_kind": spec["series_kind"],
                    "unit": spec["unit"],
                    "price_basis": spec["price_basis"],
                    "semantic_role": spec["semantic_role"],
                },
                "slots": slots,
            }
        )
    total = len(WEEKLY_KEYS) * len(DAILY_TIMEFRAMES)
    identity_core = {
        "schema_version": SCHEMA_VERSION,
        "registry_version": DAILY_REGISTRY_VERSION,
        "generated_at": cutoff_at,
        "cutoff_at": cutoff_at,
        "assets_sha256": _digest(assets),
        "slot_hashes": [
            {
                "asset_key": asset["asset_key"],
                "timeframes": {
                    timeframe: slot.get("source_identity", {}).get("response_sha256")
                    for timeframe, slot in asset["slots"].items()
                },
            }
            for asset in assets
        ],
    }
    bundle_id = f"{SOURCE_ID_PREFIX}{_digest(identity_core)}"
    return {
        "bundle_id": bundle_id,
        "schema_version": SCHEMA_VERSION,
        "registry_version": DAILY_REGISTRY_VERSION,
        "generated_at": cutoff_at,
        "cutoff_at": cutoff_at,
        "data_kind": "real" if ready_count else "unavailable",
        "source_status": "ready" if unavailable_count == 0 else "partial" if ready_count else "unavailable",
        "coverage": {
            "total_slots": total,
            "ready_slots": ready_count,
            "unavailable_slots": unavailable_count,
            "fraction": round(ready_count / total, 4) if total else 0.0,
            "requested_timeframes": list(DAILY_TIMEFRAMES),
        },
        "source_policy": {
            "base_url": client.base_url,
            "cache_policy": "bypass",
            "quality_policy": "strict",
            "fallback_policy": "explicit_for_declared_a_share_only",
            "no_stale_promotion": True,
        },
        "identity_core": identity_core,
        "assets": assets,
    }


class DailySourceStore:
    """Content-addressed source artifacts and a verified latest pointer."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).expanduser().resolve()
        self.artifacts = self.root / "artifacts"
        self.latest_path = self.root / "latest.json"

    def publish(self, bundle: Mapping[str, Any]) -> dict[str, Any]:
        value = dict(bundle)
        _validate_bundle_shape(value)
        bundle_id = str(value.get("bundle_id") or "")
        if not bundle_id.startswith(SOURCE_ID_PREFIX):
            raise DailySourceError("bundle_id_invalid")
        digest = bundle_id.removeprefix(SOURCE_ID_PREFIX)
        if digest != _digest(value.get("identity_core")):
            raise DailySourceError("bundle_identity_mismatch")
        if value["identity_core"].get("assets_sha256") != _digest(value.get("assets")):
            raise DailySourceError("bundle_assets_hash_invalid")
        payload = _json_bytes(value)
        artifact_path = self.artifacts / f"{digest}.json"
        artifact_hash = _immutable_bytes(artifact_path, payload)
        pointer = {
            "schema_version": SCHEMA_VERSION,
            "bundle_id": bundle_id,
            "artifact": {"path": f"artifacts/{digest}.json", "sha256": artifact_hash},
            "published_at": value.get("generated_at"),
        }
        _atomic_bytes(self.latest_path, _json_bytes(pointer))
        return pointer

    def latest(self) -> dict[str, Any]:
        try:
            pointer = json.loads(self.latest_path.read_text(encoding="utf-8"))
            if pointer.get("schema_version") != SCHEMA_VERSION:
                raise DailySourceError("source_pointer_schema_invalid")
            bundle_id = str(pointer.get("bundle_id") or "")
            digest = bundle_id.removeprefix(SOURCE_ID_PREFIX)
            if not bundle_id.startswith(SOURCE_ID_PREFIX) or len(digest) != 64:
                raise DailySourceError("source_pointer_identity_invalid")
            ref = pointer.get("artifact") or {}
            if ref.get("path") != f"artifacts/{digest}.json":
                raise DailySourceError("source_pointer_path_invalid")
            artifact_path = (self.root / ref["path"]).resolve()
            if self.root.resolve() not in artifact_path.parents:
                raise DailySourceError("source_pointer_path_escape")
            artifact_bytes = artifact_path.read_bytes()
            if ref.get("sha256") != hashlib.sha256(artifact_bytes).hexdigest():
                raise DailySourceError("source_pointer_hash_invalid")
            artifact = json.loads(artifact_bytes.decode("utf-8"))
            _validate_bundle_shape(artifact)
            if artifact.get("bundle_id") != bundle_id:
                raise DailySourceError("source_artifact_identity_invalid")
            if _digest(artifact.get("identity_core")) != digest:
                raise DailySourceError("source_artifact_hash_invalid")
            return artifact
        except FileNotFoundError as exc:
            raise DailySourceError("source_latest_unavailable") from exc
        except json.JSONDecodeError as exc:
            raise DailySourceError("source_latest_json_invalid") from exc


def _validate_bundle_shape(bundle: Mapping[str, Any]) -> None:
    if bundle.get("schema_version") != SCHEMA_VERSION:
        raise DailySourceError("bundle_schema_invalid")
    if bundle.get("registry_version") != DAILY_REGISTRY_VERSION:
        raise DailySourceError("bundle_registry_invalid")
    assets = bundle.get("assets")
    if not isinstance(assets, list) or [item.get("asset_key") for item in assets if isinstance(item, Mapping)] != list(WEEKLY_KEYS):
        raise DailySourceError("bundle_asset_universe_invalid")
    expected_slots = set(DAILY_TIMEFRAMES)
    for asset in assets:
        if not isinstance(asset, Mapping) or set(asset.get("slots") or {}) != expected_slots:
            raise DailySourceError("bundle_slot_shape_invalid")
        for slot in (asset.get("slots") or {}).values():
            if not isinstance(slot, Mapping):
                raise DailySourceError("bundle_slot_invalid")
            status = slot.get("status")
            bars = slot.get("bars")
            if status not in {"ready", "unavailable"}:
                raise DailySourceError("bundle_slot_status_invalid")
            if (status == "ready" and not isinstance(bars, list)) or (status == "unavailable" and bars):
                raise DailySourceError("bundle_slot_bars_status_invalid")


__all__ = [
    "DAILY_TIMEFRAMES",
    "DAILY_REGISTRY_VERSION",
    "DailyDatafeedClient",
    "DailySourceError",
    "DailySourceStore",
    "SCHEMA_VERSION",
    "build_daily_source_bundle",
    "daily_request_for_asset",
]
