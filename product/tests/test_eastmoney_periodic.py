from __future__ import annotations

import asyncio
import json
import sys
import unittest
from pathlib import Path


PRODUCT = Path(__file__).resolve().parents[1]
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from data_core import (  # noqa: E402
    EASTMONEY_BUSINESS_COMPOSITION_SOURCE,
    EASTMONEY_EARNINGS_CALENDAR_SOURCE,
    EastmoneyBusinessCompositionAdapter,
    EastmoneyEarningsCalendarAdapter,
    FetchRequest,
    MemoryAttemptSink,
    RecordDomain,
    SourceChoice,
    build_eastmoney_periodic_runtime,
    collect_eastmoney_earnings_calendar,
    validate_fetched_payload,
)
from data_core.ingestion import FetchedPayload, build_raw_capture  # noqa: E402


FIXTURES = Path(__file__).parent / "fixtures" / "eastmoney_periodic"
KNOWN_AT = "2026-07-22T01:00:00Z"


def fixture_payload(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def business_request() -> FetchRequest:
    return FetchRequest.create(
        request_id="business-fixture", domain=RecordDomain.FUNDAMENTAL,
        entity_key="300750.SZ", parameters={"kind": "business_composition"},
    )


def calendar_request(*, report_period: str = "2026-06-30") -> FetchRequest:
    return FetchRequest.create(
        request_id="calendar-fixture", domain=RecordDomain.EVENT,
        entity_key="CN:A-SHARE-UNIVERSE", parameters={"report_period": report_period},
    )


def fetched(body: bytes, url: str) -> FetchedPayload:
    return FetchedPayload(
        body=body, source_url=url, fetched_at=KNOWN_AT, known_at=KNOWN_AT,
        mime_type="application/json", data_kind="fixture",
    )


class FakeHttp:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.urls: list[str] = []

    def __call__(self, url: str, encoding_hint: str) -> bytes:
        self.urls.append(url)
        if self.fail:
            raise RuntimeError("provider temporarily unavailable")
        if "BusinessAnalysis/PageAjax" in url:
            return fixture_payload("business-composition.json")
        if "RPT_PUBLIC_BS_APPOIN" in url:
            return fixture_payload("earnings-calendar.json")
        raise AssertionError(url)


class EastmoneyPeriodicAdapterTest(unittest.TestCase):
    def test_business_fixture_keeps_segment_structure_and_provenance(self) -> None:
        adapter = EastmoneyBusinessCompositionAdapter(http_get=FakeHttp())
        value = fetched(fixture_payload("business-composition.json"), "https://example.test/f10")
        validated = validate_fetched_payload(adapter, business_request(), value)

        self.assertEqual(len(validated.records), 14)
        first = validated.records[0]
        self.assertEqual(first.domain, RecordDomain.FUNDAMENTAL)
        self.assertEqual(first.payload["segment_name"], "动力电池系统")
        self.assertEqual(first.payload["segment_category"], "product")
        self.assertEqual(first.payload["availability_time_kind"], "provider_observation")
        self.assertEqual(first.provenance.raw_hash, validated.raw.raw_hash)
        self.assertEqual(first.provenance.known_at, KNOWN_AT)
        self.assertTrue(first.provenance.source_key.startswith("eastmoney_f10_business"))

    def test_calendar_fixture_returns_each_a_share_and_future_date_is_a_field_not_event_time(self) -> None:
        adapter = EastmoneyEarningsCalendarAdapter(http_get=FakeHttp())
        value = fetched(fixture_payload("earnings-calendar.json"), "https://example.test/calendar")
        validated = validate_fetched_payload(adapter, calendar_request(), value)

        self.assertEqual(len(validated.records), 2)
        catl = next(record for record in validated.records if record.payload["ticker"] == "300750.SZ")
        maotai = next(record for record in validated.records if record.payload["ticker"] == "600519.SH")
        self.assertEqual(catl.payload["occurred_at"], KNOWN_AT)
        self.assertEqual(catl.payload["effective_disclosure_date"], "2026-08-30")
        self.assertEqual(catl.payload["calendar_status"], "appointment")
        self.assertEqual(maotai.payload["calendar_status"], "actual")
        self.assertEqual(maotai.payload["effective_disclosure_date"], "2026-08-18")
        self.assertEqual(catl.provenance.raw_hash, validated.raw.raw_hash)

    def test_calendar_rejects_invalid_page_metadata(self) -> None:
        adapter = EastmoneyEarningsCalendarAdapter(http_get=FakeHttp())
        body = json.loads(fixture_payload("earnings-calendar.json"))
        body["result"]["pages"] = 0
        value = fetched(json.dumps(body).encode(), "https://example.test/calendar")
        with self.assertRaisesRegex(ValueError, "invalid page count"):
            tuple(adapter.parse(calendar_request(), value, build_raw_capture(value)))

    def test_live_fetch_url_is_limited_to_expected_endpoint_and_contract_parameters(self) -> None:
        fake = FakeHttp()
        business = EastmoneyBusinessCompositionAdapter(http_get=fake, minimum_interval_seconds=0)
        calendar = EastmoneyEarningsCalendarAdapter(http_get=fake, minimum_interval_seconds=0)
        asyncio.run(business.fetch(business_request()))
        asyncio.run(calendar.fetch(calendar_request()))
        self.assertIn("emweb.securities.eastmoney.com", fake.urls[0])
        self.assertIn("code=SZ300750", fake.urls[0])
        self.assertIn("datacenter-web.eastmoney.com", fake.urls[1])
        self.assertIn("RPT_PUBLIC_BS_APPOIN", fake.urls[1])
        self.assertIn("pageSize=500", fake.urls[1])
        self.assertNotIn("%5C", fake.urls[1])

    def test_failed_calendar_run_is_a_receipt_and_cannot_replace_previous_success(self) -> None:
        sink = MemoryAttemptSink()
        good_runtime = build_eastmoney_periodic_runtime(
            http_get=FakeHttp(), authority_sink=sink, minimum_interval_seconds=0
        )
        good = asyncio.run(good_runtime.run(
            calendar_request(), (SourceChoice(EASTMONEY_EARNINGS_CALENDAR_SOURCE, "primary"),)
        ))
        previous_records = good.records
        broken_runtime = build_eastmoney_periodic_runtime(
            http_get=FakeHttp(fail=True), authority_sink=sink, minimum_interval_seconds=0
        )
        failed = asyncio.run(broken_runtime.run(
            calendar_request(), (SourceChoice(EASTMONEY_EARNINGS_CALENDAR_SOURCE, "primary"),)
        ))

        self.assertTrue(good.publishable)
        self.assertEqual(failed.status, "failed")
        self.assertFalse(failed.publishable)
        self.assertEqual(len(sink.attempts), 2)
        self.assertEqual(previous_records, good.records)
        self.assertEqual(sink.attempts[-1].status, "failed")
        self.assertEqual(sink.attempts[-1].records, ())

    def test_registry_has_only_the_two_periodic_source_keys(self) -> None:
        runtime = build_eastmoney_periodic_runtime(http_get=FakeHttp(), minimum_interval_seconds=0)
        self.assertEqual(
            runtime.registry.source_keys(),
            tuple(sorted((EASTMONEY_BUSINESS_COMPOSITION_SOURCE, EASTMONEY_EARNINGS_CALENDAR_SOURCE))),
        )

    def test_complete_calendar_collection_requires_every_page_and_preserves_each_page_raw_hash(self) -> None:
        class PagedHttp(FakeHttp):
            def __call__(self, url: str, encoding_hint: str) -> bytes:
                self.urls.append(url)
                body = json.loads(fixture_payload("earnings-calendar.json"))
                body["result"]["pages"] = 2
                if "pageNumber=2" in url:
                    body["result"]["data"] = [body["result"]["data"][1]]
                else:
                    body["result"]["data"] = [body["result"]["data"][0]]
                return json.dumps(body).encode()

        result = collect_eastmoney_earnings_calendar(
            "2026-06-30", http_get=PagedHttp(),
        )
        self.assertTrue(result.publishable)
        self.assertEqual(result.total_pages, 2)
        self.assertEqual(len(result.outcomes), 2)
        self.assertEqual(len(result.records), 2)
        self.assertNotEqual(
            result.outcomes[0].attempts[-1].raw.raw_hash,
            result.outcomes[1].attempts[-1].raw.raw_hash,
        )


if __name__ == "__main__":
    unittest.main()
