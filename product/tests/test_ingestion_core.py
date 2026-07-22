from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[2]
PRODUCT = ROOT / "product"
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from data_core import (  # noqa: E402
    AdapterContractError,
    AdapterRegistry,
    AuthoritySinkError,
    FetchedPayload,
    FetchRequest,
    IngestionAttempt,
    IngestionRuntime,
    QualityPolicy,
    RecordDomain,
    RecordEnvelope,
    RecordStatus,
    SQLiteFetchCache,
    SourceChoice,
    SourceManifest,
    SupabaseAuthoritySink,
    build_raw_capture,
    raw_storage_key,
    validate_fetched_payload,
)


KNOWN_AT = "2026-07-22T01:00:00Z"
FETCHED_AT = "2026-07-22T01:00:00Z"


def manifest_for(source_key: str, domain: RecordDomain) -> SourceManifest:
    return SourceManifest(
        source_key=source_key,
        domain_scope=domain.value,
        authority_tier="official",
        provider_version="2026-07-22",
        schema_version=f"{domain.value}-provider-v1",
        license_status="configured_internal_use",
        source_url=f"https://example.test/{source_key}",
    )


def payload_for(domain: RecordDomain, raw_hash: str) -> dict[str, object]:
    if domain is RecordDomain.MARKET:
        return {
            "instrument_id": "CN:300750.SZ",
            "observed_at": "2026-07-21T07:00:00Z",
            "metric": "close",
            "value": 258.2,
            "unit": "CNY/share",
        }
    if domain is RecordDomain.FUNDAMENTAL:
        return {
            "instrument_id": "CN:300750.SZ",
            "report_period": "2026-06-30",
            "announced_at": "2026-07-21T10:00:00Z",
            "metric": "revenue",
            "value": 102400000000,
            "unit": "CNY",
        }
    if domain is RecordDomain.DOCUMENT:
        key = raw_storage_key(raw_hash=raw_hash)
        return {
            "document_id": "doc-300750-20260721",
            "instrument_id": "CN:300750.SZ",
            "document_type": "annual_report",
            "published_at": "2026-07-21T10:00:00Z",
            "content_hash": raw_hash,
            "storage_uri": f"{key.bucket}/{key.path}",
        }
    if domain is RecordDomain.ESTIMATE:
        return {
            "estimate_id": "est-300750-2027-eps",
            "instrument_id": "CN:300750.SZ",
            "broker": "Example Securities",
            "published_at": "2026-07-21T10:00:00Z",
            "fiscal_period": "2027-12-31",
            "metric": "eps",
            "value": 18.5,
            "unit": "CNY/share",
        }
    if domain is RecordDomain.EVENT:
        return {
            "event_id": "evt-300750-1",
            "instrument_id": "CN:300750.SZ",
            "event_type": "announcement",
            "occurred_at": "2026-07-21T10:00:00Z",
            "title": "Example event",
            "evidence_ids": ["doc-300750-20260721"],
        }
    raise AssertionError(domain)


class StaticAdapter:
    def __init__(
        self,
        source_key: str,
        domain: RecordDomain,
        *,
        data_kind: str = "real",
        quality_flags: tuple[str, ...] = (),
        accepted: bool = True,
        delay: float = 0,
        fail: Exception | None = None,
        parse_error: Exception | None = None,
        wrong_domain: RecordDomain | None = None,
        raw_body: bytes | None = None,
    ) -> None:
        self.manifest = manifest_for(source_key, domain)
        self.domain = domain
        self.data_kind = data_kind
        self.quality_flags = quality_flags
        self.accepted = accepted
        self.delay = delay
        self.fail = fail
        self.parse_error = parse_error
        self.wrong_domain = wrong_domain
        self.raw_body = raw_body or json.dumps(
            {"source": source_key, "domain": domain.value}, sort_keys=True
        ).encode()

    async def fetch(self, request: FetchRequest) -> FetchedPayload:
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail is not None:
            raise self.fail
        return FetchedPayload(
            body=self.raw_body,
            source_url=f"https://example.test/{self.manifest.source_key}/{request.entity_key}",
            fetched_at=FETCHED_AT,
            known_at=KNOWN_AT,
            mime_type="application/json",
            data_kind=self.data_kind,
        )

    def parse(
        self,
        request: FetchRequest,
        fetched: FetchedPayload,
        raw,
    ) -> Iterable[RecordEnvelope]:
        if self.parse_error is not None:
            raise self.parse_error
        domain = self.wrong_domain or self.domain
        payload = payload_for(domain, raw.raw_hash)
        entity_key = f"{request.entity_key}:{domain.value}"
        if self.accepted:
            return (
                RecordEnvelope.accepted(
                    domain=domain,
                    entity_key=entity_key,
                    payload=payload,
                    manifest=self.manifest,
                    raw=raw,
                    quality_flags=self.quality_flags,
                ),
            )
        return (
            RecordEnvelope.rejected(
                domain=domain,
                entity_key=entity_key,
                payload={"provider_payload": "bad"},
                manifest=self.manifest,
                raw=raw,
                rejection_reason="provider payload failed validation",
                violations=("payload.invalid",),
                quality_flags=self.quality_flags,
            ),
        )


