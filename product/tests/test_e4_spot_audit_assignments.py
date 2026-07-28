from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

PRODUCT = Path(__file__).resolve().parents[1]
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from data_core.contracts import digest  # noqa: E402
from data_core.e4_spot_audit_assignments import compile_spot_audit_assignments, render_spot_audit_guide, write_spot_audit_assignments  # noqa: E402


def page_facts(count: int = 3) -> dict:
    rows = []
    for index in range(count):
        rows.append({"ticker": f"{index + 1:06d}.SZ", "status": "available", "fact": {
            "ticker": f"{index + 1:06d}.SZ", "metric": "revenue", "value": index + 1.0,
            "document_id": f"official:{index}", "raw_hash": f"{index + 10:064x}", "page_number": 7,
            "quoted_label": "营业收入", "quoted_anchor": "营业收入 1", "report_period": "2024年度",
            "statement_scope": "consolidated", "unit": "元", "currency": "CNY", "source_url": "https://example.com/report.pdf",
        }})
    value = {"schema_version": "e4-page-level-filing-facts-v1", "data_kind": "real", "truth_boundary": {"page_bound_primary_facts_only": True}, "facts": rows}
    value["receipt_hash"] = digest(value)
    return value


class SpotAuditAssignmentsTest(unittest.TestCase):
    def write(self, root: Path, value: dict) -> Path:
        path = root / "facts.json"; path.write_text(json.dumps(value), encoding="utf-8"); return path

    def test_binds_numeric_and_page_to_the_same_filing_fact_without_credit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self.write(Path(directory), page_facts())
            first = compile_spot_audit_assignments(path); second = compile_spot_audit_assignments(path)
        self.assertEqual(first["receipt_hash"], second["receipt_hash"])
        assignment = first["assignments"][0]
        self.assertEqual(first["counts"], {"assigned": 3, "pending_human_review": 3, "completed": 0})
        self.assertEqual(assignment["document_identity"]["document_id"], assignment["page_citation_check"]["document_id"])
        self.assertEqual(assignment["numeric_check"]["metric"], "revenue")
        self.assertFalse(first["truth_boundary"]["counts_as_numeric_page_audit"])

    def test_rejects_quote_only_or_tampered_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); value = page_facts(1); value["facts"][0]["fact"].pop("page_number")
            value["receipt_hash"] = digest({key: item for key, item in value.items() if key != "receipt_hash"})
            with self.assertRaisesRegex(ValueError, "page-bound"):
                compile_spot_audit_assignments(self.write(root, value))
            value = page_facts(1); value["facts"][0]["fact"]["raw_hash"] = "bad"
            with self.assertRaisesRegex(ValueError, "page-bound"):
                compile_spot_audit_assignments(self.write(root, value))

    def test_writes_human_readable_guide(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); result = write_spot_audit_assignments(self.write(root, page_facts()), root)
            guide = Path(result["guide_path"]).read_text(encoding="utf-8")
        self.assertIn("not an audit result", guide)
        self.assertIn("000001.SZ", guide)
        self.assertIn("page 7", guide)


if __name__ == "__main__":
    unittest.main()
