from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timezone
from enum import Enum
from typing import Any, Iterable
from urllib.parse import urlsplit


SCHEMA_VERSION = "data-foundation-v1"
CONTRACT_VERSION = "canonical-data-contract-v1"


class RecordDomain(str, Enum):
    MARKET = "market"
    FUNDAMENTAL = "fundamental"
    DOCUMENT = "document"
    ESTIMATE = "estimate"
    EVENT = "event"


class RecordStatus(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"


@dataclass(frozen=True)
class RecordSchema:
    """Versioned logical contract for one canonical data domain."""

    name: str
    domain: RecordDomain
    version: str
    required_fields: tuple[str, ...]

    def validate_payload(self, payload: dict[str, Any], *, known_at: str) -> None:
        if not isinstance(payload, dict):
            raise ValueError(f"{self.name} payload must be an object")
        missing = [field for field in self.required_fields if field not in payload]
        if missing:
            raise ValueError(f"{self.name} payload missing: {', '.join(missing)}")
        nulls = [field for field in self.required_fields if payload[field] is None]
        if nulls:
            raise ValueError(f"{self.name} payload null: {', '.join(nulls)}")
        _validate_json_value(payload, path=self.name)
        _validate_domain_payload(self.domain, payload, known_at=known_at)


RECORD_SCHEMAS: dict[RecordDomain, RecordSchema] = {
    RecordDomain.MARKET: RecordSchema(
        name="market-record",
        domain=RecordDomain.MARKET,
        version="market-record-v1",
        required_fields=("instrument_id", "observed_at", "metric", "value", "unit"),
    ),
    RecordDomain.FUNDAMENTAL: RecordSchema(
        name="fundamental-record",
        domain=RecordDomain.FUNDAMENTAL,
        version="fundamental-record-v1",
        required_fields=(
            "instrument_id", "report_period", "announced_at", "metric", "value", "unit",
        ),
    ),
    RecordDomain.DOCUMENT: RecordSchema(
        name="document-record",
        domain=RecordDomain.DOCUMENT,
        version="document-record-v1",
        required_fields=(
            "document_id", "instrument_id", "document_type", "published_at", "content_hash", "storage_uri",
        ),
    ),
    RecordDomain.ESTIMATE: RecordSchema(
        name="estimate-record",
        domain=RecordDomain.ESTIMATE,
        version="estimate-record-v1",
        required_fields=(
            "estimate_id", "instrument_id", "broker", "published_at", "fiscal_period", "metric", "value", "unit",
        ),
    ),
    RecordDomain.EVENT: RecordSchema(
        name="event-record",
        domain=RecordDomain.EVENT,
        version="event-record-v1",
        required_fields=(
            "event_id", "instrument_id", "event_type", "occurred_at", "title", "evidence_ids",
        ),
    ),
}

# Compatibility for the already-shipped data-foundation/research-refresh
# manifests. New adapters must declare the canonical domain values directly.
_LEGACY_DOMAIN_SCOPE_ALIASES: dict[str, frozenset[RecordDomain]] = {
    "a_share_market": frozenset({RecordDomain.MARKET, RecordDomain.FUNDAMENTAL}),
    "a_share_market_bundle": frozenset(
        {RecordDomain.MARKET, RecordDomain.FUNDAMENTAL, RecordDomain.EVENT}
    ),
}


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SourceManifest:
    """Stable source identity, adapted from datafeed's explicit trust contract."""

    source_key: str
    domain_scope: str
    authority_tier: str
    provider_version: str
    schema_version: str
    license_status: str
    source_url: str
    quality_flags: tuple[str, ...] = ()
    active: bool = True

    def validate(self) -> None:
        required = {
            "source_key": self.source_key,
            "domain_scope": self.domain_scope,
            "authority_tier": self.authority_tier,
            "provider_version": self.provider_version,
            "schema_version": self.schema_version,
            "license_status": self.license_status,
            "source_url": self.source_url,
        }
        invalid = [
            name for name, value in required.items()
            if not isinstance(value, str) or not value.strip()
        ]
        if invalid:
            raise ValueError(f"source manifest fields must be non-empty strings: {', '.join(invalid)}")
        if type(self.active) is not bool:
            raise ValueError("source manifest active must be a bool")
        if not isinstance(self.quality_flags, tuple) or not all(
            isinstance(flag, str) and flag.strip() for flag in self.quality_flags
        ):
            raise ValueError("source manifest quality_flags must be a tuple of non-empty strings")
        if self.authority_tier not in {"canonical", "official", "supplementary_only"}:
            raise ValueError(f"unsupported authority_tier: {self.authority_tier}")
        domains = self.domains
        if not domains:
            raise ValueError("source manifest has no supported record domain")

    @property
    def manifest_hash(self) -> str:
        self.validate()
        return digest(asdict(self))

    @property
    def domains(self) -> frozenset[RecordDomain]:
        values = [item.strip() for item in self.domain_scope.split(",") if item.strip()]
        if len(values) == 1 and values[0] in _LEGACY_DOMAIN_SCOPE_ALIASES:
            return _LEGACY_DOMAIN_SCOPE_ALIASES[values[0]]
        try:
            return frozenset(RecordDomain(value) for value in values)
        except ValueError as exc:
            raise ValueError(f"unsupported domain_scope: {self.domain_scope}") from exc


def _canonical_instant(value: str, *, field: str) -> str:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include timezone")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _temporal_instant(value: Any, *, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty ISO date or timestamp")
    if len(value) == 10:
        try:
            return datetime.combine(date.fromisoformat(value), time.min, tzinfo=timezone.utc)
        except ValueError as exc:
            raise ValueError(f"{field} must be an ISO date or timestamp") from exc
    return datetime.fromisoformat(_canonical_instant(value, field=field).replace("Z", "+00:00"))


