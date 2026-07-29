from __future__ import annotations
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from data_core.e4_l1_m4_governance_events import build,validate_receipt
class TestGovernance(unittest.TestCase):
 def test_only_section_four_is_governance_input(self):
  n={'data_kind':'real','ticker':'300750.SZ','receipt_id':'e4-official-narrative-evidence-v1:'+'b'*64,'blocks':[{'status':'resolved','section_path':'第四节 公司治理 > 高级管理人员变动','document_id':'1213027750','raw_hash':'a'*64,'page_number':4,'source_url':'https://static.cninfo.com.cn/finalpage/2022-04-22/1213027750.PDF','text':'高级管理人员发生变动','report_period':'2025FY'},{'status':'resolved','section_path':'第三节 管理层讨论与分析','document_id':'1213027750','raw_hash':'a'*64,'page_number':5,'source_url':'https://static.cninfo.com.cn/finalpage/2022-04-22/1213027750.PDF','text':'董事会讨论经营','report_period':'2025FY'}]}
  r=build(n);validate_receipt(r,ticker='300750.SZ');self.assertEqual(len(r['inputs']['management_record']['records']),1);self.assertEqual(len(r['inputs']['governance_events']['records']),1);self.assertEqual(r['inputs']['event_timeline']['status'],'missing')
 def test_tampered_receipt_fails_closed(self):
  n={'data_kind':'real','ticker':'300750.SZ','receipt_id':'e4-official-narrative-evidence-v1:'+'b'*64,'blocks':[{'status':'resolved','section_path':'第四节 公司治理 > 高级管理人员变动','document_id':'1213027750','raw_hash':'a'*64,'page_number':4,'source_url':'https://static.cninfo.com.cn/finalpage/2022-04-22/1213027750.PDF','text':'高级管理人员发生变动','report_period':'2025FY'}]}
  r=build(n);r['inputs']['management_record']['records'][0]['text']='forged'
  with self.assertRaisesRegex(ValueError,'hash mismatch'): validate_receipt(r,ticker='300750.SZ')
 def test_nonofficial_page_evidence_fails_closed(self):
  n={'data_kind':'real','ticker':'300750.SZ','receipt_id':'e4-official-narrative-evidence-v1:'+'b'*64,'blocks':[{'status':'resolved','section_path':'第四节 公司治理 > 高级管理人员变动','document_id':'1213027750','raw_hash':'a'*64,'page_number':4,'source_url':'https://static.cninfo.com.cn/finalpage/2022-04-22/1213027750.PDF','text':'高级管理人员发生变动','report_period':'2025FY'}]}
  r=build(n);r['inputs']['management_record']['records'][0]['source_url']='https://evil.example/fake.pdf'
  payload={k:v for k,v in r.items() if k not in {'receipt_hash','receipt_id'}}
  import hashlib,json
  r['receipt_hash']=hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True).encode()).hexdigest();r['receipt_id']=r['schema_version']+':'+r['receipt_hash']
  with self.assertRaisesRegex(ValueError,'not official CNINFO'): validate_receipt(r,ticker='300750.SZ')
