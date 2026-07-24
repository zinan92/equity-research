from __future__ import annotations

import sys
import unittest
from pathlib import Path

PRODUCT = Path(__file__).resolve().parents[1]
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from data_core.industry_graph import EvidenceCapture, audited_candidates  # noqa: E402
from data_core.n3_dossier_batch import N3_DOSSIER_BATCH_SCHEMA_VERSION, selected_positions  # noqa: E402
from data_core.n3_financial_delivery import N3_FINANCIAL_DELIVERY_SCHEMA_VERSION  # noqa: E402
from data_core.n3_falsifier_evidence import N3_FALSIFIER_EVIDENCE_SCHEMA_VERSION  # noqa: E402
from data_core.r2_acceptance import audit_r2  # noqa: E402


class R2AcceptanceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[2]
        self.captures = tuple(
            EvidenceCapture(url, (str(index + 1) * 64)[:64], "2026-07-24T00:00:00Z")
            for index, url in enumerate(sorted({item.evidence_url for item in audited_candidates()}))
        )
        self.receipt = {
            "schema_version": N3_DOSSIER_BATCH_SCHEMA_VERSION,
            "counts": {"requested": 20, "compiled": 20, "failed": 0, "no_action": 20},
            "rows": [{"ticker": item.ticker, "status": "compiled"} for item in selected_positions()],
        }

    def test_count_success_cannot_pass_without_all_five_company_questions(self) -> None:
        audit = audit_r2(self.receipt, self.captures, repository_root=self.root)
        self.assertEqual(audit["status"], "partial")
        self.assertTrue(audit["gates"]["ontology"])
        self.assertTrue(audit["gates"]["dossiers"])
        self.assertFalse(audit["gates"]["five_questions"])
        self.assertEqual(audit["five_questions"]["layer"]["covered"], 20)
        self.assertEqual(audit["five_questions"]["moat"]["covered"], 0)

    def test_archive_isolation_is_a_required_gate(self) -> None:
        audit = audit_r2(self.receipt, self.captures, repository_root=self.root)
        self.assertTrue(audit["archive_isolation"]["passed"])
        self.assertEqual(audit["archive_isolation"]["offenders"], [])

    def test_invalid_dossier_receipt_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires N3-S5"):
            audit_r2({"schema_version": "wrong"}, self.captures, repository_root=self.root)

    def test_financial_delivery_raises_only_that_question(self) -> None:
        financial = {
            "schema_version": N3_FINANCIAL_DELIVERY_SCHEMA_VERSION,
            "selection_identity": self.receipt.get("selection_identity"),
            "tickers": [{"ticker": item.ticker, "financial_delivery_available": True} for item in selected_positions()],
        }
        # Keep the same explicit identity used by the supplied dossier receipt.
        self.receipt["selection_identity"] = financial["selection_identity"] = "selection"
        audit = audit_r2(self.receipt, self.captures, repository_root=self.root, financial_delivery_receipt=financial)
        self.assertEqual(audit["five_questions"]["financial_delivery"]["covered"], 20)
        self.assertFalse(audit["gates"]["five_questions"])

    def test_source_bound_falsifier_receipt_raises_only_that_question(self) -> None:
        self.receipt["selection_identity"] = "selection"
        falsifier = {
            "schema_version": N3_FALSIFIER_EVIDENCE_SCHEMA_VERSION,
            "selection_identity": "selection",
            "rows": [
                {
                    "ticker": item.ticker,
                    "status": "accepted",
                    "evidence": {
                        "ticker": item.ticker,
                        "evidence_id": "falsifier:" + "a" * 40,
                        "source_url": "https://static.cninfo.com.cn/finalpage/fixture.pdf",
                        "raw_hash": "b" * 64,
                        "page_number": 1,
                        "known_at": "2026-07-25T00:00:00Z",
                        "observed_condition": "Issuer disclosed an observable risk condition.",
                    },
                }
                for item in selected_positions()
            ],
        }
        audit = audit_r2(
            self.receipt, self.captures, repository_root=self.root,
            falsifier_evidence_receipt=falsifier,
        )
        self.assertEqual(audit["five_questions"]["falsifier"]["covered"], 20)
        self.assertFalse(audit["gates"]["five_questions"])


if __name__ == "__main__":
    unittest.main()
