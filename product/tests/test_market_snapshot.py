from __future__ import annotations
import asyncio
import json
import sys
import unittest
from pathlib import Path

PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT))
from data_core import FetchRequest, HISTORICAL_MARKET_FIELD_POLICY, RecordDomain, SecCompanyFactsAdapter, YahooChartAdapter, YahooFxAdapter, YahooSnapshotAdapter, compare_snapshot, derive_historical_valuation, normalize_global_ticker, sec_point_in_time_inputs, validate_fetched_payload  # noqa: E402

BODY = json.dumps({"chart":{"result":[{"timestamp":[1782777600,1782864000],"indicators":{"quote":[{"close":[158.2,160.0]}]}}]}}).encode()
SEC_BODY = json.dumps({
 "cik":1045810,"entityName":"Example Corp","facts":{
  "dei":{"EntityCommonStockSharesOutstanding":{"units":{"shares":[
   {"end":"2025-05-15","val":100,"form":"10-Q","filed":"2025-05-20","accn":"s1"},
   {"end":"2026-05-15","val":100,"form":"10-Q","filed":"2026-05-20","accn":"s2"}]}}},
  "us-gaap":{
   "StockholdersEquity":{"units":{"USD":[
    {"end":"2025-03-31","val":18,"form":"10-Q","filed":"2025-05-20","accn":"e1"},
    {"end":"2026-03-31","val":20,"form":"10-Q","filed":"2026-05-20","accn":"e2"}]}},
   "NetIncomeLoss":{"units":{"USD":[
    {"start":"2024-01-01","end":"2024-12-31","val":8,"form":"10-K","filed":"2025-02-20","accn":"a1"},
    {"start":"2024-01-01","end":"2024-03-31","val":1,"form":"10-Q","filed":"2024-05-10","accn":"q0"},
    {"start":"2025-01-01","end":"2025-03-31","val":2,"form":"10-Q","filed":"2025-05-20","accn":"q1"},
    {"start":"2025-01-01","end":"2025-12-31","val":10,"form":"10-K","filed":"2026-02-20","accn":"a2"},
    {"start":"2025-01-01","end":"2025-03-31","val":2,"form":"10-Q","filed":"2026-05-20","accn":"q1-repeat"},
    {"start":"2026-01-01","end":"2026-03-31","val":4,"form":"10-Q","filed":"2026-05-20","accn":"q2"}]}}
  }
 }
}).encode()

class MarketSnapshotTest(unittest.TestCase):
 def test_symbol_normalization(self):
  self.assertEqual(normalize_global_ticker("0700.hk").instrument_id, "HK:00700.HK")
  self.assertEqual(normalize_global_ticker("0700.hk").yahoo_symbol, "0700.HK")
  self.assertEqual(normalize_global_ticker("mog.a").yahoo_symbol, "MOG-A")
  self.assertEqual(normalize_global_ticker("7203.t").currency, "JPY")
  self.assertEqual(normalize_global_ticker("nvda").market, "US")
 def test_historical_field_policy_has_primary_fallback_or_gap_for_every_market(self):
  self.assertEqual(set(HISTORICAL_MARKET_FIELD_POLICY),{"price","chg","mcap","mcap_usd","pe","pb","peg"})
  cells=[HISTORICAL_MARKET_FIELD_POLICY[field][market] for field in HISTORICAL_MARKET_FIELD_POLICY for market in ("A","HK","US","JP")]
  self.assertTrue(all(cell.get("primary") and ("fallback" in cell or cell.get("gap")) for cell in cells))
  attributed=sum(cell["confidence"] in {"high","medium"} for cell in cells)
  self.assertGreaterEqual(attributed/len(cells),0.8)
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
 def test_fx_records_are_frozen_by_trade_date(self):
  adapter=YahooFxAdapter(http_get=lambda _: BODY)
  req=FetchRequest.create(request_id="fx",domain=RecordDomain.MARKET,entity_key="JPY",parameters={"period1":1782777600,"period2":1783036800})
  out=validate_fetched_payload(adapter,req,asyncio.run(adapter.fetch(req)))
  self.assertEqual(out.records[0].payload["metric"],"usd_per_local_currency")
  self.assertEqual(out.records[0].payload["unit"],"USD/JPY")
  self.assertTrue(out.records[0].payload["historical_reconstruction_eligible"])
 def test_sec_inputs_are_point_in_time_and_reconstruct_valuation(self):
  inputs=sec_point_in_time_inputs(json.loads(SEC_BODY),"2026-07-02")
  self.assertEqual(inputs["ttm_net_income"]["value"],12)
  self.assertAlmostEqual(inputs["ttm_net_income"]["growth_pct"],(12/9-1)*100)
  values=derive_historical_valuation(5,inputs)["values"]
  self.assertAlmostEqual(values["pe"],500/12)
  self.assertAlmostEqual(values["pb"],25)
  self.assertAlmostEqual(values["peg"],1.25)
 def test_sec_adapter_binds_official_raw_companyfacts(self):
  adapter=SecCompanyFactsAdapter(http_get=lambda _: SEC_BODY)
  req=FetchRequest.create(request_id="sec",domain=RecordDomain.FUNDAMENTAL,entity_key="EXM",parameters={"cik":"1045810","as_of":"2026-07-02"})
  out=validate_fetched_payload(adapter,req,asyncio.run(adapter.fetch(req)))
  by_metric={record.payload["metric"]:record for record in out.records}
  self.assertEqual(by_metric["ttm_net_income"].payload["value"],12)
  self.assertEqual(by_metric["shares_outstanding"].provenance.raw_hash,out.raw.raw_hash)
 def test_adr_ratio_gap_blocks_false_market_cap(self):
  result=derive_historical_valuation(20,{"shares_outstanding":{"value":100,"form":"20-F"},"gaps":[]})
  self.assertEqual(result["values"],{})
  self.assertIn("adr_ratio_missing",result["gaps"])
if __name__ == "__main__": unittest.main()
