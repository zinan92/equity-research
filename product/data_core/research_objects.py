"""Versioned canonical contracts for research-layer objects.

These contracts intentionally sit on top of A1/A2: identity comes from the
Company / Universe Crosswalk, raw evidence remains in the existing authority
layer, and this module stores only stable references plus typed research state.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import json
import re
from typing import Any, Mapping

from .contracts import canonical_json, digest


RESEARCH_OBJECT_SCHEMA_VERSION = "canonical-research-object-v1"


class ResearchObjectType(str, Enum):
    COMPANY = "company"
    SECTOR_POSITION = "sector_position"
    EVIDENCE = "evidence"
    CATALYST = "catalyst"
    ROADMAP = "roadmap"
    SCORE_SNAPSHOT = "score_snapshot"
    FALSIFIER = "falsifier"
    DOSSIER = "dossier"


ALLOWED_STATES = frozenset({"draft", "accepted", "superseded", "blocked"})
ALLOWED_CONFIDENCE = frozenset({"high", "medium", "low", "unknown"})


@dataclass(frozen=True)
class ResearchObjectSchema:
    object_type: ResearchObjectType
    required_fact_fields: tuple[str, ...]
    optional_fact_fields: tuple[str, ...]
    allowed_states: frozenset[str] = ALLOWED_STATES


OBJECT_SCHEMAS: dict[ResearchObjectType, ResearchObjectSchema] = {
    ResearchObjectType.COMPANY: ResearchObjectSchema(ResearchObjectType.COMPANY, ("company_id", "display_name"), ("ticker", "market", "legal_name")),
    ResearchObjectType.SECTOR_POSITION: ResearchObjectSchema(ResearchObjectType.SECTOR_POSITION, ("company_id", "sector_id", "role"), ("segment_id", "products", "revenue_exposure")),
    ResearchObjectType.EVIDENCE: ResearchObjectSchema(ResearchObjectType.EVIDENCE, ("evidence_id", "evidence_type", "citation"), ("published_at", "document_id", "title")),
    ResearchObjectType.CATALYST: ResearchObjectSchema(ResearchObjectType.CATALYST, ("company_id", "title", "time_horizon"), ("expected_at", "leading_indicator")),
    ResearchObjectType.ROADMAP: ResearchObjectSchema(ResearchObjectType.ROADMAP, ("company_id", "milestone", "time_horizon"), ("expected_at", "dependency")),
    ResearchObjectType.SCORE_SNAPSHOT: ResearchObjectSchema(ResearchObjectType.SCORE_SNAPSHOT, ("company_id", "as_of", "score_name", "score_value"), ("score_scale", "calculation_version")),
    ResearchObjectType.FALSIFIER: ResearchObjectSchema(ResearchObjectType.FALSIFIER, ("company_id", "title", "trigger"), ("threshold", "monitoring_frequency")),
    ResearchObjectType.DOSSIER: ResearchObjectSchema(ResearchObjectType.DOSSIER, ("company_id", "dossier_version", "as_of"), ("report_model_hash", "publication_status")),
}


def _non_empty(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _object_type(value: ResearchObjectType | str) -> ResearchObjectType:
    try:
        return value if isinstance(value, ResearchObjectType) else ResearchObjectType(value)
    except ValueError as exc:
        raise ValueError(f"unsupported research object type: {value}") from exc


@dataclass(frozen=True)
class ResearchObject:
    object_id: str
    object_type: ResearchObjectType
    revision: int
    state: str
    source_ref: str
    known_at: str
    confidence: str
    evidence_refs: tuple[str, ...]
    raw_hashes: tuple[str, ...]
    snapshot_id: str
    facts: Mapping[str, Any]
    judgments: Mapping[str, Any]
    model_version: str | None = None
    revision_of: str | None = None
    schema_version: str = RESEARCH_OBJECT_SCHEMA_VERSION

    def validate(self) -> None:
        _non_empty(self.object_id, "object_id")
        object_type = _object_type(self.object_type)
        if not self.object_id.startswith(f"research-v1:{object_type.value}:"):
            raise ValueError("object_id must be namespaced by its object type")
        if self.schema_version != RESEARCH_OBJECT_SCHEMA_VERSION:
            raise ValueError("unsupported research object schema_version")
        if isinstance(self.revision, bool) or not isinstance(self.revision, int) or self.revision < 1:
            raise ValueError("revision must be a positive integer")
        if self.state not in ALLOWED_STATES:
            raise ValueError("unsupported research object state")
        _non_empty(self.source_ref, "source_ref")
        _non_empty(self.known_at, "known_at")
        if self.confidence not in ALLOWED_CONFIDENCE:
            raise ValueError("unsupported confidence")
        if not isinstance(self.evidence_refs, tuple) or not self.evidence_refs or not all(
            isinstance(item, str) and item.strip() for item in self.evidence_refs
        ):
            raise ValueError("evidence_refs must be a non-empty tuple of evidence identities")
        if not isinstance(self.raw_hashes, tuple) or not self.raw_hashes or not all(
            isinstance(item, str) and re.fullmatch(r"[0-9a-f]{64}", item) for item in self.raw_hashes
        ):
            raise ValueError("raw_hashes must be a non-empty tuple of SHA-256 identities")
        _non_empty(self.snapshot_id, "snapshot_id")
        if not isinstance(self.facts, Mapping) or not isinstance(self.judgments, Mapping):
            raise ValueError("facts and judgments must be mappings")
        schema = OBJECT_SCHEMAS[object_type]
        missing = [field for field in schema.required_fact_fields if not self.facts.get(field)]
        if missing:
            raise ValueError(f"{object_type.value} facts missing: {', '.join(missing)}")
        unknown = set(self.facts) - set(schema.required_fact_fields) - set(schema.optional_fact_fields)
        if unknown:
            raise ValueError(f"{object_type.value} facts have undeclared fields: {', '.join(sorted(unknown))}")
        if self.judgments and not self.model_version:
            raise ValueError("model_version is required when research judgments are present")
        if self.revision == 1 and self.revision_of is not None:
            raise ValueError("first revision cannot declare revision_of")
        if self.revision > 1:
            _non_empty(self.revision_of, "revision_of")

    @property
    def object_hash(self) -> str:
        self.validate()
        return digest({**asdict(self), "object_type": self.object_type.value})

    def to_record(self) -> dict[str, Any]:
        self.validate()
        return {
            "object_id": self.object_id,
            "object_type": self.object_type.value,
            "revision": self.revision,
            "state": self.state,
            "schema_version": self.schema_version,
            "source_ref": self.source_ref,
            "known_at": self.known_at,
            "confidence": self.confidence,
            "evidence_refs": list(self.evidence_refs),
            "raw_hashes": list(self.raw_hashes),
            "snapshot_id": self.snapshot_id,
            "facts": dict(self.facts),
            "judgments": dict(self.judgments),
            "model_version": self.model_version,
            "revision_of": self.revision_of,
            "object_hash": self.object_hash,
        }


def object_contract_descriptor() -> dict[str, Any]:
    return {
        "schema_version": RESEARCH_OBJECT_SCHEMA_VERSION,
        "object_types": {
            item.value: {
                "required_facts": list(schema.required_fact_fields),
                "optional_facts": list(schema.optional_fact_fields),
                "allowed_states": sorted(schema.allowed_states),
            }
            for item, schema in OBJECT_SCHEMAS.items()
        },
        "confidence": sorted(ALLOWED_CONFIDENCE),
        "fact_judgment_boundary": "facts require evidence_refs and raw_hashes; judgments require model_version and remain distinct",
    }


class ResearchObjectStore:
    """Append-only SQLite adapter for the A1/A2 research-object extension."""

    def __init__(self, connection_factory: Any) -> None:
        self.connection_factory = connection_factory

    def append(self, item: ResearchObject) -> dict[str, Any]:
        connection = self.connection_factory()
        try:
            record = self.append_in_transaction(connection, item)
            connection.commit()
            return record
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def append_in_transaction(self, connection: Any, item: ResearchObject) -> dict[str, Any]:
        """Validate and stage one revision without committing the caller transaction."""
        item.validate()
        record = item.to_record()
        self._validate_authority_bindings(connection, item)
        existing = connection.execute(
                "SELECT object_hash FROM core_research_object_revisions WHERE object_id=? AND revision=?",
                (item.object_id, item.revision),
            ).fetchone()
        if existing is not None:
            if existing[0] != record["object_hash"]:
                raise ValueError("research object revision already exists with different inputs")
            return {**record, "reused": True}
        prior = connection.execute(
                "SELECT revision, object_hash FROM core_research_object_revisions WHERE object_id=? ORDER BY revision DESC LIMIT 1",
                (item.object_id,),
        ).fetchone()
        if prior is None and item.revision != 1:
            raise ValueError("first stored revision must be revision 1")
        if prior is not None:
            if item.revision != int(prior[0]) + 1:
                raise ValueError("research object revisions must be consecutive")
            if item.revision_of != prior[1]:
                raise ValueError("revision_of must bind the immediately prior object hash")
        connection.execute(
                """INSERT INTO core_research_object_revisions (
                   object_id,object_type,revision,state,schema_version,source_ref,known_at,confidence,
                   evidence_refs_json,raw_hashes_json,snapshot_id,facts_json,judgments_json,model_version,revision_of,object_hash
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    item.object_id, item.object_type.value, item.revision, item.state, item.schema_version,
                    item.source_ref, item.known_at, item.confidence, canonical_json(record["evidence_refs"]),
                    canonical_json(record["raw_hashes"]), item.snapshot_id, canonical_json(record["facts"]),
                    canonical_json(record["judgments"]), item.model_version, item.revision_of, record["object_hash"],
                ),
        )
        return {**record, "reused": False}

    @staticmethod
    def _validate_authority_bindings(connection: Any, item: ResearchObject) -> None:
        placeholders = ",".join("?" for _ in item.raw_hashes)
        rows = connection.execute(
            f"SELECT raw_hash FROM core_raw_objects WHERE raw_hash IN ({placeholders})", item.raw_hashes
        ).fetchall()
        if {row[0] for row in rows} != set(item.raw_hashes):
            raise ValueError("research object references unknown raw evidence")
        snapshot = connection.execute(
            "SELECT manifest_json FROM core_snapshot_manifests WHERE snapshot_id=? AND quality_status='passed'",
            (item.snapshot_id,),
        ).fetchone()
        if snapshot is None:
            raise ValueError("research object references unknown or blocked snapshot")
        manifest = json.loads(snapshot[0])
        if not set(item.raw_hashes).issubset(set(manifest.get("raw_hashes") or ())):
            raise ValueError("research object raw evidence is not frozen by snapshot")

    def replay(self, object_id: str) -> dict[str, Any]:
        """Return a deterministic, prose-free revision receipt or explicit conflicts."""
        connection = self.connection_factory()
        try:
            rows = connection.execute(
                "SELECT * FROM core_research_object_revisions WHERE object_id=? ORDER BY revision", (object_id,)
            ).fetchall()
            if not rows:
                raise KeyError(object_id)
            conflicts: list[str] = []
            receipts: list[dict[str, Any]] = []
            prior_hash: str | None = None
            for row in rows:
                data = dict(row)
                try:
                    item = ResearchObject(
                        object_id=data["object_id"], object_type=ResearchObjectType(data["object_type"]),
                        revision=data["revision"], state=data["state"], schema_version=data["schema_version"],
                        source_ref=data["source_ref"], known_at=data["known_at"], confidence=data["confidence"],
                        evidence_refs=tuple(json.loads(data["evidence_refs_json"])),
                        raw_hashes=tuple(json.loads(data["raw_hashes_json"])), snapshot_id=data["snapshot_id"],
                        facts=json.loads(data["facts_json"]), judgments=json.loads(data["judgments_json"]),
                        model_version=data["model_version"], revision_of=data["revision_of"],
                    )
                    if item.object_hash != data["object_hash"]:
                        conflicts.append(f"revision {item.revision}: object_hash_mismatch")
                    if prior_hash is not None and item.revision_of != prior_hash:
                        conflicts.append(f"revision {item.revision}: prior_revision_mismatch")
                    self._validate_authority_bindings(connection, item)
                    receipts.append({
                        "revision": item.revision, "object_hash": data["object_hash"],
                        "snapshot_id": item.snapshot_id, "raw_hashes": list(item.raw_hashes),
                        "evidence_refs": list(item.evidence_refs), "model_version": item.model_version,
                    })
                    prior_hash = data["object_hash"]
                except (ValueError, KeyError, json.JSONDecodeError) as exc:
                    conflicts.append(f"revision {data['revision']}: {exc}")
            return {
                "schema_version": "research-object-replay-receipt-v1", "object_id": object_id,
                "status": "passed" if not conflicts else "blocked", "revisions": receipts,
                "conflicts": conflicts,
            }
        finally:
            connection.close()

    def history(self, object_id: str) -> list[dict[str, Any]]:
        connection = self.connection_factory()
        try:
            rows = connection.execute(
                "SELECT * FROM core_research_object_revisions WHERE object_id=? ORDER BY revision", (object_id,)
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            connection.close()
