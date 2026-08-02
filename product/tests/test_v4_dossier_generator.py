from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "product"))

from v4_dossier_generator import GENERATOR_VERSION, generate_v4_dossier  # noqa: E402


class V4GeneratorTests(unittest.TestCase):
    def test_legacy_official_adapter_is_not_a_publishable_entrypoint(self) -> None:
        with self.assertRaisesRegex(ValueError, "legacy official adapter inputs are retired"):
            generate_v4_dossier(
                ticker="300750.SZ",
                output_dir=Path(tempfile.mkdtemp()),
                official_sample_path=ROOT / "docs/dossier-production/samples/300750.SZ-v1.md",
                narrative_receipt_path=ROOT / "artifacts/evidence/300750.SZ-official-narrative-evidence.json",
                financial_receipt_path=ROOT / "artifacts/evidence/300750.SZ-financial-page-evidence.json",
            )

    def test_completed_dossier_is_validated_as_a_whole(self) -> None:
        source = ROOT / "artifacts/round7-dossiers/300750.SZ.md"
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            markdown = temp_path / "complete.md"
            markdown.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
            manifest = temp_path / "manifest.json"
            manifest.write_text(json.dumps({"ticker": "300750.SZ", "source_urls": ["https://static.cninfo.com.cn/finalpage/example.PDF"]}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "completed_markdown_path is retired"):
                generate_v4_dossier(
                    ticker="300750.SZ",
                    output_dir=temp_path / "out",
                    completed_markdown_path=markdown,
                    evidence_manifest_path=manifest,
                )

    def test_requires_one_complete_input_shape(self) -> None:
        with self.assertRaisesRegex(ValueError, "provide canonical Round 7"):
            generate_v4_dossier(ticker="300750.SZ", output_dir=Path(tempfile.mkdtemp()))

    def test_no_field_generator_is_imported(self) -> None:
        source = (ROOT / "product" / "v4_dossier_generator.py").read_text(encoding="utf-8")
        for forbidden in ("e4_model_judgments", "legacy_judgment_materials", "investment_thesis"):
            self.assertNotIn(forbidden, source)

    def test_retirement_manifest_machine_check(self) -> None:
        from scripts.verify_v4_generator_retirement import verify

        result = verify(ROOT / "docs/evidence/v4-m4-generator-retirement.json")
        self.assertEqual(result["status"], "passed")


if __name__ == "__main__":
    unittest.main()
