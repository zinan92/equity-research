from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from zoneinfo import ZoneInfo


PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT))

from data_core.market_regime_data import (  # noqa: E402
    HttpCapture,
    LicenseGateError,
    SourceCaptureError,
)
from data_core.market_regime_macro_data import (  # noqa: E402
    DXY_CHART_URL,
    MACRO_FACTOR_BY_KEY,
    MIN_OBSERVATIONS,
    MarketRegimeMacroDataError,
    MarketRegimeMacroDataStore,
    macro_registry_payload,
    normalize_dxy,
    parse_treasury_captures,
)


NOW = datetime(2026, 8, 6, 23, 0, tzinfo=timezone.utc)


def capture(
    body: bytes,
    *,
    url: str = "https://example.test/source",
    status: int | None = 200,
    content_type: str = "application/json; charset=utf-8",
    fetched_at: str = "2026-08-06T23:00:00Z",
    error: str | None = None,
) -> HttpCapture:
    return HttpCapture(
        "GET",
        url,
        url,
        status,
        (("content-type", content_type),),
        (),
        (url,),
        body,
        fetched_at,
        error,
    )


def completed_dates(count: int, *, end: date = date(2026, 8, 5)) -> list[date]:
    return [end - timedelta(days=count - index - 1) for index in range(count)]


def dxy_body(*, count: int = 210, end: date = date(2026, 8, 5)) -> bytes:
    dates = completed_dates(count, end=end)
    zone = ZoneInfo("America/New_York")
    timestamps = [
        int(datetime.combine(item, time(9, 30), tzinfo=zone).timestamp())
        for item in dates
    ]
    values = [100 + index / 10 for index in range(count)]
    return json.dumps(
        {
            "chart": {
                "result": [
                    {
                        "meta": {
                            "symbol": "DX-Y.NYB",
                            "currency": "USD",
                            "exchangeTimezoneName": "America/New_York",
                            "regularMarketTime": int(
                                datetime.combine(end, time(17), tzinfo=zone).timestamp()
                            ),
                            "currentTradingPeriod": {
                                "regular": {
                                    "end": int(
                                        datetime.combine(end, time(17), tzinfo=zone).timestamp()
                                    )
                                }
                            },
                        },
                        "timestamp": timestamps,
                        "indicators": {
                            "quote": [
                                {
                                    "open": values,
                                    "high": [value + 0.2 for value in values],
                                    "low": [value - 0.2 for value in values],
                                    "close": [value + 0.1 for value in values],
                                    "volume": [0 for _ in values],
                                }
                            ]
                        },
                    }
                ],
                "error": None,
            }
        }
    ).encode()


def treasury_csv(
    *,
    count: int = 150,
    end: date = date(2026, 8, 5),
    descending: bool = True,
    two_start: float = 4.0,
    ten_start: float = 4.5,
) -> bytes:
    dates = completed_dates(count, end=end)
    rows = [
        (
            item.strftime("%m/%d/%Y"),
            f"{two_start + index / 100:.2f}",
            f"{ten_start + index / 100:.2f}",
        )
        for index, item in enumerate(dates)
    ]
    if descending:
        rows.reverse()
    lines = ["Date,2 Yr,10 Yr", *[",".join(row) for row in rows]]
    return ("\n".join(lines) + "\n").encode()


def treasury_capture(body: bytes, *, url: str = "https://home.treasury.gov/test.csv") -> HttpCapture:
    return capture(body, url=url, content_type="text/csv; charset=utf-8")


class FakeTransport:
    def __init__(self, *, dxy: HttpCapture | None = None, treasury: HttpCapture | None = None) -> None:
        self.dxy = dxy or capture(dxy_body(), url=DXY_CHART_URL)
        self.treasury = treasury or treasury_capture(treasury_csv())
        self.calls: list[str] = []

    def __call__(self, url: str) -> HttpCapture:
        self.calls.append(url)
        return self.dxy if "finance.yahoo.com" in url else self.treasury


