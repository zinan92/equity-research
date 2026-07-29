"""Receipt-bound adapters for E4 AI judgment drafts.

The adapter is deliberately narrow: only a real, hash-valid issuer receipt can
populate the C1 inputs listed below.  It preserves the unreviewed status so
``report_contract`` can keep the affected section PARTIAL until a human review
revision exists.
"""
from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from typing import Any, Mapping

from report_contract import UNREVIEWED_JUDGMENT_STATUS


JUDGMENT_RECEIPT_SCHEMA = "e4-m3-catl-judgments-v1"
JUDGMENT_RECEIPT_SCHEMAS = frozenset({
    JUDGMENT_RECEIPT_SCHEMA,
    "e4-m3-catl-judgments-v2",
    "e4-model-judgments-v1",
})
_CITATION_KEYS = ("document_id", "raw_hash", "page_number", "quoted_anchor", "source_url")
_HASH = re.compile(r"^[0-9a-f]{64}$")

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
    # Match the v1 runtime writer exactly.  Receipt identity is about the
    # bytes the producer emitted, not a re-serialized approximation.
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


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


def _canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode()
    ).hexdigest()


def _validate_model_receipt(receipt: Mapping[str, Any]) -> None:
    if receipt.get("generator_version") != "e4-model-judgments-v1":
        raise ValueError("model judgment generator version mismatch")
    if receipt.get("prompt_version") != "e4-model-judgments-prompt-v1":
        raise ValueError("model judgment prompt version mismatch")
    if receipt.get("validator_version") != "e4-model-judgments-validator-v1":
        raise ValueError("model judgment validator version mismatch")
    for key in ("input_hash", "prompt_hash", "content_hash"):
        if not _HASH.fullmatch(str(receipt.get(key) or "")):
            raise ValueError("model judgment " + key + " is invalid")
    content = receipt.get("content")
    if not isinstance(content, Mapping) or receipt["content_hash"] != _canonical_hash(content):
        raise ValueError("model judgment content hash mismatch")
    available = [
        value
        for value in content.values()
        if isinstance(value, Mapping)
        and value.get("status") == UNREVIEWED_JUDGMENT_STATUS
    ]
    calls = receipt.get("model_receipts")
    if available and (
        not isinstance(calls, list)
        or not calls
        or any(
            not row.get("request_id")
            or not row.get("model")
            or row.get("finish_reason") != "stop"
            for row in calls
        )
    ):
        raise ValueError("model judgment lacks a completed real model-call receipt")
    response_hashes = receipt.get("response_hashes")
    if available and (
        not isinstance(response_hashes, list)
        or len(response_hashes) != len(calls)
        or any(not _HASH.fullmatch(str(value or "")) for value in response_hashes)
    ):
        raise ValueError("model judgment response hashes are incomplete")
    validation = receipt.get("validation")
    if not isinstance(validation, Mapping) or validation.get("status") not in {
        "passed",
        "partial",
    }:
        raise ValueError("model judgment validation receipt is missing")
    errors = validation.get("errors") or {}
    if "__response__" in errors:
        raise ValueError("model judgment has response-level validation errors")


def wire_unreviewed_judgment_receipt(receipt: Mapping[str, Any], *, ticker: str) -> dict[str, dict[str, Any]]:
    """Map qualifying draft judgments into their fixed C1 section inputs.

    Missing fields remain absent: receipt existence alone is never treated as
    completion.  ``receipt_id`` is the content hash of the exact real run.
    """
    if receipt.get("schema_version") not in JUDGMENT_RECEIPT_SCHEMAS or receipt.get("data_kind") != "real":
        raise ValueError("judgment receipt is not a real E4 judgment run")
    if str(receipt.get("ticker", "")).upper() != ticker.upper():
        raise ValueError("judgment receipt ticker mismatch")
    if receipt.get("receipt_hash") != _digest_without_receipt_hash(receipt):
        raise ValueError("judgment receipt hash mismatch")
    if receipt.get("schema_version") == "e4-model-judgments-v1":
        _validate_model_receipt(receipt)
    content = receipt.get("content")
    if not isinstance(content, dict):
        raise ValueError("judgment receipt content is missing")
    provenance = {
        "receipt_id": f"{receipt['schema_version']}:{receipt['receipt_hash']}",
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
