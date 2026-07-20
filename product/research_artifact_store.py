from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


PROMPT_VERSION = "deepseek-equity-writer-v1"


def artifact_path(db_path: Path, ticker: str, snapshot_id: str) -> Path:
    safe_ticker = ticker.upper().replace("/", "_")
    return db_path.parent / "research_artifacts" / safe_ticker / f"{snapshot_id}_{PROMPT_VERSION}.json"


def load_artifact(db_path: Path, ticker: str, snapshot_id: str) -> dict[str, Any] | None:
    path = artifact_path(db_path, ticker, snapshot_id)
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def write_artifact(db_path: Path, ticker: str, snapshot_id: str, value: dict[str, Any]) -> Path:
    """Durably replace an AI artifact without exposing partial JSON to readers."""
    path = artifact_path(db_path, ticker, snapshot_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(json.dumps(value, ensure_ascii=False, indent=2, default=str).encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
    return path


def artifact_hash(db_path: Path, ticker: str, snapshot_id: str) -> str | None:
    path = artifact_path(db_path, ticker, snapshot_id)
    if not path.is_file():
        return None
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None
