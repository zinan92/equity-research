"""Receipt-bound valuation and sell-side coverage for E4 partial models.

This module is deliberately a join, not a valuation engine or a broker-data
collector.  It upgrades section availability only after caller-supplied,
runtime-only receipts prove the same ticker, cutoff and accepted Context Pack
as the partial model.  The decision boundary is immutable: this path remains
Tier C / no-action even when both sections are available.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .contracts import digest


E4_RECEIPT_BOUND_COVERAGE_SCHEMA_VERSION = "e4-s4-receipt-bound-coverage-v1"
VALUATION_INPUT_SCHEMA_VERSION = "e4-s4-valuation-input-receipts-v1"
SELL_SIDE_INPUT_SCHEMA_VERSION = "e4-s4-sell-side-input-receipts-v1"


def _read_real_input(path: Path, *, schema_version: str, partial_sha256: str) -> dict[str, Mapping[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != schema_version or payload.get("data_kind") != "real":
        raise ValueError("coverage inputs must be real, schema-bound receipts")
    if payload.get("partial_receipt_sha256") != partial_sha256:
        raise ValueError("coverage input does not match partial-model receipt lineage")
    rows = payload.get("receipts")
    if not isinstance(rows, list):
        raise ValueError("coverage input receipts are invalid")
    by_ticker: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("coverage input row is invalid")
        ticker = str(row.get("ticker") or "").upper()
        if not ticker or ticker in by_ticker:
            raise ValueError("coverage input tickers must be unique and non-empty")
        by_ticker[ticker] = row
    return by_ticker


def _availability(
    row: Mapping[str, Any] | None, model: Mapping[str, Any], *, kind: str,
) -> tuple[str, str | None, str | None]:
    """Validate an input receipt and return section status, blocker and hash."""
    if row is None:
        return "missing_evidence", f"partial_model_missing_{kind}", None
    required = ("ticker", "as_of", "context_evidence_set_id", "context_manifest_hash")
    if any(not row.get(field) for field in required):
        return "blocked", f"{kind}_receipt_incomplete", None
    if str(row["ticker"]).upper() != str(model["ticker"]).upper():
        return "blocked", f"{kind}_receipt_ticker_mismatch", None
    if str(row["as_of"]) != str(model["as_of"]):
        return "blocked", f"{kind}_receipt_as_of_mismatch", None
    if row["context_evidence_set_id"] != model["evidence_set_id"] or row["context_manifest_hash"] != model["evidence_manifest_hash"]:
        return "blocked", f"{kind}_receipt_context_mismatch", None
    receipt_hash = str(row.get("receipt_hash") or row.get("binding_hash") or "")
    if len(receipt_hash) != 64 or any(char not in "0123456789abcdef" for char in receipt_hash.lower()):
        return "blocked", f"{kind}_receipt_hash_invalid", None
    if kind == "valuation" and not row.get("valuation_output_hash"):
        return "blocked", "valuation_receipt_missing_output", None
    if kind == "sell_side" and not row.get("accepted_report_ids"):
        return "missing_evidence", "sell_side_receipt_has_no_accepted_reports", receipt_hash
    return "available", None, receipt_hash


def bind_coverage(model: Mapping[str, Any], *, valuation_status: str, sell_side_status: str) -> dict[str, Any]:
    """Legacy status-only helper; production callers should use receipt binding."""
    aliases = {"accepted": "available", "missing": "missing_evidence"}
    valuation_status = aliases.get(valuation_status, valuation_status)
    sell_side_status = aliases.get(sell_side_status, sell_side_status)
    allowed = {"available", "missing_evidence", "blocked"}
    if valuation_status not in allowed or sell_side_status not in allowed:
        raise ValueError("coverage status is invalid")
    result = dict(model)
    parent_hash = str(model.get("report_model_hash") or "")
    if not parent_hash:
        raise ValueError("coverage binding requires report_model_hash")
    result["sections"] = {**dict(model.get("sections") or {}), "valuation": valuation_status, "sell_side": sell_side_status}
    result["decision_boundary"] = {"tier": "C", "action": "no_action", "target_price": None, "position_range": None}
    result["parent_report_model_hash"] = parent_hash
    result["coverage_binding_hash"] = digest({"model": parent_hash, "valuation": valuation_status, "sell_side": sell_side_status})
    material = {key: value for key, value in result.items() if key != "report_model_hash"}
    result["report_model_hash"] = digest(material)
    return result


def compile_receipt_bound_coverage(
    partial_receipt_path: Path, valuation_receipt_path: Path, sell_side_receipt_path: Path,
) -> dict[str, Any]:
    """Attach verified section availability to every model in one frozen corpus."""
    partial_bytes = partial_receipt_path.read_bytes()
    partial = json.loads(partial_bytes)
    boundary = partial.get("truth_boundary") or {}
    if partial.get("schema_version") != "e4-s4-partial-report-model-v1" or partial.get("data_kind") != "real" or not boundary.get("tier_is_c_only"):
        raise ValueError("coverage compiler requires real Tier-C partial models")
    partial_sha256 = hashlib.sha256(partial_bytes).hexdigest()
    valuations = _read_real_input(valuation_receipt_path, schema_version=VALUATION_INPUT_SCHEMA_VERSION, partial_sha256=partial_sha256)
    sell_side = _read_real_input(sell_side_receipt_path, schema_version=SELL_SIDE_INPUT_SCHEMA_VERSION, partial_sha256=partial_sha256)
    rows: list[dict[str, Any]] = []
    for entry in partial.get("models") or []:
        if entry.get("status") != "compiled":
            rows.append({"ticker": entry.get("ticker"), "status": "blocked", "blockers": ["partial_model_not_compiled"]})
            continue
        model = dict(entry.get("model") or {})
        if not model.get("as_of"):
            rows.append({"ticker": model.get("ticker") or entry.get("ticker"), "status": "blocked", "blockers": ["partial_model_missing_as_of"]})
            continue
        valuation_status, valuation_blocker, valuation_hash = _availability(valuations.get(str(model["ticker"]).upper()), model, kind="valuation")
        sell_side_status, sell_side_blocker, sell_side_hash = _availability(sell_side.get(str(model["ticker"]).upper()), model, kind="sell_side")
        covered = bind_coverage(model, valuation_status=valuation_status, sell_side_status=sell_side_status)
        blockers = [blocker for blocker in (*model.get("blockers", ()), valuation_blocker, sell_side_blocker) if blocker]
        rows.append({
            "ticker": model["ticker"], "status": "compiled", "model": covered,
            "input_receipt_hashes": {"valuation": valuation_hash, "sell_side": sell_side_hash},
            "blockers": sorted(set(blockers)),
        })
    receipt = {
        "schema_version": E4_RECEIPT_BOUND_COVERAGE_SCHEMA_VERSION,
        "data_kind": "real",
        "partial_receipt_sha256": partial_sha256,
        "valuation_receipt_sha256": hashlib.sha256(valuation_receipt_path.read_bytes()).hexdigest(),
        "sell_side_receipt_sha256": hashlib.sha256(sell_side_receipt_path.read_bytes()).hexdigest(),
        "models": rows,
        "counts": {
            "compiled": sum(row["status"] == "compiled" for row in rows),
            "valuation_available": sum(row.get("model", {}).get("sections", {}).get("valuation") == "available" for row in rows),
            "sell_side_available": sum(row.get("model", {}).get("sections", {}).get("sell_side") == "available" for row in rows),
        },
        "truth_boundary": {"tier_is_c_only": True, "counts_as_tier_a_or_b": False, "counts_as_numeric_page_audit": False, "no_action": True},
    }
    receipt["receipt_hash"] = digest(receipt)
    return receipt
