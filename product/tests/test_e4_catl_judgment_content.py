from __future__ import annotations
import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from data_core.e4_catl_judgment_content import JUDGMENT_STATUS, compile_catl_judgments
class JudgmentContentTest(unittest.TestCase):
 def test_issuer_specific_claims_remain_page_cited(self):
  base={'document_id':'doc','raw_hash':'a'*64,'page_number':2,'source_url':'https://static.cninfo.com.cn/a.pdf','report_period':'2025FY'}
  revenue={**base,'metric':'revenue','value':100,'quoted_anchor':'收入 100','unit':'万元'}; cost={**base,'metric':'operating_cost','value':70,'quoted_anchor':'成本 70','unit':'万元'}
  blocks=[{**base,'status':'resolved','section_path':'第三节 管理层讨论与分析 > 三、核心竞争力分析','text':'宁德时代披露核心竞争力与产品研发进展。'}, {**base,'status':'resolved','section_path':'第三节 管理层讨论与分析 > 四、主营业务分析','text':'宁德时代披露主营业务与产品交付进展。'}, {**base,'status':'resolved','section_path':'第三节 管理层讨论与分析 > 十一、风险因素','text':'宁德时代披露原材料价格波动风险。'}, {**base,'status':'resolved','section_path':'第三节 管理层讨论与分析 > 四、研发投入','text':'宁德时代披露研发项目进展。'}]
  out=compile_catl_judgments([revenue,cost],dossier_id='dossier_x',narrative_blocks=blocks)
  self.assertEqual(out['investment_thesis']['status'],JUDGMENT_STATUS); self.assertEqual(out['peer_comparison']['status'],'missing')
  self.assertTrue(all('宁德时代' in row['text'] for row in out.values() if row.get('status')==JUDGMENT_STATUS))
  self.assertEqual(out['falsification_tests']['tests'][0]['time_window'],'next annual filing')
  self.assertGreater(out['investment_thesis']['citation_mix']['narrative_blocks'],0)
