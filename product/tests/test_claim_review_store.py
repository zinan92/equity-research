from __future__ import annotations
import json,sys,tempfile,unittest
from pathlib import Path
PRODUCT=Path(__file__).resolve().parents[1]
if str(PRODUCT) not in sys.path:sys.path.insert(0,str(PRODUCT))
from auth_store import create_owner
from claim_review_store import ClaimReviewError,append_claim_review,export_claim_review_decisions,initialize_claim_reviews
from data_core.contracts import digest
from data_core.e4_sell_side_claim_admission import compile_admitted_sell_side_claims

def receipt():
 candidate={'candidate_id':'broker_assertion_1','report_id':'r1','raw_hash':'a'*64,'parser_version':'park-document-parser-v1','page_number':1,'chunk_id':'chunk_1','char_start':0,'char_end':30,'text':'预计收入增长并受益于行业需求。','kind':'broker_assertion_candidate','review_status':'unreviewed','truth_boundary':'broker_assertion_not_verified_company_fact'}
 value={'schema_version':'e4-s4-sell-side-claim-candidates-v1','data_kind':'real','documents':[{'status':'compiled','candidates':[candidate]}],'truth_boundary':{'counts_as_tier_a_or_b':False}};value['receipt_hash']=digest(value);return value,candidate
class ClaimReviewStore(unittest.TestCase):
 def test_owner_append_exports_admission_schema_and_rejects_duplicate(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);db=root/'auth.db';value,candidate=receipt();path=root/'candidate.json';path.write_text(json.dumps(value));owner=create_owner('owner@example.com','correct horse battery staple','Owner',db);payload={'candidate_id':candidate['candidate_id'],'decision':'accepted','reason':'Direct broker statement is clear and page-bound.','topic':'growth','stance':'bullish','strength':'explicit'}
   stored=append_claim_review(owner,path,payload,db);self.assertEqual(stored['reviewer_id'],owner['id']);exported=export_claim_review_decisions(owner,path,db);self.assertEqual(exported['schema_version'],'e4-s4-sell-side-claim-review-decisions-v1');dp=root/'decisions.json';dp.write_text(json.dumps(exported));self.assertEqual(compile_admitted_sell_side_claims(path,dp)['counts']['accepted'],1)
   with self.assertRaisesRegex(ClaimReviewError,'already has'):append_claim_review(owner,path,payload,db)
 def test_member_cannot_append_or_export_and_guards_initialize(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);db=root/'auth.db';value,candidate=receipt();path=root/'candidate.json';path.write_text(json.dumps(value));owner=create_owner('owner@example.com','correct horse battery staple','Owner',db);member={**owner,'id':'missing-member'};payload={'candidate_id':candidate['candidate_id'],'decision':'rejected','reason':'The statement is too broad for this report.'}
   with self.assertRaises(PermissionError):append_claim_review(member,path,payload,db)
   with self.assertRaises(PermissionError):export_claim_review_decisions(member,path,db)
   initialize_claim_reviews(db)
