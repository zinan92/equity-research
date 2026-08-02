from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "product"))

from data_core.round7_evidence import classify_narrative_provenance  # noqa: E402
from v4_publication import _index, public_row_is_current  # noqa: E402
from v4_quality_gate import evaluate_round7_quality  # noqa: E402


class V4QualityGateTests(unittest.TestCase):
    def test_current_bank_is_blocked_for_self_report_leak_and_independence_gap(self) -> None:
        result = evaluate_round7_quality(
            dossier_path=ROOT / "artifacts/round7-dossiers/000001.SZ.receipt.json",
            require_canonical_root=True,
        )
        codes = {item["code"] for item in result["blockers"]}
        self.assertEqual(result["status"], "blocked")
        self.assertFalse(result["publication_eligible"])
        self.assertIn("issuer_self_report_leak", codes)
        self.assertIn("insufficient_independent_evidence", codes)
        self.assertGreater(result["self_report_leak_count"], 0)

    def test_legacy_mapped_artifact_cannot_pass_canonical_gate(self) -> None:
        result = evaluate_round7_quality(
            dossier_path=ROOT / "artifacts/v4-reports-legacy/000001.SZ/receipt.json",
            require_canonical_root=False,
        )
        self.assertEqual(result["status"], "blocked")
        self.assertFalse(result["publication_eligible"])
        self.assertTrue(any(item["code"] in {"canonical_structure_invalid", "v4_contract_invalid"} for item in result["blockers"]))

    def test_hash_tamper_is_a_publication_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for suffix in ("md", "html", "receipt.json"):
                shutil.copy2(ROOT / f"artifacts/round7-dossiers/000001.SZ.{suffix}", root / f"000001.SZ.{suffix}")
            (root / "000001.SZ.html").write_text((root / "000001.SZ.html").read_text(encoding="utf-8") + "tampered", encoding="utf-8")
            result = evaluate_round7_quality(dossier_path=root / "000001.SZ.receipt.json")
            self.assertIn("html_hash_mismatch", {item["code"] for item in result["blockers"]})

    def test_malformed_top_level_types_block_without_raising(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            receipt = json.loads((ROOT / "artifacts/round7-dossiers/000001.SZ.receipt.json").read_text(encoding="utf-8"))
            receipt["artifacts"] = []
            receipt["source_receipts"] = []
            receipt["degradation"] = []
            path = root / "000001.SZ.receipt.json"
            path.write_text(json.dumps(receipt), encoding="utf-8")
            result = evaluate_round7_quality(dossier_path=path)
            codes = {item["code"] for item in result["blockers"]}
            self.assertIn("artifacts_invalid", codes)
            self.assertIn("source_receipts_invalid", codes)
            self.assertIn("degradation_invalid", codes)

    def test_markdown_identity_swap_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for suffix in ("md", "html", "receipt.json"):
                shutil.copy2(ROOT / f"artifacts/round7-dossiers/000001.SZ.{suffix}", root / f"000001.SZ.{suffix}")
            markdown_path = root / "000001.SZ.md"
            markdown_path.write_text(markdown_path.read_text(encoding="utf-8").replace("ticker: 000001.SZ", "ticker: 300750.SZ", 1), encoding="utf-8")
            result = evaluate_round7_quality(dossier_path=root / "000001.SZ.receipt.json")
            self.assertIn("markdown_ticker_mismatch", {item["code"] for item in result["blockers"]})

    def test_retained_public_row_requires_current_gate_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            company = root / "000001.SZ"
            company.mkdir()
            report = company / "report.html"
            report.write_text("canonical", encoding="utf-8")
            gate = root / "000001.SZ.quality-gate.json"
            gate_payload = {
                "ticker": "000001.SZ",
                "status": "passed",
                "publication_eligible": True,
                "html_sha256": __import__("hashlib").sha256(report.read_bytes()).hexdigest(),
                "blockers": [],
            }
            gate_payload["receipt_hash"] = __import__("hashlib").sha256(json.dumps(gate_payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            gate.write_text(json.dumps(gate_payload), encoding="utf-8")
            row = {
                "ticker": "000001.SZ",
                "relative_html": "000001.SZ/report.html",
                "status": "passed",
                "publication_eligible": True,
                "html_sha256": __import__("hashlib").sha256(report.read_bytes()).hexdigest(),
                "quality_gate_path": "000001.SZ.quality-gate.json",
                "quality_gate_sha256": __import__("hashlib").sha256(gate.read_bytes()).hexdigest(),
            }
            self.assertTrue(public_row_is_current(row, output_root=root))
            report.write_text("tampered", encoding="utf-8")
            self.assertFalse(public_row_is_current(row, output_root=root))

    def test_classifier_catches_strategy_path_but_not_plain_period_fact(self) -> None:
        self.assertEqual(
            classify_narrative_provenance(
                "本行坚持零售战略定位不动摇，持续提升客户经营贡献。",
                "年报 > 1.3.1本行发展战略",
            )[0],
            True,
        )
        self.assertEqual(
            classify_narrative_provenance(
                "2026年第一季度利润总额为17,399。",
                "年报 > 3.1总体经营情况",
            )[0],
            False,
        )

    def test_index_is_fail_closed_for_pending_rows(self) -> None:
        html = _index([
            {"ticker": "PENDING", "relative_html": "PENDING/report.html", "publication_eligible": False},
            {"ticker": "READY", "relative_html": "READY/report.html", "publication_eligible": True, "status": "passed", "quality_gate_path": "READY.quality-gate.json", "quality_gate_sha256": "a" * 64, "quality_gate_verified": True, "reader_characters": 4200, "source_count": 2},
            {"ticker": "FAKE", "relative_html": "FAKE/report.html", "publication_eligible": True, "status": "passed"},
        ])
        self.assertNotIn("PENDING/report.html", html)
        self.assertIn("READY/report.html", html)
        self.assertNotIn("FAKE/report.html", html)


if __name__ == "__main__":
    unittest.main()
