"""Evidence-preserving macro authority for Market Regime Daily v2.

This layer is deliberately separate from the price-OHLC instrument registry.
DXY is a supplementary index input; U.S. Treasury 2Y/10Y are official par
yield-curve levels; 2s10s is derived from same-date accepted Treasury rows.
"""
from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
import io
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Any, Iterable, Mapping
from uuid import uuid4
from zoneinfo import ZoneInfo

from .market_regime_data import (
    HttpCapture,
    InstrumentSpec,
    LicenseDecision,
    MarketRegimeDataError,
    SourceCaptureError,
    http_get_capture,
    license_decision,
    normalize_capture,
)


SCHEMA_VERSION = "market-regime-macro-data-v1"
MIN_OBSERVATIONS = 120
PREFERRED_OBSERVATIONS = 200
TREASURY_SOURCE_PAGE = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
    "TextView?type=daily_treasury_yield_curve"
)
TREASURY_CSV_TEMPLATE = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
    "daily-treasury-rates.csv/{year}/all?type=daily_treasury_yield_curve"
    "&field_tdr_date_value={year}&_format=csv"
)
DXY_CHART_URL = (
    "https://query2.finance.yahoo.com/v8/finance/chart/DX-Y.NYB"
    "?interval=1d&range=2y&events=history&includeAdjustedClose=false"
)


class MarketRegimeMacroDataError(MarketRegimeDataError):
    """Macro source, normalization or immutable-store contract failed."""


@dataclass(frozen=True)
class MacroFactorSpec:
    key: str
    display_name: str
    kind: str
    provider: str
    provider_symbol: str | None
    level_unit: str
    change_unit: str
    source_tier: str
    derived_from: tuple[str, ...] = ()


MACRO_FACTORS: tuple[MacroFactorSpec, ...] = (
    MacroFactorSpec(
        "dxy",
        "美元指数",
        "index_level",
        "yahoo_chart",
        "DX-Y.NYB",
        "index_points",
        "percent_return",
        "supplementary_only",
    ),
    MacroFactorSpec(
        "us2y",
        "美国国债 2Y",
        "yield_level",
        "us_treasury_daily_par_yield_curve",
        "2 Yr",
        "percent",
        "basis_points",
        "official_government_source",
    ),
    MacroFactorSpec(
        "us10y",
        "美国国债 10Y",
        "yield_level",
        "us_treasury_daily_par_yield_curve",
        "10 Yr",
        "percent",
        "basis_points",
        "official_government_source",
    ),
    MacroFactorSpec(
        "us2s10s",
        "美国国债 2s10s",
        "yield_spread",
        "derived_same_date",
        None,
        "basis_points",
        "basis_points",
        "derived_from_official_source",
        ("us2y", "us10y"),
    ),
)
MACRO_FACTOR_BY_KEY = {item.key: item for item in MACRO_FACTORS}
if len(MACRO_FACTOR_BY_KEY) != len(MACRO_FACTORS):  # pragma: no cover
    raise RuntimeError("macro factor keys must be unique")

DXY_SPEC = InstrumentSpec(
    "dxy",
    "U.S. Dollar Index",
    "macro_fx",
    "macro_factor",
    "yahoo_chart",
    "DX-Y.NYB",
    "DX-Y.NYB",
    "price_index",
    "USD",
    "index points",
    "America/New_York",
    "17:00",
    "provider_unadjusted_index_level",
    MIN_OBSERVATIONS,
    PREFERRED_OBSERVATIONS,
    240,
)


def macro_registry_payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "factors": [asdict(item) for item in MACRO_FACTORS],
        "sources": {
            "dxy": {
                "provider": "yahoo_chart",
                "provider_symbol": "DX-Y.NYB",
                "authority_tier": "supplementary_only",
                "license_scope": "local_evaluation_only",
            },
            "treasury": {
                "provider": "us_treasury_daily_par_yield_curve",
                "source_page": TREASURY_SOURCE_PAGE,
                "authority_tier": "official_government_source",
                "fields": ["Date", "2 Yr", "10 Yr"],
            },
        },
        "publication_eligible": False,
        "action_eligible": False,
    }


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise MarketRegimeMacroDataError("timestamps must include timezone")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (_canonical_json(value) + "\n").encode("utf-8")


