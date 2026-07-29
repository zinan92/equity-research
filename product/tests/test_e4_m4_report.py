from pathlib import Path
import unittest
class M4ReportTest(unittest.TestCase):
 def test_compiler_exists(self): self.assertTrue((Path(__file__).resolve().parents[2]/'scripts'/'compile_e4_m4_catl_report.py').is_file())
