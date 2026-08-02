from __future__ import annotations

import json
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "product"))

from v4_publication import build_v4_publication, render_v4_html  # noqa: E402


class V4PublicationTests(unittest.TestCase):
    def test_render_preserves_review_boundary_and_sources(self) -> None:
        source = (ROOT / "docs/evidence/v4-m3-official/300750.SZ.md").read_text(encoding="utf-8")
        rendered = render_v4_html(source, title="CATL V4")
        self.assertIn("含未审阅研究判断", rendered)
        self.assertIn("static.cninfo.com.cn", rendered)
        self.assertIn("财务与估值", rendered)

    def test_build_two_persistent_reports(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            result = build_v4_publication(
                source_root=ROOT / "docs/evidence/v4-m3-official",
                output_root=Path(temp),
            )
            self.assertEqual(result["status"], "passed")
            self.assertEqual(len(result["companies"]), 2)
            self.assertTrue(Path(result["index_path"]).is_file())
            for row in result["companies"]:
                self.assertTrue(Path(row["html_path"]).is_file())
                self.assertEqual(row["status"], "pending_human_review")
                self.assertEqual(row["tier_credit"], "none")
                source = ROOT / "docs/evidence/v4-m3-official" / f"{row['ticker']}.md"
                self.assertEqual(row["markdown_sha256"], hashlib.sha256(source.read_bytes()).hexdigest())

    def test_publication_receipt_is_machine_readable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            build_v4_publication(source_root=ROOT / "docs/evidence/v4-m3-official", output_root=Path(temp))
            receipt = json.loads((Path(temp) / "publication-receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["contract_schema_version"], "park-v4-dossier-v1")
            self.assertFalse(receipt["is_live_research"])
            self.assertEqual(receipt["fresh_model_calls"], 0)


if __name__ == "__main__":
    unittest.main()
