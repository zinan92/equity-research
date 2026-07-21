from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .contracts import SCHEMA_VERSION, SourceManifest, canonical_json, digest
from .schema import CORE_TABLES, SQLITE_DDL, schema_version_row


_CANONICAL_CONTRACTS = {
    "core_instruments": (
        ("instrument_id",),
        ("instrument_id", "ticker", "exchange", "board", "name", "industry", "listed_at", "delisted_at", "currency", "lot_size"),
    ),
    "core_trading_calendar": (
        ("exchange", "trade_date"),
        ("exchange", "trade_date", "is_open", "previous_open_date"),
    ),
    "core_instrument_status": (
        ("instrument_id", "trade_date"),
        ("instrument_id", "trade_date", "trading_status"),
    ),
    "core_corporate_actions": (
        ("action_id",),
        ("action_id", "instrument_id", "action_type", "ex_date", "announced_at", "version", "details_json"),
    ),
    "core_adjustment_factors": (
        ("instrument_id", "trade_date", "version"),
        ("instrument_id", "trade_date", "factor", "version"),
    ),
    "core_daily_bars": (
        ("instrument_id", "trade_date", "adjustment_version"),
        ("instrument_id", "trade_date", "open", "high", "low", "close", "volume", "amount", "adjustment_version", "quality_status"),
    ),
    "core_financial_facts": (
        ("fact_id",),
        ("fact_id", "instrument_id", "report_date", "announced_at", "revision", "metric_key", "metric_value", "unit", "quality_status"),
    ),
}


class QualityGateError(RuntimeError):
    def __init__(self, blockers: list[str]) -> None:
        self.blockers = blockers
        super().__init__("snapshot quality gate blocked: " + "; ".join(blockers))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_instant(value: str) -> str:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp must include timezone: {value}")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _rows(connection: sqlite3.Connection, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in connection.execute(query, params).fetchall()]


class _ManagedConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        handled = super().__exit__(exc_type, exc_value, traceback)
        self.close()
        return handled


