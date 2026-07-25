"""Human-decision admission gate for page-cited sell-side assertion candidates."""
from __future__ import annotations

import hashlib,json
from datetime import datetime
from pathlib import Path
from typing import Any,Mapping

from .contracts import digest

E4_SELL_SIDE_CLAIM_ADMISSION_SCHEMA_VERSION='e4-s4-sell-side-claim-admission-v1'
E4_SELL_SIDE_CLAIM_DECISIONS_SCHEMA_VERSION='e4-s4-sell-side-claim-review-decisions-v1'
_IDENTITY=('candidate_id','report_id','raw_hash','parser_version','page_number','chunk_id','char_start','char_end','text')

def _load(path:Path,schema:str)->tuple[bytes,dict[str,Any]]:
 raw=path.read_bytes();value=json.loads(raw)
 if value.get('schema_version')!=schema or value.get('data_kind')!='real':raise ValueError('claim admission requires real schema-bound receipts')
 return raw,value

def _instant(value:Any)->str:
 try:parsed=datetime.fromisoformat(str(value).replace('Z','+00:00'))
 except ValueError as exc:raise ValueError('decision timestamp must be ISO-8601') from exc
 if parsed.tzinfo is None:raise ValueError('decision timestamp must include timezone')
 return parsed.isoformat().replace('+00:00','Z')

def _candidates(receipt:Mapping[str,Any])->dict[str,dict[str,Any]]:
 rows=[candidate for document in receipt.get('documents',[]) if document.get('status')=='compiled' for candidate in document.get('candidates',[])]
 result={str(row.get('candidate_id') or ''):row for row in rows}
 if not result or len(result)!=len(rows):raise ValueError('candidate receipt has missing or duplicate candidate identities')
 for row in result.values():
  if row.get('kind')!='broker_assertion_candidate' or row.get('review_status')!='unreviewed':raise ValueError('candidate receipt contains non-unreviewed assertion')
 return result

def _review(candidate:Mapping[str,Any],decision:Mapping[str,Any])->dict[str,Any]:
 if decision.get('decision') not in {'accepted','rejected'}:raise ValueError('review decision must be accepted or rejected')
 for field in ('candidate_id','reviewer_id','reason'):
  if not str(decision.get(field) or '').strip():raise ValueError(f'review {field} is required')
 if str(decision['candidate_id'])!=candidate['candidate_id']:raise ValueError('review candidate identity mismatch')
 supplied=decision.get('candidate_identity')
 if not isinstance(supplied,Mapping):raise ValueError('review candidate_identity is required')
 for field in _IDENTITY:
  if supplied.get(field)!=candidate.get(field):raise ValueError(f'review candidate_identity {field} mismatch')
 reviewed={'candidate_id':candidate['candidate_id'],'decision':decision['decision'],'reviewer_id':str(decision['reviewer_id']).strip(),'decided_at':_instant(decision.get('decided_at')),'reason':str(decision['reason']).strip()}
 if decision['decision']=='accepted':
  for field in ('topic','stance','strength'):
   if not str(decision.get(field) or '').strip():raise ValueError(f'accepted review {field} is required')
  if decision['stance'] not in {'bullish','bearish','neutral'}:raise ValueError('accepted review stance is invalid')
  if decision['strength'] not in {'tentative','explicit'}:raise ValueError('accepted review strength is invalid')
  reviewed['c3_claim']={'claim_id':candidate['candidate_id'],'topic':str(decision['topic']).strip(),'stance':decision['stance'],'text':candidate['text'],'strength':decision['strength'],'citations':[{'document_id':f"sell-side-report:{candidate['report_id']}",'page_number':candidate['page_number'],'raw_hash':candidate['raw_hash'],'quote':candidate['text'],'chunk_id':candidate['chunk_id']}],'truth_boundary':'accepted_broker_assertion_not_verified_company_fact'}
 return reviewed

def compile_admitted_sell_side_claims(candidate_path:Path,decisions_path:Path)->dict[str,Any]:
 craw,candidates_receipt=_load(candidate_path,'e4-s4-sell-side-claim-candidates-v1');draw,decisions=_load(decisions_path,E4_SELL_SIDE_CLAIM_DECISIONS_SCHEMA_VERSION)
 if decisions.get('candidate_receipt_sha256')!=hashlib.sha256(craw).hexdigest():raise ValueError('review decisions do not match candidate receipt lineage')
 candidates=_candidates(candidates_receipt);seen=set();reviews=[]
 for decision in decisions.get('decisions',[]):
  if not isinstance(decision,Mapping):raise ValueError('review decision must be an object')
  candidate_id=str(decision.get('candidate_id') or '')
  if candidate_id in seen:raise ValueError('candidate may have only one review decision')
  if candidate_id not in candidates:raise ValueError('review references unknown candidate')
  seen.add(candidate_id);reviews.append(_review(candidates[candidate_id],decision))
 accepted=[review['c3_claim'] for review in reviews if review['decision']=='accepted']
 receipt={'schema_version':E4_SELL_SIDE_CLAIM_ADMISSION_SCHEMA_VERSION,'data_kind':'real','candidate_receipt_sha256':hashlib.sha256(craw).hexdigest(),'review_decisions_receipt_sha256':hashlib.sha256(draw).hexdigest(),'accepted_claims':accepted,'reviews':reviews,'counts':{'candidates':len(candidates),'accepted':len(accepted),'rejected':sum(x['decision']=='rejected' for x in reviews),'unreviewed':len(candidates)-len(reviews)},'truth_boundary':{'accepted_claims_are_broker_assertions_not_verified_company_facts':True,'counts_as_tier_a_or_b':False,'counts_as_numeric_page_audit':False,'counts_as_position_or_target':False}}
 receipt['receipt_hash']=digest(receipt);return receipt

def write_empty_claim_review_decisions(candidate_path:Path,runtime_root:Path)->dict[str,Any]:
 """Create an explicit zero-decision runtime receipt; it never fabricates review."""
 raw,receipt=_load(candidate_path,'e4-s4-sell-side-claim-candidates-v1');_candidates(receipt)
 value={'schema_version':E4_SELL_SIDE_CLAIM_DECISIONS_SCHEMA_VERSION,'data_kind':'real','candidate_receipt_sha256':hashlib.sha256(raw).hexdigest(),'decisions':[],'truth_boundary':{'no_review_decisions_fabricated':True}}
 value['receipt_hash']=digest(value);path=runtime_root/f"sell-side-claim-review-decisions-{value['receipt_hash'][:16]}.json";tmp=path.with_suffix('.json.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8');tmp.replace(path)
 return {'path':str(path),'receipt':value}

def write_admitted_sell_side_claims(candidate_path:Path,decisions_path:Path,runtime_root:Path)->dict[str,Any]:
 receipt=compile_admitted_sell_side_claims(candidate_path,decisions_path);path=runtime_root/f"sell-side-claim-admission-{receipt['receipt_hash'][:16]}.json";tmp=path.with_suffix('.json.tmp');tmp.write_text(json.dumps(receipt,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8');tmp.replace(path)
 pointer=runtime_root/'sell-side-claim-admission-latest.json';tmp=pointer.with_suffix('.json.tmp');tmp.write_text(json.dumps({'receipt':path.name,'receipt_hash':receipt['receipt_hash']},ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8');tmp.replace(pointer)
 return {'path':str(path),'receipt':receipt}
