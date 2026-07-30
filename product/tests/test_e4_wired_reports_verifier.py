import hashlib
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "product"))

from data_core.e4_judgment_review_queue import build_judgment_review_queue
from data_core.e4_judgment_wiring import wire_unreviewed_judgment_receipt
from report_contract import build_research_section_contract_v3
from tests.test_e4_judgment_wiring import receipt as judgment_receipt


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "verify_e4_wired_reports.py"
SPEC = importlib.util.spec_from_file_location("verify_e4_wired_reports", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


class WiredReportVerifierTest(unittest.TestCase):
    def _files(self, root: Path) -> tuple[Path, Path, Path, Path]:
        judgment = judgment_receipt()
        inputs = wire_unreviewed_judgment_receipt(judgment, ticker="300750.SZ")
        contract = build_research_section_contract_v3(inputs)
        sections = [
            {
                "section_id": item.section_id,
                "status": item.status.value,
                "status_reason": item.status_reason,
                "present_required": list(item.present_required),
                "missing_required": list(item.missing_required),
            }
            for item in contract.sections
        ]
        assessments = {item["section_id"]: item for item in sections}
        queue = build_judgment_review_queue(
            judgment,
            ticker="300750.SZ",
            section_assessments=assessments,
        )
        html = root / "report.html"
        count = len(queue["items"])
        html.write_text(f"数据时点：2025FY；含 {count} 项未审阅 AI 判断", encoding="utf-8")
        wiring = {
            "schema_version": "round7-m2-wiring-migration-v1",
            "rows": [
                {
                    "ticker": "300750.SZ",
                    "result": {"section_contract": {"sections": sections}},
                }
            ],
        }
        wiring["receipt_hash"] = MODULE.canonical_receipt_digest(wiring)
        report = {
            "schema_version": "round7-transitional-report-v1",
            "body_kind": "transitional_evidence_status_not_round7_chapter_dossier",
            "section_contract_schema_version": "research-section-contract-v3",
            "ticker": "300750.SZ",
            "html_path": str(html),
            "html_sha256": hashlib.sha256(html.read_bytes()).hexdigest(),
            "html_bytes": len(html.read_bytes()),
            "tier": "B",
            "tier_reasons": ["partial_or_missing_sections"],
            "input_hashes": {
                "m2": digest(wiring),
                "m3": digest(judgment),
            },
            "judgment_source_receipt_id": queue["source_receipt_id"],
            "unreviewed_judgment_count": count,
            "unreviewed_judgment_ids": list(judgment["content"]),
            "sections": sections,
        }
        report["receipt_hash"] = digest(report)
        paths = (
            root / "receipt.json",
            root / "queue.json",
            root / "judgment.json",
            root / "wiring.json",
        )
        for path, value in zip(paths, (report, queue, judgment, wiring)):
            path.write_text(json.dumps(value), encoding="utf-8")
        return paths

    def test_real_receipt_and_complete_pending_queue_pass(self):
        with TemporaryDirectory() as directory:
            receipt, queue, judgment, wiring = self._files(Path(directory))
            self.assertEqual(
                MODULE.summary(receipt, queue, judgment, wiring)["unreviewed_judgment_count"],
                10,
            )

    def test_fabricated_queue_body_fails_closed(self):
        with TemporaryDirectory() as directory:
            receipt, queue, judgment, wiring = self._files(Path(directory))
            value = json.loads(queue.read_text())
            value["items"][0]["body"] = {"text": "FABRICATED"}
            queue.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, "does not match"):
                MODULE.summary(receipt, queue, judgment, wiring)

    def test_tampered_report_receipt_fails_closed(self):
        with TemporaryDirectory() as directory:
            receipt, queue, judgment, wiring = self._files(Path(directory))
            value = json.loads(receipt.read_text())
            value["tier"] = "A"
            receipt.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                MODULE.summary(receipt, queue, judgment, wiring)

    def test_tampered_html_fails_closed(self):
        with TemporaryDirectory() as directory:
            receipt, queue, judgment, wiring = self._files(Path(directory))
            html = Path(json.loads(receipt.read_text())["html_path"])
            html.write_text("数据时点：2025FY；含 10 项未审阅 AI 判断；伪造报告")
            with self.assertRaisesRegex(ValueError, "HTML hash or size mismatch"):
                MODULE.summary(receipt, queue, judgment, wiring)

    def test_tampered_wiring_fails_closed(self):
        with TemporaryDirectory() as directory:
            receipt, queue, judgment, wiring = self._files(Path(directory))
            value = json.loads(wiring.read_text())
            value["rows"][0]["result"]["section_contract"]["sections"][0][
                "status"
            ] = "full"
            wiring.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, "wiring receipt identity"):
                MODULE.summary(receipt, queue, judgment, wiring)
