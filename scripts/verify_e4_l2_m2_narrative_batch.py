#!/usr/bin/env python3
"""Fail-closed verification summary for the L2-M2 official narrative run."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping


def _load(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def build_summary(receipt: Mapping[str, Any]) -> dict[str, Any]:
    boundary = receipt.get("truth_boundary") or {}
    rows = receipt.get("rows") or []
    cohort = receipt.get("cohort") or []
    blocks = receipt.get("blocks") or []
    if receipt.get("schema_version") != "e4-l2-narrative-batch-v1" or receipt.get("data_kind") != "real":
        raise ValueError("narrative input must be a real L2-M2 receipt")
    supplied_hash = str(receipt.get("receipt_hash") or "")
    hashed = {key: value for key, value in receipt.items() if key != "receipt_hash"}
    observed_hash = hashlib.sha256(json.dumps(hashed, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    if not supplied_hash or supplied_hash != observed_hash:
        raise ValueError("narrative receipt hash mismatch")
    if len(rows) != 100 or len(cohort) != 100 or {row.get("ticker") for row in rows} != set(cohort):
        raise ValueError("L2-M2 requires the complete 100-ticker cohort")
    if receipt.get("configured_max_concurrency") != 1 or receipt.get("sequential") is not True:
        raise ValueError("L2-M2 must remain sequential with concurrency one")
    if boundary.get("official_cninfo_pdf_only") is not True or boundary.get("page_bound_only") is not True:
        raise ValueError("narrative receipt must retain official page-bound provenance")
    available = [row for row in rows if row.get("status") == "available"]
    documents = {
        str(row.get("document", {}).get("document_id")): row.get("document", {})
        for row in available
    }
    for block in blocks:
        document = documents.get(str(block.get("document_id")))
        if not document or block.get("raw_hash") != document.get("raw_hash"):
            raise ValueError("narrative block document identity does not match an available official row")
        if not isinstance(block.get("page_number"), int) or block["page_number"] < 1 or not block.get("text"):
            raise ValueError("narrative block is missing a page-bound source text anchor")
    missing = Counter(str(row.get("reason") or "unknown") for row in rows if row.get("status") == "missing")
    return {
        "schema_version": "e4-l2-m2-narrative-batch-verification-v1",
        "data_kind": "real",
        "narrative_receipt_hash": receipt.get("receipt_hash"),
        "financial_sequence_sha256": receipt.get("financial_sequence_sha256"),
        "coverage": {
            "requested_tickers": len(cohort),
            "available_tickers": len(available),
            "missing_tickers": len(rows) - len(available),
            "annual_selections": sum(row.get("selection_basis") == "latest_available_annual" for row in rows),
            "interim_fallback_selections": sum(row.get("selection_basis") == "latest_available_interim_fallback" for row in rows),
            "page_bound_blocks": len(blocks),
            "resolved_blocks": sum(block.get("status") == "resolved" for block in blocks),
            "unresolved_blocks": sum(block.get("status") != "resolved" for block in blocks),
            "resolved_pages": len({(block.get("document_id"), block.get("page_number")) for block in blocks if block.get("status") == "resolved"}),
        },
        "missing_reason_counts": dict(sorted(missing.items())),
        "truth_boundary": {
            "official_cninfo_pdf_only": True,
            "page_bound_only": True,
            "financial_receipt_is_selection_lineage_only": True,
            "does_not_promote_tier_or_action": True,
            "missing_is_retained_not_filled": True,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--narrative-receipt", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    output = build_summary(_load(args.narrative_receipt))
    output["verification_hash"] = hashlib.sha256(
        json.dumps(output, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(args.out)


if __name__ == "__main__":
    main()
