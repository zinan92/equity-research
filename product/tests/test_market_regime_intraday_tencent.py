from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest
from zoneinfo import ZoneInfo


PRODUCT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures" / "market-regime-intraday"
sys.path.insert(0, str(PRODUCT))

from data_core.market_regime_data import HttpCapture, SourceCaptureError  # noqa: E402
from data_core.market_regime_intraday_data import (  # noqa: E402
    INSTRUMENT_BY_KEY,
    TENCENT_INSTRUMENTS,
    MarketRegimeIntradayDataStore,
    classify_tencent_session,
    normalize_tencent_captures,
    parse_tencent_quote_batch,
    tencent_m5_url,
    tencent_quote_url,
)


NOW = datetime(2026, 8, 5, 2, 45, 10, tzinfo=timezone.utc)
ZONE = ZoneInfo("Asia/Shanghai")
QUOTE_BODY = (FIXTURES / "tencent-quote-batch-200.txt").read_bytes()
M5_BODY = (FIXTURES / "tencent-m5-sh000001-200.json").read_bytes()


def capture(
    body: bytes,
    *,
    url: str,
    status: int = 200,
    content_type: str = "text/html; charset=UTF-8",
) -> HttpCapture:
    return HttpCapture(
        method="GET",
        requested_url=url,
        final_url=url,
        status_code=status,
        response_headers=(("content-type", content_type),),
        dropped_header_names=(),
        redirect_chain=(url,),
        body=body,
        fetched_at=NOW.isoformat().replace("+00:00", "Z"),
        error=f"HTTPError: {status}" if status != 200 else None,
    )


def quote_body_for(*symbols: str) -> bytes:
    wanted = set(symbols)
    lines = [
        line for line in QUOTE_BODY.decode().splitlines()
        if line.split('="', 1)[0].removeprefix("v_") in wanted
    ]
    return ("\n".join(lines) + "\n").encode()


def m5_body_for(symbol: str, mutator=None) -> bytes:  # type: ignore[no-untyped-def]
    payload = json.loads(M5_BODY)
    row = payload["data"].pop("sh000001")
    quote = row["qt"].pop("sh000001")
    quote[1] = symbol
    quote[2] = symbol[2:]
    row["qt"][symbol] = quote
    payload["data"][symbol] = row
    if mutator is not None:
        mutator(payload)
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()


class StaticTransport:
    def __init__(self, responses: dict[str, HttpCapture]) -> None:
        self.responses = responses
        self.urls: list[str] = []

    def __call__(self, url: str) -> HttpCapture:
        self.urls.append(url)
        if url not in self.responses:
            raise AssertionError(f"unexpected network request: {url}")
        return self.responses[url]


def fixture_transport(*, fail_symbol: str | None = None) -> StaticTransport:
    quote_url = tencent_quote_url(TENCENT_INSTRUMENTS)
    responses = {
        quote_url: capture(QUOTE_BODY, url=quote_url),
    }
    for spec in TENCENT_INSTRUMENTS:
        url = tencent_m5_url(spec)
        if spec.provider_symbol == fail_symbol:
            responses[url] = capture(b"gateway", url=url, status=502)
        else:
            responses[url] = capture(m5_body_for(spec.provider_symbol), url=url)
    return StaticTransport(responses)


