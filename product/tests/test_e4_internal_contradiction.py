from __future__ import annotations
import json, subprocess, sys, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
class InternalContradictionTest(unittest.TestCase):
 def test_same_document_metric_period_values_are_reported(self):
  with tempfile.TemporaryDirectory() as d:
   src=Path(d)/'src.json';out=Path(d)/'out.json';src.write_text(json.dumps({'tickers':[{'reports':[{'facts':[{'document_id':'d','page_number':5,'metric':'cash','report_period':'2026Q1','value':1},{'document_id':'d','page_number':5,'metric':'cash','report_period':'2026Q1','value':2}]}]}]}))
   subprocess.run([sys.executable,str(ROOT/'scripts'/'audit_e4_quarter_column_identity.py'),str(src),'--out',str(out)],check=True,capture_output=True)
   self.assertEqual(len(json.loads(out.read_text())['internal_contradictions']),1)
