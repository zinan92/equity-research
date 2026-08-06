from __future__ import annotations

from datetime import datetime, timezone
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
from data_core.market_regime_model import MarketRegimeAnalysisStore  # noqa: E402
from market_regime_runtime import (  # noqa: E402
    MarketRegimeApiStore,
    MarketRegimeRuntime,
    MarketRegimeRuntimeError,
    build_market_regime_api_payload,
    configured_interval_hours,
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


class FixedClock:
    def __init__(self, *values: datetime) -> None:
        self.values = list(values)

    def __call__(self) -> datetime:
        if not self.values:
            raise AssertionError("clock called too many times")
        return self.values.pop(0)


def prepared_root(root: Path, *, name: str = "runtime") -> tuple[dict, dict]:
    snapshot = snapshot_for(RISK_ON_RATES, name=name)
    persist_snapshot(root, snapshot)
    verified = MarketRegimeDataStore(root).latest()
    analysis = MarketRegimeAnalysisStore(root).compile_latest()
    return verified, analysis


class MarketRegimeRuntimeTest(unittest.TestCase):
    def test_interval_is_restricted_to_four_or_twelve_hours(self) -> None:
        self.assertEqual(configured_interval_hours(4), 4)
        self.assertEqual(configured_interval_hours("12"), 12)
        with self.assertRaisesRegex(MarketRegimeRuntimeError, "4 or 12"):
            configured_interval_hours(6)

    def test_api_bundle_has_nine_charts_three_probes_and_verified_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot, analysis = prepared_root(root)
            store = MarketRegimeApiStore(root)
            published = store.publish(snapshot, analysis)
            self.assertEqual(store.latest(), published)
            self.assertEqual(len(published["charts"]), 9)
            self.assertEqual(len(published["probes"]), 3)
            self.assertEqual(published["data_kind"], "fixture")
            self.assertFalse(published["truth_boundary"]["action_eligible"])
            self.assertEqual(
                {row["instrument"]["key"] for row in published["charts"]},
                {"sp500", "nasdaq", "shanghai", "star50", "wti", "gold", "silver", "kospi", "nikkei"},
            )
            pointer = json.loads((root / "api" / "latest.json").read_text())
            artifact = root / pointer["artifact"]["path"]
            artifact.write_bytes(artifact.read_bytes() + b" ")
            with self.assertRaisesRegex(MarketRegimeRuntimeError, "hash mismatch"):
                store.latest()

    def test_api_bundle_rejects_mismatched_analysis_and_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot, analysis = prepared_root(root)
            analysis = {**analysis, "source_run_id": "another-run"}
            with self.assertRaisesRegex(MarketRegimeRuntimeError, "identities differ"):
                build_market_regime_api_payload(snapshot, analysis)

    def test_success_cycle_records_next_due_and_verified_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prepared_root(root)
            start = datetime(2026, 8, 6, 6, 0, tzinfo=timezone.utc)
            finish = datetime(2026, 8, 6, 6, 2, tzinfo=timezone.utc)
            runtime = MarketRegimeRuntime(
                root,
                interval_hours=4,
                clock=FixedClock(start, finish),
                data_store_factory=FrozenDataStore,
            )
            result = runtime.cycle()
            self.assertEqual(result["state"], "idle")
            self.assertEqual(result["next_due_at"], "2026-08-06T10:02:00Z")
            self.assertEqual(result["bundle_id"], MarketRegimeApiStore(root).latest()["bundle_id"])
            health = runtime.health()
            self.assertFalse(health["scheduler"]["busy"])
            self.assertEqual(health["latest"]["status"], "available")

    def test_twelve_hour_cycle_records_twelve_hour_next_due(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prepared_root(root)
            moment = datetime(2026, 8, 6, 6, 0, tzinfo=timezone.utc)
            runtime = MarketRegimeRuntime(
                root,
                interval_hours=12,
                clock=FixedClock(moment, moment),
                data_store_factory=FrozenDataStore,
            )
            self.assertEqual(runtime.cycle()["next_due_at"], "2026-08-06T18:00:00Z")

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
            snapshot, analysis = prepared_root(root)
            expected = MarketRegimeApiStore(root).publish(snapshot, analysis)
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
                    ):
                        connection = http.client.HTTPConnection(*server.server_address, timeout=2)
                        connection.request("GET", "/api/market-regime")
                        response = connection.getresponse()
                        payload = json.loads(response.read())
                        connection.close()
                        self.assertEqual(response.status, 200)
                        self.assertEqual(payload["bundle_id"], expected["bundle_id"])

                        connection = http.client.HTTPConnection(*server.server_address, timeout=2)
                        connection.request("GET", "/api/market-regime/health")
                        health_response = connection.getresponse()
                        health = json.loads(health_response.read())
                        connection.close()
                        self.assertEqual(health_response.status, 200)
                        self.assertEqual(health["latest"]["status"], "available")
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
