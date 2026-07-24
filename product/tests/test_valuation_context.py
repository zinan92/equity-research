from __future__ import annotations

import hashlib
import sys
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PRODUCT = ROOT / "product"
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from data_core import (  # noqa: E402
    EvidenceCandidate,
    EvidenceGatePolicy,
    EvidenceRequirement,
    EvidenceRole,
    build_context_pack,
    build_evidence_set,
    build_sell_side_viewpoint_matrix,
    run_context_bound_valuation,
    validate_viewpoint_matrix_context,
)
from data_core.document_intelligence import (  # noqa: E402
    DocumentChunk,
    DocumentPage,
    DocumentParseResult,
    PageCitation,
)
from data_core.consensus_history import normalize_broker_estimate  # noqa: E402
from data_core.viewpoint_matrix import SellSideViewpoint, ViewpointClaim  # noqa: E402
from report_contract import (  # noqa: E402
    HistoricalFinancialPeriod,
    ValuationEngineInput,
    ValuationScenarioAssumptions,
)


AS_OF = "2026-07-22T10:00:00Z"


def sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def context(*, report_raw_hash: str | None = None):
    components = ("market", "financials", "valuation")
    candidates = [
        EvidenceCandidate(
            evidence_id=component,
            ticker="300750.SZ",
            component=component,
            role=EvidenceRole.PRIMARY,
            source_key=f"official_{component}",
            source_family="issuer_or_exchange",
            authority_tier="official",
            independent_of_subject=False,
            status="accepted",
            known_at="2026-07-21T10:00:00Z",
            effective_at="2026-07-20T10:00:00Z",
            manifest_hash=sha("manifest-" + component),
            raw_hash=sha("raw-" + component),
            record_hash=sha("record-" + component),
        )
        for component in components
    ]
    requirements = [EvidenceRequirement(component, min_primary=1, min_total=1) for component in components]
    if report_raw_hash:
        candidates.append(
            EvidenceCandidate(
                evidence_id="sell-side-report",
                ticker="300750.SZ",
                component="sell_side",
                role=EvidenceRole.INDEPENDENT,
                source_key="broker_archive",
                source_family="broker_research",
                authority_tier="supplementary_only",
                independent_of_subject=True,
                status="accepted",
                known_at="2026-07-21T10:00:00Z",
                effective_at="2026-07-20T10:00:00Z",
                manifest_hash=sha("manifest-report"),
                raw_hash=report_raw_hash,
                record_hash=sha("record-report"),
            )
        )
        requirements.append(EvidenceRequirement("sell_side", min_independent=1, min_total=1))
    evidence_set = build_evidence_set(
        ticker="300750.SZ",
        candidates=candidates,
        policy=EvidenceGatePolicy(as_of=AS_OF, requirements=tuple(requirements)),
    )
    assert evidence_set.publishable
    return build_context_pack(evidence_set)


def valuation_input() -> ValuationEngineInput:
    def period(year: int, revenue: float) -> HistoricalFinancialPeriod:
        return HistoricalFinancialPeriod(
            period=f"{year}-12-31", currency="CNY", revenue=revenue, ebit=revenue * 0.2,
            tax_rate=0.2, depreciation_amortization=revenue * 0.04, capital_expenditure=revenue * 0.08,
            change_in_nwc=revenue * 0.01, operating_cash_flow=revenue * 0.18, net_income=revenue * 0.15,
            cash=1500, debt=1000, assets=7000, liabilities=3000, equity=4000,
            shares_outstanding=2_400_000_000,
        )
    def scenario(name: str, probability: float, growth: float, margin: float) -> ValuationScenarioAssumptions:
        return ValuationScenarioAssumptions(
            name, probability, (growth,) * 5, (margin,) * 5, 0.2, 0.04, 0.08, 0.01, 0.09, 0.03
        )
    return ValuationEngineInput(
        ticker="300750.SZ", currency="CNY", unit_scale=100_000_000, current_price=250,
        market_cap=600_000_000_000, shares_outstanding=2_400_000_000,
        historical=(period(2024, 3000), period(2025, 4000)),
        scenarios=(scenario("bear", .25, .03, .16), scenario("base", .5, .12, .2), scenario("bull", .25, .22, .24)),
        peer_ev_ebitda=(14, 16, 18), historical_pe=(20, 24, 28),
    )


