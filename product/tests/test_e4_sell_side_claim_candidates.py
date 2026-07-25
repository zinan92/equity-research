from __future__ import annotations
import hashlib,io,json,sys,tempfile,unittest
from pathlib import Path
from reportlab.pdfgen import canvas
PRODUCT=Path(__file__).resolve().parents[1]
if str(PRODUCT) not in sys.path:sys.path.insert(0,str(PRODUCT))
from data_core.e4_sell_side_page_evidence import compile_sell_side_page_evidence
from data_core.e4_sell_side_claim_candidates import compile_sell_side_claim_candidates,run_sell_side_claim_candidate_slice,write_sell_side_claim_candidates
def pdf():
 b=io.BytesIO();c=canvas.Canvas(b,pageCompression=0);c.drawString(72,720,'We expect revenue growth and margin improvement.');c.showPage();c.save();return b.getvalue()
class Claims(unittest.TestCase):
 def test_page_bound_candidates_are_deterministic_and_non_actionable(self):
  with tempfile.TemporaryDirectory() as d:
   r=Path(d);raw=pdf();h=hashlib.sha256(raw).hexdigest();p=r/'r.pdf';p.write_bytes(raw);report={'report_id':'r','archive_status':'archived_pdf','pdf_raw_hash':h,'runtime_raw_path':str(p),'source_url':'https://pdf.dfcfw.com/r.pdf'};batch={'schema_version':'e4-s4-sell-side-evidence-batch-v1','data_kind':'real','truth_boundary':{'counts_as_tier_a_or_b':False},'tickers':[{'ticker':'300750.SZ','reports':[report]}]};bp=r/'b.json';bp.write_text(json.dumps(batch));page=compile_sell_side_page_evidence(bp,r);pp=r/'p.json';pp.write_text(json.dumps(page));a=compile_sell_side_claim_candidates(bp,pp,r);b=compile_sell_side_claim_candidates(bp,pp,r);self.assertEqual(a,b);self.assertTrue(a['documents'][0]['candidates']);c=a['documents'][0]['candidates'][0];self.assertEqual(c['review_status'],'unreviewed');self.assertFalse(a['truth_boundary']['counts_as_tier_a_or_b'])
 def test_writer_persists_content_addressed_receipt_and_latest_pointer(self):
  with tempfile.TemporaryDirectory() as d:
   r=Path(d);raw=pdf();h=hashlib.sha256(raw).hexdigest();p=r/'r.pdf';p.write_bytes(raw);report={'report_id':'r','archive_status':'archived_pdf','pdf_raw_hash':h,'runtime_raw_path':str(p),'source_url':'https://pdf.dfcfw.com/r.pdf'};batch={'schema_version':'e4-s4-sell-side-evidence-batch-v1','data_kind':'real','truth_boundary':{'counts_as_tier_a_or_b':False},'tickers':[{'ticker':'300750.SZ','reports':[report]}]};bp=r/'b.json';bp.write_text(json.dumps(batch));pp=r/'p.json';pp.write_text(json.dumps(compile_sell_side_page_evidence(bp,r)));result=write_sell_side_claim_candidates(bp,pp,r);pointer=json.loads((r/'sell-side-claim-candidates-latest.json').read_text());self.assertTrue(Path(result['path']).is_file());self.assertEqual(pointer['receipt_hash'],result['receipt']['receipt_hash'])
 def test_bounded_slice_resumes_without_reprocessing_first_document(self):
  with tempfile.TemporaryDirectory() as d:
   r=Path(d);raw=pdf();h=hashlib.sha256(raw).hexdigest();paths=[]
   for rid in ('r1','r2'):
    p=r/f'{rid}.pdf';p.write_bytes(raw);paths.append({'report_id':rid,'archive_status':'archived_pdf','pdf_raw_hash':h,'runtime_raw_path':str(p),'source_url':f'https://pdf.dfcfw.com/{rid}.pdf'})
   batch={'schema_version':'e4-s4-sell-side-evidence-batch-v1','data_kind':'real','truth_boundary':{'counts_as_tier_a_or_b':False},'tickers':[{'ticker':'300750.SZ','reports':paths}]};bp=r/'b.json';bp.write_text(json.dumps(batch));pp=r/'p.json';pp.write_text(json.dumps(compile_sell_side_page_evidence(bp,r)))
   first=run_sell_side_claim_candidate_slice(bp,pp,r,limit=1);self.assertFalse(first['checkpoint']['complete']);self.assertEqual(first['checkpoint']['next_index'],1)
   second=run_sell_side_claim_candidate_slice(bp,pp,r,limit=1);self.assertTrue(second['checkpoint']['complete']);self.assertEqual(second['checkpoint']['next_index'],2);self.assertEqual(second['receipt']['counts']['compiled'],2);self.assertTrue(Path(second['receipt_path']).is_file())
