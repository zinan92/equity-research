from __future__ import annotations

import fcntl
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from functools import partial
from pathlib import Path


PRODUCT = Path(__file__).resolve().parents[1]
TESTS = Path(__file__).resolve().parent
for path in (PRODUCT, TESTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from data_core import (  # noqa: E402
    CanonicalResearchRefresh,
    DataFoundation,
    RefreshInProgressError,
    SnapshotOrchestrator,
    build_refresh_plan,
    snapshot_audit,
)
from data_core.contracts import canonical_json, digest  # noqa: E402
from data_core.research_refresh import _default_research_builder  # noqa: E402
from test_research_refresh_v1 import (  # noqa: E402
    DAY_ONE,
    DAY_TWO,
    SHANGHAI,
    UNIVERSE,
    StaticAdapter,
    market_payload,
)


PREVIOUS_DAY = "2026-07-16"


def failing_research_builder(_reader, _ticker: str) -> dict:
    raise RuntimeError("injected report failure")


def backfill_payload() -> dict:
    payload = market_payload()
    exchanges = sorted({row["exchange"] for row in payload["instruments"]})
    payload["calendar"].extend(
        {
            "exchange": exchange,
            "trade_date": PREVIOUS_DAY,
            "is_open": 1,
            "previous_open_date": "2026-07-15",
        }
        for exchange in exchanges
    )
    payload["statuses"].extend(
        {**row, "trade_date": PREVIOUS_DAY} for row in list(payload["statuses"])
    )
    return payload


class SnapshotOrchestrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.foundation = DataFoundation(self.root / "canonical.db")
        self.state_root = self.root / "refresh"
        self.now_one = datetime(2026, 7, 17, 17, 30, tzinfo=SHANGHAI)
        self.now_two = datetime(2026, 7, 20, 17, 30, tzinfo=SHANGHAI)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def orchestrator(self, adapter: StaticAdapter, builder=None) -> SnapshotOrchestrator:
        refresh = CanonicalResearchRefresh(
            self.foundation,
            self.state_root,
            [adapter],
            universe=UNIVERSE,
            research_builder=builder or partial(_default_research_builder, minimum_bars=2),
        )
        return SnapshotOrchestrator(refresh)

    def test_scheduler_detects_backfill_and_closes_every_gap(self) -> None:
        plan = build_refresh_plan(
            self.foundation,
            universe=UNIVERSE,
            expected_trade_dates=(PREVIOUS_DAY, DAY_ONE),
            now=self.now_one,
        )
        self.assertTrue(plan.due)
        self.assertEqual(plan.mode, "backfill")
        self.assertEqual(plan.backfill_dates, (PREVIOUS_DAY, DAY_ONE))

        result = self.orchestrator(
            StaticAdapter(backfill_payload(), name="primary_backfill", role="primary")
        ).run(expected_trade_dates=(PREVIOUS_DAY, DAY_ONE), now=self.now_one)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["remaining_gaps"], [])
        self.assertEqual(result["plan"]["mode"], "backfill")
        states = {row["name"]: row["state"] for row in result["cadence"]["lanes"]}
        self.assertEqual(states["fast"], "fresh")
        self.assertEqual(states["slow"], "missing")
        self.assertEqual(states["periodic"], "missing")

    def test_receipt_binds_ingestion_quality_raw_hashes_and_replay(self) -> None:
        result = self.orchestrator(
            StaticAdapter(backfill_payload(), name="primary_receipt", role="primary")
        ).run(expected_trade_dates=(PREVIOUS_DAY, DAY_ONE), now=self.now_one)

        self.assertTrue(result["ingestion_runs"])
        self.assertTrue(all(item["raw_hash"] for item in result["ingestion_runs"]))
        self.assertEqual(result["quality_result"]["blockers"], [])
        self.assertTrue(result["quality_result"]["results"])
        self.assertEqual(result["snapshot"]["replay_status"], "passed")
        self.assertTrue(result["snapshot"]["raw_hashes"])
        self.assertEqual(
            result["snapshot"]["raw_hash_digest"],
            digest(result["snapshot"]["raw_hashes"]),
        )
        saved = json.loads(
            (self.state_root / "runs" / result["run_id"] / "orchestration.json").read_text()
        )
        unsigned = {key: value for key, value in saved.items() if key != "receipt_hash"}
        self.assertEqual(saved["receipt_hash"], digest(unsigned))

    def test_scheduler_skip_and_forced_repeat_are_idempotent(self) -> None:
        adapter = StaticAdapter(backfill_payload(), name="primary_idempotent", role="primary")
        orchestrator = self.orchestrator(adapter)
        first = orchestrator.run(
            expected_trade_dates=(PREVIOUS_DAY, DAY_ONE), now=self.now_one
        )
        skipped = orchestrator.run(
            expected_trade_dates=(PREVIOUS_DAY, DAY_ONE),
            now=self.now_one + timedelta(minutes=1),
        )
        self.assertEqual(skipped["status"], "skipped")
        self.assertFalse(skipped["network_called"])
        persisted_skip = json.loads(
            (self.state_root / "orchestration-latest.json").read_text()
        )
        self.assertEqual(persisted_skip["check_id"], skipped["check_id"])
        self.assertEqual(persisted_skip["receipt_hash"], skipped["receipt_hash"])
        repeated = orchestrator.run(
            expected_trade_dates=(PREVIOUS_DAY, DAY_ONE),
            now=self.now_one + timedelta(minutes=2),
            force=True,
        )
        self.assertEqual(repeated["status"], "success")
        self.assertEqual(repeated["snapshot"]["snapshot_id"], first["snapshot"]["snapshot_id"])
        self.assertEqual(repeated["snapshot"]["manifest_hash"], first["snapshot"]["manifest_hash"])

    def test_concurrent_trigger_is_rejected_by_canonical_lock(self) -> None:
        orchestrator = self.orchestrator(
            StaticAdapter(backfill_payload(), name="primary_lock", role="primary")
        )
        self.state_root.mkdir(parents=True)
        with (self.state_root / "refresh.lock").open("a+") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(RefreshInProgressError, "already"):
                orchestrator.run(
                    expected_trade_dates=(PREVIOUS_DAY, DAY_ONE), now=self.now_one
                )

    def test_source_failure_preserves_previous_valid_version(self) -> None:
        first = self.orchestrator(
            StaticAdapter(backfill_payload(), name="primary_good", role="primary")
        ).run(expected_trade_dates=(PREVIOUS_DAY, DAY_ONE), now=self.now_one)
        failed = self.orchestrator(
            StaticAdapter(None, name="primary_failed", role="primary", error="injected outage")
        ).run(
            expected_trade_dates=(PREVIOUS_DAY, DAY_ONE, DAY_TWO), now=self.now_two
        )

        self.assertEqual(failed["status"], "failed")
        self.assertEqual(
            failed["active_preserved"]["snapshot_id"], first["snapshot"]["snapshot_id"]
        )
        active = json.loads((self.state_root / "active.json").read_text())
        self.assertEqual(active["snapshot_id"], first["snapshot"]["snapshot_id"])
        self.assertTrue(failed["remaining_gaps"])
        self.assertIsNotNone(
            next(row for row in failed["cadence"]["lanes"] if row["name"] == "fast")["last_good_at"]
        )

    def test_later_stage_failure_is_isolated_and_records_preserved_active(self) -> None:
        first = self.orchestrator(
            StaticAdapter(backfill_payload(), name="primary_first", role="primary")
        ).run(expected_trade_dates=(PREVIOUS_DAY, DAY_ONE), now=self.now_one)
        failed = self.orchestrator(
            StaticAdapter(market_payload(DAY_TWO), name="primary_next", role="primary"),
            builder=failing_research_builder,
        ).run(expected_trade_dates=(PREVIOUS_DAY, DAY_ONE, DAY_TWO), now=self.now_two)

        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["canonical_status"], "partial")
        self.assertEqual(failed["canonical_stage"], "blocked_before_activation")
        self.assertIn("0/8 artifacts passed", failed["error"])
        self.assertEqual(
            failed["active_preserved"]["snapshot_id"], first["snapshot"]["snapshot_id"]
        )
        self.assertEqual(failed["snapshot"]["replay_status"], "passed")

    def test_replay_rejects_raw_membership_tampering(self) -> None:
        result = self.orchestrator(
            StaticAdapter(backfill_payload(), name="primary_tamper", role="primary")
        ).run(expected_trade_dates=(PREVIOUS_DAY, DAY_ONE), now=self.now_one)
        snapshot_id = result["snapshot"]["snapshot_id"]
        with self.foundation.connect() as connection:
            connection.execute("DROP TRIGGER core_snapshots_no_update")
            row = connection.execute(
                "SELECT manifest_json FROM core_snapshot_manifests WHERE snapshot_id=?",
                (snapshot_id,),
            ).fetchone()
            manifest = json.loads(row["manifest_json"])
            manifest["raw_hashes"] = manifest["raw_hashes"][:-1]
            manifest["raw_hash_digest"] = digest(manifest["raw_hashes"])
            connection.execute(
                "UPDATE core_snapshot_manifests SET manifest_json=?, manifest_hash=? "
                "WHERE snapshot_id=?",
                (canonical_json(manifest), digest(manifest), snapshot_id),
            )
            connection.commit()

        with self.assertRaisesRegex(RuntimeError, "raw hash membership"):
            snapshot_audit(self.foundation, snapshot_id)


if __name__ == "__main__":
    unittest.main()
