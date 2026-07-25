"""Conservative page-bound candidate extraction from parsed sell-side PDFs."""
from __future__ import annotations
import hashlib,json,re
from pathlib import Path
from typing import Any,Mapping
from .contracts import digest
from .document_intelligence import parse_pdf_document
from .e4_sell_side_page_evidence import _inside

E4_SELL_SIDE_CLAIM_CANDIDATE_SCHEMA_VERSION='e4-s4-sell-side-claim-candidates-v1'
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
def compile_sell_side_claim_candidates(batch_path:Path,page_evidence_path:Path,runtime_root:Path)->dict[str,Any]:
 braw,batch=_load(batch_path,'e4-s4-sell-side-evidence-batch-v1');eraw,evidence=_load(page_evidence_path,'e4-s4-sell-side-page-evidence-v1')
 if evidence.get('sell_side_batch_receipt_sha256')!=hashlib.sha256(braw).hexdigest():raise ValueError('page evidence does not match sell-side batch lineage')
 parsed={r['report_id']:r for r in evidence.get('documents',[]) if r.get('status')=='parsed'};rows=[]
 for tr in batch.get('tickers',[]):
  for report in tr.get('reports',[]):
   rid=str(report.get('report_id') or '');ev=parsed.get(rid);base={'ticker':str(tr.get('ticker') or '').upper(),'report_id':rid}
   if report.get('archive_status')!='archived_pdf' or ev is None:rows.append({**base,'status':'blocked','blockers':['page_verified_pdf_unavailable']});continue
   try:
    raw=_inside(runtime_root,str(report['runtime_raw_path'])).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=report.get('pdf_raw_hash'):raise ValueError('raw hash mismatch')
    doc=parse_pdf_document(f'sell-side-report:{rid}',raw,expected_raw_hash=report['pdf_raw_hash'])
    if ev.get('parse_id')!=doc.parse_id or ev.get('parser_version')!=doc.parser_version:raise ValueError('parser identity mismatch')
    candidates=[]
    pages={p.page_number:p for p in doc.pages}
    for chunk in doc.chunks:candidates+=_candidate(report,{'page_number':chunk.page_number,'parser_version':doc.parser_version},chunk.__dict__,chunk.text)
    rows.append({**base,'status':'compiled','candidates':candidates})
   except Exception as exc:rows.append({**base,'status':'blocked','blockers':['claim_candidate_input_invalid'],'error':type(exc).__name__})
 receipt={'schema_version':E4_SELL_SIDE_CLAIM_CANDIDATE_SCHEMA_VERSION,'data_kind':'real','batch_receipt_sha256':hashlib.sha256(braw).hexdigest(),'page_evidence_receipt_sha256':hashlib.sha256(eraw).hexdigest(),'documents':rows,'counts':{'compiled':sum(x['status']=='compiled' for x in rows),'candidates':sum(len(x.get('candidates',[])) for x in rows),'blocked':sum(x['status']=='blocked' for x in rows)},'truth_boundary':{'candidates_are_not_accepted_claims':True,'counts_as_tier_a_or_b':False,'counts_as_numeric_page_audit':False,'counts_as_position_or_target':False}}
 receipt['receipt_hash']=digest(receipt);return receipt
