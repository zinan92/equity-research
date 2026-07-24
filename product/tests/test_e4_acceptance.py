from __future__ import annotations

import sys
import unittest
from pathlib import Path


PRODUCT = Path(__file__).resolve().parents[1]
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from data_core.e4_acceptance import evaluate_e4_s4  # noqa: E402


def master(count: int = 100, *, data_kind: str = "real") -> dict:
    return {
        "schema_version": "ashare-security-master-v1", "data_kind": data_kind,
        "receipt_hash": "a" * 64, "truth_boundary": {"identity_only": True},
        "records": [{"ticker": f"{index:06d}.SZ"} for index in range(1, count + 1)],
    }


def coverage(count: int = 100) -> dict:
    return {
        f"{index:06d}.SZ": {
            "data_kind": "real", "report_model_hash": f"{index:064x}", "tier": "A" if index % 2 else "B",
            "numeric_spot_audit": index <= 20, "page_citation_spot_audit": index <= 20,
        }
        for index in range(1, count + 1)
    }


class E4AcceptanceTest(unittest.TestCase):
    def test_full_contract_fixture_passes_and_replays_deterministically(self) -> None:
        first = evaluate_e4_s4(master(), coverage_rows=coverage())
        second = evaluate_e4_s4(master(), coverage_rows=coverage())
        self.assertEqual((first["status"], first["counts"]), ("passed", {"identity": 100, "report_models": 100, "tier_a_or_b": 100, "spot_audits": 20}))
        self.assertEqual(first["receipt_hash"], second["receipt_hash"])

    def test_missing_evidence_is_a_failed_baseline_with_per_ticker_reasons(self) -> None:
        receipt = evaluate_e4_s4(master())
        self.assertEqual(receipt["status"], "failed")
        self.assertEqual(receipt["counts"], {"identity": 100, "report_models": 0, "tier_a_or_b": 0, "spot_audits": 0})
        self.assertEqual(len(receipt["failure_taxonomy"]), 100)
        self.assertEqual(receipt["failure_taxonomy"]["000001.SZ"], ["missing_canonical_evidence"])

    def test_non_real_and_duplicate_identity_corpora_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "non-real"):
            evaluate_e4_s4(master(data_kind="fixture"))
        duplicate = master()
        duplicate["records"][1]["ticker"] = duplicate["records"][0]["ticker"]
        with self.assertRaisesRegex(ValueError, "duplicated"):
            evaluate_e4_s4(duplicate)


if __name__ == "__main__":
    unittest.main()
