from __future__ import annotations
import json,sys,tempfile,unittest
from pathlib import Path
PRODUCT=Path(__file__).resolve().parents[1]
if str(PRODUCT) not in sys.path:sys.path.insert(0,str(PRODUCT))
from data_core.contracts import digest # noqa:E402
from spot_audit_assignment_reader import load_assignment,SpotAuditAssignmentReadError # noqa:E402
def receipt():
 a={'ticker':'300750.SZ','report_model_hash':'a'*64,'document_identity':{'raw_hash':'b'*64},'numeric_check':{'expected_value':1},'page_citation_check':{'document_id':'d'},'review_status':'pending_human_review'};r={'schema_version':'e4-s4-spot-audit-assignments-v1','data_kind':'runtime_only_audit','assignments':[a]};r['receipt_hash']=digest(r);return r
class Test(unittest.TestCase):
 def test_safe_projection_and_unavailable(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'x.json';p.write_text(json.dumps(receipt()));self.assertEqual(load_assignment('300750',p)['status'],'available');self.assertEqual(load_assignment('000001',p),{'ticker':'000001.SZ','status':'unavailable'})
 def test_tamper_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'x.json';x=receipt();x['assignments'][0]['ticker']='bad';p.write_text(json.dumps(x))
   with self.assertRaises(SpotAuditAssignmentReadError):load_assignment('300750',p)
if __name__=='__main__':unittest.main()
