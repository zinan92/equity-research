from __future__ import annotations
import hashlib, sys, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'product'))
from data_core.company_positions import CompanyPosition
from data_core.dossier_generator import compile_dossier
from data_core.evidence_gate import EvidenceCandidate,EvidenceGatePolicy,EvidenceRequirement,EvidenceRole,build_context_pack,build_evidence_set
from data_core.industry_catalysts import build_catalyst_profiles
from data_core.industry_graph import EvidenceCapture, audited_candidates

def sha(v): return hashlib.sha256(v.encode()).hexdigest()
def context(raw):
 c=EvidenceCandidate('filing','300750.SZ','filings',EvidenceRole.PRIMARY,'cninfo','issuer','official',False,'accepted','2026-07-23T00:00:00Z','2026-07-22T00:00:00Z',sha('m'),raw,sha('r'))
 return build_context_pack(build_evidence_set(ticker='300750.SZ',candidates=(c,),policy=EvidenceGatePolicy(as_of='2026-07-24T00:00:00Z',requirements=(EvidenceRequirement('filings',min_primary=1),))))
class DossierTest(unittest.TestCase):
 def test_replays_and_keeps_missing_catalysts_explicit(self):
  raw='a'*64; pack=context(raw)
  pos=CompanyPosition('300750.SZ','宁德时代','A','ai-compute/chip-design/gpu','supplier','产品','accepted',('https://official.example/a.pdf',2,raw))
  profile=build_catalyst_profiles((),as_of='2026-07-24')[0]
  d=compile_dossier(pack,pos,profile)
  self.assertEqual(d,compile_dossier(pack,pos,profile)); self.assertEqual(d.sections[3].status,'missing_evidence'); self.assertEqual(d.cost_units,0)
 def test_rejects_unaccepted_position_or_raw(self):
  raw='a'*64; profile=build_catalyst_profiles((),as_of='2026-07-24')[0]
  with self.assertRaisesRegex(ValueError,'accepted'):
   compile_dossier(context(raw),CompanyPosition('300750.SZ','x','A',profile.segment_id,'r','p'),profile)
  with self.assertRaisesRegex(ValueError,'not accepted'):
   compile_dossier(context(raw),CompanyPosition('300750.SZ','x','A',profile.segment_id,'r','p','accepted',('https://x',1,'b'*64)),profile)
 def test_three_company_fixture_contract_uses_one_schema(self):
  profile=build_catalyst_profiles((),as_of='2026-07-24')[0]
  dossiers=[]
  for ticker,name,raw in [('300750.SZ','宁德时代','a'*64),('600519.SH','贵州茅台','b'*64),('601398.SH','工商银行','c'*64)]:
   candidate=EvidenceCandidate('filing',ticker,'filings',EvidenceRole.PRIMARY,'cninfo','issuer','official',False,'accepted','2026-07-23T00:00:00Z','2026-07-22T00:00:00Z',sha('m'+ticker),raw,sha('r'+ticker))
   pack=build_context_pack(build_evidence_set(ticker=ticker,candidates=(candidate,),policy=EvidenceGatePolicy(as_of='2026-07-24T00:00:00Z',requirements=(EvidenceRequirement('filings',min_primary=1),))))
   dossiers.append(compile_dossier(pack,CompanyPosition(ticker,name,'A',profile.segment_id,'supplier','产品','accepted',('https://official.example/'+ticker,2,raw)),profile))
  self.assertEqual({tuple(s.name for s in d.sections) for d in dossiers},{('identity','industry_position','evidence_coverage','catalysts','unknowns','method')})
  self.assertEqual(len({d.dossier_id for d in dossiers}),3)
if __name__=='__main__': unittest.main()
