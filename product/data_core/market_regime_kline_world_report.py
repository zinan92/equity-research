"""Versioned white vertical report for the K-line Macro Analyst.

The renderer is intentionally separate from the installed pilot newsletter.
It projects one exact S1 context and one exact S2 model artifact, renders every
input that influenced the model, and never calls a broker or mutates a portfolio.
"""

from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from html import escape
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo
import json
import math
import os
import tempfile

from .market_regime_kline_world_context import (
    CONTEXT_ID_PREFIX,
    LOOKBACK,
    SCHEMA_VERSION as CONTEXT_SCHEMA_VERSION,
    KlineWorldContextError,
    KlineWorldContextStore,
    SERIES_ORDER,
    validate_kline_world_context,
)
from .market_regime_kline_macro_analysis import (
    KlineWorldModelError,
    KlineWorldModelStore,
    validate_world_model_artifact,
)
from .market_regime_kline_world_model import MODEL_ID_PREFIX


SCHEMA_VERSION = "market-regime-kline-world-report-v4"
RENDERER_VERSION = "market-regime-kline-world-report-renderer-v7"
REPORT_ID_PREFIX = "market-regime-kline-world-report:"
SHANGHAI = ZoneInfo("Asia/Shanghai")
PARAMETER_SURFACE_ORDER = (
    "AS_OF",
    "RISK_BUDGET",
    "LONG_GATE",
    "DISPERSION",
    "SECTOR_PRIOR",
    "BLACKOUT",
    "CONFIDENCE",
    "DATA_COVERAGE",
)

POSTURE_ZH = {"attack": "进攻", "wait": "等待", "defense": "防守", "no_view": "无方向观点", "unknown": "未知"}
POSTURE_EN = {"attack": "ATTACK", "wait": "WAIT", "defense": "DEFENSE", "no_view": "NO VIEW", "unknown": "UNKNOWN"}
CLAIM_ZH = {"fact": "事实", "inference": "推断", "unknown": "未知"}
CONFIDENCE_ZH = {"high": "高", "medium": "中", "low": "低"}


