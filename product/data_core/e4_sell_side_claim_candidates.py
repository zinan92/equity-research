"""Conservative page-bound candidate extraction from parsed sell-side PDFs."""
from __future__ import annotations
import hashlib,json,re
from pathlib import Path
from typing import Any,Mapping
from .contracts import digest
from .document_intelligence import parse_pdf_document
from .e4_sell_side_page_evidence import _inside

E4_SELL_SIDE_CLAIM_CANDIDATE_SCHEMA_VERSION='e4-s4-sell-side-claim-candidates-v1'
E4_SELL_SIDE_CLAIM_CANDIDATE_CHECKPOINT_SCHEMA_VERSION='e4-s4-sell-side-claim-candidate-checkpoint-v1'
_SENTENCE=re.compile(r'[^。！？.!?\n]{12,240}[。！？.!?]')
# Signals only select explicit broker-style assertions; they do not prove truth.
_SIGNALS=('预计','预期','看好','维持','上调','下调','增长','提升','风险','压力','受益','驱动','expect','growth','risk')
def _load(p:Path,schema:str)->tuple[bytes,dict[str,Any]]:
 raw=p.read_bytes();v=json.loads(raw)
 if v.get('schema_version')!=schema or v.get('data_kind')!='real':raise ValueError('claim candidate compiler requires real schema-bound receipts')
 return raw,v
def _candidate(report:Mapping[str,Any],page:Mapping[str,Any],chunk:Mapping[str,Any],text:str)->list[dict[str,Any]]:
 out=[]
 for m in _SENTENCE.finditer(text):
  sentence=' '.join(m.group(0).split())
  if not any(x in sentence for x in _SIGNALS):continue
  identity={'report_id':report['report_id'],'raw_hash':report['pdf_raw_hash'],'parser_version':page['parser_version'],'page_number':page['page_number'],'chunk_id':chunk['chunk_id'],'char_start':chunk['char_start']+m.start(),'char_end':chunk['char_start']+m.end(),'text':sentence}
  out.append({**identity,'candidate_id':'broker_assertion_'+digest(identity)[:40],'kind':'broker_assertion_candidate','review_status':'unreviewed','truth_boundary':'broker_assertion_not_verified_company_fact'})
 return out
def _inputs(batch_path:Path,page_evidence_path:Path)->tuple[bytes,dict[str,Any],bytes,dict[str,Any],dict[str,dict[str,Any]]]:
 braw,batch=_load(batch_path,'e4-s4-sell-side-evidence-batch-v1');eraw,evidence=_load(page_evidence_path,'e4-s4-sell-side-page-evidence-v1')
 if evidence.get('sell_side_batch_receipt_sha256')!=hashlib.sha256(braw).hexdigest():raise ValueError('page evidence does not match sell-side batch lineage')
 return braw,batch,eraw,evidence,{r['report_id']:r for r in evidence.get('documents',[]) if r.get('status')=='parsed'}
def _work(batch:Mapping[str,Any])->list[tuple[dict[str,Any],dict[str,Any]]]:
 return [(tr,report) for tr in batch.get('tickers',[]) for report in tr.get('reports',[])]
def _compile_report(tr:Mapping[str,Any],report:Mapping[str,Any],parsed:Mapping[str,Mapping[str,Any]],runtime_root:Path)->dict[str,Any]:
 rid=str(report.get('report_id') or '');ev=parsed.get(rid);base={'ticker':str(tr.get('ticker') or '').upper(),'report_id':rid}
 if report.get('archive_status')!='archived_pdf' or ev is None:return {**base,'status':'blocked','blockers':['page_verified_pdf_unavailable']}
 try:
  raw=_inside(runtime_root,str(report['runtime_raw_path'])).read_bytes()
  if hashlib.sha256(raw).hexdigest()!=report.get('pdf_raw_hash'):raise ValueError('raw hash mismatch')
  doc=parse_pdf_document(f'sell-side-report:{rid}',raw,expected_raw_hash=report['pdf_raw_hash'])
  if ev.get('parse_id')!=doc.parse_id or ev.get('parser_version')!=doc.parser_version:raise ValueError('parser identity mismatch')
  candidates=[]
  for chunk in doc.chunks:candidates+=_candidate(report,{'page_number':chunk.page_number,'parser_version':doc.parser_version},chunk.__dict__,chunk.text)
  return {**base,'status':'compiled','candidates':candidates}
 except Exception as exc:return {**base,'status':'blocked','blockers':['claim_candidate_input_invalid'],'error':type(exc).__name__}
