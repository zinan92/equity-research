from __future__ import annotations
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'product'))
from data_core.dossier_generator import CompanyDossier,DossierSection
from data_core.decision_policy import DecisionReceipt
from data_core.offline_report_model import compile_offline_report_model
class ModelTest(unittest.TestCase):
 def dossier(self,ticker='300750.SZ'):
  sections=tuple(DossierSection(n,'missing_evidence',{}) for n in ('identity','industry_position','evidence_coverage','catalysts','unknowns','method'))
  return CompanyDossier('dossier_'+'a'*40,'park-company-dossier-v1',ticker,'2026-07-24T00:00:00Z','b'*64,'a'*64,sections,'deterministic_template',None,0)
 def decision(self,ticker='300750.SZ'): return DecisionReceipt(ticker,'no_action',None,None,('gap',),'c'*64,'d'*64)
 def test_c1_contract_replays_with_eight_sections(self):
  m=compile_offline_report_model(self.dossier(),self.decision(),name='宁德时代',exchange='深交所')
  self.assertEqual(m,compile_offline_report_model(self.dossier(),self.decision(),name='宁德时代',exchange='深交所'))
  self.assertEqual(len(m.report_contract['module_manifest']),8)
 def test_ticker_mismatch_is_rejected(self):
  with self.assertRaisesRegex(ValueError,'ticker'): compile_offline_report_model(self.dossier(),self.decision('600519.SH'),name='宁德时代',exchange='深交所')
if __name__=='__main__':unittest.main()
