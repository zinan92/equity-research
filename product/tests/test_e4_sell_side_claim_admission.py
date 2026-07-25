from __future__ import annotations
import hashlib,json,sys,tempfile,unittest
from pathlib import Path
PRODUCT=Path(__file__).resolve().parents[1]
if str(PRODUCT) not in sys.path:sys.path.insert(0,str(PRODUCT))
from data_core.contracts import digest
from data_core.e4_sell_side_claim_admission import compile_admitted_sell_side_claims,write_empty_claim_review_decisions

def candidate_receipt():
 candidate={'candidate_id':'broker_assertion_abc','report_id':'r1','raw_hash':'a'*64,'parser_version':'park-document-parser-v1','page_number':2,'chunk_id':'chunk_abc','char_start':4,'char_end':40,'text':'预计收入增长并受益于行业需求。','kind':'broker_assertion_candidate','review_status':'unreviewed','truth_boundary':'broker_assertion_not_verified_company_fact'}
 value={'schema_version':'e4-s4-sell-side-claim-candidates-v1','data_kind':'real','documents':[{'status':'compiled','candidates':[candidate]}],'truth_boundary':{'counts_as_tier_a_or_b':False}};value['receipt_hash']=digest(value);return value,candidate
def decisions(candidate,raw,items):return {'schema_version':'e4-s4-sell-side-claim-review-decisions-v1','data_kind':'real','candidate_receipt_sha256':hashlib.sha256(raw).hexdigest(),'decisions':items}
class ClaimAdmission(unittest.TestCase):
 def write(self,root,name,value):
  path=root/name;path.write_text(json.dumps(value),encoding='utf-8');return path
 def test_explicit_human_acceptance_creates_c3_compatible_page_cited_claim(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);receipt,candidate=candidate_receipt();cp=self.write(root,'candidates.json',receipt);raw=cp.read_bytes();decision={'candidate_id':candidate['candidate_id'],'candidate_identity':{key:candidate[key] for key in ('candidate_id','report_id','raw_hash','parser_version','page_number','chunk_id','char_start','char_end','text')},'decision':'accepted','reviewer_id':'reviewer-1','decided_at':'2026-07-25T12:00:00Z','reason':'Direct broker assertion with page-local quote.','topic':'growth','stance':'bullish','strength':'explicit'};dp=self.write(root,'decisions.json',decisions(candidate,raw,[decision]));result=compile_admitted_sell_side_claims(cp,dp);self.assertEqual(result['counts'],{'candidates':1,'accepted':1,'rejected':0,'unreviewed':0});claim=result['accepted_claims'][0];self.assertEqual(claim['citations'][0]['document_id'],'sell-side-report:r1');self.assertFalse(result['truth_boundary']['counts_as_tier_a_or_b'])
 def test_unreviewed_candidates_are_not_admitted_and_identity_change_fails_closed(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);receipt,candidate=candidate_receipt();cp=self.write(root,'candidates.json',receipt);raw=cp.read_bytes();empty=self.write(root,'empty.json',decisions(candidate,raw,[]));result=compile_admitted_sell_side_claims(cp,empty);self.assertEqual(result['counts']['accepted'],0);self.assertEqual(result['counts']['unreviewed'],1)
   decision={'candidate_id':candidate['candidate_id'],'candidate_identity':{key:candidate[key] for key in ('candidate_id','report_id','raw_hash','parser_version','page_number','chunk_id','char_start','char_end','text')},'decision':'rejected','reviewer_id':'reviewer-1','decided_at':'2026-07-25T12:00:00Z','reason':'Duplicate context.'};decision['candidate_identity']['text']='changed';bad=self.write(root,'bad.json',decisions(candidate,raw,[decision]));
   with self.assertRaisesRegex(ValueError,'text mismatch'):compile_admitted_sell_side_claims(cp,bad)
 def test_empty_review_receipt_is_explicit_and_does_not_admit_claims(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);receipt,_candidate=candidate_receipt();cp=self.write(root,'candidates.json',receipt);empty=write_empty_claim_review_decisions(cp,root);result=compile_admitted_sell_side_claims(cp,Path(empty['path']));self.assertTrue(empty['receipt']['truth_boundary']['no_review_decisions_fabricated']);self.assertEqual(result['counts']['accepted'],0)
