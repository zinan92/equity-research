from __future__ import annotations
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'product'))
from data_core.decision_policy import DecisionInput,decide
class PolicyTest(unittest.TestCase):
 def value(self,**changes):
  base=dict(ticker='300750.SZ',context_manifest_hash='a'*64,dossier_id='dossier_a',current_price=100,target_price=130,quality_score=.8,risk_score=.2,liquidity_score=.8,coverage_passed=True,sector_exposure=.1,current_position=.02,cash_weight=.2);base.update(changes);return DecisionInput(**base)
 def test_replay_and_increase_with_caps(self):
  first=decide(self.value());self.assertEqual(first,decide(self.value()));self.assertEqual(first.action,'increase');self.assertLessEqual(first.position_range[1],.1)
 def test_missing_coverage_and_constraints_fail_closed(self):
  for value in (self.value(coverage_passed=False),self.value(target_price=None),self.value(sector_exposure=.25),self.value(cash_weight=.05)):
   r=decide(value);self.assertEqual(r.action,'no_action');self.assertIsNone(r.position_range)
 def test_negative_upside_reduces(self): self.assertEqual(decide(self.value(target_price=80)).action,'reduce')
if __name__=='__main__':unittest.main()
