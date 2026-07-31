#!/usr/bin/env python3
"""Verify and receipt the accepted Round 7 north star and safety boundary."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product"))

from data_core.research_degradation import _BLOCKED_FIELDS, _TIER_ALLOWED  # noqa: E402
from data_core.round7_north_star import (  # noqa: E402
    ROUND7_BLIND_TICKERS,
    ROUND7_BLIND_PACK_SHA256,
    ROUND7_BLIND_SAMPLE_SHA256,
    ROUND7_CANONICAL_DOSSIER_SHA256,
    ROUND7_EXTERNAL_RECEIPT_SHA256,
    ROUND7_LEGACY_BLIND_STRUCTURE_SIGNATURE,
    ROUND7_NORTH_STAR_VERSION,
    ROUND7_PARK_RECEIPT_SHA256,
    ROUND7_QUALITY_GATES,
    ROUND7_READER_UNITS,
    ROUND7_REPLAY_SHA256,
    ROUND7_STRUCTURE_SIGNATURE,
    ROUND7_TEMPLATE_SHA256,
    SAFETY_SOURCE_SHA256,
    structure_signature,
    verify_round7_document,
)


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    dossier_root = ROOT / "docs" / "dossier-production"
    manifest = json.loads(
        (dossier_root / "pilot-production-manifest.json").read_text(
            encoding="utf-8"
        )
    )
    runs = {str(row["ticker"]): row for row in manifest["runs"]}
    paths = tuple(
        dossier_root / str(runs[ticker]["path"])
        for ticker in ROUND7_BLIND_TICKERS
    )
    observed_sample_hashes = {
        ticker: file_sha(path)
        for ticker, path in zip(ROUND7_BLIND_TICKERS, paths)
    }
    if observed_sample_hashes != ROUND7_BLIND_SAMPLE_SHA256:
        raise ValueError("Round 7 approved reference sample body changed")
    canonical_path = dossier_root / "samples" / "300750.SZ-v1.md"
    canonical = verify_round7_document(canonical_path)
    if (
        file_sha(canonical_path) != ROUND7_CANONICAL_DOSSIER_SHA256
        or canonical.problems
    ):
        raise ValueError("exact Round 7 canonical dossier changed")
    template_path = dossier_root / "template-v1.md"
    if file_sha(template_path) != ROUND7_TEMPLATE_SHA256:
        raise ValueError("Round 7 legacy reusable template changed")
    replay_path = dossier_root / "reruns" / "nvda-v1-replay.md"
    replay_receipt = json.loads(
        (dossier_root / "reruns" / "nvda-v1-replay-receipt.json").read_text(
            encoding="utf-8"
        )
    )
    if (
        file_sha(replay_path) != ROUND7_REPLAY_SHA256
        or replay_receipt.get("source_sha256")
        != ROUND7_BLIND_SAMPLE_SHA256["NVDA"]
        or replay_receipt.get("output_sha256") != ROUND7_REPLAY_SHA256
        or replay_receipt.get("structure_match") is not True
        or replay_receipt.get("source_structure_signature")
        != ROUND7_LEGACY_BLIND_STRUCTURE_SIGNATURE
        or replay_receipt.get("output_structure_signature")
        != ROUND7_LEGACY_BLIND_STRUCTURE_SIGNATURE
    ):
        raise ValueError("NVDA replay receipt does not prove structure match")
    park_approval = json.loads(
        (dossier_root / "round7-park-approval-receipt.json").read_text(
            encoding="utf-8"
        )
    )
    external = json.loads(
        (dossier_root / "round7-external-preference-receipt.json").read_text(
            encoding="utf-8"
        )
    )
    external_path = dossier_root / "round7-external-preference-receipt.json"
    park_path = dossier_root / "round7-park-approval-receipt.json"
    if (
        file_sha(external_path) != ROUND7_EXTERNAL_RECEIPT_SHA256
        or file_sha(park_path) != ROUND7_PARK_RECEIPT_SHA256
        or external.get("schema_version")
        != "dossier-external-preference-receipt-v1"
        or park_approval.get("schema_version")
        != "dossier-park-approval-receipt-v1"
        or external.get("runtime_evidence", {}).get("blind_pack_sha256")
        != ROUND7_BLIND_PACK_SHA256
        or park_approval.get("runtime_evidence", {}).get("blind_pack_sha256")
        != ROUND7_BLIND_PACK_SHA256
        or tuple(external.get("runtime_evidence", {}).get("blind_set") or ())
        != ROUND7_BLIND_TICKERS
        or tuple(park_approval.get("runtime_evidence", {}).get("blind_set") or ())
        != ROUND7_BLIND_TICKERS
        or park_approval.get("approval", {}).get("approved") is not True
        or park_approval.get("approval", {}).get("round") != 7
        or park_approval.get("approval", {}).get("scope")
        != "Round 7 dossier structure and reader-facing version"
        or park_approval.get("gate", {}).get("passed") is not True
        or external.get("result", {}).get("self_wins") != 5
        or external.get("result", {}).get("external_reader_passed") is not True
    ):
        raise ValueError("Round 7 approval evidence is incomplete")

    legacy_samples = []
    for ticker in manifest.get("additional_product_samples") or ():
        path = dossier_root / str(runs[str(ticker)]["path"])
        check = verify_round7_document(path)
        legacy_samples.append(
            {
                "ticker": ticker,
                "path": str(path.relative_to(ROOT)),
                "classification": "legacy_product_sample",
                "problems": list(check.problems),
            }
        )
    safety_files = (
        ROOT / "product" / "data_core" / "research_degradation.py",
        ROOT / "product" / "data_core" / "evidence_gate.py",
        ROOT / "product" / "data_core" / "decision_policy.py",
    )
    observed_safety_hashes = {
        str(path.relative_to(ROOT)): file_sha(path) for path in safety_files
    }
    if observed_safety_hashes != SAFETY_SOURCE_SHA256:
        raise ValueError("frozen B6/Tier/decision-policy safety source changed")
    expected_tier_allowed = {
        "A": [
            "status",
            "summary",
            "report",
            "evidence",
            "action",
            "target_price",
            "position_range",
            "next_steps",
        ],
        "B": ["status", "summary", "partial_report", "evidence", "next_steps"],
        "C": ["status", "coverage", "evidence", "next_steps"],
        "missing": ["status", "next_steps"],
    }
    observed_tier_allowed = {
        tier.value: list(fields) for tier, fields in _TIER_ALLOWED.items()
    }
    if (
        observed_tier_allowed != expected_tier_allowed
        or tuple(_BLOCKED_FIELDS)
        != ("action", "target_price", "position_range")
    ):
        raise ValueError("frozen Tier or blocked-field semantics changed")
    output = {
        "schema_version": "round7-north-star-baseline-v1",
        "north_star_version": ROUND7_NORTH_STAR_VERSION,
        "status": "passed",
        "reader_units": list(ROUND7_READER_UNITS),
        "structure_signature": ROUND7_STRUCTURE_SIGNATURE,
        "quality_contract": ROUND7_QUALITY_GATES,
        "canonical_dossier": {
            "path": str(canonical_path.relative_to(ROOT)),
            "sha256": ROUND7_CANONICAL_DOSSIER_SHA256,
            "body_characters": canonical.body_characters,
            "source_rows": canonical.source_rows,
            "fact_ids": canonical.fact_ids,
        },
        "template": {
            "path": str(template_path.relative_to(ROOT)),
            "sha256": ROUND7_TEMPLATE_SHA256,
            "classification": "legacy_reusable_template",
        },
        "blind_set": [
            {
                "ticker": ticker,
                "path": str(path.relative_to(ROOT)),
                "sha256": ROUND7_BLIND_SAMPLE_SHA256[ticker],
                "classification": "approved_reference_pre_canonical_taxonomy",
            }
            for ticker, path in zip(ROUND7_BLIND_TICKERS, paths)
        ],
        "replay": {
            "path": str(replay_path.relative_to(ROOT)),
            "sha256": ROUND7_REPLAY_SHA256,
            "structure_match": True,
            "structure_signature": ROUND7_LEGACY_BLIND_STRUCTURE_SIGNATURE,
            "classification": "repeatability_evidence_pre_canonical_taxonomy",
        },
        "approval_evidence": {
            "external_self_wins": 5,
            "park_approved": True,
            "blind_pack_sha256": ROUND7_BLIND_PACK_SHA256,
            "external_receipt_sha256": ROUND7_EXTERNAL_RECEIPT_SHA256,
            "park_receipt_sha256": ROUND7_PARK_RECEIPT_SHA256,
        },
        "legacy_product_samples": legacy_samples,
        "safety_boundary": {
            "tier_allowed": observed_tier_allowed,
            "blocked_fields": list(_BLOCKED_FIELDS),
            "source_hashes": observed_safety_hashes,
            "invariants": [
                "B6 publishable evidence is required before section completeness",
                "all canonical sections must be FULL for Tier A",
                "non-A tiers block action, target_price and position_range",
                "unreviewed AI judgment cannot make a section FULL",
            ],
        },
    }
    payload = json.dumps(
        output,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    output["receipt_hash"] = hashlib.sha256(payload).hexdigest()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": output["status"],
                "out": str(args.out),
                "blind_samples": len(output["blind_set"]),
                "reader_units": len(output["reader_units"]),
                "receipt_hash": output["receipt_hash"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
