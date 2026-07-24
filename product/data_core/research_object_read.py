"""Fixture-safe canonical read contracts for E1 research objects."""
from __future__ import annotations

import json
from typing import Any


class CanonicalReadError(RuntimeError):
    pass


class CanonicalResearchReader:
    def __init__(self, connection_factory: Any, *, allow_fixture: bool = False) -> None:
        self.connection_factory = connection_factory
        self.allow_fixture = allow_fixture

    def by_ticker(self, ticker: str) -> dict[str, Any]:
        key = str(ticker or "").strip().upper()
        if not key:
            return self._gap("invalid_ticker")
        connection = self.connection_factory()
        try:
            rows = connection.execute(
                "SELECT r.*, s.snapshot_kind FROM core_research_object_revisions r "
                "JOIN core_snapshot_manifests s ON s.snapshot_id=r.snapshot_id "
                "WHERE r.state='accepted' ORDER BY r.object_id, r.revision DESC"
            ).fetchall()
            company = None
            for row in rows:
                data = dict(row)
                facts = json.loads(data["facts_json"])
                if data["object_type"] == "company" and str(facts.get("ticker", "")).upper() == key:
                    company = data
                    break
            if company is None:
                return self._gap("company_not_found", ticker=key)
            if company["snapshot_kind"] != "real" and not self.allow_fixture:
                return self._gap("fixture_or_nonreal_snapshot", ticker=key)
            company_id = json.loads(company["facts_json"])["company_id"]
            objects: dict[str, dict[str, Any]] = {}
            for row in rows:
                data = dict(row)
                if data["snapshot_kind"] != "real" and not self.allow_fixture:
                    continue
                facts = json.loads(data["facts_json"])
                if facts.get("company_id") != company_id or data["object_type"] in objects:
                    continue
                objects[data["object_type"]] = self._serialize(data)
            return {"schema_version": "canonical-research-read-v1", "status": "accepted", "ticker": key,
                    "company_id": company_id, "objects": objects, "fixture_enabled": self.allow_fixture}
        finally:
            connection.close()

    @staticmethod
    def _serialize(row: dict[str, Any]) -> dict[str, Any]:
        return {"object_id": row["object_id"], "object_type": row["object_type"], "revision": row["revision"],
                "object_hash": row["object_hash"], "snapshot_id": row["snapshot_id"], "known_at": row["known_at"],
                "evidence_refs": json.loads(row["evidence_refs_json"]), "facts": json.loads(row["facts_json"]),
                "judgments": json.loads(row["judgments_json"]), "data_kind": row["snapshot_kind"]}

    @staticmethod
    def _gap(reason: str, **extra: Any) -> dict[str, Any]:
        return {"schema_version": "canonical-research-read-v1", "status": "missing", "reason": reason, **extra}