def one_viewpoint() -> tuple[SellSideViewpoint, dict[str, DocumentParseResult]]:
    raw_hash = "a" * 64
    document_id = "broker-report-1"
    text = "The report supports durable demand with a page-bound statement."
    page = DocumentPage(document_id, 1, raw_hash, "test-parser", text, sha(text), "native_text", "none_detected")
    chunk = DocumentChunk("chunk-1", document_id, 1, raw_hash, "test-parser", 0, len(text), text, "native_text")
    document = DocumentParseResult(document_id, raw_hash, "test-parser", "parse-1", (page,), (chunk,), ())
    claim = ViewpointClaim(
        "claim-1", "demand", "bullish", "Demand is durable", "explicit",
        (PageCitation(document_id, 1, raw_hash, "durable demand", "chunk-1"),),
    )
    estimate = normalize_broker_estimate(
        ticker="300750.SZ", broker="Broker A", analyst="Analyst", report_id="report-1",
        report_date="2026-07-20", raw_hash=raw_hash, fiscal_year=2027, eps=10, target_price=400, rating="增持",
    )
    viewpoint = SellSideViewpoint(
        "300750.SZ", "report-1", "CATL update", document_id, raw_hash, "Broker A", "Analyst",
        "2026-07-20", "增持", 400, "CNY", (estimate,), (claim,),
    )
    return viewpoint, {document_id: document}


def test_valuation_replays_from_context_identity_and_missing_components_fail_closed() -> None:
    first = run_context_bound_valuation(context(), valuation_input())
    second = run_context_bound_valuation(context(), valuation_input())

    assert first == second
    assert first.context_manifest_hash == context().manifest_hash
    assert len(first.binding_hash) == 64
    assert first.valuation.output_hash
    with pytest.raises(ValueError, match="missing required components"):
        run_context_bound_valuation(context(), valuation_input(), required_components=("sell_side",))
    with pytest.raises(ValueError, match="ticker"):
        run_context_bound_valuation(context(), replace(valuation_input(), ticker="600519.SH"))


def test_viewpoint_receipt_requires_accepted_report_body_raw_hash_and_preserves_gaps() -> None:
    viewpoint, corpus = one_viewpoint()
    matrix = build_sell_side_viewpoint_matrix("300750.SZ", (viewpoint,), corpus, as_of="2026-07-21")
    receipt = validate_viewpoint_matrix_context(context(report_raw_hash=viewpoint.raw_hash), matrix, (viewpoint,))
    replay = validate_viewpoint_matrix_context(context(report_raw_hash=viewpoint.raw_hash), matrix, (viewpoint,))

    assert receipt == replay
    assert receipt.accepted_report_ids == ("report-1",)
    assert receipt.blocked_claim_ids == ()
    assert receipt.missing_fields == ()
    assert len(receipt.receipt_hash) == 64
    with pytest.raises(ValueError, match="not accepted Context Pack evidence"):
        validate_viewpoint_matrix_context(context(), matrix, (viewpoint,))


def test_fixture_or_rejected_evidence_cannot_be_promoted_into_the_context() -> None:
    item = EvidenceCandidate(
        evidence_id="fixture", ticker="300750.SZ", component="market", role=EvidenceRole.PRIMARY,
        source_key="fixture", source_family="test", authority_tier="official", independent_of_subject=False,
        status="accepted", known_at="2026-07-21T10:00:00Z", effective_at="2026-07-20T10:00:00Z",
        manifest_hash=sha("fixture-manifest"), raw_hash=sha("fixture-raw"), record_hash=sha("fixture-record"),
        quality_flags=("fixture",),
    )
    evidence_set = build_evidence_set(
        ticker="300750.SZ", candidates=(item,),
        policy=EvidenceGatePolicy(as_of=AS_OF, requirements=(EvidenceRequirement("market", min_primary=1),)),
    )
    assert evidence_set.publishable is False
    with pytest.raises(ValueError, match="coverage and conflict"):
        build_context_pack(evidence_set)