def _run_id(now: datetime) -> str:
    stamp = now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"market-regime-macro-{stamp}-{uuid4().hex[:12]}"


def _treasury_url(year: int) -> str:
    return TREASURY_CSV_TEMPLATE.format(year=year)


def _capture_core(capture: HttpCapture) -> dict[str, Any]:
    return {
        "requested_url": capture.requested_url,
        "final_url": capture.final_url,
        "status_code": capture.status_code,
        "content_type": capture.content_type,
        "raw_sha256": capture.raw_sha256,
        "raw_bytes": len(capture.body),
    }


def _capture_receipt(capture: HttpCapture, *, raw_path: str | None) -> dict[str, Any]:
    receipt = capture.receipt(raw_path=raw_path)
    # HttpCapture uses None for an empty response body. At this evidence layer an
    # empty response is still an exact byte sequence and must remain replayable.
    if raw_path is not None and not capture.body:
        receipt["raw_sha256"] = sha256(b"").hexdigest()
    return receipt


def _factor_identity(core: Mapping[str, Any]) -> str:
    digest = sha256(_canonical_json(core).encode("utf-8")).hexdigest()
    return f"{SCHEMA_VERSION}:{digest}"


def _bounded_excerpt(body: bytes, limit: int = 400) -> str | None:
    if not body:
        return None
    text = " ".join(body[: limit * 4].decode("utf-8", errors="replace").split())
    return text[:limit] or None


def _write_bytes_exclusive(path: Path, encoded: bytes) -> str:
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
    return _write_bytes_exclusive(path, _json_bytes(payload))


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


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    if not isinstance(value, dict):
        raise MarketRegimeMacroDataError(f"runtime JSON must be an object: {path}")
    return value


def _read_artifact(root: Path, reference: Mapping[str, Any]) -> dict[str, Any]:
    relative = str(reference.get("path") or "")
    expected = str(reference.get("sha256") or "")
    target = (root / relative).resolve()
    if not relative or len(expected) != 64 or root not in target.parents:
        raise MarketRegimeMacroDataError("macro artifact reference is invalid")
    try:
        encoded = target.read_bytes()
    except FileNotFoundError as exc:
        raise MarketRegimeMacroDataError("macro artifact is missing") from exc
    if sha256(encoded).hexdigest() != expected:
        raise MarketRegimeMacroDataError("macro artifact hash mismatch")
    payload = json.loads(encoded)
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
        raise MarketRegimeMacroDataError("macro artifact schema mismatch")
    identity_core = payload.get("identity_core")
    if not isinstance(identity_core, dict) or payload.get("factor_id") != _factor_identity(identity_core):
        raise MarketRegimeMacroDataError("macro factor identity mismatch")
    source_receipt = payload.get("source_receipt")
    captures = source_receipt.get("captures") if isinstance(source_receipt, dict) else None
    if not isinstance(captures, list) or not captures:
        raise MarketRegimeMacroDataError("macro factor lacks source capture receipts")
    for capture in captures:
        if not isinstance(capture, dict):
            raise MarketRegimeMacroDataError("macro source capture receipt is invalid")
        raw_bytes = capture.get("raw_bytes")
        raw_sha = str(capture.get("raw_sha256") or "")
        raw_relative = str(capture.get("raw_path") or "")
        if not isinstance(raw_bytes, int) or raw_bytes <= 0:
            raise MarketRegimeMacroDataError("accepted macro source body is empty")
        raw_target = (root / raw_relative).resolve()
        if not raw_relative or len(raw_sha) != 64 or root not in raw_target.parents:
            raise MarketRegimeMacroDataError("macro raw artifact reference is invalid")
        try:
            raw = raw_target.read_bytes()
        except FileNotFoundError as exc:
            raise MarketRegimeMacroDataError("macro raw artifact is missing") from exc
        if len(raw) != raw_bytes or sha256(raw).hexdigest() != raw_sha:
            raise MarketRegimeMacroDataError("macro raw artifact hash mismatch")
    return payload


