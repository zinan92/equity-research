from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest
from zoneinfo import ZoneInfo


PRODUCT = Path(__file__).resolve().parents[1]
ROOT = PRODUCT.parent
FIXTURES = Path(__file__).parent / "fixtures" / "market-regime-intraday"
sys.path.insert(0, str(PRODUCT))

from data_core.market_regime_data import HttpCapture, LicenseGateError, SourceCaptureError
from data_core.market_regime_intraday_data import (
    INSTRUMENT_BY_KEY,
    YAHOO_INSTRUMENTS,
    MarketRegimeIntradayDataError,
    MarketRegimeIntradayDataStore,
    classify_yahoo_session,
    normalize_yahoo_capture,
    registry_payload,
    yahoo_urls,
)


NOW = datetime(2026, 8, 5, 15, 46, tzinfo=timezone.utc)
VALID_BODY = (FIXTURES / "yahoo-query1-es-200.json").read_bytes()
RATE_LIMIT_BODY = (FIXTURES / "yahoo-query2-429.txt").read_bytes()


def capture(
    body: bytes = VALID_BODY,
    *,
    url: str | None = None,
    status: int = 200,
    content_type: str = "application/json; charset=utf-8",
) -> HttpCapture:
    requested = url or yahoo_urls(INSTRUMENT_BY_KEY["sp500_futures_proxy"])[0]
    return HttpCapture(
        method="GET",
        requested_url=requested,
        final_url=requested,
        status_code=status,
        response_headers=(("content-type", content_type),),
        dropped_header_names=(),
        redirect_chain=(requested,),
        body=body,
        fetched_at=NOW.isoformat().replace("+00:00", "Z"),
        error="HTTPError: Too Many Requests" if status == 429 else None,
    )


def body_with(mutator) -> bytes:  # type: ignore[no-untyped-def]
    payload = json.loads(VALID_BODY)
    mutator(payload)
    return json.dumps(payload, separators=(",", ":")).encode()


def set_period(meta: dict, start: datetime, end: datetime) -> None:
    meta["currentTradingPeriod"] = {
        "regular": {"start": int(start.timestamp()), "end": int(end.timestamp())}
    }


class StaticTransport:
    def __init__(self, responses: dict[str, HttpCapture]) -> None:
        self.responses = responses
        self.urls: list[str] = []

    def __call__(self, url: str) -> HttpCapture:
        self.urls.append(url)
        if url not in self.responses:
            raise AssertionError(f"unexpected network request: {url}")
        return self.responses[url]


