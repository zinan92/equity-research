"""Receipt-bound adapters for E4 AI judgment drafts.

The adapter is deliberately narrow: only a real, hash-valid issuer receipt can
populate the C1 inputs listed below.  It preserves the unreviewed status so
``report_contract`` can keep the affected section PARTIAL until a human review
revision exists.
"""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Mapping

from report_contract import UNREVIEWED_JUDGMENT_STATUS


JUDGMENT_RECEIPT_SCHEMA = "e4-m3-catl-judgments-v1"
_CITATION_KEYS = ("document_id", "raw_hash", "page_number", "quoted_anchor", "source_url")

# C1 input types are fixed by the contract.  Array inputs retain one judgment
# object per row; object inputs retain the complete judgment object.
JUDGMENT_INPUTS: dict[str, tuple[tuple[str, str, str], ...]] = {
    "investment_thesis": (("investment_thesis", "investment_thesis", "object"), ("variant_view", "variant_view", "object")),
    "competition_and_moat": (("moat_assessment", "moat_assessment", "object"),),
    "risks_and_falsification": (("risk_register", "risk_register", "array"), ("falsification_tests", "falsification_tests", "array")),
    "monitoring_and_action_triggers": (("monitoring_kpis", "monitoring_kpis", "array"), ("action_triggers", "action_triggers", "array")),
    "accounting_quality": (("accounting_checks", "accounting_checks", "array"),),
    "revenue_quality_and_kpis": (("operating_kpis", "operating_kpis", "array"),),
    "profitability_and_earnings_quality": (("margin_bridge", "margin_bridge", "object"),),
}


def _digest_without_receipt_hash(value: Mapping[str, Any]) -> str:
    payload = {key: item for key, item in value.items() if key != "receipt_hash"}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _validate_judgment(value: Mapping[str, Any], *, key: str) -> None:
    if value.get("status") != UNREVIEWED_JUDGMENT_STATUS:
        raise ValueError(f"{key} is not an unreviewed AI judgment")
    facts = value.get("facts")
    if not isinstance(facts, list) or not facts:
        raise ValueError(f"{key} has no page-level evidence")
    for fact in facts:
        citation = fact.get("citation") if isinstance(fact, dict) else None
        if not isinstance(citation, dict) or any(not citation.get(item) for item in _CITATION_KEYS):
            raise ValueError(f"{key} has an incomplete page-level citation")


def wire_unreviewed_judgment_receipt(receipt: Mapping[str, Any], *, ticker: str) -> dict[str, dict[str, Any]]:
    """Map qualifying draft judgments into their fixed C1 section inputs.

    Missing fields remain absent: receipt existence alone is never treated as
    completion.  ``receipt_id`` is the content hash of the exact real run.
    """
    if receipt.get("schema_version") != JUDGMENT_RECEIPT_SCHEMA or receipt.get("data_kind") != "real":
        raise ValueError("judgment receipt is not a real E4 judgment run")
    if str(receipt.get("ticker", "")).upper() != ticker.upper():
        raise ValueError("judgment receipt ticker mismatch")
    if receipt.get("receipt_hash") != _digest_without_receipt_hash(receipt):
        raise ValueError("judgment receipt hash mismatch")
    content = receipt.get("content")
    if not isinstance(content, dict):
        raise ValueError("judgment receipt content is missing")
    provenance = {
        "receipt_id": f"{JUDGMENT_RECEIPT_SCHEMA}:{receipt['receipt_hash']}",
        "receipt_hash": receipt["receipt_hash"],
        "source_dossier_receipt": receipt.get("source_dossier_receipt"),
    }
    section_inputs: dict[str, dict[str, Any]] = {}
    for section_id, mappings in JUDGMENT_INPUTS.items():
        for source_key, input_key, input_type in mappings:
            source = content.get(source_key)
            if not isinstance(source, dict) or source.get("status") != UNREVIEWED_JUDGMENT_STATUS:
                continue
            _validate_judgment(source, key=source_key)
            adapted = deepcopy(source)
            adapted["source_receipt"] = provenance
            section_inputs.setdefault(section_id, {})[input_key] = [adapted] if input_type == "array" else adapted
    return section_inputs
