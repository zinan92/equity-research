#!/usr/bin/env python3
"""Verify L1-M6 human-review material without granting any review outcome."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


def _load(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def _documents_by_ticker(sequence: Mapping[str, Any]) -> dict[str, set[tuple[str, str]]]:
    result: dict[str, set[tuple[str, str]]] = {}
    for ticker_row in sequence.get("tickers", []):
        ticker = str(ticker_row.get("ticker") or "").upper()
        documents = result.setdefault(ticker, set())
        for report in ticker_row.get("reports", []):
            document = report.get("document") or {}
            document_id, raw_hash = document.get("document_id"), document.get("raw_hash")
            if document_id and raw_hash:
                documents.add((str(document_id), str(raw_hash)))
    return result


def build_verification(
    queue: Mapping[str, Any], legacy: Mapping[str, Any], current: Mapping[str, Any], sequence: Mapping[str, Any],
) -> dict[str, Any]:
    items = queue.get("items") or []
    if queue.get("data_kind") != "real" or not items:
        raise ValueError("judgment queue must contain real pending items")
    if any(item.get("review_status") != "pending_human_review" for item in items):
        raise ValueError("review preparation must not contain an approval")
    if any(not citation.get("pdf_page_url", "").endswith(f"#page={citation.get('page_number')}") for item in items for citation in item.get("citations", [])):
        raise ValueError("every judgment citation must link to its PDF page")
    if items != sorted(items, key=lambda row: (row["impact_rank"], row["section_id"], row["judgment_id"])):
        raise ValueError("judgment queue is not in declared impact order")

    documents = _documents_by_ticker(sequence)
    def match(assignment: Mapping[str, Any]) -> bool:
        citation = assignment.get("page_citation_check") or {}
        return (str(citation.get("document_id")), str(citation.get("raw_hash"))) in documents.get(str(assignment.get("ticker")).upper(), set())

    legacy_assignments = legacy.get("assignments") or []
    current_assignments = current.get("assignments") or []
    valid_legacy = sorted(item["ticker"] for item in legacy_assignments if match(item))
    stale_legacy = sorted(item["ticker"] for item in legacy_assignments if not match(item))
    active_current = sorted(item["ticker"] for item in current_assignments if match(item))
    invalid_current = sorted(item["ticker"] for item in current_assignments if not match(item))
    if invalid_current:
        raise ValueError(f"current audit assignments lack current sequence lineage: {invalid_current}")

    return {
        "schema_version": "e4-l1-m6-review-prep-verification-v1",
        "data_kind": "real",
        "judgment_queue": {
            "source_receipt_id": queue["source_receipt_id"],
            "pending_human_review": len(items),
            "pdf_page_links_complete": True,
            "approval_count": 0,
            "only_review_remaining_sections": sorted({item["section_id"] for item in items if item.get("would_promote_section_to_full")}),
        },
        "spot_audit_freshness": {
            "financial_sequence_receipt_hash": sequence.get("receipt_hash"),
            "legacy_assignment_count": len(legacy_assignments),
            "legacy_still_lineage_valid": valid_legacy,
            "legacy_stale_requires_recovery": stale_legacy,
            "current_assignment_count": len(current_assignments),
            "current_assignments_with_lineage": active_current,
            "coverage_gaps": current.get("coverage_gaps") or [],
            "status": "partial_current_coverage",
        },
        "truth_boundary": {
            "human_review_not_performed": True,
            "stale_legacy_assignments_not_counted": True,
            "no_tier_or_acceptance_credit": True,
            "no_issue_218_claim": True,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--legacy-assignments", type=Path, required=True)
    parser.add_argument("--current-assignments", type=Path, required=True)
    parser.add_argument("--financial-sequence", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    output = build_verification(_load(args.queue), _load(args.legacy_assignments), _load(args.current_assignments), _load(args.financial_sequence))
    output["verification_hash"] = hashlib.sha256(json.dumps(output, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(args.out)


if __name__ == "__main__":
    main()
