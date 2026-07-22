#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys


ALLOWED_ENV = {
    "PARK_DASHBOARD_DB",
    "PARK_AUTH_DB",
    "PARK_CANONICAL_PORTFOLIO_ROOT",
    "PARK_CANONICAL_PORTFOLIO_SOURCE_DB",
    "PARK_PRIVATE_REPORT_ROOT",
    "PARK_AUTH_REQUIRED",
    "PARK_COOKIE_SECURE",
    "PARK_PRIVATE_PREVIEW",
}


def sha256_file(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def payload_file(path: Path) -> bool:
    return "__pycache__" not in path.parts and path.suffix not in {".pyc", ".pyo"} and path.name != ".DS_Store"


def load_env(path: Path) -> dict[str, str]:
    resolved = path.expanduser().resolve()
    mode = stat.S_IMODE(resolved.stat().st_mode)
    if mode & 0o077:
        raise RuntimeError("private preview environment file must be owner-only")
    values: dict[str, str] = {}
    for raw in resolved.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise RuntimeError("invalid private preview environment line")
        key, value = line.split("=", 1)
        if key not in ALLOWED_ENV or not value:
            raise RuntimeError(f"unexpected private preview environment key: {key}")
        values[key] = value
    missing = ALLOWED_ENV - values.keys()
    if missing:
        raise RuntimeError("private preview environment is incomplete")
    if any(values[key] != "1" for key in ("PARK_AUTH_REQUIRED", "PARK_COOKIE_SECURE", "PARK_PRIVATE_PREVIEW")):
        raise RuntimeError("private preview safety flags must all equal 1")
    return values


def verify_packaged_release(runtime: Path, values: dict[str, str]) -> dict:
    current = runtime / "current"
    if not current.is_symlink():
        raise RuntimeError("private preview current pointer must be a symlink")
    release = current.resolve()
    if release.parent != (runtime / "releases").resolve() or not release.is_dir():
        raise RuntimeError("private preview current pointer escapes the release store")
    manifest_path = release / "manifest.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise RuntimeError("private preview release manifest is required")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("private preview release manifest is invalid") from exc
    identity = manifest.get("identity") if isinstance(manifest, dict) else None
    if manifest.get("schema_version") != "private-preview-release-v1" or not isinstance(identity, dict):
        raise RuntimeError("private preview release identity is invalid")
    release_id = f"preview_{hashlib.sha256(canonical_json(identity).encode()).hexdigest()[:16]}"
    if manifest.get("release_id") != release_id or release.name != release_id:
        raise RuntimeError("private preview release directory does not match its identity")
    files = {
        str(path.relative_to(release)): sha256_file(path)
        for path in sorted(release.rglob("*"))
        if path.is_file() and path.name != "manifest.json" and payload_file(path.relative_to(release))
    }
    if manifest.get("files") != files:
        raise RuntimeError("private preview release files differ from the manifest")
    product = release / "product"
    code_files = {
        str(path.relative_to(product)): sha256_file(path)
        for path in sorted(product.rglob("*"))
        if path.is_file() and payload_file(path.relative_to(product))
    }
    code_hash = hashlib.sha256(canonical_json(code_files).encode()).hexdigest()
    if identity.get("product_code_hash") != code_hash:
        raise RuntimeError("private preview product code identity mismatch")
    reports = release / "canonical-reports"
    try:
        report_hashes = {
            path.stem: json.loads(path.read_text(encoding="utf-8"))["report_hash"]
            for path in sorted(reports.glob("*.json"))
            if path.is_file() and not path.is_symlink()
        }
    except (OSError, KeyError, json.JSONDecodeError, TypeError) as exc:
        raise RuntimeError("private preview report bundle is invalid") from exc
    report_bundle_hash = hashlib.sha256(canonical_json(report_hashes).encode()).hexdigest()
    if identity.get("report_bundle_hash") != report_bundle_hash or len(report_hashes) != 8:
        raise RuntimeError("private preview report bundle identity mismatch")
    expected_paths = {
        "PARK_DASHBOARD_DB": release / "research.db",
        "PARK_AUTH_DB": runtime / "auth.db",
        "PARK_CANONICAL_PORTFOLIO_ROOT": release / "canonical",
        "PARK_CANONICAL_PORTFOLIO_SOURCE_DB": release / "research.db",
        "PARK_PRIVATE_REPORT_ROOT": release / "canonical-reports",
    }
    for key, expected in expected_paths.items():
        if Path(values[key]).expanduser().resolve() != expected.resolve():
            raise RuntimeError(f"private preview environment path mismatch: {key}")
    if not expected_paths["PARK_AUTH_DB"].is_file() or expected_paths["PARK_AUTH_DB"].is_symlink():
        raise RuntimeError("private preview auth database is unavailable or unsafe")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the loopback-only Park Equity Research private preview")
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8878)
    args = parser.parse_args()
    if args.port < 1024 or args.port > 65535:
        raise SystemExit("invalid preview port")
    values = load_env(args.env_file)
    runtime = args.env_file.expanduser().resolve().parent
    verify_packaged_release(runtime, values)
    release_product = runtime / "current" / "product"
    server = release_product / "server.py"
    if not server.is_file() or server.is_symlink():
        raise RuntimeError("verified private preview product release is unavailable")
    environment = dict(os.environ)
    environment.update(values)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    os.execve(
        sys.executable,
        [sys.executable, str(server), "--host", "127.0.0.1", "--port", str(args.port)],
        environment,
    )


if __name__ == "__main__":
    main()
