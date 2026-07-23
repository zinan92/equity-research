from __future__ import annotations
import asyncio
import json
import sys
import unittest
from pathlib import Path

PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT))
from data_core import FetchRequest, RecordDomain, YahooChartAdapter, compare_snapshot, normalize_global_ticker, validate_fetched_payload  # noqa: E402

BODY = json.dumps({"chart":{"result":[{"timestamp":[1782777600,1782864000],"indicators":{"quote":[{"close":[158.2,160.0]}]}}]}}).encode()

class MarketSnapshotTest(unittest.TestCase):
 def test_symbol_normalization(self):
  self.assertEqual(normalize_global_ticker("0700.hk").instrument_id, "HK:00700.HK")
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
if __name__ == "__main__": unittest.main()
