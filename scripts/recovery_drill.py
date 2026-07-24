#!/usr/bin/env python3
"""Backup and recovery drills for the existing isolated private-preview runtime.

Artifacts are deliberately external-runtime only.  This is a recovery receipt
tool, not a production deployment command.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from prepare_private_preview import (  # noqa: E402
    PreviewReleaseError, canonical_json, copy_sqlite, ensure_external_runtime,
    point_current, sha256_file, verify_release, write_runtime_env,
)


SCHEMA_VERSION = "private-preview-recovery-drill-v1"


class RecoveryDrillError(RuntimeError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _external(path: Path) -> Path:
    try:
        return ensure_external_runtime(path)
    except PreviewReleaseError as exc:
        raise RecoveryDrillError(str(exc)) from exc


def _write_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RecoveryDrillError("backup manifest is unavailable or invalid") from exc
    if not isinstance(value, dict):
        raise RecoveryDrillError("backup manifest is invalid")
    receipt_hash = value.pop("receipt_hash", None)
    if not isinstance(receipt_hash, str) or receipt_hash != hashlib.sha256(canonical_json(value).encode()).hexdigest():
        raise RecoveryDrillError("backup manifest identity mismatch")
    return {**value, "receipt_hash": receipt_hash}


def create_backup(runtime: Path, backup_root: Path) -> dict[str, Any]:
    runtime = _external(runtime)
    backup_root = _external(backup_root)
    current = runtime / "current"
    if not current.is_symlink():
        raise RecoveryDrillError("runtime current release pointer is unavailable")
    release = current.resolve()
    verified = verify_release(release, expected_release_id=release.name, require_manifest=True)
    auth = runtime / "auth.db"
    if not auth.is_file() or auth.is_symlink():
        raise RecoveryDrillError("separate auth database is unavailable")
    backup_id = f"backup_{verified['release_id']}"
    destination = backup_root / "backups" / backup_id
    manifest_path = destination / "backup-manifest.json"
    if destination.exists():
        return {**verify_backup(destination), "status": "reused"}
    staging = backup_root / f".staging-{os.getpid()}"
    try:
        shutil.copytree(release, staging / "release", symlinks=False)
        copy_sqlite(auth, staging / "auth.db")
        copied = verify_release(staging / "release", expected_release_id=verified["release_id"], require_manifest=True)
        receipt = {
            "schema_version": SCHEMA_VERSION,
            "backup_id": backup_id,
            "release_id": copied["release_id"],
            "snapshot_id": copied["identity"]["snapshot_id"],
            "release_files_hash": hashlib.sha256(canonical_json(copied["files"]).encode()).hexdigest(),
            "auth_database_sha256": sha256_file(staging / "auth.db"),
            "created_at": _now().isoformat(),
            "truth_boundary": {"external_runtime_only": True, "contains_credentials": True, "committed_to_git": False},
        }
        receipt["receipt_hash"] = hashlib.sha256(canonical_json(receipt).encode()).hexdigest()
        _write_json(staging / "backup-manifest.json", receipt)
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staging, destination)
        return {**receipt, "status": "created"}
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def verify_backup(backup: Path) -> dict[str, Any]:
    backup = backup.expanduser().resolve()
    manifest = _load_manifest(backup / "backup-manifest.json")
    if manifest.get("schema_version") != SCHEMA_VERSION or not isinstance(manifest.get("release_id"), str):
        raise RecoveryDrillError("backup schema is unsupported")
    release = verify_release(backup / "release", expected_release_id=manifest["release_id"], require_manifest=True)
    auth = backup / "auth.db"
    if not auth.is_file() or auth.is_symlink() or sha256_file(auth) != manifest.get("auth_database_sha256"):
        raise RecoveryDrillError("backup auth database identity mismatch")
    with closing(sqlite3.connect(auth)) as connection:
        if not connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='members'").fetchone():
            raise RecoveryDrillError("backup auth database is not an identity store")
    release_files_hash = hashlib.sha256(canonical_json(release["files"]).encode()).hexdigest()
    if release_files_hash != manifest.get("release_files_hash"):
        raise RecoveryDrillError("backup release file identity mismatch")
    return {**manifest, "status": "verified"}


def restore_backup(backup: Path, target_runtime: Path) -> dict[str, Any]:
    verified = verify_backup(backup)
    target_runtime = _external(target_runtime)
    source = backup.expanduser().resolve()
    release_id = verified["release_id"]
    destination = target_runtime / "releases" / release_id
    if destination.exists():
        verify_release(destination, expected_release_id=release_id, require_manifest=True)
        status = "reused"
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source / "release", destination, symlinks=False)
        verify_release(destination, expected_release_id=release_id, require_manifest=True)
        status = "restored"
    copy_sqlite(source / "auth.db", target_runtime / "auth.db")
    point_current(target_runtime, release_id)
    write_runtime_env(target_runtime)
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "release_id": release_id,
        "snapshot_id": verified["snapshot_id"],
        "auth_database_sha256": sha256_file(target_runtime / "auth.db"),
        "current_release_verified": verify_release(target_runtime / "current", expected_release_id=release_id, require_manifest=True)["release_id"] == release_id,
        "restored_at": _now().isoformat(),
    }
    receipt["receipt_hash"] = hashlib.sha256(canonical_json(receipt).encode()).hexdigest()
    _write_json(target_runtime / "recovery-receipt.json", receipt)
    return receipt


def rollback(runtime: Path, release_id: str) -> dict[str, Any]:
    runtime = _external(runtime)
    current = runtime / "current"
    if not current.is_symlink():
        raise RecoveryDrillError("runtime current release pointer is unavailable")
    before = verify_release(current.resolve(), expected_release_id=current.resolve().name, require_manifest=True)["release_id"]
    if release_id == before:
        raise RecoveryDrillError("rollback target must be a distinct verified prior release")
    point_current(runtime, release_id)
    write_runtime_env(runtime)
    after = verify_release(runtime / "current", expected_release_id=release_id, require_manifest=True)["release_id"]
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "status": "rolled_back",
        "from_release_id": before,
        "to_release_id": after,
        "rolled_back_at": _now().isoformat(),
    }
    receipt["receipt_hash"] = hashlib.sha256(canonical_json(receipt).encode()).hexdigest()
    _write_json(runtime / "rollback-receipt.json", receipt)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description="Rehearse isolated private-preview backup and recovery")
    parser.add_argument("--runtime", type=Path, required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    backup = commands.add_parser("backup")
    backup.add_argument("--backup-root", type=Path, required=True)
    restore = commands.add_parser("restore")
    restore.add_argument("--backup", type=Path, required=True)
    rollback_command = commands.add_parser("rollback")
    rollback_command.add_argument("release_id")
    args = parser.parse_args()
    if args.command == "backup":
        result = create_backup(args.runtime, args.backup_root)
    elif args.command == "restore":
        result = restore_backup(args.backup, args.runtime)
    else:
        result = rollback(args.runtime, args.release_id)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
