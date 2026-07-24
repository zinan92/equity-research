"""Historic, evidence-bound three-company vertical-slice receipts.

This module is deliberately small: it proves that the same E1--E3 contracts
can consume three real official disclosures without turning the disclosures
into a claim of complete current research coverage.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

from .company_positions import CompanyPosition
from .contracts import RecordDomain, SourceManifest
from .decision_policy import DecisionInput, DecisionReceipt, decide
from .dossier_generator import CompanyDossier, compile_dossier
from .evidence_gate import (
    EvidenceCandidate,
    EvidenceGatePolicy,
    EvidenceRequirement,
    EvidenceRole,
    ResearchContextPack,
    SourceCoverageGap,
    build_context_pack,
    build_evidence_set,
)
from .industry_catalysts import (
    CATALYST_PROFILE_SCHEMA_VERSION,
    SECTION_NAMES,
    CatalystSection,
    IndustryCatalystProfile,
)
from .offline_report_model import OfflineReportModel, compile_offline_report_model
from .sector_taxonomy import validate_position_segment


VERTICAL_SLICE_SCHEMA_VERSION = "park-vertical-slice-v1"
VERTICAL_SLICE_AS_OF = "2025-05-01T00:00:00Z"


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


@dataclass(frozen=True)
class OfficialEvidenceAnchor:
    ticker: str
    name: str
    exchange: str
    segment_id: str
    role: str
    product_keyword: str
    document_url: str
    document_title: str
    published_at: str
    page: int
    raw_hash: str
    source_key: str
    source_root: str
    source_family: str

    def validate(self) -> None:
        if len(self.raw_hash) != 64 or any(char not in "0123456789abcdef" for char in self.raw_hash):
            raise ValueError("vertical evidence raw hash must be SHA-256")
        if self.page < 1 or not self.document_url.startswith("https://"):
            raise ValueError("vertical evidence requires an HTTPS URL and one-based page")
        validate_position_segment(self.segment_id)

    @property
    def manifest(self) -> SourceManifest:
        return SourceManifest(
            source_key=self.source_key,
            domain_scope=RecordDomain.DOCUMENT.value,
            authority_tier="official",
            provider_version="2026-07-24",
            schema_version="official-filing-vertical-slice-v1",
            license_status="public_disclosure_internal_use",
            source_url=self.source_root,
        )


# Each row was captured from a public issuer/exchange disclosure in the 2025-07-24
# vertical-slice run. Raw PDFs stay outside Git; the immutable URL/page/SHA identity
# is enough to re-fetch and verify the cited claim without copying report prose.
OFFICIAL_EVIDENCE_ANCHORS: tuple[OfficialEvidenceAnchor, ...] = (
    OfficialEvidenceAnchor(
        "300750.SZ", "宁德时代", "SZSE", "cross-sector/battery", "battery-system supplier", "电池",
        "https://static.cninfo.com.cn/finalpage/2025-03-15/1222806982.PDF", "宁德时代：2024年年度报告",
        "2025-03-15T00:00:00Z", 2,
        "b4f1713d7b821eb076c102711d177fe942ccc2bc8dd171ae5d7a95799a65b0ad",
        "cninfo_official_filing_document_v1", "https://static.cninfo.com.cn/", "issuer",
    ),
    OfficialEvidenceAnchor(
        "600519.SH", "贵州茅台", "SSE", "cross-sector/consumer", "branded-baijiu producer", "茅台酒",
        "https://static.cninfo.com.cn/finalpage/2025-04-03/1222993912.PDF", "贵州茅台：2024年年度报告",
        "2025-04-03T00:00:00Z", 5,
        "8ad3773fb3fd27fa49b2393982c90d8a47b9cff65f167a5cef1b11eeb968fb7d",
        "cninfo_official_filing_document_v1", "https://static.cninfo.com.cn/", "issuer",
    ),
    OfficialEvidenceAnchor(
        "600036.SH", "招商银行", "SSE", "cross-sector/bank", "national-commercial bank", "商业银行",
        "https://s3gw.cmbimg.com/lb5001-cmbweb-prd-1255000097/cmbir/20250325/e86337ff-2172-46c2-8174-411903fd7020.pdf",
        "招商银行股份有限公司2024年度报告摘要", "2025-03-25T00:00:00Z", 11,
        "3db21481f342cf986eabc4987b3da147a99bd2bc6b01f70653d20be7544c00c1",
        "cmb_company_ir_filing_document_v1", "https://s3gw.cmbimg.com/", "issuer",
    ),
)


def official_evidence_anchors() -> tuple[OfficialEvidenceAnchor, ...]:
    for anchor in OFFICIAL_EVIDENCE_ANCHORS:
        anchor.validate()
    return OFFICIAL_EVIDENCE_ANCHORS


def _missing_profile(segment_id: str) -> IndustryCatalystProfile:
    sections = tuple(
        CatalystSection(name, "missing_evidence", "No accepted current evidence is available for this section.")
        for name in SECTION_NAMES
    )
    input_hash = _hash({"schema_version": CATALYST_PROFILE_SCHEMA_VERSION, "segment_id": segment_id, "as_of": VERTICAL_SLICE_AS_OF[:10], "sections": [asdict(item) for item in sections]})
    profile = IndustryCatalystProfile(
        "catalyst_" + input_hash[:40], segment_id, VERTICAL_SLICE_AS_OF[:10], sections, input_hash
    )
    profile.validate()
    return profile


def _context(anchor: OfficialEvidenceAnchor) -> ResearchContextPack:
    candidate = EvidenceCandidate(
        evidence_id="official-filing:" + anchor.raw_hash[:40], ticker=anchor.ticker,
        component="filings", role=EvidenceRole.PRIMARY, source_key=anchor.source_key,
        source_family=anchor.source_family, authority_tier="official", independent_of_subject=False,
        status="accepted", known_at=anchor.published_at, effective_at=anchor.published_at,
        manifest_hash=anchor.manifest.manifest_hash, raw_hash=anchor.raw_hash,
        record_hash=_hash({"anchor": asdict(anchor)}),
    )
    policy = EvidenceGatePolicy(
        as_of=VERTICAL_SLICE_AS_OF, requirements=(EvidenceRequirement("filings", min_primary=1),)
    )
    evidence_set = build_evidence_set(
        ticker=anchor.ticker, candidates=(candidate,), policy=policy,
        source_gaps=(
            SourceCoverageGap("market-authority", "market", "not captured in this historic filing slice", required=False),
            SourceCoverageGap("valuation-authority", "valuation", "not captured in this historic filing slice", required=False),
            SourceCoverageGap("sell-side-authority", "sell_side", "not captured in this historic filing slice", required=False),
        ),
    )
    return build_context_pack(evidence_set)


@dataclass(frozen=True)
class VerticalSliceReceipt:
    ticker: str
    anchor: OfficialEvidenceAnchor
    context_manifest_hash: str
    dossier: CompanyDossier
    decision: DecisionReceipt
    report: OfflineReportModel
    gaps: tuple[str, ...]
    receipt_hash: str


def compile_vertical_slice(anchor: OfficialEvidenceAnchor) -> VerticalSliceReceipt:
    anchor.validate()
    context = _context(anchor)
    position = CompanyPosition(
        anchor.ticker, anchor.name, "A", anchor.segment_id, anchor.role, anchor.product_keyword,
        "accepted", (anchor.document_url, anchor.page, anchor.raw_hash),
    )
    dossier = compile_dossier(context, position, _missing_profile(anchor.segment_id))
    decision = decide(DecisionInput(
        ticker=anchor.ticker, context_manifest_hash=context.manifest_hash, dossier_id=dossier.dossier_id,
        current_price=None, target_price=None, quality_score=None, risk_score=None, liquidity_score=None,
        coverage_passed=False, sector_exposure=0.0, current_position=0.0, cash_weight=1.0,
    ))
    report = compile_offline_report_model(
        dossier, decision, name=anchor.name, exchange=anchor.exchange
    )
    gaps = ("market_price", "valuation", "quality_risk_liquidity", "sell_side", "catalyst_profile")
    material = {
        "schema_version": VERTICAL_SLICE_SCHEMA_VERSION, "ticker": anchor.ticker,
        "anchor": asdict(anchor), "context_manifest_hash": context.manifest_hash,
        "dossier_id": dossier.dossier_id, "decision_receipt_hash": decision.receipt_hash,
        "report_export_hash": report.export_hash, "gaps": gaps,
    }
    return VerticalSliceReceipt(
        anchor.ticker, anchor, context.manifest_hash, dossier, decision, report, gaps, _hash(material)
    )


def compile_three_company_vertical_slices() -> tuple[VerticalSliceReceipt, ...]:
    return tuple(compile_vertical_slice(anchor) for anchor in official_evidence_anchors())


def vertical_slice_audit() -> dict[str, object]:
    rows = compile_three_company_vertical_slices()
    return {
        "schema_version": VERTICAL_SLICE_SCHEMA_VERSION,
        "status": "partial_evidence_bound",
        "companies": [
            {
                "ticker": row.ticker, "position_citation": {
                    "url": row.anchor.document_url, "page": row.anchor.page, "raw_hash": row.anchor.raw_hash,
                },
                "context_manifest_hash": row.context_manifest_hash,
                "dossier_id": row.dossier.dossier_id,
                "decision_action": row.decision.action,
                "decision_reasons": row.decision.reasons,
                "report_export_hash": row.report.export_hash,
                "gaps": row.gaps,
                "receipt_hash": row.receipt_hash,
            }
            for row in rows
        ],
        "shared_schema": len({row.dossier.schema_version for row in rows}) == 1,
        "fixture_facts_used": False,
    }
