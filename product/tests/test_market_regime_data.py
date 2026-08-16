from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile
import unittest
from zoneinfo import ZoneInfo


PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT))

from data_core.market_regime_data import (  # noqa: E402
    COMMERCIAL_RIGHTS_APPROVED,
    INSTRUMENTS,
    INSTRUMENT_BY_KEY,
    HttpCapture,
    LicenseGateError,
    LOCAL_EVALUATION,
    MarketRegimeDataError,
    MarketRegimeDataStore,
    SourceCaptureError,
    instrument_registry_payload,
    license_decision,
    normalize_capture,
)


NOW = datetime(2026, 8, 6, 23, 0, tzinfo=timezone.utc)


def completed_dates(count: int, *, end: date = date(2026, 8, 6)) -> list[date]:
    return [end - timedelta(days=count - 1 - index) for index in range(count)]


def yahoo_body(
    symbol: str,
    *,
    count: int = 210,
    currency: str = "USD",
    timezone_name: str = "America/New_York",
    rows: list[dict] | None = None,
    regular_market_time: datetime | None = None,
    scheduled_session_end: datetime | None = None,
) -> bytes:
    source_rows = rows or [
        {"date": item, "open": 100 + index, "high": 102 + index, "low": 99 + index, "close": 101 + index, "volume": 10_000 + index}
        for index, item in enumerate(completed_dates(count))
    ]
    zone = ZoneInfo(timezone_name)
    timestamps = [int(datetime.combine(row["date"], time(9, 30), tzinfo=zone).timestamp()) for row in source_rows]
    default_close = datetime.combine(source_rows[-1]["date"], time(16, 0), tzinfo=zone)
    observed = regular_market_time or default_close
    session_end = scheduled_session_end or default_close
    quote = {field: [row.get(field) for row in source_rows] for field in ("open", "high", "low", "close", "volume")}
    return json.dumps(
        {
            "chart": {
                "result": [
                    {
                        "meta": {
                            "symbol": symbol,
                            "currency": currency,
                            "exchangeTimezoneName": timezone_name,
                            "regularMarketTime": int(observed.timestamp()),
                            "currentTradingPeriod": {"regular": {"end": int(session_end.timestamp())}},
                        },
                        "timestamp": timestamps,
                        "indicators": {"quote": [quote]},
                    }
                ],
                "error": None,
            }
        }
    ).encode()


def tencent_body(symbol: str, *, count: int = 210) -> bytes:
    rows = []
    for index, item in enumerate(completed_dates(count)):
        base = 1_000 + index
        rows.append([item.isoformat(), str(base), str(base + 1), str(base + 2), str(base - 1), str(50_000 + index)])
    quote_row = [""] * 31
    quote_row[30] = completed_dates(count)[-1].strftime("%Y%m%d") + "160000"
    return json.dumps(
        {"code": 0, "data": {symbol: {"day": rows, "qt": {symbol: quote_row}}}}
    ).encode()


def capture(
    body: bytes,
    *,
    status: int = 200,
    content_type: str = "application/json; charset=utf-8",
    headers: tuple[tuple[str, str], ...] | None = None,
) -> HttpCapture:
    safe_headers = headers or (("content-type", content_type),)
    return HttpCapture(
        "GET",
        "https://example.test/requested",
        "https://example.test/final",
        status,
        safe_headers,
        (),
        ("https://example.test/requested", "https://example.test/final"),
        body,
        NOW.isoformat().replace("+00:00", "Z"),
    )


