#!/usr/bin/env python3
"""Emit the focused E2-S5 sell-side evidence and consensus acceptance receipt."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TESTS = (
    "product.tests.test_sell_side_archive",
    "product.tests.test_consensus_history",
    "product.tests.test_viewpoint_matrix",
)


def run() -> int:
    results = []
    for test in TESTS:
        completed = subprocess.run(
            [sys.executable, "-m", "unittest", "-q", test],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        results.append({"test": test, "returncode": completed.returncode})
    passed = all(item["returncode"] == 0 for item in results)
    print(json.dumps({
        "schema_version": "e2-s5-sell-side-acceptance-v1",
        "status": "passed" if passed else "failed",
        "validation_scope": "fixture contract corpus; no report body or provider response is published by this receipt",
        "archive": "catalog metadata, canonical PDF URL, raw-hash dedupe, unavailable-PDF metadata-only and source failure paths covered",
        "estimates": "report/broker/date/fiscal-year provenance, PIT filtering, stale/outlier quarantine and deterministic replay covered",
        "viewpoints": "document/page/raw-bound claims, disagreement language and evidence-strength caps covered",
        "live_probe": {"status": "not_run", "reason": "external collection remains explicit and its raw output is never committed"},
        "tests": results,
    }, ensure_ascii=False, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(run())
