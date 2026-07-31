"""Receipt-bound C1 adapters for the accepted R2 industry world model."""
from __future__ import annotations

import hashlib
import json
from pathlib import PurePosixPath
from typing import Any, Mapping

from .industry_company_index import build_industry_company_index
from .industry_ontology import build_ontology, ontology_receipt
from .n3_dossier_batch import N3_DOSSIER_BATCH_SCHEMA_VERSION
from .r2_acceptance import R2_ACCEPTANCE_SCHEMA_VERSION


def _hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _filing_document_id(url: str) -> str:
    name = PurePosixPath(url).name.rsplit(".", 1)[0]
    return f"official-filing:cninfo:{name}"


def _validate_r2(audit: Mapping[str, Any], batch: Mapping[str, Any]) -> None:
    if audit.get("schema_version") != R2_ACCEPTANCE_SCHEMA_VERSION or audit.get("status") != "passed":
        raise ValueError("R2 acceptance receipt is not passed")
    if not all(bool(value) for value in (audit.get("gates") or {}).values()):
        raise ValueError("R2 acceptance receipt has a failed gate")
    if batch.get("schema_version") != N3_DOSSIER_BATCH_SCHEMA_VERSION:
        raise ValueError("R2 dossier receipt schema mismatch")
    counts = batch.get("counts") or {}
    if {key: counts.get(key) for key in ("requested", "compiled", "failed", "no_action")} != {"requested": 20, "compiled": 20, "failed": 0, "no_action": 20}:
        raise ValueError("R2 dossier receipt is incomplete")


def wire_r2_industry_receipts(
    acceptance_receipt: Mapping[str, Any], dossier_receipt: Mapping[str, Any], *, ticker: str,
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """Return only issuer-specific R2 inputs that retain a real receipt chain.

    The ontology itself is an industry model, not an issuer fact.  It becomes a
    C1 industry profile only where an accepted, official-page-cited company
    position links the issuer to one of its segments.  R2 has no dated,
    issuer-specific catalyst calendar, so this adapter intentionally never
    manufactures ``catalyst_calendar``.
    """
    _validate_r2(acceptance_receipt, dossier_receipt)
    normalized = ticker.upper()
    dossier = next((row for row in dossier_receipt.get("rows", []) if isinstance(row, dict) and str(row.get("ticker", "")).upper() == normalized and row.get("status") == "compiled"), None)
    position = build_industry_company_index().company(normalized)
    if dossier is None or position is None or position.citation is None:
        return {}, {"shape_mismatch": "no accepted issuer-specific R2 company position and dossier"}
    url, page, raw_hash = position.citation
    nodes, segments = build_ontology()
    segment = next(item for item in segments if item.segment_id == position.segment_id)
    node = next(item for item in nodes if item.node_id == segment.node_id)
    acceptance_id = acceptance_receipt.get("receipt_hash") or _hash(acceptance_receipt)
    dossier_id = dossier_receipt.get("receipt_hash") or _hash(dossier_receipt)
    source_receipts = {
        "r2_acceptance_receipt_id": f"{R2_ACCEPTANCE_SCHEMA_VERSION}:{acceptance_id}",
        "r2_dossier_receipt_id": f"{N3_DOSSIER_BATCH_SCHEMA_VERSION}:{dossier_id}",
        "r2_dossier_file_sha256": _hash(dossier_receipt),
    }
    citation = {"document_id": _filing_document_id(url), "page": page, "raw_hash": raw_hash, "source_url": url}
    company_profile = {
        "status": "accepted_r2_company_profile", "ticker": normalized, "name": position.name,
        "role": position.role, "segment_id": position.segment_id, "dossier_id": dossier["dossier_id"],
        "citation": citation, "source_receipts": source_receipts,
        "truth_boundary": "R2 position and dossier are no_action research objects, not a target price or action.",
    }
    industry_profile = {
        "status": "accepted_r2_industry_profile", "ticker": normalized,
        "node": {"id": node.node_id, "name": node.name, "definition": node.definition, "boundary": node.boundary},
        "segment": {"id": segment.segment_id, "name": segment.name, "definition": segment.definition, "boundary": segment.boundary},
        "issuer_position": {"role": position.role, "citation": citation},
        "ontology_receipt": ontology_receipt(), "source_receipts": source_receipts,
        "truth_boundary": "Industry taxonomy is a research model; the issuer link is the page-cited company position.",
    }
    return {
        "business_model_and_business_lines": {
            "industry_evidence": [industry_profile],
            "company_position": company_profile,
            "business_evidence": [company_profile],
        },
    }, source_receipts