class KlineWorldReportError(RuntimeError):
    """An upstream, identity, rendering or immutable-store invariant failed."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (_canonical_json(value) + "\n").encode("utf-8")


def _digest(value: Any) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise KlineWorldReportError("generated_at_timezone_required")
    return value.isoformat().replace("+00:00", "Z")


def _atomic_bytes(path: Path, encoded: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _immutable_bytes(path: Path, encoded: bytes) -> str:
    digest = sha256(encoded).hexdigest()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if path.read_bytes() != encoded:
            raise KlineWorldReportError("immutable_output_conflict")
        return digest
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    return digest


def _safe_ref(value: Any, *, field: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != {"path", "sha256"}:
        raise KlineWorldReportError(f"{field}_reference_invalid")
    path, digest = str(value.get("path") or ""), str(value.get("sha256") or "")
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise KlineWorldReportError(f"{field}_reference_invalid")
    return {"path": path, "sha256": digest}


def _read_ref(
    root: Path,
    value: Any,
    *,
    field: str,
    expected_path: str | None = None,
) -> bytes:
    reference = _safe_ref(value, field=field)
    if expected_path is not None and reference["path"] != expected_path:
        raise KlineWorldReportError(f"{field}_reference_invalid")
    target = (root / reference["path"]).resolve()
    if root not in target.parents:
        raise KlineWorldReportError("report_path_escape")
    try:
        encoded = target.read_bytes()
    except FileNotFoundError as exc:
        raise KlineWorldReportError(f"{field}_unavailable") from exc
    if sha256(encoded).hexdigest() != reference["sha256"]:
        raise KlineWorldReportError(f"{field}_hash_mismatch")
    return encoded


def _json_object(encoded: bytes, *, field: str) -> dict[str, Any]:
    try:
        value = json.loads(encoded)
    except json.JSONDecodeError as exc:
        raise KlineWorldReportError(f"{field}_invalid") from exc
    if not isinstance(value, dict):
        raise KlineWorldReportError(f"{field}_invalid")
    return value


def _current_source_refs(
    context_store: KlineWorldContextStore,
    world_model_store: KlineWorldModelStore,
    *,
    context_id: str,
    world_model_id: str,
) -> dict[str, Any]:
    if not context_id.startswith(CONTEXT_ID_PREFIX) or not world_model_id.startswith(MODEL_ID_PREFIX):
        raise KlineWorldReportError("report_source_identity_invalid")
    context_digest = context_id.removeprefix(CONTEXT_ID_PREFIX)
    context_artifact_path = f"artifacts/{context_digest}.json"
    context_receipt_path = f"receipts/{context_digest}.json"
    try:
        context_artifact_bytes = (context_store.root / context_artifact_path).read_bytes()
        context_receipt_bytes = (context_store.root / context_receipt_path).read_bytes()
        model_state = json.loads((world_model_store.root / "state.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise KlineWorldReportError("report_source_reference_unavailable") from exc
    pointer = model_state.get("pointer") if isinstance(model_state, Mapping) else None
    if (
        not isinstance(pointer, Mapping)
        or pointer.get("world_model_id") != world_model_id
        or pointer.get("context_id") != context_id
    ):
        raise KlineWorldReportError("report_source_advanced")
    model_artifact = _safe_ref(pointer.get("artifact"), field="world_model_artifact")
    model_receipt = _safe_ref(pointer.get("receipt"), field="world_model_receipt")
    model_digest = world_model_id.removeprefix(MODEL_ID_PREFIX)
    if model_artifact["path"] != f"artifacts/{model_digest}.json":
        raise KlineWorldReportError("world_model_artifact_reference_invalid")
    _read_ref(world_model_store.root, model_artifact, field="world_model_artifact")
    _read_ref(world_model_store.root, model_receipt, field="world_model_receipt")
    return {
        "context": {
            "context_id": context_id,
            "artifact": {
                "path": context_artifact_path,
                "sha256": sha256(context_artifact_bytes).hexdigest(),
            },
            "receipt": {
                "path": context_receipt_path,
                "sha256": sha256(context_receipt_bytes).hexdigest(),
            },
        },
        "world_model": {
            "world_model_id": world_model_id,
            "context_id": context_id,
            "artifact": model_artifact,
            "receipt": model_receipt,
        },
    }


def _load_bound_sources(
    context_store: KlineWorldContextStore,
    world_model_store: KlineWorldModelStore,
    sources: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(sources, Mapping) or set(sources) != {"context", "world_model"}:
        raise KlineWorldReportError("report_sources_invalid")
    context_source, model_source = sources.get("context"), sources.get("world_model")
    if not isinstance(context_source, Mapping) or set(context_source) != {"context_id", "artifact", "receipt"}:
        raise KlineWorldReportError("report_context_source_invalid")
    if not isinstance(model_source, Mapping) or set(model_source) != {"world_model_id", "context_id", "artifact", "receipt"}:
        raise KlineWorldReportError("report_model_source_invalid")
    context_id = str(context_source.get("context_id") or "")
    world_model_id = str(model_source.get("world_model_id") or "")
    if (
        not context_id.startswith(CONTEXT_ID_PREFIX)
        or not world_model_id.startswith(MODEL_ID_PREFIX)
        or model_source.get("context_id") != context_id
    ):
        raise KlineWorldReportError("report_source_identity_invalid")
    context_digest = context_id.removeprefix(CONTEXT_ID_PREFIX)
    context_artifact_ref = _safe_ref(context_source.get("artifact"), field="context_artifact")
    context_receipt_ref = _safe_ref(context_source.get("receipt"), field="context_receipt")
    context_artifact_bytes = _read_ref(
        context_store.root,
        context_artifact_ref,
        field="context_artifact",
        expected_path=f"artifacts/{context_digest}.json",
    )
    context_receipt_bytes = _read_ref(
        context_store.root,
        context_receipt_ref,
        field="context_receipt",
        expected_path=f"receipts/{context_digest}.json",
    )
    context = validate_kline_world_context(_json_object(context_artifact_bytes, field="context_artifact"))
    context_receipt = _json_object(context_receipt_bytes, field="context_receipt")
    expected_context_receipt = {
        "schema_version": CONTEXT_SCHEMA_VERSION,
        "event": "completed",
        "context_id": context_id,
        "inputs": context["inputs"],
        "artifact": context_artifact_ref,
        "truth_boundary": context["truth_boundary"],
    }
    if context.get("context_id") != context_id or context_receipt != expected_context_receipt:
        raise KlineWorldReportError("context_receipt_identity_mismatch")

    model_digest = world_model_id.removeprefix(MODEL_ID_PREFIX)
    model_artifact_ref = _safe_ref(model_source.get("artifact"), field="world_model_artifact")
    model_receipt_ref = _safe_ref(model_source.get("receipt"), field="world_model_receipt")
    model_artifact_bytes = _read_ref(
        world_model_store.root,
        model_artifact_ref,
        field="world_model_artifact",
        expected_path=f"artifacts/{model_digest}.json",
    )
    model_receipt_bytes = _read_ref(
        world_model_store.root,
        model_receipt_ref,
        field="world_model_receipt",
    )
    model = validate_world_model_artifact(
        _json_object(model_artifact_bytes, field="world_model_artifact"), context
    )
    model_receipt = _json_object(model_receipt_bytes, field="world_model_receipt")
    expected_context_artifact = {
        **context_artifact_ref,
        "receipt_sha256": context_receipt_ref["sha256"],
    }
    if (
        model.get("world_model_id") != world_model_id
        or model.get("context_id") != context_id
        or model_receipt.get("event") != "completed"
        or model_receipt.get("world_model_id") != world_model_id
        or model_receipt.get("context_id") != context_id
        or model_receipt.get("artifact") != model_artifact_ref
        or model_receipt.get("context_artifact") != expected_context_artifact
        or model_receipt.get("generation_status") != model.get("generation_status")
        or model_receipt.get("output_hash") != model.get("output_hash")
        or model_receipt.get("truth_boundary") != model.get("truth_boundary")
    ):
        raise KlineWorldReportError("world_model_receipt_identity_mismatch")
    return context, model


def _finite(value: Any, *, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise KlineWorldReportError(f"invalid_number:{field}") from exc
    if not math.isfinite(number):
        raise KlineWorldReportError(f"invalid_number:{field}")
    return round(number, 6)


def _truth_boundary(generation_status: str) -> dict[str, Any]:
    success = generation_status == "model_generated_unreviewed"
    return {
        "track": "kline_only",
        "finance_newsletter_input": False,
        "local_evaluation_only": True,
        "model_generated_unreviewed": success,
        "macro_parameters_present": success,
        "individual_security_advice": False,
        "automatic_execution_eligible": False,
        "broker_access": False,
        "portfolio_mutation": False,
        "publication_eligible": False,
    }


def _parameter_value(name: str, macro: Mapping[str, Any]) -> Any:
    field = {
        "AS_OF": "as_of",
        "RISK_BUDGET": "risk_budget",
        "LONG_GATE": "long_gate",
        "DISPERSION": "dispersion",
        "SECTOR_PRIOR": "sector_prior",
        "BLACKOUT": "blackout",
        "CONFIDENCE": "confidence",
        "DATA_COVERAGE": "data_coverage",
    }.get(name)
    if field is None:
        raise KlineWorldReportError("parameter_surface_name_invalid")
    return macro.get(field)


def _parameter_surface(
    *,
    context: Mapping[str, Any],
    macro: Mapping[str, Any],
    basis: list[Mapping[str, Any]],
    controls: Mapping[str, Any],
    generation_status: str,
) -> list[dict[str, Any]]:
    as_of = str((context.get("alignment") or {}).get("as_of") or "")
    if macro.get("as_of") not in (None, as_of):
        raise KlineWorldReportError("parameter_surface_as_of_mismatch")
    rows: list[dict[str, Any]] = [
        {
            "parameter": "AS_OF",
            "value": as_of,
            "source": "MEASURED",
            "inputs": list(SERIES_ORDER),
            "missing_inputs": [],
            "rule": "latest exact completed-session date present in all 17 aligned series",
            "statement": "全报告唯一基准日；正文、表格、卡片、图表和相对领导关系均以此日为终点。",
        }
    ]
    if generation_status != "model_generated_unreviewed":
        return rows
    by_parameter = {str(row.get("parameter")): row for row in basis}
    if list(by_parameter) != list(PARAMETER_SURFACE_ORDER[1:]):
        raise KlineWorldReportError("parameter_surface_basis_order_invalid")
    provenance = controls.get("parameter_provenance")
    if not isinstance(provenance, Mapping):
        raise KlineWorldReportError("parameter_surface_provenance_missing")
    for name in PARAMETER_SURFACE_ORDER[1:]:
        row = by_parameter[name]
        expected = provenance.get(name)
        if not isinstance(expected, Mapping):
            raise KlineWorldReportError("parameter_surface_provenance_missing")
        for field in ("source", "inputs", "missing_inputs", "rule"):
            if row.get(field) != expected.get(field):
                raise KlineWorldReportError("parameter_surface_provenance_mismatch")
        value = _parameter_value(name, macro)
        if name == "DATA_COVERAGE" and value is not None:
            value = round(float(value), 2)
        rows.append(
            {
                "parameter": name,
                "value": value,
                "source": row.get("source"),
                "inputs": list(row.get("inputs") or []),
                "missing_inputs": list(row.get("missing_inputs") or []),
                "rule": row.get("rule"),
                "statement": row.get("statement"),
            }
        )
    if [row["parameter"] for row in rows] != list(PARAMETER_SURFACE_ORDER):
        raise KlineWorldReportError("parameter_surface_order_invalid")
    return rows


def _parameter_display(row: Mapping[str, Any]) -> str:
    name, value = str(row.get("parameter") or ""), row.get("value")
    if value is None:
        return "—"
    if name in {"RISK_BUDGET", "CONFIDENCE", "DATA_COVERAGE"}:
        try:
            return f"{float(value):.2f}"
        except (TypeError, ValueError):
            return "—"
    if isinstance(value, (list, dict)):
        return _canonical_json(value)
    return str(value)


def _list_display(value: Any) -> str:
    if not isinstance(value, list) or not value:
        return "[]"
    return ", ".join(str(item) for item in value)


def _alignment_text(row: Mapping[str, Any]) -> str:
    status = str(row.get("alignment_status") or "")
    if status == "at_as_of":
        return "at_as_of"
    if status == "ahead_of_as_of":
        return "ahead_of_as_of"
    raise KlineWorldReportError("report_alignment_status_invalid")


def _reference_index(context: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in context.get("series") or []:
        if not isinstance(item, dict):
            raise KlineWorldReportError("context_series_invalid")
        for reference in (item.get("series_id"), item.get("evidence_id")):
            if reference:
                key = str(reference)
                if key in result:
                    raise KlineWorldReportError("context_reference_duplicate")
                result[key] = {"kind": "series", "value": item}
    for item in context.get("relationships") or []:
        if not isinstance(item, dict) or not item.get("relationship_id"):
            raise KlineWorldReportError("context_relationship_invalid")
        key = str(item["relationship_id"])
        if key in result:
            raise KlineWorldReportError("context_reference_duplicate")
        result[key] = {"kind": "relationship", "value": item}
    return result


def _citation_view(reference_id: str, references: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    entry = references.get(reference_id)
    if not entry:
        raise KlineWorldReportError("report_citation_unknown")
    item = entry["value"]
    if entry["kind"] == "series":
        features = item.get("features") or {}
        rate = item.get("series_type") == "rate_level"
        return {
            "reference_id": reference_id,
            "kind": "series",
            "key": item.get("key"),
            "label": item.get("display_name"),
            "session": item.get("session"),
            "quality": item.get("quality"),
            "metric_label": "20日变化" if not rate else "20日变化",
            "metric_value": features.get("change_20d_bp" if rate else "return_20d_pct"),
            "metric_unit": "basis_points" if rate else "percent_return",
        }
    features = item.get("features") or {}
    return {
        "reference_id": reference_id,
        "kind": "relationship",
        "key": item.get("key"),
        "label": item.get("question"),
        "session": (item.get("points") or [{}])[-1].get("date"),
        "quality": "derived",
        "metric_label": "20日相对变化",
        "metric_value": features.get("relative_change_20d_pct"),
        "metric_unit": "percent_return",
        "leader": features.get("leader_20d"),
    }


def _citations(ids: Any, references: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(ids, list):
        raise KlineWorldReportError("report_citation_shape_invalid")
    normalized = [str(item) for item in ids]
    if len(normalized) != len(set(normalized)):
        raise KlineWorldReportError("report_citation_duplicate")
    return [_citation_view(item, references) for item in normalized]


def _enriched_rows(rows: Any, references: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        raise KlineWorldReportError("report_rows_invalid")
    result = []
    for row in rows:
        if not isinstance(row, dict):
            raise KlineWorldReportError("report_row_invalid")
        result.append({**row, "citations": _citations(row.get("evidence_ids"), references)})
    return result


def _series_projection(item: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    points = item.get("points") or []
    if not isinstance(points, list) or len(points) != LOOKBACK:
        raise KlineWorldReportError("report_series_history_invalid")
    rate = item.get("series_type") == "rate_level"
    current_field = "value" if rate else "close"
    features = item.get("features") or {}
    change_prefix = "change" if rate else "return"
    change_suffix = "bp" if rate else "pct"
    unit = "basis_points" if rate else "percent_return"
    base = {
        "key": item.get("key"),
        "display_name": item.get("display_name"),
        "role": item.get("role"),
        "series_type": item.get("series_type"),
        "level_unit": item.get("level_unit"),
        "change_unit": unit,
        "session": item.get("session"),
        "actual_latest_session": item.get("actual_latest_session"),
        "actual_latest_equals_as_of": item.get("actual_latest_equals_as_of"),
        "alignment_status": item.get("alignment_status"),
        "discarded_post_as_of_sessions": item.get("discarded_post_as_of_sessions"),
        "close_at": item.get("close_at"),
        "quality": item.get("quality"),
        "series_id": item.get("series_id"),
        "evidence_id": item.get("evidence_id"),
        "level": _finite(points[-1].get(current_field), field=f"{item.get('key')}.level"),
        "change_5d": features.get(f"{change_prefix}_5d_{change_suffix}"),
        "change_20d": features.get(f"{change_prefix}_20d_{change_suffix}"),
        "change_60d": features.get(f"{change_prefix}_60d_{change_suffix}"),
        "trend_60d": features.get("trend_60d"),
    }
    chart = {**base, "chart_type": "line" if rate else "candlestick", "points": points}
    return base, chart


def _relationship_projection(item: Mapping[str, Any], labels: Mapping[str, str]) -> dict[str, Any]:
    features = item.get("features") or {}
    return {
        "relationship_id": item.get("relationship_id"),
        "key": item.get("key"),
        "lhs": item.get("lhs"),
        "lhs_label": labels.get(str(item.get("lhs")), str(item.get("lhs"))),
        "rhs": item.get("rhs"),
        "rhs_label": labels.get(str(item.get("rhs")), str(item.get("rhs"))),
        "question": item.get("question"),
        "semantics": item.get("semantics"),
        "change_5d": features.get("relative_change_5d_pct"),
        "change_20d": features.get("relative_change_20d_pct"),
        "change_60d": features.get("relative_change_60d_pct"),
        "leader_20d": features.get("leader_20d"),
        "leader_label": labels.get(str(features.get("leader_20d")), "均衡"),
        "points": item.get("points"),
    }


def build_world_report(
    *,
    context: Mapping[str, Any],
    world_model: Mapping[str, Any],
    generated_at: datetime,
    allow_fixture: bool = False,
) -> dict[str, Any]:
    """Build a deterministic report projection over exact validated authorities."""
    try:
        context_value = validate_kline_world_context(context)
        model_value = validate_world_model_artifact(world_model, context_value)
    except (KlineWorldContextError, KlineWorldModelError) as exc:
        raise KlineWorldReportError(str(exc)) from exc
    if context_value.get("data_kind") != "real" and not allow_fixture:
        raise KlineWorldReportError("fixture_context_report_forbidden")
    if model_value.get("context_id") != context_value.get("context_id"):
        raise KlineWorldReportError("world_model_context_mismatch")

    generated_iso = _iso(generated_at)
    generated_local = generated_at.astimezone(SHANGHAI)
    references = _reference_index(context_value)
    labels = {str(item["key"]): str(item["display_name"]) for item in context_value["series"]}
    output = model_value.get("output") or {}
    macro_raw = output.get("macro_parameters") or {}
    risk_budget = macro_raw.get("risk_budget")
    confidence_value = macro_raw.get("confidence")
    if isinstance(confidence_value, (int, float)) and not isinstance(confidence_value, bool) and float(confidence_value) < 0.5:
        posture = "no_view"
    elif isinstance(risk_budget, (int, float)) and not isinstance(risk_budget, bool):
        posture = "defense" if float(risk_budget) <= 0.4 else "wait" if float(risk_budget) <= 0.6 else "attack"
    else:
        posture = "unknown"
    if posture not in POSTURE_ZH:
        raise KlineWorldReportError("report_posture_invalid")

    cross_section: list[dict[str, Any]] = []
    charts: list[dict[str, Any]] = []
    by_key = {str(item.get("key")): item for item in context_value.get("series") or []}
    if list(by_key) != list(SERIES_ORDER):
        raise KlineWorldReportError("report_series_order_invalid")
    for key in SERIES_ORDER:
        row, chart = _series_projection(by_key[key])
        cross_section.append(row)
        charts.append(chart)

    relationships = [
        _relationship_projection(item, labels)
        for item in context_value.get("relationships") or []
    ]
    world_view = {
        "headline": output.get("headline"),
        "synthesis": output.get("summary"),
        "evidence_ids": output.get("evidence_ids") or [],
        "citations": _citations(output.get("evidence_ids") or [], references),
    }
    parameter_basis = _enriched_rows(output.get("parameter_basis") or [], references)
    inventory = {
        str(row.get("data_id")): row
        for row in (model_value.get("analysis_controls") or {}).get("data_inventory") or []
        if isinstance(row, Mapping)
    }
    for row in parameter_basis:
        row["missing_items"] = [
            inventory[item]
            for item in row.get("missing_data_ids") or []
            if item in inventory
        ]
    observations = _enriched_rows(output.get("observations") or [], references)
    for row in observations:
        row["missing_items"] = [
            inventory[item]
            for item in row.get("missing_data_ids") or []
            if item in inventory
        ]
    insights = _enriched_rows(output.get("insights") or [], references)

    generation_status = str(model_value.get("generation_status") or "interpretation_unavailable")
    parameter_surface = _parameter_surface(
        context=context_value,
        macro=macro_raw,
        basis=parameter_basis,
        controls=model_value.get("analysis_controls") or {},
        generation_status=generation_status,
    )
    core = {
        "schema_version": SCHEMA_VERSION,
        "renderer_version": RENDERER_VERSION,
        "report_date": generated_local.date().isoformat(),
        "generated_at": generated_iso,
        "context_id": context_value["context_id"],
        "world_model_id": model_value["world_model_id"],
        "data_kind": context_value["data_kind"],
        "generation_status": generation_status,
        "failure_code": model_value.get("failure_code"),
        "posture": posture,
        "posture_zh": POSTURE_ZH[posture],
        "posture_en": POSTURE_EN[posture],
        "confidence": {
            "score": macro_raw.get("confidence"),
            "cap": (model_value.get("analysis_controls") or {}).get("confidence_cap"),
            "data_coverage": macro_raw.get("data_coverage"),
        },
        "time": context_value.get("time"),
        "coverage": context_value.get("coverage"),
        "world_model": world_view,
        "macro_parameters": macro_raw,
        "parameter_surface": parameter_surface,
        "parameter_basis": parameter_basis,
        "insights": insights,
        "observations": observations,
        "data_ledger": output.get("data_ledger") or [],
        "analysis_controls": model_value.get("analysis_controls"),
        "cross_section": cross_section,
        "relationships": relationships,
        "charts": charts,
        "truth_boundary": _truth_boundary(generation_status),
    }
    report_id = f"{REPORT_ID_PREFIX}{_digest(core)}"
    return {"report_id": report_id, "identity_core": core, **core}


def validate_world_report(
    report: Mapping[str, Any],
    *,
    context: Mapping[str, Any],
    world_model: Mapping[str, Any],
    allow_fixture: bool = False,
) -> dict[str, Any]:
    core = report.get("identity_core")
    if not isinstance(core, dict):
        raise KlineWorldReportError("report_identity_core_missing")
    if report.get("report_id") != f"{REPORT_ID_PREFIX}{_digest(core)}":
        raise KlineWorldReportError("report_identity_mismatch")
    if any(report.get(key) != value for key, value in core.items()):
        raise KlineWorldReportError("report_projection_mismatch")
    try:
        generated_at = datetime.fromisoformat(str(core.get("generated_at") or "").replace("Z", "+00:00"))
    except ValueError as exc:
        raise KlineWorldReportError("report_generated_at_invalid") from exc
    expected = build_world_report(
        context=context,
        world_model=world_model,
        generated_at=generated_at,
        allow_fixture=allow_fixture,
    )
    if _canonical_json(report) != _canonical_json(expected):
        raise KlineWorldReportError("report_upstream_projection_mismatch")
    return dict(report)


def _fmt(value: Any, unit: str | None = None) -> str:
    if value is None:
        return "—"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    if unit == "basis_points":
        return f"{number:+.1f} bp"
    if unit == "percent_return":
        return f"{number:+.1f}%"
    if unit == "percent":
        return f"{number:.2f}%"
    if abs(number) >= 1000:
        return f"{number:,.1f}"
    return f"{number:.2f}"


def _cite_html(citations: list[Mapping[str, Any]]) -> str:
    return "".join(
        '<button class="cite" type="button" data-evidence="'
        + escape(str(item.get("reference_id") or ""))
        + '">'
        + escape(str(item.get("label") or item.get("key") or "证据"))
        + " · "
        + escape(_fmt(item.get("metric_value"), str(item.get("metric_unit") or "")))
        + "</button>"
        for item in citations
    )


def render_markdown(report: Mapping[str, Any]) -> str:
    world = report.get("world_model") or {}
    surface = report.get("parameter_surface") or []
    surface_by_name = {str(row.get("parameter")): row for row in surface}
    as_of = _parameter_display(surface_by_name.get("AS_OF") or {})
    lines = [
        f"# K 线世界日报｜{report.get('posture_zh')} / {report.get('posture_en')}｜{report.get('report_date')}",
        "",
        f"## {report.get('posture_zh')} / {report.get('posture_en')}",
        "",
        str(world.get("headline") or ""),
        "",
        str(world.get("synthesis") or ""),
        "",
        f"- 全报告唯一基准日 AS_OF：{as_of}",
        f"- RISK_BUDGET：{_parameter_display(surface_by_name.get('RISK_BUDGET') or {})}",
        f"- LONG_GATE：{_parameter_display(surface_by_name.get('LONG_GATE') or {})}",
        f"- CONFIDENCE：{_parameter_display(surface_by_name.get('CONFIDENCE') or {})}",
        f"- DATA_COVERAGE：{_parameter_display(surface_by_name.get('DATA_COVERAGE') or {})}",
        "",
        "## 17 张完成日线证据",
        "",
        f"全部图表、收益、利率变化与相对关系均以 `{as_of}` 为终点；完整 OHLC 日线与利率曲线请查看 HTML 版本。",
        "",
        "## 宏观参数：同一份可回放记录",
        "",
        "| 参数 | 值 | SOURCE | INPUTS | MISSING_INPUTS | RULE |",
        "|---|---|---|---|---|---|",
    ]
    for row in surface:
        lines.append(
            f"| {row.get('parameter')} | {_parameter_display(row)} | {row.get('source')} | "
            f"{_list_display(row.get('inputs'))} | {_list_display(row.get('missing_inputs'))} | {row.get('rule')} |"
        )
    lines.extend(["", "### 参数口径", ""])
    for row in surface:
        lines.append(f"- **{row.get('parameter')}**：{row.get('statement')}")
    lines.extend(["", "## 洞察与观察", "", "### 洞察", ""])
    if report.get("insights"):
        for index, row in enumerate(report.get("insights") or [], 1):
            falsifier = row.get("falsifier") or {}
            lines.append(
                f"{index}. **{row.get('conclusion')}**；证伪：{falsifier.get('metric')} "
                f"{falsifier.get('operator')} {falsifier.get('threshold')} {falsifier.get('unit')}；"
                f"复核 {row.get('review_date')}。"
            )
    else:
        lines.append("- 本日不提供方向观点；洞察区按合同留空。")
    lines.extend(["", "### 观察", ""])
    for row in report.get("observations") or []:
        claim = CLAIM_ZH.get(str(row.get("claim_type")), str(row.get("claim_type")))
        lines.append(f"- [{claim}] {row.get('statement')}")
    lines.extend(["", "## 数据台账", ""])
    for row in report.get("data_ledger") or []:
        lines.append(f"- {row.get('item')}：{row.get('status')}；{row.get('impact')}")
    lines.extend(
        [
            "",
            "## 17 个市场与 12 组相对领导关系",
            "",
            "### 17 个市场观测",
            "",
            "| 市场 | AS_OF | 实际最新日 | 对齐状态 | 丢弃 AS_OF 后行数 | 5日 | 20日 | 60日 |",
            "|---|---|---|---|---:|---:|---:|---:|",
        ]
    )
    for row in report.get("cross_section") or []:
        unit = str(row.get("change_unit") or "")
        lines.append(
            f"| {row.get('display_name')} | {row.get('session')} | {row.get('actual_latest_session')} | "
            f"{_alignment_text(row)} | {int(row.get('discarded_post_as_of_sessions') or 0)} | "
            f"{_fmt(row.get('change_5d'), unit)} | "
            f"{_fmt(row.get('change_20d'), unit)} | {_fmt(row.get('change_60d'), unit)} |"
        )
    lines.extend(["", "### 12 组相对领导关系", ""])
    for row in report.get("relationships") or []:
        lines.append(
            f"- {row.get('lhs_label')} / {row.get('rhs_label')}：20日 {_fmt(row.get('change_20d'), 'percent_return')}，"
            f"领导端 {row.get('leader_label')}"
        )
    if report.get("generation_status") != "model_generated_unreviewed":
        lines.extend(["", "本期 LLM 宏观分析未通过验证；只展示同一上下文的冻结市场证据，不复用旧参数或解释。"])
    lines.extend(
        [
            "",
            "---",
            "",
            "模型生成、未经人工复核；宏观参数供后续研究层消费。仅限本地评估，不可公开分发。",
            "本系统不会自动执行交易，不读取经纪账户，不修改任何持仓。",
            "本日报不读取 Finance Daily Newsletter；两个 Track 仅供人工对照。",
            "",
        ]
    )
    return "\n".join(lines)


def render_html(report: Mapping[str, Any]) -> str:
    posture = str(report.get("posture") or "unknown")
    world = report.get("world_model") or {}
    surface = report.get("parameter_surface") or []
    surface_by_name = {str(row.get("parameter")): row for row in surface}
    as_of = _parameter_display(surface_by_name.get("AS_OF") or {})
    parameter_cards = "".join(
        '<div class="parameter-card" data-parameter="'
        + escape(str(row.get("parameter") or ""))
        + '" data-value="'
        + escape(_parameter_display(row))
        + '" data-source="'
        + escape(str(row.get("source") or ""))
        + '"><small>'
        + escape(str(row.get("parameter") or ""))
        + "</small><strong>"
        + escape(_parameter_display(row))
        + '</strong><span class="source-chip">'
        + escape(str(row.get("source") or ""))
        + "</span></div>"
        for row in surface
    )
    basis_html = "".join(
        '<article class="basis-row" data-parameter-record="'
        + escape(str(row.get("parameter") or ""))
        + '" data-value="'
        + escape(_parameter_display(row))
        + '" data-source="'
        + escape(str(row.get("source") or ""))
        + '" data-inputs="'
        + escape(_canonical_json(row.get("inputs") or []))
        + '" data-missing-inputs="'
        + escape(_canonical_json(row.get("missing_inputs") or []))
        + '" data-rule="'
        + escape(str(row.get("rule") or ""))
        + '"><span class="parameter-name">'
        + escape(str(row.get("parameter") or ""))
        + '</span><div><p class="parameter-statement">'
        + escape(str(row.get("statement") or ""))
        + '</p><dl class="parameter-provenance"><dt>VALUE</dt><dd>'
        + escape(_parameter_display(row))
        + "</dd><dt>SOURCE</dt><dd>"
        + escape(str(row.get("source") or ""))
        + "</dd><dt>INPUTS</dt><dd>"
        + escape(_list_display(row.get("inputs")))
        + "</dd><dt>MISSING_INPUTS</dt><dd>"
        + escape(_list_display(row.get("missing_inputs")))
        + "</dd><dt>RULE</dt><dd>"
        + escape(str(row.get("rule") or ""))
        + "</dd></dl></div></article>"
        for row in surface
    )
    observation_html = "".join(
        '<li><span class="chain-index">'
        + f"{index:02d}"
        + '</span><div><span class="claim '
        + escape(str(row.get("claim_type") or ""))
        + '">'
        + escape(CLAIM_ZH.get(str(row.get("claim_type")), str(row.get("claim_type"))))
        + "</span><p>"
        + escape(str(row.get("statement") or ""))
        + ("<ol class=\"inference-steps\">" + "".join("<li>" + escape(str(step)) + "</li>" for step in row.get("inference_chain") or []) + "</ol>" if row.get("inference_chain") else "")
        + '</p><div class="citations">'
        + _cite_html(row.get("citations") or [])
        + "".join(
            '<span class="missing-chip">缺 · '
            + escape(str(item.get("item") or item.get("data_id") or ""))
            + "</span>"
            for item in row.get("missing_items") or []
        )
        + "</div></div></li>"
        for index, row in enumerate(report.get("observations") or [], 1)
    )
    insight_html = "".join(
        '<article class="insight-row"><header><span>洞察 '
        + f"{index:02d}"
        + "</span><strong>"
        + escape(str(row.get("conclusion") or ""))
        + "</strong><small>"
        + escape(str(row.get("affected_parameter") or ""))
        + '</small></header><div class="trade-body"><div><b>为什么不是复述</b><p>'
        + escape(str(row.get("why_not_restating") or ""))
        + "</p></div><div><b>数值证伪门槛</b><p>"
        + escape(
            f"{(row.get('falsifier') or {}).get('metric', '—')} "
            f"{(row.get('falsifier') or {}).get('operator', '—')} "
            f"{(row.get('falsifier') or {}).get('threshold', '—')} "
            f"{(row.get('falsifier') or {}).get('unit', '')}"
        )
        + '</p></div></div><footer><small>复核 '
        + escape(str(row.get("review_date") or ""))
        + '</small><div class="citations">'
        + _cite_html(row.get("citations") or [])
        + "</div></footer></article>"
        for index, row in enumerate(report.get("insights") or [], 1)
    )
    if not insight_html:
        insight_html = '<div class="empty-insight"><strong>本日不提供方向观点</strong><p>CONFIDENCE 低于打开方向闸门的最低要求；洞察区按合同留空，不用观察冒充 insight。</p></div>'
    ledger_html = "".join(
        '<article class="ledger-row"><span class="ledger-status '
        + escape(str(row.get("status") or ""))
        + '">'
        + escape("部分" if row.get("status") == "partial" else "缺失")
        + '</span><div><strong>'
        + escape(str(row.get("item") or ""))
        + '</strong><p>'
        + escape(str(row.get("question") or ""))
        + '</p><small>'
        + escape(str(row.get("impact") or ""))
        + "</small></div></article>"
        for row in report.get("data_ledger") or []
    )
    cross_html = "".join(
        '<div class="market-row"><div><strong>'
        + escape(str(row.get("display_name") or row.get("key") or ""))
        + "</strong><small>"
        + "AS_OF "
        + escape(str(row.get("session") or ""))
        + " · 实际最新 "
        + escape(str(row.get("actual_latest_session") or ""))
        + " · "
        + escape(_alignment_text(row))
        + " · 丢弃 "
        + escape(str(int(row.get("discarded_post_as_of_sessions") or 0)))
        + " 行"
        + '</small></div><span class="number '
        + ("positive" if float(row.get("change_5d") or 0) >= 0 else "negative")
        + '">'
        + escape(_fmt(row.get("change_5d"), str(row.get("change_unit") or "")))
        + '</span><span class="number">'
        + escape(_fmt(row.get("change_20d"), str(row.get("change_unit") or "")))
        + '</span><span class="number">'
        + escape(_fmt(row.get("change_60d"), str(row.get("change_unit") or "")))
        + "</span></div>"
        for row in report.get("cross_section") or []
    )
    relationship_html = "".join(
        '<article class="relative-row"><div><strong>'
        + escape(str(row.get("lhs_label") or ""))
        + " / "
        + escape(str(row.get("rhs_label") or ""))
        + "</strong><small>20日领导端 · "
        + escape(str(row.get("leader_label") or "均衡"))
        + '</small></div><canvas data-relative="'
        + escape(str(row.get("key") or ""))
        + '" aria-label="相对强弱趋势"></canvas><span class="number">'
        + escape(_fmt(row.get("change_20d"), "percent_return"))
        + "</span></article>"
        for row in report.get("relationships") or []
    )
    chart_html = "".join(
        '<article class="chart-card"><header><div><span>'
        + f"{index:02d}"
        + "</span><h3>"
        + escape(str(chart.get("display_name") or ""))
        + "</h3></div><small>"
        + "AS_OF "
        + escape(str(chart.get("session") or ""))
        + " · 实际最新 "
        + escape(str(chart.get("actual_latest_session") or ""))
        + " · "
        + escape(_alignment_text(chart))
        + " · 丢弃 "
        + escape(str(int(chart.get("discarded_post_as_of_sessions") or 0)))
        + " 行"
        + '</small></header><canvas data-chart="'
        + escape(str(chart.get("key") or ""))
        + '" aria-label="'
        + escape(str(chart.get("display_name") or ""))
        + ' 日线图"></canvas><footer><span>5日 '
        + escape(_fmt(chart.get("change_5d"), str(chart.get("change_unit") or "")))
        + "</span><span>20日 "
        + escape(_fmt(chart.get("change_20d"), str(chart.get("change_unit") or "")))
        + "</span><span>60日 "
        + escape(_fmt(chart.get("change_60d"), str(chart.get("change_unit") or "")))
        + "</span></footer></article>"
        for index, chart in enumerate(report.get("charts") or [], 1)
    )
    status_label = "模型生成 · 未人工复核" if report.get("generation_status") == "model_generated_unreviewed" else "模型解释不可用 · 仅展示证据"
    data_label = "VISUAL QA FIXTURE" if report.get("data_kind") == "fixture" else "LOCAL ONLY"
    unavailable = "" if report.get("generation_status") == "model_generated_unreviewed" else (
        '<div class="unavailable"><strong>本期宏观分析未通过验证</strong><p>冻结行情仍可查看；宏观参数、洞察与观察不会复用旧内容。</p></div>'
    )
    embedded = _canonical_json(report).replace("</", "<\\/")
    return f'''<!doctype html>
<html lang="zh-CN" data-posture="{escape(posture)}">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>K 线世界日报｜{escape(str(report.get("posture_zh") or ""))}｜{escape(str(report.get("report_date") or ""))}</title>
<style>
:root{{--ink:#151714;--subtle:#5f665f;--faint:#8e958f;--line:#e2e2dc;--paper:#fffefa;--canvas:#f3f1eb;--accent:#a36a16;--accent-deep:#70480d;--accent-wash:#fff2d9;--positive:#177a50;--negative:#cf443c;--observed:#eef2ef;--inferred:#f3eef7;--recommended:#fff0d6}}
html[data-posture="attack"]{{--accent:#197a50;--accent-deep:#0d5a39;--accent-wash:#e2f2e8;--recommended:#e5f5eb}}
html[data-posture="wait"]{{--accent:#b9740d;--accent-deep:#7e4d05;--accent-wash:#fff0d0;--recommended:#fff0d6}}
html[data-posture="defense"]{{--accent:#d4473e;--accent-deep:#9e2c25;--accent-wash:#fde7e4;--recommended:#fde7e4}}
html[data-posture="no_view"]{{--accent:#526779;--accent-deep:#344656;--accent-wash:#e8eef2;--recommended:#edf2f5}}
*{{box-sizing:border-box}}html,body{{margin:0;min-width:0;background:var(--canvas);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Noto Sans CJK SC",sans-serif}}body{{overflow-x:hidden}}button{{font:inherit}}main{{width:min(1060px,100%);margin:0 auto;background:var(--paper);min-height:100vh;border-left:1px solid var(--line);border-right:1px solid var(--line)}}
.mast{{height:62px;padding:0 42px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--line);gap:20px}}.brand{{font-size:12px;letter-spacing:.08em}}.brand span{{color:var(--faint);margin-left:10px}}.mast-meta{{display:flex;gap:8px;align-items:center}}.mast-meta span{{font-size:10px;color:var(--subtle);padding:5px 8px;border:1px solid var(--line);background:#fff}}
.hero{{padding:48px 42px 44px 35px;border-bottom:1px solid var(--line);border-left:7px solid var(--accent-wash);display:grid;grid-template-columns:minmax(0,1fr) 210px;gap:48px;align-items:end;background:var(--paper)}}.eyebrow{{font-size:10px;letter-spacing:.2em;color:var(--accent);font-weight:700}}.hero h1{{font-family:"Songti SC","STSong",Georgia,serif;font-size:clamp(86px,11vw,126px);font-weight:500;letter-spacing:-.09em;line-height:.82;margin:20px 0 13px;color:var(--accent)}}.hero-en{{font-size:10px;letter-spacing:.34em;color:var(--accent-deep);font-weight:700}}.headline{{font-family:"Songti SC","STSong",Georgia,serif;font-size:24px;line-height:1.45;margin:30px 0 8px;max-width:720px}}.synthesis{{font-size:14px;line-height:1.8;color:var(--subtle);margin:0;max-width:730px}}.confidence-panel{{border:1px solid var(--line);background:#fff;padding:18px 17px}}.confidence-panel>span{{display:block;font-size:9px;letter-spacing:.16em;color:var(--faint);margin-bottom:12px}}.confidence-metric{{padding:12px 0;border-top:1px solid var(--line)}}.confidence-metric:first-of-type{{border-top:0;padding-top:0}}.confidence-metric small{{display:block;font-size:10px;color:var(--subtle)}}.confidence-metric strong{{display:block;font-family:"Songti SC",Georgia,serif;font-size:30px;color:var(--accent);font-weight:500;margin-top:4px}}.confidence-panel p{{font-size:10px;color:var(--faint);line-height:1.5;margin:7px 0 0}}
.unavailable{{margin:24px 42px 0;padding:18px;border:1px solid var(--accent);background:var(--accent-wash)}}.unavailable p{{margin:6px 0 0;font-size:13px;color:var(--subtle)}}section{{padding:42px;border-bottom:1px solid var(--line)}}.section-head{{display:flex;justify-content:space-between;align-items:baseline;gap:22px;margin-bottom:26px}}.section-title{{display:flex;gap:12px;align-items:center}}.section-title b{{font-family:Georgia,serif;font-size:12px;color:var(--accent);font-weight:500}}.section-title h2{{font-size:14px;margin:0}}.section-head>small{{font-size:10px;color:var(--faint);text-align:right}}.subsection+.subsection{{margin-top:42px;padding-top:34px;border-top:1px solid var(--line)}}.subsection-head{{display:flex;justify-content:space-between;align-items:baseline;gap:18px;margin-bottom:20px}}.subsection-head h3{{font-size:12px;margin:0}}.subsection-head small{{font-size:9px;color:var(--faint);text-align:right}}
.flows{{border-top:1px solid var(--line)}}.flow-row{{display:grid;grid-template-columns:135px 135px minmax(0,1fr);border-bottom:1px solid var(--line);padding:20px 0;gap:20px;align-items:start}}.flow-side small{{display:block;color:var(--faint);font-size:9px;letter-spacing:.12em;margin-bottom:7px}}.flow-side strong{{font-family:"Songti SC",Georgia,serif;font-size:21px;font-weight:500}}.destination strong{{color:var(--accent)}}.flow-copy{{border-left:1px solid var(--line);padding-left:20px}}.confidence-word{{font-size:9px;color:var(--accent);letter-spacing:.12em}}.flow-copy p{{font-size:13px;line-height:1.65;margin:7px 0 0}}
.citations{{display:flex;flex-wrap:wrap;gap:5px;margin-top:9px}}.cite{{border:1px solid var(--line);background:#f7f7f3;color:var(--subtle);font-size:9px;padding:4px 6px;cursor:pointer;border-radius:0}}.cite:hover,.cite:focus-visible{{border-color:var(--accent);color:var(--accent-deep);outline:none}}
.chain{{list-style:none;margin:0;padding:0;max-width:820px}}.chain li{{display:grid;grid-template-columns:34px minmax(0,1fr);gap:18px;padding:0 0 26px;position:relative}}.chain li:not(:last-child)::before{{content:"";position:absolute;top:22px;bottom:3px;left:15px;border-left:1px solid var(--line)}}.chain-index{{font-family:Georgia,serif;color:var(--accent);background:var(--paper);font-size:12px;padding-top:5px;z-index:1}}.claim{{display:inline-block;font-size:9px;letter-spacing:.1em;padding:3px 6px;background:var(--observed);color:#52615a}}.claim.inferred{{background:var(--inferred);color:#6b5479}}.chain p{{font-family:"Songti SC",Georgia,serif;font-size:21px;line-height:1.55;margin:7px 0 0}}
.trade-plan{{border-top:2px solid var(--accent)}}.trade-row{{padding:22px 0;border-bottom:1px solid var(--line)}}.trade-row header{{display:grid;grid-template-columns:70px minmax(0,1fr) auto;gap:14px;align-items:baseline}}.trade-row header span{{font-size:9px;color:var(--accent);letter-spacing:.1em}}.trade-row header strong{{font-family:"Songti SC",Georgia,serif;font-size:22px;font-weight:500}}.trade-row header small{{color:var(--subtle);font-size:11px}}.trade-body{{display:grid;grid-template-columns:1fr 1fr;gap:30px;margin:17px 0 13px;padding-left:84px}}.trade-body b{{font-size:10px;color:var(--faint);font-weight:600}}.trade-body p{{font-size:13px;line-height:1.65;margin:5px 0 0}}.trade-row footer{{display:flex;justify-content:flex-end;gap:18px;align-items:flex-start;padding-left:84px}}.trade-row footer .citations{{margin-top:0;justify-content:flex-end}}
.parameter-board{{display:grid;grid-template-columns:repeat(4,1fr);border:1px solid var(--line);margin-bottom:28px}}.parameter-card{{padding:18px;border-right:1px solid var(--line);min-width:0}}.parameter-card:last-child{{border-right:0}}.parameter-card small{{display:block;font-size:9px;color:var(--faint);letter-spacing:.08em}}.parameter-card strong{{display:block;font-family:"Songti SC",Georgia,serif;font-size:28px;font-weight:500;color:var(--accent);margin-top:8px;overflow-wrap:anywhere}}.parameter-card span{{display:block;font-size:9px;color:var(--subtle);margin-top:5px}}.basis-list{{border-top:1px solid var(--line);min-width:0}}.basis-row{{display:grid;grid-template-columns:145px minmax(0,1fr);gap:22px;padding:17px 0;border-bottom:1px solid var(--line);min-width:0}}.basis-row>*{{min-width:0}}.parameter-name{{font:10px ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--accent);letter-spacing:.04em}}.basis-row p{{font-size:13px;line-height:1.7;margin:0;overflow-wrap:anywhere;word-break:break-word}}.missing-chip{{display:inline-flex;border:1px solid #e9c7c3;background:#fff5f3;color:#9e2c25;font-size:9px;padding:4px 6px}}.insight-list{{border-top:2px solid var(--accent)}}.insight-row{{padding:22px 0;border-bottom:1px solid var(--line)}}.insight-row header{{display:grid;grid-template-columns:70px minmax(0,1fr) auto;gap:14px;align-items:baseline}}.insight-row header span{{font-size:9px;color:var(--accent);letter-spacing:.1em}}.insight-row header strong{{font-family:"Songti SC",Georgia,serif;font-size:22px;font-weight:500}}.insight-row header small{{font-size:10px;color:var(--subtle)}}.insight-row footer{{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;padding-left:84px}}.empty-insight{{border:1px solid var(--accent);background:var(--accent-wash);padding:20px}}.empty-insight strong{{font-family:"Songti SC",Georgia,serif;font-size:22px;font-weight:500}}.empty-insight p{{font-size:12px;line-height:1.65;color:var(--subtle);margin:7px 0 0}}.claim.fact{{background:var(--observed);color:#52615a}}.claim.inference{{background:var(--inferred);color:#6b5479}}.claim.unknown{{background:#f1efeb;color:#756f65}}.inference-steps{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-size:11px;color:var(--subtle);margin:10px 0 0;padding-left:18px}}.ledger-list{{display:grid;grid-template-columns:1fr 1fr;gap:0 28px;border-top:1px solid var(--line)}}.ledger-row{{display:grid;grid-template-columns:42px minmax(0,1fr);gap:12px;padding:16px 0;border-bottom:1px solid var(--line)}}.ledger-status{{font-size:9px;color:#9e2c25;border:1px solid #e9c7c3;height:max-content;text-align:center;padding:4px}}.ledger-status.partial{{color:#7e4d05;border-color:#ead3a3}}.ledger-row strong{{font-size:12px}}.ledger-row p{{font-size:11px;color:var(--subtle);line-height:1.55;margin:5px 0}}.ledger-row small{{font-size:9px;color:var(--faint);line-height:1.55}}
.parameter-card{{border-bottom:1px solid var(--line)}}.parameter-card:nth-child(4n){{border-right:0}}.parameter-card:nth-last-child(-n+4){{border-bottom:0}}.parameter-card:last-child{{border-right:0}}.parameter-card strong{{font-size:24px}}.source-chip{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;overflow-wrap:anywhere}}.parameter-provenance{{display:grid;grid-template-columns:110px minmax(0,1fr);gap:5px 12px;margin:12px 0 0}}.parameter-provenance dt{{font:8px ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--faint)}}.parameter-provenance dd{{font:10px ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--subtle);margin:0;overflow-wrap:anywhere}}
.cross-head,.market-row{{display:grid;grid-template-columns:minmax(155px,1.6fr) repeat(3,minmax(70px,.7fr));gap:14px;align-items:center}}.cross-head{{font-size:9px;color:var(--faint);letter-spacing:.08em;padding:0 0 8px;border-bottom:1px solid var(--line)}}.cross-head span:not(:first-child){{text-align:right}}.market-row{{padding:10px 0;border-bottom:1px solid var(--line)}}.market-row>div{{min-width:0}}.market-row strong{{display:block;font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}.market-row small{{display:block;color:var(--faint);font-size:9px;margin-top:2px;white-space:normal;line-height:1.4}}.number{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11px;text-align:right;font-variant-numeric:tabular-nums}}.positive{{color:var(--positive)}}.negative{{color:var(--negative)}}
.relative-list{{display:grid;grid-template-columns:1fr 1fr;gap:0 30px;border-top:1px solid var(--line)}}.relative-row{{display:grid;grid-template-columns:minmax(130px,1fr) 90px 58px;gap:10px;align-items:center;padding:13px 0;border-bottom:1px solid var(--line)}}.relative-row strong{{display:block;font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}.relative-row small{{display:block;font-size:9px;color:var(--faint);margin-top:3px}}.relative-row canvas{{width:90px;height:30px;display:block}}
.charts{{display:grid;grid-template-columns:1fr 1fr;gap:18px}}.chart-card{{border:1px solid var(--line);background:#fff;padding:15px;min-width:0}}.chart-card header{{display:flex;justify-content:space-between;gap:10px;align-items:baseline}}.chart-card header div{{display:flex;gap:9px;align-items:baseline;min-width:0}}.chart-card header span{{font-size:9px;color:var(--accent)}}.chart-card h3{{font-size:12px;margin:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}.chart-card header small{{font-size:8px;color:var(--faint);white-space:nowrap}}.chart-card>canvas{{width:100%;height:165px;display:block;margin:10px 0}}.chart-card footer{{display:flex;gap:14px;color:var(--subtle);font-size:9px}}
.boundary{{padding:30px 42px 42px;background:#f1efe8;border-bottom:7px solid var(--accent);font-size:10px;line-height:1.8;color:var(--subtle)}}.boundary strong{{color:var(--ink)}}.boundary code{{display:block;margin-top:9px;overflow-wrap:anywhere;word-break:break-all;color:var(--faint)}}
dialog{{width:min(560px,calc(100% - 32px));border:1px solid var(--line);padding:0;background:var(--paper);color:var(--ink);box-shadow:0 22px 70px rgba(20,20,15,.22)}}dialog::backdrop{{background:rgba(20,22,19,.35)}}.evidence-dialog header{{padding:20px 22px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;gap:18px;align-items:start}}.evidence-dialog h3{{font-family:"Songti SC",Georgia,serif;font-size:22px;margin:0}}.evidence-dialog button{{border:1px solid var(--line);background:#fff;padding:5px 9px;cursor:pointer}}.evidence-body{{padding:20px 22px}}.evidence-body dl{{display:grid;grid-template-columns:110px 1fr;gap:8px 14px;margin:0}}.evidence-body dt{{font-size:10px;color:var(--faint)}}.evidence-body dd{{font-size:12px;margin:0;overflow-wrap:anywhere}}
@media(max-width:720px){{main{{border:0}}.mast{{height:auto;min-height:58px;padding:14px 20px;align-items:flex-start}}.brand{{white-space:nowrap}}.brand span{{display:none}}.mast-meta{{flex-wrap:wrap;justify-content:flex-end}}.mast-meta span{{font-size:8px;padding:4px 6px}}.hero{{padding:38px 20px 32px 14px;border-left-width:6px;grid-template-columns:1fr;gap:26px;background:var(--paper)}}.hero h1{{font-size:90px;margin-top:18px}}.headline{{font-size:21px;margin-top:25px}}.synthesis{{font-size:13px}}.confidence-panel{{display:grid;grid-template-columns:1fr 1fr;gap:0 20px}}.confidence-panel>span{{grid-column:1/-1}}.confidence-metric:nth-of-type(2){{border-top:0;padding-top:0}}.confidence-panel p{{grid-column:1/-1}}.unavailable{{margin:18px 20px 0}}section{{padding:34px 20px}}.section-head,.subsection-head{{align-items:flex-start}}.section-head>small,.subsection-head>small{{max-width:140px}}.parameter-board{{grid-template-columns:1fr 1fr}}.parameter-card:nth-child(2){{border-right:0}}.parameter-card:nth-child(-n+2){{border-bottom:1px solid var(--line)}}.basis-row{{grid-template-columns:minmax(0,1fr);gap:7px}}.chain p{{font-size:19px}}.insight-row header{{grid-template-columns:62px minmax(0,1fr)}}.insight-row header small{{grid-column:2}}.trade-body{{grid-template-columns:1fr;padding-left:0;gap:13px}}.insight-row footer{{padding-left:0;display:block}}.ledger-list{{grid-template-columns:1fr}}.cross-head,.market-row{{grid-template-columns:minmax(115px,1.3fr) repeat(3,minmax(54px,.7fr));gap:7px}}.market-row strong{{font-size:11px}}.number{{font-size:9px}}.relative-list,.charts{{grid-template-columns:1fr}}.relative-row{{grid-template-columns:minmax(120px,1fr) 78px 52px}}.relative-row canvas{{width:78px}}.chart-card>canvas{{height:155px}}.boundary{{padding:26px 20px 34px}}}}
@media(max-width:720px){{.parameter-card:nth-child(n){{border-right:1px solid var(--line);border-bottom:1px solid var(--line)}}.parameter-card:nth-child(2n){{border-right:0}}.parameter-card:nth-last-child(-n+2){{border-bottom:0}}.parameter-provenance{{grid-template-columns:92px minmax(0,1fr)}}.chart-card header{{align-items:flex-start}}.chart-card header small{{white-space:normal;text-align:right;line-height:1.4;max-width:165px}}}}
@media print{{body{{background:#fff}}main{{width:100%;border:0}}.cite{{color:var(--subtle)}}dialog{{display:none}}}}
</style></head>
<body><main>
<header class="mast"><div class="brand">K 线世界日报 <span>Macro Analyst · Parameter First</span></div><div class="mast-meta"><span>{escape(str(report.get("report_date") or ""))}</span><span>{escape(status_label)}</span><span>{escape(data_label)}</span></div></header>
<div class="hero"><div><div class="eyebrow">今日市场姿态 / MARKET POSTURE</div><h1>{escape(str(report.get("posture_zh") or ""))}</h1><div class="hero-en">{escape(str(report.get("posture_en") or ""))}</div><p class="headline">{escape(str(world.get("headline") or ""))}</p><p class="synthesis">{escape(str(world.get("synthesis") or ""))}</p><div class="citations">{_cite_html(world.get("citations") or [])}</div></div><aside class="confidence-panel"><span>唯一基准日 · 参数快照</span><div class="confidence-metric"><small>AS_OF</small><strong>{escape(as_of)}</strong></div><div class="confidence-metric"><small>风险预算 / 闸门</small><strong>{escape(_parameter_display(surface_by_name.get("RISK_BUDGET") or {}))} · {escape(_parameter_display(surface_by_name.get("LONG_GATE") or {}))}</strong></div><p>置信度 {escape(_parameter_display(surface_by_name.get("CONFIDENCE") or {}))} · 数据覆盖 {escape(_parameter_display(surface_by_name.get("DATA_COVERAGE") or {}))}</p></aside></div>
{unavailable}
<section id="charts"><div class="section-head"><div class="section-title"><b>01</b><h2>17 张完成日线证据</h2></div><small>全部数值止于 AS_OF {escape(as_of)}；价格为 OHLC K 线，利率为折线</small></div><div class="charts">{chart_html}</div></section>
<section id="macro-parameters"><div class="section-head"><div class="section-title"><b>02</b><h2>宏观参数：同一份可回放记录</h2></div><small>值、来源、输入、缺失与规则同时展示</small></div><div class="parameter-board">{parameter_cards}</div><div class="basis-list">{basis_html}</div></section>
<section id="insights-observations"><div class="section-head"><div class="section-title"><b>03</b><h2>哪些是洞察，哪些只是观察？</h2></div><small>洞察必须可证伪、改变行动</small></div><div class="subsection"><div class="subsection-head"><h3>洞察 / INSIGHTS</h3><small>0–3 条 · 宁缺毋滥</small></div><div class="insight-list">{insight_html}</div></div><div class="subsection"><div class="subsection-head"><h3>观察 / OBSERVATIONS</h3><small>事实、推断、未知分开标记</small></div><ol class="chain">{observation_html}</ol></div></section>
<section id="data-ledger"><div class="section-head"><div class="section-title"><b>04</b><h2>哪些关键数据还没有拿到？</h2></div><small>缺口显式入账，不用历史价格假装预期</small></div><div class="ledger-list">{ledger_html}</div></section>
<section id="market-evidence"><div class="section-head"><div class="section-title"><b>05</b><h2>17 个市场与 12 组相对领导关系</h2></div><small>横截面与相对强弱放在一起看</small></div><div class="subsection" id="cross-section"><div class="subsection-head"><h3>17 个市场观测</h3><small>美债变化统一用 bp</small></div><div class="cross-head"><span>市场</span><span>5日</span><span>20日</span><span>60日</span></div><div>{cross_html}</div></div><div class="subsection" id="relative-leadership"><div class="subsection-head"><h3>12 组相对领导关系</h3><small>标准化相对表现 · 20日领导端</small></div><div class="relative-list">{relationship_html}</div></div></section>
<footer class="boundary"><strong>研究边界：</strong>模型生成、未经人工复核；本页输出宏观参数，最细只到板块，不输出个股、入场价、止损位或个人仓位。仅限 Park 本地评估，当前数据权利不支持公开分发。<br>系统不会自动执行交易，不读取经纪账户，不修改任何持仓。Finance Daily Newsletter 不是本页输入，两个 Track 只做人工对照。<code>{escape(str(report.get("report_id") or ""))}</code></footer>
</main>
<dialog id="evidence-dialog" class="evidence-dialog"><header><h3 id="evidence-title">证据</h3><button type="button" id="evidence-close">关闭</button></header><div class="evidence-body"><dl id="evidence-fields"></dl></div></dialog>
<script id="report-data" type="application/json">{embedded}</script>
<script>
const REPORT=JSON.parse(document.getElementById('report-data').textContent);
const CSS=getComputedStyle(document.documentElement),UP=CSS.getPropertyValue('--positive').trim(),DOWN=CSS.getPropertyValue('--negative').trim(),ACCENT=CSS.getPropertyValue('--accent').trim(),GRID='#ecece6',TEXT='#767d77';
function fit(canvas){{const r=canvas.getBoundingClientRect(),d=Math.max(1,window.devicePixelRatio||1);canvas.width=Math.round(r.width*d);canvas.height=Math.round(r.height*d);const c=canvas.getContext('2d');c.setTransform(d,0,0,d,0,0);return[c,r.width,r.height]}}
function drawSeries(canvas,chart){{const[c,w,h]=fit(canvas),rows=(chart.points||[]).slice(-70),line=chart.chart_type==='line',values=rows.flatMap(r=>line?[Number(r.value)]:[Number(r.high),Number(r.low)]).filter(Number.isFinite);if(!values.length)return;let lo=Math.min(...values),hi=Math.max(...values);if(hi===lo){{hi+=1;lo-=1}}const p={{l:7,r:7,t:10,b:17}},y=v=>p.t+(hi-v)/(hi-lo)*(h-p.t-p.b),step=(w-p.l-p.r)/Math.max(rows.length,1);c.clearRect(0,0,w,h);c.strokeStyle=GRID;c.lineWidth=1;for(let i=0;i<4;i++){{const yy=p.t+i*(h-p.t-p.b)/3;c.beginPath();c.moveTo(p.l,yy);c.lineTo(w-p.r,yy);c.stroke()}}if(line){{c.strokeStyle=ACCENT;c.lineWidth=1.6;c.beginPath();rows.forEach((r,i)=>{{const x=p.l+(i+.5)*step,yy=y(Number(r.value));i?c.lineTo(x,yy):c.moveTo(x,yy)}});c.stroke()}}else{{rows.forEach((r,i)=>{{const o=Number(r.open),cl=Number(r.close),high=Number(r.high),low=Number(r.low),x=p.l+(i+.5)*step,color=cl>=o?UP:DOWN,width=Math.max(1.2,Math.min(5,step*.58)),top=Math.min(y(o),y(cl)),bodyHeight=Math.max(1,Math.abs(y(o)-y(cl)));c.strokeStyle=color;c.lineWidth=1;c.beginPath();c.moveTo(x,y(high));c.lineTo(x,y(low));c.stroke();if(cl>=o){{c.strokeStyle=UP;c.strokeRect(x-width/2,top,width,bodyHeight)}}else{{c.fillStyle=DOWN;c.fillRect(x-width/2,top,width,bodyHeight)}}}})}}c.fillStyle=TEXT;c.font='8px -apple-system,sans-serif';c.fillText(rows[0]?.date||'',p.l,h-3);c.textAlign='right';c.fillText(rows.at(-1)?.date||'',w-p.r,h-3);c.textAlign='left'}}
function drawRelative(canvas,row){{const[c,w,h]=fit(canvas),points=(row.points||[]).slice(-45),values=points.map(x=>Number(x.relative_index)).filter(Number.isFinite);if(!values.length)return;let lo=Math.min(...values),hi=Math.max(...values);if(hi===lo){{hi+=1;lo-=1}}const x=i=>i/(Math.max(values.length-1,1))*w,y=v=>3+(hi-v)/(hi-lo)*(h-6);c.clearRect(0,0,w,h);c.strokeStyle=ACCENT;c.lineWidth=1.3;c.beginPath();values.forEach((v,i)=>i?c.lineTo(x(i),y(v)):c.moveTo(x(i),y(v)));c.stroke()}}
function redraw(){{for(const canvas of document.querySelectorAll('canvas[data-chart]')){{const chart=REPORT.charts.find(x=>x.key===canvas.dataset.chart);if(chart)drawSeries(canvas,chart)}}for(const canvas of document.querySelectorAll('canvas[data-relative]')){{const row=REPORT.relationships.find(x=>x.key===canvas.dataset.relative);if(row)drawRelative(canvas,row)}}}}
const evidence=new Map();for(const section of [REPORT.world_model,...REPORT.parameter_basis,...REPORT.insights,...REPORT.observations]){{for(const item of section?.citations||[])evidence.set(item.reference_id,item)}}
const dialog=document.getElementById('evidence-dialog'),fields=document.getElementById('evidence-fields'),title=document.getElementById('evidence-title');
document.addEventListener('click',event=>{{const button=event.target.closest('[data-evidence]');if(!button)return;const item=evidence.get(button.dataset.evidence);if(!item)return;title.textContent=item.label||item.key||'证据';const rows=[['引用 ID',item.reference_id],['类型',item.kind],['完成日',item.session||'—'],['质量',item.quality||'—'],[item.metric_label||'指标',`${{item.metric_value??'—'}} ${{item.metric_unit==='basis_points'?'bp':item.metric_unit==='percent_return'?'%':''}}`],['20日领导端',item.leader||'—']];fields.replaceChildren(...rows.flatMap(([key,value])=>{{const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=key;dd.textContent=String(value);return[dt,dd]}}));dialog.showModal()}});
document.getElementById('evidence-close').addEventListener('click',()=>dialog.close());
redraw();let resizeTimer;addEventListener('resize',()=>{{clearTimeout(resizeTimer);resizeTimer=setTimeout(redraw,100)}});
</script></body></html>'''


class KlineWorldReportStore:
    """Publish immutable JSON/HTML/Markdown and atomically advance one pointer."""

    def __init__(
        self,
        context_store: KlineWorldContextStore,
        world_model_store: KlineWorldModelStore,
        root: Path | str,
        output_root: Path | str,
        *,
        allow_fixture: bool = False,
    ) -> None:
        self.context_store = context_store
        self.world_model_store = world_model_store
        self.root = Path(root).expanduser().resolve()
        self.output_root = Path(output_root).expanduser().resolve()
        self.allow_fixture = allow_fixture

    def compile_latest(self, *, generated_at: datetime) -> dict[str, Any]:
        context = self.context_store.latest()
        model = self.world_model_store.latest(expected_context_id=str(context["context_id"]))
        report = build_world_report(
            context=context,
            world_model=model,
            generated_at=generated_at,
            allow_fixture=self.allow_fixture,
        )
        return self.publish(report)

    def publish(self, report: Mapping[str, Any]) -> dict[str, Any]:
        context = self.context_store.latest()
        model = self.world_model_store.latest(expected_context_id=str(context["context_id"]))
        validated = validate_world_report(
            report,
            context=context,
            world_model=model,
            allow_fixture=self.allow_fixture,
        )
        if validated.get("data_kind") != "real" and not self.allow_fixture:
            raise KlineWorldReportError("fixture_report_publication_forbidden")
        sources = _current_source_refs(
            self.context_store,
            self.world_model_store,
            context_id=str(validated["context_id"]),
            world_model_id=str(validated["world_model_id"]),
        )
        bound_context, bound_model = _load_bound_sources(
            self.context_store, self.world_model_store, sources
        )
        validate_world_report(
            validated,
            context=bound_context,
            world_model=bound_model,
            allow_fixture=self.allow_fixture,
        )
        digest = str(validated["report_id"]).removeprefix(REPORT_ID_PREFIX)
        report_ref = {"path": f"artifacts/{digest}.json"}
        html_ref = {"path": f"artifacts/{digest}.html"}
        markdown_ref = {"path": f"artifacts/{digest}.md"}
        report_ref["sha256"] = _immutable_bytes(self.root / report_ref["path"], _json_bytes(validated))
        html_ref["sha256"] = _immutable_bytes(self.output_root / html_ref["path"], render_html(validated).encode("utf-8"))
        markdown_ref["sha256"] = _immutable_bytes(self.output_root / markdown_ref["path"], render_markdown(validated).encode("utf-8"))
        receipt = {
            "schema_version": SCHEMA_VERSION,
            "event": "completed",
            "report_id": validated["report_id"],
            "context_id": validated["context_id"],
            "world_model_id": validated["world_model_id"],
            "report": report_ref,
            "html": html_ref,
            "markdown": markdown_ref,
            "sources": sources,
            "truth_boundary": validated["truth_boundary"],
        }
        receipt_ref = {"path": f"receipts/{digest}.json"}
        receipt_ref["sha256"] = _immutable_bytes(self.root / receipt_ref["path"], _json_bytes(receipt))
        state = {
            "schema_version": SCHEMA_VERSION,
            "report_id": validated["report_id"],
            "context_id": validated["context_id"],
            "world_model_id": validated["world_model_id"],
            "report": report_ref,
            "html": html_ref,
            "markdown": markdown_ref,
            "receipt": receipt_ref,
        }
        state_path = self.root / "state.json"
        prior = state_path.read_bytes() if state_path.exists() else None
        _atomic_bytes(state_path, _json_bytes(state))
        try:
            self.latest()
        except Exception:
            if prior is None:
                state_path.unlink(missing_ok=True)
            else:
                _atomic_bytes(state_path, prior)
            raise
        return state

    def load(self, report_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        if not report_id.startswith(REPORT_ID_PREFIX):
            raise KlineWorldReportError("report_identity_invalid")
        digest = report_id.removeprefix(REPORT_ID_PREFIX)
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise KlineWorldReportError("report_identity_invalid")
        receipt_path = f"receipts/{digest}.json"
        try:
            receipt_bytes = (self.root / receipt_path).read_bytes()
        except FileNotFoundError as exc:
            raise KlineWorldReportError("report_receipt_unavailable") from exc
        receipt = _json_object(receipt_bytes, field="report_receipt")
        required_receipt = {
            "schema_version",
            "event",
            "report_id",
            "context_id",
            "world_model_id",
            "report",
            "html",
            "markdown",
            "sources",
            "truth_boundary",
        }
        if set(receipt) != required_receipt or receipt.get("schema_version") != SCHEMA_VERSION:
            raise KlineWorldReportError("report_receipt_invalid")
        report_ref = _safe_ref(receipt.get("report"), field="report")
        html_ref = _safe_ref(receipt.get("html"), field="html")
        markdown_ref = _safe_ref(receipt.get("markdown"), field="markdown")
        report_bytes = _read_ref(
            self.root,
            report_ref,
            field="report",
            expected_path=f"artifacts/{digest}.json",
        )
        html_bytes = _read_ref(
            self.output_root,
            html_ref,
            field="html",
            expected_path=f"artifacts/{digest}.html",
        )
        markdown_bytes = _read_ref(
            self.output_root,
            markdown_ref,
            field="markdown",
            expected_path=f"artifacts/{digest}.md",
        )
        report = _json_object(report_bytes, field="report_artifact")
        context, model = _load_bound_sources(
            self.context_store, self.world_model_store, receipt.get("sources")
        )
        validated = validate_world_report(
            report,
            context=context,
            world_model=model,
            allow_fixture=self.allow_fixture,
        )
        expected_receipt = {
            "schema_version": SCHEMA_VERSION,
            "event": "completed",
            "report_id": validated["report_id"],
            "context_id": validated["context_id"],
            "world_model_id": validated["world_model_id"],
            "report": report_ref,
            "html": html_ref,
            "markdown": markdown_ref,
            "sources": receipt["sources"],
            "truth_boundary": validated["truth_boundary"],
        }
        if receipt != expected_receipt or validated["report_id"] != report_id:
            raise KlineWorldReportError("report_receipt_identity_mismatch")
        if html_bytes != render_html(validated).encode("utf-8") or markdown_bytes != render_markdown(validated).encode("utf-8"):
            raise KlineWorldReportError("report_render_replay_mismatch")
        state = {
            "schema_version": SCHEMA_VERSION,
            "report_id": report_id,
            "context_id": validated["context_id"],
            "world_model_id": validated["world_model_id"],
            "report": report_ref,
            "html": html_ref,
            "markdown": markdown_ref,
            "receipt": {
                "path": receipt_path,
                "sha256": sha256(receipt_bytes).hexdigest(),
            },
        }
        return state, validated

    def latest(self) -> tuple[dict[str, Any], dict[str, Any]]:
        try:
            state = json.loads((self.root / "state.json").read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            raise KlineWorldReportError("report_latest_unavailable") from exc
        required = {"schema_version", "report_id", "context_id", "world_model_id", "report", "html", "markdown", "receipt"}
        if not isinstance(state, dict) or set(state) != required or state.get("schema_version") != SCHEMA_VERSION:
            raise KlineWorldReportError("report_state_invalid")
        report_id = str(state.get("report_id") or "")
        if not report_id.startswith(REPORT_ID_PREFIX):
            raise KlineWorldReportError("report_state_identity_invalid")
        loaded_state, validated = self.load(report_id)
        if state != loaded_state:
            raise KlineWorldReportError("report_state_reference_mismatch")
        return loaded_state, validated
