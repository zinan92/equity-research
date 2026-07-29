#!/usr/bin/env python3
"""Verify the real CATL narrative receipt without treating it as research prose."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from data_core.e4_catl_financial_history import CATL_REPORTS
from data_core.e4_narrative_evidence import NARRATIVE_SCHEMA


def digest(receipt: dict) -> str:
    payload = {key: value for key, value in receipt.items() if key not in {"receipt_hash", "receipt_id"}}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
    errors: list[str] = []
    if receipt.get("schema_version") != NARRATIVE_SCHEMA or receipt.get("data_kind") != "real":
        errors.append("receipt_schema_or_data_kind_invalid")
    if receipt.get("receipt_hash") != digest(receipt):
        errors.append("receipt_hash_invalid")
    expected = {report.document_id: report.source_url for report in CATL_REPORTS}
    reports = {str(row.get("document_id")): row for row in receipt.get("reports", [])}
    if set(reports) != set(expected):
        errors.append("official_document_set_mismatch")
    for document_id, source_url in expected.items():
        row = reports.get(document_id, {})
        if row.get("status") != "available" or row.get("source_url") != source_url or not row.get("raw_hash"):
            errors.append(f"official_document_unavailable:{document_id}")
    resolved = 0
    unresolved = 0
    sample: list[dict] = []
    seen_paths: set[tuple[str, str]] = set()
    for block in receipt.get("blocks", []):
        document_id = str(block.get("document_id"))
        row = reports.get(document_id, {})
        if not all(block.get(key) for key in ("document_id", "raw_hash", "page_number", "text", "source_url")):
            errors.append("block_missing_page_identity")
            continue
        if block.get("source_url") != row.get("source_url") or block.get("raw_hash") != row.get("raw_hash"):
            errors.append(f"block_source_identity_mismatch:{document_id}")
        text = str(block.get("text"))
        if text.startswith("目录") and ("……" in text or text.count("...") >= 3):
            errors.append("toc_leaked_into_narrative_block")
        if block.get("status") == "resolved":
            resolved += 1
            if not block.get("section_path"):
                errors.append("resolved_block_missing_section_path")
            key = (document_id, str(block.get("section_path")))
            if key not in seen_paths and len(sample) < 10:
                seen_paths.add(key)
                sample.append({key: block[key] for key in ("document_id", "page_number", "section_path", "source_url", "text")})
        elif block.get("status") == "unresolved":
            unresolved += 1
            if block.get("section_path") or not block.get("reason"):
                errors.append("unresolved_block_not_explicit")
        else:
            errors.append("unknown_block_status")
    if len(sample) < 10:
        errors.append("fewer_than_ten_page_level_spot_checks")
    result = {
        "status": "passed" if not errors else "failed", "receipt_id": receipt.get("receipt_id"),
        "official_pdf_reports": len(reports), "resolved_blocks": resolved, "unresolved_blocks": unresolved,
        "spot_checks": sample, "errors": sorted(set(errors)),
    }
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
