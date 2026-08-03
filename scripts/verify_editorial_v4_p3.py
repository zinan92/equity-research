#!/usr/bin/env python3
"""Fail-closed acceptance audit for the five real V4/P3 dossiers.

This verifier is intentionally independent of the generation loop.  It reads
the frozen packet, final report, iteration receipt, raw QA and persisted
filtered QA, then writes a content-addressed audit result.  It never calls a
model, changes Tier/B6/decision policy, or approves human review.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product"))

from editorial_v4_contract import AGGRESSIVE_JUDGMENT_CUES, SECTIONS, canonical_hash, validate_dossier  # noqa: E402
from editorial_v4_qa import QA_FILTER_VERSION, _filter_false_positive_blockers  # noqa: E402

DEFAULT_TICKERS = ("000333.SZ", "600519.SH", "600900.SH", "300750.SZ", "000001.SZ")


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _qa_path(iteration_dir: Path) -> Path:
    for name in ("independent-qa-filtered.json", "independent-qa-recheck.json", "independent-qa.json"):
        candidate = iteration_dir / name
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"no independent QA artifact in {iteration_dir}")


def audit_one(root: Path, ticker: str) -> dict[str, Any]:
    out = root / ticker
    packet = _read(root / "evidence-packets" / f"{ticker}.json")
    dossier = _read(out / "report.json")
    receipt = _read(out / "quality-loop-receipt.json")
    iteration = int(receipt.get("final_iteration"))
    iteration_dir = out / "iterations" / str(iteration)
    qa_path = _qa_path(iteration_dir)
    qa = _read(qa_path)
    machine = validate_dossier(dossier, packet)
    raw_blockers = qa.get("raw_blockers") or qa.get("blockers") or []
    filtered = qa.get("filtered_blockers") if "filtered_blockers" in qa else None
    if filtered is None:
        filtered = _filter_false_positive_blockers(qa, dossier, packet)
    sections = {str(row.get("id")): str(row.get("body") or "") for row in dossier.get("sections") or [] if isinstance(row, dict)}
    section_checks = {
        section_id: {"chars": len(sections.get(section_id, "")), "minimum": minimum, "passed": len(sections.get(section_id, "")) >= minimum}
        for section_id, _title, minimum in SECTIONS
    }
    judgments = [claim for claim in dossier.get("claims") or [] if isinstance(claim, dict) and claim.get("kind") == "judgment"]
    body = "\n".join([str(dossier.get("latest_card") or "")] + list(sections.values()))
    official = (
        packet.get("data_kind") == "real"
        and packet.get("truth_boundary", {}).get("official_pdf_only") is True
        and all("cninfo.com.cn" in str(source.get("source_url")) for source in packet.get("sources") or [])
    )
    boundary = dossier.get("boundary") or {}
    boundary_ok = all(boundary.get(key) is True for key in ("review_only", "no_tier_credit", "no_b6_credit", "no_decision_policy_credit", "no_publication_credit"))
    checks = {
        "machine": machine.get("status") == "passed",
        "sections": all(row["passed"] for row in section_checks.values()),
        "body_chars": sum(len(value) for value in sections.values()) >= 2200,
        "aggressive_voice": bool(AGGRESSIVE_JUDGMENT_CUES.search(body)) and any(
            AGGRESSIVE_JUDGMENT_CUES.search(str(claim.get("text") or "")) for claim in judgments
        ),
        "judgment_refs_and_falsifiers": all(claim.get("evidence_ids") and claim.get("falsifier") for claim in judgments),
        "official_packet": official,
        "deepseek_run": dossier.get("production_record", {}).get("model_provider") == "DeepSeek",
        "qa_filtered": not filtered,
        "review_boundary": boundary_ok and receipt.get("review_status") == "pending" and receipt.get("action_state") == "blocked",
        "persistent_outputs": all((out / filename).exists() for filename in ("report.json", "report.md", "report.html", "quality-loop-receipt.json")),
    }
    final_status = "passed" if all(checks.values()) else "needs_review"
    return {
        "ticker": ticker,
        "issuer_name": dossier.get("issuer_name"),
        "final_iteration": iteration,
        "final_status": final_status,
        "checks": checks,
        "failed_checks": [name for name, passed in checks.items() if not passed],
        "machine_errors": machine.get("errors") or [],
        "section_checks": section_checks,
        "body_chars": sum(len(value) for value in sections.values()),
        "judgment_count": len(judgments),
        "aggressive_judgment_count": sum(1 for claim in judgments if AGGRESSIVE_JUDGMENT_CUES.search(str(claim.get("text") or ""))),
        "raw_qa_blockers": len(raw_blockers),
        "filtered_qa_blockers": len(filtered),
        "qa_path": str(qa_path.relative_to(root)),
        "packet_hash": packet.get("packet_hash"),
        "report_hash": canonical_hash(dossier),
        "review_only": True,
        "no_tier_credit": True,
        "no_publication_credit": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT / "artifacts/editorial-v4-p3")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("tickers", nargs="*", default=list(DEFAULT_TICKERS))
    args = parser.parse_args()
    rows = [audit_one(args.root, ticker.upper()) for ticker in args.tickers]
    result = {
        "schema_version": "editorial-v4-p3-completion-audit-v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "root": str(args.root),
        "qa_filter_version": QA_FILTER_VERSION,
        "all_passed": all(row["final_status"] == "passed" for row in rows),
        "review_only": True,
        "no_tier_credit": True,
        "no_publication_credit": True,
        "reports": rows,
    }
    output = args.output or args.root / "completion-audit.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "all_passed": result["all_passed"], "reports": [{"ticker": row["ticker"], "status": row["final_status"], "failed_checks": row["failed_checks"]} for row in rows]}, ensure_ascii=False))
    if not result["all_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
