#!/usr/bin/env python3
"""Evaluate R2 against a real N3-S5 runtime receipt."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product"))

from data_core.industry_graph import audited_candidates, capture_official_evidence  # noqa: E402
from data_core.r2_acceptance import audit_r2  # noqa: E402


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("batch_receipt", type=Path)
    args = parser.parse_args()
    captures = capture_official_evidence(
        (item.evidence_url for item in audited_candidates()), fetched_at="2026-07-24T00:00:00Z"
    )
    receipt = json.loads(args.batch_receipt.read_text(encoding="utf-8"))
    print(json.dumps(audit_r2(receipt, captures, repository_root=ROOT), ensure_ascii=False, sort_keys=True, indent=2))
