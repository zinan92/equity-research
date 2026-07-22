from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import PurePosixPath
import re

from .contracts import RecordDomain, re_full_sha256


RAW_BUCKET = "canonical-raw"
_MIME_EXTENSIONS = {
    "application/json": "json",
    "text/html": "html",
    "application/pdf": "pdf",
}
_SAFE_SEGMENT = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")


@dataclass(frozen=True)
class StorageObjectKey:
    bucket: str
    path: str
    mime_type: str
    raw_hash: str

    def validate(self) -> None:
        if self.bucket != RAW_BUCKET:
            raise ValueError(f"unsupported raw bucket: {self.bucket}")
        if self.mime_type not in _MIME_EXTENSIONS:
            raise ValueError(f"unsupported raw MIME type: {self.mime_type}")
        if not re_full_sha256(self.raw_hash):
            raise ValueError("raw_hash must be a lowercase SHA-256 digest")
        path = PurePosixPath(self.path)
        if path.is_absolute() or ".." in path.parts or str(path) != self.path:
            raise ValueError("storage path must be normalized and relative")
        if path.suffix != f".{_MIME_EXTENSIONS[self.mime_type]}":
            raise ValueError("storage path extension does not match MIME type")
        parts = path.parts
        if (
            len(parts) != 8
            or parts[0] != "raw"
            or parts[1] not in {domain.value for domain in RecordDomain}
            or not _SAFE_SEGMENT.fullmatch(parts[2])
            or parts[6] != self.raw_hash[:2]
            or parts[7] != f"{self.raw_hash}.{_MIME_EXTENSIONS[self.mime_type]}"
        ):
            raise ValueError("storage path does not match canonical raw layout")
        try:
            datetime.strptime("/".join(parts[3:6]), "%Y/%m/%d")
        except ValueError as exc:
            raise ValueError("storage path contains an invalid UTC date") from exc


def raw_storage_key(
    *,
    domain: RecordDomain,
    source_key: str,
    known_at: str,
    raw_hash: str,
    mime_type: str,
) -> StorageObjectKey:
    if not isinstance(domain, RecordDomain):
        raise ValueError(f"unsupported record domain: {domain}")
    if not isinstance(source_key, str) or not _SAFE_SEGMENT.fullmatch(source_key):
        raise ValueError("source_key is not a safe storage segment")
    if mime_type not in _MIME_EXTENSIONS:
        raise ValueError(f"unsupported raw MIME type: {mime_type}")
    if not re_full_sha256(raw_hash):
        raise ValueError("raw_hash must be a lowercase SHA-256 digest")
    try:
        instant = datetime.fromisoformat(str(known_at).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("known_at must be an ISO-8601 timestamp") from exc
    if instant.tzinfo is None:
        raise ValueError("known_at must include timezone")
    instant = instant.astimezone(timezone.utc)
    extension = _MIME_EXTENSIONS[mime_type]
    path = (
        f"raw/{domain.value}/{source_key}/{instant:%Y/%m/%d}/"
        f"{raw_hash[:2]}/{raw_hash}.{extension}"
    )
    key = StorageObjectKey(
        bucket=RAW_BUCKET,
        path=path,
        mime_type=mime_type,
        raw_hash=raw_hash,
    )
    key.validate()
    return key
