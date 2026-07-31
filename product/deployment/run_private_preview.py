#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import zipfile


ALLOWED_ENV = {
    "PARK_DASHBOARD_DB",
    "PARK_AUTH_DB",
    "PARK_CANONICAL_PORTFOLIO_ROOT",
    "PARK_CANONICAL_PORTFOLIO_SOURCE_DB",
    "PARK_PRIVATE_REPORT_ROOT",
    "PARK_PRIVATE_RESEARCH_PACK",
    "PARK_AUTH_REQUIRED",
    "PARK_COOKIE_SECURE",
    "PARK_PRIVATE_PREVIEW",
    "PARK_MANUAL_PAID_PILOT",
    "PARK_PUBLIC_READ_ONLY",
}


def sha256_file(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def research_pack_path(root: Path, name: str) -> Path:
    if not isinstance(name, str):
        raise RuntimeError("private preview research-pack path is invalid")
    relative = Path(name)
    if relative.is_absolute() or relative.as_posix() != name or any(part in {"", ".", ".."} for part in relative.parts):
        raise RuntimeError("private preview research-pack path is unsafe")
    resolved_root = root.resolve()
    resolved = (resolved_root / relative).resolve()
    if resolved_root not in resolved.parents:
        raise RuntimeError("private preview research-pack path escapes its root")
    return resolved


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
    optional = {"PARK_PUBLIC_READ_ONLY"}
    missing = ALLOWED_ENV - optional - values.keys()
    if missing:
        raise RuntimeError("private preview environment is incomplete")
    values.setdefault("PARK_PUBLIC_READ_ONLY", "0")
    if any(values[key] != "1" for key in (
        "PARK_AUTH_REQUIRED", "PARK_COOKIE_SECURE", "PARK_PRIVATE_PREVIEW", "PARK_MANUAL_PAID_PILOT",
    )):
        raise RuntimeError("private preview safety flags must all equal 1")
    if values["PARK_PUBLIC_READ_ONLY"] not in {"0", "1"}:
        raise RuntimeError("public read-only flag must equal 0 or 1")
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
    if values["PARK_PUBLIC_READ_ONLY"] == "1" and identity.get("public_read_only_contract") != "v1":
        raise RuntimeError("private preview release is not public read-only capable")
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
    server_source = (product / "server.py").read_text(encoding="utf-8")
    expected_public_contract = "v1" if (
        "PARK_PUBLIC_READ_ONLY" in server_source and "def public_read_only_get(" in server_source
    ) else None
    if identity.get("public_read_only_contract") != expected_public_contract:
        raise RuntimeError("private preview public read-only contract identity mismatch")
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
    pack_root = release / "research-pack"
    pack_manifest_path = pack_root / "pack-manifest.json"
    if not pack_manifest_path.is_file() or pack_manifest_path.is_symlink():
        raise RuntimeError("private preview research-pack manifest is required")
    try:
        pack_manifest = json.loads(pack_manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("private preview research-pack manifest is invalid") from exc
    pack_hash = pack_manifest.pop("pack_hash", None) if isinstance(pack_manifest, dict) else None
    expected_pack_hash = hashlib.sha256(canonical_json(pack_manifest).encode()).hexdigest()
    if pack_hash != expected_pack_hash or identity.get("research_pack_hash") != pack_hash:
        raise RuntimeError("private preview research-pack identity mismatch")
    pack_files = pack_manifest.get("files")
    if not isinstance(pack_files, dict):
        raise RuntimeError("private preview research-pack files are invalid")
    canonical_root = release / "canonical"
    canonical_pack_sources = {
        "portfolio.json": canonical_root / "versions" / f"{identity['portfolio_id']}.json",
        "diff.json": canonical_root / "latest-diff.json",
        "ledger.json": canonical_root / "latest-ledger.json",
        "ledger-history.json": canonical_root / "ledger-history.json",
        **{f"reports/{ticker}.json": reports / f"{ticker}.json" for ticker in report_hashes},
    }
    if set(pack_files) != set(canonical_pack_sources):
        raise RuntimeError("private preview research-pack file set differs from the release")
    actual_pack_files: dict[str, str] = {}
    for name in sorted(pack_files):
        path = research_pack_path(pack_root, name)
        if path.is_file() and not path.is_symlink():
            actual_pack_files[name] = sha256_file(path)
    if actual_pack_files != pack_files:
        raise RuntimeError("private preview research-pack files differ from the pack manifest")
    for name, source in canonical_pack_sources.items():
        if not source.is_file() or source.is_symlink() or actual_pack_files[name] != sha256_file(source):
            raise RuntimeError(f"private preview research-pack member differs from the release: {name}")
    archive_path = pack_root / "research-pack.zip"
    try:
        with zipfile.ZipFile(archive_path) as archive:
            expected_members = sorted([*pack_files, "pack-manifest.json"])
            if sorted(archive.namelist()) != expected_members or archive.testzip() is not None:
                raise RuntimeError("private preview research-pack archive is invalid")
            if any(archive.read(name) != research_pack_path(pack_root, name).read_bytes() for name in expected_members):
                raise RuntimeError("private preview research-pack archive member mismatch")
    except (OSError, zipfile.BadZipFile) as exc:
        raise RuntimeError("private preview research-pack archive is unavailable") from exc
    expected_paths = {
        "PARK_DASHBOARD_DB": release / "research.db",
        "PARK_AUTH_DB": runtime / "auth.db",
        "PARK_CANONICAL_PORTFOLIO_ROOT": release / "canonical",
        "PARK_CANONICAL_PORTFOLIO_SOURCE_DB": release / "research.db",
        "PARK_PRIVATE_REPORT_ROOT": release / "canonical-reports",
        "PARK_PRIVATE_RESEARCH_PACK": release / "research-pack",
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
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if args.port < 1024 or args.port > 65535:
        raise SystemExit("invalid preview port")
    values = load_env(args.env_file)
    runtime = args.env_file.expanduser().resolve().parent
    manifest = verify_packaged_release(runtime, values)
    if args.verify_only:
        print(json.dumps({
            "status": "verified",
            "release_id": manifest["release_id"],
            "public_read_only": values["PARK_PUBLIC_READ_ONLY"] == "1",
        }, ensure_ascii=False))
        return
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
