from __future__ import annotations
import sys, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT/"product"))
from data_core.e4_narrative_batch import _selection  # noqa: E402

class NarrativeBatchTest(unittest.TestCase):
 def test_prefers_latest_annual_over_newer_interim(self):
  row={"reports":[{"period":"2026Q1","status":"available","document":{}},{"period":"2025FY","status":"available","document":{}},{"period":"2024FY","status":"available","document":{}}]}
  selected = _selection(row)
  self.assertEqual(selected[0]["period"],"2025FY")
  self.assertEqual(selected[1], "latest_available_annual")
 def test_records_interim_fallback(self):
  selected = _selection({"reports":[{"period":"2026Q1","status":"available","document":{}}]})
  self.assertEqual(selected[0]["period"], "2026Q1")
  self.assertEqual(selected[1], "latest_available_interim_fallback")
 def test_returns_none_without_available_official_document(self): self.assertIsNone(_selection({"reports":[{"period":"2025FY","status":"missing"}]}))
