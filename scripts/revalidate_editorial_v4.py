#!/usr/bin/env python3
"""Re-run deterministic validation/filtering on an existing DeepSeek QA receipt.

This does not invent a new model result.  It is used when the contract/filter
gets stricter or fixes a known QA false-positive class: the raw DeepSeek
response remains immutable, while the current deterministic filter decides
whether the draft can be persisted as a review-only pass.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product"))

from editorial_v4_contract import canonical_hash, validate_dossier  # noqa: E402
from editorial_v4_qa import QA_FILTER_VERSION, _filter_false_positive_blockers  # noqa: E402
from editorial_v4_renderer import render_dossier  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("ticker")
    parser.add_argument("--root", type=Path, default=ROOT / "artifacts/editorial-v4")
    parser.add_argument("--iteration", type=int, default=None)
    args = parser.parse_args()

    ticker = args.ticker.upper()
    out = args.root / ticker
    packet = json.loads((args.root / "evidence-packets" / f"{ticker}.json").read_text(encoding="utf-8"))
    receipt_path = out / "quality-loop-receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8")) if receipt_path.exists() else {"iterations": []}
    iteration = args.iteration
    if iteration is None:
        iteration = max(int(row.get("iteration", -1)) for row in receipt.get("iterations") or [])
    iteration_dir = out / "iterations" / str(iteration)
    dossier = json.loads((iteration_dir / "report.json").read_text(encoding="utf-8"))
    # A fresh no-feedback QA recheck supersedes the original QA response.  Do
    # not let a stale malformed/false-positive response turn a valid draft
    # back into needs_review when this script is rerun after a filter update.
    qa_path = iteration_dir / "independent-qa-recheck.json"
    if not qa_path.exists():
        qa_path = iteration_dir / "independent-qa.json"
    raw_qa = json.loads(qa_path.read_text(encoding="utf-8"))
    raw_blockers = raw_qa.get("raw_blockers") or raw_qa.get("blockers") or []
    raw_status = raw_qa.get("raw_status")
    if raw_status not in {"passed", "failed"}:
        raw_status = "failed" if any(
            not isinstance(row, dict) or str(row.get("severity") or "blocker").lower() == "blocker"
            for row in raw_blockers
        ) else "passed"
    machine = validate_dossier(dossier, packet)
    filtered = _filter_false_positive_blockers(raw_qa, dossier, packet, machine)
    status = "passed" if machine.get("status") == "passed" and not filtered else "needs_review"
    filtered_qa = dict(raw_qa)
    filtered_qa.update({
        "raw_status": raw_status,
        "raw_blockers": raw_blockers,
        "status": "passed" if not filtered else "failed",
        "blockers": filtered,
        "filtered_blockers": filtered,
        "filter_version": QA_FILTER_VERSION,
        "filtered_from": qa_path.name,
        "filtered_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    })
    (iteration_dir / "independent-qa-filtered.json").write_text(
        json.dumps(filtered_qa, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    shutil.copyfile(iteration_dir / "report.json", out / "report.json")
    render_dossier(dossier, packet, out)
    receipt.update({
        "final_iteration": iteration,
        "final_report_hash": canonical_hash(dossier),
        "machine_status": machine.get("status"),
        "machine_errors": machine.get("errors") or [],
        "independent_qa_status": "passed" if not filtered else "failed",
        "independent_qa_raw_status": raw_status,
        "independent_qa_raw_blockers": raw_blockers,
        "independent_qa_filtered_blockers": filtered,
        "qa_filter_version": QA_FILTER_VERSION,
        "final_status": status,
        "review_status": "pending",
        "action_state": "blocked",
        "no_tier_credit": True,
        "no_publication_credit": True,
        "revalidated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    })
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ticker": ticker, "iteration": iteration, "final_status": status, "machine_status": machine.get("status"), "raw_qa_status": raw_status, "filtered_blockers": len(filtered), "filter_version": QA_FILTER_VERSION}, ensure_ascii=False))


if __name__ == "__main__":
    main()
