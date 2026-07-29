#!/usr/bin/env python3
"""Summarize a 100-ticker official-PDF financial-sequence run, fail closed."""
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
        raise ValueError(f"{path} must be a JSON object")
    return value


def build_summary(sequence: Mapping[str, Any], identity: Mapping[str, Any]) -> dict[str, Any]:
    boundary = sequence.get("truth_boundary") or {}
    if sequence.get("schema_version") != "e4-financial-sequence-batch-v1" or sequence.get("data_kind") != "real":
        raise ValueError("financial sequence must be a real batch receipt")
    if boundary.get("official_cninfo_pdf_only") is not True or boundary.get("page_bound_only") is not True:
        raise ValueError("financial sequence must retain official page-bound truth boundary")
    rows = sequence.get("tickers") or []
    cohort = sequence.get("cohort") or []
    if len(rows) != 100 or len(cohort) != 100 or set(cohort) != {row.get("ticker") for row in rows}:
        raise ValueError("L2-M1 requires a completed 100-ticker cohort")
    if sequence.get("configured_max_concurrency") != 1 or sequence.get("sequential") is not True:
        raise ValueError("L2-M1 must remain single-concurrency sequential")
    if len(sequence.get("periods_attempted") or []) != 6:
        raise ValueError("financial history must attempt five FY periods plus the interim floor")
    identity_records = identity.get("records") or []
    identity_by_ticker = {str(item.get("ticker") or "").upper(): item for item in identity_records}
    if identity.get("schema_version") != "ashare-security-master-v1" or identity.get("data_kind") != "real":
        raise ValueError("identity input must be a real security-master receipt")
    if not set(cohort).issubset(identity_by_ticker):
        raise ValueError("financial cohort is not contained in the frozen identity receipt")
    failures = Counter(
        str(report.get("reason") or "unknown")
        for row in rows for report in row.get("reports") or [] if report.get("status") == "missing"
    )
    rows_with_facts = [row for row in rows if any(report.get("facts") for report in row.get("reports") or [])]
    return {
        "schema_version": "e4-l2-m1-financial-batch-verification-v1",
        "data_kind": "real",
        "identity_receipt_hash": identity.get("receipt_hash"),
        "financial_sequence_receipt_hash": sequence.get("receipt_hash"),
        "coverage": {
            "requested_tickers": len(rows),
            "tickers_with_at_least_one_page_fact": len(rows_with_facts),
            "available_reports": sequence.get("counts", {}).get("available_reports"),
            "missing_reports": sequence.get("counts", {}).get("missing_reports"),
            "page_facts": sequence.get("counts", {}).get("facts"),
            "periods_attempted_per_ticker": len(sequence.get("periods_attempted") or []),
            "exchange_counts": dict(sorted(Counter(str(identity_by_ticker[ticker].get("exchange")) for ticker in cohort).items())),
        },
        "missing_reason_counts": dict(sorted(failures.items())),
        "truth_boundary": {
            "identity_is_not_financial_fact": True,
            "official_cninfo_pdf_only": True,
            "page_bound_only": True,
            "does_not_promote_tier_or_action": True,
            "missing_is_retained_not_filled": True,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--financial-sequence", type=Path, required=True)
    parser.add_argument("--identity-receipt", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    output = build_summary(_load(args.financial_sequence), _load(args.identity_receipt))
    output["verification_hash"] = hashlib.sha256(json.dumps(output, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(args.out)


if __name__ == "__main__":
    main()
