from __future__ import annotations

from pathlib import Path
import sqlite3

from .ingestion import FetchedPayload, FetchRequest


class SQLiteFetchCache:
    """Mutable local replay cache; deliberately cannot implement authority storage."""

    authority = False

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as connection:
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

    def put(self, source_key: str, request: FetchRequest, fetched: FetchedPayload) -> None:
        fetched.validate()
        with sqlite3.connect(self.path) as connection:
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

    def get(self, source_key: str, request: FetchRequest) -> FetchedPayload | None:
        with sqlite3.connect(self.path) as connection:
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
        with sqlite3.connect(self.path) as connection:
            return int(connection.execute("select count(*) from fetch_cache").fetchone()[0])
