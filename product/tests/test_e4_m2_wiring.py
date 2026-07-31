from __future__ import annotations
import sys, unittest
from pathlib import Path
PRODUCT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(PRODUCT))
from data_core.e4_page_level_filing_facts import FilingNumericFact
from data_core.e4_vertical_degradation import compile_vertical_degradation
class M2WiringTest(unittest.TestCase):
 def test_receipted_input_changes_contract_without_policy_change(self):
  f=FilingNumericFact('300750.SZ','revenue',1,'doc','a'*64,1,'营收','营收 1','2025FY','consolidated','元','CNY','https://static.cninfo.com.cn/a.pdf')
  r=compile_vertical_degradation('300750.SZ',(f,),known_at='2026-07-29T00:00:00Z',additional_section_inputs={'one_line_positioning':{'market_snapshot':{'receipt_id':'m1'}},'research_conclusion_and_open_questions':{'decision_policy_output':{'receipt_id':'m1'}}})
  s={x['section_id']:x for x in r['section_contract']['sections']};self.assertEqual(len(s),9);self.assertEqual(s['one_line_positioning']['status'],'partial');self.assertEqual(s['research_conclusion_and_open_questions']['status'],'partial');self.assertEqual(r['degradation']['tier'],'B')