def _receipt(braw:bytes,eraw:bytes,rows:list[dict[str,Any]])->dict[str,Any]:
 receipt={'schema_version':E4_SELL_SIDE_CLAIM_CANDIDATE_SCHEMA_VERSION,'data_kind':'real','batch_receipt_sha256':hashlib.sha256(braw).hexdigest(),'page_evidence_receipt_sha256':hashlib.sha256(eraw).hexdigest(),'documents':rows,'counts':{'compiled':sum(x['status']=='compiled' for x in rows),'candidates':sum(len(x.get('candidates',[])) for x in rows),'blocked':sum(x['status']=='blocked' for x in rows)},'truth_boundary':{'candidates_are_not_accepted_claims':True,'counts_as_tier_a_or_b':False,'counts_as_numeric_page_audit':False,'counts_as_position_or_target':False}}
 receipt['receipt_hash']=digest(receipt);return receipt
def _write_receipt(runtime_root:Path,receipt:Mapping[str,Any])->Path:
 path=runtime_root/f"sell-side-claim-candidates-{receipt['receipt_hash'][:16]}.json"
 temporary=path.with_suffix(path.suffix+'.tmp');temporary.write_text(json.dumps(receipt,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8');temporary.replace(path)
 pointer=runtime_root/'sell-side-claim-candidates-latest.json';tmp=pointer.with_suffix(pointer.suffix+'.tmp');tmp.write_text(json.dumps({'receipt':path.name,'receipt_hash':receipt['receipt_hash']},ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8');tmp.replace(pointer)
 return path
def compile_sell_side_claim_candidates(batch_path:Path,page_evidence_path:Path,runtime_root:Path)->dict[str,Any]:
 braw,batch,eraw,_evidence,parsed=_inputs(batch_path,page_evidence_path)
 return _receipt(braw,eraw,[_compile_report(tr,report,parsed,runtime_root) for tr,report in _work(batch)])

def run_sell_side_claim_candidate_slice(batch_path:Path,page_evidence_path:Path,runtime_root:Path,*,limit:int=10,resume:bool=True)->dict[str,Any]:
 """Run a bounded deterministic slice and persist a lineage-bound checkpoint."""
 if limit<1:raise ValueError('limit must be positive')
 braw,batch,eraw,_evidence,parsed=_inputs(batch_path,page_evidence_path);work=_work(batch)
 lineage=digest({'batch_receipt_sha256':hashlib.sha256(braw).hexdigest(),'page_evidence_receipt_sha256':hashlib.sha256(eraw).hexdigest()})
 checkpoint_path=runtime_root/f'sell-side-claim-candidate-checkpoint-{lineage[:16]}.json'
 rows:list[dict[str,Any]]=[]
 if resume and checkpoint_path.is_file():
  checkpoint=json.loads(checkpoint_path.read_text(encoding='utf-8'))
  if checkpoint.get('schema_version')!=E4_SELL_SIDE_CLAIM_CANDIDATE_CHECKPOINT_SCHEMA_VERSION or checkpoint.get('lineage')!=lineage:raise ValueError('candidate checkpoint lineage mismatch')
  rows=list(checkpoint.get('documents') or [])
 start=len(rows)
 if start>len(work):raise ValueError('candidate checkpoint exceeds batch work')
 stop=min(start+limit,len(work));rows.extend(_compile_report(tr,report,parsed,runtime_root) for tr,report in work[start:stop])
 checkpoint={'schema_version':E4_SELL_SIDE_CLAIM_CANDIDATE_CHECKPOINT_SCHEMA_VERSION,'data_kind':'real','lineage':lineage,'batch_receipt_sha256':hashlib.sha256(braw).hexdigest(),'page_evidence_receipt_sha256':hashlib.sha256(eraw).hexdigest(),'documents':rows,'next_index':stop,'total_documents':len(work),'complete':stop==len(work),'truth_boundary':{'candidates_are_not_accepted_claims':True,'counts_as_tier_a_or_b':False,'counts_as_numeric_page_audit':False,'counts_as_position_or_target':False}}
 checkpoint['checkpoint_hash']=digest(checkpoint)
 temporary=checkpoint_path.with_suffix('.json.tmp');temporary.write_text(json.dumps(checkpoint,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8');temporary.replace(checkpoint_path)
 pointer=runtime_root/'sell-side-claim-candidate-checkpoint-latest.json';temporary=pointer.with_suffix('.json.tmp');temporary.write_text(json.dumps({'checkpoint':checkpoint_path.name,'checkpoint_hash':checkpoint['checkpoint_hash']},ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8');temporary.replace(pointer)
 result={'checkpoint_path':str(checkpoint_path),'checkpoint':checkpoint}
 if checkpoint['complete']:
  result['receipt']=_receipt(braw,eraw,rows);result['receipt_path']=str(_write_receipt(runtime_root,result['receipt']))
 return result

def write_sell_side_claim_candidates(batch_path:Path,page_evidence_path:Path,runtime_root:Path)->dict[str,Any]:
 """Persist a runtime-only, content-addressed candidate receipt."""
 receipt=compile_sell_side_claim_candidates(batch_path,page_evidence_path,runtime_root)
 return {'path':str(_write_receipt(runtime_root,receipt)),'receipt':receipt}