class MarketRegimeIntradayTencentTest(unittest.TestCase):
    def test_fixed_quote_and_m5_bytes_normalize_completed_interval_end_bars(self) -> None:
        quote_capture = capture(QUOTE_BODY, url=tencent_quote_url(TENCENT_INSTRUMENTS))
        parsed = parse_tencent_quote_batch(quote_capture, TENCENT_INSTRUMENTS)
        spec = INSTRUMENT_BY_KEY["shanghai"]
        normalized = normalize_tencent_captures(
            spec,
            parsed[spec.provider_symbol],
            capture(M5_BODY, url=tencent_m5_url(spec)),
            observed_at=NOW,
            received_at=NOW,
        )
        self.assertEqual(normalized["timestamp_semantics"], "interval_end")
        self.assertEqual(normalized["bar_count"], 3)
        self.assertEqual(normalized["provider_timestamp"], "2026-08-05T02:40:00Z")
        self.assertEqual(normalized["dropped_unfinished_bars"], ["2026-08-05T02:45:00Z"])
        self.assertEqual(normalized["session_state"], "open")
        self.assertEqual(normalized["freshness"], "live_candidate")
        self.assertEqual(normalized["age_seconds"], 310)
        self.assertEqual(normalized["source_quality_flags"], ["provider_declares_text_html_for_json"])
        self.assertFalse(normalized["publication_eligible"])
        self.assertFalse(normalized["action_eligible"])

    def test_a_share_sessions_cover_pre_morning_lunch_afternoon_post_weekend_holiday(self) -> None:
        def local(hour: int, minute: int, *, day: int = 5) -> datetime:
            return datetime(2026, 8, day, hour, minute, tzinfo=ZONE)

        cases = [
            (local(9, 15), local(9, 15), "close", "pre"),
            (local(10, 0), local(10, 0), "open", "open"),
            (local(12, 0), local(11, 30), "close", "lunch_break"),
            (local(12, 0), local(12, 0), "open", "unknown"),
            (local(14, 0), local(14, 0), "open", "open"),
            (local(15, 30), local(15, 0), "close", "post"),
            (local(10, 0, day=8), local(15, 0), "close", "closed"),
        ]
        for observed, quote_at, market_state, expected in cases:
            with self.subTest(observed=observed, state=market_state):
                self.assertEqual(
                    classify_tencent_session(
                        observed,
                        quote_at=quote_at,
                        market_observed_at=observed,
                        market_state=market_state,
                    ),
                    expected,
                )
        holiday = datetime(2026, 9, 7, 10, 0, tzinfo=ZONE)
        previous = datetime(2026, 9, 4, 15, 0, tzinfo=ZONE)
        self.assertEqual(
            classify_tencent_session(
                holiday,
                quote_at=previous,
                market_observed_at=holiday,
                market_state="close",
            ),
            "closed",
        )
        self.assertEqual(
            classify_tencent_session(
                holiday,
                quote_at=previous,
                market_observed_at=holiday,
                market_state="open",
            ),
            "unknown",
        )
        delayed_open = datetime(2026, 8, 5, 10, 30, tzinfo=ZONE)
        self.assertEqual(
            classify_tencent_session(
                delayed_open,
                quote_at=datetime(2026, 8, 5, 10, 0, tzinfo=ZONE),
                market_observed_at=delayed_open,
                market_state="open",
            ),
            "unknown",
        )

    def test_quote_batch_requires_exact_fixed_identities(self) -> None:
        url = tencent_quote_url(TENCENT_INSTRUMENTS)
        with self.assertRaisesRegex(SourceCaptureError, "missing"):
            parse_tencent_quote_batch(
                capture(quote_body_for("sh000001"), url=url),
                TENCENT_INSTRUMENTS,
            )
        wrong = QUOTE_BODY.replace(b"v_sh000688", b"v_sh999999", 1)
        with self.assertRaisesRegex(SourceCaptureError, "identity"):
            parse_tencent_quote_batch(capture(wrong, url=url), TENCENT_INSTRUMENTS)
        with self.assertRaisesRegex(SourceCaptureError, "content type"):
            parse_tencent_quote_batch(
                capture(QUOTE_BODY, url=url, content_type="application/json"),
                TENCENT_INSTRUMENTS,
            )

    def test_bad_m5_shape_order_future_and_quote_conflict_fail_closed(self) -> None:
        spec = INSTRUMENT_BY_KEY["shanghai"]
        quote_capture = capture(QUOTE_BODY, url=tencent_quote_url(TENCENT_INSTRUMENTS))
        row = parse_tencent_quote_batch(quote_capture, TENCENT_INSTRUMENTS)[spec.provider_symbol]

        def duplicate(payload: dict) -> None:
            rows = payload["data"]["sh000001"]["m5"]
            rows[2][0] = rows[1][0]

        def future(payload: dict) -> None:
            payload["data"]["sh000001"]["m5"][-1][0] = "202608051050"

        def quote_conflict(payload: dict) -> None:
            payload["data"]["sh000001"]["qt"]["sh000001"][30] = "20260805105000"

        def embedded_future(payload: dict) -> None:
            payload["data"]["sh000001"]["qt"]["sh000001"][30] = "20260805104700"

        for mutate, pattern in (
            (duplicate, "duplicate"),
            (future, "future"),
            (quote_conflict, "future"),
            (embedded_future, "embedded quote timestamp is in the future"),
        ):
            with self.subTest(mutate=mutate.__name__), self.assertRaisesRegex(SourceCaptureError, pattern):
                normalize_tencent_captures(
                    spec,
                    row,
                    capture(m5_body_for("sh000001", mutate), url=tencent_m5_url(spec)),
                    observed_at=NOW,
                    received_at=NOW,
                )
        with self.assertRaisesRegex(SourceCaptureError, "JSON-shaped"):
            normalize_tencent_captures(
                spec,
                row,
                capture(b"<html>blocked</html>", url=tencent_m5_url(spec)),
                observed_at=NOW,
                received_at=NOW,
            )

    def test_store_fetches_one_quote_batch_and_one_m5_per_asset(self) -> None:
        transport = fixture_transport()
        with tempfile.TemporaryDirectory() as directory:
            snapshot = MarketRegimeIntradayDataStore(directory, http_get=transport).refresh(
                instrument_keys=[item.key for item in TENCENT_INSTRUMENTS],
                now=NOW,
                run_id="tencent-fixture",
            )
            replay = MarketRegimeIntradayDataStore(directory, http_get=transport).latest()
        self.assertEqual(snapshot, replay)
        self.assertEqual(snapshot["accepted_count"], 3)
        self.assertEqual(snapshot["quality"], "complete")
        self.assertEqual(len(transport.urls), 4)
        self.assertEqual(transport.urls[0], tencent_quote_url(TENCENT_INSTRUMENTS))
        self.assertEqual(
            [item["instrument"]["key"] for item in snapshot["instruments"]],
            ["shanghai", "star50", "china_dividend"],
        )
        quote_locators = {
            item["source_attempts"][0]["raw_path"] for item in snapshot["instruments"]
        }
        self.assertEqual(len(quote_locators), 1)

    def test_one_m5_failure_degrades_only_that_asset(self) -> None:
        transport = fixture_transport(fail_symbol="sh000688")
        with tempfile.TemporaryDirectory() as directory:
            snapshot = MarketRegimeIntradayDataStore(directory, http_get=transport).refresh(
                instrument_keys=[item.key for item in TENCENT_INSTRUMENTS],
                now=NOW,
                run_id="one-failure",
            )
        self.assertEqual(snapshot["quality"], "partial")
        self.assertEqual(snapshot["accepted_count"], 2)
        by_key = {item["instrument"]["key"]: item for item in snapshot["instruments"]}
        self.assertEqual(by_key["shanghai"]["refresh_status"], "accepted")
        self.assertEqual(by_key["star50"]["refresh_status"], "rejected")
        self.assertEqual(by_key["star50"]["freshness"], "unavailable")
        self.assertIn("gateway", by_key["star50"]["refresh_failure"]["source_attempts"][-1]["bounded_raw_excerpt"])

    def test_quote_failure_skips_m5_and_preserves_last_good_age(self) -> None:
        spec = INSTRUMENT_BY_KEY["shanghai"]
        quote_url = tencent_quote_url([spec])
        m5_url = tencent_m5_url(spec)
        good = StaticTransport(
            {
                quote_url: capture(quote_body_for(spec.provider_symbol), url=quote_url),
                m5_url: capture(M5_BODY, url=m5_url),
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = MarketRegimeIntradayDataStore(root, http_get=good)
            accepted = store.refresh(instrument_keys=[spec.key], now=NOW, run_id="good")
            pointer = root / "intraday/instruments/shanghai/latest-good.json"
            before = pointer.read_bytes()

            failed = StaticTransport(
                {quote_url: capture(b"gateway", url=quote_url, status=502)}
            )
            partial = MarketRegimeIntradayDataStore(root, http_get=failed).refresh(
                instrument_keys=[spec.key],
                now=NOW + timedelta(hours=2),
                run_id="quote-failed",
            )
            fallback = partial["instruments"][0]
            self.assertEqual(failed.urls, [quote_url])
            self.assertEqual(pointer.read_bytes(), before)
            self.assertEqual(fallback["observed_at"], accepted["instruments"][0]["observed_at"])
            self.assertGreater(fallback["current_age_seconds"], fallback["age_seconds"])
            self.assertEqual(fallback["refresh_status"], "rejected")

    def test_fixed_tencent_fixture_replays_to_same_snapshot_identity(self) -> None:
        identities = []
        for _ in range(2):
            with tempfile.TemporaryDirectory() as directory:
                snapshot = MarketRegimeIntradayDataStore(
                    directory, http_get=fixture_transport()
                ).refresh(
                    instrument_keys=[item.key for item in TENCENT_INSTRUMENTS],
                    now=NOW,
                    run_id="replay",
                )
                identities.append(snapshot["snapshot_id"])
        self.assertEqual(identities[0], identities[1])


if __name__ == "__main__":
    unittest.main()
