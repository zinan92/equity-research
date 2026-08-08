from __future__ import annotations

from datetime import datetime, timedelta, timezone
import http.client
import json
import os
from pathlib import Path
import sys
import tempfile
from threading import Thread
import unittest
from unittest.mock import patch


PRODUCT = Path(__file__).resolve().parents[1]
ROOT = PRODUCT.parent
sys.path.insert(0, str(PRODUCT))

from data_core.market_regime_data import MarketRegimeDataStore  # noqa: E402
from data_core.market_regime_intraday_data import (  # noqa: E402
    INTRADAY_INSTRUMENTS,
    YAHOO_INSTRUMENTS,
    MarketRegimeIntradayDataStore,
    yahoo_urls,
)
from data_core.market_regime_intraday_model import (  # noqa: E402
    MarketRegimeIntradayOverlayStore,
)
from data_core.market_regime_model import MarketRegimeAnalysisStore  # noqa: E402
from market_regime_runtime import (  # noqa: E402
    HEALTH_SCHEMA_VERSION,
    MarketRegimeApiStore,
    MarketRegimeRuntime,
    MarketRegimeRuntimeError,
    build_material_change_receipt,
    build_market_regime_api_payload,
    configured_interval_hours,
)
from product.tests.test_market_regime_intraday_model import (  # noqa: E402
    intraday_snapshot,
    persist_intraday,
    resign_snapshot,
)
from product.tests.test_market_regime_intraday_data import (  # noqa: E402
    NOW as RAW_FIXTURE_NOW,
    VALID_BODY as YAHOO_VALID_BODY,
    capture as yahoo_capture,
)
from product.tests.test_market_regime_intraday_tencent import (  # noqa: E402
    fixture_transport as tencent_fixture_transport,
)
from product.tests.test_market_regime_model import (  # noqa: E402
    RISK_ON_RATES,
    persist_snapshot,
    snapshot_for,
)


class FrozenDataStore:
    def __init__(self, root: Path) -> None:
        self.store = MarketRegimeDataStore(root)

    def refresh(self) -> dict:
        return self.store.latest()

    def latest(self) -> dict:
        return self.store.latest()


class FailedDataStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def refresh(self) -> dict:
        raise RuntimeError("upstream unavailable")


class FailedAnalysisStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def compile_latest(self) -> dict:
        raise RuntimeError("compile failed")


class FailedOverlayStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def compile_latest(self) -> dict:
        raise RuntimeError("overlay compile failed")


class FixedClock:
    def __init__(self, *values: datetime) -> None:
        self.values = list(values)

    def __call__(self) -> datetime:
        if not self.values:
            raise AssertionError("clock called too many times")
        return self.values.pop(0)


class MappingTransport:
    def __init__(self, responses: dict[str, object]) -> None:
        self.responses = responses
        self.urls: list[str] = []

    def __call__(self, url: str):  # type: ignore[no-untyped-def]
        self.urls.append(url)
        if url not in self.responses:
            raise AssertionError(f"unexpected fixture request: {url}")
        return self.responses[url]


def prepared_root(root: Path, *, name: str = "runtime") -> tuple[dict, dict, dict, dict]:
    snapshot = snapshot_for(RISK_ON_RATES, name=name)
    persist_snapshot(root, snapshot)
    verified = MarketRegimeDataStore(root).latest()
    analysis = MarketRegimeAnalysisStore(root).compile_latest()
    intraday_at = datetime(2026, 8, 6, 8, 0, tzinfo=timezone.utc)
    rates = {
        item.key: -0.001 if item.key in {"vix", "gold", "silver"} else 0.001
        for item in INTRADAY_INSTRUMENTS
    }
    live_snapshot = intraday_snapshot(
        intraday_at,
        rates,
        name=f"{name}-intraday",
    )
    persist_intraday(root, live_snapshot)
    verified_intraday = MarketRegimeIntradayDataStore(root).latest()
    MarketRegimeIntradayOverlayStore(root).compile_latest()
    overlay = MarketRegimeIntradayOverlayStore(root).latest()
    return verified, analysis, verified_intraday, overlay


