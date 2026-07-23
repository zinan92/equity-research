from __future__ import annotations
import asyncio
import json
import sys
import unittest
from pathlib import Path

PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT))
from data_core import FetchRequest, RecordDomain, YahooChartAdapter, YahooSnapshotAdapter, compare_snapshot, normalize_global_ticker, validate_fetched_payload  # noqa: E402

BODY = json.dumps({"chart":{"result":[{"timestamp":[1782777600,1782864000],"indicators":{"quote":[{"close":[158.2,160.0]}]}}]}}).encode()

class MarketSnapshotTest(unittest.TestCase):
 def test_symbol_normalization(self):
  self.assertEqual(normalize_global_ticker("0700.hk").instrument_id, "HK:00700.HK")
  self.assertEqual(normalize_global_ticker("0700.hk").yahoo_symbol, "0700.HK")
  self.assertEqual(normalize_global_ticker("mog.a").yahoo_symbol, "MOG-A")
  self.assertEqual(normalize_global_ticker("7203.t").currency, "JPY")
  self.assertEqual(normalize_global_ticker("nvda").market, "US")
 def test_chart_records_are_provenance_bound(self):
  adapter=YahooChartAdapter(http_get=lambda _: BODY)
  req=FetchRequest.create(request_id="x",domain=RecordDomain.MARKET,entity_key="NVDA",parameters={"period1":1782777600,"period2":1783036800})
  fetched=asyncio.run(adapter.fetch(req))
  out=validate_fetched_payload(adapter,req,fetched)
  self.assertEqual(len(out.records),2)
  self.assertEqual(out.records[0].payload["metric"],"daily_close")
  self.assertEqual(out.records[0].provenance.raw_hash,out.raw.raw_hash)
 def test_valuation_is_not_fabricated_from_bar(self):
  report=compare_snapshot({"price":100,"mcap":200},{"price":100.4})
  self.assertTrue(report["passed"])
  self.assertEqual(next(x for x in report["rows"] if x["field"]=="mcap")["status"],"missing")
 def test_snapshot_records_current_valuation_with_explicit_provenance(self):
  adapter=YahooSnapshotAdapter(snapshot_getter=lambda _: {"currency":"HKD","last_price":447.8,"previous_close":440.0,"market_cap":4030900000000,"pe_ttm":16.0,"pb":3.1,"peg_trailing":1.31})
  req=FetchRequest.create(request_id="snapshot",domain=RecordDomain.MARKET,entity_key="0700.HK")
  fetched=asyncio.run(adapter.fetch(req))
  out=validate_fetched_payload(adapter,req,fetched)
  by_metric={record.payload["metric"]:record for record in out.records}
  self.assertAlmostEqual(by_metric["change_pct"].payload["value"], (447.8/440-1)*100)
  self.assertIn("market_cap", by_metric)
  self.assertNotIn("market_cap_usd", by_metric)
  self.assertFalse(by_metric["pe_ttm"].payload["historical_reconstruction_eligible"])
  self.assertEqual(by_metric["price"].provenance.raw_hash,out.raw.raw_hash)
if __name__ == "__main__": unittest.main()
