#!/usr/bin/env python3
"""Verify the N1/M1 30-company acceptance manifest without benchmark data."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


REQUIRED_MARKETS = {"A", "HK", "US", "JP"}
REQUIRED_FIELDS = ("price", "change_pct", "revenue_growth")


def verify_manifest(path: Path, root: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    problems: list[str] = []
    companies = data.get("companies")
    if not isinstance(companies, list) or len(companies) != 30:
        problems.append("manifest must contain exactly 30 companies")
        companies = companies if isinstance(companies, list) else []

    tickers = [row.get("ticker") for row in companies if isinstance(row, dict)]
    if len(tickers) != len(set(tickers)):
        problems.append("ticker identifiers must be unique")
    for row in companies:
        if not isinstance(row, dict) or any(not isinstance(row.get(key), str) or not row[key].strip() for key in ("ticker", "name", "market", "sector", "reason")):
            problems.append("each company requires ticker, name, market, sector and reason")
            break

    markets = Counter(row.get("market") for row in companies if isinstance(row, dict))
    sectors = Counter(row.get("sector") for row in companies if isinstance(row, dict))
    for market in REQUIRED_MARKETS:
        if markets[market] < 3:
            problems.append(f"market {market} has fewer than 3 companies")
    for sector, count in sectors.items():
        if count < 3:
            problems.append(f"sector {sector} has fewer than 3 companies")
    if len(sectors) < 6:
        problems.append("manifest must cover at least six sectors")

    matrix = data.get("field_matrix") if isinstance(data.get("field_matrix"), dict) else {}
    recipes = data.get("regeneration_recipes") if isinstance(data.get("regeneration_recipes"), dict) else {}
    high_medium = 0
    total_cells = 0
    gap_cells: list[str] = []
    for row in companies:
        if not isinstance(row, dict):
            continue
        for field in REQUIRED_FIELDS:
            definition = matrix.get(field, {}).get(row.get("market")) if isinstance(matrix.get(field), dict) else None
            total_cells += 1
            if not isinstance(definition, dict):
                problems.append(f"missing field matrix for {field}/{row.get('market')}")
                continue
            confidence = definition.get("confidence")
            recipe = definition.get("recipe")
            if confidence in {"high", "medium"}:
                high_medium += 1
                recipe_data = recipes.get(recipe)
                evidence = recipe_data.get("evidence") if isinstance(recipe_data, dict) else None
                if not isinstance(evidence, str) or not (root / evidence).is_file():
                    problems.append(f"attributed {field}/{row.get('market')} lacks a local regeneration evidence file")
            elif confidence == "gap":
                gap_cells.append(f"{row.get('ticker')}:{field}")
            else:
                problems.append(f"invalid confidence for {field}/{row.get('market')}")

    coverage = high_medium / total_cells if total_cells else 0.0
    if coverage < 0.80:
        problems.append(f"high/medium field coverage {coverage:.2%} is below 80%")
    refs = data.get("evidence_refs") if isinstance(data.get("evidence_refs"), dict) else {}
    for name, reference in refs.items():
        if not isinstance(reference, str) or not (root / reference).is_file():
            problems.append(f"evidence reference {name} is missing")
    return {
        "schema_version": "m1-acceptance-verification-v1",
        "passed": not problems,
        "company_count": len(companies),
        "markets": dict(sorted(markets.items())),
        "sectors": dict(sorted(sectors.items())),
        "field_cells": total_cells,
        "high_medium_cells": high_medium,
        "high_medium_coverage": coverage,
        "explicit_gap_cells": gap_cells,
        "problems": problems,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    report = verify_manifest(args.manifest, root)
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.write_text(serialized, encoding="utf-8")
    else:
        print(serialized, end="")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