def _change(values: list[float], periods: int) -> float:
    if len(values) <= periods:
        raise MarketRegimeMacroDataError("macro history is too short for change")
    return values[-1] - values[-periods - 1]


def normalize_dxy(capture: HttpCapture, *, now: datetime) -> dict[str, Any]:
    normalized = normalize_capture(DXY_SPEC, capture, now=now)
    closes = [float(row["close"]) for row in normalized["bars"]]
    core = {
        "factor": asdict(MACRO_FACTOR_BY_KEY["dxy"]),
        "bars": normalized["bars"],
        "last_completed_session": normalized["last_completed_session"],
        "last_completed_close_at": normalized["last_completed_close_at"],
        "quality": normalized["quality"],
        "value": closes[-1],
        "changes": {
            "1d_pct": round((closes[-1] / closes[-2] - 1) * 100, 6),
            "5d_pct": round((closes[-1] / closes[-6] - 1) * 100, 6),
            "20d_pct": round((closes[-1] / closes[-21] - 1) * 100, 6),
        },
        "dropped_unfinished_sessions": normalized["dropped_unfinished_sessions"],
        "dropped_empty_provider_sessions": normalized["dropped_empty_provider_sessions"],
        "source": _capture_core(capture),
    }
    return core


def _parse_yield(value: Any, *, field: str, capture: HttpCapture) -> float:
    text = str(value or "").strip()
    if not text or text.upper() == "N/A":
        raise SourceCaptureError(f"Treasury {field} is unavailable", capture=capture)
    try:
        number = float(text)
    except ValueError as exc:
        raise SourceCaptureError(f"Treasury {field} is not numeric", capture=capture) from exc
    if not math.isfinite(number) or number < 0 or number > 30:
        raise SourceCaptureError(f"Treasury {field} is outside accepted bounds", capture=capture)
    return number


