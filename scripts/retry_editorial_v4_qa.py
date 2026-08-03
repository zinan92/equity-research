#!/usr/bin/env python3
"""Run the real independent QA pass for an existing V4 iteration.

This is intentionally separate from deterministic revalidation: it never
rewrites the model dossier and never turns a malformed/failed model response
into a pass.  It is useful when generation succeeded but the QA transport
returned a transient malformed JSON response.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product"))

from deepseek_writer import DEFAULT_KEY_FILE, DEFAULT_MODEL  # noqa: E402
from editorial_v4_contract import canonical_hash, validate_dossier  # noqa: E402
from editorial_v4_qa import independent_qa  # noqa: E402
from editorial_v4_renderer import render_dossier  # noqa: E402
from editorial_v4_generator import write_draft  # noqa: E402


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("ticker")
    parser.add_argument("--root", type=Path, default=ROOT / "artifacts/editorial-v4")
    parser.add_argument("--iteration", type=int, required=True)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--key-file", type=Path, default=DEFAULT_KEY_FILE)
    args = parser.parse_args()
    ticker = args.ticker.upper()
    out = args.root / ticker
    iteration_dir = out / "iterations" / str(args.iteration)
    packet = json.loads((args.root / "evidence-packets" / f"{ticker}.json").read_text(encoding="utf-8"))
    dossier = json.loads((iteration_dir / "report.json").read_text(encoding="utf-8"))
    machine = validate_dossier(dossier, packet)
    qa, qa_receipt, qa_request = independent_qa(
        dossier, packet, machine, key_file=args.key_file, model=args.model,
    )
    _write(iteration_dir / "independent-qa.json", qa)
    _write(iteration_dir / "qa-provider-receipt.json", qa_receipt)
    _write(iteration_dir / "qa-request.json", qa_request)

    receipt_path = out / "quality-loop-receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8")) if receipt_path.exists() else {"iterations": []}
    rows = receipt.setdefault("iterations", [])
    rows = [row for row in rows if int(row.get("iteration", -1)) != args.iteration]
    rows.append({
        "iteration": args.iteration,
        "run_id": dossier.get("production_record", {}).get("run_id"),
        "request_id": (dossier.get("generation_receipt") or {}).get("request_id"),
        "report_hash": canonical_hash(dossier),
        "machine_status": machine.get("status"),
        "machine_errors": len(machine.get("errors") or []),
        "qa_status": qa.get("status"),
        "qa_run_id": qa.get("run_id"),
        "qa_request_id": qa_receipt.get("request_id"),
        "qa_blockers": len(qa.get("blockers") or []),
        "qa_advisories": len(qa.get("advisories") or []),
    })
    rows.sort(key=lambda row: int(row.get("iteration", -1)))
    receipt["iterations"] = rows
    receipt.update({
        "final_iteration": args.iteration,
        "final_report_hash": canonical_hash(dossier),
        "final_status": "passed" if machine.get("status") == "passed" and qa.get("status") == "passed" else "needs_review",
        "machine_status": machine.get("status"),
        "machine_errors": machine.get("errors") or [],
        "independent_qa_status": qa.get("status"),
        "independent_qa_raw_status": qa.get("raw_status") or qa.get("status"),
        "independent_qa_filtered_blockers": qa.get("blockers") or [],
        "qa_filter_version": qa.get("filter_version"),
        "revalidated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "review_status": "pending",
        "action_state": "blocked",
        "no_tier_credit": True,
        "no_publication_credit": True,
    })
    _write(receipt_path, receipt)
    if receipt["final_status"] == "passed":
        write_draft(dossier, out)
        render_dossier(dossier, packet, out)
    print(json.dumps({
        "ticker": ticker,
        "iteration": args.iteration,
        "final_status": receipt["final_status"],
        "machine_status": machine.get("status"),
        "raw_qa_status": qa.get("status"),
        "filtered_blockers": len(qa.get("blockers") or []),
        "filter_version": qa.get("filter_version"),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
