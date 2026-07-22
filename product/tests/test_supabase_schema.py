from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import unittest


ROOT = Path(__file__).resolve().parents[2]
PRODUCT = ROOT / "product"
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from data_core import RAW_BUCKET, StorageObjectKey, raw_storage_key  # noqa: E402


MIGRATION = ROOT / "supabase/migrations/202607220001_canonical_authority.sql"
SEED = ROOT / "supabase/seed.sql"
BUCKET = ROOT / "supabase/storage/canonical-raw.bucket.json"


class SupabaseSchemaTests(unittest.TestCase):
    def test_storage_paths_are_deterministic_typed_and_safe(self) -> None:
        key = raw_storage_key(raw_hash="a" * 64)
        self.assertEqual(key.bucket, RAW_BUCKET)
        self.assertEqual(key.path, f"raw/sha256/aa/{'a' * 64}")
        self.assertEqual(key, raw_storage_key(raw_hash="a" * 64))
        with self.assertRaisesRegex(ValueError, "lowercase SHA-256"):
            raw_storage_key(raw_hash="not-a-hash")
        with self.assertRaisesRegex(ValueError, "content-addressed raw layout"):
            StorageObjectKey(
                bucket=RAW_BUCKET,
                path=f"wrong/sha256/aa/{'a' * 64}",
                raw_hash="a" * 64,
            ).validate()
        with self.assertRaisesRegex(ValueError, "content-addressed raw layout"):
            StorageObjectKey(
                bucket=RAW_BUCKET,
                path=f"raw/sha256/99/{'a' * 64}",
                raw_hash="a" * 64,
            ).validate()

    def test_migration_declares_three_schemas_rls_and_service_role_boundary(self) -> None:
        sql = MIGRATION.read_text()
        for schema in ("market", "research", "control"):
            self.assertIn(f"create schema if not exists {schema};", sql)
        for table in (
            "control.source_manifests", "control.ingestion_runs", "control.raw_objects",
            "control.raw_captures", "control.record_receipts", "market.market_records", "market.fundamental_records",
            "research.documents", "research.estimates", "research.events",
            "control.dataset_snapshots", "control.dataset_snapshot_records",
        ):
            self.assertIn(f"create table if not exists {table}", sql)
            self.assertIn(f"alter table {table} enable row level security;", sql)
        self.assertIn("revoke all on schema market, research, control from anon, authenticated", sql)
        self.assertIn("grant all on all tables in schema market, research, control to service_role", sql)
        self.assertNotIn("storage.objects", sql)
        self.assertNotIn("insert into storage.buckets", sql)
        self.assertNotIn("grant select", sql.lower())
        bucket = json.loads(BUCKET.read_text())
        self.assertEqual(bucket["id"], RAW_BUCKET)
        self.assertFalse(bucket["public"])
        self.assertEqual(bucket["file_size_limit"], 50 * 1024 * 1024)
        self.assertEqual(bucket["client_policies"], [])
        self.assertFalse(bucket["managed_storage_schema_mutation"])

    def test_dev_seed_contains_no_market_or_research_facts(self) -> None:
        seed = SEED.read_text()
        self.assertIn("development_seed_v1", seed)
        self.assertIn("false", seed)
        self.assertNotIn("market.market_records", seed)
        self.assertNotIn("market.fundamental_records", seed)
        self.assertNotIn("research.documents", seed)

    def test_empty_supabase_databases_replay_to_identical_schema(self) -> None:
        docker = shutil.which("docker")
        if not docker:
            self.skipTest("docker is unavailable")
        if subprocess.run([docker, "info"], capture_output=True).returncode != 0:
            self.skipTest("docker daemon is unavailable")
        if subprocess.run(
            [docker, "image", "inspect", "postgres:16-alpine"], capture_output=True
        ).returncode != 0:
            self.skipTest("local postgres:16-alpine image is unavailable")

        name = f"equity-research-a2-{os.getpid()}"
        subprocess.run([docker, "container", "rm", name], capture_output=True)
        started = subprocess.run(
            [
                docker, "run", "--detach", "--name", name,
                "--env", "POSTGRES_PASSWORD=contract-test", "postgres:16-alpine",
            ],
            text=True,
            capture_output=True,
        )
        self.assertEqual(started.returncode, 0, started.stderr)
        try:
            for _ in range(60):
                ready = subprocess.run(
                    [docker, "exec", name, "pg_isready", "-U", "postgres"],
                    capture_output=True,
                )
                if ready.returncode == 0:
                    break
                time.sleep(0.2)
            else:
                self.fail("postgres contract container did not become ready")
            # The official image briefly exposes its initialization server,
            # then restarts into the final server. Wait through that handoff.
            time.sleep(1)
            for _ in range(30):
                stable = subprocess.run(
                    [docker, "exec", name, "psql", "-U", "postgres", "-d", "postgres", "-c", "select 1"],
                    capture_output=True,
                )
                if stable.returncode == 0:
                    break
                time.sleep(0.2)
            else:
                self.fail("postgres contract container did not reach stable ready state")

            roles = """
do $$ begin
  if not exists (select 1 from pg_roles where rolname='anon') then create role anon nologin; end if;
  if not exists (select 1 from pg_roles where rolname='authenticated') then create role authenticated nologin; end if;
  if not exists (select 1 from pg_roles where rolname='service_role') then create role service_role nologin bypassrls; end if;
end $$;
"""
            self._psql(docker, name, "postgres", roles)
            signatures = []
            for database in ("authority_one", "authority_two"):
                for _ in range(20):
                    created = subprocess.run(
                        [docker, "exec", name, "createdb", "-U", "postgres", database],
                        text=True,
                        capture_output=True,
                    )
                    if created.returncode == 0:
                        break
                    time.sleep(0.2)
                self.assertEqual(created.returncode, 0, created.stderr)
                self._psql(docker, name, database, self._supabase_storage_prelude())
                self._psql(docker, name, database, MIGRATION.read_text())
                self._psql(docker, name, database, SEED.read_text())
                signatures.append(self._schema_signature(docker, name, database))
                seed_count = self._psql(
                    docker, name, database,
                    "select count(*) from control.source_manifests where source_key='development_seed_v1';",
                    tuples=True,
                )
                self.assertEqual(seed_count.strip(), "1")

                self._psql(
                    docker, name, database,
                    f"""
insert into control.source_manifests(
  manifest_hash, source_key, domain_scope, authority_tier, provider_version,
  provider_schema_version, license_status, source_url, active
) values (
  repeat('a',64), 'authority_test_v1', array['market','fundamental'], 'canonical', 'test-v1',
  'test-schema-v1', 'test_fixture', 'https://example.test/', true
);
insert into control.ingestion_runs(
  run_id, manifest_hash, idempotency_key, attempt, data_kind, status, started_at, finished_at
) values ('run-1', repeat('a',64), 'seed-run', 1, 'fixture', 'success', now(), now());
insert into control.raw_objects(
  raw_hash, storage_bucket, storage_path, payload_size
) values (
  repeat('1',64), 'canonical-raw',
  'raw/sha256/11/{'1' * 64}', 2
);
insert into control.raw_captures(
  capture_id, raw_hash, run_id, manifest_hash, source_url, mime_type, fetched_at, known_at
) values (
  'capture-1', repeat('1',64), 'run-1', repeat('a',64),
  'https://example.test/market.json', 'application/json', now(), now()
);
insert into control.record_receipts(
  record_hash, contract_version, capture_id, run_id, raw_hash, manifest_hash, domain, record_schema_version,
  entity_key, payload_json, payload_hash, known_at, status, rejection_reason, violations
) values (
  repeat('2',64), 'canonical-data-contract-v1', 'capture-1', 'run-1', repeat('1',64), repeat('a',64), 'market', 'market-record-v1',
  'provider-row-1', '{{}}'::jsonb, repeat('4',64),
  (select known_at from control.raw_captures where capture_id='capture-1'),
  'rejected', 'invalid row', array['value.missing']
);
insert into control.raw_captures(
  capture_id, raw_hash, run_id, manifest_hash, source_url, mime_type, fetched_at, known_at
) values (
  'capture-1b', repeat('1',64), 'run-1', repeat('a',64),
  'https://mirror.example.test/market.json', 'application/json', now(), now() + interval '1 second'
);
insert into control.record_receipts(
  record_hash, contract_version, capture_id, run_id, raw_hash, manifest_hash, domain, record_schema_version,
  entity_key, payload_json, payload_hash, known_at, status, rejection_reason, violations
) values (
  repeat('3',64), 'canonical-data-contract-v1', 'capture-1', 'run-1', repeat('1',64), repeat('a',64),
  'fundamental', 'fundamental-record-v1', 'provider-fundamental-row-1', '{{}}'::jsonb, repeat('3',64),
  (select known_at from control.raw_captures where capture_id='capture-1'),
  'rejected', 'invalid row', array['value.missing']
);
""",
                )
                capture_receipt_counts = self._psql(
                    docker, name, database,
                    "select (select count(*) from control.raw_captures) || ':' || (select count(distinct domain) from control.record_receipts where capture_id='capture-1');",
                    tuples=True,
                )
                self.assertEqual(capture_receipt_counts.strip(), "2:2")
                rejected_canonical = self._psql_result(
                    docker, name, database,
                    """
insert into market.market_records(record_hash,instrument_id,observed_at,metric,value,unit,known_at)
values (repeat('2',64),'CN:300750.SZ',now(),'close',1,'CNY/share',now());
""",
                )
                self.assertNotEqual(rejected_canonical.returncode, 0)
                self.assertIn("requires an accepted receipt", rejected_canonical.stderr)

                self._psql(
                    docker, name, database,
                    """
insert into control.record_receipts(
  record_hash, contract_version, capture_id, run_id, raw_hash, manifest_hash, domain, record_schema_version,
  entity_key, payload_json, payload_hash, known_at, status
) values (
  repeat('6',64), 'canonical-data-contract-v1', 'capture-1', 'run-1', repeat('1',64), repeat('a',64), 'market', 'market-record-v1',
  'market:close:mismatch',
  '{"instrument_id":"CN:300750.SZ","observed_at":"2026-07-22T00:00:00Z","metric":"close","value":100,"unit":"CNY/share"}'::jsonb,
  repeat('6',64), (select known_at from control.raw_captures where capture_id='capture-1'), 'accepted'
);
""",
                )
                divergent = self._psql_result(
                    docker, name, database,
                    """
insert into market.market_records(record_hash,instrument_id,observed_at,metric,value,unit,known_at)
values (
  repeat('6',64), 'CN:300750.SZ', '2026-07-22T00:00:00Z', 'close', 999, 'USD',
  (select known_at from control.raw_captures where capture_id='capture-1')
);
""",
                )
                self.assertNotEqual(divergent.returncode, 0)
                self.assertIn("differs from accepted payload", divergent.stderr)

                self._psql(
                    docker, name, database,
                    """
insert into control.record_receipts(
  record_hash, contract_version, capture_id, run_id, raw_hash, manifest_hash, domain, record_schema_version,
  entity_key, payload_json, payload_hash, known_at, status
) values (
  repeat('9',64), 'canonical-data-contract-v1', 'capture-1', 'run-1', repeat('1',64), repeat('a',64), 'market', 'market-record-v1',
  'market:close:missing-unit',
  '{"instrument_id":"CN:300750.SZ","observed_at":"2026-07-22T00:00:00Z","metric":"close","value":100}'::jsonb,
  repeat('9',64), (select known_at from control.raw_captures where capture_id='capture-1'), 'accepted'
);
""",
                )
                missing_payload_field = self._psql_result(
                    docker, name, database,
                    """
insert into market.market_records(record_hash,instrument_id,observed_at,metric,value,unit,known_at)
values (
  repeat('9',64), 'CN:300750.SZ', '2026-07-22T00:00:00Z', 'close', 100, 'CNY/share',
  (select known_at from control.raw_captures where capture_id='capture-1')
);
""",
                )
                self.assertNotEqual(missing_payload_field.returncode, 0)
                self.assertIn("differs from accepted payload", missing_payload_field.stderr)

                wrong_schema = self._psql_result(
                    docker, name, database,
                    """
insert into control.record_receipts(
  record_hash, contract_version, capture_id, run_id, raw_hash, manifest_hash, domain, record_schema_version,
  entity_key, payload_json, payload_hash, known_at, status
) values (
  repeat('b',64), 'canonical-data-contract-v1', 'capture-1', 'run-1', repeat('1',64), repeat('a',64),
  'market', 'event-record-v1', 'market:wrong-schema', '{}', repeat('b',64),
  (select known_at from control.raw_captures where capture_id='capture-1'), 'accepted'
);
""",
                )
                self.assertNotEqual(wrong_schema.returncode, 0)
                self.assertIn("does not match domain", wrong_schema.stderr)

                future_receipt = self._psql_result(
                    docker, name, database,
                    """
insert into control.record_receipts(
  record_hash, contract_version, capture_id, run_id, raw_hash, manifest_hash, domain, record_schema_version,
  entity_key, payload_json, payload_hash, known_at, status
) values (
  repeat('7',64), 'canonical-data-contract-v1', 'capture-1', 'run-1', repeat('1',64), repeat('a',64), 'market', 'market-record-v1',
  'market:future', '{}', repeat('7',64), '2030-01-01T00:00:00Z', 'accepted'
);
""",
                )
                self.assertNotEqual(future_receipt.returncode, 0)
                self.assertIn("foreign key constraint", future_receipt.stderr)

                invalid_mime = self._psql_result(
                    docker, name, database,
                    """
insert into control.raw_captures(
  capture_id, raw_hash, run_id, manifest_hash, source_url, mime_type, fetched_at, known_at
) values (
  'capture-invalid-mime', repeat('1',64), 'run-1', repeat('a',64),
  'https://example.test/market.json', 'text/plain', now(), now()
);
""",
                )
                self.assertNotEqual(invalid_mime.returncode, 0)
                self.assertIn("check constraint", invalid_mime.stderr)
                hash_path_mismatch = self._psql_result(
                    docker, name, database,
                    f"""
insert into control.raw_objects(raw_hash,storage_bucket,storage_path,payload_size)
values (
  repeat('8',64), 'canonical-raw',
  'raw/sha256/99/{'9' * 64}', 2
);
""",
                )
                self.assertNotEqual(hash_path_mismatch.returncode, 0)
                self.assertIn("check constraint", hash_path_mismatch.stderr)
                self._psql(
                    docker, name, database,
                    """
insert into control.ingestion_runs(
  run_id, manifest_hash, idempotency_key, attempt, data_kind, status, started_at, finished_at
) values ('run-2', repeat('a',64), 'seed-run-2', 1, 'fixture', 'success', now(), now());
insert into control.raw_captures(
  capture_id, raw_hash, run_id, manifest_hash, source_url, mime_type, fetched_at, known_at
) values (
  'capture-2', repeat('1',64), 'run-2', repeat('a',64),
  'https://mirror.example.test/market.json', 'application/json', now(), now() + interval '1 day'
);
""",
                )
                reuse_counts = self._psql(
                    docker, name, database,
                    "select (select count(*) from control.raw_objects) || ':' || (select count(*) from control.raw_captures);",
                    tuples=True,
                )
                self.assertEqual(reuse_counts.strip(), "1:3")

                denied = self._psql_result(
                    docker, name, database,
                    "set role anon; select * from control.source_manifests;",
                )
                self.assertNotEqual(denied.returncode, 0)
                self.assertIn("permission denied", denied.stderr)
                service = self._psql_result(
                    docker, name, database,
                    "set role service_role; select count(*) from control.source_manifests;",
                )
                self.assertEqual(service.returncode, 0, service.stderr)
                immutable = self._psql_result(
                    docker, name, database,
                    "update control.source_manifests set active=true where source_key='development_seed_v1';",
                )
                self.assertNotEqual(immutable.returncode, 0)
                self.assertIn("append-only", immutable.stderr)

            self.assertEqual(signatures[0], signatures[1])
        finally:
            subprocess.run([docker, "stop", "--time", "1", name], capture_output=True)
            subprocess.run([docker, "container", "rm", name], capture_output=True)

    @staticmethod
    def _supabase_storage_prelude() -> str:
        return """
create schema storage;
create table storage.buckets (
  id text primary key,
  name text not null,
  public boolean not null default false,
  file_size_limit bigint,
  allowed_mime_types text[]
);
create table storage.objects (
  id bigint generated always as identity primary key,
  bucket_id text not null references storage.buckets(id),
  name text not null
);
"""

    @staticmethod
    def _psql_result(docker: str, container: str, database: str, sql: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [docker, "exec", "-i", container, "psql", "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-d", database],
            input=sql,
            text=True,
            capture_output=True,
        )

    def _psql(
        self, docker: str, container: str, database: str, sql: str, *, tuples: bool = False
    ) -> str:
        command = [docker, "exec", "-i", container, "psql", "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-d", database]
        if tuples:
            command[5:5] = ["-A", "-t"]
        result = subprocess.run(command, input=sql, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def _schema_signature(self, docker: str, container: str, database: str) -> str:
        sql = """
select json_build_object(
  'tables', (select json_agg(x order by x) from (
    select table_schema || '.' || table_name as x
    from information_schema.tables
    where table_schema in ('market','research','control')
  ) q),
  'rls', (select json_agg(x order by x) from (
    select schemaname || '.' || tablename || ':' || rowsecurity::text as x
    from pg_tables where schemaname in ('market','research','control')
  ) q),
  'raw_capture_table', (select count(*) from information_schema.tables
    where table_schema='control' and table_name='raw_captures')
);
"""
        raw = self._psql(docker, container, database, sql, tuples=True).strip()
        return json.dumps(json.loads(raw), sort_keys=True, separators=(",", ":"))


if __name__ == "__main__":
    unittest.main()
