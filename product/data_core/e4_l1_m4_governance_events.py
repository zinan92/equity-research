"""Official narrative-backed CATL governance inputs and explicit event gaps."""
from __future__ import annotations
import hashlib,json
from datetime import datetime,timezone
from typing import Any,Mapping

SCHEMA='e4-l1-m4-governance-events-v1'
def _cite(b:Mapping[str,Any])->dict[str,Any]: return {k:b[k] for k in ('document_id','raw_hash','page_number','source_url','section_path','text','report_period')}
def build(narrative:Mapping[str,Any])->dict[str,Any]:
 if narrative.get('data_kind')!='real' or narrative.get('ticker')!='300750.SZ': raise ValueError('real CATL narrative receipt required')
 rows=[b for b in narrative.get('blocks',[]) if b.get('status')=='resolved' and str(b.get('section_path','')).startswith('第四节 公司治理')]
 management=[_cite(b) for b in rows if any(x in str(b.get('section_path',''))+str(b.get('text','')) for x in ('董事','监事','高级管理','管理层'))]
 changes=[_cite(b) for b in rows if any(x in str(b.get('section_path',''))+str(b.get('text','')) for x in ('变动','聘任','离任','任职'))]
 out={'schema_version':SCHEMA,'data_kind':'real','ticker':'300750.SZ','generated_at':datetime.now(timezone.utc).replace(microsecond=0).isoformat(),'source_narrative_receipt':narrative['receipt_id'],'inputs':{'management_record':{'status':'available','records':management},'governance_events':{'status':'available','records':changes},'macro_exposures':{'status':'missing','reason':'no_official_macro_source'},'policy_events':{'status':'missing','reason':'event_intelligence_has_no_configured_official_monitor'},'event_timeline':{'status':'missing','reason':'event_intelligence_has_no_configured_official_monitor'}},'truth_boundary':{'official_pdf_governance_only':True,'event_intelligence_not_substituted_with_news':True,'counts_as_tier_a_or_b':False}}
 out['receipt_hash']=hashlib.sha256(json.dumps(out,ensure_ascii=False,sort_keys=True).encode()).hexdigest();out['receipt_id']=SCHEMA+':'+out['receipt_hash'];return out
