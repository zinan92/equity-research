#!/usr/bin/env python3
"""Emit the focused E2-S4 official-filings/document-corpus acceptance receipt."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TESTS = (
    "product.tests.test_official_filing_ingest",
    "product.tests.test_document_intelligence",
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
    receipt = {
        "schema_version": "e2-s4-official-corpus-acceptance-v1",
        "status": "passed" if passed else "failed",
        "validation_scope": "fixture contract corpus; no fixture data promoted to authority",
        "discovery": "incremental known-document-ID skip path covered",
        "raw_identity": "official PDF, source URL, MIME, raw hash and storage receipt covered",
        "document_intelligence": {
            "page_mapping_threshold": 0.95,
            "ocr_coverage_threshold": 0.90,
            "fail_closed": "unreadable/OCR-failed pages remain gaps",
        },
        "citation": "document ID, page, raw hash, source URL and storage URI round-trip covered",
        "live_probe": {
            "status": "not_run",
            "reason": "network collection is explicit; no live upstream response is committed or represented by this receipt",
        },
        "tests": results,
    }
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(run())
