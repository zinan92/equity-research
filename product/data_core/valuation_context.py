"""Bind deterministic valuation and sell-side outputs to an accepted Context Pack.

This module deliberately does not fetch data or create valuation assumptions.  It
only proves that an existing C2/C3 result can be replayed from a frozen evidence
identity, and fails closed when the Context Pack is not sufficient for the
requested output.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Iterable, Sequence

from report_contract import DeterministicValuationResult, ValuationEngineInput, run_deterministic_valuation

from .evidence_gate import ResearchContextPack
from .viewpoint_matrix import SellSideViewpoint, SellSideViewpointMatrix


VALUATION_CONTEXT_SCHEMA_VERSION = "park-valuation-context-v1"


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _as_of_date(value: str) -> str:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()


def _require_context_components(context: ResearchContextPack, required: Sequence[str]) -> None:
    available = {item.component for item in context.evidence}
    missing = sorted(set(required).difference(available))
    if missing:
        raise ValueError("Context Pack is missing required components: " + ", ".join(missing))


@dataclass(frozen=True)
class ContextBoundValuation:
    schema_version: str
    context_evidence_set_id: str
    context_manifest_hash: str
    ticker: str
    required_components: tuple[str, ...]
    valuation: DeterministicValuationResult
    binding_hash: str


@dataclass(frozen=True)
class ViewpointContextReceipt:
    schema_version: str
    context_evidence_set_id: str
    context_manifest_hash: str
    matrix_id: str
    ticker: str
    accepted_report_ids: tuple[str, ...]
    missing_fields: tuple[str, ...]
    blocked_claim_ids: tuple[str, ...]
    receipt_hash: str


def run_context_bound_valuation(
    context: ResearchContextPack,
    value: ValuationEngineInput,
    *,
    required_components: Sequence[str] = ("market", "financials", "valuation"),
) -> ContextBoundValuation:
    """Run C2 unchanged and bind its exact input/output hashes to Context Pack identity."""

    if value.ticker.upper() != context.ticker.upper():
        raise ValueError("valuation ticker does not match Context Pack")
    normalized_components = tuple(sorted(set(required_components)))
    if not normalized_components or any(not component.strip() for component in normalized_components):
        raise ValueError("required context components must be non-empty")
    _require_context_components(context, normalized_components)
    result = run_deterministic_valuation(value)
    payload = {
        "schema_version": VALUATION_CONTEXT_SCHEMA_VERSION,
        "context_evidence_set_id": context.evidence_set_id,
        "context_manifest_hash": context.manifest_hash,
        "ticker": context.ticker.upper(),
        "required_components": list(normalized_components),
        "valuation_input_hash": result.input_hash,
        "valuation_output_hash": result.output_hash,
    }
    return ContextBoundValuation(
        schema_version=VALUATION_CONTEXT_SCHEMA_VERSION,
        context_evidence_set_id=context.evidence_set_id,
        context_manifest_hash=context.manifest_hash,
        ticker=context.ticker.upper(),
        required_components=normalized_components,
        valuation=result,
        binding_hash=_digest(payload),
    )


def validate_viewpoint_matrix_context(
    context: ResearchContextPack,
    matrix: SellSideViewpointMatrix,
    viewpoints: Iterable[SellSideViewpoint],
) -> ViewpointContextReceipt:
    """Return a deterministic receipt only when every matrix report is accepted evidence.

    The C3 matrix has already checked report/document/page citations.  This
    bridge adds the remaining join: each report body raw hash must be present in
    the accepted Context Pack.  Missing report fields and blocked claims remain
    visible in the receipt; they are never silently filled.
    """

    if matrix.ticker.upper() != context.ticker.upper():
        raise ValueError("viewpoint matrix ticker does not match Context Pack")
    if _as_of_date(matrix.as_of) > _as_of_date(context.as_of):
        raise ValueError("viewpoint matrix as_of is after Context Pack cutoff")
    supplied = tuple(viewpoints)
    by_id = {item.report_id: item for item in supplied}
    row_ids = tuple(row.report_id for row in matrix.rows)
    if len(by_id) != len(supplied) or set(row_ids) != set(by_id):
        raise ValueError("supplied viewpoints do not exactly match matrix rows")
    accepted_hashes = {item.raw_hash for item in context.evidence}
    unbound = sorted(item.report_id for item in supplied if item.raw_hash not in accepted_hashes)
    if unbound:
        raise ValueError("viewpoint reports are not accepted Context Pack evidence: " + ", ".join(unbound))
    for item in supplied:
        item.validate()
    missing_fields = tuple(sorted({field for row in matrix.rows for field in row.missing_fields}))
    blocked_claim_ids = tuple(sorted(item.claim_id for item in matrix.blocked_claims))
    payload = {
        "schema_version": VALUATION_CONTEXT_SCHEMA_VERSION,
        "context_evidence_set_id": context.evidence_set_id,
        "context_manifest_hash": context.manifest_hash,
        "matrix_id": matrix.matrix_id,
        "matrix_input_hash": matrix.input_hash,
        "ticker": context.ticker.upper(),
        "accepted_report_ids": sorted(row_ids),
        "missing_fields": list(missing_fields),
        "blocked_claim_ids": list(blocked_claim_ids),
    }
    return ViewpointContextReceipt(
        schema_version=VALUATION_CONTEXT_SCHEMA_VERSION,
        context_evidence_set_id=context.evidence_set_id,
        context_manifest_hash=context.manifest_hash,
        matrix_id=matrix.matrix_id,
        ticker=context.ticker.upper(),
        accepted_report_ids=tuple(sorted(row_ids)),
        missing_fields=missing_fields,
        blocked_claim_ids=blocked_claim_ids,
        receipt_hash=_digest(payload),
    )
