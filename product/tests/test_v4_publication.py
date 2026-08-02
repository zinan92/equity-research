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
        source = (ROOT / "artifacts/round7-dossiers/300750.SZ.md").read_text(encoding="utf-8")
        rendered = render_v4_html(source, title="CATL V4")
        self.assertIn("未审阅 AI 判断", rendered)
        self.assertIn("static.cninfo.com.cn", rendered)
        self.assertIn("财务与经营时间序列", rendered)

    def test_build_two_persistent_reports(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            result = build_v4_publication(
                source_root=ROOT / "artifacts/round7-dossiers",
                output_root=Path(temp),
            )
            self.assertEqual(result["status"], "blocked")
            self.assertEqual(len(result["companies"]), 0)
            self.assertEqual(len(result["review_queue"]), 3)
            self.assertTrue(Path(result["index_path"]).is_file())
            index = (Path(temp) / "index.html").read_text(encoding="utf-8")
            self.assertIn("暂无可公开档案", index)
            self.assertNotIn("300750.SZ/report.html", index)

    def test_publication_receipt_is_machine_readable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            build_v4_publication(source_root=ROOT / "artifacts/round7-dossiers", output_root=Path(temp))
            receipt = json.loads((Path(temp) / "publication-receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["contract_schema_version"], "park-v4-dossier-v1")
            self.assertFalse(receipt["is_live_research"])
            self.assertEqual(receipt["fresh_model_calls"], 0)
            self.assertEqual(receipt["status"], "blocked")

    def test_blocked_refresh_quarantines_stale_public_company_dir(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output_root = Path(temp)
            stale_dir = output_root / "300750.SZ"
            stale_dir.mkdir()
            (stale_dir / "report.html").write_text("old public copy", encoding="utf-8")
            result = build_v4_publication(
                source_root=ROOT / "artifacts/round7-dossiers",
                output_root=output_root,
            )
            self.assertFalse((output_root / "300750.SZ" / "report.html").exists())
            self.assertTrue(any((output_root / ".blocked-history").glob("300750.SZ*")))
            queue_row = next(item for item in result["review_queue"] if item["ticker"] == "300750.SZ")
            self.assertTrue(queue_row["stale_publication_quarantined"])


if __name__ == "__main__":
    unittest.main()
