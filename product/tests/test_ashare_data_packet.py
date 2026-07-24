from __future__ import annotations

import json
import sys
import tempfile
import unittest
import asyncio
from pathlib import Path


PRODUCT = Path(__file__).resolve().parents[1]
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from data_core import (  # noqa: E402
    AShareTickerError,
    FetchRequest,
    RecordDomain,
    SQLiteFetchCache,
    SourceChoice,
    TENCENT_QUOTE_SOURCE,
    build_ashare_runtime,
    collect_ashare_packet,
    normalize_ashare_ticker,
)
from data_core.ashare import (  # noqa: E402
    EastmoneyFundamentalAdapter,
    EastmoneyStatementAdapter,
    TencentDailyBarAdapter,
)
from data_core.ingestion import FetchedPayload, build_raw_capture  # noqa: E402


def quote_payload(
    symbol: str = "sz300750", *, name: str = "宁德时代", include_metrics: bool = True
) -> bytes:
    fields = [""] * 50
    fields[1] = name
    fields[3] = "258.20" if include_metrics else ""
    fields[30] = "20260721150000"
    fields[32] = "1.25" if include_metrics else ""
    fields[33] = "262.00" if include_metrics else ""
    fields[34] = "253.00" if include_metrics else ""
    fields[39] = "21.50"
    fields[44] = "10800.00"
    fields[45] = "11400.00"
    fields[46] = "5.10"
    return (f'v_{symbol}="' + "~".join(fields) + '";\n').encode("gbk")


def kline_payload(symbol: str = "sz300750") -> bytes:
    payload = {
        "data": {
            symbol: {
                "qfqday": [
                    ["2026-07-20", "250.00", "255.00", "256.00", "249.00", "100000"],
                    ["2026-07-21", "256.00", "258.20", "262.00", "253.00", "120000"],
                ]
            }
        }
    }
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def fundamental_payload(secucode: str = "300750.SZ") -> bytes:
    payload = {
        "result": {
            "data": [
                {
                    "SECUCODE": secucode,
                    "SECURITY_CODE": secucode[:6],
                    "REPORT_DATE": "2026-03-31 00:00:00",
                    "NOTICE_DATE": "2026-04-20 00:00:00",
                    "REPORT_TYPE": "一季报",
                    "TOTALOPERATEREVE": 84705000000,
                    "PARENTNETPROFIT": 13963000000,
                    "TOTALOPERATEREVETZ": 52.4,
                    "PARENTNETPROFITTZ": 48.5,
                    "ROEJQ": 5.72,
                    "XSMLL": 24.82,
                    "XSJLL": 16.48,
                    "ZCFZL": 67.3,
                    "MGJYXJJE": 5.24,
                }
            ]
        }
    }
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def statement_payload(
    report_name: str, secucode: str = "300750.SZ", *, sparse: bool = False
) -> bytes:
    shared = {
        "SECUCODE": secucode,
        "SECURITY_CODE": secucode[:6],
        "REPORT_DATE": "2026-03-31 00:00:00",
        "NOTICE_DATE": "2026-04-20 00:00:00",
        "DATE_TYPE_CODE": "001",
    }
    values = {
        "RPT_DMSK_FN_BALANCE": {
            "TOTAL_ASSETS": 1046329036000,
            "TOTAL_LIABILITIES": 652096744000,
            "TOTAL_EQUITY": 394232291000,
            "MONETARYFUNDS": 351997422000,
            "ACCOUNTS_RECE": 77710096000,
            "INVENTORY": 108940929000,
            "FIXED_ASSET": 150043366000,
        },
        "RPT_DMSK_FN_INCOME": {
            "TOTAL_OPERATE_INCOME": 129131041000,
            "TOTAL_OPERATE_COST": 107104438000,
            "OPERATE_PROFIT": 26651291000,
            "TOTAL_PROFIT": 26681603000,
            "PARENT_NETPROFIT": 20737710000,
            "DEDUCT_PARENT_NETPROFIT": 18092638000,
        },
        "RPT_DMSK_FN_CASHFLOW": {
            "NETCASH_OPERATE": 33680852000,
            "NETCASH_INVEST": -14623616000,
            "NETCASH_FINANCE": 8762324000,
            "CONSTRUCT_LONG_ASSET": 12416302000,
        },
    }
    statement_values = values[report_name]
    if sparse:
        first_key = next(iter(statement_values))
        statement_values = {first_key: statement_values[first_key]}
    return json.dumps(
        {"result": {"data": [{**shared, **statement_values}]}},
        ensure_ascii=False,
    ).encode("utf-8")


