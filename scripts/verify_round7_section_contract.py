#!/usr/bin/env python3
"""Verify and receipt the Round 7 C1 contract and frozen safety semantics."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product"))

from data_core.evidence_gate import (  # noqa: E402
    EvidenceCandidate,
    EvidenceGatePolicy,
    EvidenceRequirement,
    EvidenceRole,
    build_evidence_set,
)
from data_core.research_degradation import assess_any_ticker  # noqa: E402
from data_core.round7_north_star import (  # noqa: E402
    ROUND7_READER_UNITS,
    SAFETY_SOURCE_SHA256,
)
from report_contract import (  # noqa: E402
    RESEARCH_SECTION_SPECS_V3,
    ReportContractError,
    build_research_section_contract_v3,
)


MIGRATED_CONSUMERS = (
    "product/report_contract.py",
    "product/data_core/e4_vertical_degradation.py",
    "product/data_core/e4_r2_industry_wiring.py",
    "product/data_core/e4_judgment_wiring.py",
    "product/data_core/e4_judgment_review_queue.py",
    "scripts/run_e4_m2_research_wiring.py",
    "scripts/build_e4_l1_m5_reassessment.py",
    "scripts/inventory_e4_section_completion.py",
    "scripts/compile_e4_m4_report.py",
    "scripts/verify_e4_wired_reports.py",
    "product/data_core/research_degradation.py",
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _value(value_type: str, *, chapter: bool = False) -> object:
    if chapter:
        return {
            "status": "human_reviewed_judgment",
            "review_status": "approved",
            "text": "reviewed complete chapter",
            "evidence_bindings": [
                {
                    "document_id": "official:filing",
                    "page_number": 1,
                    "quoted_anchor": "official filing text",
                }
            ],
        }
    return {
        "object": {"verified": True},
        "array": [{"verified": True}],
        "string": "verified",
        "number": 1.0,
        "boolean": True,
    }[value_type]


def _full_inputs() -> dict[str, dict[str, object]]:
    return {
        spec.section_id: {
            item.key: _value(
                item.value_type,
                chapter=item.key == "chapter_draft",
            )
            for item in spec.required_inputs
        }
        for spec in RESEARCH_SECTION_SPECS_V3
    }


def _evidence_set():
    candidate = EvidenceCandidate(
        evidence_id="official-filing",
        ticker="300750.SZ",
        component="filings",
        role=EvidenceRole.PRIMARY,
        source_key="cninfo",
        source_family="official-regulatory",
        authority_tier="official",
        independent_of_subject=False,
        status="accepted",
        known_at="2026-07-30T00:00:00Z",
        effective_at="2026-07-30T00:00:00Z",
        manifest_hash="a" * 64,
        raw_hash="b" * 64,
        record_hash="c" * 64,
    )
    return build_evidence_set(
        ticker="300750.SZ",
        candidates=(candidate,),
        policy=EvidenceGatePolicy(
            as_of="2026-07-30T00:00:00Z",
            requirements=(EvidenceRequirement("filings", min_primary=1),),
        ),
    )


def verify() -> dict[str, object]:
    section_ids = tuple(item.section_id for item in RESEARCH_SECTION_SPECS_V3)
    if section_ids != ROUND7_READER_UNITS:
        raise ValueError("C1 section order diverges from the Round 7 north star")
    empty = build_research_section_contract_v3({})
    if empty.target_body_characters != (4_200, 5_500):
        raise ValueError("Round 7 character target changed")
    try:
        build_research_section_contract_v3({"investment_thesis": {}})
    except ReportContractError:
        old_section_rejected = True
    else:
        raise ValueError("retired 18-section identifier was accepted")

    evidence_set = _evidence_set()
    reviewed = build_research_section_contract_v3(
        _full_inputs(),
        structure_only=False,
        evidence_set=evidence_set,
    )
    reviewed_tier = assess_any_ticker(
        "300750.SZ",
        evidence_set=evidence_set,
        section_contract=reviewed,
        data_kind="real",
    )
    if reviewed_tier.tier.value != "A" or reviewed_tier.blocked_fields:
        raise ValueError("reviewed all-FULL path no longer reaches the unchanged Tier A")

    unreviewed_inputs = _full_inputs()
    unreviewed_inputs["one_line_positioning"]["chapter_draft"] = {
        "status": "ai_generated_judgment_unreviewed",
        "text": "draft",
        "evidence_bindings": [
            {
                "document_id": "official:filing",
                "page_number": 1,
                "quoted_anchor": "official filing text",
            }
        ],
    }
    unreviewed = build_research_section_contract_v3(
        unreviewed_inputs,
        structure_only=False,
        evidence_set=evidence_set,
    )
    unreviewed_tier = assess_any_ticker(
        "300750.SZ",
        evidence_set=evidence_set,
        section_contract=unreviewed,
        data_kind="real",
    )
    first = unreviewed.sections[0]
    if (
        first.status.value != "partial"
        or first.status_reason != "pending_judgment_review"
        or unreviewed_tier.tier.value != "B"
        or tuple(unreviewed_tier.blocked_fields)
        != ("action", "target_price", "position_range")
    ):
        raise ValueError("unreviewed chapter bypassed the Tier safety boundary")

    observed_hashes = {
        relative: _sha(ROOT / relative)
        for relative in SAFETY_SOURCE_SHA256
    }
    if observed_hashes != SAFETY_SOURCE_SHA256:
        raise ValueError("Tier, B6, or decision-policy source changed")

    output: dict[str, object] = {
        "schema_version": "round7-section-contract-verification-v1",
        "status": "passed",
        "section_contract": {
            "schema_version": reviewed.schema_version,
            "contract_version": reviewed.contract_version,
            "contract_hash": reviewed.contract_hash,
            "profile_id": reviewed.profile_id,
            "profile_hash": reviewed.profile_hash,
            "section_ids": list(section_ids),
            "target_body_characters": list(reviewed.target_body_characters),
            "required_inputs": {
                spec.section_id: [item.key for item in spec.required_inputs]
                for spec in RESEARCH_SECTION_SPECS_V3
            },
        },
        "checks": {
            "old_section_rejected": old_section_rejected,
            "reviewed_all_full_tier": reviewed_tier.tier.value,
            "reviewed_allowed_fields": list(reviewed_tier.allowed_fields),
            "unreviewed_section": asdict(first),
            "unreviewed_tier": unreviewed_tier.tier.value,
            "unreviewed_blocked_fields": list(unreviewed_tier.blocked_fields),
            "safety_source_hashes": observed_hashes,
        },
        "migrated_consumers": list(MIGRATED_CONSUMERS),
        "publication_appendices": ["production_record", "sources"],
        "publication_appendices_count_toward_tier": False,
    }
    output["receipt_hash"] = hashlib.sha256(
        json.dumps(
            output,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    output = verify()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
