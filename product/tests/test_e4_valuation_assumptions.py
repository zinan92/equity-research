from __future__ import annotations
import sys,unittest
from pathlib import Path
PRODUCT=Path(__file__).resolve().parents[1]
if str(PRODUCT) not in sys.path:sys.path.insert(0,str(PRODUCT))
from data_core.e4_valuation_assumptions import compile_assumption_receipt # noqa:E402
def value():
 s=lambda n,p:{'name':n,'probability':p,'revenue_growth':[.1,.1,.1],'ebit_margin':[.2,.2,.2],'tax_rate':.2,'depreciation_pct_revenue':.04,'capex_pct_revenue':.08,'nwc_investment_pct_revenue':.01,'wacc':.09,'terminal_growth':.03}
 return {'ticker':'300750.SZ','research_cutoff':'2026-07-25T00:00:00Z','author_id':'member_1','rationale':'The analyst explicitly records a scenario rationale with evidence context.','source_identities':{'filing':{'raw_hash':'a'*64}},'scenarios':[s('bear',.25),s('base',.5),s('bull',.25)]}
class Test(unittest.TestCase):
 def test_explicit_and_deterministic(self):self.assertEqual(compile_assumption_receipt(value())['receipt_hash'],compile_assumption_receipt(value())['receipt_hash'])
 def test_no_default(self):
  v=value();v['scenarios']=[]
  with self.assertRaises(ValueError):compile_assumption_receipt(v)
if __name__=='__main__':unittest.main()
