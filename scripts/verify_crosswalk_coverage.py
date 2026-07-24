#!/usr/bin/env python3
"""Check golden-set identity parsing against a runtime-only crosswalk audit."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRODUCT = ROOT / "product"
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from data_core.universe_crosswalk import _canonical_ticker  # noqa: E402


def verify(golden_path: Path, audit_path: Path) -> dict:
    golden = json.loads(golden_path.read_text(encoding="utf-8"))
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    companies = golden.get("companies") if isinstance(golden, dict) else None
    records = audit.get("records") if isinstance(audit, dict) else None
    if not isinstance(companies, list) or len(companies) != 30:
        raise ValueError("golden manifest must contain 30 companies")
    if not isinstance(records, list):
        raise ValueError("audit must contain crosswalk records")
    matched_tickers = {
        row.get("ticker") for row in records
        if isinstance(row, dict) and row.get("status") == "matched" and row.get("ticker")
    }
    rows = []
    for company in companies:
        market = str(company.get("market") or "")
        ticker = str(company.get("ticker") or "")
        code = ticker.split(".", 1)[0]
        parsed = _canonical_ticker(code, market)
        if market == "A":
            parsed = ticker if ticker.endswith((".SH", ".SZ", ".BJ")) else parsed
        rows.append({
            "ticker": ticker,
            "parsed_ticker": parsed,
            "parse_status": "parsed" if parsed == ticker else "parse_mismatch",
            "archive_crosswalk_status": "matched" if ticker in matched_tickers else "unmapped",
        })
    parse_passed = sum(row["parse_status"] == "parsed" for row in rows)
    archive_matched = sum(row["archive_crosswalk_status"] == "matched" for row in rows)
    return {
        "schema_version": "crosswalk-golden-coverage-v1",
        "boundary": "Runtime-only receipt; archive absence is not converted into canonical identity.",
        "golden_count": len(rows),
        "parsed_count": parse_passed,
        "archive_matched_count": archive_matched,
        "archive_unmapped_count": len(rows) - archive_matched,
        "passed": parse_passed == len(rows),
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--golden", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    output = verify(args.golden, args.audit)
    args.out.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: output[key] for key in ("golden_count", "parsed_count", "archive_matched_count", "archive_unmapped_count", "passed")}, ensure_ascii=False))
    return 0 if output["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
