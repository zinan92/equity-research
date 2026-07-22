from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from .contracts import re_full_sha256


RAW_BUCKET = "canonical-raw"
@dataclass(frozen=True)
class StorageObjectKey:
    bucket: str
    path: str
    raw_hash: str

    def validate(self) -> None:
        if self.bucket != RAW_BUCKET:
            raise ValueError(f"unsupported raw bucket: {self.bucket}")
        if not re_full_sha256(self.raw_hash):
            raise ValueError("raw_hash must be a lowercase SHA-256 digest")
        path = PurePosixPath(self.path)
        if path.is_absolute() or ".." in path.parts or str(path) != self.path:
            raise ValueError("storage path must be normalized and relative")
        parts = path.parts
        if (
            len(parts) != 4
            or parts[0] != "raw"
            or parts[1] != "sha256"
            or parts[2] != self.raw_hash[:2]
            or parts[3] != self.raw_hash
        ):
            raise ValueError("storage path does not match content-addressed raw layout")


def raw_storage_key(
    *,
    raw_hash: str,
) -> StorageObjectKey:
    if not re_full_sha256(raw_hash):
        raise ValueError("raw_hash must be a lowercase SHA-256 digest")
    path = f"raw/sha256/{raw_hash[:2]}/{raw_hash}"
    key = StorageObjectKey(
        bucket=RAW_BUCKET,
        path=path,
        raw_hash=raw_hash,
    )
    key.validate()
    return key
