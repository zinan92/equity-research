from __future__ import annotations
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from data_core.e4_l1_m4_governance_events import build
class TestGovernance(unittest.TestCase):
 def test_only_section_four_is_governance_input(self):
  n={'data_kind':'real','ticker':'300750.SZ','receipt_id':'n:1','blocks':[{'status':'resolved','section_path':'第四节 公司治理 > 高级管理人员变动','document_id':'d','raw_hash':'a'*64,'page_number':4,'source_url':'https://official/x','text':'高级管理人员发生变动','report_period':'2025FY'},{'status':'resolved','section_path':'第三节 管理层讨论与分析','document_id':'d','raw_hash':'a'*64,'page_number':5,'source_url':'https://official/x','text':'董事会讨论经营','report_period':'2025FY'}]}
  r=build(n);self.assertEqual(len(r['inputs']['management_record']['records']),1);self.assertEqual(len(r['inputs']['governance_events']['records']),1);self.assertEqual(r['inputs']['event_timeline']['status'],'missing')
