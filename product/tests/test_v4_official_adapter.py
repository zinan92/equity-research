from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "product"))

from data_core.round7_evidence import canonical_hash  # noqa: E402
from v4_official_adapter import adapt_official_sample, adapt_round7_dossier, write_official_outputs  # noqa: E402


class V4OfficialAdapterTests(unittest.TestCase):
    def test_legacy_official_sample_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "legacy official sample adapter is retired"):
            adapt_official_sample(
                ticker="300750.SZ",
                sample_path=ROOT / "docs/dossier-production/samples/300750.SZ-v1.md",
                narrative_receipt_path=ROOT / "artifacts/evidence/300750.SZ-official-narrative-evidence.json",
                financial_receipt_path=ROOT / "artifacts/evidence/300750.SZ-financial-page-evidence.json",
            )

    def test_fixture_input_is_rejected(self) -> None:
        source = ROOT / "docs/dossier-production/samples/300750.SZ-v1.md"
        text = source.read_text(encoding="utf-8") + "\nfixture\n"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.md"
            path.write_text(text, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "legacy official sample adapter is retired"):
                adapt_official_sample(
                    ticker="300750.SZ",
                    sample_path=path,
                    narrative_receipt_path=ROOT / "artifacts/evidence/300750.SZ-official-narrative-evidence.json",
                    financial_receipt_path=ROOT / "artifacts/evidence/300750.SZ-financial-page-evidence.json",
                )

    def test_human_reviewed_round7_dossier_remains_packagable(self) -> None:
        source = ROOT / "artifacts/round7-dossiers/300750.SZ.receipt.json"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dossier = json.loads(source.read_text(encoding="utf-8"))
            dossier["review_status"] = "human_reviewed"
            dossier["production_record"]["human_review_status"] = "human_reviewed"
            for chapter in dossier["chapters"]:
                chapter["review_status"] = "human_reviewed"
            dossier["content_hash"] = canonical_hash({
                key: value for key, value in dossier.items()
                if key not in {"content_hash", "artifacts", "receipt_hash"}
            })
            dossier_path = root / "300750.SZ.receipt.json"
            markdown_path = root / "300750.SZ.md"
            dossier_path.write_text(json.dumps(dossier, ensure_ascii=False), encoding="utf-8")
            markdown_path.write_text(
                (ROOT / "artifacts/round7-dossiers/300750.SZ.md").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            text, record = adapt_round7_dossier(
                ticker="300750.SZ",
                dossier_path=dossier_path,
                markdown_path=markdown_path,
            )
            self.assertEqual(record["status"], "human_reviewed")
            self.assertIn("财务与经营时间序列", text)


if __name__ == "__main__":
    unittest.main()
