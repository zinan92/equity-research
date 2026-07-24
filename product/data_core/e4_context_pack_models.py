"""Compose real E4 receipts into auditable, Tier-C Context Pack models.

This is deliberately glue around B6/E4/C3 contracts. It does not fetch a
provider, infer an estimate, or promote a partial model into a recommendation.
The compiler fails closed when the three inputs do not describe the same
ticker, cutoff and official-receipt lineage.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .contracts import digest
from .e4_valuation_sellside_coverage import bind_coverage


E4_CONTEXT_PACK_MODEL_SCHEMA_VERSION = "e4-s4-context-pack-model-v1"
_MARKET_SCHEMA = "e4-s4-market-fundamentals-batch-v1"
_MATRIX_SCHEMA = "e4-s4-sell-side-matrix-v1"
_PARTIAL_SCHEMA = "e4-s4-partial-report-model-v1"


def _load(path: Path, schema: str) -> tuple[bytes, dict[str, Any]]:
    raw = path.read_bytes()
    value = json.loads(raw)
    if value.get("schema_version") != schema or value.get("data_kind") != "real":
        raise ValueError("context-pack compiler requires real schema-bound receipts")
    return raw, value


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _valid_hash(value: object) -> bool:
    value = str(value or "")
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value.lower())


def _instant(value: object, *, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include timezone")
    return parsed.astimezone(timezone.utc)


def _at_or_before(value: object, cutoff: datetime) -> bool:
    return _instant(value, field="source known_at") <= cutoff


def _by_ticker(rows: object, *, label: str) -> dict[str, Mapping[str, Any]]:
    if not isinstance(rows, list):
        raise ValueError(f"{label} rows must be a list")
    result: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError(f"{label} row is invalid")
        ticker = str(row.get("ticker") or "").upper()
        if not ticker or ticker in result:
            raise ValueError(f"{label} tickers must be unique and non-empty")
        result[ticker] = row
    return result


def _market_component(row: Mapping[str, Any] | None, *, cutoff: datetime) -> tuple[dict[str, Any], list[str]]:
    if row is None:
        return {"status": "missing_evidence", "source_receipts": []}, ["market_fundamentals_missing_ticker"]
    if row.get("data_kind") != "real":
        return {"status": "blocked", "source_receipts": []}, ["market_fundamentals_not_real"]
    sources = row.get("source_receipts")
    if not isinstance(sources, Mapping):
        return {"status": "blocked", "source_receipts": []}, ["market_fundamentals_missing_source_receipts"]
    relevant = ("quote", "daily_bars", "fundamentals", "balance_sheet", "income_statement", "cash_flow")
    receipts: list[dict[str, str]] = []
    blockers: list[str] = []
    for name in relevant:
        source = sources.get(name)
        if not isinstance(source, Mapping):
            blockers.append(f"market_fundamentals_missing_{name}_receipt")
            continue
        raw_hash, manifest_hash, known_at = source.get("raw_hash"), source.get("manifest_hash"), source.get("known_at")
        if not _valid_hash(raw_hash) or not _valid_hash(manifest_hash):
            blockers.append(f"market_fundamentals_invalid_{name}_identity")
            continue
        try:
            known_on_time = _at_or_before(known_at, cutoff)
        except ValueError:
            blockers.append(f"market_fundamentals_invalid_{name}_known_at")
            continue
        if not known_on_time:
            blockers.append(f"market_fundamentals_{name}_known_at_after_cutoff")
            continue
        receipts.append({"component": name, "source_key": str(source.get("source_key") or ""), "raw_hash": str(raw_hash), "manifest_hash": str(manifest_hash), "known_at": str(known_at)})
    if blockers:
        return {"status": "blocked", "source_receipts": receipts}, blockers
    available = bool(row.get("market_available")) and bool(row.get("fundamentals_available"))
    return {"status": "available" if available else "missing_evidence", "source_receipts": receipts}, ([] if available else ["market_or_fundamentals_unavailable"])


def _sell_side_component(row: Mapping[str, Any] | None, *, as_of: str) -> tuple[dict[str, Any], list[str]]:
    if row is None:
        return {"status": "missing_evidence", "matrix_id": None, "report_ids": []}, ["sell_side_matrix_missing_ticker"]
    if row.get("status") != "compiled" or not isinstance(row.get("matrix"), Mapping):
        return {"status": "missing_evidence", "matrix_id": None, "report_ids": []}, ["sell_side_matrix_unavailable"]
    matrix = row["matrix"]
    if matrix.get("research_cutoff") != as_of or not _valid_hash(matrix.get("input_hash")):
        return {"status": "blocked", "matrix_id": matrix.get("matrix_id"), "report_ids": []}, ["sell_side_matrix_cutoff_or_identity_mismatch"]
    report_ids = []
    for item in matrix.get("rows") or []:
        if not isinstance(item, Mapping) or not item.get("report_id"):
            return {"status": "blocked", "matrix_id": matrix.get("matrix_id"), "report_ids": []}, ["sell_side_matrix_invalid_row"]
        report_ids.append(str(item["report_id"]))
    if not report_ids:
        return {"status": "missing_evidence", "matrix_id": matrix.get("matrix_id"), "report_ids": []}, ["sell_side_matrix_no_page_verified_reports"]
    return {"status": "available", "matrix_id": matrix.get("matrix_id"), "input_hash": matrix["input_hash"], "report_ids": sorted(report_ids)}, []


def compile_context_pack_models(partial_receipt_path: Path, market_receipt_path: Path, sell_side_matrix_path: Path, *, as_of: str) -> dict[str, Any]:
    """Bind three captured input families into Tier-C models.

    ``as_of`` is one explicit, timezone-qualified research cutoff. Source
    observations retain their actual capture timestamps and may be earlier, but
    never later, than that cutoff; the C3 matrix must declare the cutoff
    exactly. This is a point-in-time rule, not a claim that providers captured
    every source at the same instant.
    """
    partial_raw, partial = _load(partial_receipt_path, _PARTIAL_SCHEMA)
    market_raw, market = _load(market_receipt_path, _MARKET_SCHEMA)
    matrix_raw, matrices = _load(sell_side_matrix_path, _MATRIX_SCHEMA)
    cutoff = _instant(as_of, field="as_of")
    if not partial.get("truth_boundary", {}).get("tier_is_c_only"):
        raise ValueError("partial model receipt must preserve Tier C boundary")
    if market.get("truth_boundary", {}).get("counts_as_tier_a_or_b") is not False:
        raise ValueError("market receipt truth boundary is invalid")
    if matrices.get("truth_boundary", {}).get("counts_as_tier_a_or_b") is not False:
        raise ValueError("sell-side matrix truth boundary is invalid")
    official_sha = str(partial.get("input_receipt_sha256") or "")
    if not _valid_hash(official_sha) or market.get("official_receipt_sha256") != official_sha:
        raise ValueError("market receipt does not match partial official lineage")
    market_sha = _sha256(market_raw)
    if partial.get("companion_receipt_sha256") != market_sha:
        raise ValueError("partial model does not match market companion lineage")
    if matrices.get("research_cutoff") != as_of:
        raise ValueError("sell-side matrix receipt cutoff does not match requested cutoff")

    market_by_ticker = _by_ticker(market.get("tickers"), label="market receipt")
    matrices_by_ticker = _by_ticker(matrices.get("matrices"), label="sell-side matrix receipt")
    output: list[dict[str, Any]] = []
    for entry in partial.get("models") or []:
        if entry.get("status") != "compiled" or not isinstance(entry.get("model"), Mapping):
            output.append({"ticker": entry.get("ticker"), "status": "blocked", "blockers": ["partial_model_not_compiled"]})
            continue
        model = dict(entry["model"])
        ticker = str(model.get("ticker") or "").upper()
        try:
            partial_on_time = _at_or_before(model.get("as_of"), cutoff)
        except ValueError:
            partial_on_time = False
        if not ticker or not partial_on_time:
            output.append({"ticker": ticker or entry.get("ticker"), "status": "blocked", "blockers": ["partial_model_cutoff_mismatch"]})
            continue
        market_component, market_blockers = _market_component(market_by_ticker.get(ticker), cutoff=cutoff)
        sell_side_component, sell_side_blockers = _sell_side_component(matrices_by_ticker.get(ticker), as_of=as_of)
        # Reuse E4's coverage binder while deliberately leaving valuation
        # unavailable: C3 catalog ratings are not valuation receipts.
        covered = bind_coverage(model, valuation_status="missing_evidence", sell_side_status=sell_side_component["status"])
        covered["sections"] = {**covered["sections"], "market": market_component["status"], "fundamentals": market_component["status"]}
        covered["decision_boundary"] = {"tier": "C", "action": "no_action", "target_price": None, "position_range": None}
        material = {key: value for key, value in covered.items() if key != "report_model_hash"}
        covered["report_model_hash"] = digest(material)
        context_pack = {
            "kind": "B6_context_identity_with_E4_component_bindings", "evidence_set_id": model["evidence_set_id"],
            "manifest_hash": model["evidence_manifest_hash"], "ticker": ticker, "as_of": as_of,
            "official_context_as_of": model["as_of"],
            "official": {"status": "available", "official_receipt_sha256": official_sha, "raw_hash": model["raw_hash"], "document_id": model["document_id"]},
            "market_fundamentals": market_component, "sell_side": sell_side_component,
        }
        output.append({"ticker": ticker, "status": "compiled", "context_pack": context_pack, "model": covered, "blockers": sorted(set(model.get("blockers", ()) + market_blockers + sell_side_blockers))})
    receipt = {
        "schema_version": E4_CONTEXT_PACK_MODEL_SCHEMA_VERSION, "data_kind": "real", "as_of": as_of,
        "partial_receipt_sha256": _sha256(partial_raw), "official_receipt_sha256": official_sha,
        "market_receipt_sha256": market_sha, "sell_side_matrix_receipt_sha256": _sha256(matrix_raw), "models": output,
        "counts": {"compiled": sum(row["status"] == "compiled" for row in output), "market_available": sum(row.get("context_pack", {}).get("market_fundamentals", {}).get("status") == "available" for row in output), "sell_side_available": sum(row.get("context_pack", {}).get("sell_side", {}).get("status") == "available" for row in output)},
        "truth_boundary": {"tier_is_c_only": True, "counts_as_tier_a_or_b": False, "counts_as_numeric_page_audit": False, "no_action": True, "not_a_full_equity_research_report": True},
    }
    receipt["receipt_hash"] = digest(receipt)
    return receipt