class MarketRegimeRuntimeTest(unittest.TestCase):
    def test_interval_is_restricted_to_four_or_twelve_hours(self) -> None:
        self.assertEqual(configured_interval_hours(4), 4)
        self.assertEqual(configured_interval_hours("12"), 12)
        with self.assertRaisesRegex(MarketRegimeRuntimeError, "4 or 12"):
            configured_interval_hours(6)

    def test_api_bundle_has_nine_charts_three_probes_and_verified_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot, analysis, intraday, overlay = prepared_root(root)
            store = MarketRegimeApiStore(root)
            published = store.publish(snapshot, analysis, intraday, overlay)
            self.assertEqual(store.latest(), published)
            self.assertEqual(len(published["charts"]), 9)
            self.assertEqual(len(published["probes"]), 3)
            self.assertEqual(len(published["intraday"]["assets"]), 14)
            self.assertEqual(published["data_kind"], "fixture")
            self.assertFalse(published["truth_boundary"]["action_eligible"])
            self.assertEqual(
                published["structural"]["analysis_id"],
                published["analysis_id"],
            )
            self.assertEqual(
                published["intraday"]["snapshot_id"],
                published["intraday_snapshot_id"],
            )
            self.assertEqual(published["overlay"]["overlay_id"], published["overlay_id"])
            receipt = published["material_change_receipt"]
            self.assertEqual(receipt["current_overlay_id"], published["overlay_id"])
            self.assertEqual(receipt["threshold_policy"]["enter_score"], 18.0)
            self.assertEqual(receipt["threshold_policy"]["cooldown_seconds"], 1800)
            self.assertEqual(
                receipt["receipt_id"],
                published["material_change_receipt_id"],
            )
            self.assertEqual(
                {row["instrument"]["key"] for row in published["charts"]},
                {"sp500", "nasdaq", "shanghai", "star50", "wti", "gold", "silver", "kospi", "nikkei"},
            )
            pointer = json.loads((root / "api" / "latest.json").read_text())
            artifact = root / pointer["artifact"]["path"]
            artifact.write_bytes(artifact.read_bytes() + b" ")
            with self.assertRaisesRegex(MarketRegimeRuntimeError, "hash mismatch"):
                store.latest()

    def test_api_pointer_path_cannot_escape_runtime_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = prepared_root(root)
            store = MarketRegimeApiStore(root)
            store.publish(*inputs)
            pointer_path = root / "api" / "latest.json"
            pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
            pointer["artifact"]["path"] = "api/artifacts/../../../../outside.json"
            pointer_path.write_text(json.dumps(pointer), encoding="utf-8")
            with self.assertRaisesRegex(MarketRegimeRuntimeError, "escapes runtime root"):
                store.latest()

    def test_api_bundle_rejects_mismatched_analysis_and_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot, analysis, intraday, overlay = prepared_root(root)
            analysis = {**analysis, "source_run_id": "another-run"}
            with self.assertRaisesRegex(MarketRegimeRuntimeError, "identities differ"):
                build_market_regime_api_payload(
                    snapshot,
                    analysis,
                    intraday,
                    overlay,
                )

    def test_api_bundle_rejects_incoherent_overlay_and_intraday_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot, analysis, intraday, overlay = prepared_root(root)
            rates = {item.key: 0.0 for item in INTRADAY_INSTRUMENTS}
            different_intraday = intraday_snapshot(
                datetime(2026, 8, 6, 8, 15, tzinfo=timezone.utc),
                rates,
                name="different-intraday",
            )
            with self.assertRaisesRegex(
                MarketRegimeRuntimeError,
                "overlay and intraday snapshot identities differ",
            ):
                build_market_regime_api_payload(
                    snapshot,
                    analysis,
                    different_intraday,
                    overlay,
                )

    def test_material_receipt_binds_thresholds_contributions_and_cooldown(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _, _, _, overlay = prepared_root(Path(directory))
            receipt = build_material_change_receipt(overlay)
            self.assertEqual(receipt["previous_overlay_id"], overlay["baseline_overlay_id"])
            self.assertEqual(receipt["current_overlay_id"], overlay["overlay_id"])
            self.assertEqual(
                receipt["cooldown"]["pending_relation"],
                overlay["transition"]["pending_relation"],
            )
            self.assertEqual(
                {row["evidence_id"] for row in receipt["contribution_evidence"]},
                {row["evidence_id"] for row in overlay["signal_contributions"]},
            )
            self.assertFalse(receipt["truth_boundary"]["action_eligible"])

    def test_fixed_raw_to_normalized_overlay_api_replay_is_deterministic(self) -> None:
        identities = []
        for _ in range(2):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                daily = snapshot_for(RISK_ON_RATES, name="raw-api")
                persist_snapshot(root, daily)
                structural_snapshot = MarketRegimeDataStore(root).latest()
                analysis = MarketRegimeAnalysisStore(root).compile_latest()

                responses = dict(tencent_fixture_transport().responses)
                for spec in YAHOO_INSTRUMENTS:
                    body = json.loads(YAHOO_VALID_BODY)
                    meta = body["chart"]["result"][0]["meta"]
                    meta["symbol"] = spec.provider_symbol
                    meta["currency"] = spec.currency
                    meta["exchangeTimezoneName"] = spec.exchange_timezone
                    encoded = json.dumps(body, separators=(",", ":")).encode()
                    primary, _ = yahoo_urls(spec)
                    responses[primary] = yahoo_capture(
                        encoded,
                        url=primary,
                    )
                transport = MappingTransport(responses)
                collected = MarketRegimeIntradayDataStore(
                    root,
                    http_get=transport,
                ).refresh(
                    now=RAW_FIXTURE_NOW,
                    run_id="raw-to-api-fixture",
                )
                self.assertEqual(collected["accepted_count"], 14)
                verified_intraday = MarketRegimeIntradayDataStore(root).latest()
                overlay = MarketRegimeIntradayOverlayStore(root).compile_latest()["overlay"]
                bundle = MarketRegimeApiStore(root).publish(
                    structural_snapshot,
                    analysis,
                    verified_intraday,
                    overlay,
                )
                identities.append(
                    (
                        verified_intraday["snapshot_id"],
                        overlay["overlay_id"],
                        bundle["material_change_receipt_id"],
                        bundle["bundle_id"],
                    )
                )
        self.assertEqual(identities[0], identities[1])

    def test_success_cycle_records_next_due_and_verified_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prepared_root(root)
            start = datetime(2026, 8, 6, 8, 0, tzinfo=timezone.utc)
            finish = datetime(2026, 8, 6, 8, 2, tzinfo=timezone.utc)
            health_at = datetime(2026, 8, 6, 8, 3, tzinfo=timezone.utc)
            runtime = MarketRegimeRuntime(
                root,
                interval_hours=4,
                clock=FixedClock(start, finish, health_at),
                data_store_factory=FrozenDataStore,
            )
            result = runtime.cycle()
            self.assertEqual(result["state"], "idle")
            self.assertEqual(result["next_due_at"], "2026-08-06T12:02:00Z")
            self.assertEqual(result["bundle_id"], MarketRegimeApiStore(root).latest()["bundle_id"])
            health = runtime.health()
            self.assertEqual(health["schema_version"], HEALTH_SCHEMA_VERSION)
            self.assertFalse(health["scheduler"]["busy"])
            self.assertEqual(health["latest"]["status"], "available")
            self.assertEqual(
                health["latest"]["layers"]["overlay"]["overlay_id"],
                result["overlay_id"],
            )
            self.assertEqual(
                sum(
                    health["latest"]["layers"]["intraday"]["session_counts"].values()
                ),
                14,
            )

    def test_twelve_hour_cycle_records_twelve_hour_next_due(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prepared_root(root)
            moment = datetime(2026, 8, 6, 8, 0, tzinfo=timezone.utc)
            runtime = MarketRegimeRuntime(
                root,
                interval_hours=12,
                clock=FixedClock(moment, moment),
                data_store_factory=FrozenDataStore,
            )
            self.assertEqual(runtime.cycle()["next_due_at"], "2026-08-06T20:00:00Z")

    def test_refresh_failure_preserves_last_verified_api_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prepared_root(root)
            moment = datetime(2026, 8, 6, 6, 0, tzinfo=timezone.utc)
            success = MarketRegimeRuntime(
                root,
                clock=FixedClock(moment, moment),
                data_store_factory=FrozenDataStore,
            ).cycle()
            pointer_before = (root / "api" / "latest.json").read_bytes()
            bundle_before = MarketRegimeApiStore(root).latest()
            failed = MarketRegimeRuntime(
                root,
                clock=FixedClock(moment, moment),
                data_store_factory=FailedDataStore,
            ).cycle()
            self.assertEqual(success["state"], "idle")
            self.assertEqual(failed["state"], "failed")
            self.assertEqual(failed["last_error"]["message"], "upstream unavailable")
            self.assertEqual((root / "api" / "latest.json").read_bytes(), pointer_before)
            self.assertEqual(MarketRegimeApiStore(root).latest(), bundle_before)

    def test_compile_failure_preserves_last_verified_api_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prepared_root(root)
            moment = datetime(2026, 8, 6, 6, 0, tzinfo=timezone.utc)
            MarketRegimeRuntime(
                root,
                clock=FixedClock(moment, moment),
                data_store_factory=FrozenDataStore,
            ).cycle()
            pointer_before = (root / "api" / "latest.json").read_bytes()
            failed = MarketRegimeRuntime(
                root,
                clock=FixedClock(moment, moment),
                data_store_factory=FrozenDataStore,
                analysis_store_factory=FailedAnalysisStore,
            ).cycle()
            self.assertEqual(failed["state"], "failed")
            self.assertEqual(failed["last_error"]["message"], "compile failed")
            self.assertEqual((root / "api" / "latest.json").read_bytes(), pointer_before)

    def test_overlay_failure_preserves_last_verified_api_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot, analysis, intraday, overlay = prepared_root(root)
            MarketRegimeApiStore(root).publish(snapshot, analysis, intraday, overlay)
            pointer_before = (root / "api" / "latest.json").read_bytes()
            moment = datetime(2026, 8, 6, 8, 15, tzinfo=timezone.utc)
            failed = MarketRegimeRuntime(
                root,
                clock=FixedClock(moment, moment),
                data_store_factory=FrozenDataStore,
                overlay_store_factory=FailedOverlayStore,
            ).cycle()
            self.assertEqual(failed["state"], "failed")
            self.assertEqual(failed["last_error"]["message"], "overlay compile failed")
            self.assertEqual((root / "api" / "latest.json").read_bytes(), pointer_before)

    def test_partial_and_closed_are_honest_publishable_bundles(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot, analysis, _, previous = prepared_root(root)
            rates = {item.key: 0.001 for item in INTRADAY_INSTRUMENTS}
            states = {item.key: "closed" for item in INTRADAY_INSTRUMENTS}
            closed_snapshot = intraday_snapshot(
                datetime(2026, 8, 6, 8, 15, tzinfo=timezone.utc),
                rates,
                states=states,
                name="closed",
            )
            persist_intraday(root, closed_snapshot)
            closed_receipt = MarketRegimeIntradayOverlayStore(root).compile_latest()
            closed_overlay = closed_receipt["overlay"]
            closed_bundle = MarketRegimeApiStore(root).publish(
                snapshot,
                analysis,
                closed_snapshot,
                closed_overlay,
            )
            self.assertEqual(closed_bundle["overlay"]["relation"], "closed")

            partial_snapshot = intraday_snapshot(
                datetime(2026, 8, 6, 8, 30, tzinfo=timezone.utc),
                rates,
                name="partial",
            )
            shanghai = next(
                row
                for row in partial_snapshot["instruments"]
                if row["instrument"]["key"] == "shanghai"
            )
            shanghai["refresh_status"] = "rejected"
            shanghai["freshness"] = "unavailable"
            shanghai["refresh_failure"] = {
                "reason": "fixture upstream failure",
                "source_attempts": [],
            }
            partial_snapshot["quality"] = "partial"
            partial_snapshot["accepted_count"] = 13
            partial_snapshot["rejected_count"] = 1
            resign_snapshot(partial_snapshot)
            persist_intraday(root, partial_snapshot)
            partial_overlay = MarketRegimeIntradayOverlayStore(root).compile_latest()["overlay"]
            partial_bundle = MarketRegimeApiStore(root).publish(
                snapshot,
                analysis,
                partial_snapshot,
                partial_overlay,
            )
            self.assertEqual(partial_bundle["intraday"]["quality"], "partial")
            self.assertEqual(partial_bundle["overlay"]["relation"], "insufficient")
            self.assertNotEqual(partial_bundle["bundle_id"], closed_bundle["bundle_id"])
            self.assertEqual(
                partial_bundle["material_change_receipt"]["previous_overlay_id"],
                closed_overlay["overlay_id"],
            )

    def test_publish_failure_or_incoherent_input_leaves_latest_pointer_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot, analysis, intraday, overlay = prepared_root(root)
            store = MarketRegimeApiStore(root)
            store.publish(snapshot, analysis, intraday, overlay)
            pointer = root / "api" / "latest.json"
            before = pointer.read_bytes()
            bad_overlay = json.loads(json.dumps(overlay))
            bad_overlay["intraday"]["snapshot_id"] = "market-regime-intraday-snapshot:" + "0" * 64
            with self.assertRaises(MarketRegimeRuntimeError):
                store.publish(snapshot, analysis, intraday, bad_overlay)
            self.assertEqual(pointer.read_bytes(), before)
            with patch(
                "market_regime_runtime._write_atomic",
                side_effect=OSError("pointer write failed"),
            ):
                with self.assertRaisesRegex(OSError, "pointer write failed"):
                    store.publish(snapshot, analysis, intraday, overlay)
            self.assertEqual(pointer.read_bytes(), before)

    def test_health_age_grows_without_mutating_bundle_or_source_times(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = prepared_root(root)
            MarketRegimeApiStore(root).publish(*inputs)
            pointer = (root / "api" / "latest.json").read_bytes()
            first_at = datetime(2026, 8, 6, 8, 10, tzinfo=timezone.utc)
            second_at = first_at + timedelta(minutes=1)
            runtime = MarketRegimeRuntime(root, clock=FixedClock(first_at, second_at))
            first = runtime.health()
            second = runtime.health()
            first_age = first["latest"]["layers"]["overlay"]["age_seconds"]
            second_age = second["latest"]["layers"]["overlay"]["age_seconds"]
            self.assertEqual(second_age - first_age, 60)
            self.assertEqual((root / "api" / "latest.json").read_bytes(), pointer)
            self.assertEqual(
                first["latest"]["layers"]["intraday"]["last_success_at"],
                second["latest"]["layers"]["intraday"]["last_success_at"],
            )

    def test_lock_contention_returns_busy_without_replacing_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = MarketRegimeRuntime(root)
            descriptor = first._try_lock()
            self.assertIsNotNone(descriptor)
            try:
                result = MarketRegimeRuntime(root).cycle()
                self.assertEqual(result["state"], "busy")
                self.assertFalse((root / "scheduler" / "status.json").exists())
            finally:
                first._unlock(descriptor)

    def test_http_routes_read_bundle_without_refresh_or_compile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = prepared_root(root)
            expected = MarketRegimeApiStore(root).publish(*inputs)
            with patch.dict(os.environ, {"PARK_MARKET_REGIME_ROOT": str(root)}):
                from http.server import ThreadingHTTPServer
                from server import DashboardHandler

                server = ThreadingHTTPServer(("127.0.0.1", 0), DashboardHandler)
                thread = Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    with patch.object(
                        MarketRegimeDataStore,
                        "refresh",
                        side_effect=AssertionError("HTTP must not refresh"),
                    ), patch.object(
                        MarketRegimeAnalysisStore,
                        "compile_latest",
                        side_effect=AssertionError("HTTP must not compile"),
                    ), patch.object(
                        MarketRegimeIntradayDataStore,
                        "refresh",
                        side_effect=AssertionError("HTTP must not refresh intraday"),
                    ), patch.object(
                        MarketRegimeIntradayOverlayStore,
                        "compile_latest",
                        side_effect=AssertionError("HTTP must not compile overlay"),
                    ):
                        connection = http.client.HTTPConnection(*server.server_address, timeout=2)
                        connection.request("GET", "/api/market-regime")
                        response = connection.getresponse()
                        payload = json.loads(response.read())
                        connection.close()
                        self.assertEqual(response.status, 200)
                        self.assertEqual(payload["bundle_id"], expected["bundle_id"])
                        self.assertEqual(
                            payload["overlay_id"],
                            expected["overlay_id"],
                        )

                        connection = http.client.HTTPConnection(*server.server_address, timeout=2)
                        connection.request("GET", "/api/market-regime/health")
                        health_response = connection.getresponse()
                        health = json.loads(health_response.read())
                        connection.close()
                        self.assertEqual(health_response.status, 200)
                        self.assertEqual(health["latest"]["status"], "available")
                        self.assertEqual(
                            health["latest"]["layers"]["intraday"]["snapshot_id"],
                            expected["intraday_snapshot_id"],
                        )
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