def parse_treasury_captures(
    captures: Iterable[HttpCapture], *, now: datetime
) -> dict[str, dict[str, Any]]:
    rows_by_date: dict[date, tuple[float, float, str]] = {}
    source_cores: list[dict[str, Any]] = []
    provider_orders: list[str] = []
    capture_list = list(captures)
    if not capture_list:
        raise MarketRegimeMacroDataError("Treasury capture is required")
    local_today = now.astimezone(ZoneInfo("America/New_York")).date()
    for capture in capture_list:
        if capture.status_code != 200:
            raise SourceCaptureError(
                f"Treasury HTTP status is {capture.status_code}", capture=capture
            )
        if capture.content_type not in {"text/csv", "application/csv", "application/octet-stream"}:
            raise SourceCaptureError(
                f"Treasury Content-Type is not CSV: {capture.content_type or 'missing'}",
                capture=capture,
            )
        if not capture.body:
            raise SourceCaptureError("Treasury CSV body is empty", capture=capture)
        try:
            text = capture.body.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise SourceCaptureError("Treasury CSV is not UTF-8", capture=capture) from exc
        reader = csv.DictReader(io.StringIO(text))
        required = {"Date", "2 Yr", "10 Yr"}
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            raise SourceCaptureError("Treasury CSV columns are incomplete", capture=capture)
        source_dates: list[date] = []
        for raw in reader:
            try:
                session = datetime.strptime(str(raw.get("Date") or ""), "%m/%d/%Y").date()
            except ValueError as exc:
                raise SourceCaptureError("Treasury Date is invalid", capture=capture) from exc
            if session > local_today:
                raise SourceCaptureError(
                    f"Treasury row is dated in the future: {session.isoformat()}", capture=capture
                )
            two = _parse_yield(raw.get("2 Yr"), field="2 Yr", capture=capture)
            ten = _parse_yield(raw.get("10 Yr"), field="10 Yr", capture=capture)
            if session in rows_by_date:
                raise SourceCaptureError(
                    f"duplicate Treasury date: {session.isoformat()}", capture=capture
                )
            rows_by_date[session] = (two, ten, capture.raw_sha256 or "")
            source_dates.append(session)
        if not source_dates:
            raise SourceCaptureError("Treasury CSV has no data rows", capture=capture)
        if source_dates == sorted(source_dates):
            provider_orders.append("ascending")
        elif source_dates == sorted(source_dates, reverse=True):
            provider_orders.append("descending_reordered")
        else:
            raise SourceCaptureError("Treasury CSV dates are unordered", capture=capture)
        source_cores.append(_capture_core(capture))

    ordered = sorted(rows_by_date.items())
    if len(ordered) < MIN_OBSERVATIONS:
        raise SourceCaptureError(
            f"Treasury history is too short: {len(ordered)} < {MIN_OBSERVATIONS}",
            capture=capture_list[-1],
        )
    latest_date = ordered[-1][0]
    age_days = max(0, (local_today - latest_date).days)
    quality = "fresh" if age_days <= 4 else "partial" if age_days <= 10 else "stale"
    close_at = datetime.combine(
        latest_date, time(15, 30), tzinfo=ZoneInfo("America/New_York")
    ).astimezone(timezone.utc)
    twos = [value[1][0] for value in ordered]
    tens = [value[1][1] for value in ordered]
    spreads = [(ten - two) * 100 for two, ten in zip(twos, tens)]
    source = {
        "source_page": TREASURY_SOURCE_PAGE,
        "captures": source_cores,
        "provider_orders": provider_orders,
    }

    def factor_payload(key: str, values: list[float], unit: str) -> dict[str, Any]:
        observations = [
            {"date": session.isoformat(), "value": round(value, 6)}
            for (session, _), value in zip(ordered, values)
        ]
        return {
            "factor": asdict(MACRO_FACTOR_BY_KEY[key]),
            "observations": observations,
            "observation_count": len(observations),
            "last_completed_session": latest_date.isoformat(),
            "last_completed_close_at": _iso(close_at),
            "quality": quality,
            "age_days": age_days,
            "value": round(values[-1], 6),
            "level_unit": unit,
            "changes": {
                "1d_bp": round(_change(values, 1) * (100 if unit == "percent" else 1), 6),
                "5d_bp": round(_change(values, 5) * (100 if unit == "percent" else 1), 6),
                "20d_bp": round(_change(values, 20) * (100 if unit == "percent" else 1), 6),
            },
            "source": source,
        }

    us2y = factor_payload("us2y", twos, "percent")
    us10y = factor_payload("us10y", tens, "percent")
    curve = factor_payload("us2s10s", spreads, "basis_points")
    curve["derivation"] = {
        "formula": "us10y_percent - us2y_percent",
        "scale_to_basis_points": 100,
        "same_date_required": True,
        "latest_inputs": {
            "date": latest_date.isoformat(),
            "us2y_percent": round(twos[-1], 6),
            "us10y_percent": round(tens[-1], 6),
            "source_raw_sha256": ordered[-1][1][2],
        },
    }
    return {"us2y": us2y, "us10y": us10y, "us2s10s": curve}


