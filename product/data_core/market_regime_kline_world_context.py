"""Immutable completed-daily context for the cross-asset LLM world model.

This module does not call an LLM.  It turns already-verified daily, macro,
evidence-pack and Bitcoin artifacts into a bounded machine-readable tape: exact
OHLC/rate histories, deterministic multi-horizon features and a fixed registry
of relative-performance relationships.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
import statistics
import tempfile
from typing import Any, Mapping

from .market_regime_data import INSTRUMENTS, SCHEMA_VERSION as DAILY_SCHEMA_VERSION
from .market_regime_daily_evidence import SLOT_KEYS
from .market_regime_macro_data import (
    MACRO_FACTOR_BY_KEY,
    SCHEMA_VERSION as MACRO_SCHEMA_VERSION,
)


SCHEMA_VERSION = "market-regime-kline-world-context-v2"
ALIGNED_TAPE_SCHEMA_VERSION = "market-regime-kline-aligned-tape-v1"
CONTEXT_ID_PREFIX = "market-regime-kline-world-context:"
SERIES_ID_PREFIX = "market-regime-kline-series:"
SOURCE_SERIES_ID_PREFIX = "market-regime-kline-source-series:"
RELATIONSHIP_ID_PREFIX = "market-regime-kline-relationship:"
BITCOIN_ID_PREFIX = "market-regime-kline-bitcoin:"
SOURCE_LOOKBACK = 520
LOOKBACK = 300
FEATURE_WINDOWS = (5, 20, 60)
MAX_LLM_PROJECTION_BYTES = 750_000
DAILY_RUN_RE = re.compile(r"^market-regime-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}$")
MACRO_RUN_RE = re.compile(r"^market-regime-macro-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}$")

SERIES_ORDER = (
    "sp500",
    "nasdaq",
    "shanghai",
    "star50",
    "nikkei",
    "kospi",
    "us_dividend",
    "china_dividend",
    "wti",
    "gold",
    "silver",
    "bitcoin",
    "vix",
    "dxy",
    "us2y",
    "us10y",
    "us2s10s",
)
CANONICAL_KEYS = frozenset(SLOT_KEYS)
SUPPLEMENTAL_KEYS = frozenset({"bitcoin"})
RATE_KEYS = frozenset({"us2y", "us10y", "us2s10s"})
PRICE_KEYS = frozenset(SERIES_ORDER).difference(RATE_KEYS)

if len(SERIES_ORDER) != 17 or len(set(SERIES_ORDER)) != 17:  # pragma: no cover
    raise RuntimeError("world context requires exactly 17 unique series")
if CANONICAL_KEYS.union(SUPPLEMENTAL_KEYS) != frozenset(SERIES_ORDER):  # pragma: no cover
    raise RuntimeError("world context series do not match canonical plus supplemental inputs")


@dataclass(frozen=True)
class PairSpec:
    key: str
    lhs: str
    rhs: str
    question: str


PAIR_REGISTRY = (
    PairSpec("us_growth_vs_broad", "nasdaq", "sp500", "美国成长相对大盘是否取得领导权？"),
    PairSpec("a_tech_vs_broad", "star50", "shanghai", "A 股科技相对大盘是否取得领导权？"),
    PairSpec("us_dividend_vs_growth", "us_dividend", "nasdaq", "美国红利是否相对成长走强？"),
    PairSpec("a_dividend_vs_tech", "china_dividend", "star50", "A 股红利是否相对科技走强？"),
    PairSpec("korea_vs_japan", "kospi", "nikkei", "韩国是否相对日本取得区域领导权？"),
    PairSpec("us_vs_asia", "sp500", "nikkei", "美国大盘是否相对日本走强？"),
    PairSpec("us_vs_china", "sp500", "shanghai", "美国大盘是否相对 A 股走强？"),
    PairSpec("equity_vs_gold", "sp500", "gold", "风险资产是否相对黄金走强？"),
    PairSpec("gold_vs_oil", "gold", "wti", "货币型商品是否相对能源走强？"),
    PairSpec("silver_vs_gold", "silver", "gold", "白银是否相对黄金扩张风险偏好？"),
    PairSpec("bitcoin_vs_equity", "bitcoin", "sp500", "Bitcoin 是否相对美股走强？"),
    PairSpec("dollar_vs_gold", "dxy", "gold", "美元是否相对黄金走强？"),
)
PAIR_BY_KEY = {item.key: item for item in PAIR_REGISTRY}
if len(PAIR_BY_KEY) != len(PAIR_REGISTRY):  # pragma: no cover
    raise RuntimeError("world context relationship keys must be unique")


class KlineWorldContextError(RuntimeError):
    """A source, series, relationship, identity or store invariant failed."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (_canonical_json(value) + "\n").encode("utf-8")