def _validate_json_value(value: Any, *, path: str) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} contains non-finite number")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_value(item, path=f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{path} contains a non-string object key")
            _validate_json_value(item, path=f"{path}.{key}")
        return
    raise ValueError(f"{path} contains non-JSON value: {type(value).__name__}")


def _canonical_payload_json(payload: dict[str, Any]) -> str:
    if not isinstance(payload, dict):
        raise ValueError("record payload must be an object")
    _validate_json_value(payload, path="record payload")
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _require_string(payload: dict[str, Any], *fields: str) -> None:
    invalid = [field for field in fields if not isinstance(payload.get(field), str) or not payload[field].strip()]
    if invalid:
        raise ValueError(f"payload fields must be non-empty strings: {', '.join(invalid)}")


def _require_number(payload: dict[str, Any], field: str) -> None:
    value = payload.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{field} must be a finite number")


def _not_after_known_at(payload: dict[str, Any], field: str, *, known_at: str) -> None:
    event_time = _temporal_instant(payload.get(field), field=field)
    cutoff = datetime.fromisoformat(_canonical_instant(known_at, field="known_at").replace("Z", "+00:00"))
    if event_time > cutoff:
        raise ValueError(f"{field} cannot be later than provenance known_at")


def _validate_domain_payload(domain: RecordDomain, payload: dict[str, Any], *, known_at: str) -> None:
    _require_string(payload, "instrument_id")
    if domain is RecordDomain.MARKET:
        _require_string(payload, "metric", "unit")
        _require_number(payload, "value")
        _not_after_known_at(payload, "observed_at", known_at=known_at)
    elif domain is RecordDomain.FUNDAMENTAL:
        _require_string(payload, "report_period", "metric", "unit")
        date.fromisoformat(payload["report_period"])
        _require_number(payload, "value")
        _not_after_known_at(payload, "announced_at", known_at=known_at)
    elif domain is RecordDomain.DOCUMENT:
        _require_string(payload, "document_id", "document_type", "content_hash", "storage_uri")
        if not re_full_sha256(payload["content_hash"]):
            raise ValueError("content_hash must be a lowercase SHA-256 digest")
        _not_after_known_at(payload, "published_at", known_at=known_at)
    elif domain is RecordDomain.ESTIMATE:
        _require_string(payload, "estimate_id", "broker", "fiscal_period", "metric", "unit")
        date.fromisoformat(payload["fiscal_period"])
        _require_number(payload, "value")
        _not_after_known_at(payload, "published_at", known_at=known_at)
    elif domain is RecordDomain.EVENT:
        _require_string(payload, "event_id", "event_type", "title")
        evidence_ids = payload.get("evidence_ids")
        if not isinstance(evidence_ids, list) or not evidence_ids or not all(
            isinstance(item, str) and item.strip() for item in evidence_ids
        ):
            raise ValueError("evidence_ids must be a non-empty list of strings")
        _not_after_known_at(payload, "occurred_at", known_at=known_at)


