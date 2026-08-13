from __future__ import annotations

import json
import fcntl
from hashlib import sha256
import os
from pathlib import Path
import tempfile
from threading import Thread
import unittest
from unittest.mock import patch
import sys
from urllib.request import urlopen


PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT))

from data_core.market_regime_daily_bundle import (  # noqa: E402
    MarketRegimeDailyBundleError,
    MarketRegimeDailyBundleRace,
    MarketRegimeDailyBundleStore,
)
from data_core.market_regime_daily_evidence import MarketRegimeDailyEvidenceStore  # noqa: E402
from data_core.market_regime_daily_narrative import MarketRegimeDailyNarrativeStore  # noqa: E402
from market_regime_daily_runtime import MarketRegimeDailyRuntime  # noqa: E402
from product.tests.test_market_regime_daily_evidence import fixture_inputs  # noqa: E402
from product.tests.test_market_regime_daily_narrative import FakeProvider, valid_output  # noqa: E402


def stores(root: Path) -> tuple[MarketRegimeDailyEvidenceStore, MarketRegimeDailyNarrativeStore, MarketRegimeDailyBundleStore]:
    macro_root = root / "macro"
    macro_root.mkdir(parents=True, exist_ok=True)
    fixture_inputs(root, macro_root)
    evidence = MarketRegimeDailyEvidenceStore(root, macro_root, root / "daily-v2" / "evidence-packs")
    evidence.compile_latest()
    narrative = MarketRegimeDailyNarrativeStore(evidence, root / "daily-v2" / "narratives")
    narrative.compile_latest(None)
    bundle = MarketRegimeDailyBundleStore(evidence, narrative, root / "daily-v2" / "bundles")
    return evidence, narrative, bundle


