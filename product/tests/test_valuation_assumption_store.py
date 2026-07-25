from __future__ import annotations
import sys,tempfile,unittest
from pathlib import Path
PRODUCT=Path(__file__).resolve().parents[1]
if str(PRODUCT) not in sys.path:sys.path.insert(0,str(PRODUCT))
from auth_store import create_owner,create_invite,redeem_invite # noqa:E402
from data_store import initialize # noqa:E402
from valuation_assumption_store import append_assumption,export_assumptions,ValuationAssumptionStoreError # noqa:E402
def payload():
 s=lambda n,p:{'name':n,'probability':p,'revenue_growth':[.1,.1,.1],'ebit_margin':[.2,.2,.2],'tax_rate':.2,'depreciation_pct_revenue':.04,'capex_pct_revenue':.08,'nwc_investment_pct_revenue':.01,'wacc':.09,'terminal_growth':.03}
 return {'ticker':'300750.SZ','research_cutoff':'2026-07-25T00:00:00Z','rationale':'Explicit analyst judgment with evidence rationale that exceeds threshold.','source_identities':{'filing':{'raw_hash':'a'*64}},'scenarios':[s('bear',.25),s('base',.5),s('bull',.25)]}
class Test(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.db=Path(self.t.name)/'d.db';initialize(self.db,force_seed=True);self.owner=create_owner('o@example.com','owner-password-2026','O',self.db);i=create_invite(self.owner['id'],'member',self.db);self.member=redeem_invite(i['code'],'m@example.com','member-password-2026','M',self.db)
 def tearDown(self):self.t.cleanup()
 def test_owner_append_export_and_duplicate(self):
  saved=append_assumption(self.owner,payload(),self.db);self.assertEqual(saved['author_id'],self.owner['id']);self.assertEqual(len(export_assumptions(self.owner,self.db)['receipts']),1)
  with self.assertRaises(ValuationAssumptionStoreError):append_assumption(self.owner,payload(),self.db)
 def test_member_rejected(self):
  with self.assertRaises(PermissionError):append_assumption(self.member,payload(),self.db)
if __name__=='__main__':unittest.main()
