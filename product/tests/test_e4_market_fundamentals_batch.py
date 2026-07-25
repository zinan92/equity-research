from __future__ import annotations
import json, sys, tempfile, time
from pathlib import Path
import unittest
PRODUCT=Path(__file__).resolve().parents[1]
if str(PRODUCT) not in sys.path: sys.path.insert(0,str(PRODUCT))
from data_core.e4_market_fundamentals_batch import _collect_with_component_retries, _packet_row, run_market_fundamentals_batch  # noqa: E402

REQUIRED=("quote","daily_bars","fundamentals","balance_sheet","income_statement","cash_flow")
def identity(): return {"schema_version":"ashare-security-master-v1","data_kind":"real","truth_boundary":{"identity_only":True},"records":[{"ticker":f"{i:06d}.SZ"} for i in range(100)]}
def official(): return {"schema_version":"e4-s4-official-evidence-batch-v1","data_kind":"real","truth_boundary":{"counts_as_report_model_coverage":False},"tickers":[]}
def good_worker(ticker, q):
    q.put({"status":"ok","summary":{"instrument":{"ticker":ticker},"data_gaps":[],"sources":{k:{"data_kind":"real","publishable":True,"selected_source":k,"raw_hash":"a"*64,"manifest_hash":"b"*64,"known_at":"2026-07-24T00:00:00Z"} for k in REQUIRED}}})
def valued_worker(ticker, q):
    q.put({"status":"ok","summary":{"instrument":{"ticker":ticker},"data_gaps":[],"quote":{"last_price":10.2,"change_pct":1.1,"observed_at":"2026-07-24T00:00:00Z","unrelated":"not-copied"},"daily_bars":[{"trade_date":"2026-07-24","adjustment":"qfq","open":10,"close":10.2,"high":10.3,"low":9.9,"volume":100,"unrelated":"not-copied"}],"fundamentals":[{"report_period":"2026-03-31","announced_at":"2026-04-28","revenue":1000,"net_profit_parent":100,"total_assets":3000,"total_liabilities":1200,"total_equity":1800,"total_operating_income":800,"net_profit_parent_statement":90,"net_cash_operating":110,"unrelated":"not-copied"}],"sources":{k:{"data_kind":"real","publishable":True,"selected_source":k,"raw_hash":"a"*64,"manifest_hash":"b"*64,"known_at":"2026-07-24T00:00:00Z"} for k in REQUIRED}}})
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
   self.assertEqual(r['receipt']['tickers'][0]['display_facts'],{})
   self.assertIn('market_display_facts_missing_validated_values',r['receipt']['tickers'][0]['display_fact_blockers'])
 def test_timeout_isolated_and_nonreal_official_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);i,o=self.paths(root); started=time.monotonic()
   r=run_market_fundamentals_batch(i,o,root/'runtime',max_tickers=2,inter_ticker_delay_seconds=0,collector_timeout_seconds=.5,worker=hung_then_good_worker)
   self.assertLess(time.monotonic()-started,2.5); self.assertEqual(r['receipt']['tickers'][0]['blockers'],['collector_timeout']); self.assertTrue(r['receipt']['tickers'][1]['market_available'])
   bad=official();bad['data_kind']='fixture';o.write_text(json.dumps(bad))
   with self.assertRaisesRegex(ValueError,'real E4 official'): run_market_fundamentals_batch(i,o,root/'bad',max_tickers=1,worker=good_worker)

 def test_display_facts_are_bounded_and_source_bound(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);i,o=self.paths(root)
   row=run_market_fundamentals_batch(i,o,root/'runtime',max_tickers=1,inter_ticker_delay_seconds=0,worker=valued_worker)['receipt']['tickers'][0]
   self.assertEqual(row['display_facts']['market']['quote']['last_price'],10.2)
   self.assertNotIn('unrelated',row['display_facts']['market']['quote'])
   self.assertEqual(row['display_facts']['fundamentals']['latest_period']['report_period'],'2026-03-31')
   self.assertEqual(row['display_facts']['fundamentals']['source_components'],['fundamentals','balance_sheet','income_statement','cash_flow'])
   self.assertEqual(row['display_fact_blockers'],[])

 def test_component_gaps_are_typed_and_retried_without_fallback(self):
  summary={"instrument":{"ticker":"000001.SZ"},"data_gaps":[{"domain":"income_statement","reason":"transport_timeout"}],"sources":{k:{"data_kind":"real","publishable":True,"selected_source":k,"raw_hash":"a"*64,"manifest_hash":"b"*64,"known_at":"2026-07-24T00:00:00Z"} for k in REQUIRED}}
  summary['sources']['income_statement']={"data_kind":"unknown","publishable":False,"selected_source":"income_statement"}
  row=_packet_row('000001.SZ',summary)
  self.assertEqual(row['status'],'partial');self.assertEqual(row['component_blockers']['income_statement'],['non_real_source_data','transport_timeout']);self.assertNotIn('fundamentals',row['display_facts'])
  rows=iter([row,{**row,"status":"captured","market_available":True,"fundamentals_available":True,"component_blockers":{},"blockers":[]}])
  replay=_collect_with_component_retries('000001.SZ',1,good_worker,max_attempts=2,collect_once=lambda *_:next(rows))
  self.assertEqual(replay['collection_attempts'],2);self.assertEqual(replay['attempt_history'][0]['component_blockers']['income_statement'],['non_real_source_data','transport_timeout'])

 def test_interrupted_run_resumes_checkpoint_without_recollecting(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);i,o=self.paths(root)
   def first_sleep(_seconds): raise KeyboardInterrupt()
   with self.assertRaises(KeyboardInterrupt):
    run_market_fundamentals_batch(i,o,root/'runtime',max_tickers=3,inter_ticker_delay_seconds=1,worker=good_worker,sleep=first_sleep)
   pointer=json.loads((root/'runtime'/'market-fundamentals-batch-latest.json').read_text())
   self.assertEqual(pointer['state'],'in_progress')
   checkpoint=json.loads((root/'runtime'/'market-fundamentals-batch-checkpoint.json').read_text())
   self.assertEqual([row['ticker'] for row in checkpoint['tickers']],['000000.SZ'])
   result=run_market_fundamentals_batch(i,o,root/'runtime',max_tickers=3,inter_ticker_delay_seconds=1,worker=good_worker,sleep=lambda _seconds:None)
   self.assertEqual(result['receipt']['counts']['requested'],3)
   self.assertEqual(json.loads((root/'runtime'/'market-fundamentals-batch-latest.json').read_text())['state'],'completed')

 def test_checkpoint_config_mismatch_fails_closed(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);i,o=self.paths(root)
   with self.assertRaises(KeyboardInterrupt):
    run_market_fundamentals_batch(i,o,root/'runtime',max_tickers=2,inter_ticker_delay_seconds=1,worker=good_worker,sleep=lambda _seconds:(_ for _ in ()).throw(KeyboardInterrupt()))
   with self.assertRaisesRegex(ValueError,'does not match'):
    run_market_fundamentals_batch(i,o,root/'runtime',max_tickers=3,inter_ticker_delay_seconds=1,worker=good_worker,sleep=lambda _seconds:None)