class MarketRegimeDailyBundleTest(unittest.TestCase):
    def test_fallback_publishes_and_same_candidate_becomes_check(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _, _, bundle = stores(Path(directory))
            first = bundle.publish_candidate(bundle.capture_candidate())
            self.assertEqual(first["action"], "published")
            first_state = bundle.latest_state()
            second = bundle.publish_candidate(bundle.capture_candidate())
            self.assertEqual(second["action"], "checked")
            self.assertEqual(second["state"]["served"], first_state["served"])
            self.assertIsNotNone(second["state"]["latest_check_receipt"])
            self.assertEqual(bundle.latest()["bundle_id"], first["artifact"]["bundle_id"])

    def test_receipt_only_narrative_rerun_does_not_create_new_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, narrative, bundle = stores(root)
            first = bundle.publish_candidate(bundle.capture_candidate())
            # S4 writes a new completion receipt/run id while its immutable
            # fallback artifact remains byte-identical for the same pack.
            narrative.compile_latest(None)
            second = bundle.publish_candidate(bundle.capture_candidate())
            self.assertEqual(second["action"], "checked")
            self.assertEqual(second["artifact"]["bundle_id"], first["artifact"]["bundle_id"])
            state = bundle.latest_state()
            check = json.loads((root / "daily-v2" / "bundles" / state["latest_check_receipt"]["path"]).read_text())
            self.assertEqual(check["event"], "check")

    def test_same_pack_fallback_upgrades_to_model_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence, narrative, bundle = stores(root)
            fallback = bundle.publish_candidate(bundle.capture_candidate())
            pack = evidence.latest()
            model = narrative.compile_latest(FakeProvider(valid_output(pack)))
            self.assertEqual(model["generation_status"], "model_generated_unreviewed")
            upgraded = bundle.publish_candidate(bundle.capture_candidate())
            self.assertEqual(upgraded["action"], "published")
            self.assertNotEqual(upgraded["artifact"]["bundle_id"], fallback["artifact"]["bundle_id"])
            self.assertEqual(upgraded["artifact"]["generation_status"], "model_generated_unreviewed")

    def test_candidate_advance_does_not_replace_served_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _, _, bundle = stores(Path(directory))
            published = bundle.publish_candidate(bundle.capture_candidate())
            old_state_bytes = bundle.state_path.read_bytes()
            stale = bundle.capture_candidate()
            changed = json.loads(json.dumps(stale))
            changed["publication_identity"]["generation_status"] = "model_generated_unreviewed"
            with patch.object(bundle, "capture_candidate", return_value=changed):
                with self.assertRaises(MarketRegimeDailyBundleRace):
                    bundle.publish_candidate(stale)
            self.assertEqual(bundle.state_path.read_bytes(), old_state_bytes)
            self.assertEqual(bundle.latest()["bundle_id"], published["artifact"]["bundle_id"])

    def test_s5_only_projection_rebind_fails_against_source_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, _, bundle = stores(root)
            published = bundle.publish_candidate(bundle.capture_candidate())
            state = bundle.latest_state()
            artifact_ref = state["served"]["artifact"]
            artifact_path = root / "daily-v2" / "bundles" / artifact_ref["path"]
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
            artifact["evidence"]["quality"] = "tampered"
            identity = artifact["publication_identity"]
            identity["projection_hashes"] = bundle._projection_hashes(artifact)
            digest = sha256(
                json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            artifact["bundle_id"] = f"market-regime-daily-bundle:{digest}"
            artifact_path = root / "daily-v2" / "bundles" / "artifacts" / f"{digest}.json"
            artifact_path.parent.mkdir(parents=True, exist_ok=True)
            encoded = (json.dumps(artifact, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
            artifact_path.write_bytes(encoded)
            completion = json.loads(
                (root / "daily-v2" / "bundles" / state["served"]["completion_receipt"]["path"]).read_text()
            )
            completion["bundle_id"] = artifact["bundle_id"]
            completion["publication_identity"] = identity
            completion_path = root / "daily-v2" / "bundles" / "receipts" / "completion-rebound.json"
            completion_path.parent.mkdir(parents=True, exist_ok=True)
            completion_encoded = (json.dumps(completion, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
            completion_path.write_bytes(completion_encoded)
            rebound = {
                "schema_version": state["schema_version"],
                "served": {
                    "bundle_id": artifact["bundle_id"],
                    "artifact": {"path": f"artifacts/{digest}.json", "sha256": sha256(encoded).hexdigest()},
                    "completion_receipt": {"path": "receipts/completion-rebound.json", "sha256": sha256(completion_encoded).hexdigest()},
                },
                "latest_check_receipt": None,
            }
            (root / "daily-v2" / "bundles" / "state.json").write_text(
                json.dumps(rebound, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(MarketRegimeDailyBundleError, "source projection"):
                bundle.latest()

    def test_corrupt_state_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _, _, bundle = stores(Path(directory))
            bundle.publish_candidate(bundle.capture_candidate())
            bundle.state_path.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(MarketRegimeDailyBundleError, "state schema"):
                bundle.latest()

    def test_corrupt_completion_and_check_receipts_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, _, bundle = stores(root)
            first = bundle.publish_candidate(bundle.capture_candidate())
            completion_path = root / "daily-v2" / "bundles" / first["state"]["served"]["completion_receipt"]["path"]
            completion_path.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(MarketRegimeDailyBundleError, "hash mismatch"):
                bundle.latest()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, _, bundle = stores(root)
            first = bundle.publish_candidate(bundle.capture_candidate())
            bundle.publish_candidate(bundle.capture_candidate())
            check_path = root / "daily-v2" / "bundles" / bundle.latest_state()["latest_check_receipt"]["path"]
            check_path.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(MarketRegimeDailyBundleError, "hash mismatch"):
                bundle.latest()

    def test_state_readback_failure_restores_exact_last_good_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence, narrative, bundle = stores(root)
            bundle.publish_candidate(bundle.capture_candidate())
            old_state = bundle.state_path.read_bytes()
            narrative.compile_latest(FakeProvider(valid_output(evidence.latest())))
            candidate = bundle.capture_candidate()
            original_read = bundle._read_state
            calls = 0

            def fail_on_readback(*, validate_provenance: bool = True):
                nonlocal calls
                calls += 1
                if calls >= 2:
                    raise MarketRegimeDailyBundleError("injected final validation crash")
                return original_read(validate_provenance=validate_provenance)

            with patch.object(bundle, "_read_state", side_effect=fail_on_readback):
                with self.assertRaisesRegex(MarketRegimeDailyBundleError, "injected final validation"):
                    bundle.publish_candidate(candidate)
            self.assertEqual(bundle.state_path.read_bytes(), old_state)

    def test_stale_check_becomes_candidate_advanced_orphan_after_publish(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence, narrative, bundle = stores(root)
            first = bundle.publish_candidate(bundle.capture_candidate())
            stale = bundle.capture_candidate()
            narrative.compile_latest(FakeProvider(valid_output(evidence.latest())))
            second = bundle.publish_candidate(bundle.capture_candidate())
            self.assertNotEqual(first["artifact"]["bundle_id"], second["artifact"]["bundle_id"])
            with self.assertRaises(MarketRegimeDailyBundleRace):
                bundle.publish_candidate(stale)
            self.assertEqual(bundle.latest()["bundle_id"], second["artifact"]["bundle_id"])

    def test_runtime_health_uses_served_state_and_fixed_failure_shape(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            macro = root / "macro"
            macro.mkdir()
            fixture_inputs(root, macro)
            runtime = MarketRegimeDailyRuntime(root, provider_factory=lambda: None)
            result = runtime.cycle()
            self.assertEqual(result["state"], "idle")
            health = runtime.health()
            self.assertEqual(health["served"]["bundle_id"], result["served_bundle_id"])
            self.assertEqual(health["served"]["generation_status"], "deterministic_fallback")
            self.assertNotIn("/", json.dumps(health["failure"] or {}))

    def test_daily_routes_are_read_only_same_origin_and_no_store(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            macro = root / "macro"
            macro.mkdir()
            fixture_inputs(root, macro)
            runtime = MarketRegimeDailyRuntime(root, provider_factory=lambda: None)
            runtime.cycle()
            before = (root / "daily-v2" / "bundles" / "state.json").read_bytes()
            with patch.dict(os.environ, {"PARK_MARKET_REGIME_ROOT": str(root)}):
                from http.server import ThreadingHTTPServer
                from server import DashboardHandler

                server = ThreadingHTTPServer(("127.0.0.1", 0), DashboardHandler)
                thread = Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    with urlopen(f"http://127.0.0.1:{server.server_port}/api/market-regime/daily") as response:
                        payload = json.loads(response.read())
                        self.assertEqual(response.status, 200)
                        self.assertEqual(response.headers["Cache-Control"], "no-store")
                    with urlopen(f"http://127.0.0.1:{server.server_port}/api/market-regime/daily/health") as response:
                        health = json.loads(response.read())
                        self.assertEqual(response.status, 200)
                        self.assertEqual(response.headers["Cache-Control"], "no-store")
                finally:
                    server.shutdown()
                    thread.join(timeout=2)
                    server.server_close()
            self.assertEqual(payload["schema_version"], "market-regime-daily-bundle-v1")
            self.assertEqual(health["served"]["bundle_id"], payload["bundle_id"])
            self.assertEqual((root / "daily-v2" / "bundles" / "state.json").read_bytes(), before)

    def test_health_has_age_and_empty_health_get_has_no_filesystem_side_effect(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = MarketRegimeDailyRuntime(root, provider_factory=lambda: None)
            before = sorted(str(path.relative_to(root)) for path in root.rglob("*"))
            unavailable = runtime.health()
            after = sorted(str(path.relative_to(root)) for path in root.rglob("*"))
            self.assertEqual(unavailable["served"], {"status": "unavailable"})
            self.assertEqual(before, after)

            macro = root / "macro"
            macro.mkdir()
            fixture_inputs(root, macro)
            result = runtime.cycle()
            self.assertEqual(result["state"], "idle")
            health = runtime.health()
            self.assertIsInstance(health["served"]["age_seconds"], int)

    def test_health_does_not_echo_tampered_failure_detail_or_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = MarketRegimeDailyRuntime(root)
            status = runtime._base_status({}, attempt_id="attempt-safe", now="2026-08-06T23:00:00Z")
            status.update(
                {
                    "state": "failed",
                    "last_failure": {
                        "at": "2026-08-06T23:00:00Z",
                        "code": "bundle_publish_failed",
                        "phase": "bundle",
                        "detail": "sk-live-secret",
                        "path": "/Users/wendy/.env",
                    }
                }
            )
            runtime.status_path.parent.mkdir(parents=True)
            runtime.status_path.write_text(json.dumps(status), encoding="utf-8")
            health = runtime.health()
            self.assertIsNone(health["failure"])
            self.assertNotIn("sk-live", json.dumps(health))
            self.assertNotIn(".env", json.dumps(health))

    def test_standalone_daily_respects_cohesive_pipeline_lock(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "scheduler" / "pipeline.lock"
            path.parent.mkdir(parents=True)
            descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            try:
                result = MarketRegimeDailyRuntime(root).cycle()
                self.assertEqual(result["state"], "busy")
                self.assertEqual(result["contention"], "cohesive_pipeline")
            finally:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
                os.close(descriptor)


if __name__ == "__main__":
    unittest.main()
