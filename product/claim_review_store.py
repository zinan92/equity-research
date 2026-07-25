"""Append-only owner review decisions for E4 sell-side assertion candidates."""
from __future__ import annotations
import hashlib,json,re,sqlite3
from contextlib import closing
from datetime import datetime,timezone
from pathlib import Path
from typing import Any,Mapping
from auth_store import AUTH_DB_PATH,initialize_auth
from data_store import connect
CLAIM_REVIEW_SCHEMA_VERSION='e4-s4-sell-side-claim-review-decisions-v1'
_IDENTITY=('candidate_id','report_id','raw_hash','parser_version','page_number','chunk_id','char_start','char_end','text')
CLAIM_REVIEW_SCHEMA="""
CREATE TABLE IF NOT EXISTS sell_side_claim_reviews (
 id TEXT PRIMARY KEY,candidate_receipt_sha256 TEXT NOT NULL,candidate_id TEXT NOT NULL,candidate_identity_json TEXT NOT NULL,
 decision TEXT NOT NULL CHECK (decision IN ('accepted','rejected')),reviewer_id TEXT NOT NULL REFERENCES members(id),reason TEXT NOT NULL,
 topic TEXT,stance TEXT CHECK (stance IN ('bullish','bearish','neutral')),strength TEXT CHECK (strength IN ('tentative','explicit')),decided_at TEXT NOT NULL,
 UNIQUE(candidate_receipt_sha256,candidate_id));
CREATE TRIGGER IF NOT EXISTS sell_side_claim_reviews_no_update BEFORE UPDATE ON sell_side_claim_reviews BEGIN SELECT RAISE(ABORT, 'claim review rows are append-only'); END;
CREATE TRIGGER IF NOT EXISTS sell_side_claim_reviews_no_delete BEFORE DELETE ON sell_side_claim_reviews BEGIN SELECT RAISE(ABORT, 'claim review rows are append-only'); END;
"""
_TRIGGERS={'sell_side_claim_reviews_no_update':"CREATE TRIGGER sell_side_claim_reviews_no_update BEFORE UPDATE ON sell_side_claim_reviews BEGIN SELECT RAISE(ABORT, 'claim review rows are append-only'); END",'sell_side_claim_reviews_no_delete':"CREATE TRIGGER sell_side_claim_reviews_no_delete BEFORE DELETE ON sell_side_claim_reviews BEGIN SELECT RAISE(ABORT, 'claim review rows are append-only'); END"}
class ClaimReviewError(RuntimeError):pass
def _canonical_sql(value:str)->str:return re.sub(r'\s+',' ',value.strip()).removesuffix(';')
def _sha(value:object)->str:return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def _now()->str:return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
def initialize_claim_reviews(db_path:Path=AUTH_DB_PATH)->None:
 initialize_auth(db_path)
 with closing(connect(db_path)) as conn:
  conn.executescript(CLAIM_REVIEW_SCHEMA);rows=conn.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger' AND name IN (?,?)",tuple(_TRIGGERS)).fetchall();actual={x['name']:_canonical_sql(x['sql'] or '') for x in rows};expected={k:_canonical_sql(v) for k,v in _TRIGGERS.items()}
  if actual!=expected:raise ClaimReviewError('claim-review append-only guard is missing or altered')
  conn.commit()
def _candidate(path:Path,candidate_id:str)->tuple[bytes,dict[str,Any]]:
 raw=path.read_bytes();receipt=json.loads(raw)
 if receipt.get('schema_version')!='e4-s4-sell-side-claim-candidates-v1' or receipt.get('data_kind')!='real':raise ClaimReviewError('real candidate receipt is required')
 matches=[x for doc in receipt.get('documents',[]) if doc.get('status')=='compiled' for x in doc.get('candidates',[]) if x.get('candidate_id')==candidate_id]
 if len(matches)!=1:raise ClaimReviewError('candidate is unavailable or ambiguous')
 candidate=matches[0]
 if candidate.get('kind')!='broker_assertion_candidate' or candidate.get('review_status')!='unreviewed' or any(candidate.get(k) in (None,'') for k in _IDENTITY):raise ClaimReviewError('candidate is not a complete unreviewed broker assertion')
 return raw,{k:candidate[k] for k in _IDENTITY}