class MarketRegimeIntradayDataTest(unittest.TestCase):
    def test_registry_freezes_cash_proxy_identity_and_yahoo_scope(self) -> None:
        registry = registry_payload()
        self.assertEqual(len(YAHOO_INSTRUMENTS), 11)
        self.assertEqual(registry["provider"], "yahoo_chart")
        self.assertEqual(registry["interval"], "5m")
        self.assertFalse(registry["publication_eligible"])
        self.assertEqual(INSTRUMENT_BY_KEY["sp500_cash"].canonical_symbol, "^GSPC")
        self.assertEqual(INSTRUMENT_BY_KEY["sp500_futures_proxy"].canonical_symbol, "ES=F")
        self.assertEqual(INSTRUMENT_BY_KEY["nasdaq_cash"].canonical_symbol, "^IXIC")
        self.assertEqual(INSTRUMENT_BY_KEY["nasdaq100_futures_proxy"].canonical_symbol, "NQ=F")
        self.assertNotEqual(
            INSTRUMENT_BY_KEY["sp500_cash"].canonical_symbol,
            INSTRUMENT_BY_KEY["sp500_futures_proxy"].canonical_symbol,
        )
        self.assertIn("Nasdaq-100 futures proxy", " ".join(registry["hard_invariants"]))

    def test_fixed_bytes_normalize_only_completed_bars_with_explicit_times(self) -> None:
        normalized = normalize_yahoo_capture(
            INSTRUMENT_BY_KEY["sp500_futures_proxy"],
            capture(),
            observed_at=NOW,
            received_at=NOW,
        )
        self.assertEqual(normalized["bar_count"], 3)
        self.assertEqual(normalized["provider_timestamp"], "2026-08-05T15:35:00Z")
        self.assertEqual(normalized["last_completed_bar_end_at"], "2026-08-05T15:40:00Z")
        self.assertEqual(normalized["dropped_unfinished_bars"], ["2026-08-05T15:45:00Z"])
        self.assertEqual(normalized["session_state"], "open")
        self.assertEqual(normalized["freshness"], "live_candidate")
        self.assertEqual(normalized["age_seconds"], 660)
        self.assertEqual(normalized["observed_at"], normalized["received_at"])
        self.assertFalse(normalized["publication_eligible"])
        self.assertFalse(normalized["action_eligible"])

    def test_null_disorder_duplicate_future_and_bad_ohlc_fail_closed(self) -> None:
        def partial(payload: dict) -> None:
            payload["chart"]["result"][0]["indicators"]["quote"][0]["close"][1] = None

        def duplicate(payload: dict) -> None:
            payload["chart"]["result"][0]["timestamp"][2] = payload["chart"]["result"][0]["timestamp"][1]

        def unordered(payload: dict) -> None:
            payload["chart"]["result"][0]["timestamp"][1:3] = reversed(
                payload["chart"]["result"][0]["timestamp"][1:3]
            )

        def future(payload: dict) -> None:
            payload["chart"]["result"][0]["timestamp"][0] = int((NOW + timedelta(minutes=5)).timestamp())

        def inverted(payload: dict) -> None:
            payload["chart"]["result"][0]["indicators"]["quote"][0]["high"][1] = 7000

        for mutate in (partial, duplicate, unordered, future, inverted):
            with self.subTest(mutate=mutate.__name__):
                with self.assertRaises(SourceCaptureError):
                    normalize_yahoo_capture(
                        INSTRUMENT_BY_KEY["sp500_futures_proxy"],
                        capture(body_with(mutate)),
                        observed_at=NOW,
                        received_at=NOW,
                    )

    def test_trailing_all_null_bar_is_dropped_and_disclosed(self) -> None:
        def make_null(payload: dict) -> None:
            quote = payload["chart"]["result"][0]["indicators"]["quote"][0]
            for field in ("open", "high", "low", "close"):
                quote[field][-1] = None
            quote["volume"][-1] = 0

        normalized = normalize_yahoo_capture(
            INSTRUMENT_BY_KEY["sp500_futures_proxy"],
            capture(body_with(make_null)),
            observed_at=NOW,
            received_at=NOW,
        )
        self.assertEqual(normalized["bar_count"], 3)
        self.assertEqual(normalized["dropped_all_null_bars"], ["2026-08-05T15:45:00Z"])
        self.assertEqual(normalized["dropped_unfinished_bars"], [])

        def make_internal_null(payload: dict) -> None:
            quote = payload["chart"]["result"][0]["indicators"]["quote"][0]
            for field in ("open", "high", "low", "close"):
                quote[field][1] = None
            quote["volume"][1] = 0

        internal = normalize_yahoo_capture(
            INSTRUMENT_BY_KEY["sp500_futures_proxy"],
            capture(body_with(make_internal_null)),
            observed_at=NOW,
            received_at=NOW,
        )
        self.assertEqual(internal["dropped_internal_all_null_bars"], ["2026-08-05T15:30:00Z"])

        def null_with_volume(payload: dict) -> None:
            make_internal_null(payload)
            payload["chart"]["result"][0]["indicators"]["quote"][0]["volume"][1] = 100

        with self.assertRaisesRegex(SourceCaptureError, "non-zero volume"):
            normalize_yahoo_capture(
                INSTRUMENT_BY_KEY["sp500_futures_proxy"],
                capture(body_with(null_with_volume)),
                observed_at=NOW,
                received_at=NOW,
            )

    def test_http_mime_shape_symbol_currency_and_timezone_are_identity_gates(self) -> None:
        cases = [
            capture(status=429, body=RATE_LIMIT_BODY, content_type="text/html"),
            capture(body=b"<html>blocked</html>", content_type="text/html"),
            capture(body=b"not-json"),
            capture(body=body_with(lambda p: p["chart"]["result"][0]["meta"].update(symbol="NQ=F"))),
            capture(body=body_with(lambda p: p["chart"]["result"][0]["meta"].update(currency="EUR"))),
            capture(body=body_with(lambda p: p["chart"]["result"][0]["meta"].update(exchangeTimezoneName="UTC"))),
        ]
        for item in cases:
            with self.subTest(status=item.status_code, content_type=item.content_type):
                with self.assertRaises(SourceCaptureError):
                    normalize_yahoo_capture(
                        INSTRUMENT_BY_KEY["sp500_futures_proxy"],
                        item,
                        observed_at=NOW,
                        received_at=NOW,
                    )

    def test_sessions_cover_weekend_holiday_dst_lunch_and_maintenance(self) -> None:
        future = INSTRUMENT_BY_KEY["sp500_futures_proxy"]
        weekend = datetime(2026, 8, 8, 15, 0, tzinfo=timezone.utc)
        self.assertEqual(classify_yahoo_session(future, weekend, {}), "closed")

        cash = INSTRUMENT_BY_KEY["sp500_cash"]
        holiday = datetime(2026, 9, 7, 15, 0, tzinfo=timezone.utc)
        old_start = datetime(2026, 9, 4, 13, 30, tzinfo=timezone.utc)
        old_end = datetime(2026, 9, 4, 20, 0, tzinfo=timezone.utc)
        meta: dict = {"currentTradingPeriod": {"regular": {"start": int(old_start.timestamp()), "end": int(old_end.timestamp())}}}
        self.assertEqual(classify_yahoo_session(cash, holiday, meta), "closed")

        for local_date in ((2026, 1, 8), (2026, 7, 8)):
            zone = ZoneInfo("America/New_York")
            start = datetime(*local_date, 9, 30, tzinfo=zone)
            end = datetime(*local_date, 16, 0, tzinfo=zone)
            observed = datetime(*local_date, 11, 0, tzinfo=zone)
            dst_meta: dict = {}
            set_period(dst_meta, start, end)
            self.assertEqual(classify_yahoo_session(cash, observed, dst_meta), "open")

        nikkei = INSTRUMENT_BY_KEY["nikkei"]
        tokyo = ZoneInfo("Asia/Tokyo")
        lunch = datetime(2026, 8, 5, 12, 0, tzinfo=tokyo)
        japan_meta: dict = {}
        set_period(
            japan_meta,
            datetime(2026, 8, 5, 9, 0, tzinfo=tokyo),
            datetime(2026, 8, 5, 15, 30, tzinfo=tokyo),
        )
        self.assertEqual(classify_yahoo_session(nikkei, lunch, japan_meta), "lunch_break")

        new_york = ZoneInfo("America/New_York")
        maintenance = datetime(2026, 8, 5, 17, 30, tzinfo=new_york)
        self.assertEqual(classify_yahoo_session(future, maintenance, {}), "maintenance")

    def test_query1_fallback_to_query2_is_explicit(self) -> None:
        spec = INSTRUMENT_BY_KEY["sp500_futures_proxy"]
        query1, query2 = yahoo_urls(spec)
        valid_query2 = capture(url=query2)
        transport = StaticTransport(
            {
                query1: capture(url=query1, status=502, body=b"gateway", content_type="text/html"),
                query2: valid_query2,
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            snapshot = MarketRegimeIntradayDataStore(directory, http_get=transport).refresh(
                instrument_keys=[spec.key], now=NOW, run_id="fallback-run"
            )
        self.assertEqual(transport.urls, [query1, query2])
        self.assertEqual(snapshot["accepted_count"], 1)
        self.assertEqual(snapshot["instruments"][0]["selected_endpoint"], "query2")
        self.assertEqual(
            [item["accepted"] for item in snapshot["instruments"][0]["source_attempts"]],
            [False, True],
        )

    def test_failure_preserves_last_good_times_and_recomputes_only_current_age(self) -> None:
        spec = INSTRUMENT_BY_KEY["sp500_futures_proxy"]
        query1, query2 = yahoo_urls(spec)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            good_transport = StaticTransport({query1: capture(url=query1)})
            good_store = MarketRegimeIntradayDataStore(root, http_get=good_transport)
            good = good_store.refresh(
                instrument_keys=[spec.key], now=NOW, run_id="good-run"
            )
            pointer_path = root / "intraday/instruments/sp500_futures_proxy/latest-good.json"
            pointer_before = pointer_path.read_bytes()
            original = good["instruments"][0]

            bad_transport = StaticTransport(
                {
                    query1: capture(url=query1, status=502, body=b"gateway", content_type="text/html"),
                    query2: capture(url=query2, status=429, body=RATE_LIMIT_BODY, content_type="text/html"),
                }
            )
            failed_store = MarketRegimeIntradayDataStore(root, http_get=bad_transport)
            later = NOW + timedelta(hours=2)
            partial = failed_store.refresh(
                instrument_keys=[spec.key], now=later, run_id="failed-run"
            )
            fallback = partial["instruments"][0]
            self.assertEqual(partial["quality"], "partial")
            self.assertEqual(fallback["refresh_status"], "rejected")
            self.assertEqual(fallback["observed_at"], original["observed_at"])
            self.assertEqual(fallback["received_at"], original["received_at"])
            self.assertGreater(fallback["current_age_seconds"], original["age_seconds"])
            self.assertEqual(fallback["freshness"], "delayed")
            self.assertEqual(
                fallback["refresh_failure"]["source_attempts"][-1]["bounded_raw_excerpt"],
                "Edge: Too Many Requests",
            )
            self.assertEqual(pointer_path.read_bytes(), pointer_before)
            self.assertEqual(failed_store.latest()["snapshot_id"], partial["snapshot_id"])

    def test_fixed_fixture_replay_has_same_snapshot_and_artifact_identity(self) -> None:
        identities = []
        for _ in range(2):
            spec = INSTRUMENT_BY_KEY["sp500_futures_proxy"]
            query1, _ = yahoo_urls(spec)
            transport = StaticTransport({query1: capture(url=query1)})
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                snapshot = MarketRegimeIntradayDataStore(root, http_get=transport).refresh(
                    instrument_keys=[spec.key], now=NOW, run_id="replay-run"
                )
                identities.append(
                    (
                        snapshot["snapshot_id"],
                        snapshot["instruments"][0]["normalized_artifact"]["sha256"],
                    )
                )
        self.assertEqual(identities[0], identities[1])

    def test_unknown_symbol_is_rejected_before_transport_and_tamper_fails(self) -> None:
        transport = StaticTransport({})
        with tempfile.TemporaryDirectory() as directory:
            store = MarketRegimeIntradayDataStore(directory, http_get=transport)
            with self.assertRaisesRegex(MarketRegimeIntradayDataError, "unknown"):
                store.refresh(instrument_keys=["ES=F"], now=NOW, run_id="bad")
            self.assertEqual(transport.urls, [])

            spec = INSTRUMENT_BY_KEY["sp500_futures_proxy"]
            query1, _ = yahoo_urls(spec)
            transport.responses[query1] = capture(url=query1)
            snapshot = store.refresh(instrument_keys=[spec.key], now=NOW, run_id="good")
            pointer = json.loads(Path(directory, "intraday/latest.json").read_text())
            artifact = Path(directory, pointer["snapshot"]["path"])
            artifact.write_bytes(artifact.read_bytes() + b" ")
            with self.assertRaisesRegex(MarketRegimeIntradayDataError, "hash mismatch"):
                store.latest()
            self.assertTrue(snapshot["snapshot_id"].startswith("market-regime-intraday-snapshot:"))

    def test_private_or_public_collection_remains_fail_closed(self) -> None:
        spec = INSTRUMENT_BY_KEY["sp500_futures_proxy"]
        query1, _ = yahoo_urls(spec)
        transport = StaticTransport({query1: capture(url=query1)})
        with tempfile.TemporaryDirectory() as directory:
            store = MarketRegimeIntradayDataStore(directory, http_get=transport)
            for mode in ("private_beta", "public"):
                with self.subTest(mode=mode), self.assertRaisesRegex(LicenseGateError, "disabled"):
                    store.refresh(
                        instrument_keys=[spec.key],
                        now=NOW,
                        run_id=f"blocked-{mode}",
                        deployment_mode=mode,
                    )
        self.assertEqual(transport.urls, [])

    def test_fixture_run_id_cannot_escape_runtime_root(self) -> None:
        transport = StaticTransport({})
        with tempfile.TemporaryDirectory() as directory:
            store = MarketRegimeIntradayDataStore(directory, http_get=transport)
            with self.assertRaisesRegex(MarketRegimeIntradayDataError, "unsafe"):
                store.refresh(
                    instrument_keys=["sp500_futures_proxy"],
                    now=NOW,
                    run_id="../../escape",
                )
        self.assertEqual(transport.urls, [])


if __name__ == "__main__":
    unittest.main()
