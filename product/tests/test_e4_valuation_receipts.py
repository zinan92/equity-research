from __future__ import annotations
import hashlib,json,sys,tempfile,unittest
from pathlib import Path
PRODUCT=Path(__file__).resolve().parents[1]
if str(PRODUCT) not in sys.path: sys.path.insert(0,str(PRODUCT))
from data_core.e4_valuation_receipts import E4_VALUATION_RECEIPT_SCHEMA_VERSION,compile_real_valuation_receipts
CUTOFF='2026-07-25T23:59:59Z'
class TestValuationReceipts(unittest.TestCase):
 def write(self,r,n,v): p=r/n;p.write_text(json.dumps(v),encoding='utf-8');return p
 def inputs(self,r):
  partial={'schema_version':'e4-s4-partial-report-model-v1','data_kind':'real','truth_boundary':{'tier_is_c_only':True},'models':[{'status':'compiled','model':{'ticker':'300750.SZ','evidence_set_id':'set','evidence_manifest_hash':'manifest'}}]}; p=self.write(r,'partial.json',partial)
  h='a'*64; source={'raw_hash':h,'manifest_hash':'b'*64,'known_at':'2026-07-24T00:00:00Z'}
  period=lambda y,rev:{'period':f'{y}-12-31','currency':'CNY','revenue':rev,'ebit':rev*.2,'tax_rate':.2,'depreciation_amortization':rev*.04,'capital_expenditure':rev*.08,'change_in_nwc':rev*.01,'operating_cash_flow':rev*.18,'net_income':rev*.15,'cash':1500,'debt':1000,'assets':7000,'liabilities':3000,'equity':4000,'shares_outstanding':2400000000}
  scenario=lambda n,p,g,m:{'name':n,'probability':p,'revenue_growth':[g]*5,'ebit_margin':[m]*5,'tax_rate':.2,'depreciation_pct_revenue':.04,'capex_pct_revenue':.08,'nwc_investment_pct_revenue':.01,'wacc':.09,'terminal_growth':.03}
  row={'ticker':'300750.SZ','context_evidence_set_id':'set','context_manifest_hash':'manifest','research_cutoff':CUTOFF,'source_receipts':{k:source for k in ('quote','fundamentals','balance_sheet','income_statement','cash_flow')},'assumption_receipt':source,'engine_input':{'ticker':'300750.SZ','currency':'CNY','unit_scale':100000000,'current_price':250,'market_cap':600000000000,'shares_outstanding':2400000000,'historical':[period(2024,3000),period(2025,4000)],'scenarios':[scenario('bear',.25,.03,.16),scenario('base',.5,.12,.2),scenario('bull',.25,.22,.24)],'peer_ev_ebitda':[14,16,18],'historical_pe':[20,24,28]}}
  i={'schema_version':E4_VALUATION_RECEIPT_SCHEMA_VERSION,'data_kind':'real','partial_receipt_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'research_cutoff':CUTOFF,'receipts':[row]};return p,self.write(r,'inputs.json',i)
 def test_compiles_replayable_tier_c_receipt(self):
  with tempfile.TemporaryDirectory() as d:
   p,i=self.inputs(Path(d));a=compile_real_valuation_receipts(p,i,research_cutoff=CUTOFF);b=compile_real_valuation_receipts(p,i,research_cutoff=CUTOFF);self.assertEqual(a,b);self.assertEqual(a['counts']['compiled'],1);self.assertFalse(a['truth_boundary']['counts_as_tier_a_or_b'])
 def test_mismatch_and_future_source_block(self):
  with tempfile.TemporaryDirectory() as d:
   p,i=self.inputs(Path(d));v=json.loads(i.read_text());v['receipts'][0]['source_receipts']['quote']={**v['receipts'][0]['source_receipts']['quote'],'known_at':'2026-07-26T00:00:00Z'};i.write_text(json.dumps(v));a=compile_real_valuation_receipts(p,i,research_cutoff=CUTOFF);self.assertIn('valuation_quote_known_at_after_cutoff',a['receipts'][0]['blockers'])
   v['partial_receipt_sha256']='0'*64;i.write_text(json.dumps(v));
   with self.assertRaisesRegex(ValueError,'lineage'):compile_real_valuation_receipts(p,i,research_cutoff=CUTOFF)
