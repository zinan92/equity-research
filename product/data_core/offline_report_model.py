"""Offline report-model receipt bound to existing C1 section contract."""
from __future__ import annotations
import hashlib,json
from dataclasses import asdict,dataclass
from report_contract import build_structure_truth_set
from .dossier_generator import CompanyDossier
from .decision_policy import DecisionReceipt

def _hash(v): return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest()
@dataclass(frozen=True)
class OfflineReportModel:
 ticker:str; dossier_id:str; decision_receipt_hash:str; report_contract:dict; input_hash:str; export_hash:str
def compile_offline_report_model(dossier:CompanyDossier,decision:DecisionReceipt,*,name:str,exchange:str,market:str='CN')->OfflineReportModel:
 if decision.ticker!=dossier.ticker: raise ValueError('decision ticker does not match dossier')
 contract=build_structure_truth_set(ticker=dossier.ticker,name=name,exchange=exchange,market=market)
 payload={'dossier_id':dossier.dossier_id,'decision_receipt_hash':decision.receipt_hash,'contract':contract,'dossier_input_hash':dossier.input_hash}
 ih=_hash(payload); return OfflineReportModel(dossier.ticker,dossier.dossier_id,decision.receipt_hash,contract,ih,_hash({'input_hash':ih,'modules':contract['module_manifest']}))
