from __future__ import annotations
import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from data_core.e4_l1_m3_sell_side_admission import probe_catl_sell_side_admission

class AdmissionTest(unittest.TestCase):
 def test_aggregator_probe_is_never_admitted(self):
  class Outcome:
   publishable=False;attempts=()
  class Runtime:
   async def run(self,*_): return Outcome()
  with patch('data_core.e4_l1_m3_sell_side_admission.build_ths_forecast_runtime',return_value=Runtime()):
   r=probe_catl_sell_side_admission()
  self.assertEqual(r['inputs']['broker_estimates']['reason'],'source_policy_inadmissible_aggregator')
  self.assertEqual(r['inputs']['consensus_history']['status'],'missing')
  self.assertEqual(r['admitted_c1_inputs'],{})
