"""Wire real vertical-slice filing facts through B6, C1 and degradation.

This is intentionally narrow: it produces an honest partial contract for one
issuer and delegates the tier decision to ``assess_any_ticker`` unchanged.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any, Iterable

from report_contract import build_research_section_contract_v2

from .contracts import RecordDomain, SourceManifest, digest
from .e4_page_level_filing_facts import FilingNumericFact
from .evidence_gate import EvidenceCandidate, EvidenceGatePolicy, EvidenceRequirement, EvidenceRole, build_evidence_set
from .research_degradation import assess_any_ticker


E4_VERTICAL_DEGRADATION_SCHEMA_VERSION = "e4-vertical-degradation-v1"


def _candidate(ticker: str, facts: tuple[FilingNumericFact, ...], *, known_at: str) -> EvidenceCandidate:
    first = facts[0]
    manifest = SourceManifest(
        source_key="official_filing_page_fact_v1", domain_scope=RecordDomain.DOCUMENT.value,
        authority_tier="official", provider_version="e4-vertical-degradation-v1",
        schema_version="official-filing-page-fact-v1", license_status="public_disclosure_internal_use",
        source_url=first.source_url,
    )
    manifest.validate()
    return EvidenceCandidate(
        evidence_id="official-page-fact:" + first.raw_hash[:40], ticker=ticker, component="filings",
        role=EvidenceRole.PRIMARY, source_key=manifest.source_key, source_family="official-regulatory",
        authority_tier="official", independent_of_subject=False, status="accepted", known_at=known_at,
        effective_at=known_at, manifest_hash=manifest.manifest_hash, raw_hash=first.raw_hash,
        record_hash=digest({"document_id": first.document_id, "facts": [asdict(item) for item in facts]}),
    )


def compile_vertical_degradation(
    ticker: str, facts: Iterable[FilingNumericFact], *, known_at: str,
) -> dict[str, Any]:
    materialized = tuple(facts)
    if not materialized:
        raise ValueError("vertical degradation requires at least one page-level filing fact")
    if any(item.ticker.upper() != ticker.upper() for item in materialized):
        raise ValueError("page-level filing fact ticker mismatch")
    if any(item.statement_scope != "consolidated" for item in materialized):
        raise ValueError("vertical degradation only accepts consolidated page-level facts")
    candidate = _candidate(ticker.upper(), materialized, known_at=known_at)
    # This is the existing B6 shape for one accepted official filing; no
    # requirement, conflict, or freshness setting is relaxed here.
    evidence_set = build_evidence_set(
        ticker=ticker.upper(), candidates=(candidate,), policy=EvidenceGatePolicy(
            as_of=known_at, requirements=(EvidenceRequirement("filings", min_primary=1),),
        ),
    )
    citation_index = [asdict(item) for item in materialized]
    # A revenue row extracted from an official, immutable filing page is also
    # a real (albeit one-period) revenue-history observation.  Keep the full
    # page identity instead of substituting a vendor F10 series.  This is
    # intentionally insufficient for a FULL section: operating KPIs remain
    # absent until an evidence-bound source supplies them.
    revenue_history = [
        asdict(item) for item in materialized if item.metric == "revenue"
    ]
    section_inputs = {
        # A page-cited filing proves these objects exist, not a valuation,
        # thesis, peer set, or investment decision.
        "profitability_and_earnings_quality": {"income_history": citation_index},
        "revenue_quality_and_kpis": {"revenue_history": revenue_history},
        "evidence_and_methodology": {
            "evidence_set_receipt": {"id": evidence_set.evidence_set_id, "status": evidence_set.receipt.status},
            "citation_index": citation_index,
            "methodology": {"parser": "park-document-parser-v1", "source": "official_pdf_page_fact"},
        },
    }
    contract = build_research_section_contract_v2(
        section_inputs, structure_only=False, evidence_set=evidence_set,
    )
    degradation = assess_any_ticker(ticker.upper(), evidence_set=evidence_set, section_contract=contract, data_kind="real")
    return {
        "ticker": ticker.upper(), "data_kind": "real", "page_facts": citation_index,
        "evidence_set": {
            "evidence_set_id": evidence_set.evidence_set_id, "manifest_hash": evidence_set.manifest_hash,
            "status": evidence_set.receipt.status, "coverage": {
                "requirements": [asdict(item) for item in evidence_set.receipt.coverage.requirements],
                "source_gaps": [asdict(item) for item in evidence_set.receipt.coverage.source_gaps],
            },
        },
        "section_contract": {
            "evidence_manifest_hash": contract.evidence_manifest_hash, "live_eligible": contract.live_eligible,
            "sections": [asdict(item) for item in contract.sections],
        },
        "degradation": asdict(degradation),
    }