def _frozen_factor(
    *, key: str, core: Mapping[str, Any], run_id: str, generated_at: str,
    license_value: LicenseDecision, source_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    identity_core = {"schema_version": SCHEMA_VERSION, "key": key, "core": core}
    return {
        "schema_version": SCHEMA_VERSION,
        "factor_id": _factor_identity(identity_core),
        "identity_core": identity_core,
        "run_id": run_id,
        "generated_at": generated_at,
        # The receipt is audit metadata, not factor identity. Replaying identical
        # raw bytes may change fetch timestamps and raw paths without changing
        # the content-addressed factor_id.
        "source_receipt": dict(source_receipt),
        **core,
        "license": license_value.as_json(),
        "data_kind": "real",
        "publication_eligible": False,
        "action_eligible": False,
    }


class MarketRegimeMacroDataStore:
    """Serial macro collector with immutable raw evidence and latest-good pointers."""

    def __init__(self, root: Path | str, *, http_get=http_get_capture) -> None:
        self.root = Path(root).expanduser().resolve()
        self.http_get = http_get
        self._live_transport = http_get is http_get_capture

    def _fallback(self, key: str, failure: Mapping[str, Any]) -> dict[str, Any]:
        pointer = _read_json(self.root / "factors" / key / "latest-good.json")
        if pointer is None:
            return {
                "schema_version": SCHEMA_VERSION,
                "factor": asdict(MACRO_FACTOR_BY_KEY[key]),
                "quality": "unavailable",
                "refresh_status": "rejected",
                "refresh_failure": dict(failure),
                "publication_eligible": False,
                "action_eligible": False,
            }
        reference = pointer.get("artifact") or {}
        artifact = _read_artifact(self.root, reference)
        return {
            **artifact,
            "artifact": reference,
            "refresh_status": "rejected",
            "refresh_failure": dict(failure),
        }

    def _not_refreshed(self, key: str) -> dict[str, Any]:
        pointer = _read_json(self.root / "factors" / key / "latest-good.json")
        if pointer is None:
            return {
                "schema_version": SCHEMA_VERSION,
                "factor": asdict(MACRO_FACTOR_BY_KEY[key]),
                "quality": "unavailable",
                "refresh_status": "not_requested",
                "publication_eligible": False,
                "action_eligible": False,
            }
        reference = pointer.get("artifact") or {}
        artifact = _read_artifact(self.root, reference)
        return {
            **artifact,
            "artifact": reference,
            "refresh_status": "not_refreshed",
        }

    def refresh(
        self,
        *,
        now: datetime | None = None,
        factor_keys: Iterable[str] | None = None,
        deployment_mode: str | None = None,
        license_status: str | None = None,
        license_reference: str | None = None,
    ) -> dict[str, Any]:
        selected = list(factor_keys or [item.key for item in MACRO_FACTORS])
        if not selected or len(selected) != len(set(selected)):
            raise MarketRegimeMacroDataError("factor_keys must be a non-empty unique list")
        unknown = [key for key in selected if key not in MACRO_FACTOR_BY_KEY]
        if unknown:
            raise MarketRegimeMacroDataError(
                f"unknown macro factors: {', '.join(unknown)}"
            )
        if now is not None and self._live_transport:
            raise MarketRegimeMacroDataError(
                "clock overrides require an injected offline transport"
            )
        current = (now or _utc_now()).astimezone(timezone.utc)
        license_value = license_decision(
            deployment_mode=deployment_mode,
            license_status=license_status,
            license_reference=license_reference,
            private_preview=False,
        )
        run_id = _run_id(current)
        started_at = _iso(current)
        _write_json_exclusive(
            self.root / "run-events" / run_id / "000-started.json",
            {
                "schema_version": SCHEMA_VERSION,
                "event": "started",
                "run_id": run_id,
                "started_at": started_at,
                "factor_keys": selected,
                "license": license_value.as_json(),
            },
        )
        results: list[dict[str, Any]] = []
        snapshot_factors: list[dict[str, Any]] = []
        pending_pointers: list[tuple[str, dict[str, Any]]] = []
        accepted_cores: dict[str, dict[str, Any]] = {}
        accepted_receipts: dict[str, dict[str, Any]] = {}

        if "dxy" in selected:
            capture: HttpCapture | None = None
            raw_relative: str | None = None
            try:
                capture = self.http_get(DXY_CHART_URL)
                raw_relative = f"raw/{run_id}/dxy.json"
                _write_bytes_exclusive(self.root / raw_relative, capture.body)
                accepted_cores["dxy"] = normalize_dxy(capture, now=current)
                accepted_receipts["dxy"] = {
                    "captures": [_capture_receipt(capture, raw_path=raw_relative)]
                }
            except Exception as exc:
                if isinstance(exc, SourceCaptureError) and exc.capture is not None:
                    capture = exc.capture
                failure = {
                    "key": "dxy",
                    "status": "rejected",
                    "quality": "unavailable",
                    "reason": str(exc),
                    "source": (
                        _capture_receipt(capture, raw_path=raw_relative)
                        if capture
                        else None
                    ),
                    "bounded_raw_excerpt": _bounded_excerpt(capture.body) if capture else None,
                }
                results.append(failure)
                snapshot_factors.append(self._fallback("dxy", failure))

        rate_keys = [key for key in selected if key in {"us2y", "us10y", "us2s10s"}]
        if rate_keys:
            captures: list[HttpCapture] = []
            raw_paths: list[str | None] = []
            try:
                current_year = current.astimezone(ZoneInfo("America/New_York")).year
                first = self.http_get(_treasury_url(current_year))
                captures.append(first)
                path: str | None = f"raw/{run_id}/treasury-{current_year}.csv"
                _write_bytes_exclusive(self.root / path, first.body)
                raw_paths.append(path)
                parsed = parse_treasury_captures(captures, now=current)
            except SourceCaptureError as first_error:
                if "history is too short" not in str(first_error):
                    raise_error: Exception | None = first_error
                else:
                    try:
                        prior = self.http_get(_treasury_url(current_year - 1))
                        captures.append(prior)
                        path = f"raw/{run_id}/treasury-{current_year - 1}.csv"
                        _write_bytes_exclusive(self.root / path, prior.body)
                        raw_paths.append(path)
                        parsed = parse_treasury_captures(captures, now=current)
                        raise_error = None
                    except Exception as exc:
                        raise_error = exc
                if raise_error is not None:
                    parsed = {}
                    for key in rate_keys:
                        failure = {
                            "key": key,
                            "status": "rejected",
                            "quality": "unavailable",
                            "reason": str(raise_error),
                            "sources": [
                                _capture_receipt(
                                    capture,
                                    raw_path=(
                                        raw_paths[index]
                                        if index < len(raw_paths)
                                        else None
                                    )
                                )
                                for index, capture in enumerate(captures)
                            ],
                            "bounded_raw_excerpt": _bounded_excerpt(captures[-1].body) if captures else None,
                        }
                        results.append(failure)
                        snapshot_factors.append(self._fallback(key, failure))
            except Exception as exc:
                parsed = {}
                for key in rate_keys:
                    failure = {
                        "key": key,
                        "status": "rejected",
                        "quality": "unavailable",
                        "reason": str(exc),
                        "sources": [
                            _capture_receipt(
                                capture,
                                raw_path=(
                                    raw_paths[index]
                                    if index < len(raw_paths)
                                    else None
                                )
                            )
                            for index, capture in enumerate(captures)
                        ],
                        "bounded_raw_excerpt": _bounded_excerpt(captures[-1].body) if captures else None,
                    }
                    results.append(failure)
                    snapshot_factors.append(self._fallback(key, failure))
            for key in rate_keys:
                if key in parsed:
                    accepted_cores[key] = parsed[key]
                    accepted_receipts[key] = {
                        "captures": [
                            _capture_receipt(
                                capture,
                                raw_path=(
                                    raw_paths[index]
                                    if index < len(raw_paths)
                                    else None
                                )
                            )
                            for index, capture in enumerate(captures)
                        ]
                    }

        completed_at = _iso(_utc_now())
        for key, core in accepted_cores.items():
            frozen = _frozen_factor(
                key=key,
                core=core,
                run_id=run_id,
                generated_at=completed_at,
                license_value=license_value,
                source_receipt=accepted_receipts[key],
            )
            relative = f"normalized/{run_id}/{key}.json"
            artifact_hash = _write_json_exclusive(self.root / relative, frozen)
            reference = {
                "path": relative,
                "sha256": artifact_hash,
                "schema_version": SCHEMA_VERSION,
                "factor_id": frozen["factor_id"],
            }
            pending_pointers.append(
                (
                    key,
                    {
                        "schema_version": SCHEMA_VERSION,
                        "factor_key": key,
                        "run_id": run_id,
                        "artifact": reference,
                    },
                )
            )
            results.append(
                {
                    "key": key,
                    "status": "accepted",
                    "quality": frozen["quality"],
                    "factor_id": frozen["factor_id"],
                    "artifact": reference,
                    "source_receipt": frozen["source_receipt"],
                }
            )
            snapshot_factors.append({**frozen, "artifact": reference})

        for key in MACRO_FACTOR_BY_KEY:
            if key not in selected:
                snapshot_factors.append(self._not_refreshed(key))

        order = {key: index for index, key in enumerate(MACRO_FACTOR_BY_KEY)}
        results.sort(key=lambda item: order[item["key"]])
        snapshot_factors.sort(
            key=lambda item: order[(item.get("factor") or {}).get("key")]
        )
        receipt = {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "started_at": started_at,
            "completed_at": completed_at,
            "license": license_value.as_json(),
            "registry_sha256": sha256(
                _canonical_json(macro_registry_payload()).encode("utf-8")
            ).hexdigest(),
            "results": results,
            "accepted_count": sum(item["status"] == "accepted" for item in results),
            "rejected_count": sum(item["status"] == "rejected" for item in results),
        }
        _write_json_exclusive(self.root / "runs" / f"{run_id}.json", receipt)
        _write_json_exclusive(
            self.root / "run-events" / run_id / "001-completed.json",
            {"event": "completed", **receipt},
        )
        for key, pointer in pending_pointers:
            _write_json_atomic(self.root / "factors" / key / "latest-good.json", pointer)
        qualities = [str(item.get("quality") or "unavailable") for item in snapshot_factors]
        quality = (
            "unavailable"
            if not qualities or all(value == "unavailable" for value in qualities)
            else "partial"
            if (
                any(value != "fresh" for value in qualities)
                or receipt["rejected_count"]
                or any(
                    item.get("refresh_status") in {"not_requested", "not_refreshed"}
                    for item in snapshot_factors
                )
            )
            else "fresh"
        )
        snapshot = {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "generated_at": completed_at,
            "quality": quality,
            "factor_count": len(snapshot_factors),
            "factors": snapshot_factors,
            "refresh_receipt": f"runs/{run_id}.json",
            "license": license_value.as_json(),
            "publication_eligible": False,
            "action_eligible": False,
        }
        _write_json_atomic(self.root / "latest.json", snapshot)
        return snapshot

    def latest(self) -> dict[str, Any]:
        payload = _read_json(self.root / "latest.json")
        if payload is None:
            raise MarketRegimeMacroDataError("macro latest snapshot is unavailable")
        if payload.get("schema_version") != SCHEMA_VERSION:
            raise MarketRegimeMacroDataError("macro latest snapshot schema mismatch")
        for item in payload.get("factors") or []:
            reference = item.get("artifact") if isinstance(item, dict) else None
            if not reference:
                if isinstance(item, dict) and item.get("quality") == "unavailable":
                    continue
                raise MarketRegimeMacroDataError("macro snapshot factor lacks artifact")
            frozen = _read_artifact(self.root, reference)
            projected = {
                key: value
                for key, value in item.items()
                if key not in {"artifact", "refresh_status", "refresh_failure"}
            }
            if _canonical_json(projected) != _canonical_json(frozen):
                raise MarketRegimeMacroDataError("macro snapshot differs from artifact")
        return payload
