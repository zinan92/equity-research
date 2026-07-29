from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Any

from .ingestion import FetchedPayload, FetchRequest


class SQLiteFetchCache:
    """Mutable local replay cache; deliberately cannot implement authority storage."""

    authority = False

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute(
                """
                create table if not exists fetch_cache (
                  cache_key text primary key,
                  source_key text not null,
                  domain text not null,
                  entity_key text not null,
                  body blob not null,
                  source_url text not null,
                  fetched_at text not null,
                  known_at text not null,
                  mime_type text not null,
                  status_code integer not null,
                  cached_at text not null default (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                )
                """
            )
            connection.commit()

    def put(self, source_key: str, request: FetchRequest, fetched: FetchedPayload) -> None:
        fetched.validate()
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute(
                """
                insert into fetch_cache(
                  cache_key,source_key,domain,entity_key,body,source_url,
                  fetched_at,known_at,mime_type,status_code
                ) values (?,?,?,?,?,?,?,?,?,?)
                on conflict(cache_key) do update set
                  body=excluded.body,
                  source_url=excluded.source_url,
                  fetched_at=excluded.fetched_at,
                  known_at=excluded.known_at,
                  mime_type=excluded.mime_type,
                  status_code=excluded.status_code,
                  cached_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
                """,
                (
                    request.cache_key(source_key),
                    source_key,
                    request.domain.value,
                    request.entity_key,
                    fetched.body,
                    fetched.source_url,
                    fetched.fetched_at,
                    fetched.known_at,
                    fetched.mime_type,
                    fetched.status_code,
                ),
            )
            connection.commit()

    def get(self, source_key: str, request: FetchRequest) -> FetchedPayload | None:
        with closing(sqlite3.connect(self.path)) as connection:
            row = connection.execute(
                """
                select body,source_url,fetched_at,known_at,mime_type,status_code
                from fetch_cache where cache_key=?
                """,
                (request.cache_key(source_key),),
            ).fetchone()
        if row is None:
            return None
        fetched = FetchedPayload(
            body=bytes(row[0]),
            source_url=row[1],
            fetched_at=row[2],
            known_at=row[3],
            mime_type=row[4],
            status_code=row[5],
            data_kind="cached",
        )
        fetched.validate()
        return fetched

    def count(self) -> int:
        with closing(sqlite3.connect(self.path)) as connection:
            return int(connection.execute("select count(*) from fetch_cache").fetchone()[0])


@dataclass(frozen=True)
class CachedReportTask:
    cache_key: str
    ticker: str
    snapshot_id: str
    evidence_manifest_hash: str
    report_export_hash: str
    artifact: dict[str, Any]
    cached_at: str


class SQLiteReportTaskCache:
    """Local replay cache for report tasks, never an authority store.

    A report task cache key is bound to ticker + immutable snapshot + accepted
    evidence manifest.  It cannot return a result for a different identity.
    """

    authority = False

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute(
                """
                create table if not exists report_task_cache (
                  cache_key text primary key,
                  ticker text not null,
                  snapshot_id text not null,
                  evidence_manifest_hash text not null,
                  report_export_hash text not null,
                  artifact_json text not null,
                  cached_at text not null
                )
                """
            )
            connection.commit()

    def put(
        self, *, cache_key: str, ticker: str, snapshot_id: str,
        evidence_manifest_hash: str, report_export_hash: str, artifact: dict[str, Any],
    ) -> CachedReportTask:
        cached_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        payload = json.dumps(artifact, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute(
                """
                insert into report_task_cache(
                  cache_key,ticker,snapshot_id,evidence_manifest_hash,report_export_hash,artifact_json,cached_at
                ) values (?,?,?,?,?,?,?)
                on conflict(cache_key) do update set
                  report_export_hash=excluded.report_export_hash,
                  artifact_json=excluded.artifact_json,cached_at=excluded.cached_at
                """,
                (cache_key, ticker.upper(), snapshot_id, evidence_manifest_hash, report_export_hash, payload, cached_at),
            )
            connection.commit()
        return CachedReportTask(cache_key, ticker.upper(), snapshot_id, evidence_manifest_hash, report_export_hash, dict(artifact), cached_at)

    def get(
        self, *, cache_key: str, ticker: str, snapshot_id: str, evidence_manifest_hash: str,
    ) -> CachedReportTask | None:
        with closing(sqlite3.connect(self.path)) as connection:
            row = connection.execute(
                """
                select cache_key,ticker,snapshot_id,evidence_manifest_hash,report_export_hash,artifact_json,cached_at
                from report_task_cache
                where cache_key=? and ticker=? and snapshot_id=? and evidence_manifest_hash=?
                """,
                (cache_key, ticker.upper(), snapshot_id, evidence_manifest_hash),
            ).fetchone()
        if row is None:
            return None
        artifact = json.loads(row[5])
        if not isinstance(artifact, dict):
            raise ValueError("cached report task artifact must be an object")
        return CachedReportTask(*row[:5], artifact, row[6])
