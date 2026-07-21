from __future__ import annotations

import copy
import json
import re
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


PRODUCT = Path(__file__).resolve().parents[1]
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from data_core import DataFoundation, QualityGateError, SnapshotReader, SourceManifest  # noqa: E402
from data_core.fixtures import AS_OF, KNOWN_AT, fixture_payload  # noqa: E402


MANIFEST = SourceManifest(
    source_key="acceptance_fixture_v1",
    domain_scope="market",
    authority_tier="canonical",
    provider_version="fixture-1",
    schema_version="fixture-1",
    license_status="internal_test_only",
    source_url="fixture://data-foundation-v1",
    quality_flags=("fixture", "not_real_time"),
)


class DataFoundationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "foundation.db"
        self.foundation = DataFoundation(self.db_path)
        self.payload = fixture_payload()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def ingest(self, payload=None):
        return self.foundation.ingest_fixture(payload or self.payload, MANIFEST)

    def test_schema_and_postgres_contract_cover_canonical_domains(self) -> None:
        self.foundation.initialize()
        with self.foundation.connect() as connection:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        required = {
            "core_instruments", "core_trading_calendar", "core_corporate_actions",
            "core_adjustment_factors", "core_daily_bars", "core_financial_facts",
            "core_intelligence_items", "core_ingestion_runs", "core_raw_objects",
            "core_quality_results", "core_snapshot_manifests",
        }
        self.assertTrue(required.issubset(tables))
        postgres = (PRODUCT / "data_core/migrations/0001_canonical_foundation.postgres.sql").read_text()
        logical_contract = {
            ("core_source_manifest_versions", "market.source_manifest_versions"): {
                "manifest_hash", "source_key", "provider_version", "schema_version", "license_status", "source_url",
            },
            ("core_ingestion_runs", "market.ingestion_runs"): {
                "run_id", "source_manifest_hash", "data_kind", "idempotency_key", "attempt", "status",
            },
            ("core_raw_objects", "market.raw_objects"): {
                "raw_hash", "run_id", "source_manifest_hash", "known_at", "payload_size",
            },
            ("core_source_observations", "market.source_observations"): {
                "observation_id", "run_id", "entity_type", "entity_key", "canonical_hash", "raw_hash",
            },
            ("core_daily_bars", "market.daily_bars"): {
                "instrument_id", "trade_date", "adjustment_version", "known_at", "quality_status",
            },
            ("core_financial_facts", "market.financial_facts"): {
                "fact_id", "report_date", "announced_at", "revision", "known_at", "quality_status",
            },
            ("core_quality_results", "market.quality_results"): {
                "quality_id", "evaluation_id", "run_id", "status", "detail",
            },
            ("core_snapshot_manifests", "research.dataset_snapshots"): {
                "snapshot_id", "snapshot_kind", "known_at", "quality_evaluation_id", "quality_digest", "manifest_hash",
            },
            ("core_snapshot_items", "research.dataset_snapshot_items"): {
                "snapshot_id", "table_name", "row_key", "row_hash", "row_json",
            },
        }
        with self.foundation.connect() as connection:
            for (sqlite_table, postgres_table), fields in logical_contract.items():
                sqlite_fields = {row["name"] for row in connection.execute(f"PRAGMA table_info({sqlite_table})")}
                self.assertTrue(fields.issubset(sqlite_fields), (sqlite_table, fields - sqlite_fields))
                match = re.search(
                    rf"create table if not exists {re.escape(postgres_table)} \((.*?)\n\);",
                    postgres,
                    re.DOTALL | re.IGNORECASE,
                )
                self.assertIsNotNone(match, postgres_table)
                postgres_fields = {
                    line.strip().split()[0].strip(",")
                    for line in match.group(1).splitlines()
                    if line.strip() and not line.lstrip().lower().startswith(("primary ", "foreign ", "unique ", "check "))
                }
                translated = {"payload_size" if field == "payload_json" else field for field in fields}
                self.assertTrue(translated.issubset(postgres_fields), (postgres_table, translated - postgres_fields))

    def test_fixture_covers_12_stocks_and_market_edge_cases(self) -> None:
        self.ingest()
        report = self.foundation.coverage_report()
        self.assertEqual(report["instrument_count"], 12)
        self.assertEqual({row["exchange"] for row in report["segments"]}, {"SSE", "SZSE", "BSE"})
        boards = {row["board"] for row in report["segments"]}
        self.assertTrue({"MAIN", "CHINEXT", "STAR", "BSE"}.issubset(boards))
        self.assertEqual(report["edge_cases"], {"suspended": 1, "corporate_action": 1, "financial_revision": 1})
        self.assertTrue(report["fixture_only"])

    def test_ingestion_is_idempotent_and_preserves_provenance(self) -> None:
        first = self.ingest()
        second = self.ingest()
        self.assertFalse(first["reused"])
        self.assertTrue(second["reused"])
        self.assertEqual(first["run_id"], second["run_id"])
        with self.foundation.connect() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM core_ingestion_runs").fetchone()[0], 1)
            row = connection.execute("SELECT * FROM core_raw_objects").fetchone()
            self.assertEqual(row["provider_version"], MANIFEST.provider_version)
            self.assertEqual(row["license_status"], MANIFEST.license_status)

    def test_conflicting_second_run_fails_closed_instead_of_claiming_old_rows(self) -> None:
        first = self.ingest()
        changed = copy.deepcopy(self.payload)
        changed["bars"][0]["close"] += 1
        with self.assertRaisesRegex(RuntimeError, "failed closed"):
            self.ingest(changed)
        with self.foundation.connect() as connection:
            failed = connection.execute(
                "SELECT run_id, status, accepted_count FROM core_ingestion_runs WHERE status='failed'"
            ).fetchone()
        self.assertIsNotNone(failed)
        self.assertEqual(failed["accepted_count"], 0)
        self.assertEqual(
            self.foundation.create_snapshot(first["run_id"], as_of=AS_OF, known_at=KNOWN_AT)["snapshot_kind"],
            "fixture",
        )
        with self.assertRaises(QualityGateError):
            self.foundation.create_snapshot(failed["run_id"], as_of=AS_OF, known_at=KNOWN_AT)

    def test_failed_retry_preserves_each_attempt_receipt(self) -> None:
        self.ingest()
        changed = copy.deepcopy(self.payload)
        changed["bars"][0]["close"] += 2
        for _ in range(2):
            with self.assertRaisesRegex(RuntimeError, "failed closed"):
                self.ingest(changed)
        with self.foundation.connect() as connection:
            rows = connection.execute(
                "SELECT attempt, status, accepted_count FROM core_ingestion_runs WHERE status='failed' ORDER BY attempt"
            ).fetchall()
        self.assertEqual([(row["attempt"], row["status"], row["accepted_count"]) for row in rows], [(1, "failed", 0), (2, "failed", 0)])

    def test_next_trading_day_ingestion_is_incremental_and_snapshot_includes_history(self) -> None:
        first = self.ingest()
        first_snapshot = self.foundation.create_snapshot(first["run_id"], as_of=AS_OF, known_at=KNOWN_AT)
        next_day = copy.deepcopy(self.payload)
        next_day["as_of"] = "2026-07-20"
        next_day["known_at"] = "2026-07-20T16:30:00+08:00"
        for row in next_day["calendar"]:
            row["trade_date"] = "2026-07-20"
            row["previous_open_date"] = AS_OF
        for row in next_day["statuses"]:
            row["trade_date"] = "2026-07-20"
        for row in next_day["factors"]:
            row["trade_date"] = "2026-07-20"
            row["factor"] = 1.0
        for row in next_day["bars"]:
            row["trade_date"] = "2026-07-20"
            row["close"] += 0.5
        next_day["actions"] = []
        second = self.ingest(next_day)
        self.assertNotEqual(second["run_id"], first["run_id"])
        second_snapshot = self.foundation.create_snapshot(
            second["run_id"], as_of="2026-07-20", known_at=next_day["known_at"]
        )
        first_bars = list(SnapshotReader(self.foundation, first_snapshot["snapshot_id"]).rows("core_daily_bars"))
        second_bars = list(SnapshotReader(self.foundation, second_snapshot["snapshot_id"]).rows("core_daily_bars"))
        self.assertEqual(len(first_bars), 11)
        self.assertEqual(len(second_bars), 22)
        with self.foundation.connect() as connection:
            frozen = connection.execute(
                "SELECT table_name, row_json FROM core_snapshot_items WHERE snapshot_id=?",
                (second_snapshot["snapshot_id"],),
            ).fetchall()
        canonical_raw_hashes = {
            json.loads(row["row_json"])["raw_hash"]
            for row in frozen
            if row["table_name"] in {"core_daily_bars", "core_financial_facts"}
        }
        frozen_raw_hashes = {
            json.loads(row["row_json"])["raw_hash"]
            for row in frozen if row["table_name"] == "core_raw_objects"
        }
        self.assertTrue(canonical_raw_hashes.issubset(frozen_raw_hashes))
        self.assertEqual(len(frozen_raw_hashes), 2)

    def test_fixture_run_cannot_be_promoted_to_real_snapshot(self) -> None:
        result = self.ingest()
        with self.assertRaisesRegex(ValueError, "cannot promote fixture"):
            self.foundation.create_snapshot(
                result["run_id"], as_of=AS_OF, known_at=KNOWN_AT, snapshot_kind="real"
            )

    def test_manifest_version_is_bound_to_run_and_cannot_reuse_old_provenance(self) -> None:
        first = self.ingest()
        v2 = SourceManifest(
            source_key=MANIFEST.source_key,
            domain_scope=MANIFEST.domain_scope,
            authority_tier=MANIFEST.authority_tier,
            provider_version="fixture-2",
            schema_version="fixture-2",
            license_status=MANIFEST.license_status,
            source_url=MANIFEST.source_url,
            quality_flags=MANIFEST.quality_flags,
        )
        with self.assertRaisesRegex(RuntimeError, "failed closed"):
            self.foundation.ingest_fixture(self.payload, v2)
        with self.foundation.connect() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM core_source_manifest_versions").fetchone()[0], 2)
            bound = connection.execute(
                "SELECT source_manifest_hash FROM core_ingestion_runs WHERE run_id=?", (first["run_id"],)
            ).fetchone()[0]
        self.assertEqual(bound, MANIFEST.manifest_hash)
        self.assertEqual(self.foundation.quality_gate(first["run_id"], as_of=AS_OF, known_at=KNOWN_AT), [])

    def test_quality_gate_blocks_missing_adjustment_factor(self) -> None:
        result = self.ingest()
        with self.foundation.connect() as connection:
            connection.execute("DELETE FROM core_adjustment_factors WHERE instrument_id='CN:600519.SH'")
            connection.commit()
        with self.assertRaises(QualityGateError) as caught:
            self.foundation.create_snapshot(result["run_id"], as_of=AS_OF, known_at=KNOWN_AT)
        self.assertIn("bars missing adjustment version", " ".join(caught.exception.blockers))

    def test_quality_gate_blocks_missing_corporate_action_version(self) -> None:
        result = self.ingest()
        with self.foundation.connect() as connection:
            connection.execute("DELETE FROM core_corporate_actions")
            connection.commit()
        with self.assertRaises(QualityGateError) as caught:
            self.foundation.create_snapshot(result["run_id"], as_of=AS_OF, known_at=KNOWN_AT)
        self.assertIn("missing corporate action version", " ".join(caught.exception.blockers))

    def test_raw_payload_and_source_manifest_are_database_enforced_append_only(self) -> None:
        self.ingest()
        with self.assertRaises(sqlite3.IntegrityError):
            with self.foundation.connect() as connection:
                connection.execute("UPDATE core_raw_objects SET payload_json='{}'")
        with self.assertRaises(sqlite3.IntegrityError):
            with self.foundation.connect() as connection:
                connection.execute("UPDATE core_source_manifest_versions SET provider_version='tampered'")

    def test_passed_snapshot_cannot_include_degraded_rows(self) -> None:
        result = self.ingest()
        with self.foundation.connect() as connection:
            connection.execute(
                "UPDATE core_daily_bars SET quality_status='degraded' WHERE instrument_id='CN:600519.SH'"
            )
        with self.assertRaises(QualityGateError) as caught:
            self.foundation.create_snapshot(result["run_id"], as_of=AS_OF, known_at=KNOWN_AT)
        self.assertIn("non-accepted canonical rows", " ".join(caught.exception.blockers))

    def test_quality_gate_reconciles_canonical_rows_to_source_observations(self) -> None:
        result = self.ingest()
        with self.foundation.connect() as connection:
            connection.execute(
                "UPDATE core_daily_bars SET close=9999 WHERE instrument_id='CN:600519.SH'"
            )
        with self.assertRaises(QualityGateError) as caught:
            self.foundation.create_snapshot(result["run_id"], as_of=AS_OF, known_at=KNOWN_AT)
        self.assertIn("missing matching source observation", " ".join(caught.exception.blockers))

    def test_quality_gate_requires_status_for_every_in_scope_instrument(self) -> None:
        result = self.ingest()
        with self.foundation.connect() as connection:
            connection.execute(
                "DELETE FROM core_instrument_status WHERE instrument_id='CN:600519.SH'"
            )
        with self.assertRaises(QualityGateError) as caught:
            self.foundation.create_snapshot(result["run_id"], as_of=AS_OF, known_at=KNOWN_AT)
        self.assertIn("missing trading status", " ".join(caught.exception.blockers))

    def test_quality_gate_blocks_future_financial_revision(self) -> None:
        payload = copy.deepcopy(self.payload)
        payload["financials"][0]["announced_at"] = "2026-07-18T09:00:00+08:00"
        payload["financials"][0]["fact_id"] += ":future"
        result = self.ingest(payload)
        with self.assertRaises(QualityGateError) as caught:
            self.foundation.create_snapshot(result["run_id"], as_of=AS_OF, known_at=KNOWN_AT)
        self.assertIn("future-visible financial facts", " ".join(caught.exception.blockers))

    def test_point_in_time_compares_mixed_offsets_as_instants(self) -> None:
        payload = copy.deepcopy(self.payload)
        payload["financials"][0]["announced_at"] = "2026-07-17T09:00:00+00:00"
        payload["financials"][0]["fact_id"] += ":mixed-offset-future"
        result = self.ingest(payload)
        with self.assertRaises(QualityGateError) as caught:
            self.foundation.create_snapshot(result["run_id"], as_of=AS_OF, known_at=KNOWN_AT)
        self.assertIn("future-visible financial facts", " ".join(caught.exception.blockers))

    def test_later_run_cannot_hide_future_fact_from_earlier_lineage(self) -> None:
        first_payload = copy.deepcopy(self.payload)
        first_payload["financials"][0]["announced_at"] = "2026-07-20T09:00:00+08:00"
        first_payload["financials"][0]["fact_id"] += ":future-lineage"
        first = self.ingest(first_payload)
        with self.assertRaises(QualityGateError):
            self.foundation.create_snapshot(first["run_id"], as_of=AS_OF, known_at=KNOWN_AT)

        next_day = copy.deepcopy(self.payload)
        next_day["as_of"] = "2026-07-18"
        next_day["known_at"] = "2026-07-18T16:30:00+08:00"
        next_day["financials"] = []
        next_day["actions"] = []
        for row in next_day["calendar"]:
            row["trade_date"] = "2026-07-18"
            row["previous_open_date"] = AS_OF
        for row in next_day["statuses"]:
            row["trade_date"] = "2026-07-18"
        for row in next_day["factors"]:
            row["trade_date"] = "2026-07-18"
            row["factor"] = 1.0
        for row in next_day["bars"]:
            row["trade_date"] = "2026-07-18"
        second = self.ingest(next_day)
        with self.assertRaises(QualityGateError) as caught:
            self.foundation.create_snapshot(
                second["run_id"], as_of="2026-07-18", known_at=next_day["known_at"]
            )
        self.assertIn("future-visible financial facts", " ".join(caught.exception.blockers))

    def test_future_corporate_action_cannot_back_current_adjustment_factor(self) -> None:
        payload = copy.deepcopy(self.payload)
        payload["actions"][0]["announced_at"] = "2026-07-18T09:00:00+08:00"
        result = self.ingest(payload)
        with self.assertRaises(QualityGateError) as caught:
            self.foundation.create_snapshot(result["run_id"], as_of=AS_OF, known_at=KNOWN_AT)
        blockers = " ".join(caught.exception.blockers)
        self.assertIn("future-visible corporate actions", blockers)
        self.assertIn("missing corporate action version", blockers)

    def test_snapshot_replay_is_deterministic_and_append_only(self) -> None:
        result = self.ingest()
        snapshot = self.foundation.create_snapshot(result["run_id"], as_of=AS_OF, known_at=KNOWN_AT)
        self.assertEqual(snapshot["snapshot_kind"], "fixture")
        self.assertEqual(self.foundation.replay_digest(snapshot["snapshot_id"]), self.foundation.replay_digest(snapshot["snapshot_id"]))
        with self.assertRaises(sqlite3.IntegrityError):
            with self.foundation.connect() as connection:
                connection.execute("UPDATE core_snapshot_manifests SET known_at=? WHERE snapshot_id=?", ("2099-01-01", snapshot["snapshot_id"]))
        with self.foundation.connect() as connection:
            manifest = json.loads(connection.execute(
                "SELECT manifest_json FROM core_snapshot_manifests WHERE snapshot_id=?", (snapshot["snapshot_id"],)
            ).fetchone()[0])
        self.assertTrue(manifest["quality_evaluation_id"])
        self.assertTrue(manifest["quality_digest"])

    def test_quality_evaluation_identity_binds_selected_state_without_duplicates(self) -> None:
        result = self.ingest()
        passed = self.foundation.quality_evaluation(result["run_id"], as_of=AS_OF, known_at=KNOWN_AT)
        with self.foundation.connect() as connection:
            factor = dict(connection.execute(
                "SELECT * FROM core_adjustment_factors WHERE instrument_id='CN:600519.SH'"
            ).fetchone())
            connection.execute(
                "DELETE FROM core_adjustment_factors WHERE instrument_id='CN:600519.SH'"
            )
        blocked = self.foundation.quality_evaluation(result["run_id"], as_of=AS_OF, known_at=KNOWN_AT)
        self.assertNotEqual(blocked["evaluation_id"], passed["evaluation_id"])
        with self.foundation.connect() as connection:
            columns = list(factor)
            connection.execute(
                f"INSERT INTO core_adjustment_factors ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                [factor[column] for column in columns],
            )
        passed_again = self.foundation.quality_evaluation(result["run_id"], as_of=AS_OF, known_at=KNOWN_AT)
        self.assertEqual(passed_again["evaluation_id"], passed["evaluation_id"])
        with self.foundation.connect() as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM core_quality_results WHERE evaluation_id=?",
                (passed["evaluation_id"],),
            ).fetchone()[0]
        self.assertEqual(count, len(passed["results"]))

    def test_snapshot_blocks_state_change_between_gate_and_freeze(self) -> None:
        result = self.ingest()
        db_path = self.db_path

        class MutatingFoundation(DataFoundation):
            def quality_evaluation(self, run_id, *, as_of, known_at):
                evaluation = super().quality_evaluation(run_id, as_of=as_of, known_at=known_at)
                with self.connect() as connection:
                    connection.execute(
                        "UPDATE core_daily_bars SET close=9999 WHERE instrument_id='CN:600519.SH'"
                    )
                return evaluation

        with self.assertRaises(QualityGateError) as caught:
            MutatingFoundation(db_path).create_snapshot(
                result["run_id"], as_of=AS_OF, known_at=KNOWN_AT
            )
        self.assertIn("state changed after quality evaluation", " ".join(caught.exception.blockers))

    def test_snapshot_reader_returns_frozen_rows_after_canonical_state_changes(self) -> None:
        result = self.ingest()
        snapshot = self.foundation.create_snapshot(result["run_id"], as_of=AS_OF, known_at=KNOWN_AT)
        reader = SnapshotReader(self.foundation, snapshot["snapshot_id"])
        before = list(reader.rows("core_daily_bars"))
        with self.foundation.connect() as connection:
            connection.execute(
                """UPDATE core_daily_bars SET close=close+999
                   WHERE instrument_id='CN:600519.SH' AND trade_date=?""",
                (AS_OF,),
            )
            connection.commit()
        self.assertEqual(list(reader.rows("core_daily_bars")), before)
        with self.foundation.connect() as connection:
            current_close = connection.execute(
                "SELECT close FROM core_daily_bars WHERE instrument_id='CN:600519.SH' AND trade_date=?",
                (AS_OF,),
            ).fetchone()[0]
        self.assertNotEqual(
            current_close,
            next(row["close"] for row in before if row["instrument_id"] == "CN:600519.SH"),
        )

    def test_product_replay_path_consumes_canonical_snapshot_without_network(self) -> None:
        result = self.ingest()
        snapshot = self.foundation.create_snapshot(result["run_id"], as_of=AS_OF, known_at=KNOWN_AT)
        from real_pipeline import replay_snapshot

        with patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden during replay")):
            replay = replay_snapshot(snapshot["snapshot_id"], self.db_path)
        self.assertTrue(replay["canonical"])
        self.assertEqual(replay["instrument_count"], 12)
        self.assertEqual(replay["contexts"]["300750.SZ"]["snapshot_id"], snapshot["snapshot_id"])

    def test_export_import_restore_preserves_replay_digest(self) -> None:
        result = self.ingest()
        snapshot = self.foundation.create_snapshot(result["run_id"], as_of=AS_OF, known_at=KNOWN_AT)
        before = self.foundation.replay_digest(snapshot["snapshot_id"])
        bundle = self.foundation.export_bundle()
        restored = DataFoundation(Path(self.temp.name) / "restored.db")
        restored.import_bundle(bundle)
        self.assertEqual(restored.replay_digest(snapshot["snapshot_id"]), before)
        self.assertEqual(restored.export_bundle()["bundle_hash"], bundle["bundle_hash"])

    def test_export_rejects_tampering(self) -> None:
        self.ingest()
        bundle = self.foundation.export_bundle()
        bundle["tables"]["core_instruments"][0]["name"] = "tampered"
        restored = DataFoundation(Path(self.temp.name) / "tampered.db")
        with self.assertRaisesRegex(ValueError, "invalid or incompatible"):
            restored.import_bundle(bundle)


if __name__ == "__main__":
    unittest.main()
