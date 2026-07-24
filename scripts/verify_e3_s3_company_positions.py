#!/usr/bin/env python3
"""Run the explicit official-filing audit for E3-S3 company positions."""

from __future__ import annotations

import json
import sys
import argparse
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product"))
from data_core.company_positions import AUDIT_TARGETS, REVIEW_TARGETS, audit_positions, position_coverage  # noqa: E402


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument(
        "--limit", type=int, default=0,
        help="Number of explicit official-filing audits to run (default: 0; report the frozen review queue only).",
    )
    args = parser.parse_args()
    audited_targets = AUDIT_TARGETS[args.offset : args.offset + args.limit]
    # Strip frozen acceptance before a live re-audit. Otherwise an unavailable
    # upstream page could accidentally preserve yesterday's accepted citation.
    fresh_targets = tuple(replace(item, status="needs_evidence", citation=None) for item in audited_targets)
    audited = {item.ticker: item for item in audit_positions(fresh_targets)}
    positions = tuple(audited.get(item.ticker, item) for item in REVIEW_TARGETS)
    coverage = position_coverage(positions)
    frozen = {item.ticker: item for item in REVIEW_TARGETS}
    citation_mismatches = [
        item.ticker for item in audited.values()
        if frozen[item.ticker].status == "accepted" and item.citation != frozen[item.ticker].citation
    ]
    print(json.dumps({
        "schema_version": "e3-s3-company-position-audit-v1",
        "status": "passed" if coverage["total"] >= 50 and coverage["page_cited"] >= 30 and not citation_mismatches else "partial",
        "coverage": coverage,
        "citation_mismatches": sorted(citation_mismatches),
        "positions": [item.__dict__ for item in positions],
    }, ensure_ascii=False, sort_keys=True))
