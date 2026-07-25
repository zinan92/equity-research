"""Fail-closed, product-safe projection of a spot-audit assignment receipt."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any,Mapping
from data_core.contracts import digest
from data_core.ashare import normalize_ashare_ticker
from data_core.e4_spot_audit_assignments import E4_SPOT_AUDIT_ASSIGNMENTS_SCHEMA_VERSION
class SpotAuditAssignmentReadError(ValueError):pass
def load_assignment(ticker:str,path:Path)->dict[str,Any]:
 try: normalized=normalize_ashare_ticker(ticker).ticker; receipt=json.loads(path.read_text(encoding='utf-8'))
 except Exception as exc:raise SpotAuditAssignmentReadError('audit assignment is unavailable') from exc
 if receipt.get('schema_version')!=E4_SPOT_AUDIT_ASSIGNMENTS_SCHEMA_VERSION or receipt.get('data_kind')!='runtime_only_audit' or receipt.get('receipt_hash')!=digest({k:v for k,v in receipt.items() if k!='receipt_hash'}):raise SpotAuditAssignmentReadError('audit assignment receipt is invalid')
 rows=[x for x in receipt.get('assignments',[]) if isinstance(x,Mapping) and x.get('ticker')==normalized]
 if len(rows)>1:raise SpotAuditAssignmentReadError('audit assignment is ambiguous')
 if not rows:return {'ticker':normalized,'status':'unavailable'}
 row=rows[0]
 allowed=('ticker','report_model_hash','document_identity','numeric_check','page_citation_check','financial_context','review_status')
 return {'status':'available','receipt_hash':receipt['receipt_hash'],**{k:row[k] for k in allowed if k in row}}