class RecordingSink:
    def __init__(self) -> None:
        self.attempts: list[IngestionAttempt] = []

    def persist_attempt(self, attempt: IngestionAttempt) -> None:
        self.attempts.append(attempt)


class FixtureRejectingSink(RecordingSink):
    def persist_attempt(self, attempt: IngestionAttempt) -> None:
        if attempt.data_kind == "fixture":
            raise AssertionError("fixture attempts must not be persisted to authority")
        super().persist_attempt(attempt)


class ManualClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 7, 22, 1, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        current = self.value
        self.value = self.value + timedelta(seconds=1)
        return current


def request_for(domain: RecordDomain) -> FetchRequest:
    return FetchRequest.create(
        request_id=f"req-{domain.value}",
        domain=domain,
        entity_key="CN:300750.SZ",
        parameters={"window": "latest"},
    )


def registry_with(*adapters: StaticAdapter) -> AdapterRegistry:
    registry = AdapterRegistry()
    for adapter in adapters:
        registry.register(adapter)
    return registry


class FakeObjectStore:
    def __init__(self) -> None:
        self.objects: list[dict[str, object]] = []

    def put_if_absent(self, *, bucket: str, path: str, body: bytes, content_type: str) -> None:
        self.objects.append(
            {"bucket": bucket, "path": path, "body": body, "content_type": content_type}
        )


class FakeCursor:
    def __init__(self) -> None:
        self.statements: list[tuple[str, tuple[object, ...]]] = []
        self.fetchone_value: tuple[object, ...] | None = None

    def execute(self, sql: str, params: tuple[object, ...]) -> None:
        self.statements.append((" ".join(sql.split()), params))
        if "insert into control.raw_objects" in sql:
            self.fetchone_value = (params[1], params[2], params[3])

    def fetchone(self):
        return self.fetchone_value

    def close(self) -> None:
        pass


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self.cursor_obj = cursor
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def cursor(self) -> FakeCursor:
        return self.cursor_obj

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True


