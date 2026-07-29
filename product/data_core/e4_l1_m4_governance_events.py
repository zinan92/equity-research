"""Official narrative-backed CATL governance inputs and explicit event gaps."""
from __future__ import annotations
import hashlib,json
import re
from datetime import datetime,timezone
from typing import Any,Mapping

SCHEMA='e4-l1-m4-governance-events-v1'
_HASH=re.compile(r'^[0-9a-f]{64}$')
_DOCUMENT_ID=re.compile(r'^(?:\d{10}|official-filing:[^:]+:\d{10})$')
_NARRATIVE_RECEIPT=re.compile(r'^e4-official-narrative-evidence-v1:[0-9a-f]{64}$')
_CNINFO_PREFIX='https://static.cninfo.com.cn/finalpage/'
def _cite(b:Mapping[str,Any])->dict[str,Any]: return {k:b[k] for k in ('document_id','raw_hash','page_number','source_url','section_path','text','report_period')}
def validate_receipt(receipt:Mapping[str,Any],*,ticker:str)->None:
 if receipt.get('schema_version')!=SCHEMA or receipt.get('data_kind')!='real': raise ValueError('real governance receipt required')
 if str(receipt.get('ticker','')).upper()!=ticker.upper(): raise ValueError('governance receipt ticker mismatch')
 payload={k:v for k,v in receipt.items() if k not in {'receipt_hash','receipt_id'}}
 expected=hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
 if receipt.get('receipt_hash')!=expected or receipt.get('receipt_id')!=SCHEMA+':'+expected: raise ValueError('governance receipt hash mismatch')
 boundary=receipt.get('truth_boundary') or {}
 if boundary.get('official_pdf_governance_only') is not True or boundary.get('counts_as_tier_a_or_b') is not False: raise ValueError('governance truth boundary mismatch')
 if not _NARRATIVE_RECEIPT.fullmatch(str(receipt.get('source_narrative_receipt') or '')): raise ValueError('governance source narrative identity mismatch')
 for key in ('management_record','governance_events'):
  value=(receipt.get('inputs') or {}).get(key) or {}
  if value.get('status')=='available':
   records=value.get('records')
   if not isinstance(records,list) or not records: raise ValueError('available governance input has no records')
   if any(any(not row.get(field) for field in ('document_id','raw_hash','page_number','source_url','text','report_period')) for row in records): raise ValueError('governance record lacks page evidence')
   if any(not _DOCUMENT_ID.fullmatch(str(row['document_id'])) or not _HASH.fullmatch(str(row['raw_hash'])) or not str(row['source_url']).startswith(_CNINFO_PREFIX) or not str(row['source_url']).endswith('.PDF') or not isinstance(row['page_number'],int) or row['page_number']<1 for row in records): raise ValueError('governance record is not official CNINFO page evidence')
def build(narrative:Mapping[str,Any])->dict[str,Any]:
 if narrative.get('data_kind')!='real' or narrative.get('ticker')!='300750.SZ': raise ValueError('real CATL narrative receipt required')
 rows=[b for b in narrative.get('blocks',[]) if b.get('status')=='resolved' and str(b.get('section_path','')).startswith('第四节 公司治理')]
 management=[_cite(b) for b in rows if any(x in str(b.get('section_path',''))+str(b.get('text','')) for x in ('董事','监事','高级管理','管理层'))]
 changes=[_cite(b) for b in rows if any(x in str(b.get('section_path',''))+str(b.get('text','')) for x in ('变动','聘任','离任','任职'))]
 out={'schema_version':SCHEMA,'data_kind':'real','ticker':'300750.SZ','generated_at':datetime.now(timezone.utc).replace(microsecond=0).isoformat(),'source_narrative_receipt':narrative['receipt_id'],'inputs':{'management_record':{'status':'available','records':management},'governance_events':{'status':'available','records':changes},'macro_exposures':{'status':'missing','reason':'no_official_macro_source'},'policy_events':{'status':'missing','reason':'event_intelligence_has_no_configured_official_monitor'},'event_timeline':{'status':'missing','reason':'event_intelligence_has_no_configured_official_monitor'}},'truth_boundary':{'official_pdf_governance_only':True,'event_intelligence_not_substituted_with_news':True,'counts_as_tier_a_or_b':False}}
 out['receipt_hash']=hashlib.sha256(json.dumps(out,ensure_ascii=False,sort_keys=True).encode()).hexdigest();out['receipt_id']=SCHEMA+':'+out['receipt_hash'];return out
