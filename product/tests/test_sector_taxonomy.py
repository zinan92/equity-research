from __future__ import annotations
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'product'))
from data_core.sector_taxonomy import build_cross_sector_taxonomy,taxonomy_receipt,validate_position_segment
class TaxonomyTest(unittest.TestCase):
 def test_separate_stable_namespaces(self):
  rows=build_cross_sector_taxonomy();self.assertEqual([r.segment_id for r in rows],['cross-sector/battery','cross-sector/consumer','cross-sector/bank']);self.assertEqual(validate_position_segment('ai-compute/chip-design/gpu'),'ai-compute');self.assertEqual(validate_position_segment('cross-sector/bank'),'cross-sector')
 def test_unknown_segment_fails_closed(self):
  with self.assertRaisesRegex(ValueError,'unknown'):validate_position_segment('ai-compute/consumer/baijiu')
  self.assertEqual(taxonomy_receipt()['segment_count'],3)
if __name__=='__main__':unittest.main()