def _digest(value: Any) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _finite(value: Any, *, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise KlineWorldContextError(f"invalid_number:{field}") from exc
    if not math.isfinite(number):
        raise KlineWorldContextError(f"invalid_number:{field}")
    return round(number, 6)


def _truth_boundary() -> dict[str, Any]:
    return {
        "track": "kline_only",
        "finance_newsletter_input": False,
        "local_evaluation_only": True,
        "observed_price_is_direct_flow": False,
        "market_advice_allowed": True,
        "automatic_execution_eligible": False,
        "publication_eligible": False,
    }


def _source_kind_allowed(item: Mapping[str, Any], *, allow_fixture: bool) -> None:
    kind = str(item.get("data_kind") or "")
    if kind == "real":
        return
    if allow_fixture and kind == "fixture":
        return
    raise KlineWorldContextError("fixture_or_unknown_source_forbidden")


def _validate_dates(points: list[dict[str, Any]], *, key: str) -> None:
    dates = [str(row.get("date") or "") for row in points]
    if not dates or any(not value for value in dates) or dates != sorted(dates):
        raise KlineWorldContextError(f"series_dates_invalid:{key}")
    if len(dates) != len(set(dates)):
        raise KlineWorldContextError(f"series_dates_duplicate:{key}")


def _return(values: list[float], periods: int) -> float:
    if len(values) <= periods or values[-periods - 1] == 0:
        raise KlineWorldContextError("feature_history_too_short")
    return round((values[-1] / values[-periods - 1] - 1) * 100, 6)


def _price_features(values: list[float]) -> dict[str, Any]:
    if len(values) < LOOKBACK:
        raise KlineWorldContextError("price_history_too_short")
    if any(value <= 0 for value in values):
        raise KlineWorldContextError("price_value_must_be_positive")
    returns = {f"return_{window}d_pct": _return(values, window) for window in FEATURE_WINDOWS}
    ma20 = statistics.fmean(values[-20:])
    ma60 = statistics.fmean(values[-60:])
    peak = max(values)
    log_returns = [math.log(values[index] / values[index - 1]) for index in range(len(values) - 20, len(values))]
    realized = statistics.pstdev(log_returns) * math.sqrt(252) * 100 if len(log_returns) > 1 else 0.0
    return {
        **returns,
        "distance_ma20_pct": round((values[-1] / ma20 - 1) * 100, 6),
        "distance_ma60_pct": round((values[-1] / ma60 - 1) * 100, 6),
        "drawdown_300d_pct": round((values[-1] / peak - 1) * 100, 6),
        "realized_vol_20d_pct": round(realized, 6),
        "trend_60d": "up" if returns["return_60d_pct"] > 1 else "down" if returns["return_60d_pct"] < -1 else "flat",
    }


def _rate_features(values: list[float], *, level_unit: str) -> dict[str, Any]:
    if len(values) < LOOKBACK:
        raise KlineWorldContextError("rate_history_too_short")
    scale = 100 if level_unit == "percent" else 1
    changes = {
        f"change_{window}d_bp": round((values[-1] - values[-window - 1]) * scale, 6)
        for window in FEATURE_WINDOWS
    }
    high_distance = (values[-1] - max(values)) * scale
    low_distance = (values[-1] - min(values)) * scale
    return {
        **changes,
        "distance_from_300d_high_bp": round(high_distance, 6),
        "distance_from_300d_low_bp": round(low_distance, 6),
        "trend_60d": "up" if changes["change_60d_bp"] > 5 else "down" if changes["change_60d_bp"] < -5 else "flat",
    }


def _slot_map(pack: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    slots = pack.get("slots")
    if not isinstance(slots, list) or [item.get("key") for item in slots if isinstance(item, dict)] != list(SLOT_KEYS):
        raise KlineWorldContextError("evidence_slots_invalid")
    result = {str(item["key"]): item for item in slots if isinstance(item, dict)}
    if len(result) != len(SLOT_KEYS) or any(not result[key].get("evidence_id") for key in SLOT_KEYS):
        raise KlineWorldContextError("evidence_slot_unavailable")
    return result


def _read_bound_json(root: Path, relative: str, expected_hash: str) -> dict[str, Any]:
    target = (root / relative).resolve()
    if root not in target.parents or len(expected_hash) != 64:
        raise KlineWorldContextError("source_artifact_reference_invalid")
    try:
        encoded = target.read_bytes()
        value = json.loads(encoded)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise KlineWorldContextError("source_artifact_unavailable") from exc
    if sha256(encoded).hexdigest() != expected_hash:
        raise KlineWorldContextError("source_artifact_hash_mismatch")
    if not isinstance(value, dict):
        raise KlineWorldContextError("source_artifact_not_object")
    return value


def load_context_source_snapshots(
    *,
    daily_root: Path | str,
    macro_root: Path | str,
    pack: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Reload exact immutable source artifacts referenced by a frozen S3 pack.

    Never joins independently moving ``latest`` pointers.  This makes a later
    context compile replay-safe even when the daily collector has already
    advanced after the evidence pack was frozen.
    """
    daily_base = Path(daily_root).expanduser().resolve()
    macro_base = Path(macro_root).expanduser().resolve()
    pack_inputs = pack.get("inputs") or {}
    daily_run = str(pack_inputs.get("daily_run_id") or "")
    macro_run = str(pack_inputs.get("macro_run_id") or "")
    if not DAILY_RUN_RE.fullmatch(daily_run) or not MACRO_RUN_RE.fullmatch(macro_run):
        raise KlineWorldContextError("source_run_identity_invalid")
    slots = _slot_map(pack)

    daily_items = []
    for spec in INSTRUMENTS:
        source_identity = slots[spec.key].get("source_identity") or {}
        expected_hash = str(source_identity.get("normalized_artifact_sha256") or "")
        relative = f"normalized/{daily_run}/{spec.key}.json"
        artifact = _read_bound_json(daily_base, relative, expected_hash)
        if (
            artifact.get("schema_version") != DAILY_SCHEMA_VERSION
            or artifact.get("run_id") != daily_run
            or _canonical_json(artifact.get("instrument")) != _canonical_json(asdict(spec))
            or artifact.get("data_kind") != "real"
        ):
            raise KlineWorldContextError(f"daily_source_artifact_mismatch:{spec.key}")
        daily_items.append(
            {
                **artifact,
                "normalized_artifact": {
                    "path": relative,
                    "sha256": expected_hash,
                    "schema_version": DAILY_SCHEMA_VERSION,
                },
            }
        )

    macro_items = []
    for key, spec in MACRO_FACTOR_BY_KEY.items():
        source_identity = slots[key].get("source_identity") or {}
        expected_hash = str(source_identity.get("artifact_sha256") or "")
        expected_factor = str(source_identity.get("factor_id") or "")
        relative = f"normalized/{macro_run}/{key}.json"
        artifact = _read_bound_json(macro_base, relative, expected_hash)
        if (
            artifact.get("schema_version") != MACRO_SCHEMA_VERSION
            or artifact.get("run_id") != macro_run
            or _canonical_json(artifact.get("factor")) != _canonical_json(asdict(spec))
            or artifact.get("factor_id") != expected_factor
            or artifact.get("data_kind") != "real"
        ):
            raise KlineWorldContextError(f"macro_source_artifact_mismatch:{key}")
        macro_items.append(
            {
                **artifact,
                "artifact": {
                    "path": relative,
                    "sha256": expected_hash,
                    "schema_version": MACRO_SCHEMA_VERSION,
                    "factor_id": expected_factor,
                },
            }
        )
    return (
        {
            "schema_version": DAILY_SCHEMA_VERSION,
            "run_id": daily_run,
            "quality": "fresh" if all(item.get("quality") == "fresh" for item in daily_items) else "partial",
            "instrument_count": len(daily_items),
            "instruments": daily_items,
        },
        {
            "schema_version": MACRO_SCHEMA_VERSION,
            "run_id": macro_run,
            "quality": "fresh" if all(item.get("quality") == "fresh" for item in macro_items) else "partial",
            "factor_count": len(macro_items),
            "factors": macro_items,
            "publication_eligible": False,
            "action_eligible": False,
        },
    )


def build_kline_world_context_from_roots(
    *,
    daily_root: Path | str,
    macro_root: Path | str,
    pack: Mapping[str, Any],
    bitcoin: Mapping[str, Any],
) -> dict[str, Any]:
    daily, macro = load_context_source_snapshots(
        daily_root=daily_root,
        macro_root=macro_root,
        pack=pack,
    )
    return build_kline_world_context(
        daily=daily,
        macro=macro,
        pack=pack,
        bitcoin=bitcoin,
    )


def _price_series(
    item: Mapping[str, Any],
    *,
    key: str,
    display_name: str,
    level_unit: str,
    role: str,
    evidence_id: str | None,
    source_identity: Mapping[str, Any],
    allow_fixture: bool,
) -> dict[str, Any]:
    _source_kind_allowed(item, allow_fixture=allow_fixture)
    artifact_hash = str(source_identity.get("artifact_sha256") or "")
    bitcoin_id = str(source_identity.get("bitcoin_id") or "")
    if len(artifact_hash) != 64 and not bitcoin_id.startswith("market-regime-kline-bitcoin:"):
        raise KlineWorldContextError(f"series_source_identity_invalid:{key}")
    bars = item.get("bars")
    if not isinstance(bars, list) or len(bars) < LOOKBACK:
        raise KlineWorldContextError(f"series_history_too_short:{key}")
    selected: list[dict[str, Any]] = []
    for raw in bars[-SOURCE_LOOKBACK:]:
        if not isinstance(raw, dict):
            raise KlineWorldContextError(f"series_row_invalid:{key}")
        row = {
            "date": str(raw.get("date") or ""),
            "open": _finite(raw.get("open"), field=f"{key}.open"),
            "high": _finite(raw.get("high"), field=f"{key}.high"),
            "low": _finite(raw.get("low"), field=f"{key}.low"),
            "close": _finite(raw.get("close"), field=f"{key}.close"),
        }
        if row["low"] > min(row["open"], row["close"]) or row["high"] < max(row["open"], row["close"]):
            raise KlineWorldContextError(f"series_ohlc_invalid:{key}")
        if raw.get("volume") is not None:
            row["volume"] = _finite(raw.get("volume"), field=f"{key}.volume")
        selected.append(row)
    _validate_dates(selected, key=key)
    actual_session = str(item.get("last_completed_session") or selected[-1]["date"])
    if actual_session != selected[-1]["date"]:
        raise KlineWorldContextError(f"series_session_mismatch:{key}")
    core = {
        "key": key,
        "display_name": display_name,
        "role": role,
        "series_type": "ohlc",
        "level_unit": level_unit,
        "change_unit": "percent_return",
        "session": actual_session,
        "close_at": str(item.get("last_completed_close_at") or ""),
        "quality": str(item.get("quality") or "unavailable"),
        "evidence_id": evidence_id,
        "source_identity": dict(source_identity),
        "points": selected,
    }
    if core["quality"] not in {"fresh", "partial", "stale"}:
        raise KlineWorldContextError(f"series_unavailable:{key}")
    return {
        "source_series_id": f"{SOURCE_SERIES_ID_PREFIX}{key}:{_digest(core)}",
        **core,
    }


def _rate_series(
    item: Mapping[str, Any],
    *,
    key: str,
    evidence_id: str,
    allow_fixture: bool,
) -> dict[str, Any]:
    _source_kind_allowed(item, allow_fixture=allow_fixture)
    if len(str((item.get("artifact") or {}).get("sha256") or "")) != 64:
        raise KlineWorldContextError(f"series_source_identity_invalid:{key}")
    spec = MACRO_FACTOR_BY_KEY[key]
    observations = item.get("observations")
    if not isinstance(observations, list) or len(observations) < LOOKBACK:
        raise KlineWorldContextError(f"series_history_too_short:{key}")
    points = [
        {"date": str(raw.get("date") or ""), "value": _finite(raw.get("value"), field=f"{key}.value")}
        for raw in observations[-SOURCE_LOOKBACK:]
        if isinstance(raw, dict)
    ]
    if len(points) < LOOKBACK:
        raise KlineWorldContextError(f"series_row_invalid:{key}")
    _validate_dates(points, key=key)
    actual_session = str(item.get("last_completed_session") or points[-1]["date"])
    if actual_session != points[-1]["date"]:
        raise KlineWorldContextError(f"series_session_mismatch:{key}")
    core = {
        "key": key,
        "display_name": spec.display_name,
        "role": "canonical",
        "series_type": "rate_level",
        "level_unit": spec.level_unit,
        "change_unit": "basis_points",
        "session": actual_session,
        "close_at": str(item.get("last_completed_close_at") or ""),
        "quality": str(item.get("quality") or "unavailable"),
        "evidence_id": evidence_id,
        "source_identity": {
            "run_id": item.get("run_id"),
            "factor_id": item.get("factor_id"),
            "artifact_sha256": (item.get("artifact") or {}).get("sha256"),
        },
        "points": points,
    }
    if core["quality"] not in {"fresh", "partial", "stale"}:
        raise KlineWorldContextError(f"series_unavailable:{key}")
    return {
        "source_series_id": f"{SOURCE_SERIES_ID_PREFIX}{key}:{_digest(core)}",
        **core,
    }


def _common_as_of(series: Mapping[str, Mapping[str, Any]]) -> str:
    date_sets = [
        {str(row.get("date") or "") for row in item.get("points") or []}
        for item in series.values()
    ]
    common = set.intersection(*date_sets) if date_sets else set()
    common.discard("")
    if not common:
        raise KlineWorldContextError("context_alignment_unavailable")
    as_of = max(common)
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", as_of):
        raise KlineWorldContextError("context_alignment_date_invalid")
    return as_of


def _aligned_series(item: Mapping[str, Any], *, as_of: str) -> dict[str, Any]:
    key = str(item.get("key") or "")
    eligible = [row for row in item.get("points") or [] if str(row.get("date") or "") <= as_of]
    if len(eligible) < LOOKBACK:
        raise KlineWorldContextError(f"aligned_history_too_short:{key}")
    points = [dict(row) for row in eligible[-LOOKBACK:]]
    _validate_dates(points, key=key)
    actual_session = str(item.get("session") or "")
    discarded = sum(
        str(row.get("date") or "") > as_of for row in item.get("points") or []
    )
    source_quality = str(item.get("quality") or "unavailable")
    quality = (
        "stale"
        if source_quality == "stale"
        else "fresh"
        if actual_session == as_of and source_quality == "fresh"
        else "partial"
    )
    rate = item.get("series_type") == "rate_level"
    values = [float(row["value"] if rate else row["close"]) for row in points]
    core = {
        "key": key,
        "display_name": item.get("display_name"),
        "role": item.get("role"),
        "series_type": item.get("series_type"),
        "level_unit": item.get("level_unit"),
        "change_unit": item.get("change_unit"),
        "session": as_of,
        "close_at": item.get("close_at") if actual_session == as_of else "",
        "actual_latest_session": actual_session,
        "actual_latest_close_at": item.get("close_at"),
        "actual_latest_equals_as_of": actual_session == as_of,
        "alignment_status": "at_as_of" if actual_session == as_of else "ahead_of_as_of",
        "discarded_post_as_of_sessions": discarded,
        "source_history_sessions": len(item.get("points") or []),
        "source_quality": source_quality,
        "quality": quality,
        "evidence_id": item.get("evidence_id"),
        "source_identity": {
            **dict(item.get("source_identity") or {}),
            "source_series_id": item.get("source_series_id"),
        },
        "points": points,
        "features": (
            _rate_features(values, level_unit=str(item.get("level_unit") or ""))
            if rate
            else _price_features(values)
        ),
    }
    return {"series_id": f"{SERIES_ID_PREFIX}{key}:{_digest(core)}", **core}


def _relationship(spec: PairSpec, series: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    lhs, rhs = series[spec.lhs], series[spec.rhs]
    lhs_by_date = {row["date"]: row["close"] for row in lhs["points"]}
    rhs_by_date = {row["date"]: row["close"] for row in rhs["points"]}
    common = sorted(set(lhs_by_date).intersection(rhs_by_date))
    if len(common) < 61:
        raise KlineWorldContextError(f"relationship_history_too_short:{spec.key}")
    common = common[-LOOKBACK:]
    lhs_start, rhs_start = lhs_by_date[common[0]], rhs_by_date[common[0]]
    if lhs_start == 0 or rhs_start == 0:
        raise KlineWorldContextError(f"relationship_zero_reference:{spec.key}")
    points = []
    for session in common:
        lhs_normalized = lhs_by_date[session] / lhs_start * 100
        rhs_normalized = rhs_by_date[session] / rhs_start * 100
        points.append(
            {
                "date": session,
                "relative_index": round(lhs_normalized / rhs_normalized * 100, 6),
            }
        )
    values = [row["relative_index"] for row in points]
    changes = {
        f"relative_change_{window}d_pct": _return(values, window)
        for window in FEATURE_WINDOWS
    }
    core = {
        "key": spec.key,
        "lhs": spec.lhs,
        "rhs": spec.rhs,
        "question": spec.question,
        "semantics": "normalized_relative_performance_not_literal_fund_flow",
        "lhs_series_id": lhs["series_id"],
        "rhs_series_id": rhs["series_id"],
        "points": points,
        "features": {
            **changes,
            "leader_20d": spec.lhs if changes["relative_change_20d_pct"] > 0.5 else spec.rhs if changes["relative_change_20d_pct"] < -0.5 else "balanced",
        },
    }
    return {
        "relationship_id": f"{RELATIONSHIP_ID_PREFIX}{spec.key}:{_digest(core)}",
        **core,
    }


def build_kline_world_context(
    *,
    daily: Mapping[str, Any],
    macro: Mapping[str, Any],
    pack: Mapping[str, Any],
    bitcoin: Mapping[str, Any],
    allow_fixture: bool = False,
) -> dict[str, Any]:
    """Compile one deterministic world-model context from verified artifacts."""
    pack_inputs = pack.get("inputs") or {}
    if pack_inputs.get("daily_run_id") != daily.get("run_id"):
        raise KlineWorldContextError("daily_pack_identity_mismatch")
    if pack_inputs.get("macro_run_id") != macro.get("run_id"):
        raise KlineWorldContextError("macro_pack_identity_mismatch")
    pack_id = str(pack.get("pack_id") or "")
    bitcoin_id = str(bitcoin.get("bitcoin_id") or "")
    if not pack_id.startswith("market-regime-daily-evidence:"):
        raise KlineWorldContextError("pack_identity_invalid")
    if not bitcoin_id.startswith(BITCOIN_ID_PREFIX):
        raise KlineWorldContextError("bitcoin_identity_invalid")
    bitcoin_core = bitcoin.get("identity_core")
    if not allow_fixture:
        if not isinstance(bitcoin_core, dict) or bitcoin_id != f"{BITCOIN_ID_PREFIX}{_digest(bitcoin_core)}":
            raise KlineWorldContextError("bitcoin_identity_core_mismatch")
        if any(bitcoin.get(key) != value for key, value in bitcoin_core.items()):
            raise KlineWorldContextError("bitcoin_identity_projection_mismatch")
    slots = _slot_map(pack)
    daily_items = {
        str((item.get("instrument") or {}).get("key")): item
        for item in daily.get("instruments") or []
        if isinstance(item, dict)
    }
    macro_items = {
        str((item.get("factor") or {}).get("key")): item
        for item in macro.get("factors") or []
        if isinstance(item, dict)
    }
    if set(daily_items) != {item.key for item in INSTRUMENTS}:
        raise KlineWorldContextError("daily_universe_mismatch")
    if set(macro_items) != set(MACRO_FACTOR_BY_KEY):
        raise KlineWorldContextError("macro_universe_mismatch")
    instrument_by_key = {item.key: item for item in INSTRUMENTS}
    if any(_canonical_json(daily_items[key].get("instrument")) != _canonical_json(asdict(spec)) for key, spec in instrument_by_key.items()):
        raise KlineWorldContextError("daily_registry_mismatch")
    if any(_canonical_json(macro_items[key].get("factor")) != _canonical_json(asdict(spec)) for key, spec in MACRO_FACTOR_BY_KEY.items()):
        raise KlineWorldContextError("macro_registry_mismatch")

    source_kinds = {
        str(item.get("data_kind") or "unknown")
        for item in [*daily_items.values(), *macro_items.values(), bitcoin]
    }
    data_kind = "real" if source_kinds == {"real"} else "fixture" if allow_fixture and source_kinds.issubset({"real", "fixture"}) else "unknown"

    source_by_key: dict[str, dict[str, Any]] = {}
    for key, spec in instrument_by_key.items():
        item = daily_items[key]
        source_by_key[key] = _price_series(
            item,
            key=key,
            display_name=spec.display_name,
            level_unit=spec.unit,
            role="canonical",
            evidence_id=str(slots[key]["evidence_id"]),
            source_identity={
                "run_id": item.get("run_id"),
                "artifact_sha256": (item.get("normalized_artifact") or {}).get("sha256"),
            },
            allow_fixture=allow_fixture,
        )
    dxy = macro_items["dxy"]
    source_by_key["dxy"] = _price_series(
        dxy,
        key="dxy",
        display_name=MACRO_FACTOR_BY_KEY["dxy"].display_name,
        level_unit=MACRO_FACTOR_BY_KEY["dxy"].level_unit,
        role="canonical",
        evidence_id=str(slots["dxy"]["evidence_id"]),
        source_identity={
            "run_id": dxy.get("run_id"),
            "factor_id": dxy.get("factor_id"),
            "artifact_sha256": (dxy.get("artifact") or {}).get("sha256"),
        },
        allow_fixture=allow_fixture,
    )
    for key in RATE_KEYS:
        source_by_key[key] = _rate_series(
            macro_items[key],
            key=key,
            evidence_id=str(slots[key]["evidence_id"]),
            allow_fixture=allow_fixture,
        )
    bitcoin_instrument = bitcoin.get("instrument") or {}
    source_by_key["bitcoin"] = _price_series(
        bitcoin,
        key="bitcoin",
        display_name=str(bitcoin_instrument.get("display_name") or "Bitcoin"),
        level_unit=str(bitcoin.get("level_unit") or bitcoin_instrument.get("unit") or "USD/coin"),
        role="supplemental",
        evidence_id=None,
        source_identity={"bitcoin_id": bitcoin_id},
        allow_fixture=allow_fixture,
    )

    as_of = _common_as_of(source_by_key)
    by_key = {
        key: _aligned_series(source_by_key[key], as_of=as_of)
        for key in SERIES_ORDER
    }
    source_series = [source_by_key[key] for key in SERIES_ORDER]
    series = [by_key[key] for key in SERIES_ORDER]
    relationships = [_relationship(spec, by_key) for spec in PAIR_REGISTRY]
    qualities = [item["quality"] for item in series]
    core = {
        "schema_version": SCHEMA_VERSION,
        "compiler_version": SCHEMA_VERSION,
        "lookback": LOOKBACK,
        "source_lookback": SOURCE_LOOKBACK,
        "alignment": {
            "schema_version": ALIGNED_TAPE_SCHEMA_VERSION,
            "as_of": as_of,
            "required_sessions_per_series": LOOKBACK,
            "series_count": len(series),
            "relationship_count": len(relationships),
        },
        "inputs": {
            "daily_run_id": daily.get("run_id"),
            "macro_run_id": macro.get("run_id"),
            "pack_id": pack_id,
            "bitcoin_id": bitcoin_id,
        },
        "data_kind": data_kind,
        "quality": "fresh" if all(value == "fresh" for value in qualities) else "partial",
        "source_time": pack.get("time"),
        "time": {
            "as_of": as_of,
            "semantics": "latest_exact_completed_session_shared_by_all_17_series",
        },
        "coverage": {"accepted": len(series), "total": len(SERIES_ORDER), "ratio": 1.0},
        "agreement_inputs": pack.get("agreement_inputs"),
        "confidence_inputs": pack.get("confidence_inputs"),
        "contradiction_candidates": pack.get("contradiction_candidates"),
        "source_series": source_series,
        "series": series,
        "relationships": relationships,
        "truth_boundary": _truth_boundary(),
    }
    context_id = f"{CONTEXT_ID_PREFIX}{_digest(core)}"
    context = {"context_id": context_id, "identity_core": core, **core}
    context["llm_projection"] = build_llm_projection(context)
    return context


def build_llm_projection(context: Mapping[str, Any]) -> dict[str, Any]:
    """Return the exact bounded provider input; omit storage paths/receipts."""
    series = []
    for item in context.get("series") or []:
        series.append(
            {
                key: item.get(key)
                for key in (
                    "series_id",
                    "key",
                    "display_name",
                    "role",
                    "series_type",
                    "level_unit",
                    "change_unit",
                    "session",
                    "close_at",
                    "actual_latest_session",
                    "actual_latest_close_at",
                    "actual_latest_equals_as_of",
                    "alignment_status",
                    "discarded_post_as_of_sessions",
                    "source_history_sessions",
                    "source_quality",
                    "quality",
                    "evidence_id",
                    "points",
                    "features",
                )
            }
        )
    relationships = [
        {
            key: item.get(key)
            for key in (
                "relationship_id",
                "key",
                "lhs",
                "rhs",
                "question",
                "semantics",
                "points",
                "features",
            )
        }
        for item in context.get("relationships") or []
    ]
    projection = {
        "schema_version": SCHEMA_VERSION,
        "context_id": context.get("context_id"),
        "task": "Interpret the frozen completed-daily cross-asset tape as one capital-rotation world model.",
        "claim_classes": ["observed", "inferred", "recommended"],
        "time": context.get("time"),
        "alignment": context.get("alignment"),
        "coverage": context.get("coverage"),
        "data_kind": context.get("data_kind"),
        "series": series,
        "relationships": relationships,
        "truth_boundary": context.get("truth_boundary"),
    }
    if len(_canonical_json(projection).encode("utf-8")) > MAX_LLM_PROJECTION_BYTES:
        raise KlineWorldContextError("context_llm_projection_too_large")
    return projection


def validate_kline_world_context(context: Mapping[str, Any]) -> dict[str, Any]:
    if context.get("schema_version") != SCHEMA_VERSION:
        raise KlineWorldContextError("context_schema_mismatch")
    core = context.get("identity_core")
    if not isinstance(core, dict):
        raise KlineWorldContextError("context_identity_core_missing")
    expected_id = f"{CONTEXT_ID_PREFIX}{_digest(core)}"
    if context.get("context_id") != expected_id:
        raise KlineWorldContextError("context_identity_mismatch")
    for key, value in core.items():
        if context.get(key) != value:
            raise KlineWorldContextError("context_projection_mismatch")
    if core.get("truth_boundary") != _truth_boundary():
        raise KlineWorldContextError("context_truth_boundary_mismatch")
    if core.get("data_kind") not in {"real", "fixture"}:
        raise KlineWorldContextError("context_data_kind_invalid")
    alignment = core.get("alignment")
    if (
        not isinstance(alignment, dict)
        or alignment.get("schema_version") != ALIGNED_TAPE_SCHEMA_VERSION
        or alignment.get("required_sessions_per_series") != LOOKBACK
        or alignment.get("series_count") != len(SERIES_ORDER)
        or alignment.get("relationship_count") != len(PAIR_REGISTRY)
    ):
        raise KlineWorldContextError("context_alignment_invalid")
    as_of = str(alignment.get("as_of") or "")
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", as_of):
        raise KlineWorldContextError("context_alignment_date_invalid")
    source_series = core.get("source_series")
    if not isinstance(source_series, list) or [item.get("key") for item in source_series if isinstance(item, dict)] != list(SERIES_ORDER):
        raise KlineWorldContextError("context_source_series_order_mismatch")
    source_by_key: dict[str, dict[str, Any]] = {}
    for item in source_series:
        if not isinstance(item, dict):
            raise KlineWorldContextError("context_source_series_invalid")
        key = str(item.get("key") or "")
        item_core = {field: value for field, value in item.items() if field != "source_series_id"}
        if item.get("source_series_id") != f"{SOURCE_SERIES_ID_PREFIX}{key}:{_digest(item_core)}":
            raise KlineWorldContextError("context_source_series_identity_mismatch")
        if not LOOKBACK <= len(item.get("points") or []) <= SOURCE_LOOKBACK:
            raise KlineWorldContextError("context_source_series_lookback_mismatch")
        points = item.get("points") or []
        if any(not isinstance(row, dict) for row in points):
            raise KlineWorldContextError("context_source_series_row_invalid")
        _validate_dates(points, key=key)
        if item.get("session") != points[-1].get("date"):
            raise KlineWorldContextError("context_source_series_session_mismatch")
        rate = key in RATE_KEYS
        expected_fields = {"date", "value"} if rate else {"date", "open", "high", "low", "close"}
        for row in points:
            if not expected_fields.issubset(row) or set(row) - (expected_fields | ({"volume"} if not rate else set())):
                raise KlineWorldContextError("context_source_series_row_invalid")
            if rate:
                _finite(row.get("value"), field=f"{key}.value")
            else:
                opened = _finite(row.get("open"), field=f"{key}.open")
                high = _finite(row.get("high"), field=f"{key}.high")
                low = _finite(row.get("low"), field=f"{key}.low")
                closed = _finite(row.get("close"), field=f"{key}.close")
                if low > min(opened, closed) or high < max(opened, closed):
                    raise KlineWorldContextError("context_source_series_ohlc_invalid")
                if row.get("volume") is not None:
                    _finite(row.get("volume"), field=f"{key}.volume")
        source_by_key[key] = item
    derived_as_of = _common_as_of(source_by_key)
    expected_alignment = {
        "schema_version": ALIGNED_TAPE_SCHEMA_VERSION,
        "as_of": derived_as_of,
        "required_sessions_per_series": LOOKBACK,
        "series_count": len(SERIES_ORDER),
        "relationship_count": len(PAIR_REGISTRY),
    }
    if alignment != expected_alignment:
        raise KlineWorldContextError("context_alignment_derivation_mismatch")
    expected_by_key = {
        key: _aligned_series(source_by_key[key], as_of=derived_as_of)
        for key in SERIES_ORDER
    }
    expected_series = [expected_by_key[key] for key in SERIES_ORDER]
    if core.get("series") != expected_series:
        raise KlineWorldContextError("context_series_derivation_mismatch")
    expected_relationships = [
        _relationship(spec, expected_by_key) for spec in PAIR_REGISTRY
    ]
    if core.get("relationships") != expected_relationships:
        raise KlineWorldContextError("context_relationship_derivation_mismatch")
    series = core.get("series")
    if not isinstance(series, list) or [item.get("key") for item in series if isinstance(item, dict)] != list(SERIES_ORDER):
        raise KlineWorldContextError("context_series_order_mismatch")
    for item in series:
        if not isinstance(item, dict):
            raise KlineWorldContextError("context_series_invalid")
        key = str(item.get("key") or "")
        item_core = {field: value for field, value in item.items() if field != "series_id"}
        if item.get("series_id") != f"{SERIES_ID_PREFIX}{key}:{_digest(item_core)}":
            raise KlineWorldContextError("context_series_identity_mismatch")
        if len(item.get("points") or []) != LOOKBACK:
            raise KlineWorldContextError("context_series_lookback_mismatch")
        if item.get("session") != as_of or (item.get("points") or [])[-1].get("date") != as_of:
            raise KlineWorldContextError("context_series_as_of_mismatch")
        if item.get("actual_latest_equals_as_of") != (item.get("actual_latest_session") == as_of):
            raise KlineWorldContextError("context_series_alignment_flag_mismatch")
        if key in CANONICAL_KEYS and not item.get("evidence_id"):
            raise KlineWorldContextError("context_canonical_evidence_missing")
        if key in SUPPLEMENTAL_KEYS and item.get("role") != "supplemental":
            raise KlineWorldContextError("context_supplement_role_mismatch")
    relationships = core.get("relationships")
    if not isinstance(relationships, list) or [item.get("key") for item in relationships if isinstance(item, dict)] != [item.key for item in PAIR_REGISTRY]:
        raise KlineWorldContextError("context_relationship_order_mismatch")
    for item in relationships:
        key = str(item.get("key") or "")
        item_core = {field: value for field, value in item.items() if field != "relationship_id"}
        if item.get("relationship_id") != f"{RELATIONSHIP_ID_PREFIX}{key}:{_digest(item_core)}":
            raise KlineWorldContextError("context_relationship_identity_mismatch")
    if context.get("llm_projection") != build_llm_projection(context):
        raise KlineWorldContextError("context_llm_projection_mismatch")
    return dict(context)


def _atomic_bytes(path: Path, encoded: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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


def _immutable_bytes(path: Path, encoded: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != encoded:
            raise KlineWorldContextError("immutable_context_collision")
        return sha256(encoded).hexdigest()
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


class KlineWorldContextStore:
    """Publish immutable context and receipt before atomically advancing latest."""

    def __init__(self, root: Path | str, *, allow_fixture: bool = False) -> None:
        self.root = Path(root).expanduser().resolve()
        self.allow_fixture = allow_fixture

    def publish(self, context: Mapping[str, Any]) -> dict[str, Any]:
        validated = validate_kline_world_context(context)
        if validated.get("data_kind") != "real" and not self.allow_fixture:
            raise KlineWorldContextError("fixture_context_publication_forbidden")
        digest = str(validated["context_id"]).removeprefix(CONTEXT_ID_PREFIX)
        artifact_relative = f"artifacts/{digest}.json"
        artifact_bytes = _json_bytes(validated)
        artifact_hash = _immutable_bytes(self.root / artifact_relative, artifact_bytes)
        receipt = {
            "schema_version": SCHEMA_VERSION,
            "event": "completed",
            "context_id": validated["context_id"],
            "inputs": validated["inputs"],
            "artifact": {"path": artifact_relative, "sha256": artifact_hash},
            "truth_boundary": _truth_boundary(),
        }
        receipt_relative = f"receipts/{digest}.json"
        receipt_hash = _immutable_bytes(self.root / receipt_relative, _json_bytes(receipt))
        pointer = {
            "schema_version": SCHEMA_VERSION,
            "context_id": validated["context_id"],
            "artifact": receipt["artifact"],
            "receipt": {"path": receipt_relative, "sha256": receipt_hash},
        }
        latest_path = self.root / "latest.json"
        prior = latest_path.read_bytes() if latest_path.exists() else None
        _atomic_bytes(latest_path, _json_bytes(pointer))
        try:
            self.latest()
        except Exception:
            if prior is None:
                latest_path.unlink(missing_ok=True)
            else:
                _atomic_bytes(latest_path, prior)
            raise
        return pointer

    def latest(self) -> dict[str, Any]:
        try:
            pointer_bytes = (self.root / "latest.json").read_bytes()
            pointer = json.loads(pointer_bytes)
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            raise KlineWorldContextError("context_latest_unavailable") from exc
        if not isinstance(pointer, dict) or pointer.get("schema_version") != SCHEMA_VERSION:
            raise KlineWorldContextError("context_pointer_invalid")
        context_id = str(pointer.get("context_id") or "")
        if not context_id.startswith(CONTEXT_ID_PREFIX):
            raise KlineWorldContextError("context_pointer_identity_invalid")
        digest = context_id.removeprefix(CONTEXT_ID_PREFIX)
        artifact_ref, receipt_ref = pointer.get("artifact") or {}, pointer.get("receipt") or {}
        if artifact_ref.get("path") != f"artifacts/{digest}.json" or receipt_ref.get("path") != f"receipts/{digest}.json":
            raise KlineWorldContextError("context_pointer_path_invalid")
        artifact_target = (self.root / str(artifact_ref.get("path"))).resolve()
        receipt_target = (self.root / str(receipt_ref.get("path"))).resolve()
        if self.root not in artifact_target.parents or self.root not in receipt_target.parents:
            raise KlineWorldContextError("context_pointer_path_escape")
        try:
            artifact_bytes = artifact_target.read_bytes()
            receipt_bytes = receipt_target.read_bytes()
            artifact = json.loads(artifact_bytes)
            receipt = json.loads(receipt_bytes)
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            raise KlineWorldContextError("context_artifact_unavailable") from exc
        if sha256(artifact_bytes).hexdigest() != artifact_ref.get("sha256"):
            raise KlineWorldContextError("context_artifact_hash_mismatch")
        if sha256(receipt_bytes).hexdigest() != receipt_ref.get("sha256"):
            raise KlineWorldContextError("context_receipt_hash_mismatch")
        validated = validate_kline_world_context(artifact)
        expected_receipt = {
            "schema_version": SCHEMA_VERSION,
            "event": "completed",
            "context_id": validated["context_id"],
            "inputs": validated["inputs"],
            "artifact": artifact_ref,
            "truth_boundary": _truth_boundary(),
        }
        if receipt != expected_receipt or validated["context_id"] != context_id:
            raise KlineWorldContextError("context_receipt_identity_mismatch")
        return validated