class MarketRegimeDataTest(unittest.TestCase):
    def test_registry_freezes_nine_charts_and_three_visible_evidence_dependencies(self) -> None:
        registry = instrument_registry_payload()
        self.assertEqual((registry["primary_chart_count"], registry["evidence_probe_count"]), (9, 3))
        self.assertEqual(len(INSTRUMENTS), 12)
        self.assertEqual(INSTRUMENT_BY_KEY["sp500"].provider_symbol, "^GSPC")
        self.assertEqual(INSTRUMENT_BY_KEY["star50"].canonical_symbol, "000688.SH")
        self.assertEqual(INSTRUMENT_BY_KEY["wti"].price_basis, "provider_continuous_front_month_unadjusted")
        self.assertEqual({item.currency for item in INSTRUMENTS}, {"USD", "CNY", "KRW", "JPY"})
        self.assertTrue(all(item.exchange_timezone and item.session_close for item in INSTRUMENTS))
        self.assertTrue(all(source["authority_tier"] == "supplementary_only" for source in registry["sources"].values()))

    def test_license_gate_keeps_local_evaluation_unverified_and_private_beta_closed(self) -> None:
        local = license_decision(
            deployment_mode="local_prototype", license_status=LOCAL_EVALUATION, private_preview=False
        )
        self.assertTrue(local.allowed)
        self.assertFalse(local.verified_for_publication)
        with self.assertRaises(LicenseGateError):
            license_decision(
                deployment_mode="private_beta", license_status=LOCAL_EVALUATION, private_preview=True
            )
        with self.assertRaises(LicenseGateError):
            license_decision(
                deployment_mode="private_beta",
                license_status=COMMERCIAL_RIGHTS_APPROVED,
                private_preview=True,
            )
        with self.assertRaises(LicenseGateError):
            license_decision(
                deployment_mode="private_beta",
                license_status=COMMERCIAL_RIGHTS_APPROVED,
                license_reference="contract:market-data-001",
                private_preview=True,
            )
        attested = license_decision(
            deployment_mode="local_prototype",
            license_status=COMMERCIAL_RIGHTS_APPROVED,
            license_reference="contract:market-data-001",
            private_preview=False,
        )
        self.assertFalse(attested.verified_for_publication)

    def test_yahoo_ohlc_is_identity_bound_and_current_unfinished_bar_is_excluded(self) -> None:
        spec = INSTRUMENT_BY_KEY["sp500"]
        rows = [
            {"date": item, "open": 100 + index, "high": 102 + index, "low": 99 + index, "close": 101 + index, "volume": 10_000}
            for index, item in enumerate(completed_dates(210, end=date(2026, 8, 5)))
        ]
        rows.append({"date": date(2026, 8, 6), "open": 310, "high": 312, "low": 309, "close": 311, "volume": 11_000})
        before_close = datetime(2026, 8, 6, 18, 0, tzinfo=timezone.utc)
        new_york = ZoneInfo("America/New_York")
        normalized = normalize_capture(
            spec,
            capture(
                yahoo_body(
                    "^GSPC",
                    rows=rows,
                    regular_market_time=datetime(2026, 8, 6, 14, 0, tzinfo=new_york),
                    scheduled_session_end=datetime(2026, 8, 6, 16, 0, tzinfo=new_york),
                )
            ),
            now=before_close,
        )
        self.assertEqual(normalized["bar_count"], 210)
        self.assertEqual(normalized["last_completed_session"], "2026-08-05")
        self.assertEqual(normalized["dropped_unfinished_sessions"], ["2026-08-06"])
        self.assertEqual(normalized["quality"], "fresh")

    def test_unfinished_inverted_ohlc_is_dropped_but_completed_row_stays_strict(self) -> None:
        spec = INSTRUMENT_BY_KEY["sp500"]
        rows = [
            {
                "date": item,
                "open": 100 + index,
                "high": 102 + index,
                "low": 99 + index,
                "close": 101 + index,
                "volume": 10_000,
            }
            for index, item in enumerate(completed_dates(210, end=date(2026, 8, 5)))
        ]
        rows.append(
            {
                "date": date(2026, 8, 6),
                "open": 310,
                "high": 312,
                "low": 309,
                "close": 313,
                "volume": 11_000,
            }
        )
        new_york = ZoneInfo("America/New_York")
        body = yahoo_body(
            "^GSPC",
            rows=rows,
            regular_market_time=datetime(2026, 8, 6, 14, 0, tzinfo=new_york),
            scheduled_session_end=datetime(2026, 8, 6, 16, 0, tzinfo=new_york),
        )
        raw_hash = sha256(body).hexdigest()
        before_close = normalize_capture(
            spec,
            capture(body),
            now=datetime(2026, 8, 6, 18, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(before_close["last_completed_session"], "2026-08-05")
        self.assertEqual(before_close["dropped_unfinished_sessions"], ["2026-08-06"])
        self.assertEqual(sha256(body).hexdigest(), raw_hash)
        with self.assertRaisesRegex(SourceCaptureError, "OHLC range is inverted"):
            normalize_capture(
                spec,
                capture(body),
                now=datetime(2026, 8, 6, 21, 0, tzinfo=timezone.utc),
            )

    def test_tencent_index_ohlc_is_normalized_without_fake_adjustment(self) -> None:
        spec = INSTRUMENT_BY_KEY["shanghai"]
        normalized = normalize_capture(
            spec,
            capture(tencent_body("sh000001"), content_type="text/html; charset=UTF-8"),
            now=NOW,
        )
        self.assertEqual(normalized["bar_count"], 210)
        self.assertEqual(normalized["bars"][-1]["close"], 1210.0)
        self.assertEqual(normalized["price_basis"], "provider_unadjusted_index_level")
        self.assertEqual(normalized["last_completed_close_at"], "2026-08-06T07:00:00Z")
        self.assertEqual(normalized["source_quality_flags"], ["provider_declares_text_html_for_json"])

    def test_tencent_adjusted_series_is_rejected_by_unadjusted_index_contract(self) -> None:
        payload = json.loads(tencent_body("sh000001"))
        stock = payload["data"]["sh000001"]
        stock["qfqday"] = stock.pop("day")
        with self.assertRaisesRegex(SourceCaptureError, "adjusted qfqday"):
            normalize_capture(
                INSTRUMENT_BY_KEY["shanghai"],
                capture(
                    json.dumps(payload).encode(),
                    content_type="text/html; charset=UTF-8",
                ),
                now=NOW,
            )

    def test_wrong_symbol_bad_mime_and_http_failure_are_rejected_with_capture(self) -> None:
        spec = INSTRUMENT_BY_KEY["sp500"]
        cases = (
            capture(yahoo_body("^IXIC")),
            capture(b"<html>blocked</html>", content_type="text/html"),
            capture(b"gateway", status=502, content_type="text/html"),
        )
        for item in cases:
            with self.subTest(status=item.status_code, mime=item.content_type):
                with self.assertRaises(SourceCaptureError) as caught:
                    normalize_capture(spec, item, now=NOW)
                self.assertIs(caught.exception.capture, item)

    def test_yahoo_currency_timezone_and_future_date_are_identity_failures(self) -> None:
        spec = INSTRUMENT_BY_KEY["sp500"]
        future_rows = [
            {"date": item, "open": 100 + index, "high": 102 + index, "low": 99 + index, "close": 101 + index, "volume": 10_000}
            for index, item in enumerate(completed_dates(210, end=date(2026, 8, 7)))
        ]
        cases = (
            yahoo_body("^GSPC", currency="EUR"),
            yahoo_body("^GSPC", timezone_name="America/Chicago"),
            yahoo_body("^GSPC", rows=future_rows),
        )
        for body in cases:
            with self.assertRaises(SourceCaptureError):
                normalize_capture(spec, capture(body), now=NOW)

    def test_null_inverted_duplicate_and_short_histories_fail_closed(self) -> None:
        spec = INSTRUMENT_BY_KEY["sp500"]
        base_rows = [
            {"date": item, "open": 100 + index, "high": 102 + index, "low": 99 + index, "close": 101 + index, "volume": 10_000}
            for index, item in enumerate(completed_dates(210))
        ]
        variants = []
        null_rows = [dict(item) for item in base_rows]
        null_rows[3]["open"] = None
        variants.append(null_rows)
        inverted = [dict(item) for item in base_rows]
        inverted[5]["high"] = inverted[5]["low"] - 1
        variants.append(inverted)
        duplicate = [dict(item) for item in base_rows]
        duplicate[7]["date"] = duplicate[6]["date"]
        variants.append(duplicate)
        out_of_order = [dict(item) for item in base_rows]
        out_of_order[8], out_of_order[9] = out_of_order[9], out_of_order[8]
        variants.append(out_of_order)
        variants.append(base_rows[:20])
        for rows in variants:
            with self.subTest(row_count=len(rows)):
                with self.assertRaises(SourceCaptureError):
                    normalize_capture(spec, capture(yahoo_body("^GSPC", rows=rows)), now=NOW)

    def test_yahoo_all_null_provider_session_is_disclosed_and_skipped(self) -> None:
        spec = INSTRUMENT_BY_KEY["vix"]
        rows = [
            {"date": item, "open": 20 + index / 10, "high": 21 + index / 10, "low": 19 + index / 10, "close": 20.5 + index / 10, "volume": 0}
            for index, item in enumerate(completed_dates(210))
        ]
        rows[12] = {"date": rows[12]["date"], "open": None, "high": None, "low": None, "close": None, "volume": None}
        normalized = normalize_capture(
            spec,
            capture(yahoo_body("^VIX", rows=rows, timezone_name="America/Chicago")),
            now=NOW,
        )
        self.assertEqual(normalized["bar_count"], 209)
        self.assertEqual(normalized["dropped_empty_provider_sessions"], [rows[12]["date"].isoformat()])

    def test_short_accepted_history_is_partial_and_old_history_is_stale(self) -> None:
        spec = INSTRUMENT_BY_KEY["sp500"]
        partial = normalize_capture(spec, capture(yahoo_body("^GSPC", count=130)), now=NOW)
        self.assertEqual(partial["quality"], "partial")
        stale_now = NOW + timedelta(days=11)
        stale = normalize_capture(spec, capture(yahoo_body("^GSPC", count=210)), now=stale_now)
        self.assertEqual(stale["quality"], "stale")

    def test_provider_session_metadata_marks_a_missing_completed_trading_day_partial(self) -> None:
        spec = INSTRUMENT_BY_KEY["sp500"]
        zone = ZoneInfo("America/New_York")
        friday = date(2026, 7, 31)
        monday_close = datetime(2026, 8, 3, 16, 0, tzinfo=zone)
        monday_after_close = datetime(2026, 8, 3, 21, 0, tzinfo=timezone.utc)
        body = yahoo_body(
            "^GSPC",
            count=210,
            rows=[
                {"date": item, "open": 100 + index, "high": 102 + index, "low": 99 + index, "close": 101 + index, "volume": 10_000}
                for index, item in enumerate(completed_dates(210, end=friday))
            ],
            regular_market_time=monday_close,
            scheduled_session_end=monday_close,
        )
        normalized = normalize_capture(spec, capture(body), now=monday_after_close)
        self.assertEqual(normalized["quality"], "partial")
        self.assertEqual(normalized["missing_expected_session"], "2026-08-03")

    def test_tencent_quote_date_marks_missing_post_close_index_bar_partial(self) -> None:
        symbol = "sh000001"
        payload = json.loads(tencent_body(symbol))
        stock = payload["data"][symbol]
        stock["day"] = [row for row in stock["day"] if row[0] < "2026-08-06"]
        stock["qt"][symbol][30] = "20260806150000"
        normalized = normalize_capture(
            INSTRUMENT_BY_KEY["shanghai"],
            capture(
                json.dumps(payload).encode(),
                content_type="text/html; charset=UTF-8",
            ),
            now=datetime(2026, 8, 6, 7, 30, tzinfo=timezone.utc),
        )
        self.assertEqual(normalized["quality"], "partial")
        self.assertEqual(normalized["missing_expected_session"], "2026-08-06")

    def test_store_preserves_raw_receipts_and_does_not_overwrite_latest_good_on_failure(self) -> None:
        valid = capture(yahoo_body("^GSPC"), headers=(("content-type", "application/json"), ("etag", "abc")))
        failed = capture(b"<html>rate limited</html>", status=502, content_type="text/html")
        responses = iter((valid, failed))

        def fake_get(url: str) -> HttpCapture:
            del url
            return next(responses)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = MarketRegimeDataStore(root, http_get=fake_get)
            first = store.refresh(
                now=NOW,
                instrument_keys=["sp500"],
                deployment_mode="local_prototype",
                license_status=LOCAL_EVALUATION,
                private_preview=False,
            )
            latest_path = root / "instruments" / "sp500" / "latest-good.json"
            first_hash = sha256(latest_path.read_bytes()).hexdigest()
            self.assertEqual(first["quality"], "fresh")
            self.assertFalse(first["instruments"][0]["publication_eligible"])
            raw_path = root / first["instruments"][0]["source"]["raw_path"]
            self.assertEqual(sha256(raw_path.read_bytes()).hexdigest(), first["instruments"][0]["source"]["raw_sha256"])
            artifact = first["instruments"][0]["normalized_artifact"]
            artifact_path = root / artifact["path"]
            self.assertEqual(sha256(artifact_path.read_bytes()).hexdigest(), artifact["sha256"])
            second = store.refresh(
                now=NOW + timedelta(hours=1),
                instrument_keys=["sp500"],
                deployment_mode="local_prototype",
                license_status=LOCAL_EVALUATION,
                private_preview=False,
            )
            self.assertEqual(sha256(latest_path.read_bytes()).hexdigest(), first_hash)
            self.assertEqual(second["quality"], "partial")
            self.assertEqual(second["instruments"][0]["refresh_status"], "rejected")
            receipt = json.loads((root / second["refresh_receipt"]).read_text())
            self.assertEqual(receipt["rejected_count"], 1)
            first_receipt = json.loads((root / first["refresh_receipt"]).read_text())
            self.assertEqual(first_receipt["results"][0]["normalized_artifact"], artifact)
            self.assertEqual(receipt["results"][0]["bounded_raw_excerpt"], "<html>rate limited</html>")
            self.assertEqual(len(list((root / "runs").glob("*.json"))), 2)
            self.assertEqual(len(list((root / "run-events").glob("*/000-started.json"))), 2)

    def test_unknown_instrument_never_reaches_network(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = MarketRegimeDataStore(directory, http_get=lambda *args, **kwargs: self.fail("network called"))
            with self.assertRaises(MarketRegimeDataError):
                store.refresh(
                    now=NOW,
                    instrument_keys=["bitcoin"],
                    deployment_mode="local_prototype",
                    license_status=LOCAL_EVALUATION,
                    private_preview=False,
                )

    def test_live_transport_rejects_a_forged_capture_clock(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(MarketRegimeDataError, "offline/fixture"):
                MarketRegimeDataStore(directory).refresh(
                    now=NOW,
                    instrument_keys=["sp500"],
                    deployment_mode="local_prototype",
                    license_status=LOCAL_EVALUATION,
                    private_preview=False,
                )

    def test_latest_detects_normalized_artifact_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = MarketRegimeDataStore(root, http_get=lambda url: capture(yahoo_body("^GSPC")))
            snapshot = store.refresh(
                now=NOW,
                instrument_keys=["sp500"],
                deployment_mode="local_prototype",
                license_status=LOCAL_EVALUATION,
                private_preview=False,
            )
            artifact_path = root / snapshot["instruments"][0]["normalized_artifact"]["path"]
            artifact_path.write_bytes(artifact_path.read_bytes() + b" ")
            with self.assertRaisesRegex(MarketRegimeDataError, "hash mismatch"):
                store.latest()


if __name__ == "__main__":
    unittest.main()