class FakeHttp:
    def __init__(
        self,
        *,
        missing: set[str] | None = None,
        wrong_financial_identity: bool = False,
        quote_identity_only: bool = False,
        sparse_statements: bool = False,
    ) -> None:
        self.missing = missing or set()
        self.wrong_financial_identity = wrong_financial_identity
        self.quote_identity_only = quote_identity_only
        self.sparse_statements = sparse_statements
        self.urls: list[str] = []

    def __call__(self, url: str, encoding_hint: str) -> bytes:
        self.urls.append(url)
        if "quote" in self.missing and "qt.gtimg.cn" in url:
            raise RuntimeError("quote unavailable")
        if "bars" in self.missing and "fqkline" in url:
            raise RuntimeError("bars unavailable")
        if "fundamentals" in self.missing and "eastmoney" in url:
            raise RuntimeError("fundamentals unavailable")
        if "qt.gtimg.cn" in url:
            symbol = url.rsplit("=", 1)[-1]
            return quote_payload(symbol, include_metrics=not self.quote_identity_only)
        if "fqkline" in url:
            symbol = url.split("param=", 1)[1].split(",", 1)[0]
            return kline_payload(symbol)
        if "eastmoney" in url:
            requested = "600519.SH" if "600519.SH" in url else "300750.SZ"
            secucode = "000001.SZ" if self.wrong_financial_identity else requested
            if "RPT_DMSK_FN_BALANCE" in url:
                return statement_payload(
                    "RPT_DMSK_FN_BALANCE", secucode, sparse=self.sparse_statements
                )
            if "RPT_DMSK_FN_INCOME" in url:
                return statement_payload(
                    "RPT_DMSK_FN_INCOME", secucode, sparse=self.sparse_statements
                )
            if "RPT_DMSK_FN_CASHFLOW" in url:
                return statement_payload(
                    "RPT_DMSK_FN_CASHFLOW", secucode, sparse=self.sparse_statements
                )
            return fundamental_payload(secucode)
        raise AssertionError(url)