class IngestionCoreTests(unittest.TestCase):
    def test_all_five_domains_use_same_adapter_contract_harness(self) -> None:
        for domain in RecordDomain:
            adapter = StaticAdapter(f"src-{domain.value}", domain)
            fetched = asyncio.run(adapter.fetch(request_for(domain)))
            validated = validate_fetched_payload(adapter, request_for(domain), fetched)
            self.assertTrue(validated.quality.passed)
            self.assertEqual(validated.records[0].domain, domain)
            self.assertEqual(validated.records[0].provenance.raw_hash, validated.raw.raw_hash)

    def test_raw_capture_path_is_content_addressed(self) -> None:
        fetched = FetchedPayload(
            body=b'{"x":1}',
            source_url="https://example.test/raw",
            fetched_at=FETCHED_AT,
            known_at=KNOWN_AT,
            mime_type="application/json",
        )
        raw = build_raw_capture(fetched)
        self.assertEqual(raw.raw_hash, raw_storage_key(raw_hash=raw.raw_hash).raw_hash)
        self.assertEqual(raw.storage_uri, f"canonical-raw/raw/sha256/{raw.raw_hash[:2]}/{raw.raw_hash}")

    def test_invalid_output_and_wrong_domain_fail_closed(self) -> None:
        request = request_for(RecordDomain.MARKET)
        adapter = StaticAdapter("src-market", RecordDomain.MARKET)
        fetched = asyncio.run(adapter.fetch(request))
        adapter.parse = lambda *_args: [{"not": "an envelope"}]  # type: ignore[method-assign]
        with self.assertRaises(AdapterContractError):
            validate_fetched_payload(adapter, request, fetched)

        wrong = StaticAdapter("src-market-2", RecordDomain.MARKET, wrong_domain=RecordDomain.EVENT)
        fetched = asyncio.run(wrong.fetch(request))
        with self.assertRaises(AdapterContractError):
            validate_fetched_payload(wrong, request, fetched)

    def test_primary_failure_falls_back_and_persists_both_live_attempts(self) -> None:
        primary = StaticAdapter("primary", RecordDomain.MARKET, fail=RuntimeError("down"))
        fallback = StaticAdapter("fallback", RecordDomain.MARKET)
        sink = RecordingSink()
        runtime = IngestionRuntime(
            registry_with(primary, fallback),
            sink,
            clock=ManualClock(),
            timeout_seconds=0.1,
        )
        outcome = asyncio.run(
            runtime.run(
                request_for(RecordDomain.MARKET),
                (SourceChoice("primary", "primary"), SourceChoice("fallback", "fallback")),
            )
        )
        self.assertTrue(outcome.publishable)
        self.assertEqual(outcome.selected_source, "fallback")
        self.assertEqual([attempt.status for attempt in sink.attempts], ["failed", "success"])

    def test_quality_block_falls_back(self) -> None:
        primary = StaticAdapter("primary", RecordDomain.MARKET, quality_flags=("stale",))
        fallback = StaticAdapter("fallback", RecordDomain.MARKET)
        sink = RecordingSink()
        runtime = IngestionRuntime(
            registry_with(primary, fallback),
            sink,
            quality_policy=QualityPolicy(blocking_flags=("stale",)),
            clock=ManualClock(),
        )
        outcome = asyncio.run(
            runtime.run(
                request_for(RecordDomain.MARKET),
                (SourceChoice("primary", "primary"), SourceChoice("fallback", "fallback")),
            )
        )
        self.assertTrue(outcome.publishable)
        self.assertEqual(outcome.selected_source, "fallback")
        self.assertEqual(sink.attempts[0].status, "degraded")

    def test_sqlite_cache_is_degraded_and_not_authority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cache = SQLiteFetchCache(Path(directory) / "fetch-cache.sqlite")
            source = StaticAdapter("source", RecordDomain.MARKET)
            first_sink = RecordingSink()
            first_runtime = IngestionRuntime(
                registry_with(source), first_sink, cache=cache, clock=ManualClock()
            )
            first = asyncio.run(
                first_runtime.run(request_for(RecordDomain.MARKET), (SourceChoice("source", "primary"),))
            )
            self.assertTrue(first.publishable)
            self.assertEqual(cache.count(), 1)
            self.assertEqual(len(first_sink.attempts), 1)

            failing = StaticAdapter("source", RecordDomain.MARKET, fail=RuntimeError("offline"))
            second_sink = RecordingSink()
            second_runtime = IngestionRuntime(
                registry_with(failing), second_sink, cache=cache, clock=ManualClock()
            )
            second = asyncio.run(
                second_runtime.run(request_for(RecordDomain.MARKET), (SourceChoice("source", "primary"),))
            )
            self.assertEqual(second.status, "degraded")
            self.assertFalse(second.publishable)
            self.assertEqual(second.data_kind, "cached")
            self.assertFalse(cache.authority)
            self.assertEqual([attempt.data_kind for attempt in second_sink.attempts], ["real"])

    def test_registry_duplicate_fails_closed(self) -> None:
        registry = AdapterRegistry()
        registry.register(StaticAdapter("dup", RecordDomain.MARKET))
        with self.assertRaises(AdapterContractError):
            registry.register(StaticAdapter("dup", RecordDomain.MARKET))

    def test_supabase_sink_uploads_raw_and_emits_authority_sql(self) -> None:
        adapter = StaticAdapter("source", RecordDomain.DOCUMENT)
        sink = RecordingSink()
        runtime = IngestionRuntime(registry_with(adapter), sink, clock=ManualClock())
        outcome = asyncio.run(
            runtime.run(request_for(RecordDomain.DOCUMENT), (SourceChoice("source", "primary"),))
        )
        self.assertTrue(outcome.publishable)
        cursor = FakeCursor()
        connection = FakeConnection(cursor)
        object_store = FakeObjectStore()
        authority = SupabaseAuthoritySink(
            connection_factory=lambda: connection,
            object_store=object_store,
        )
        authority.persist_attempt(sink.attempts[0])
        sql = "\n".join(statement for statement, _params in cursor.statements)
        self.assertIn("insert into control.source_manifests", sql)
        self.assertIn("insert into control.ingestion_runs", sql)
        self.assertIn("insert into control.raw_objects", sql)
        self.assertIn("insert into control.raw_captures", sql)
        self.assertIn("insert into control.record_receipts", sql)
        self.assertIn("insert into research.documents", sql)
        self.assertEqual(object_store.objects[0]["bucket"], "canonical-raw")
        self.assertTrue(connection.committed)
        self.assertFalse(connection.rolled_back)

    def test_supabase_sink_does_not_insert_domain_rows_for_degraded_attempt(self) -> None:
        adapter = StaticAdapter("source", RecordDomain.MARKET, quality_flags=("stale",))
        sink = RecordingSink()
        runtime = IngestionRuntime(
            registry_with(adapter),
            sink,
            quality_policy=QualityPolicy(blocking_flags=("stale",)),
            clock=ManualClock(),
        )
        outcome = asyncio.run(
            runtime.run(request_for(RecordDomain.MARKET), (SourceChoice("source", "primary"),))
        )
        self.assertFalse(outcome.publishable)
        cursor = FakeCursor()
        authority = SupabaseAuthoritySink(
            connection_factory=lambda: FakeConnection(cursor),
            object_store=FakeObjectStore(),
        )
        authority.persist_attempt(sink.attempts[0])
        sql = "\n".join(statement for statement, _params in cursor.statements)
        self.assertNotIn("insert into control.record_receipts", sql)
        self.assertNotIn("insert into market.market_records", sql)

    def test_supabase_sink_rejects_cached_attempts(self) -> None:
        adapter = StaticAdapter("source", RecordDomain.MARKET)
        fetched = asyncio.run(adapter.fetch(request_for(RecordDomain.MARKET)))
        cached = FetchedPayload(
            body=fetched.body,
            source_url=fetched.source_url,
            fetched_at=fetched.fetched_at,
            known_at=fetched.known_at,
            mime_type=fetched.mime_type,
            data_kind="cached",
        )
        with tempfile.TemporaryDirectory() as directory:
            cache = SQLiteFetchCache(Path(directory) / "fetch-cache.sqlite")
            cache.put("source", request_for(RecordDomain.MARKET), fetched)
            failing = StaticAdapter("source", RecordDomain.MARKET, fail=RuntimeError("offline"))
            runtime = IngestionRuntime(
                registry_with(failing), RecordingSink(), cache=cache, clock=ManualClock()
            )
            outcome = asyncio.run(
                runtime.run(request_for(RecordDomain.MARKET), (SourceChoice("source", "primary"),))
            )
        cached_attempt = outcome.attempts[-1]
        self.assertEqual(cached_attempt.data_kind, "cached")
        authority = SupabaseAuthoritySink(
            connection_factory=lambda: FakeConnection(FakeCursor()),
            object_store=FakeObjectStore(),
        )
        with self.assertRaises(AuthoritySinkError):
            authority.persist_attempt(cached_attempt)
        self.assertEqual(cached.data_kind, "cached")

    def test_supabase_sink_rejects_fixture_attempts(self) -> None:
        adapter = StaticAdapter("fixture-source", RecordDomain.MARKET, data_kind="fixture")
        sink = RecordingSink()
        runtime = IngestionRuntime(registry_with(adapter), sink, clock=ManualClock())
        outcome = asyncio.run(
            runtime.run(request_for(RecordDomain.MARKET), (SourceChoice("fixture-source", "primary"),))
        )
        authority = SupabaseAuthoritySink(
            connection_factory=lambda: FakeConnection(FakeCursor()),
            object_store=FakeObjectStore(),
        )
        with self.assertRaises(AuthoritySinkError):
            authority.persist_attempt(outcome.attempts[0])

    def test_document_record_must_match_raw_capture_identity(self) -> None:
        adapter = StaticAdapter("source", RecordDomain.DOCUMENT)
        request = request_for(RecordDomain.DOCUMENT)
        fetched = asyncio.run(adapter.fetch(request))
        raw = build_raw_capture(fetched)

        def mismatched_parse(*_args):
            payload = payload_for(RecordDomain.DOCUMENT, "b" * 64)
            return (
                RecordEnvelope.accepted(
                    domain=RecordDomain.DOCUMENT,
                    entity_key="doc:mismatch",
                    payload=payload,
                    manifest=adapter.manifest,
                    raw=raw,
                ),
            )

        adapter.parse = mismatched_parse  # type: ignore[method-assign]
        with self.assertRaises(AdapterContractError):
            validate_fetched_payload(adapter, request, fetched, raw=raw)

    def test_parse_failure_still_persists_raw_capture(self) -> None:
        adapter = StaticAdapter("source", RecordDomain.MARKET, parse_error=ValueError("bad parse"))
        sink = RecordingSink()
        runtime = IngestionRuntime(registry_with(adapter), sink, clock=ManualClock())
        outcome = asyncio.run(
            runtime.run(request_for(RecordDomain.MARKET), (SourceChoice("source", "primary"),))
        )
        self.assertEqual(outcome.status, "failed")
        self.assertIsNotNone(sink.attempts[0].raw)
        self.assertEqual(sink.attempts[0].records, ())

    def test_live_adapter_cached_label_is_failed_but_raw_is_audited(self) -> None:
        adapter = StaticAdapter("source", RecordDomain.MARKET, data_kind="cached")
        sink = RecordingSink()
        runtime = IngestionRuntime(registry_with(adapter), sink, clock=ManualClock())
        outcome = asyncio.run(
            runtime.run(request_for(RecordDomain.MARKET), (SourceChoice("source", "primary"),))
        )
        self.assertEqual(outcome.status, "failed")
        self.assertEqual(len(sink.attempts), 1)
        self.assertEqual(sink.attempts[0].data_kind, "real")
        self.assertIsNotNone(sink.attempts[0].raw)
        self.assertIn("live adapter cannot label", sink.attempts[0].error or "")

    def test_fixture_data_never_promotes(self) -> None:
        adapter = StaticAdapter("fixture-source", RecordDomain.MARKET, data_kind="fixture")
        sink = RecordingSink()
        runtime = IngestionRuntime(registry_with(adapter), sink, clock=ManualClock())
        outcome = asyncio.run(
            runtime.run(request_for(RecordDomain.MARKET), (SourceChoice("fixture-source", "primary"),))
        )
        self.assertFalse(outcome.publishable)
        self.assertEqual(outcome.attempts[0].status, "degraded")
        self.assertEqual(outcome.attempts[0].data_kind, "fixture")
        self.assertEqual(sink.attempts, [])

    def test_fixture_primary_does_not_abort_real_fallback(self) -> None:
        fixture = StaticAdapter("fixture-source", RecordDomain.MARKET, data_kind="fixture")
        fallback = StaticAdapter("real-fallback", RecordDomain.MARKET)
        sink = FixtureRejectingSink()
        runtime = IngestionRuntime(registry_with(fixture, fallback), sink, clock=ManualClock())
        outcome = asyncio.run(
            runtime.run(
                request_for(RecordDomain.MARKET),
                (
                    SourceChoice("fixture-source", "primary"),
                    SourceChoice("real-fallback", "fallback"),
                ),
            )
        )
        self.assertTrue(outcome.publishable)
        self.assertEqual(outcome.selected_source, "real-fallback")
        self.assertEqual([attempt.choice.source_key for attempt in sink.attempts], ["real-fallback"])


if __name__ == "__main__":
    unittest.main()