def _owner(member:Mapping[str,Any],conn:sqlite3.Connection)->None:
 row=conn.execute("SELECT role,status FROM members WHERE id=?",(member.get('id'),)).fetchone()
 if not row or row['role']!='owner' or row['status']!='active':raise PermissionError('owner access required')
def _review_input(payload:Mapping[str,Any])->tuple[str,str,str|None,str|None,str|None]:
 decision=str(payload.get('decision') or '');reason=' '.join(str(payload.get('reason') or '').split())
 if decision not in {'accepted','rejected'}:raise ClaimReviewError('decision must be accepted or rejected')
 if not 10<=len(reason)<=2000:raise ClaimReviewError('reason must contain 10-2000 characters')
 if decision=='rejected':return decision,reason,None,None,None
 topic=' '.join(str(payload.get('topic') or '').split());stance=str(payload.get('stance') or '');strength=str(payload.get('strength') or '')
 if not topic or stance not in {'bullish','bearish','neutral'} or strength not in {'tentative','explicit'}:raise ClaimReviewError('accepted review requires topic, valid stance and strength')
 return decision,reason,topic,stance,strength
def _public(row:sqlite3.Row|Mapping[str,Any])->dict[str,Any]:
 value=dict(row);out={'candidate_id':value['candidate_id'],'candidate_identity':json.loads(value['candidate_identity_json']),'decision':value['decision'],'reviewer_id':value['reviewer_id'],'decided_at':value['decided_at'],'reason':value['reason']}
 if value['decision']=='accepted':out.update({'topic':value['topic'],'stance':value['stance'],'strength':value['strength']})
 return out
def append_claim_review(member:Mapping[str,Any],candidate_receipt_path:Path,payload:Mapping[str,Any],db_path:Path=AUTH_DB_PATH)->dict[str,Any]:
 initialize_claim_reviews(db_path);raw,identity=_candidate(candidate_receipt_path,str(payload.get('candidate_id') or ''));decision,reason,topic,stance,strength=_review_input(payload);lineage=hashlib.sha256(raw).hexdigest();review_id='claim_review_'+_sha({'lineage':lineage,'candidate_id':identity['candidate_id']})[:20]
 with closing(connect(db_path)) as conn:
  conn.execute('BEGIN IMMEDIATE');_owner(member,conn)
  try:conn.execute("INSERT INTO sell_side_claim_reviews VALUES (?,?,?,?,?,?,?,?,?,?,?)",(review_id,lineage,identity['candidate_id'],json.dumps(identity,ensure_ascii=False,sort_keys=True),decision,member['id'],reason,topic,stance,strength,_now()))
  except sqlite3.IntegrityError as exc:raise ClaimReviewError('candidate already has a review decision for this receipt') from exc
  conn.commit();return _public(conn.execute('SELECT * FROM sell_side_claim_reviews WHERE id=?',(review_id,)).fetchone())
def export_claim_review_decisions(owner:Mapping[str,Any],candidate_receipt_path:Path,db_path:Path=AUTH_DB_PATH)->dict[str,Any]:
 initialize_claim_reviews(db_path);raw=candidate_receipt_path.read_bytes();receipt=json.loads(raw)
 if receipt.get('schema_version')!='e4-s4-sell-side-claim-candidates-v1' or receipt.get('data_kind')!='real':raise ClaimReviewError('real candidate receipt is required')
 lineage=hashlib.sha256(raw).hexdigest()
 with closing(connect(db_path)) as conn:
  _owner(owner,conn);rows=conn.execute('SELECT * FROM sell_side_claim_reviews WHERE candidate_receipt_sha256=? ORDER BY decided_at,id',(lineage,)).fetchall()
  payload={'schema_version':CLAIM_REVIEW_SCHEMA_VERSION,'data_kind':'real','candidate_receipt_sha256':lineage,'decisions':[_public(row) for row in rows],'truth_boundary':{'decisions_are_explicit_human_reviews':True,'no_auto_acceptance':True}}
  payload['receipt_hash']=_sha(payload);return payload
