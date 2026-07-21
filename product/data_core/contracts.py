from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, Iterable


SCHEMA_VERSION = "data-foundation-v1"


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
        missing = [name for name, value in required.items() if not str(value).strip()]
        if missing:
            raise ValueError(f"source manifest missing: {', '.join(missing)}")
        if self.authority_tier not in {"canonical", "official", "supplementary_only"}:
            raise ValueError(f"unsupported authority_tier: {self.authority_tier}")

    @property
    def manifest_hash(self) -> str:
        self.validate()
        return digest(asdict(self))


def rows_digest(rows: Iterable[dict[str, Any]]) -> str:
    return digest(list(rows))
