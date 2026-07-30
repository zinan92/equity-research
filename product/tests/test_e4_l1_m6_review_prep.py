from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("l1_m6", ROOT / "scripts" / "verify_e4_l1_m6_review_prep.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC); sys.modules[SPEC.name] = MODULE; SPEC.loader.exec_module(MODULE)


class L1M6ReviewPrepTest(unittest.TestCase):
    def test_stale_legacy_is_not_counted_and_current_lineage_is_required(self) -> None:
        queue = {"data_kind": "real", "source_receipt_id": "r", "items": [{"judgment_id": "risk_register", "impact_rank": 2, "section_id": "core_risks", "review_status": "pending_human_review", "citations": [{"page_number": 8, "pdf_page_url": "https://official/a.pdf#page=8"}], "would_promote_section_to_full": False}]}
        assignment = {"ticker": "300750.SZ", "page_citation_check": {"document_id": "d1", "raw_hash": "a"}}
        stale = {"ticker": "600519.SH", "page_citation_check": {"document_id": "old", "raw_hash": "b"}}
        sequence = {"receipt_hash": "sequence", "tickers": [{"ticker": "300750.SZ", "reports": [{"document": {"document_id": "d1", "raw_hash": "a"}}]}]}
        result = MODULE.build_verification(queue, {"assignments": [assignment, stale]}, {"assignments": [assignment], "coverage_gaps": []}, sequence)
        self.assertEqual(result["spot_audit_freshness"]["legacy_still_lineage_valid"], ["300750.SZ"])
        self.assertEqual(result["spot_audit_freshness"]["legacy_stale_requires_recovery"], ["600519.SH"])
        self.assertTrue(result["truth_boundary"]["no_issue_218_claim"])
