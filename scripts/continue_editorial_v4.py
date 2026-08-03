#!/usr/bin/env python3
"""Continue QA/repair iterations for a previously generated editorial V4 draft."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product"))

from deepseek_writer import DEFAULT_KEY_FILE, DEFAULT_MODEL  # noqa: E402
from editorial_v4_contract import canonical_hash, validate_dossier  # noqa: E402
from editorial_v4_generator import generate_once, write_draft  # noqa: E402
from editorial_v4_qa import independent_qa, repair_feedback  # noqa: E402
from editorial_v4_renderer import render_dossier  # noqa: E402


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("ticker")
    parser.add_argument("--root", type=Path, default=ROOT / "artifacts/editorial-v4")
    parser.add_argument("--max-extra", type=int, default=5)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--key-file", type=Path, default=DEFAULT_KEY_FILE)
    parser.add_argument("--reasoning-effort", default="high")
    parser.add_argument("--thinking-type", choices=("enabled", "disabled"), default="enabled")
    parser.add_argument("--max-tokens", type=int, default=22000)
    args = parser.parse_args()
    ticker = args.ticker.upper()
    out = args.root / ticker
    packet = json.loads((args.root / "evidence-packets" / f"{ticker}.json").read_text(encoding="utf-8"))
    receipt_path = out / "quality-loop-receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8")) if receipt_path.exists() else {"iterations": []}
    iterations = receipt.setdefault("iterations", [])
    last_iter = max((int(row.get("iteration", -1)) for row in iterations), default=-1)
    # The stable root is written only for a passed dossier.  When the latest
    # candidate is needs_review, always continue from that latest iteration,
    # never silently fall back to an older root report.
    prior_path = out / "iterations" / str(last_iter) / "report.json" if last_iter >= 0 else out / "report.json"
    if not prior_path.exists():
        prior_path = out / "report.json"
    if not prior_path.exists():
        last = max((int(p.name) for p in (out / "iterations").iterdir() if p.name.isdigit()), default=-1)
        prior_path = out / "iterations" / str(last) / "report.json"
    prior = json.loads(prior_path.read_text(encoding="utf-8"))
    last_machine = validate_dossier(prior, packet)
    last_qa: dict[str, object] = {}
    for extra in range(max(1, args.max_extra)):
        iteration = last_iter + 1
        machine = validate_dossier(prior, packet)
        qa, qa_receipt, qa_request = independent_qa(prior, packet, machine, key_file=args.key_file, model=args.model)
        last_machine, last_qa = machine, qa
        feedback = repair_feedback(machine, qa)
        if not feedback:
            # A no-feedback recheck is still a real QA event.  Persist it
            # instead of silently treating the previous iteration's stale QA
            # file as proof; both deterministic machine validation and this
            # fresh QA result must be passed.
            recheck_dir = out / "iterations" / str(last_iter)
            _write(recheck_dir / "independent-qa-recheck.json", qa)
            _write(recheck_dir / "qa-recheck-provider-receipt.json", qa_receipt)
            _write(recheck_dir / "qa-recheck-request.json", qa_request)
            for row in iterations:
                if int(row.get("iteration", -1)) == last_iter:
                    row.update({
                        "qa_status": qa.get("status"),
                        "qa_run_id": qa.get("run_id"),
                        "qa_request_id": qa_receipt.get("request_id"),
                        "qa_blockers": len(qa.get("blockers") or []),
                        "qa_advisories": len(qa.get("advisories") or []),
                    })
            receipt["final_iteration"] = last_iter
            receipt["final_report_hash"] = canonical_hash(prior)
            receipt["machine_status"] = machine["status"]
            receipt["independent_qa_status"] = qa["status"]
            receipt["independent_qa_raw_status"] = qa.get("raw_status") or qa.get("status")
            receipt["independent_qa_filtered_blockers"] = qa.get("blockers") or []
            receipt["qa_filter_version"] = qa.get("filter_version")
            receipt["final_status"] = "passed" if machine.get("status") == "passed" and qa.get("status") == "passed" else "needs_review"
            break
        dossier, provider_receipt, request = generate_once(
            packet, key_file=args.key_file, model=args.model, iteration=iteration,
            repair_feedback=feedback, prior_dossier=prior,
            reasoning_effort=args.reasoning_effort, max_tokens=args.max_tokens, thinking_type=args.thinking_type,
        )
        iteration_dir = out / "iterations" / str(iteration)
        iteration_dir.mkdir(parents=True, exist_ok=True)
        write_draft(dossier, iteration_dir)
        _write(iteration_dir / "generation-request.json", request)
        _write(iteration_dir / "provider-receipt.json", provider_receipt)
        next_machine = validate_dossier(dossier, packet)
        next_qa, next_qa_receipt, next_qa_request = independent_qa(dossier, packet, next_machine, key_file=args.key_file, model=args.model)
        last_machine, last_qa = next_machine, next_qa
        _write(iteration_dir / "machine-validation.json", next_machine)
        _write(iteration_dir / "independent-qa.json", next_qa)
        _write(iteration_dir / "qa-provider-receipt.json", next_qa_receipt)
        _write(iteration_dir / "qa-request.json", next_qa_request)
        row = {"iteration": iteration, "run_id": dossier.get("production_record", {}).get("run_id"), "request_id": provider_receipt.get("request_id"), "report_hash": canonical_hash(dossier), "machine_status": next_machine["status"], "machine_errors": len(next_machine.get("errors") or []), "qa_status": next_qa["status"], "qa_run_id": next_qa.get("run_id"), "qa_request_id": next_qa_receipt.get("request_id"), "qa_blockers": len(next_qa.get("blockers") or [])}
        iterations.append(row)
        prior = dossier
        last_iter = iteration
        if next_machine["status"] == "passed" and next_qa["status"] == "passed":
            write_draft(dossier, out)
            render_dossier(dossier, packet, out)
            receipt.update({"final_iteration": iteration, "final_report_hash": canonical_hash(dossier), "machine_status": "passed", "independent_qa_status": "passed", "final_status": "passed", "review_status": "pending", "action_state": "blocked", "no_tier_credit": True, "no_publication_credit": True})
            break
    else:
        receipt.update({"final_iteration": last_iter, "final_report_hash": canonical_hash(prior), "final_status": "needs_review", "machine_status": last_machine.get("status"), "machine_errors": last_machine.get("errors") or [], "independent_qa_status": last_qa.get("status"), "independent_qa_run_id": last_qa.get("run_id"), "independent_qa_blockers": last_qa.get("blockers") or []})
    # The no-feedback path can terminate at the top of the loop after a
    # successful repair.  Persist that exact candidate at the stable root as
    # well; iteration receipts remain the immutable audit trail.
    if receipt.get("final_status") == "passed" and canonical_hash(prior) == receipt.get("final_report_hash"):
        write_draft(prior, out)
        render_dossier(prior, packet, out)
    receipt["iterations"] = iterations
    _write(receipt_path, receipt)
    print(json.dumps({"ticker": ticker, "final_status": receipt.get("final_status"), "final_iteration": receipt.get("final_iteration"), "machine_status": receipt.get("machine_status"), "qa_status": receipt.get("independent_qa_status")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
