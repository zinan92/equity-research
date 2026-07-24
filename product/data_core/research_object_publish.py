"""A3-style atomic publication glue for canonical research objects."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from .contracts import canonical_json, digest
from .research_objects import ResearchObject, ResearchObjectStore


class ResearchObjectPublishError(RuntimeError):
    pass


class ResearchObjectPublisher:
    """Publishes E1 objects and evidence receipts in one existing-authority transaction."""

    def __init__(self, connection_factory: Any) -> None:
        self.connection_factory = connection_factory
        self.store = ResearchObjectStore(connection_factory)

    def publish(self, objects: Iterable[ResearchObject]) -> dict[str, Any]:
        items = tuple(objects)
        if not items:
            raise ValueError("research-object publication requires at least one object")
        connection = self.connection_factory()
        try:
            connection.execute("BEGIN")
            records = [self.store.append_in_transaction(connection, item) for item in items]
            for record in records:
                receipt_id = "receipt:" + digest({"object_hash": record["object_hash"]})[:32]
                connection.execute(
                    """INSERT OR IGNORE INTO core_research_object_receipts (
                       receipt_id,object_id,revision,object_hash,snapshot_id,evidence_refs_json,raw_hashes_json,status,reason,created_at
                       ) VALUES (?,?,?,?,?,?,?,'accepted',NULL,?)""",
                    (receipt_id, record["object_id"], record["revision"], record["object_hash"], record["snapshot_id"],
                     canonical_json(record["evidence_refs"]), canonical_json(record["raw_hashes"]),
                     datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")),
                )
            connection.commit()
            return {"schema_version": "research-object-publication-receipt-v1", "status": "accepted", "records": records}
        except Exception as exc:
            connection.rollback()
            return {"schema_version": "research-object-publication-receipt-v1", "status": "blocked", "records": [], "reason": f"{type(exc).__name__}: {exc}"}
        finally:
            connection.close()
