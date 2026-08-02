from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "product"))

from v4_official_adapter import adapt_official_sample, write_official_outputs  # noqa: E402


class V4OfficialAdapterTests(unittest.TestCase):
    def test_catl_and_moutai_bind_only_official_receipts(self) -> None:
        rows = {}
        for ticker in ("300750.SZ", "600519.SH"):
            rows[ticker] = adapt_official_sample(
                ticker=ticker,
                sample_path=ROOT / "docs/dossier-production/samples" / f"{ticker}-v1.md",
                narrative_receipt_path=ROOT / "artifacts/evidence" / f"{ticker}-official-narrative-evidence.json",
                financial_receipt_path=ROOT / "artifacts/evidence" / f"{ticker}-financial-page-evidence.json",
            )
        with tempfile.TemporaryDirectory() as tmp:
            receipt = write_official_outputs(rows, Path(tmp))
            self.assertEqual(receipt["status"], "passed")
            self.assertEqual(receipt["fresh_model_calls"], 0)
            self.assertEqual(receipt["new_official_documents"], 0)
            for row in receipt["companies"]:
                text = Path(row["output_path"]).read_text(encoding="utf-8")
                self.assertEqual(row["validation"], "passed")
                self.assertIn("pending_human_review", text)
                self.assertNotIn("东财F10", text)
                self.assertTrue(all("cninfo.com.cn" in url for url in row["source_urls"]))

    def test_fixture_input_is_rejected(self) -> None:
        source = ROOT / "docs/dossier-production/samples/300750.SZ-v1.md"
        text = source.read_text(encoding="utf-8") + "\nfixture\n"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.md"
            path.write_text(text, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "fixture"):
                adapt_official_sample(
                    ticker="300750.SZ",
                    sample_path=path,
                    narrative_receipt_path=ROOT / "artifacts/evidence/300750.SZ-official-narrative-evidence.json",
                    financial_receipt_path=ROOT / "artifacts/evidence/300750.SZ-financial-page-evidence.json",
                )


if __name__ == "__main__":
    unittest.main()
