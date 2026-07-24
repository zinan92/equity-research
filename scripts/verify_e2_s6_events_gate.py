#!/usr/bin/env python3
"""Emit the focused E2-S6 event-intelligence/evidence-gate acceptance receipt."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TESTS = ("product/tests/test_event_intelligence.py", "product/tests/test_evidence_gate.py")


def run() -> int:
    results = []
    for test in TESTS:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", test],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        results.append({"test": test, "returncode": result.returncode})
    passed = all(result["returncode"] == 0 for result in results)
    print(json.dumps({
        "schema_version": "e2-s6-events-gate-acceptance-v1",
        "status": "passed" if passed else "failed",
        "validation_scope": "fixture contract corpus; no news item or inference is promoted by this receipt",
        "events": "explicit entity resolution, cross-source provenance-preserving dedupe and source-failure gaps covered",
        "evidence_gate": "accepted-only context packs, PIT/freshness/conflict coverage tiers and tamper rejection covered",
        "tests": results,
    }, ensure_ascii=False, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(run())
