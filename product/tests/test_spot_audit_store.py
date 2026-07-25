from __future__ import annotations
import json,sys,tempfile,unittest
from pathlib import Path
PRODUCT=Path(__file__).resolve().parents[1]
if str(PRODUCT) not in sys.path:sys.path.insert(0,str(PRODUCT))
from auth_store import create_owner,redeem_invite,create_invite # noqa:E402
from data_core.contracts import digest # noqa:E402
from data_store import initialize # noqa:E402
from spot_audit_store import SpotAuditReviewError,append_spot_audit_review,export_spot_audit_reviews # noqa:E402
def receipt():
 a={'ticker':'300750.SZ','report_model_hash':'a'*64,'document_identity':{'document_id':'official:1','raw_hash':'b'*64},'numeric_check':{'fact_path':'x','expected_value':1},'page_citation_check':{'document_id':'official:1','raw_hash':'b'*64},'review_status':'pending_human_review'}
 r={'schema_version':'e4-s4-spot-audit-assignments-v1','data_kind':'runtime_only_audit','assignments':[a]};r['receipt_hash']=digest(r);return r
class Test(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.r=Path(self.t.name);self.p=self.r/'a.json';self.p.write_text(json.dumps(receipt()));self.db=self.r/'a.db';initialize(self.db,force_seed=True);self.owner=create_owner('x@example.com','owner-password-2026','X',self.db);inv=create_invite(self.owner['id'],'preview',self.db);self.member=redeem_invite(inv['code'],'m@example.com','preview-password-2026','M',self.db)
 def tearDown(self):self.t.cleanup()
 def payload(self):return {'ticker':'300750.SZ','numeric_result':'pass','page_result':'pass','page_number':3,'quoted_label':'主营业务收入','rationale':'The reviewer independently checked the declared source identity.'}
 def test_owner_appends_and_exports(self):
  saved=append_spot_audit_review(self.owner,self.p,self.payload(),self.db);self.assertEqual(saved['ticker'],'300750.SZ');out=export_spot_audit_reviews(self.owner,self.p,self.db);self.assertEqual(len(out['decisions']),1);self.assertTrue(out['truth_boundary']['does_not_change_e4_acceptance'])
 def test_member_and_duplicate_rejected(self):
  with self.assertRaises(PermissionError):append_spot_audit_review(self.member,self.p,self.payload(),self.db)
  append_spot_audit_review(self.owner,self.p,self.payload(),self.db)
  with self.assertRaisesRegex(SpotAuditReviewError,'already'):append_spot_audit_review(self.owner,self.p,self.payload(),self.db)
if __name__=='__main__':unittest.main()
