#!/usr/bin/env python3
"""Verify the V4/P4 golden-set freeze and one out-of-sample dossier."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product"))

from editorial_v4_contract import canonical_hash  # noqa: E402
from verify_editorial_v4_p3 import audit_one  # noqa: E402


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT / "artifacts/editorial-v4-p4")
    parser.add_argument("--golden", type=Path, default=ROOT / "artifacts/editorial-v4-p4/golden-set-manifest.json")
    parser.add_argument("--ticker", default="000002.SZ")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    golden = _read(args.golden)
    golden_rows = {str(row.get("ticker")): row for row in golden.get("reports") or [] if isinstance(row, dict)}
    golden_checks = {
        "park_review_accepted": golden.get("park_review_status") == "accepted",
        "five_report_set": len(golden_rows) == 5 and set(golden_rows) == {"000333.SZ", "600519.SH", "600900.SH", "300750.SZ", "000001.SZ"},
        "no_prose_reuse": golden.get("prose_reuse_for_generation") is False,
        "no_evidence_reuse": golden.get("evidence_reuse_for_generation") is False,
        "all_review_only": all(row.get("review_only") is True and row.get("no_tier_credit") is True and row.get("no_publication_credit") is True for row in golden_rows.values()),
    }
    blind = args.ticker.upper()
    blind_dir = args.root / blind
    audit = audit_one(args.root, blind)
    packet = _read(args.root / "evidence-packets" / f"{blind}.json")
    receipt = _read(blind_dir / "quality-loop-receipt.json")
    request_paths = sorted(blind_dir.glob("iterations/*/generation-request.json"))
    request_text = "\n".join(path.read_text(encoding="utf-8") for path in request_paths)
    blind_checks = {
        "not_in_golden_set": blind not in golden_rows,
        "official_packet": packet.get("data_kind") == "real" and packet.get("truth_boundary", {}).get("official_pdf_only") is True,
        "fresh_deepseek_receipt": bool(request_paths) and audit.get("issuer_name") and receipt.get("packet_hash") == packet.get("packet_hash"),
        "no_golden_text_in_request": not any(str(row.get("ticker")) in request_text for row in golden_rows.values()),
        "blind_audit_passed": audit.get("final_status") == "passed",
        "review_only": receipt.get("review_status") == "pending" and receipt.get("action_state") == "blocked" and receipt.get("no_tier_credit") is True and receipt.get("no_publication_credit") is True,
    }
    result = {
        "schema_version": "editorial-v4-p4-blind-acceptance-audit-v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "golden_manifest_hash": canonical_hash(golden),
        "golden_checks": golden_checks,
        "blind_ticker": blind,
        "blind_checks": blind_checks,
        "blind_report": audit,
        "all_passed": all(golden_checks.values()) and all(blind_checks.values()),
        "review_only": True,
        "no_tier_credit": True,
        "no_publication_credit": True,
    }
    output = args.output or args.root / "blind-acceptance-audit.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # Keep a compact hand-off receipt separate from the immutable per-iteration
    # batch receipt.  The latter records the initial needs_review run; this
    # receipt records the accepted final iteration after repair/revalidation so
    # readers do not mistake historical blockers for the current gate state.
    final_receipt = {
        "schema_version": "editorial-v4-p4-final-receipt-v1",
        "generated_at": result["generated_at"],
        "golden_manifest_hash": result["golden_manifest_hash"],
        "golden_tickers": sorted(golden_rows),
        "rejected_candidates": [
            {
                "ticker": str(row.get("ticker") or ""),
                "reason_code": row.get("reason_code"),
                "status": row.get("status"),
            }
            for row in (_read(args.root / "blind-candidate-rejections/300115.SZ.json"),)
        ] if (args.root / "blind-candidate-rejections/300115.SZ.json").exists() else [],
        "blind": {
            "ticker": blind,
            "issuer_name": audit.get("issuer_name"),
            "packet_hash": packet.get("packet_hash"),
            "final_iteration": audit.get("final_iteration"),
            "report_hash": audit.get("report_hash"),
            "body_chars": audit.get("body_chars"),
            "judgment_count": audit.get("judgment_count"),
            "aggressive_judgment_count": audit.get("aggressive_judgment_count"),
            "machine_status": receipt.get("machine_status"),
            "qa_raw_status": receipt.get("independent_qa_raw_status"),
            "qa_raw_blockers": len(receipt.get("independent_qa_raw_blockers") or []),
            "qa_filtered_status": receipt.get("independent_qa_status"),
            "qa_filtered_blockers": len(receipt.get("independent_qa_filtered_blockers") or []),
            "review_status": receipt.get("review_status"),
            "action_state": receipt.get("action_state"),
            "no_tier_credit": receipt.get("no_tier_credit"),
            "no_publication_credit": receipt.get("no_publication_credit"),
        },
        "acceptance_audit": "blind-acceptance-audit.json",
        "all_passed": result["all_passed"],
        "review_only": True,
        "no_tier_credit": True,
        "no_publication_credit": True,
    }
    (args.root / "final-receipt.json").write_text(json.dumps(final_receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "all_passed": result["all_passed"], "golden_checks": golden_checks, "blind_checks": blind_checks}, ensure_ascii=False))
    if not result["all_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
