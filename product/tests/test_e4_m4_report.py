from pathlib import Path
import unittest
class M4ReportTest(unittest.TestCase):
 def test_compiler_is_issuer_generic(self):
  source=(Path(__file__).resolve().parents[2]/'scripts'/'compile_e4_m4_report.py').read_text()
  self.assertIn("company_adapter(ticker).name",source)
  self.assertIn("p.add_argument('--ticker',required=True)",source)
  self.assertNotIn("宁德时代",source)
  self.assertNotIn("贵州茅台",source)
  self.assertNotIn("default='300750.SZ'",source)
