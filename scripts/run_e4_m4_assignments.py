#!/usr/bin/env python3
"""Select one conservative, page-bound M2 fact per ticker for M4 audit."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


_METRIC_PRIORITY = (
    "total_assets", "total_liabilities", "revenue", "net_profit_parent",
    "operating_cash_flow", "capital_expenditure", "operating_profit",
    "total_profit", "depreciation_fixed_assets", "cash", "current_assets",
    "current_liabilities", "share_capital_amount",
)
_UNIT_MULTIPLIER = {"元": 1.0, "千元": 1_000.0, "万元": 10_000.0, "百万元": 1_000_000.0, "人民币百万元": 1_000_000.0}


def _has_note_reference_before_value(fact: dict) -> bool:
    """Reject a Chinese table note (for example ``六、22``) as a value."""
    label = str(fact.get("quoted_label") or "")
    anchor = str(fact.get("quoted_anchor") or "")
    suffix = anchor[anchor.find(label) + len(label):] if label and label in anchor else anchor
    return bool(re.match(r"\s*[一二三四五六七八九十]+、\d+\s+", suffix))


def _annotate_cross_year_status(facts: list[dict]) -> None:
    """Attach an honest status without deduplicating multi-document facts."""
    groups: dict[tuple[str, str], list[dict]] = {}
    for fact in facts:
        if fact.get("column_identity") not in {"current_period", "previous_period", "period_end", "period_begin"}:
            continue
        if fact.get("unit") not in _UNIT_MULTIPLIER:
            continue
        groups.setdefault((str(fact.get("metric")), str(fact.get("report_period"))), []).append(fact)
    for group in groups.values():
        document_ids = {str(fact.get("document_id")) for fact in group}
        if len(document_ids) < 2:
            for fact in group:
                fact["cross_year_status"] = "unverified"
            continue
        values = [float(fact["value"]) * _UNIT_MULTIPLIER[str(fact["unit"])] for fact in group]
        consistent = max(values) - min(values) <= max(1.0, max(abs(value) for value in values) * 1e-6)
        for fact in group:
            fact["cross_year_status"] = "cross_verified" if consistent else "disputed"


def _select_fact(facts: list[dict]) -> dict | None:
    candidates = [
        fact for fact in facts
        if fact.get("column_identity") in {"current_period", "period_end"}
        and fact.get("metric") in _METRIC_PRIORITY
        and fact.get("cross_year_status", "unverified") != "disputed"
        and not _has_note_reference_before_value(fact)
        # Audit selection can be stricter than fact admission. This cohort's
        # expected currency values are material issuer statements; filtering
        # out tiny values prevents an unresolved note reference becoming the
        # reader's first independent audit object.
        and abs(float(fact.get("value") or 0)) >= 1_000
    ]
    return min(
        candidates,
        key=lambda fact: (
            0 if fact.get("cross_year_status") == "cross_verified" else 1,
            _METRIC_PRIORITY.index(fact["metric"]),
        ),
    ) if candidates else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("m2", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    source = json.loads(args.m2.read_text())
    assignments: list[dict] = []
    gaps: list[dict] = []
    for row in source["tickers"]:
        facts = [fact for report in row["reports"] for fact in report.get("facts", [])]
        _annotate_cross_year_status(facts)
        fact = _select_fact(facts)
        if fact is None:
            gaps.append({"ticker": row["ticker"], "reason": "no_conservative_page_bound_fact"})
            continue
        assignments.append({
            "ticker": row["ticker"],
            "numeric_check": {
                "metric": fact["metric"], "expected_value": fact["value"],
                "unit": fact["unit"], "currency": fact["currency"],
                "report_period": fact["report_period"],
                "statement_scope": fact["statement_scope"],
                "column_identity": fact["column_identity"],
                "cross_year_status": fact.get("cross_year_status", "unverified"),
            },
            "page_citation_check": {
                key: fact[key]
                for key in ("document_id", "raw_hash", "page_number", "quoted_label", "quoted_anchor", "source_url")
            },
            "review_status": "pending_human_review",
        })
    output = {
        "schema_version": "e4-m4-page-bound-assignments-v2",
        "data_kind": "runtime_only_audit",
        "assignments": assignments,
        "coverage_gaps": gaps,
        "counts": {"assigned": len(assignments), "unassigned": len(gaps)},
        "selection_policy": {"note_reference_rejected": True, "minimum_absolute_value": 1_000},
        "truth_boundary": {
            "assignments_are_not_completed_audits": True,
            "counts_as_numeric_page_audit": False,
            "counts_as_tier_a_or_b": False,
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(output["counts"]))


if __name__ == "__main__":
    main()