class MarketRegimeMacroDataTest(unittest.TestCase):
    def test_registry_freezes_units_authority_and_publication_boundary(self) -> None:
        registry = macro_registry_payload()
        self.assertEqual(set(MACRO_FACTOR_BY_KEY), {"dxy", "us2y", "us10y", "us2s10s"})
        self.assertEqual(MACRO_FACTOR_BY_KEY["dxy"].change_unit, "percent_return")
        self.assertEqual(MACRO_FACTOR_BY_KEY["us2y"].change_unit, "basis_points")
        self.assertEqual(MACRO_FACTOR_BY_KEY["us2s10s"].level_unit, "basis_points")
        self.assertEqual(registry["sources"]["treasury"]["authority_tier"], "official_government_source")
        self.assertFalse(registry["publication_eligible"])
        self.assertFalse(registry["action_eligible"])

    def test_dxy_normalizes_completed_daily_bars_and_percent_changes(self) -> None:
        normalized = normalize_dxy(capture(dxy_body(), url=DXY_CHART_URL), now=NOW)
        self.assertEqual(normalized["last_completed_session"], "2026-08-05")
        self.assertEqual(len(normalized["bars"]), 210)
        self.assertEqual(normalized["factor"]["key"], "dxy")
        self.assertGreater(normalized["changes"]["5d_pct"], 0)
        self.assertEqual(normalized["source"]["raw_bytes"], len(dxy_body()))

    def test_dxy_drops_unfinished_session_and_rejects_identity_mismatch(self) -> None:
        payload = json.loads(dxy_body(end=date(2026, 8, 6)))
        result = payload["chart"]["result"][0]
        result["meta"]["regularMarketTime"] = int(
            datetime(2026, 8, 6, 14, 0, tzinfo=ZoneInfo("America/New_York")).timestamp()
        )
        before_close = datetime(2026, 8, 6, 18, 0, tzinfo=timezone.utc)
        normalized = normalize_dxy(
            capture(json.dumps(payload).encode(), url=DXY_CHART_URL), now=before_close
        )
        self.assertEqual(normalized["last_completed_session"], "2026-08-05")
        self.assertEqual(normalized["dropped_unfinished_sessions"], ["2026-08-06"])

        for field, value in (("symbol", "DX"), ("currency", "EUR")):
            broken = json.loads(dxy_body())
            broken["chart"]["result"][0]["meta"][field] = value
            with self.subTest(field=field):
                with self.assertRaises(SourceCaptureError):
                    normalize_dxy(
                        capture(json.dumps(broken).encode(), url=DXY_CHART_URL), now=NOW
                    )

        with self.assertRaises(SourceCaptureError):
            normalize_dxy(capture(b"{not-json", url=DXY_CHART_URL), now=NOW)

    def test_treasury_reorders_descending_rows_and_derives_curve_same_date(self) -> None:
        parsed = parse_treasury_captures([treasury_capture(treasury_csv())], now=NOW)
        two = parsed["us2y"]
        ten = parsed["us10y"]
        curve = parsed["us2s10s"]
        self.assertEqual(two["last_completed_session"], "2026-08-05")
        self.assertEqual(two["observations"][0]["date"], completed_dates(150)[0].isoformat())
        self.assertEqual(two["changes"]["5d_bp"], 5.0)
        self.assertEqual(ten["changes"]["20d_bp"], 20.0)
        self.assertEqual(curve["value"], 50.0)
        self.assertEqual(curve["level_unit"], "basis_points")
        self.assertEqual(curve["derivation"]["latest_inputs"]["date"], "2026-08-05")
        self.assertEqual(curve["source"]["provider_orders"], ["descending_reordered"])

    def test_treasury_can_merge_two_year_captures_without_losing_order(self) -> None:
        older = treasury_capture(
            treasury_csv(count=80, end=date(2025, 12, 31)),
            url="https://home.treasury.gov/2025.csv",
        )
        newer = treasury_capture(
            treasury_csv(count=80, end=date(2026, 8, 5)),
            url="https://home.treasury.gov/2026.csv",
        )
        parsed = parse_treasury_captures([newer, older], now=NOW)
        observations = parsed["us10y"]["observations"]
        self.assertEqual(len(observations), 160)
        self.assertLess(observations[0]["date"], observations[-1]["date"])

    def test_treasury_weekend_gap_is_fresh_and_old_source_is_stale(self) -> None:
        friday = treasury_capture(treasury_csv(end=date(2026, 8, 7)))
        monday = datetime(2026, 8, 10, 18, 0, tzinfo=timezone.utc)
        later = datetime(2026, 8, 20, 18, 0, tzinfo=timezone.utc)
        self.assertEqual(parse_treasury_captures([friday], now=monday)["us2y"]["quality"], "fresh")
        self.assertEqual(parse_treasury_captures([friday], now=later)["us2y"]["quality"], "stale")

    def test_treasury_rejects_bad_transport_shape_and_semantics(self) -> None:
        cases = {
            "HTTP status": capture(b"down", status=503, content_type="text/csv"),
            "Content-Type": capture(b"<html>blocked</html>", content_type="text/html"),
            "columns": treasury_capture(b"Date,1 Yr\n08/05/2026,4.00\n"),
            "unavailable": treasury_capture(b"Date,2 Yr,10 Yr\n08/05/2026,N/A,4.50\n"),
            "future": treasury_capture(b"Date,2 Yr,10 Yr\n08/07/2026,4.00,4.50\n"),
            "duplicate": treasury_capture(
                b"Date,2 Yr,10 Yr\n08/05/2026,4.00,4.50\n08/05/2026,4.01,4.51\n"
            ),
            "unordered": treasury_capture(
                b"Date,2 Yr,10 Yr\n08/04/2026,4.00,4.50\n08/05/2026,4.01,4.51\n08/03/2026,3.99,4.49\n"
            ),
            "too short": treasury_capture(treasury_csv(count=20)),
        }
        for expected, item in cases.items():
            with self.subTest(expected=expected):
                with self.assertRaisesRegex(SourceCaptureError, expected):
                    parse_treasury_captures([item], now=NOW)

    def test_store_persists_raw_receipts_immutable_factors_and_stable_identity(self) -> None:
        with tempfile.TemporaryDirectory() as first_temp, tempfile.TemporaryDirectory() as second_temp:
            first_transport = FakeTransport()
            first_store = MarketRegimeMacroDataStore(first_temp, http_get=first_transport)
            first = first_store.refresh(now=NOW)
            second = MarketRegimeMacroDataStore(second_temp, http_get=FakeTransport()).refresh(now=NOW)

            self.assertEqual(first["factor_count"], 4)
            self.assertEqual(first["quality"], "fresh")
            first_by_key = {item["factor"]["key"]: item for item in first["factors"]}
            second_by_key = {item["factor"]["key"]: item for item in second["factors"]}
            self.assertEqual(
                {key: value["factor_id"] for key, value in first_by_key.items()},
                {key: value["factor_id"] for key, value in second_by_key.items()},
            )
            dxy_receipt = first_by_key["dxy"]["source_receipt"]["captures"][0]
            self.assertEqual(dxy_receipt["method"], "GET")
            self.assertTrue(dxy_receipt["raw_path"].startswith("raw/"))
            self.assertTrue((Path(first_temp) / dxy_receipt["raw_path"]).exists())
            self.assertEqual(first_store.latest()["run_id"], first["run_id"])

            dxy_artifact = Path(first_temp) / first_by_key["dxy"]["artifact"]["path"]
            dxy_artifact.write_bytes(dxy_artifact.read_bytes() + b" ")
            with self.assertRaisesRegex(MarketRegimeMacroDataError, "hash mismatch"):
                first_store.latest()

            second_dxy = second_by_key["dxy"]
            second_raw = (
                Path(second_temp)
                / second_dxy["source_receipt"]["captures"][0]["raw_path"]
            )
            second_raw.write_bytes(second_raw.read_bytes() + b" ")
            with self.assertRaisesRegex(MarketRegimeMacroDataError, "raw artifact hash mismatch"):
                MarketRegimeMacroDataStore(
                    second_temp, http_get=FakeTransport()
                ).latest()

    def test_failed_refresh_retains_last_good_and_records_bounded_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = MarketRegimeMacroDataStore(temp, http_get=FakeTransport())
            accepted = store.refresh(now=NOW, factor_keys=["us2y"])
            accepted_by_key = {item["factor"]["key"]: item for item in accepted["factors"]}
            accepted_id = accepted_by_key["us2y"]["factor_id"]
            pointer_path = Path(temp) / "factors" / "us2y" / "latest-good.json"
            pointer_before = pointer_path.read_bytes()
            failed_transport = FakeTransport(
                treasury=capture(
                    b"<html>Access Denied request id 123</html>",
                    url="https://home.treasury.gov/test.csv",
                    status=403,
                    content_type="text/html",
                )
            )
            fallback = MarketRegimeMacroDataStore(temp, http_get=failed_transport).refresh(
                now=NOW + timedelta(hours=1), factor_keys=["us2y"]
            )
            factor = next(
                item for item in fallback["factors"] if item["factor"]["key"] == "us2y"
            )
            self.assertEqual(factor["factor_id"], accepted_id)
            self.assertEqual(factor["refresh_status"], "rejected")
            self.assertIn("Access Denied", factor["refresh_failure"]["bounded_raw_excerpt"])
            self.assertEqual(fallback["quality"], "partial")
            self.assertEqual(pointer_path.read_bytes(), pointer_before)

    def test_zero_byte_attempt_is_stored_and_hashed_even_when_rejected(self) -> None:
        empty = capture(b"", url=DXY_CHART_URL, error=None)
        with tempfile.TemporaryDirectory() as temp:
            snapshot = MarketRegimeMacroDataStore(
                temp, http_get=FakeTransport(dxy=empty)
            ).refresh(now=NOW, factor_keys=["dxy"])
            receipt = json.loads((Path(temp) / snapshot["refresh_receipt"]).read_text())
            source = receipt["results"][0]["source"]
            self.assertEqual(source["raw_bytes"], 0)
            self.assertEqual(
                source["raw_sha256"],
                "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            )
            raw_path = Path(temp) / source["raw_path"]
            self.assertTrue(raw_path.exists())
            self.assertEqual(raw_path.read_bytes(), b"")

        empty_treasury = capture(
            b"",
            url="https://home.treasury.gov/empty.csv",
            content_type="text/csv",
        )
        with tempfile.TemporaryDirectory() as temp:
            snapshot = MarketRegimeMacroDataStore(
                temp, http_get=FakeTransport(treasury=empty_treasury)
            ).refresh(now=NOW, factor_keys=["us2y"])
            receipt = json.loads((Path(temp) / snapshot["refresh_receipt"]).read_text())
            source = receipt["results"][0]["sources"][0]
            self.assertEqual(source["raw_bytes"], 0)
            self.assertEqual(
                source["raw_sha256"],
                "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            )
            self.assertEqual((Path(temp) / source["raw_path"]).read_bytes(), b"")

    def test_subset_refresh_preserves_four_factor_surface_and_marks_partial(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            first = MarketRegimeMacroDataStore(temp, http_get=FakeTransport()).refresh(now=NOW)
            first_by_key = {item["factor"]["key"]: item for item in first["factors"]}
            changed = FakeTransport(
                treasury=treasury_capture(
                    treasury_csv(two_start=4.1, ten_start=4.6)
                )
            )
            second = MarketRegimeMacroDataStore(temp, http_get=changed).refresh(
                now=NOW + timedelta(hours=1), factor_keys=["us2y"]
            )
            second_by_key = {item["factor"]["key"]: item for item in second["factors"]}
            self.assertEqual(second["factor_count"], 4)
            self.assertEqual(second["quality"], "partial")
            self.assertNotEqual(second_by_key["us2y"]["factor_id"], first_by_key["us2y"]["factor_id"])
            for key in ("dxy", "us10y", "us2s10s"):
                self.assertEqual(second_by_key[key]["factor_id"], first_by_key[key]["factor_id"])
                self.assertEqual(second_by_key[key]["refresh_status"], "not_refreshed")

    def test_status_distinguishes_unused_runtime_from_integrity_failure(self) -> None:
        script = PRODUCT.parent / "scripts" / "refresh_market_regime_macro_data.py"
        with tempfile.TemporaryDirectory() as empty_temp:
            empty_result = subprocess.run(
                [sys.executable, str(script), "--root", empty_temp, "--status"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(empty_result.returncode, 0)
            self.assertEqual(json.loads(empty_result.stdout)["quality"], "unavailable")

        with tempfile.TemporaryDirectory() as corrupt_temp:
            snapshot = MarketRegimeMacroDataStore(
                corrupt_temp, http_get=FakeTransport()
            ).refresh(now=NOW)
            artifact = Path(corrupt_temp) / snapshot["factors"][0]["artifact"]["path"]
            artifact.write_bytes(artifact.read_bytes() + b" ")
            corrupt_result = subprocess.run(
                [sys.executable, str(script), "--root", corrupt_temp, "--status"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(corrupt_result.returncode, 2)
            self.assertIn("hash mismatch", json.loads(corrupt_result.stdout)["reason"])

    def test_unknown_factor_is_rejected_before_transport_and_private_beta_is_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            transport = FakeTransport()
            store = MarketRegimeMacroDataStore(temp, http_get=transport)
            with self.assertRaisesRegex(MarketRegimeMacroDataError, "unknown macro factors"):
                store.refresh(now=NOW, factor_keys=["usd"])
            self.assertEqual(transport.calls, [])
            with self.assertRaises(LicenseGateError):
                store.refresh(
                    now=NOW,
                    factor_keys=["dxy"],
                    deployment_mode="private_beta",
                    license_status="local_evaluation_only",
                )

    def test_default_live_transport_refuses_clock_override(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(MarketRegimeMacroDataError, "clock overrides"):
                MarketRegimeMacroDataStore(temp).refresh(now=NOW, factor_keys=["dxy"])

    def test_minimum_history_contract_is_not_accidentally_weakened(self) -> None:
        self.assertEqual(MIN_OBSERVATIONS, 120)


if __name__ == "__main__":
    unittest.main()
