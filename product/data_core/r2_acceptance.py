"""Fail-closed R2 acceptance audit for the AI-compute world model."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Iterable, Mapping

from .industry_catalysts import IndustryCatalystProfile, build_catalyst_profiles, catalyst_coverage
from .industry_company_index import IndustryCompanyIndex, build_industry_company_index
from .industry_graph import EvidenceCapture, IndustryGraph, build_audited_graph
from .industry_ontology import build_ontology
from .n3_dossier_batch import N3_DOSSIER_BATCH_SCHEMA_VERSION
from .n3_financial_delivery import N3_FINANCIAL_DELIVERY_SCHEMA_VERSION
from .n3_falsifier_evidence import N3_FALSIFIER_EVIDENCE_SCHEMA_VERSION
from .n3_moat_evidence import N3_MOAT_EVIDENCE_SCHEMA_VERSION


R2_ACCEPTANCE_SCHEMA_VERSION = "r2-ai-compute-world-model-acceptance-v1"
QUESTION_NAMES = ("layer", "moat", "financial_delivery", "market_future", "falsifier")
ARCHIVE_ISOLATION_MODULES = (
    "product/data_core/company_positions.py",
    "product/data_core/industry_company_index.py",
    "product/data_core/industry_graph.py",
    "product/data_core/industry_catalysts.py",
    "product/data_core/n3_dossier_batch.py",
    "product/data_core/dossier_generator.py",
    "product/data_core/decision_policy.py",
    "product/data_core/offline_report_model.py",
)


def _archive_isolation(root: Path) -> dict[str, object]:
    """Assert production data/research code has no archived-product dependency."""

    inspected = tuple(root / relative for relative in ARCHIVE_ISOLATION_MODULES)
    missing = [str(path.relative_to(root)) for path in inspected if not path.is_file()]
    offenders = [str(path.relative_to(root)) for path in inspected if path.is_file() and "ainiusq" in path.read_text(encoding="utf-8").lower()]
    if missing:
        offenders.extend(missing)
    return {"inspected_files": len(inspected), "offenders": offenders, "passed": not offenders}


def _batch_counts(receipt: Mapping[str, object]) -> dict[str, int]:
    if receipt.get("schema_version") != N3_DOSSIER_BATCH_SCHEMA_VERSION:
        raise ValueError("R2 audit requires N3-S5 dossier receipt")
    counts = receipt.get("counts")
    if not isinstance(counts, Mapping):
        raise ValueError("N3-S5 receipt is missing counts")
    required = ("requested", "compiled", "failed", "no_action")
    if any(not isinstance(counts.get(key), int) for key in required):
        raise ValueError("N3-S5 receipt counts are invalid")
    return {key: int(counts[key]) for key in required}


def _financial_delivery_rows(
    receipt: Mapping[str, object] | None,
    *,
    dossier_selection_identity: str | None,
) -> set[str]:
    if receipt is None:
        return set()
    if receipt.get("schema_version") != N3_FINANCIAL_DELIVERY_SCHEMA_VERSION:
        raise ValueError("R2 audit requires N3 financial-delivery receipt")
    if receipt.get("selection_identity") != dossier_selection_identity:
        raise ValueError("financial-delivery receipt selection identity mismatch")
    return {
        str(row.get("ticker")).upper()
        for row in receipt.get("tickers", [])
        if isinstance(row, Mapping) and row.get("financial_delivery_available") is True
    }


def _falsifier_rows(
    receipt: Mapping[str, object] | None,
    *,
    dossier_selection_identity: str | None,
) -> set[str]:
    if receipt is None:
        return set()
    if receipt.get("schema_version") != N3_FALSIFIER_EVIDENCE_SCHEMA_VERSION:
        raise ValueError("R2 audit requires N3 falsifier-evidence receipt")
    if receipt.get("selection_identity") != dossier_selection_identity:
        raise ValueError("falsifier-evidence receipt selection identity mismatch")
    accepted: set[str] = set()
    for row in receipt.get("rows", []):
        if not isinstance(row, Mapping) or row.get("status") != "accepted":
            continue
        evidence = row.get("evidence")
        if not isinstance(evidence, Mapping):
            continue
        required = ("ticker", "evidence_id", "source_url", "raw_hash", "page_number", "known_at", "observed_condition")
        if any(not evidence.get(key) for key in required):
            continue
        if str(evidence.get("ticker")).upper() != str(row.get("ticker")).upper():
            continue
        accepted.add(str(row["ticker"]).upper())
    return accepted


def _moat_rows(
    receipt: Mapping[str, object] | None,
    *,
    dossier_selection_identity: str | None,
) -> set[str]:
    if receipt is None:
        return set()
    if receipt.get("schema_version") != N3_MOAT_EVIDENCE_SCHEMA_VERSION:
        raise ValueError("R2 audit requires N3 moat-evidence receipt")
    if receipt.get("selection_identity") != dossier_selection_identity:
        raise ValueError("moat-evidence receipt selection identity mismatch")
    accepted: set[str] = set()
    for row in receipt.get("rows", []):
        if not isinstance(row, Mapping) or row.get("status") != "accepted":
            continue
        evidence = row.get("evidence")
        required = ("ticker", "evidence_id", "source_url", "raw_hash", "page_number", "known_at", "observed_capability")
        if not isinstance(evidence, Mapping) or any(not evidence.get(key) for key in required):
            continue
        if str(evidence.get("ticker")).upper() == str(row.get("ticker")).upper():
            accepted.add(str(row["ticker"]).upper())
    return accepted


def _five_question_coverage(index: IndustryCompanyIndex, catalyst_profiles: Iterable[IndustryCatalystProfile], batch: Mapping[str, object], financial_delivery: set[str], falsifier_evidence: set[str], moat_evidence: set[str]) -> dict[str, dict[str, object]]:
    compiled = {str(row.get("ticker")).upper() for row in batch.get("rows", []) if isinstance(row, Mapping) and row.get("status") == "compiled"}
    accepted = [position for position in index.review_records if position.status == "accepted" and position.ticker.upper() in compiled]
    profiles = {profile.segment_id: profile for profile in catalyst_profiles}
    accepted_tickers = {item.ticker.upper() for item in accepted}
    # The current N3 contract has cited positions only. It has not yet parsed
    # company-specific moat, financial delivery, market-future or falsifier facts.
    return {
        "layer": {"covered": len(accepted), "required": 20, "source": "accepted_company_position"},
        "moat": {"covered": len(accepted_tickers.intersection(moat_evidence)), "required": 20, "source": "n3_company_moat_evidence" if moat_evidence else "missing_company_moat_evidence"},
        "financial_delivery": {"covered": len(accepted_tickers.intersection(financial_delivery)), "required": 20, "source": "n3_pit_financial_delivery" if financial_delivery else "missing_parsed_financial_evidence"},
        "market_future": {"covered": 0, "required": 20, "source": "missing_market_expectation_evidence"},
        "falsifier": {"covered": len(accepted_tickers.intersection(falsifier_evidence)), "required": 20, "source": "n3_company_falsifier_evidence" if falsifier_evidence else "missing_company_falsifier_evidence"},
    }


def audit_r2(
    batch_receipt: Mapping[str, object],
    captures: Iterable[EvidenceCapture],
    *,
    repository_root: Path,
    financial_delivery_receipt: Mapping[str, object] | None = None,
    falsifier_evidence_receipt: Mapping[str, object] | None = None,
    moat_evidence_receipt: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Evaluate the R2 contract without allowing a count-only pass."""

    nodes, segments = build_ontology()
    index = build_industry_company_index()
    graph: IndustryGraph = build_audited_graph(captures, as_of="2026-07-24")
    profiles = build_catalyst_profiles(captures, as_of="2026-07-24")
    batch_counts = _batch_counts(batch_receipt)
    financial_delivery = _financial_delivery_rows(
        financial_delivery_receipt,
        dossier_selection_identity=str(batch_receipt.get("selection_identity") or ""),
    )
    falsifier_evidence = _falsifier_rows(
        falsifier_evidence_receipt,
        dossier_selection_identity=str(batch_receipt.get("selection_identity") or ""),
    )
    moat_evidence = _moat_rows(
        moat_evidence_receipt,
        dossier_selection_identity=str(batch_receipt.get("selection_identity") or ""),
    )
    questions = _five_question_coverage(index, profiles, batch_receipt, financial_delivery, falsifier_evidence, moat_evidence)
    isolation = _archive_isolation(repository_root)
    gates = {
        "ontology": 10 <= len(nodes) <= 15 and len(segments) >= 104,
        "company_positions": 50 <= len(index.review_records) <= 100 and index.coverage()["accepted"] >= 20,
        "relationship_graph": graph.audit()["accepted"] > 0,
        "dossiers": batch_counts == {"requested": 20, "compiled": 20, "failed": 0, "no_action": 20},
        "five_questions": all(value["covered"] >= value["required"] for value in questions.values()),
        "archive_isolation": bool(isolation["passed"]),
    }
    return {
        "schema_version": R2_ACCEPTANCE_SCHEMA_VERSION,
        "status": "passed" if all(gates.values()) else "partial",
        "gates": gates,
        "ontology": {"node_count": len(nodes), "segment_count": len(segments)},
        "company_positions": dict(index.coverage()),
        "relationship_graph": dict(graph.audit()),
        "catalysts": catalyst_coverage(profiles),
        "dossiers": batch_counts,
        "five_questions": questions,
        "archive_isolation": isolation,
        "truth_boundary": {"count_only_cannot_pass": True, "no_action_is_not_recommendation": True},
    }
