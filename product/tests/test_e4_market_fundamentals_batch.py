from __future__ import annotations
import json, sys, tempfile, time
from pathlib import Path
import unittest
PRODUCT=Path(__file__).resolve().parents[1]
if str(PRODUCT) not in sys.path: sys.path.insert(0,str(PRODUCT))
from data_core.e4_market_fundamentals_batch import run_market_fundamentals_batch  # noqa: E402

REQUIRED=("quote","daily_bars","fundamentals","balance_sheet","income_statement","cash_flow")
def identity(): return {"schema_version":"ashare-security-master-v1","data_kind":"real","truth_boundary":{"identity_only":True},"records":[{"ticker":f"{i:06d}.SZ"} for i in range(100)]}
def official(): return {"schema_version":"e4-s4-official-evidence-batch-v1","data_kind":"real","truth_boundary":{"counts_as_report_model_coverage":False},"tickers":[]}
def good_worker(ticker, q):
    q.put({"status":"ok","summary":{"instrument":{"ticker":ticker},"data_gaps":[],"sources":{k:{"data_kind":"real","publishable":True,"selected_source":k,"raw_hash":"a"*64,"manifest_hash":"b"*64,"known_at":"2026-07-24T00:00:00Z"} for k in REQUIRED}}})
def hung_then_good_worker(ticker,q):
    if ticker=="000000.SZ": time.sleep(2); return
    good_worker(ticker,q)

class MarketFundamentalsBatchTest(unittest.TestCase):
 def paths(self,root):
  i,o=root/'identity.json',root/'official.json'; i.write_text(json.dumps(identity()));o.write_text(json.dumps(official()));return i,o
 def test_real_packet_receipt_is_input_only(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);i,o=self.paths(root)
   r=run_market_fundamentals_batch(i,o,root/'runtime',max_tickers=2,inter_ticker_delay_seconds=0,worker=good_worker)
   self.assertEqual(r['receipt']['counts'],{'requested':2,'market_available':2,'fundamentals_available':2,'failed':0})
   self.assertFalse(r['receipt']['truth_boundary']['counts_as_tier_a_or_b'])
 def test_timeout_isolated_and_nonreal_official_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);i,o=self.paths(root); started=time.monotonic()
   r=run_market_fundamentals_batch(i,o,root/'runtime',max_tickers=2,inter_ticker_delay_seconds=0,collector_timeout_seconds=.5,worker=hung_then_good_worker)
   self.assertLess(time.monotonic()-started,2.5); self.assertEqual(r['receipt']['tickers'][0]['blockers'],['collector_timeout']); self.assertTrue(r['receipt']['tickers'][1]['market_available'])
   bad=official();bad['data_kind']='fixture';o.write_text(json.dumps(bad))
   with self.assertRaisesRegex(ValueError,'real E4 official'): run_market_fundamentals_batch(i,o,root/'bad',max_tickers=1,worker=good_worker)
