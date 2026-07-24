#!/usr/bin/env python3
"""Validate disclosed score arithmetic against a local, read-only benchmark.

No benchmark row is checked into the repository. The emitted JSON is an audit
artifact chosen by the caller and may list residual tickers only at that local
path; it is not product data.
"""
from __future__ import annotations

import argparse
import json
import math
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
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
    )


def _empty_formula_counter() -> dict[str, int]:
    return {"rows": 0, "calculable": 0, "matched": 0, "missing_inputs": 0}


def _finalize_formula_counter(counter: dict[str, int]) -> dict[str, Any]:
    calculable = counter["calculable"]
    return {
        **counter,
        "match_rate": counter["matched"] / calculable if calculable else 0.0,
        "input_coverage": calculable / counter["rows"] if counter["rows"] else 0.0,
    }


def validate(scores_path: Path, levels_path: Path, levels_market_path: Path) -> dict[str, Any]:
    score_rows = _records(scores_path)
    by_universe: dict[str, dict[str, dict[str, int]]] = defaultdict(
        lambda: {"composite": _empty_formula_counter(), "opportunity": _empty_formula_counter()}
    )
    residuals = []
    for row in score_rows:
        universe = str(row.get("universe") or "unspecified")
        counters = by_universe[universe]
        counters["composite"]["rows"] += 1
        counters["opportunity"]["rows"] += 1
        score = row.get("s") if isinstance(row.get("s"), dict) else {}
        dims = {key: score.get(key) for key in ("growth", "quality", "value", "attention")}
        if all(_numeric(value) for value in dims.values()) and _numeric(score.get("composite")):
            counters["composite"]["calculable"] += 1
            observed = composite_score(**dims)
            if observed == score["composite"]:
                counters["composite"]["matched"] += 1
            else:
                residuals.append(
                    {
                        "universe": universe,
                        "code": row.get("code"),
                        "field": "composite",
                        "expected": score["composite"],
                        "observed": observed,
                    }
                )
        else:
            counters["composite"]["missing_inputs"] += 1
        opportunity_dims = {key: dims[key] for key in ("growth", "quality", "value")}
        if all(_numeric(value) for value in opportunity_dims.values()) and _numeric(row.get("opp")):
            counters["opportunity"]["calculable"] += 1
            observed = opportunity_score(**opportunity_dims)
            if observed == row["opp"]:
                counters["opportunity"]["matched"] += 1
            else:
                residuals.append(
                    {
                        "universe": universe,
                        "code": row.get("code"),
                        "field": "opportunity",
                        "expected": row["opp"],
                        "observed": observed,
                    }
                )
        else:
            counters["opportunity"]["missing_inputs"] += 1

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
    universe_validation = {
        universe: {
            name: _finalize_formula_counter(counter)
            for name, counter in counters.items()
        }
        for universe, counters in sorted(by_universe.items())
    }
    main_validation = universe_validation.get("main", {})
    main_composite_rate = main_validation.get("composite", {}).get("match_rate", 0.0)
    main_opportunity_rate = main_validation.get("opportunity", {}).get("match_rate", 0.0)
    peg_rate = peg_matches / peg_checked if peg_checked else 0.0
    return {
        "schema_version": "disclosed-scoring-validation-v2",
        "benchmark_counts": {
            "score_rows": len(score_rows),
            "main_universe_rows": sum(1 for row in score_rows if row.get("universe") == "main"),
            "levels_rows": len(levels),
            "levels_market_rows": len(market),
        },
        "formula_validation": {
            "by_universe": universe_validation,
            "peg_grade": {"checked": peg_checked, "matched": peg_matches, "match_rate": peg_rate},
        },
        "residuals": residuals,
        "grade_predictability": grade_assessment,
        "passed": (
            main_validation.get("composite", {}).get("rows") == 649
            and main_composite_rate >= 0.95
            and main_opportunity_rate >= 0.95
            and peg_rate >= 0.95
        ),
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