@dataclass(frozen=True)
class RawCapture:
    """Immutable raw landing receipt required before normalization."""

    raw_hash: str
    storage_uri: str
    source_url: str
    fetched_at: str
    known_at: str
    mime_type: str
    payload_size: int

    def validate(self) -> None:
        string_fields = {
            "raw_hash": self.raw_hash,
            "storage_uri": self.storage_uri,
            "source_url": self.source_url,
            "fetched_at": self.fetched_at,
            "known_at": self.known_at,
            "mime_type": self.mime_type,
        }
        invalid = [
            name for name, value in string_fields.items()
            if not isinstance(value, str) or not value.strip()
        ]
        if invalid:
            raise ValueError(f"raw capture fields must be non-empty strings: {', '.join(invalid)}")
        if not re_full_sha256(self.raw_hash):
            raise ValueError("raw_hash must be a lowercase SHA-256 digest")
        if not self.storage_uri.strip():
            raise ValueError("storage_uri is required")
        parsed = urlsplit(self.source_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("source_url must be an absolute HTTP(S) URL")
        _canonical_instant(self.fetched_at, field="fetched_at")
        _canonical_instant(self.known_at, field="known_at")
        if not self.mime_type.strip():
            raise ValueError("mime_type is required")
        if type(self.payload_size) is not int or self.payload_size < 0:
            raise ValueError("payload_size must be a nonnegative int")


def re_full_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


@dataclass(frozen=True)
class Provenance:
    source_key: str
    source_manifest_hash: str
    provider_version: str
    provider_schema_version: str
    raw_hash: str
    known_at: str

    @classmethod
    def bind(cls, manifest: SourceManifest, raw: RawCapture) -> "Provenance":
        manifest.validate()
        raw.validate()
        return cls(
            source_key=manifest.source_key,
            source_manifest_hash=manifest.manifest_hash,
            provider_version=manifest.provider_version,
            provider_schema_version=manifest.schema_version,
            raw_hash=raw.raw_hash,
            known_at=_canonical_instant(raw.known_at, field="known_at"),
        )

    def validate(self, *, manifest: SourceManifest, raw: RawCapture) -> None:
        expected = Provenance.bind(manifest, raw)
        if self != expected:
            raise ValueError("record provenance is not bound to the supplied manifest and raw capture")


@dataclass(frozen=True)
class RecordEnvelope:
    """Only valid boundary object allowed to leave a provider adapter."""

    contract_version: str
    domain: RecordDomain
    record_schema_version: str
    entity_key: str
    payload_json: str
    payload_hash: str
    status: RecordStatus
    provenance: Provenance
    quality_flags: tuple[str, ...] = ()
    rejection_reason: str | None = None
    violations: tuple[str, ...] = ()

    @classmethod
    def accepted(
        cls,
        *,
        domain: RecordDomain,
        entity_key: str,
        payload: dict[str, Any],
        manifest: SourceManifest,
        raw: RawCapture,
        quality_flags: tuple[str, ...] = (),
    ) -> "RecordEnvelope":
        schema = RECORD_SCHEMAS[domain]
        payload_json = _canonical_payload_json(payload)
        envelope = cls(
            contract_version=CONTRACT_VERSION,
            domain=domain,
            record_schema_version=schema.version,
            entity_key=entity_key,
            payload_json=payload_json,
            payload_hash=digest(payload),
            status=RecordStatus.ACCEPTED,
            provenance=Provenance.bind(manifest, raw),
            quality_flags=quality_flags,
        )
        envelope.validate(manifest=manifest, raw=raw)
        return envelope

    @classmethod
    def rejected(
        cls,
        *,
        domain: RecordDomain,
        entity_key: str,
        payload: dict[str, Any],
        manifest: SourceManifest,
        raw: RawCapture,
        rejection_reason: str,
        violations: tuple[str, ...],
        quality_flags: tuple[str, ...] = (),
    ) -> "RecordEnvelope":
        schema = RECORD_SCHEMAS[domain]
        payload_json = _canonical_payload_json(payload)
        envelope = cls(
            contract_version=CONTRACT_VERSION,
            domain=domain,
            record_schema_version=schema.version,
            entity_key=entity_key,
            payload_json=payload_json,
            payload_hash=digest(payload),
            status=RecordStatus.REJECTED,
            provenance=Provenance.bind(manifest, raw),
            quality_flags=quality_flags,
            rejection_reason=rejection_reason,
            violations=violations,
        )
        envelope.validate(manifest=manifest, raw=raw)
        return envelope

    def validate(self, *, manifest: SourceManifest, raw: RawCapture) -> None:
        if self.contract_version != CONTRACT_VERSION:
            raise ValueError(f"unsupported contract_version: {self.contract_version}")
        if not isinstance(self.domain, RecordDomain):
            raise ValueError(f"unsupported record domain: {self.domain}")
        if not isinstance(self.status, RecordStatus):
            raise ValueError(f"unsupported record status: {self.status}")
        schema = RECORD_SCHEMAS.get(self.domain)
        if schema is None or self.record_schema_version != schema.version:
            raise ValueError(f"unsupported record schema: {self.record_schema_version}")
        if self.domain not in manifest.domains:
            raise ValueError(f"source {manifest.source_key} is not registered for {self.domain.value}")
        if not self.entity_key.strip():
            raise ValueError("entity_key is required")
        if not isinstance(self.quality_flags, tuple) or not all(
            isinstance(flag, str) and flag.strip() for flag in self.quality_flags
        ):
            raise ValueError("record quality_flags must be a tuple of non-empty strings")
        if not isinstance(self.violations, tuple):
            raise ValueError("record violations must be a tuple")
        if not isinstance(self.payload_json, str):
            raise ValueError("record payload_json must be a canonical JSON string")
        try:
            payload = json.loads(self.payload_json)
        except json.JSONDecodeError as exc:
            raise ValueError("record payload_json is invalid") from exc
        if _canonical_payload_json(payload) != self.payload_json:
            raise ValueError("record payload_json is not canonical")
        if self.payload_hash != digest(payload):
            raise ValueError("record payload no longer matches payload_hash")
        self.provenance.validate(manifest=manifest, raw=raw)
        if self.status is RecordStatus.ACCEPTED:
            if not manifest.active:
                raise ValueError(f"source {manifest.source_key} is inactive")
            if self.rejection_reason is not None or self.violations:
                raise ValueError("accepted record cannot include rejection metadata")
            schema.validate_payload(payload, known_at=self.provenance.known_at)
            if self.domain is RecordDomain.DOCUMENT:
                if payload["content_hash"] != raw.raw_hash or payload["storage_uri"] != raw.storage_uri:
                    raise ValueError("document payload must be bound to the supplied raw capture")
        else:
            if not isinstance(self.rejection_reason, str) or not self.rejection_reason.strip():
                raise ValueError("rejected record requires rejection_reason")
            if not self.violations or not all(isinstance(item, str) and item.strip() for item in self.violations):
                raise ValueError("rejected record requires structured violations")

    @property
    def record_hash(self) -> str:
        return digest(
            {
                "contract_version": self.contract_version,
                "domain": self.domain.value,
                "record_schema_version": self.record_schema_version,
                "entity_key": self.entity_key,
                "payload": self.payload,
                "payload_hash": self.payload_hash,
                "status": self.status.value,
                "provenance": asdict(self.provenance),
                "quality_flags": list(self.quality_flags),
                "rejection_reason": self.rejection_reason,
                "violations": list(self.violations),
            }
        )

    @property
    def payload(self) -> dict[str, Any]:
        """Return a detached copy; the envelope retains immutable canonical JSON."""

        return json.loads(self.payload_json)


def contract_descriptor() -> dict[str, Any]:
    """Stable, serializable descriptor used by docs, tests, and future adapters."""

    return {
        "contract_version": CONTRACT_VERSION,
        "record_statuses": [status.value for status in RecordStatus],
        "record_schemas": {
            domain.value: {
                "name": schema.name,
                "version": schema.version,
                "required_fields": list(schema.required_fields),
            }
            for domain, schema in RECORD_SCHEMAS.items()
        },
        "required_provenance": [
            "source_key",
            "source_manifest_hash",
            "provider_version",
            "provider_schema_version",
            "raw_hash",
            "known_at",
        ],
        "required_envelope_fields": [
            "contract_version",
            "domain",
            "record_schema_version",
            "entity_key",
            "payload",
            "payload_hash",
            "status",
            "provenance",
        ],
    }


def validate_adapter_output(
    *,
    manifest: SourceManifest,
    raw: RawCapture,
    records: Iterable[RecordEnvelope],
) -> tuple[RecordEnvelope, ...]:
    """Fail-closed adapter boundary shared by contract tests and A3 runtime."""

    manifest.validate()
    raw.validate()
    materialized = tuple(records)
    for record in materialized:
        if not isinstance(record, RecordEnvelope):
            raise ValueError("adapter output must contain only RecordEnvelope values")
        record.validate(manifest=manifest, raw=raw)
    return materialized


def rows_digest(rows: Iterable[dict[str, Any]]) -> str:
    return digest(list(rows))
