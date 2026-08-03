#!/usr/bin/env python3
"""Build one replayable, review-only acceptance receipt for the V4 P3 batch.

The aggregate is deliberately read-only with respect to dossier roots: it
revalidates each final report against its frozen official evidence packet and
records the raw independent-QA diagnostics separately from the deterministic
filtered blockers.  It never grants Tier, action, or publication credit.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product"))

from editorial_v4_contract import AGGRESSIVE_JUDGMENT_CUES, canonical_hash, validate_dossier  # noqa: E402
from editorial_v4_qa import QA_FILTER_VERSION, _filter_false_positive_blockers  # noqa: E402


DEFAULT_TICKERS = ("000333.SZ", "600519.SH", "600900.SH", "300750.SZ", "000001.SZ")


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _iteration(receipt: dict[str, Any]) -> int:
    final = receipt.get("final_iteration")
    if final is not None:
        return int(final)
    return max(int(row.get("iteration", -1)) for row in receipt.get("iterations") or [])


def _aggressive_samples(dossier: dict[str, Any]) -> tuple[int, list[str]]:
    samples: list[str] = []
    count = 0
    for claim in dossier.get("claims") or []:
        if not isinstance(claim, dict) or claim.get("kind") != "judgment":
            continue
        text = str(claim.get("text") or "")
        if AGGRESSIVE_JUDGMENT_CUES.search(text):
            count += 1
            if len(samples) < 5:
                samples.append(f"{claim.get('claim_id')}: {text}")
    return count, samples


def build(root: Path, tickers: tuple[str, ...]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for ticker in tickers:
        out = root / ticker
        packet = _read(root / "evidence-packets" / f"{ticker}.json")
        receipt = _read(out / "quality-loop-receipt.json")
        iteration = _iteration(receipt)
        iteration_dir = out / "iterations" / str(iteration)
        dossier = _read(out / "report.json")
        machine = validate_dossier(dossier, packet)
        qa_path = iteration_dir / "independent-qa-filtered.json"
        if not qa_path.exists():
            qa_path = iteration_dir / "independent-qa-recheck.json"
        if not qa_path.exists():
            qa_path = iteration_dir / "independent-qa.json"
        qa = _read(qa_path)
        filtered = _filter_false_positive_blockers(qa, dossier, packet)
        raw = qa.get("raw_blockers") or qa.get("blockers") or []
        raw_status = qa.get("raw_status")
        if raw_status not in {"passed", "failed"}:
            raw_status = "failed" if any(
                not isinstance(row, dict) or str(row.get("severity") or "blocker").lower() == "blocker"
                for row in raw
            ) else "passed"
        sections = [
            {"id": row.get("id"), "title": row.get("title"), "chars": len(str(row.get("body") or ""))}
            for row in dossier.get("sections") or []
            if isinstance(row, dict)
        ]
        aggressive_count, aggressive_samples = _aggressive_samples(dossier)
        final_status = "passed" if machine.get("status") == "passed" and not filtered else "needs_review"
        rows.append({
            "ticker": ticker,
            "issuer_name": dossier.get("issuer_name"),
            "final_iteration": iteration,
            "final_status": final_status,
            "receipt_status": receipt.get("final_status"),
            "report_hash": canonical_hash(dossier),
            "packet_hash": packet.get("packet_hash"),
            "machine_status": machine.get("status"),
            "machine_errors": machine.get("errors") or [],
            "independent_qa_file": str(qa_path.relative_to(root)),
            "independent_qa_raw_status": raw_status,
            "independent_qa_raw_blockers": len(raw),
            "independent_qa_filtered_blockers": filtered,
            "qa_filter_version": qa.get("filter_version") or QA_FILTER_VERSION,
            "body_chars": sum(row["chars"] for row in sections),
            "section_lengths": sections,
            "claim_count": len(dossier.get("claims") or []),
            "aggressive_judgment_count": aggressive_count,
            "aggressive_judgment_samples": aggressive_samples,
            "review_status": receipt.get("review_status", "pending"),
            "action_state": receipt.get("action_state", "blocked"),
            "no_tier_credit": bool(receipt.get("no_tier_credit", True)),
            "no_publication_credit": bool(receipt.get("no_publication_credit", True)),
            "report_paths": {
                "markdown": str((out / "report.md").relative_to(root.parent.parent)),
                "html": str((out / "report.html").relative_to(root.parent.parent)),
                "receipt": str((out / "quality-loop-receipt.json").relative_to(root.parent.parent)),
            },
        })
    return {
        "schema_version": "editorial-v4-p3-aggregate-receipt-v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "root": str(root),
        "source": "real DeepSeek whole-report runs over frozen official-PDF evidence packets",
        "review_only": True,
        "action_state": "blocked",
        "no_tier_credit": True,
        "no_publication_credit": True,
        "qa_filter_version": QA_FILTER_VERSION,
        "all_final_status_passed": all(row["final_status"] == "passed" for row in rows),
        "tickers": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT / "artifacts/editorial-v4-p3")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("tickers", nargs="*", default=list(DEFAULT_TICKERS))
    args = parser.parse_args()
    result = build(args.root, tuple(ticker.upper() for ticker in args.tickers))
    output = args.output or args.root / "aggregate-receipt.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "all_final_status_passed": result["all_final_status_passed"],
        "tickers": [{"ticker": row["ticker"], "final_status": row["final_status"], "body_chars": row["body_chars"], "raw_qa_blockers": row["independent_qa_raw_blockers"], "filtered_blockers": len(row["independent_qa_filtered_blockers"])} for row in result["tickers"]],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
