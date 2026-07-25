"""Fail-closed reader for source-bound E4 partial Report Models.

The reader deliberately exposes only the product-safe projection of a real,
Tier-C partial model.  It is not a report compiler and cannot turn incomplete
evidence into a target, position, or recommendation.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from data_core.ashare import normalize_ashare_ticker
from data_core.contracts import digest
from data_core.e4_partial_report_models import E4_PARTIAL_REPORT_MODEL_SCHEMA_VERSION


class PartialModelStoreError(ValueError):
    """The configured partial-model receipt cannot safely be read."""


def _read_json(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PartialModelStoreError("partial model receipt is unavailable") from exc
    if not isinstance(value, Mapping):
        raise PartialModelStoreError("partial model receipt is invalid")
    return value


def _receipt_path(root: Path) -> Path:
    resolved_root = root.resolve()
    pointer = _read_json(resolved_root / "partial-report-models-latest.json")
    name = pointer.get("receipt")
    if not isinstance(name, str) or not name or Path(name).name != name:
        raise PartialModelStoreError("partial model receipt pointer is unsafe")
    target = (resolved_root / name).resolve()
    try:
        target.relative_to(resolved_root)
    except ValueError as exc:
        raise PartialModelStoreError("partial model receipt pointer escapes its root") from exc
    if not target.is_file() or target.is_symlink():
        raise PartialModelStoreError("partial model receipt is unavailable")
    receipt = _read_json(target)
    receipt_hash = receipt.get("receipt_hash")
    material = {key: value for key, value in receipt.items() if key != "receipt_hash"}
    if not isinstance(receipt_hash, str) or receipt_hash != digest(material):
        raise PartialModelStoreError("partial model receipt identity is invalid")
    if pointer.get("receipt_hash") != receipt_hash:
        raise PartialModelStoreError("partial model pointer identity mismatch")
    return target


def _safe_model(ticker: str, model: Mapping[str, Any], receipt_hash: str) -> dict[str, Any]:
    boundary = model.get("decision_boundary")
    if (
        model.get("schema_version") != E4_PARTIAL_REPORT_MODEL_SCHEMA_VERSION
        or model.get("data_kind") != "real"
        or model.get("ticker") != ticker
        or not isinstance(boundary, Mapping)
        or boundary != {"tier": "C", "action": "no_action", "target_price": None, "position_range": None}
    ):
        raise PartialModelStoreError("partial model boundary is invalid")
    allowed = (
        "as_of", "evidence_set_id", "evidence_manifest_hash", "raw_hash", "document_id",
        "report_model_hash", "sections", "input_facts", "blockers", "numeric_spot_audit",
        "page_citation_spot_audit",
    )
    payload = {key: model[key] for key in allowed if key in model}
    return {
        "ticker": ticker,
        "status": "available",
        "data_kind": "real",
        "receipt_hash": receipt_hash,
        "decision_boundary": dict(boundary),
        **payload,
    }


def load_partial_model(ticker: str, root: Path) -> dict[str, Any]:
    """Return a safe exact-ticker projection, or an explicit unavailable state."""
    try:
        normalized = normalize_ashare_ticker(ticker).ticker
    except ValueError as exc:
        raise PartialModelStoreError("ticker is invalid") from exc
    receipt_path = _receipt_path(root)
    receipt = _read_json(receipt_path)
    boundary = receipt.get("truth_boundary")
    if (
        receipt.get("schema_version") != E4_PARTIAL_REPORT_MODEL_SCHEMA_VERSION
        or receipt.get("data_kind") != "real"
        or not isinstance(boundary, Mapping)
        or boundary.get("tier_is_c_only") is not True
    ):
        raise PartialModelStoreError("partial model receipt boundary is invalid")
    rows = receipt.get("models")
    if not isinstance(rows, list):
        raise PartialModelStoreError("partial model receipt rows are invalid")
    matching = [row for row in rows if isinstance(row, Mapping) and row.get("ticker") == normalized]
    if len(matching) > 1:
        raise PartialModelStoreError("partial model receipt has duplicate ticker rows")
    if not matching:
        return {"ticker": normalized, "status": "unavailable", "data_kind": "real", "blockers": ["partial_model_not_available"]}
    row = matching[0]
    if row.get("status") != "compiled":
        blockers = row.get("blockers")
        return {
            "ticker": normalized,
            "status": "unavailable",
            "data_kind": "real",
            "blockers": list(blockers) if isinstance(blockers, list) else ["partial_model_not_available"],
        }
    model = row.get("model")
    if not isinstance(model, Mapping):
        raise PartialModelStoreError("compiled partial model is invalid")
    return _safe_model(normalized, model, str(receipt["receipt_hash"]))
