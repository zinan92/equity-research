#!/usr/bin/env python3
"""Verify the two persistent E4 wired-report outputs without changing data."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product"))

from data_core.e4_judgment_review_queue import build_judgment_review_queue
from data_core.e4_judgment_wiring import wire_unreviewed_judgment_receipt


def digest(value: dict, *, omit_receipt_hash: bool = False) -> str:
    payload = {key: item for key, item in value.items() if key != "receipt_hash"} if omit_receipt_hash else value
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def canonical_receipt_digest(value: dict) -> str:
    payload = {key: item for key, item in value.items() if key != "receipt_hash"}
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        ).encode()
    ).hexdigest()


def summary(
    receipt_path: Path,
    queue_path: Path,
    judgment_path: Path,
    wiring_path: Path,
) -> dict:
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    judgment = json.loads(judgment_path.read_text(encoding="utf-8"))
    wiring = json.loads(wiring_path.read_text(encoding="utf-8"))
    wire_unreviewed_judgment_receipt(judgment, ticker=receipt.get("ticker", ""))
    if (
        receipt.get("schema_version") != "round7-transitional-report-v1"
        or receipt.get("section_contract_schema_version")
        != "research-section-contract-v3"
        or receipt.get("body_kind")
        != "transitional_evidence_status_not_round7_chapter_dossier"
    ):
        raise ValueError("report receipt is not the Round 7 transitional schema")
    if receipt.get("receipt_hash") != digest(receipt, omit_receipt_hash=True):
        raise ValueError("report receipt hash mismatch")
    if receipt.get("input_hashes", {}).get("m3") != digest(judgment):
        raise ValueError("report does not bind the supplied judgment receipt")
    if (
        wiring.get("schema_version") != "round7-m2-wiring-migration-v1"
        or wiring.get("receipt_hash") != canonical_receipt_digest(wiring)
    ):
        raise ValueError("Round 7 wiring receipt identity is invalid")
    if receipt.get("input_hashes", {}).get("m2") != digest(wiring):
        raise ValueError("report does not bind the supplied Round 7 wiring receipt")
    html = Path(receipt["html_path"])
    html_bytes = html.read_bytes() if html.is_file() else b""
    if (
        hashlib.sha256(html_bytes).hexdigest() != receipt.get("html_sha256")
        or len(html_bytes) != receipt.get("html_bytes")
    ):
        raise ValueError("report HTML hash or size mismatch")
    rendered = html_bytes.decode("utf-8")
    if "数据时点" not in rendered:
        raise ValueError(f"missing or invalid report HTML: {html}")
    if receipt.get("tier") == "A":
        raise ValueError("wired report must not reach Tier A")
    if f"含 {receipt.get('unreviewed_judgment_count')} 项未审阅 AI 判断" not in rendered:
        raise ValueError("report does not display the unreviewed judgment count")
    states = Counter(item["status"] for item in receipt["sections"])
    if sum(states.values()) != 9:
        raise ValueError("report does not contain the nine Round 7 sections")
    if queue.get("ticker") != receipt.get("ticker"):
        raise ValueError("review queue ticker does not match report receipt")
    if queue.get("source_receipt_id") != receipt.get("judgment_source_receipt_id"):
        raise ValueError("review queue source receipt does not match report receipt")
    queue_items = queue.get("items", [])
    queue_ids = [item.get("judgment_id") for item in queue_items]
    if set(queue_ids) != set(receipt.get("unreviewed_judgment_ids", [])):
        raise ValueError("review queue is not a complete copy of report judgments")
    if [item.get("impact_rank") for item in queue_items] != sorted(item.get("impact_rank") for item in queue_items):
        raise ValueError("review queue is not sorted by conclusion impact")
    if len(queue_items) != receipt.get("unreviewed_judgment_count"):
        raise ValueError("review queue count does not match report banner")
    section_by_id = {item["section_id"]: item for item in receipt["sections"]}
    wiring_row = next(
        (
            item
            for item in wiring.get("rows", [])
            if str(item.get("ticker", "")).upper() == receipt["ticker"].upper()
        ),
        None,
    )
    if (
        wiring_row is None
        or wiring_row.get("result", {})
        .get("section_contract", {})
        .get("sections")
        != receipt["sections"]
    ):
        raise ValueError("report sections do not match the supplied Round 7 wiring")
    expected_queue = build_judgment_review_queue(
        judgment,
        ticker=receipt["ticker"],
        section_assessments=section_by_id,
    )
    if queue != expected_queue:
        raise ValueError("review queue content does not match the real judgment receipt")
    for item in queue_items:
        section = section_by_id[item["section_id"]]
        if section["status"] != "partial" or section.get("status_reason") != "pending_judgment_review":
            raise ValueError("an unreviewed judgment is not held at PARTIAL pending review")
        if item.get("review_status") != "pending_human_review" or not item.get("body"):
            raise ValueError("review queue item is not directly reviewable")
        if not item.get("citations") or not all(
            citation.get("document_id")
            and citation.get("page_number")
            and citation.get("quoted_anchor")
            and citation.get("pdf_page_url")
            for citation in item["citations"]
        ):
            raise ValueError("review queue item lacks page-level evidence")
    return {"ticker": receipt["ticker"], "html_path": str(html), "receipt_path": str(receipt_path), "review_queue_path": str(queue_path), "judgment_source_receipt_id": receipt["judgment_source_receipt_id"], "tier": receipt["tier"], "tier_reasons": receipt["tier_reasons"], "unreviewed_judgment_count": receipt["unreviewed_judgment_count"], "section_counts": dict(states), "sections": [{key: item.get(key) for key in ("section_id", "status", "status_reason", "present_required", "missing_required")} for item in receipt["sections"]]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("receipts", nargs="+", type=Path)
    parser.add_argument("--review-queue", action="append", required=True, type=Path)
    parser.add_argument("--judgment", action="append", required=True, type=Path)
    parser.add_argument("--wiring", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    if len(args.receipts) != len(args.review_queue) or len(args.receipts) != len(args.judgment):
        raise ValueError("provide exactly one review queue and judgment receipt for each report receipt")
    reports = [
        summary(receipt, queue, judgment, args.wiring)
        for receipt, queue, judgment in zip(
            args.receipts,
            args.review_queue,
            args.judgment,
        )
    ]
    result = {"schema_version": "round7-wired-report-verification-v1", "status": "passed", "reports": reports}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
