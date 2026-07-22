from __future__ import annotations

import hashlib
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
PRODUCT = ROOT / "product"
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from data_core import (  # noqa: E402
    EvidenceCandidate,
    EvidenceConflict,
    EvidenceGatePolicy,
    EvidenceRequirement,
    EvidenceRole,
    RecordDomain,
    RecordEnvelope,
    SourceCoverageGap,
    SourceManifest,
    build_context_pack,
    build_evidence_set,
    build_raw_capture,
    verify_evidence_set,
)
from data_core.ingestion import FetchedPayload  # noqa: E402


AS_OF = "2026-07-22T10:00:00Z"


def sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def candidate(
    evidence_id: str,
    *,
    component: str = "filings",
    role: EvidenceRole = EvidenceRole.PRIMARY,
    authority_tier: str | None = None,
    independent: bool | None = None,
    status: str = "accepted",
    known_at: str = "2026-07-21T10:00:00Z",
    effective_at: str = "2026-07-20T10:00:00Z",
    quality_flags: tuple[str, ...] = (),
) -> EvidenceCandidate:
    tier = authority_tier or (
        "supplementary_only" if role in {EvidenceRole.INDEPENDENT, EvidenceRole.LEAD} else "official"
    )
    is_independent = independent if independent is not None else role is EvidenceRole.INDEPENDENT
    return EvidenceCandidate(
        evidence_id=evidence_id,
        ticker="300750.SZ",
        component=component,
        role=role,
        source_key=f"source_{evidence_id}",
        source_family=f"family_{evidence_id}",
        authority_tier=tier,
        independent_of_subject=is_independent,
        status=status,
        known_at=known_at,
        effective_at=effective_at,
        manifest_hash=sha("manifest:" + evidence_id),
        raw_hash=sha("raw:" + evidence_id),
        record_hash=sha("record:" + evidence_id),
        quality_flags=quality_flags,
    )


def policy(*requirements: EvidenceRequirement) -> EvidenceGatePolicy:
    return EvidenceGatePolicy(as_of=AS_OF, requirements=tuple(requirements))


def test_record_and_source_manifest_bind_into_candidate() -> None:
    manifest = SourceManifest(
        source_key="cninfo_filing",
        domain_scope="document",
        authority_tier="official",
        provider_version="2026-07-22",
        schema_version="cninfo-document-v1",
        license_status="configured_internal_use",
        source_url="https://www.cninfo.com.cn/",
    )
    raw = build_raw_capture(
        FetchedPayload(
            body=b"%PDF-fixture",
            source_url="https://static.cninfo.com.cn/report.pdf",
            fetched_at="2026-07-21T10:00:00Z",
            known_at="2026-07-21T10:00:00Z",
            mime_type="application/pdf",
        )
    )
    record = RecordEnvelope.accepted(
        domain=RecordDomain.DOCUMENT,
        entity_key="CN:300750.SZ:filing:1",
        payload={
            "document_id": "filing-1",
            "instrument_id": "CN:300750.SZ",
            "document_type": "quarterly_report",
            "published_at": "2026-07-20T10:00:00Z",
            "content_hash": raw.raw_hash,
            "storage_uri": raw.storage_uri,
        },
        manifest=manifest,
        raw=raw,
    )

    item = EvidenceCandidate.from_record(
        record,
        manifest,
        ticker="300750.SZ",
        component="filings",
        role=EvidenceRole.PRIMARY,
        source_family="cninfo",
        effective_at="2026-07-20T10:00:00Z",
    )

    assert item.manifest_hash == manifest.manifest_hash
    assert item.raw_hash == raw.raw_hash
    assert item.record_hash == record.record_hash
    assert item.role_violation() is None


def test_primary_independent_and_lead_roles_are_machine_validated() -> None:
    items = (
        candidate("primary_spoof", authority_tier="supplementary_only"),
        candidate("independent_spoof", role=EvidenceRole.INDEPENDENT, independent=False),
        candidate("lead", role=EvidenceRole.LEAD),
        candidate("primary_valid"),
        candidate("independent_valid", role=EvidenceRole.INDEPENDENT),
    )
    result = build_evidence_set(
        ticker="300750.SZ",
        candidates=items,
        policy=policy(EvidenceRequirement("filings", min_primary=1, min_independent=1, min_total=2)),
    )

    assert result.publishable is True
    assert result.receipt.accepted_ids == ("independent_valid", "primary_valid")
    reasons = {item.evidence_id: item.reason for item in result.receipt.rejected}
    assert reasons["primary_spoof"].startswith("role_violation")
    assert reasons["independent_spoof"].startswith("role_violation")
    assert reasons["lead"] == "lead_only_not_evidence"


