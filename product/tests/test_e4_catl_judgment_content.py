from __future__ import annotations
import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from data_core.e4_catl_judgment_content import JUDGMENT_STATUS, compile_catl_judgments
class JudgmentContentTest(unittest.TestCase):
 def test_factual_numbers_remain_page_cited(self):
  f={'metric':'revenue','value':1,'document_id':'doc','raw_hash':'a'*64,'page_number':2,'quoted_anchor':'收入 1','source_url':'https://static.cninfo.com.cn/a.pdf','report_period':'2025FY','unit':'万元'}
  out=compile_catl_judgments([f],dossier_id='dossier_x')
  self.assertEqual(out['investment_thesis']['status'],JUDGMENT_STATUS); self.assertEqual(out['peer_comparison']['status'],'missing'); self.assertEqual(out['investment_thesis']['facts'][0]['citation']['page_number'],2)
