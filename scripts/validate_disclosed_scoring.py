#!/usr/bin/env python3
"""Validate disclosed score arithmetic against a local, read-only benchmark.

No benchmark row is checked into the repository. The emitted JSON is an audit
artifact chosen by the caller and may list residual tickers only at that local
path; it is not product data.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PRODUCT = ROOT / "product"
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from data_core import composite_score, opportunity_score, peg_grade  # noqa: E402


def _records(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    records = value.get("records") if isinstance(value, dict) else None
    if not isinstance(records, list):
        raise ValueError(f"{path} must contain an object with records")
    return [item for item in records if isinstance(item, dict)]


def _numeric(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float))


def validate(scores_path: Path, levels_path: Path, levels_market_path: Path) -> dict[str, Any]:
    score_rows = _records(scores_path)
    composite_checked = 0
    composite_matches = 0
    opportunity_checked = 0
    opportunity_matches = 0
    residuals = []
    for row in score_rows:
        score = row.get("s") if isinstance(row.get("s"), dict) else {}
        dims = {key: score.get(key) for key in ("growth", "quality", "value", "attention")}
        if all(_numeric(value) for value in dims.values()) and _numeric(score.get("composite")):
            composite_checked += 1
            observed = composite_score(**dims)
            if observed == score["composite"]:
                composite_matches += 1
            else:
                residuals.append({"code": row.get("code"), "field": "composite", "expected": score["composite"], "observed": observed})
        opportunity_dims = {key: dims[key] for key in ("growth", "quality", "value")}
        if all(_numeric(value) for value in opportunity_dims.values()) and _numeric(row.get("opp")):
            opportunity_checked += 1
            observed = opportunity_score(**opportunity_dims)
            if observed == row["opp"]:
                opportunity_matches += 1
            else:
                residuals.append({"code": row.get("code"), "field": "opportunity", "expected": row["opp"], "observed": observed})

    levels = _records(levels_path)
    market = {str(row.get("code")): row for row in _records(levels_market_path)}
    peg_checked = 0
    peg_matches = 0
    for row in levels:
        expected = row.get("peg_grade")
        quote = market.get(str(row.get("code")))
        if expected in (None, "", "—") or not quote or not _numeric(quote.get("peg")):
            continue
        peg_checked += 1
        observed = peg_grade(quote["peg"])
        if observed == expected:
            peg_matches += 1
        else:
            residuals.append({"code": row.get("code"), "field": "peg_grade", "expected": expected, "observed": observed})

    grades_by_score: dict[float, set[str]] = defaultdict(set)
    missing_inputs = {"barrier": 0, "gross_margin": 0, "net_margin": 0, "rack_verdict": 0}
    for row in levels:
        grades_by_score[float(row.get("score", 0))].add(str(row.get("grade")))
        for field in missing_inputs:
            if row.get(field) in (None, ""):
                missing_inputs[field] += 1
    ambiguous_score_values = sorted(score for score, grades in grades_by_score.items() if len(grades) > 1)
    grade_assessment = {
        "status": "manual_judgment_not_formulaically_reproducible",
        "reason": "Same visible score maps to multiple grades and most rows omit the disclosed qualitative inputs; a threshold fit would be tautological or misleading.",
        "score_values_with_multiple_grades": len(ambiguous_score_values),
        "total_distinct_score_values": len(grades_by_score),
        "missing_input_counts": missing_inputs,
    }
    composite_rate = composite_matches / composite_checked if composite_checked else 0.0
    opportunity_rate = opportunity_matches / opportunity_checked if opportunity_checked else 0.0
    peg_rate = peg_matches / peg_checked if peg_checked else 0.0
    return {
        "schema_version": "disclosed-scoring-validation-v1",
        "formula_validation": {
            "composite": {"checked": composite_checked, "matched": composite_matches, "match_rate": composite_rate},
            "opportunity": {"checked": opportunity_checked, "matched": opportunity_matches, "match_rate": opportunity_rate},
            "peg_grade": {"checked": peg_checked, "matched": peg_matches, "match_rate": peg_rate},
        },
        "residuals": residuals,
        "grade_predictability": grade_assessment,
        "passed": composite_rate >= 0.95 and opportunity_rate >= 0.95 and peg_rate >= 0.95,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scores", required=True, type=Path)
    parser.add_argument("--levels", required=True, type=Path)
    parser.add_argument("--levels-market", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    report = validate(args.scores, args.levels, args.levels_market)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(args.out)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