def test_evidence_set_identity_is_immutable_and_deterministically_recomputable() -> None:
    items = (
        candidate("official"),
        candidate("crosscheck", role=EvidenceRole.INDEPENDENT),
    )
    gate_policy = policy(EvidenceRequirement("filings", min_primary=1, min_independent=1, min_total=2))
    first = build_evidence_set(ticker="300750.SZ", candidates=reversed(items), policy=gate_policy)
    second = build_evidence_set(ticker="300750.SZ", candidates=items, policy=gate_policy)

    assert first == second
    assert verify_evidence_set(first, candidates=items, policy=gate_policy) is True
    assert first.evidence_set_id == "evidence_set_" + first.manifest_hash[:40]
    with pytest.raises(FrozenInstanceError):
        first.ticker = "600519.SH"  # type: ignore[misc]


def test_known_at_freshness_and_quality_gates_are_recomputable() -> None:
    items = (
        candidate("fresh"),
        candidate("future", known_at="2026-07-23T10:00:00Z"),
        candidate("stale", effective_at="2025-01-01T00:00:00Z"),
        candidate("fixture", quality_flags=("fixture",)),
        candidate("rejected", status="rejected"),
    )
    gate_policy = policy(EvidenceRequirement("filings", min_primary=1, min_total=1))
    result = build_evidence_set(ticker="300750.SZ", candidates=items, policy=gate_policy)

    assert result.publishable is True
    assert result.receipt.accepted_ids == ("fresh",)
    reasons = {item.evidence_id: item.reason for item in result.receipt.rejected}
    assert reasons == {
        "fixture": "blocking_quality_flag",
        "future": "known_at_after_as_of",
        "rejected": "record_status:rejected",
        "stale": "stale>180d",
    }
    assert verify_evidence_set(result, candidates=items, policy=gate_policy) is True


def test_blocking_conflict_prevents_context_pack_even_when_coverage_is_complete() -> None:
    items = (
        candidate("official"),
        candidate("crosscheck", role=EvidenceRole.INDEPENDENT),
    )
    conflict = EvidenceConflict(
        conflict_id="conflict_price",
        component="filings",
        severity="blocking",
        evidence_ids=("official", "crosscheck"),
        reason="reported values disagree beyond policy tolerance",
    )
    result = build_evidence_set(
        ticker="300750.SZ",
        candidates=items,
        policy=policy(EvidenceRequirement("filings", min_primary=1, min_independent=1, min_total=2)),
        conflicts=(conflict,),
    )

    assert result.publishable is False
    assert result.receipt.blocking_conflict_ids == ("conflict_price",)
    with pytest.raises(ValueError, match="coverage and conflict"):
        build_context_pack(result)


def test_coverage_report_names_missing_roles_and_required_source_gaps() -> None:
    result = build_evidence_set(
        ticker="300750.SZ",
        candidates=(candidate("official"),),
        policy=policy(
            EvidenceRequirement("filings", min_primary=1, min_independent=1, min_total=2),
            EvidenceRequirement("consensus", min_total=1),
        ),
        source_gaps=(
            SourceCoverageGap("ths_forecast", "consensus", "upstream unavailable", required=True),
            SourceCoverageGap("google_news", "events", "optional source timed out"),
        ),
    )

    assert result.publishable is False
    assert result.receipt.coverage.missing == (
        "filings:independent<1",
        "filings:total<2",
        "consensus:total<1",
        "consensus:source:ths_forecast:upstream unavailable",
        "events:source:google_news:optional source timed out",
    )


def test_context_pack_contains_only_gate_accepted_evidence() -> None:
    items = (
        candidate("market", component="market", authority_tier="canonical"),
        candidate("filing", component="filings"),
        candidate("sell_side", component="sell_side", role=EvidenceRole.INDEPENDENT),
        candidate("consensus", component="consensus", role=EvidenceRole.INDEPENDENT),
        candidate("news", component="events", role=EvidenceRole.INDEPENDENT),
        candidate("uzi_lead", component="events", role=EvidenceRole.LEAD),
        candidate("bad_news", component="events", role=EvidenceRole.INDEPENDENT, status="rejected"),
    )
    gate_policy = policy(
        EvidenceRequirement("market", min_primary=1, min_total=1),
        EvidenceRequirement("filings", min_primary=1, min_total=1),
        EvidenceRequirement("sell_side", min_independent=1, min_total=1),
        EvidenceRequirement("consensus", min_independent=1, min_total=1),
        EvidenceRequirement("events", min_independent=1, min_total=1),
    )
    evidence_set = build_evidence_set(ticker="300750.SZ", candidates=items, policy=gate_policy)
    context = build_context_pack(evidence_set)

    assert evidence_set.publishable is True
    assert {item.evidence_id for item in context.evidence} == {
        "market", "filing", "sell_side", "consensus", "news"
    }
    assert "uzi_lead" not in context.index
    assert "bad_news" not in context.index
    with pytest.raises(TypeError):
        context.index["injected"] = candidate("injected")  # type: ignore[index]
