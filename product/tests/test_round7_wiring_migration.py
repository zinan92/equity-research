from __future__ import annotations

import copy
import importlib.util
import unittest
from pathlib import Path

from tests.test_e4_judgment_wiring import receipt as judgment_receipt


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "migrate_e4_wiring_to_round7.py"
SPEC = importlib.util.spec_from_file_location("migrate_e4_wiring_to_round7", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def fact() -> dict:
    return {
        "ticker": "300750.SZ",
        "metric": "revenue",
        "value": 1,
        "document_id": "official-filing:cninfo:1",
        "raw_hash": "a" * 64,
        "page_number": 8,
        "quoted_label": "营业收入",
        "quoted_anchor": "营业收入 1",
        "report_period": "2025FY",
        "statement_scope": "consolidated",
        "unit": "元",
        "currency": "CNY",
        "source_url": "https://static.cninfo.com.cn/a.pdf",
    }


def legacy_receipt() -> dict:
    value = {
        "schema_version": "e4-m2-research-wiring-v1",
        "rows": [
            {
                "ticker": "300750.SZ",
                "status": "available",
                "input_receipts": {"financial_sequences_sha256": "sequence"},
                "result": {
                    "page_facts": [fact()],
                    "section_contract": {
                        "sections": [
                            {"section_id": "executive_summary", "status": "full"}
                        ]
                    },
                },
            }
        ],
    }
    value["receipt_hash"] = MODULE._legacy_receipt_hash(value)
    return value


class Round7WiringMigrationTest(unittest.TestCase):
    def migrate(self, legacy: dict) -> dict:
        return MODULE.migrate(
            legacy,
            legacy_file_sha256=MODULE.LEGACY_WIRING_FILE_SHA256,
            judgments={"300750.SZ": judgment_receipt()},
            governance={},
        )

    def test_reassesses_real_values_without_copying_old_status(self) -> None:
        output = self.migrate(legacy_receipt())
        row = output["rows"][0]
        sections = {
            item["section_id"]: item
            for item in row["result"]["section_contract"]["sections"]
        }
        self.assertEqual(len(sections), 9)
        self.assertNotIn("executive_summary", sections)
        self.assertEqual(
            sections["financials_and_valuation"]["status"],
            "partial",
        )
        self.assertEqual(
            sections["one_line_positioning"]["status_reason"],
            "pending_judgment_review",
        )
        self.assertEqual(row["result"]["degradation"]["tier"], "B")
        self.assertFalse(
            output["truth_boundary"]["old_section_statuses_carried_forward"]
        )

    def test_tampered_parent_receipt_or_file_identity_is_rejected(self) -> None:
        tampered = legacy_receipt()
        tampered["receipt_hash"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "receipt hash mismatch"):
            self.migrate(tampered)
        with self.assertRaisesRegex(ValueError, "file identity mismatch"):
            MODULE.migrate(
                legacy_receipt(),
                legacy_file_sha256="0" * 64,
                judgments={"300750.SZ": judgment_receipt()},
                governance={},
            )

    def test_nonofficial_page_fact_is_rejected(self) -> None:
        tampered = copy.deepcopy(legacy_receipt())
        page_fact = tampered["rows"][0]["result"]["page_facts"][0]
        page_fact["source_url"] = "https://evil.example/fake.pdf"
        tampered["receipt_hash"] = MODULE._legacy_receipt_hash(tampered)
        with self.assertRaisesRegex(ValueError, "not official filing evidence"):
            self.migrate(tampered)


if __name__ == "__main__":
    unittest.main()
