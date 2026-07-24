from __future__ import annotations
import hashlib, io, json, sys, tempfile, unittest
from pathlib import Path
from reportlab.pdfgen import canvas
PRODUCT=Path(__file__).resolve().parents[1]
if str(PRODUCT) not in sys.path: sys.path.insert(0,str(PRODUCT))
from data_core.e4_sell_side_matrix import compile_sell_side_matrices  # noqa: E402
from data_core.e4_sell_side_page_evidence import compile_sell_side_page_evidence  # noqa: E402
def pdf() -> bytes:
    out=io.BytesIO(); c=canvas.Canvas(out,pageCompression=0); c.drawString(72,720,"Page verified research report"); c.showPage(); c.save(); return out.getvalue()
class SellSideMatrixTest(unittest.TestCase):
    def test_compiles_page_verified_rating_and_preserves_missing_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); runtime=root/'runtime'; runtime.mkdir(); raw=pdf(); h=hashlib.sha256(raw).hexdigest(); path=runtime/'r.pdf'; path.write_bytes(raw)
            report={"report_id":"r1","archive_status":"archived_pdf","pdf_raw_hash":h,"runtime_raw_path":str(path),"source_url":"https://pdf.dfcfw.com/pdf/H3_r1_1.pdf","broker":"券商","rating":"买入","published_at":"2026-07-01T00:00:00Z","title":"报告"}
            batch={"schema_version":"e4-s4-sell-side-evidence-batch-v1","data_kind":"real","truth_boundary":{"counts_as_tier_a_or_b":False},"tickers":[{"ticker":"300750.SZ","reports":[report]}]}; bp=root/'batch.json'; bp.write_text(json.dumps(batch),encoding='utf-8')
            page=compile_sell_side_page_evidence(bp,runtime); pp=root/'page.json'; pp.write_text(json.dumps(page),encoding='utf-8')
            result=compile_sell_side_matrices(bp,pp,runtime,as_of='2026-07-25',research_cutoff='2026-07-25T23:59:59Z'); row=result['matrices'][0]
            self.assertEqual((row['status'],row['matrix']['coverage']['report_count']),('compiled',1)); self.assertIn('target_price',row['matrix']['rows'][0]['missing_fields']); self.assertFalse(result['truth_boundary']['counts_as_tier_a_or_b'])
            self.assertEqual((result['research_cutoff'],row['matrix']['research_cutoff']),('2026-07-25T23:59:59Z','2026-07-25T23:59:59Z'))
    def test_rejects_lineage_mismatch_and_missing_rating(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); runtime=root/'runtime'; runtime.mkdir(); batch={"schema_version":"e4-s4-sell-side-evidence-batch-v1","data_kind":"real","truth_boundary":{"counts_as_tier_a_or_b":False},"tickers":[]}; bp=root/'batch.json'; bp.write_text(json.dumps(batch),encoding='utf-8')
            page={"schema_version":"e4-s4-sell-side-page-evidence-v1","data_kind":"real","sell_side_batch_receipt_sha256":"wrong","documents":[]}; pp=root/'page.json'; pp.write_text(json.dumps(page),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'lineage'): compile_sell_side_matrices(bp,pp,runtime,as_of='2026-07-25',research_cutoff='2026-07-25T23:59:59Z')

    def test_rejects_date_only_research_cutoff_and_binds_it_into_receipt_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); runtime=root/'runtime'; runtime.mkdir(); raw=pdf(); h=hashlib.sha256(raw).hexdigest(); path=runtime/'r.pdf'; path.write_bytes(raw)
            report={"report_id":"r1","archive_status":"archived_pdf","pdf_raw_hash":h,"runtime_raw_path":str(path),"source_url":"https://pdf.dfcfw.com/pdf/H3_r1_1.pdf","broker":"券商","rating":"买入","published_at":"2026-07-01T00:00:00Z","title":"报告"}
            batch={"schema_version":"e4-s4-sell-side-evidence-batch-v1","data_kind":"real","truth_boundary":{"counts_as_tier_a_or_b":False},"tickers":[{"ticker":"300750.SZ","reports":[report]}]}; bp=root/'batch.json'; bp.write_text(json.dumps(batch),encoding='utf-8')
            page=compile_sell_side_page_evidence(bp,runtime); pp=root/'page.json'; pp.write_text(json.dumps(page),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'research_cutoff'): compile_sell_side_matrices(bp,pp,runtime,as_of='2026-07-25',research_cutoff='2026-07-25')
            one=compile_sell_side_matrices(bp,pp,runtime,as_of='2026-07-25',research_cutoff='2026-07-25T12:00:00Z')
            replay=compile_sell_side_matrices(bp,pp,runtime,as_of='2026-07-25',research_cutoff='2026-07-25T12:00:00Z')
            two=compile_sell_side_matrices(bp,pp,runtime,as_of='2026-07-25',research_cutoff='2026-07-25T13:00:00Z')
            self.assertEqual(one,replay)
            self.assertNotEqual(one['receipt_hash'],two['receipt_hash'])
