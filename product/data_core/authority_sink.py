from __future__ import annotations

from typing import Any, Callable, Protocol

from .contracts import RecordDomain, RecordEnvelope, RecordStatus, SourceManifest
from .ingestion import IngestionAttempt
from .storage_layout import RAW_BUCKET, StorageObjectKey


class ObjectStore(Protocol):
    def put_if_absent(
        self,
        *,
        bucket: str,
        path: str,
        body: bytes,
        content_type: str,
    ) -> None:
        ...


class AuthoritySinkError(RuntimeError):
    """Authority persistence failed; ingestion must fail closed."""


class SupabaseAuthoritySink:
    """DB-API + Storage adapter for the canonical-authority-v1 schema.

    The actual Supabase client wiring belongs to deployment. This sink keeps A3
    dependency-free by accepting a DB-API connection factory and a small object
    storage adapter.
    """

    def __init__(
        self,
        *,
        connection_factory: Callable[[], Any],
        object_store: ObjectStore,
    ) -> None:
        self.connection_factory = connection_factory
        self.object_store = object_store

    def persist_attempt(self, attempt: IngestionAttempt) -> None:
        if attempt.data_kind in {"cached", "fixture"}:
            raise AuthoritySinkError(f"{attempt.data_kind} attempts are not authority records")
        attempt.manifest.validate()
        if attempt.raw is not None:
            attempt.raw.validate()
        for record in attempt.records:
            record.validate(manifest=attempt.manifest, raw=attempt.raw)  # type: ignore[arg-type]

        raw_key: StorageObjectKey | None = None
        if attempt.raw is not None:
            raw_key = _storage_key_from_uri(attempt.raw.storage_uri, raw_hash=attempt.raw.raw_hash)
            if attempt.fetched is None:
                raise AuthoritySinkError("raw capture cannot be persisted without fetched bytes")
            self.object_store.put_if_absent(
                bucket=raw_key.bucket,
                path=raw_key.path,
                body=attempt.fetched.body,
                content_type=attempt.raw.mime_type,
            )

        connection = self.connection_factory()
        cursor = connection.cursor()
        try:
            self._insert_manifest(cursor, attempt.manifest)
            self._insert_run(cursor, attempt)
            if raw_key is not None:
                self._insert_raw_object(cursor, attempt, raw_key)
                self._insert_raw_capture(cursor, attempt)
                self._insert_receipts(cursor, attempt)
                if attempt.promote:
                    self._insert_domain_rows(cursor, attempt)
            connection.commit()
        except Exception as exc:
            rollback = getattr(connection, "rollback", None)
            if callable(rollback):
                rollback()
            if isinstance(exc, AuthoritySinkError):
                raise
            raise AuthoritySinkError(str(exc)) from exc
        finally:
            close_cursor = getattr(cursor, "close", None)
            if callable(close_cursor):
                close_cursor()
            close_connection = getattr(connection, "close", None)
            if callable(close_connection):
                close_connection()

    @staticmethod
    def _insert_manifest(cursor: Any, manifest: SourceManifest) -> None:
        cursor.execute(
            """
            insert into control.source_manifests(
              manifest_hash,source_key,domain_scope,authority_tier,provider_version,
              provider_schema_version,license_status,source_url,quality_flags,active
            ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            on conflict (manifest_hash) do nothing
            """,
            (
                manifest.manifest_hash,
                manifest.source_key,
                [domain.value for domain in sorted(manifest.domains, key=lambda item: item.value)],
                manifest.authority_tier,
                manifest.provider_version,
                manifest.schema_version,
                manifest.license_status,
                manifest.source_url,
                list(manifest.quality_flags),
                manifest.active,
            ),
        )

    @staticmethod
    def _insert_run(cursor: Any, attempt: IngestionAttempt) -> None:
        cursor.execute(
            """
            insert into control.ingestion_runs(
              run_id,manifest_hash,idempotency_key,attempt,data_kind,status,started_at,
              finished_at,fetched_count,accepted_count,error_summary
            ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            on conflict (run_id) do nothing
            """,
            (
                attempt.run_id,
                attempt.manifest.manifest_hash,
                attempt.idempotency_key,
                attempt.attempt,
                attempt.data_kind,
                attempt.status,
                attempt.started_at,
                attempt.finished_at,
                1 if attempt.fetched is not None else 0,
                attempt.quality.accepted_count,
                attempt.error,
            ),
        )

    @staticmethod
    def _insert_raw_object(cursor: Any, attempt: IngestionAttempt, raw_key: StorageObjectKey) -> None:
        assert attempt.raw is not None
        cursor.execute(
            """
            insert into control.raw_objects(raw_hash,storage_bucket,storage_path,payload_size)
            values (%s,%s,%s,%s)
            on conflict (raw_hash) do nothing
            """,
            (attempt.raw.raw_hash, raw_key.bucket, raw_key.path, attempt.raw.payload_size),
        )
        cursor.execute(
            """
            select storage_bucket,storage_path,payload_size
            from control.raw_objects
            where raw_hash=%s
            """,
            (attempt.raw.raw_hash,),
        )
        row = cursor.fetchone()
        if row is not None:
            bucket, path, payload_size = _row_values(row, "storage_bucket", "storage_path", "payload_size")
            if bucket != raw_key.bucket or path != raw_key.path or int(payload_size) != attempt.raw.payload_size:
                raise AuthoritySinkError("existing raw object metadata does not match fetched bytes")

    @staticmethod
    def _insert_raw_capture(cursor: Any, attempt: IngestionAttempt) -> None:
        assert attempt.raw is not None
        capture_id = attempt.capture_id
        if capture_id is None:
            raise AuthoritySinkError("raw attempt is missing capture_id")
        cursor.execute(
            """
            insert into control.raw_captures(
              capture_id,raw_hash,run_id,manifest_hash,source_url,mime_type,
              fetched_at,known_at,http_status
            ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            on conflict (capture_id) do nothing
            """,
            (
                capture_id,
                attempt.raw.raw_hash,
                attempt.run_id,
                attempt.manifest.manifest_hash,
                attempt.raw.source_url,
                attempt.raw.mime_type,
                attempt.raw.fetched_at,
                attempt.raw.known_at,
                attempt.fetched.status_code if attempt.fetched is not None else None,
            ),
        )

    @staticmethod
    def _insert_receipts(cursor: Any, attempt: IngestionAttempt) -> None:
        assert attempt.raw is not None
        capture_id = attempt.capture_id
        if capture_id is None:
            raise AuthoritySinkError("raw attempt is missing capture_id")
        for record in attempt.records:
            if not attempt.promote and record.status is RecordStatus.ACCEPTED:
                continue
            cursor.execute(
                """
                insert into control.record_receipts(
                  record_hash,contract_version,capture_id,run_id,raw_hash,manifest_hash,
                  domain,record_schema_version,entity_key,payload_json,payload_hash,
                  known_at,status,quality_flags,rejection_reason,violations
                ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s)
                on conflict (record_hash) do nothing
                """,
                (
                    record.record_hash,
                    record.contract_version,
                    capture_id,
                    attempt.run_id,
                    attempt.raw.raw_hash,
                    attempt.manifest.manifest_hash,
                    record.domain.value,
                    record.record_schema_version,
                    record.entity_key,
                    record.payload_json,
                    record.payload_hash,
                    record.provenance.known_at,
                    record.status.value,
                    list(record.quality_flags),
                    record.rejection_reason,
                    list(record.violations),
                ),
            )

    @staticmethod
    def _insert_domain_rows(cursor: Any, attempt: IngestionAttempt) -> None:
        for record in attempt.records:
            if record.status is not RecordStatus.ACCEPTED:
                continue
            payload = record.payload
            if record.domain is RecordDomain.MARKET:
                cursor.execute(
                    """
                    insert into market.market_records(
                      record_hash,instrument_id,observed_at,metric,value,unit,known_at
                    ) values (%s,%s,%s,%s,%s,%s,%s)
                    on conflict (record_hash) do nothing
                    """,
                    (
                        record.record_hash,
                        payload["instrument_id"],
                        payload["observed_at"],
                        payload["metric"],
                        payload["value"],
                        payload["unit"],
                        record.provenance.known_at,
                    ),
                )
            elif record.domain is RecordDomain.FUNDAMENTAL:
                cursor.execute(
                    """
                    insert into market.fundamental_records(
                      record_hash,instrument_id,report_period,announced_at,metric,value,unit,known_at
                    ) values (%s,%s,%s,%s,%s,%s,%s,%s)
                    on conflict (record_hash) do nothing
                    """,
                    (
                        record.record_hash,
                        payload["instrument_id"],
                        payload["report_period"],
                        payload["announced_at"],
                        payload["metric"],
                        payload["value"],
                        payload["unit"],
                        record.provenance.known_at,
                    ),
                )
            elif record.domain is RecordDomain.DOCUMENT:
                document_key = _storage_key_from_uri(payload["storage_uri"], raw_hash=payload["content_hash"])
                cursor.execute(
                    """
                    insert into research.documents(
                      record_hash,document_id,instrument_id,document_type,published_at,
                      content_hash,storage_bucket,storage_path,known_at
                    ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    on conflict (record_hash) do nothing
                    """,
                    (
                        record.record_hash,
                        payload["document_id"],
                        payload["instrument_id"],
                        payload["document_type"],
                        payload["published_at"],
                        payload["content_hash"],
                        document_key.bucket,
                        document_key.path,
                        record.provenance.known_at,
                    ),
                )
            elif record.domain is RecordDomain.ESTIMATE:
                cursor.execute(
                    """
                    insert into research.estimates(
                      record_hash,estimate_id,instrument_id,broker,published_at,
                      fiscal_period,metric,value,unit,known_at
                    ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    on conflict (record_hash) do nothing
                    """,
                    (
                        record.record_hash,
                        payload["estimate_id"],
                        payload["instrument_id"],
                        payload["broker"],
                        payload["published_at"],
                        payload["fiscal_period"],
                        payload["metric"],
                        payload["value"],
                        payload["unit"],
                        record.provenance.known_at,
                    ),
                )
            elif record.domain is RecordDomain.EVENT:
                cursor.execute(
                    """
                    insert into research.events(
                      record_hash,event_id,instrument_id,event_type,occurred_at,
                      title,evidence_ids,known_at
                    ) values (%s,%s,%s,%s,%s,%s,%s,%s)
                    on conflict (record_hash) do nothing
                    """,
                    (
                        record.record_hash,
                        payload["event_id"],
                        payload["instrument_id"],
                        payload["event_type"],
                        payload["occurred_at"],
                        payload["title"],
                        list(payload["evidence_ids"]),
                        record.provenance.known_at,
                    ),
                )


def _storage_key_from_uri(storage_uri: str, *, raw_hash: str) -> StorageObjectKey:
    prefix = f"{RAW_BUCKET}/"
    if not isinstance(storage_uri, str) or not storage_uri.startswith(prefix):
        raise AuthoritySinkError("storage_uri must point at canonical-raw storage")
    key = StorageObjectKey(bucket=RAW_BUCKET, path=storage_uri[len(prefix):], raw_hash=raw_hash)
    key.validate()
    return key


def _row_values(row: Any, *fields: str) -> tuple[Any, ...]:
    if isinstance(row, dict):
        return tuple(row[field] for field in fields)
    return tuple(row[index] for index, _field in enumerate(fields))