class AShareDataPacketTest(unittest.TestCase):
    def test_normalizes_common_sh_sz_formats_and_rejects_ambiguous(self) -> None:
        self.assertEqual(normalize_ashare_ticker("600519").ticker, "600519.SH")
        self.assertEqual(normalize_ashare_ticker("sh600519").exchange, "SSE")
        self.assertEqual(normalize_ashare_ticker("300750.sz").board, "CHINEXT")
        self.assertEqual(normalize_ashare_ticker("000001").ticker, "000001.SZ")
        with self.assertRaises(AShareTickerError):
            normalize_ashare_ticker("123456")
        with self.assertRaises(AShareTickerError):
            normalize_ashare_ticker("SH300750.SZ")
        with self.assertRaises(AShareTickerError):
            normalize_ashare_ticker("300750.SH")
        with self.assertRaises(AShareTickerError):
            normalize_ashare_ticker("900901.SH")

    def test_collects_publishable_packet_for_sz_ticker(self) -> None:
        packet = collect_ashare_packet("300750.SZ", http_get=FakeHttp(), bar_limit=2, fundamental_periods=1)
        self.assertTrue(packet.publishable)
        self.assertEqual(packet.instrument.instrument_id, "CN:300750.SZ")
        self.assertEqual(packet.identity["name"], "宁德时代")
        self.assertEqual(packet.quote["last_price"], 258.2)
        self.assertEqual(len(packet.daily_bars), 2)
        self.assertEqual(packet.daily_bars[-1]["close"], 258.2)
        self.assertEqual(packet.fundamentals[0]["revenue"], 84705000000)
        self.assertEqual(packet.fundamentals[0]["total_assets"], 1046329036000)
        self.assertEqual(packet.fundamentals[0]["net_cash_operating"], 33680852000)
        self.assertFalse(packet.data_gaps)
        summary = packet.to_summary()
        self.assertEqual(summary["sources"]["quote"]["status"], "success")
        self.assertEqual(summary["sources"]["fundamentals"]["accepted_records"], 9)
        self.assertEqual(summary["sources"]["balance_sheet"]["accepted_records"], 7)
        self.assertEqual(summary["sources"]["income_statement"]["accepted_records"], 6)
        self.assertEqual(summary["sources"]["cash_flow"]["accepted_records"], 4)
        self.assertEqual(len(summary["sources"]["quote"]["raw_hash"]), 64)
        self.assertTrue(summary["sources"]["quote"]["source_url"].startswith("https://"))

    def test_collects_publishable_packet_for_sh_ticker(self) -> None:
        fake = FakeHttp()
        packet = collect_ashare_packet("600519", http_get=fake, bar_limit=2, fundamental_periods=1)
        self.assertTrue(packet.publishable)
        self.assertEqual(packet.instrument.exchange, "SSE")
        self.assertTrue(any("sh600519" in url for url in fake.urls))

    def test_missing_source_becomes_explicit_gap_not_fabricated_data(self) -> None:
        packet = collect_ashare_packet(
            "300750.SZ",
            http_get=FakeHttp(missing={"fundamentals"}),
            bar_limit=2,
            fundamental_periods=1,
        )
        self.assertFalse(packet.publishable)
        self.assertEqual(packet.fundamentals, ())
        self.assertEqual(packet.data_gaps[0].domain, "fundamentals")
        self.assertIn("fundamentals unavailable", packet.data_gaps[0].reason)

    def test_wrong_provider_financial_identity_fails_closed(self) -> None:
        packet = collect_ashare_packet(
            "300750.SZ",
            http_get=FakeHttp(wrong_financial_identity=True),
            bar_limit=2,
            fundamental_periods=1,
        )
        self.assertFalse(packet.publishable)
        self.assertEqual(packet.fundamentals, ())
        self.assertTrue(any("identity mismatch" in gap.reason for gap in packet.data_gaps))

    def test_identity_only_quote_is_not_publishable(self) -> None:
        packet = collect_ashare_packet(
            "300750.SZ",
            http_get=FakeHttp(quote_identity_only=True),
            bar_limit=2,
            fundamental_periods=1,
        )
        self.assertFalse(packet.publishable)
        self.assertNotIn("last_price", packet.quote or {})
        self.assertTrue(any("missing_quote_fields" in gap.reason for gap in packet.data_gaps))

    def test_sparse_statements_are_not_publishable(self) -> None:
        packet = collect_ashare_packet(
            "300750.SZ",
            http_get=FakeHttp(sparse_statements=True),
            bar_limit=2,
            fundamental_periods=1,
        )
        self.assertFalse(packet.publishable)
        self.assertTrue(
            any("missing_latest_period_fields" in gap.reason for gap in packet.data_gaps)
        )

    def test_local_cache_fallback_is_degraded_and_not_publishable(self) -> None:
        fake = FakeHttp()
        with tempfile.TemporaryDirectory() as tmp:
            cache = SQLiteFetchCache(Path(tmp) / "cache.sqlite3")
            runtime = build_ashare_runtime(http_get=fake, cache=cache)
            request = FetchRequest.create(
                request_id="quote-cache-seed",
                domain=RecordDomain.MARKET,
                entity_key="300750.SZ",
                parameters={"kind": "quote"},
            )
            first = asyncio.run(runtime.run(request, (SourceChoice(TENCENT_QUOTE_SOURCE, "primary"),)))
            self.assertTrue(first.publishable)

            broken_runtime = build_ashare_runtime(http_get=FakeHttp(missing={"quote"}), cache=cache)
            second = asyncio.run(
                broken_runtime.run(request, (SourceChoice(TENCENT_QUOTE_SOURCE, "primary"),))
            )
            self.assertEqual(second.status, "degraded")
            self.assertFalse(second.publishable)
        self.assertEqual(second.data_kind, "cached")
        self.assertEqual(len(second.attempts), 2)

    def test_packet_refreshes_use_distinct_ingestion_request_ids(self) -> None:
        runtime = build_ashare_runtime(http_get=FakeHttp())
        first = collect_ashare_packet(
            "300750.SZ", runtime=runtime, bar_limit=2, fundamental_periods=1
        )
        second = collect_ashare_packet(
            "300750.SZ", runtime=runtime, bar_limit=2, fundamental_periods=1
        )
        first_ids = {attempt.request.request_id for outcome in first.outcomes.values() for attempt in outcome.attempts}
        second_ids = {attempt.request.request_id for outcome in second.outcomes.values() for attempt in outcome.attempts}
        self.assertTrue(first_ids.isdisjoint(second_ids))

    def test_in_progress_daily_bar_never_claims_a_future_close_time(self) -> None:
        known_at = "2026-07-21T02:30:00Z"
        fetched = FetchedPayload(
            body=kline_payload(),
            source_url="https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?fixture=1",
            fetched_at=known_at,
            known_at=known_at,
            mime_type="application/json",
            data_kind="fixture",
        )
        request = FetchRequest.create(
            request_id="intraday-bar",
            domain=RecordDomain.MARKET,
            entity_key="300750.SZ",
            parameters={"kind": "daily_bars", "limit": 2},
        )
        adapter = TencentDailyBarAdapter(http_get=FakeHttp(), limit=2)
        records = tuple(adapter.parse(request, fetched, build_raw_capture(fetched)))
        current_day = [
            record.payload
            for record in records
            if record.payload.get("trade_date") == "2026-07-21"
        ]
        self.assertTrue(current_day)
        self.assertTrue(all(item["observed_at"] == known_at for item in current_day))

    def test_future_scheduled_financial_rows_are_not_accepted_as_pit_facts(self) -> None:
        known_at = "2026-07-24T10:00:00Z"
        request = FetchRequest.create(
            request_id="future-financial-row",
            domain=RecordDomain.FUNDAMENTAL,
            entity_key="300750.SZ",
            parameters={"periods": 4},
        )

        main = json.loads(fundamental_payload())
        main["result"]["data"].insert(
            0,
            {
                **main["result"]["data"][0],
                "REPORT_DATE": "2026-06-30 00:00:00",
                "NOTICE_DATE": "2026-08-30 00:00:00",
            },
        )
        main_fetched = FetchedPayload(
            body=json.dumps(main).encode(),
            source_url="https://datacenter.eastmoney.com/fixture/main",
            fetched_at=known_at,
            known_at=known_at,
            mime_type="application/json",
            data_kind="fixture",
        )
        main_records = tuple(
            EastmoneyFundamentalAdapter(http_get=FakeHttp()).parse(
                request, main_fetched, build_raw_capture(main_fetched)
            )
        )
        self.assertTrue(main_records)
        self.assertTrue(
            all(record.payload["report_period"] == "2026-03-31" for record in main_records)
        )

        statement = json.loads(statement_payload("RPT_DMSK_FN_INCOME"))
        statement["result"]["data"].insert(
            0,
            {
                **statement["result"]["data"][0],
                "REPORT_DATE": "2026-06-30 00:00:00",
                "NOTICE_DATE": "2026-08-30 00:00:00",
            },
        )
        statement_fetched = FetchedPayload(
            body=json.dumps(statement).encode(),
            source_url="https://datacenter.eastmoney.com/fixture/income",
            fetched_at=known_at,
            known_at=known_at,
            mime_type="application/json",
            data_kind="fixture",
        )
        statement_records = tuple(
            EastmoneyStatementAdapter("income_statement", http_get=FakeHttp()).parse(
                request, statement_fetched, build_raw_capture(statement_fetched)
            )
        )
        self.assertTrue(statement_records)
        self.assertTrue(
            all(record.payload["report_period"] == "2026-03-31" for record in statement_records)
        )


if __name__ == "__main__":
    unittest.main()
