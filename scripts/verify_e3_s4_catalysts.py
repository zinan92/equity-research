#!/usr/bin/env python3
"""Explicitly capture first-party sources and audit E3-S4 catalyst profiles."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product"))

from data_core.industry_catalysts import build_catalyst_profiles, catalyst_coverage  # noqa: E402
from data_core.industry_graph import audited_candidates, capture_official_evidence  # noqa: E402


if __name__ == "__main__":
    as_of = "2026-07-24"
    try:
        captures = capture_official_evidence(
            (item.evidence_url for item in audited_candidates()), fetched_at=as_of + "T00:00:00Z"
        )
    except ValueError as exc:
        print(json.dumps({
            "schema_version": "e3-s4-catalyst-audit-v1",
            "status": "partial",
            "coverage": {"total": 108, "available": 0, "missing_evidence": 108, "fact_sections": 0},
            "captures": [], "fact_profile_ids": [], "source_gap": str(exc),
        }, ensure_ascii=False, sort_keys=True))
        raise SystemExit(0)
    profiles = build_catalyst_profiles(captures, as_of=as_of)
    coverage = catalyst_coverage(profiles)
    print(json.dumps({
        "schema_version": "e3-s4-catalyst-audit-v1",
        "status": "passed" if coverage["total"] == 108 and coverage["available"] >= 20 else "partial",
        "coverage": coverage,
        "captures": [item.__dict__ for item in captures],
        "fact_profile_ids": [item.profile_id for item in profiles if item.status == "available"],
    }, ensure_ascii=False, sort_keys=True))