class DataFoundation:
    """SQLite acceptance adapter for the canonical Postgres data contract.

    Consumers receive a snapshot-bound reader. Network access deliberately does
    not exist on this class, so analysis cannot refresh facts mid-run.
    """

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)

    def connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.db_path, factory=_ManagedConnection)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        installed_at = _now()
        with closing(self.connect()) as connection:
            connection.executescript(SQLITE_DDL)
            connection.execute(
                "INSERT OR IGNORE INTO core_schema_versions(version, installed_at) VALUES (?, ?)",
                schema_version_row(installed_at),
            )
            connection.commit()

    def register_source(self, manifest: SourceManifest) -> None:
        manifest.validate()
        self.initialize()
        with closing(self.connect()) as connection:
            connection.execute(
                """INSERT INTO core_source_registry (
                   source_key, domain_scope, authority_tier, provider_version, schema_version,
                   license_status, source_url, quality_flags_json, manifest_hash, active, created_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(source_key) DO NOTHING""",
                (
                    manifest.source_key, manifest.domain_scope, manifest.authority_tier,
                    manifest.provider_version, manifest.schema_version, manifest.license_status,
                    manifest.source_url, canonical_json(manifest.quality_flags), manifest.manifest_hash,
                    int(manifest.active), _now(),
                ),
            )
            identity = connection.execute(
                "SELECT domain_scope, authority_tier FROM core_source_registry WHERE source_key=?",
                (manifest.source_key,),
            ).fetchone()
            if not identity or identity["domain_scope"] != manifest.domain_scope or identity["authority_tier"] != manifest.authority_tier:
                raise ValueError("source identity cannot change domain_scope or authority_tier")
            connection.execute(
                """INSERT OR IGNORE INTO core_source_manifest_versions (
                   manifest_hash, source_key, provider_version, schema_version, license_status,
                   source_url, quality_flags_json, active, created_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    manifest.manifest_hash, manifest.source_key, manifest.provider_version,
                    manifest.schema_version, manifest.license_status, manifest.source_url,
                    canonical_json(manifest.quality_flags), int(manifest.active), _now(),
                ),
            )
            connection.commit()

    def ingest_fixture(self, payload: dict[str, Any], manifest: SourceManifest) -> dict[str, Any]:
        if not payload.get("fixture"):
            raise ValueError("acceptance loader only accepts payloads explicitly labelled fixture=true")
        self.register_source(manifest)
        payload = deepcopy(payload)
        payload["known_at"] = _canonical_instant(payload["known_at"])
        for row in payload["actions"]:
            row["announced_at"] = _canonical_instant(row["announced_at"])
        for row in payload["financials"]:
            row["announced_at"] = _canonical_instant(row["announced_at"])
        raw_json = canonical_json(payload)
        raw_hash = digest(payload)
        idempotency_key = digest({
            "source": manifest.source_key,
            "source_manifest_hash": manifest.manifest_hash,
            "raw_hash": raw_hash,
        })
        with closing(self.connect()) as connection:
            existing = connection.execute(
                """SELECT run_id, status, accepted_count FROM core_ingestion_runs
                   WHERE idempotency_key=? AND status='success' ORDER BY attempt DESC LIMIT 1""",
                (idempotency_key,),
            ).fetchone()
            if existing:
                return {"run_id": existing["run_id"], "status": existing["status"], "reused": True, "raw_hash": raw_hash}
            attempt = connection.execute(
                "SELECT COALESCE(MAX(attempt), 0) + 1 FROM core_ingestion_runs WHERE idempotency_key=?",
                (idempotency_key,),
            ).fetchone()[0]
            run_id = f"run_{idempotency_key[:16]}" + (f"_{attempt:02d}" if attempt > 1 else "")
            now = _now()
            fetched = sum(len(payload[key]) for key in ("instruments", "calendar", "statuses", "factors", "actions", "bars", "financials"))
            try:
                connection.execute(
                    """INSERT INTO core_ingestion_runs (
                       run_id, source_key, source_manifest_hash, data_kind, idempotency_key,
                       attempt, started_at, status
                       ) VALUES (?, ?, ?, 'fixture', ?, ?, ?, 'running')""",
                    (run_id, manifest.source_key, manifest.manifest_hash, idempotency_key, attempt, now),
                )
                connection.execute(
                    """INSERT INTO core_raw_objects (
                       raw_hash, run_id, source_key, source_manifest_hash, object_kind, storage_uri, fetched_at, known_at,
                       http_status, payload_size, payload_json, provider_version, schema_version, license_status
                       ) VALUES (?, ?, ?, ?, 'acceptance_fixture', ?, ?, ?, 200, ?, ?, ?, ?, ?)""",
                    (
                        raw_hash, run_id, manifest.source_key, manifest.manifest_hash, f"fixture://{raw_hash}", now,
                        payload["known_at"], len(raw_json.encode("utf-8")), raw_json, manifest.provider_version,
                        manifest.schema_version, manifest.license_status,
                    ),
                )
                accepted = self._insert_fixture_rows(
                    connection, payload, manifest.source_key, manifest.manifest_hash, run_id, raw_hash
                )
                if accepted != fetched:
                    raise RuntimeError(f"accepted row count mismatch: {accepted}/{fetched}")
                connection.execute(
                    """UPDATE core_ingestion_runs SET finished_at=?, status='success',
                       fetched_count=?, accepted_count=? WHERE run_id=?""",
                    (_now(), fetched, accepted, run_id),
                )
                connection.commit()
            except Exception as exc:
                connection.rollback()
                connection.execute(
                    """INSERT INTO core_ingestion_runs (
                       run_id, source_key, source_manifest_hash, data_kind, idempotency_key, attempt,
                       started_at, finished_at, status,
                       fetched_count, accepted_count, error_summary
                       ) VALUES (?, ?, ?, 'fixture', ?, ?, ?, ?, 'failed', ?, 0, ?)""",
                    (
                        run_id, manifest.source_key, manifest.manifest_hash, idempotency_key,
                        attempt, now, _now(), fetched, f"{type(exc).__name__}: {exc}",
                    ),
                )
                connection.commit()
                raise RuntimeError(f"fixture ingestion failed closed: {exc}") from exc
        return {"run_id": run_id, "status": "success", "reused": False, "raw_hash": raw_hash}

    @staticmethod
    def _accept_canonical(
        connection: sqlite3.Connection,
        *,
        table: str,
        values: dict[str, Any],
        key_columns: tuple[str, ...],
        business_columns: tuple[str, ...],
        source_key: str,
        source_manifest_hash: str,
        run_id: str,
        raw_hash: str,
    ) -> int:
        columns = tuple(values)
        placeholders = ",".join("?" for _ in columns)
        connection.execute(
            f"INSERT OR IGNORE INTO {table} ({','.join(columns)}) VALUES ({placeholders})",
            tuple(values[column] for column in columns),
        )
        where = " AND ".join(f"{column}=?" for column in key_columns)
        existing = connection.execute(
            f"SELECT {','.join(business_columns)} FROM {table} WHERE {where}",
            tuple(values[column] for column in key_columns),
        ).fetchone()
        expected = {column: values[column] for column in business_columns}
        if not existing or dict(existing) != expected:
            raise RuntimeError(f"canonical conflict for {table} {canonical_json({column: values[column] for column in key_columns})}")
        entity_key = canonical_json({column: values[column] for column in key_columns})
        canonical_hash = digest(expected)
        observation_id = digest({"run": run_id, "table": table, "key": entity_key})[:32]
        connection.execute(
            """INSERT INTO core_source_observations (
               observation_id, run_id, source_key, source_manifest_hash, entity_type,
               entity_key, canonical_hash, raw_hash, status, created_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'accepted', ?)""",
            (
                observation_id, run_id, source_key, source_manifest_hash, table,
                entity_key, canonical_hash, raw_hash, _now(),
            ),
        )
        return 1

    @classmethod
    def _insert_fixture_rows(
        cls,
        connection: sqlite3.Connection,
        payload: dict[str, Any],
        source_key: str,
        source_manifest_hash: str,
        run_id: str,
        raw_hash: str,
    ) -> int:
        known_at = payload["known_at"]
        accepted = 0
        for row in payload["instruments"]:
            values = {
                "instrument_id": row["instrument_id"], "ticker": row["ticker"], "exchange": row["exchange"],
                "board": row["board"], "name": row["name"], "industry": row["industry"],
                "listed_at": row["listed_at"], "delisted_at": None, "currency": "CNY", "lot_size": 100,
                "source_key": source_key, "known_at": known_at, "raw_hash": raw_hash,
            }
            accepted += cls._accept_canonical(
                connection, table="core_instruments", values=values, key_columns=("instrument_id",),
                business_columns=("instrument_id", "ticker", "exchange", "board", "name", "industry", "listed_at", "delisted_at", "currency", "lot_size"),
                source_key=source_key, source_manifest_hash=source_manifest_hash, run_id=run_id, raw_hash=raw_hash,
            )
        for row in payload["calendar"]:
            values = {**row, "source_key": source_key, "known_at": known_at, "raw_hash": raw_hash}
            accepted += cls._accept_canonical(
                connection, table="core_trading_calendar", values=values, key_columns=("exchange", "trade_date"),
                business_columns=("exchange", "trade_date", "is_open", "previous_open_date"),
                source_key=source_key, source_manifest_hash=source_manifest_hash, run_id=run_id, raw_hash=raw_hash,
            )
        for row in payload["statuses"]:
            values = {**row, "source_key": source_key, "run_id": run_id, "known_at": known_at, "raw_hash": raw_hash}
            accepted += cls._accept_canonical(
                connection, table="core_instrument_status", values=values, key_columns=("instrument_id", "trade_date"),
                business_columns=("instrument_id", "trade_date", "trading_status"),
                source_key=source_key, source_manifest_hash=source_manifest_hash, run_id=run_id, raw_hash=raw_hash,
            )
        for row in payload["actions"]:
            values = {
                "action_id": row["action_id"], "instrument_id": row["instrument_id"], "action_type": row["action_type"],
                "ex_date": row["ex_date"], "announced_at": row["announced_at"], "version": row["version"],
                "details_json": canonical_json(row["details"]), "source_key": source_key, "run_id": run_id,
                "known_at": known_at, "raw_hash": raw_hash,
            }
            accepted += cls._accept_canonical(
                connection, table="core_corporate_actions", values=values, key_columns=("action_id",),
                business_columns=("action_id", "instrument_id", "action_type", "ex_date", "announced_at", "version", "details_json"),
                source_key=source_key, source_manifest_hash=source_manifest_hash, run_id=run_id, raw_hash=raw_hash,
            )
        for row in payload["factors"]:
            values = {**row, "source_key": source_key, "run_id": run_id, "known_at": known_at, "raw_hash": raw_hash}
            accepted += cls._accept_canonical(
                connection, table="core_adjustment_factors", values=values,
                key_columns=("instrument_id", "trade_date", "version"),
                business_columns=("instrument_id", "trade_date", "factor", "version"),
                source_key=source_key, source_manifest_hash=source_manifest_hash, run_id=run_id, raw_hash=raw_hash,
            )
        for row in payload["bars"]:
            values = {**row, "source_key": source_key, "run_id": run_id, "known_at": known_at, "raw_hash": raw_hash, "quality_status": "accepted"}
            accepted += cls._accept_canonical(
                connection, table="core_daily_bars", values=values,
                key_columns=("instrument_id", "trade_date", "adjustment_version"),
                business_columns=("instrument_id", "trade_date", "open", "high", "low", "close", "volume", "amount", "adjustment_version", "quality_status"),
                source_key=source_key, source_manifest_hash=source_manifest_hash, run_id=run_id, raw_hash=raw_hash,
            )
        for row in payload["financials"]:
            values = {**row, "source_key": source_key, "run_id": run_id, "known_at": known_at, "raw_hash": raw_hash, "quality_status": "accepted"}
            accepted += cls._accept_canonical(
                connection, table="core_financial_facts", values=values, key_columns=("fact_id",),
                business_columns=("fact_id", "instrument_id", "report_date", "announced_at", "revision", "metric_key", "metric_value", "unit", "quality_status"),
                source_key=source_key, source_manifest_hash=source_manifest_hash, run_id=run_id, raw_hash=raw_hash,
            )
        return accepted

    @staticmethod
    def _canonical_reconciliation_gaps(
        connection: sqlite3.Connection, *, as_of: str, known_at: str
    ) -> list[str]:
        gaps: list[str] = []
        for table, (key_columns, business_columns) in _CANONICAL_CONTRACTS.items():
            columns = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
            predicates = ["known_at<=?"] if "known_at" in columns else []
            params: list[Any] = [known_at] if predicates else []
            if "trade_date" in columns:
                predicates.append("trade_date<=?")
                params.append(as_of)
            if "report_date" in columns:
                predicates.append("report_date<=?")
                params.append(as_of)
            if "announced_at" in columns:
                predicates.append("announced_at<=?")
                params.append(known_at)
            if "quality_status" in columns:
                predicates.append("quality_status='accepted'")
            where = " WHERE " + " AND ".join(predicates) if predicates else ""
            for row in _rows(connection, f"SELECT * FROM {table}{where}", tuple(params)):
                entity_key = canonical_json({column: row[column] for column in key_columns})
                canonical_hash = digest({column: row[column] for column in business_columns})
                observation = connection.execute(
                    """SELECT raw.raw_hash, raw.payload_json, raw.provider_version, raw.schema_version,
                              raw.license_status, v.provider_version AS manifest_provider_version,
                              v.schema_version AS manifest_schema_version,
                              v.license_status AS manifest_license_status
                       FROM core_source_observations o
                       JOIN core_ingestion_runs r ON r.run_id=o.run_id AND r.status='success'
                       JOIN core_raw_objects raw ON raw.raw_hash=o.raw_hash
                           AND raw.run_id=o.run_id AND raw.source_key=o.source_key
                           AND raw.source_manifest_hash=o.source_manifest_hash
                       JOIN core_source_manifest_versions v ON v.manifest_hash=o.source_manifest_hash
                           AND v.source_key=o.source_key
                       WHERE o.entity_type=? AND o.entity_key=? AND o.canonical_hash=?
                           AND o.status='accepted' AND raw.known_at<=?
                       LIMIT 1""",
                    (table, entity_key, canonical_hash, known_at),
                ).fetchone()
                observation_valid = False
                if observation:
                    try:
                        observation_valid = (
                            digest(json.loads(observation["payload_json"])) == observation["raw_hash"]
                            and observation["provider_version"] == observation["manifest_provider_version"]
                            and observation["schema_version"] == observation["manifest_schema_version"]
                            and observation["license_status"] == observation["manifest_license_status"]
                        )
                    except (TypeError, ValueError, json.JSONDecodeError):
                        observation_valid = False
                if not observation_valid:
                    gaps.append(f"{table}:{entity_key}")
        return gaps

    @staticmethod
    def _quality_state_digest(
        connection: sqlite3.Connection, *, run_id: str, as_of: str, known_at: str
    ) -> str:
        state: dict[str, Any] = {}
        for table in _CANONICAL_CONTRACTS:
            ordered_columns = [row["name"] for row in connection.execute(f"PRAGMA table_info({table})")]
            columns = set(ordered_columns)
            predicates = ["known_at<=?"] if "known_at" in columns else []
            params: list[Any] = [known_at] if predicates else []
            if "trade_date" in columns:
                predicates.append("trade_date<=?")
                params.append(as_of)
            if "report_date" in columns:
                predicates.append("report_date<=?")
                params.append(as_of)
            if "announced_at" in columns:
                predicates.append("announced_at<=?")
                params.append(known_at)
            where = " WHERE " + " AND ".join(predicates) if predicates else ""
            state[table] = _rows(
                connection,
                f"SELECT * FROM {table}{where} ORDER BY {','.join(ordered_columns)}",
                tuple(params),
            )
        for table in ("core_ingestion_runs", "core_raw_objects", "core_source_observations"):
            ordered_columns = [row["name"] for row in connection.execute(f"PRAGMA table_info({table})")]
            state[table] = _rows(
                connection,
                f"SELECT * FROM {table} WHERE run_id=? ORDER BY {','.join(ordered_columns)}",
                (run_id,),
            )
        run = connection.execute(
            "SELECT source_key, source_manifest_hash FROM core_ingestion_runs WHERE run_id=?", (run_id,)
        ).fetchone()
        if run:
            state["core_source_registry"] = _rows(
                connection, "SELECT * FROM core_source_registry WHERE source_key=?", (run["source_key"],)
            )
            state["core_source_manifest_versions"] = _rows(
                connection, "SELECT * FROM core_source_manifest_versions WHERE manifest_hash=?",
                (run["source_manifest_hash"],),
            )
        return digest(state)

    def quality_evaluation(self, run_id: str, *, as_of: str, known_at: str) -> dict[str, Any]:
        known_at = _canonical_instant(known_at)
        blockers: list[str] = []
        with closing(self.connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            exchanges = {
                row["exchange"] for row in _rows(
                    connection,
                    "SELECT DISTINCT exchange FROM core_instruments WHERE known_at<=?",
                    (known_at,),
                )
            }
            open_exchanges = {
                row["exchange"] for row in _rows(
                    connection,
                    "SELECT exchange FROM core_trading_calendar WHERE trade_date=? AND is_open=1 AND known_at<=?",
                    (as_of, known_at),
                )
            }
            if exchanges - open_exchanges:
                blockers.append("missing trading calendar: " + ",".join(sorted(exchanges - open_exchanges)))
            missing_status = _rows(
                connection,
                """SELECT i.ticker FROM core_instruments i
                   LEFT JOIN core_instrument_status s ON s.instrument_id=i.instrument_id
                       AND s.trade_date=? AND s.known_at<=?
                   WHERE i.known_at<=? AND s.instrument_id IS NULL ORDER BY i.ticker""",
                (as_of, known_at, known_at),
            )
            if missing_status:
                blockers.append("instruments missing trading status: " + ",".join(row["ticker"] for row in missing_status))
            active_missing_bars = _rows(
                connection,
                """SELECT i.ticker FROM core_instruments i
                   JOIN core_instrument_status s ON s.instrument_id=i.instrument_id
                       AND s.trade_date=? AND s.known_at<=?
                   LEFT JOIN core_daily_bars b ON b.instrument_id=i.instrument_id AND b.trade_date=?
                       AND b.known_at<=? AND b.quality_status='accepted'
                   WHERE s.trading_status='normal' AND b.instrument_id IS NULL ORDER BY i.ticker""",
                (as_of, known_at, as_of, known_at),
            )
            if active_missing_bars:
                blockers.append("normal instruments missing bars: " + ",".join(row["ticker"] for row in active_missing_bars))
            missing_factors = _rows(
                connection,
                """SELECT i.ticker FROM core_daily_bars b JOIN core_instruments i ON i.instrument_id=b.instrument_id
                   LEFT JOIN core_adjustment_factors f ON f.instrument_id=b.instrument_id AND f.trade_date=b.trade_date
                       AND f.version=b.adjustment_version AND f.known_at<=?
                   WHERE b.trade_date=? AND b.known_at<=? AND b.quality_status='accepted'
                       AND f.instrument_id IS NULL ORDER BY i.ticker""",
                (known_at, as_of, known_at),
            )
            if missing_factors:
                blockers.append("bars missing adjustment version: " + ",".join(row["ticker"] for row in missing_factors))
            missing_actions = _rows(
                connection,
                """SELECT i.ticker FROM core_adjustment_factors f
                   JOIN core_instruments i ON i.instrument_id=f.instrument_id
                   LEFT JOIN core_corporate_actions a ON a.instrument_id=f.instrument_id
                       AND a.ex_date=f.trade_date AND a.version=f.version
                       AND a.known_at<=? AND a.announced_at<=?
                   WHERE f.trade_date=? AND f.known_at<=? AND ABS(f.factor-1.0)>0.0000001
                       AND a.action_id IS NULL ORDER BY i.ticker""",
                (known_at, known_at, as_of, known_at),
            )
            if missing_actions:
                blockers.append("adjusted instruments missing corporate action version: " + ",".join(row["ticker"] for row in missing_actions))
            future_financials = _rows(
                connection,
                """SELECT fact_id FROM core_financial_facts
                   WHERE report_date<=? AND known_at<=? AND announced_at>?""",
                (as_of, known_at, known_at),
            )
            if future_financials:
                blockers.append(f"future-visible financial facts: {len(future_financials)}")
            future_actions = _rows(
                connection,
                """SELECT action_id FROM core_corporate_actions
                   WHERE known_at<=? AND announced_at>?""",
                (known_at, known_at),
            )
            if future_actions:
                blockers.append(f"future-visible corporate actions: {len(future_actions)}")
            missing_provenance = connection.execute(
                """SELECT COUNT(*) FROM core_source_observations o
                   JOIN core_ingestion_runs r ON r.run_id=o.run_id
                   JOIN core_raw_objects raw ON raw.raw_hash=o.raw_hash AND raw.run_id=o.run_id
                       AND raw.source_key=o.source_key AND raw.source_manifest_hash=o.source_manifest_hash
                   LEFT JOIN core_source_manifest_versions v
                       ON v.manifest_hash=o.source_manifest_hash AND v.source_key=o.source_key
                   WHERE o.run_id=? AND (
                       o.status!='accepted' OR r.status!='success' OR v.manifest_hash IS NULL
                       OR raw.provider_version!=v.provider_version
                       OR raw.schema_version!=v.schema_version
                       OR raw.license_status!=v.license_status
                   )""",
                (run_id,),
            ).fetchone()[0]
            if missing_provenance:
                blockers.append(f"rows missing provenance: {missing_provenance}")
            invalid_raw = 0
            for raw in _rows(connection, "SELECT raw_hash, payload_json FROM core_raw_objects WHERE run_id=?", (run_id,)):
                try:
                    invalid_raw += int(digest(json.loads(raw["payload_json"])) != raw["raw_hash"])
                except (TypeError, ValueError, json.JSONDecodeError):
                    invalid_raw += 1
            if invalid_raw:
                blockers.append(f"raw payload hash mismatch: {invalid_raw}")
            run = connection.execute(
                "SELECT status, data_kind, fetched_count, accepted_count FROM core_ingestion_runs WHERE run_id=?",
                (run_id,),
            ).fetchone()
            if not run or run["status"] != "success":
                blockers.append("ingestion run is not successful")
            elif connection.execute(
                "SELECT COUNT(*) FROM core_source_observations WHERE run_id=? AND status='accepted'",
                (run_id,),
            ).fetchone()[0] != run["accepted_count"] or run["accepted_count"] != run["fetched_count"]:
                blockers.append("ingestion receipt does not match accepted observations")
            raw_future = connection.execute(
                "SELECT COUNT(*) FROM core_raw_objects WHERE run_id=? AND known_at>?",
                (run_id, known_at),
            ).fetchone()[0]
            if raw_future:
                blockers.append(f"raw object exceeds knowledge cutoff: {raw_future}")
            rejected_rows = connection.execute(
                """SELECT COUNT(*) FROM (
                     SELECT quality_status, known_at, trade_date FROM core_daily_bars
                     UNION ALL SELECT quality_status, known_at, report_date FROM core_financial_facts
                   ) WHERE known_at<=? AND trade_date<=? AND quality_status!='accepted'""",
                (known_at, as_of),
            ).fetchone()[0]
            if rejected_rows:
                blockers.append(f"non-accepted canonical rows selected: {rejected_rows}")
            reconciliation_gaps = self._canonical_reconciliation_gaps(
                connection, as_of=as_of, known_at=known_at
            )
            if reconciliation_gaps:
                blockers.append(
                    "canonical rows missing matching source observation: "
                    + ",".join(reconciliation_gaps[:6])
                )
            checked_at = _now()
            checks = {
                "trading_calendar": not any(item.startswith("missing trading calendar") for item in blockers),
                "status_coverage": not any(item.startswith("instruments missing trading status") for item in blockers),
                "bar_coverage": not any(item.startswith("normal instruments") for item in blockers),
                "adjustment_version": not any(item.startswith("bars missing adjustment") for item in blockers),
                "corporate_action_version": not any(item.startswith("adjusted instruments") for item in blockers),
                "point_in_time": not any(item.startswith("future-visible") for item in blockers),
                "provenance": not any(item.startswith("rows missing provenance") for item in blockers),
                "raw_integrity": not any(item.startswith("raw payload hash") for item in blockers),
                "ingestion_run": not any(item.startswith("ingestion run") for item in blockers),
                "ingestion_receipt": not any(item.startswith("ingestion receipt") for item in blockers),
                "raw_cutoff": not any(item.startswith("raw object") for item in blockers),
                "accepted_rows_only": not any(item.startswith("non-accepted") for item in blockers),
                "canonical_reconciliation": not any(item.startswith("canonical rows") for item in blockers),
            }
            state_digest = self._quality_state_digest(
                connection, run_id=run_id, as_of=as_of, known_at=known_at
            )
            evaluation_id = digest({
                "run": run_id, "as_of": as_of, "known_at": known_at,
                "schema_version": SCHEMA_VERSION, "state_digest": state_digest,
                "blockers": blockers,
            })[:32]
            results = []
            for key, passed in checks.items():
                relevant = [item for item in blockers if {
                    "trading_calendar": item.startswith("missing trading calendar"),
                    "status_coverage": item.startswith("instruments missing trading status"),
                    "bar_coverage": item.startswith("normal instruments"),
                    "adjustment_version": item.startswith("bars missing adjustment"),
                    "corporate_action_version": item.startswith("adjusted instruments"),
                    "point_in_time": item.startswith("future-visible"),
                    "provenance": item.startswith("rows missing provenance"),
                    "raw_integrity": item.startswith("raw payload hash"),
                    "ingestion_run": item.startswith("ingestion run"),
                    "ingestion_receipt": item.startswith("ingestion receipt"),
                    "raw_cutoff": item.startswith("raw object"),
                    "accepted_rows_only": item.startswith("non-accepted"),
                    "canonical_reconciliation": item.startswith("canonical rows"),
                }[key]]
                detail = "contract satisfied" if passed else "; ".join(relevant)
                result = {"check_key": key, "status": "passed" if passed else "blocked", "detail": detail}
                results.append(result)
                quality_id = digest({"evaluation": evaluation_id, **result})[:32]
                connection.execute(
                    """INSERT INTO core_quality_results (
                       quality_id, evaluation_id, run_id, check_key, entity_key, status, detail, checked_at
                       ) VALUES (?, ?, ?, ?, 'foundation', ?, ?, ?)
                       ON CONFLICT(quality_id) DO NOTHING""",
                    (quality_id, evaluation_id, run_id, key, result["status"], detail, checked_at),
                )
                stored = connection.execute(
                    "SELECT status, detail FROM core_quality_results WHERE quality_id=?",
                    (quality_id,),
                ).fetchone()
                if not stored or dict(stored) != {"status": result["status"], "detail": detail}:
                    raise RuntimeError("quality evaluation identity changed for the same inputs")
            connection.commit()
        return {
            "evaluation_id": evaluation_id,
            "quality_digest": digest(sorted(results, key=lambda item: item["check_key"])),
            "state_digest": state_digest,
            "blockers": blockers,
            "results": results,
            "known_at": known_at,
            "data_kind": run["data_kind"] if run else None,
        }

    def quality_gate(self, run_id: str, *, as_of: str, known_at: str) -> list[str]:
        return self.quality_evaluation(run_id, as_of=as_of, known_at=known_at)["blockers"]

    def create_snapshot(
        self,
        run_id: str,
        *,
        as_of: str,
        known_at: str,
        snapshot_kind: str | None = None,
        model_version: str = "data-core-only",
        dependency_lock_hash: str = "stdlib-only",
        random_seed: int = 0,
    ) -> dict[str, Any]:
        evaluation = self.quality_evaluation(run_id, as_of=as_of, known_at=known_at)
        trigger_kind = evaluation["data_kind"]
        if trigger_kind not in {"fixture", "cached", "real"}:
            raise QualityGateError(["snapshot kind is not bound to a valid ingestion run"])
        requested_kind = snapshot_kind
        known_at = evaluation["known_at"]
        if evaluation["blockers"]:
            raise QualityGateError(evaluation["blockers"])
        tables = (
            "core_instruments", "core_trading_calendar", "core_instrument_status",
            "core_corporate_actions", "core_adjustment_factors", "core_daily_bars",
            "core_financial_facts", "core_intelligence_items",
        )
        with closing(self.connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            locked_state_digest = self._quality_state_digest(
                connection, run_id=run_id, as_of=as_of, known_at=known_at
            )
            if locked_state_digest != evaluation["state_digest"]:
                connection.rollback()
                raise QualityGateError(["canonical state changed after quality evaluation"])
            items: list[dict[str, str]] = []
            frozen_rows: list[tuple[str, str, str, str]] = []
            selected_raw_hashes: set[str] = set()
            for table in tables:
                columns = [row["name"] for row in connection.execute(f"PRAGMA table_info({table})")]
                order_by = ",".join(f"t.{column}" for column in columns)
                predicates = ["t.known_at <= ?"] if "known_at" in columns else []
                params: list[Any] = [known_at] if predicates else []
                if "trade_date" in columns:
                    predicates.append("t.trade_date <= ?")
                    params.append(as_of)
                if "report_date" in columns:
                    predicates.append("t.report_date <= ?")
                    params.append(as_of)
                if "announced_at" in columns:
                    predicates.append("t.announced_at <= ?")
                    params.append(known_at)
                if "quality_status" in columns:
                    predicates.append("t.quality_status = 'accepted'")
                from_clause = f"{table} t"
                where = " WHERE " + " AND ".join(predicates) if predicates else ""
                for index, row in enumerate(_rows(connection, f"SELECT t.* FROM {from_clause}{where} ORDER BY {order_by}", tuple(params))):
                    row_key = f"{index:08d}"
                    row_hash = digest(row)
                    items.append({"table": table, "key": row_key, "hash": row_hash})
                    frozen_rows.append((table, row_key, row_hash, canonical_json(row)))
                    if row.get("raw_hash"):
                        selected_raw_hashes.add(row["raw_hash"])

            def freeze_rows(table: str, rows: list[dict[str, Any]]) -> None:
                for index, row in enumerate(rows):
                    row_key = f"{index:08d}"
                    row_hash = digest(row)
                    items.append({"table": table, "key": row_key, "hash": row_hash})
                    frozen_rows.append((table, row_key, row_hash, canonical_json(row)))

            if not selected_raw_hashes:
                raise QualityGateError(["snapshot contains no canonical rows"])
            placeholders = ",".join("?" for _ in selected_raw_hashes)
            raw_rows = _rows(
                connection,
                f"SELECT * FROM core_raw_objects WHERE raw_hash IN ({placeholders}) ORDER BY raw_hash",
                tuple(sorted(selected_raw_hashes)),
            )
            if {row["raw_hash"] for row in raw_rows} != selected_raw_hashes:
                raise QualityGateError(["selected canonical rows are missing frozen raw objects"])
            lineage_run_ids = sorted({row["run_id"] for row in raw_rows} | {run_id})
            run_placeholders = ",".join("?" for _ in lineage_run_ids)
            run_rows = _rows(
                connection,
                f"SELECT * FROM core_ingestion_runs WHERE run_id IN ({run_placeholders}) ORDER BY run_id",
                tuple(lineage_run_ids),
            )
            lineage_kinds = {row["data_kind"] for row in run_rows}
            if lineage_kinds != {trigger_kind}:
                raise QualityGateError([
                    "snapshot lineage mixes trust kinds: " + ",".join(sorted(lineage_kinds | {trigger_kind}))
                ])
            if requested_kind is not None and requested_kind != trigger_kind:
                raise ValueError(f"snapshot kind cannot promote {trigger_kind} run to {requested_kind}")
            snapshot_kind = trigger_kind
            manifest_hashes = sorted({row["source_manifest_hash"] for row in run_rows})
            source_keys = sorted({row["source_key"] for row in run_rows})
            freeze_rows("core_source_registry", _rows(
                connection,
                f"SELECT * FROM core_source_registry WHERE source_key IN ({','.join('?' for _ in source_keys)}) ORDER BY source_key",
                tuple(source_keys),
            ))
            freeze_rows("core_source_manifest_versions", _rows(
                connection,
                f"SELECT * FROM core_source_manifest_versions WHERE manifest_hash IN ({','.join('?' for _ in manifest_hashes)}) ORDER BY manifest_hash",
                tuple(manifest_hashes),
            ))
            freeze_rows("core_ingestion_runs", run_rows)
            freeze_rows("core_raw_objects", raw_rows)
            observation_rows = _rows(
                connection,
                f"""SELECT * FROM core_source_observations
                    WHERE raw_hash IN ({placeholders}) AND status='accepted'
                    ORDER BY run_id, entity_type, entity_key""",
                tuple(sorted(selected_raw_hashes)),
            )
            observed_raw_hashes = {row["raw_hash"] for row in observation_rows}
            if observed_raw_hashes != selected_raw_hashes:
                raise QualityGateError(["selected canonical rows are missing frozen source observations"])
            freeze_rows("core_source_observations", observation_rows)
            freeze_rows("core_quality_results", _rows(
                connection,
                "SELECT * FROM core_quality_results WHERE evaluation_id=? ORDER BY check_key",
                (evaluation["evaluation_id"],),
            ))
            lineage_run_ids = [
                row["run_id"] for row in _rows(
                    connection,
                    f"SELECT run_id FROM core_ingestion_runs WHERE run_id IN ({run_placeholders}) ORDER BY run_id",
                    tuple(lineage_run_ids),
                )
            ]
            frozen_state_items = sorted(
                [
                    {"table": table, "key": row_key, "hash": row_hash}
                    for table, row_key, row_hash, _ in frozen_rows
                    if table != "core_quality_results"
                ],
                key=lambda item: (item["table"], item["key"]),
            )
            frozen_state_digest = digest(frozen_state_items)
            manifest = {
                "snapshot_kind": snapshot_kind,
                "as_of": as_of,
                "known_at": known_at,
                "schema_version": SCHEMA_VERSION,
                "model_version": model_version,
                "dependency_lock_hash": dependency_lock_hash,
                "random_seed": random_seed,
                "run_id": run_id,
                "lineage_run_ids": lineage_run_ids,
                "quality_evaluation_id": evaluation["evaluation_id"],
                "quality_digest": evaluation["quality_digest"],
                "quality_state_digest": evaluation["state_digest"],
                "frozen_state_digest": frozen_state_digest,
                "items": items,
            }
            manifest_hash = digest(manifest)
            snapshot_id = f"core_{snapshot_kind}_{manifest_hash[:16]}"
            connection.execute(
                """INSERT OR IGNORE INTO core_snapshot_manifests (
                   snapshot_id, snapshot_kind, as_of, known_at, schema_version, model_version,
                   dependency_lock_hash, random_seed, quality_status, quality_evaluation_id,
                   quality_digest, manifest_json, manifest_hash, created_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'passed', ?, ?, ?, ?, ?)""",
                (
                    snapshot_id, snapshot_kind, as_of, known_at, SCHEMA_VERSION, model_version,
                    dependency_lock_hash, random_seed, evaluation["evaluation_id"],
                    evaluation["quality_digest"], canonical_json(manifest), manifest_hash, _now(),
                ),
            )
            connection.executemany(
                "INSERT OR IGNORE INTO core_snapshot_items VALUES (?, ?, ?, ?, ?)",
                [(snapshot_id, table, row_key, row_hash, row_json) for table, row_key, row_hash, row_json in frozen_rows],
            )
            connection.commit()
        return {"snapshot_id": snapshot_id, "manifest_hash": manifest_hash, "item_count": len(items), "snapshot_kind": snapshot_kind}

    def replay_digest(self, snapshot_id: str) -> str:
        with closing(self.connect()) as connection:
            manifest = connection.execute(
                "SELECT manifest_json, manifest_hash FROM core_snapshot_manifests WHERE snapshot_id=? AND quality_status='passed'",
                (snapshot_id,),
            ).fetchone()
            if not manifest:
                raise KeyError(snapshot_id)
            parsed = json.loads(manifest["manifest_json"])
            if digest(parsed) != manifest["manifest_hash"]:
                raise RuntimeError("snapshot manifest hash mismatch")
            stored_rows = _rows(
                connection,
                """SELECT table_name AS 'table', row_key AS 'key', row_hash AS 'hash', row_json
                   FROM core_snapshot_items WHERE snapshot_id=? ORDER BY table_name, row_key""",
                (snapshot_id,),
            )
            for row in stored_rows:
                if digest(json.loads(row["row_json"])) != row["hash"]:
                    raise RuntimeError("snapshot frozen row hash mismatch")
            stored_items = [{key: row[key] for key in ("table", "key", "hash")} for row in stored_rows]
            expected = sorted(parsed["items"], key=lambda row: (row["table"], row["key"]))
            if stored_items != expected:
                raise RuntimeError("snapshot item manifest mismatch")
            frozen_state_digest = digest([
                item for item in stored_items if item["table"] != "core_quality_results"
            ])
            if frozen_state_digest != parsed.get("frozen_state_digest"):
                raise RuntimeError("snapshot frozen state digest mismatch")
            frozen_quality_results = [
                json.loads(row["row_json"]) for row in stored_rows
                if row["table"] == "core_quality_results"
            ]
            quality_results = [
                {
                    "check_key": row["check_key"],
                    "status": row["status"],
                    "detail": row["detail"],
                }
                for row in frozen_quality_results
            ]
            if digest(quality_results) != parsed.get("quality_digest"):
                raise RuntimeError("snapshot quality evaluation digest mismatch")
            return digest({"manifest_hash": manifest["manifest_hash"], "items": stored_items})

    def export_bundle(self) -> dict[str, Any]:
        self.initialize()
        with closing(self.connect()) as connection:
            bundle: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "tables": {}}
            for table in CORE_TABLES:
                columns = [row["name"] for row in connection.execute(f"PRAGMA table_info({table})")]
                bundle["tables"][table] = _rows(connection, f"SELECT * FROM {table} ORDER BY {','.join(columns)}")
            bundle["bundle_hash"] = digest(bundle)
            return bundle

    def import_bundle(self, bundle: dict[str, Any]) -> None:
        expected = bundle.get("bundle_hash")
        unsigned = {key: value for key, value in bundle.items() if key != "bundle_hash"}
        if bundle.get("schema_version") != SCHEMA_VERSION or digest(unsigned) != expected:
            raise ValueError("invalid or incompatible canonical export")
        self.initialize()
        with closing(self.connect()) as connection:
            nonempty = [
                table for table in CORE_TABLES
                if table != "core_schema_versions"
                and connection.execute(f"SELECT EXISTS(SELECT 1 FROM {table} LIMIT 1)").fetchone()[0]
            ]
            if nonempty:
                raise ValueError("canonical import target must be empty: " + ",".join(nonempty))
            connection.execute("PRAGMA defer_foreign_keys = ON")
            connection.execute("DELETE FROM core_schema_versions")
            for table in CORE_TABLES:
                rows = bundle["tables"].get(table, [])
                if not rows:
                    continue
                columns = list(rows[0])
                placeholders = ",".join("?" for _ in columns)
                connection.executemany(
                    f"INSERT OR IGNORE INTO {table} ({','.join(columns)}) VALUES ({placeholders})",
                    [[row[column] for column in columns] for row in rows],
                )
            connection.commit()
        restored = self.export_bundle()
        if restored["bundle_hash"] != expected:
            raise RuntimeError("canonical import did not reproduce source bundle exactly")

    def coverage_report(self) -> dict[str, Any]:
        with closing(self.connect()) as connection:
            rows = _rows(connection, "SELECT exchange, board, industry, COUNT(*) AS count FROM core_instruments GROUP BY exchange, board, industry ORDER BY exchange, board, industry")
            cases = {
                "suspended": connection.execute("SELECT COUNT(*) FROM core_instrument_status WHERE trading_status='suspended'").fetchone()[0],
                "corporate_action": connection.execute("SELECT COUNT(*) FROM core_corporate_actions").fetchone()[0],
                "financial_revision": connection.execute("SELECT COUNT(*) FROM (SELECT instrument_id, report_date, metric_key FROM core_financial_facts GROUP BY instrument_id, report_date, metric_key HAVING MAX(revision)>1)").fetchone()[0],
            }
            return {
                "instrument_count": connection.execute("SELECT COUNT(*) FROM core_instruments").fetchone()[0],
                "segments": rows,
                "edge_cases": cases,
                "fixture_only": True,
            }


class SnapshotReader:
    """Read-only, snapshot-bound consumer surface; there is no fetch method."""

    def __init__(self, foundation: DataFoundation, snapshot_id: str) -> None:
        self.foundation = foundation
        self.snapshot_id = snapshot_id
        foundation.replay_digest(snapshot_id)

    def rows(self, table_name: str) -> Iterable[dict[str, Any]]:
        allowed = {
            "core_instruments", "core_trading_calendar", "core_instrument_status",
            "core_adjustment_factors", "core_daily_bars", "core_financial_facts",
            "core_corporate_actions", "core_intelligence_items",
        }
        if table_name not in allowed:
            raise ValueError(f"snapshot reader table not allowed: {table_name}")
        with closing(self.foundation.connect()) as connection:
            rows = connection.execute(
                """SELECT row_json FROM core_snapshot_items
                   WHERE snapshot_id=? AND table_name=? ORDER BY row_key""",
                (self.snapshot_id, table_name),
            ).fetchall()
            yield from (json.loads(row["row_json"]) for row in rows)

    def research_context(self, ticker: str) -> dict[str, Any]:
        normalized = ticker.upper()
        instruments = [row for row in self.rows("core_instruments") if row["ticker"] == normalized]
        if len(instruments) != 1:
            raise KeyError(normalized)
        instrument = instruments[0]
        instrument_id = instrument["instrument_id"]
        by_instrument = {}
        for table in (
            "core_instrument_status", "core_adjustment_factors", "core_daily_bars",
            "core_financial_facts", "core_corporate_actions", "core_intelligence_items",
        ):
            by_instrument[table.removeprefix("core_")] = [
                row for row in self.rows(table) if row.get("instrument_id") == instrument_id
            ]
        return {
            "snapshot_id": self.snapshot_id,
            "instrument": instrument,
            "trading_calendar": list(self.rows("core_trading_calendar")),
            **by_instrument,
        }
