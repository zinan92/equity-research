#!/usr/bin/env python3
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
import zipfile


ROOT = Path(__file__).resolve().parents[1]
PRODUCT = ROOT / "product"
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from auth_store import initialize_auth  # noqa: E402
from billing_store import initialize_billing  # noqa: E402
from data_store import connect, stock_payload, verify_snapshot_content_attestation  # noqa: E402
from feedback_store import initialize_feedback  # noqa: E402
from portfolio_allocation import (  # noqa: E402
    CanonicalPortfolioError, _report_binding, digest, load_portfolio_history, load_portfolio_state, portfolio_diff,
)
from portfolio_ledger import (  # noqa: E402
    PortfolioLedgerError,
    verify_ledger_fills_against_source,
    verify_ledger_history,
    verify_ledger_matches_portfolio,
    verify_ledger_payload,
)
from research_reports import _baseline_report  # noqa: E402


SCHEMA_VERSION = "private-preview-release-v1"
DEFAULT_RUNTIME = Path.home() / "Library" / "Application Support" / "Park Equity Research Preview"
DEFAULT_SOURCE_DB = PRODUCT / "runtime" / "m4-live.db"
DEFAULT_SOURCE_STATE = PRODUCT / "runtime" / "canonical_portfolio"
DEFAULT_DEEP_REPORTS = ROOT / "evidence" / "m4-cross-company-research" / "live"
STATE_FILES = {"current.json", "latest-diff.json", "latest-ledger.json", "ledger-history.json"}
AUTH_TABLES = (
    "members", "invite_codes", "member_sessions", "member_events", "member_feedback",
    "billing_events", "billing_settings", "billing_control_events",
)
TRANSIENT_CODE_PARTS = {"__pycache__"}
TRANSIENT_CODE_SUFFIXES = {".pyc", ".pyo"}


class PreviewReleaseError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def is_release_payload_file(path: Path) -> bool:
    """Exclude interpreter caches that may appear after a packaged release starts."""
    return not (
        TRANSIENT_CODE_PARTS.intersection(path.parts)
        or path.suffix in TRANSIENT_CODE_SUFFIXES
        or path.name == ".DS_Store"
    )


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def research_pack_path(root: Path, name: str) -> Path:
    if not isinstance(name, str):
        raise PreviewReleaseError("research-pack path is invalid")
    relative = Path(name)
    if relative.is_absolute() or relative.as_posix() != name or any(part in {"", ".", ".."} for part in relative.parts):
        raise PreviewReleaseError("research-pack path is unsafe")
    resolved_root = root.resolve()
    resolved = (resolved_root / relative).resolve()
    if resolved_root not in resolved.parents:
        raise PreviewReleaseError("research-pack path escapes its root")
    return resolved


def ensure_external_runtime(runtime: Path) -> Path:
    resolved = runtime.expanduser().resolve()
    repo = ROOT.resolve()
    if resolved == repo or repo in resolved.parents:
        raise PreviewReleaseError("private preview runtime must be outside the repository")
    resolved.mkdir(parents=True, exist_ok=True)
    os.chmod(resolved, 0o700)
    return resolved


def copy_sqlite(source: Path, target: Path) -> None:
    if not source.is_file() or source.is_symlink():
        raise PreviewReleaseError("research source database is unavailable or unsafe")
    target.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(source)) as source_conn, closing(sqlite3.connect(target)) as target_conn:
        source_conn.backup(target_conn)
    os.chmod(target, 0o600)


def copy_state(source: Path, target: Path) -> None:
    if not source.is_dir() or source.is_symlink():
        raise PreviewReleaseError("canonical portfolio state is unavailable or unsafe")
    (target / "versions").mkdir(parents=True, exist_ok=True)
    for name in sorted(STATE_FILES):
        item = source / name
        if not item.is_file() or item.is_symlink():
            raise PreviewReleaseError(f"canonical portfolio state is incomplete: {name}")
        shutil.copy2(item, target / name)
    versions = sorted((source / "versions").glob("canonical_portfolio_*.json"))
    if not versions or any(item.is_symlink() for item in versions):
        raise PreviewReleaseError("canonical portfolio versions are unavailable or unsafe")
    for item in versions:
        shutil.copy2(item, target / "versions" / item.name)


def copy_product_code(source: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    root_modules = sorted(source.glob("*.py"))
    if not root_modules or any(item.is_symlink() for item in root_modules):
        raise PreviewReleaseError("product server modules are unavailable or unsafe")
    for item in root_modules:
        shutil.copy2(item, target / item.name)
    for directory in ("static", "schemas", "data", "data_core"):
        source_dir = source / directory
        if not source_dir.is_dir() or source_dir.is_symlink():
            raise PreviewReleaseError(f"product code directory is unavailable or unsafe: {directory}")
        shutil.copytree(
            source_dir,
            target / directory,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"),
        )


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PreviewReleaseError(f"invalid release JSON: {path.name}") from exc
    if not isinstance(value, dict):
        raise PreviewReleaseError(f"invalid release object: {path.name}")
    return value


def copy_report_bundle(source_db: Path, current: dict, deep_root: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    snapshot_id = current["snapshot"]["snapshot_id"]
    for position in current["positions"]:
        ticker = position["ticker"]
        candidate = deep_root / ticker / "report.json"
        report = load_json(candidate) if candidate.is_file() and not candidate.is_symlink() else None
        if report is None or (report.get("generated_from") or {}).get("snapshot_id") != snapshot_id:
            stock = stock_payload(ticker, source_db, snapshot_id=snapshot_id)
            if not stock:
                raise PreviewReleaseError(f"snapshot-bound private report input is unavailable: {ticker}")
            report = _baseline_report(stock, source_db)
        try:
            binding = _report_binding(report, snapshot_id)
        except CanonicalPortfolioError as exc:
            raise PreviewReleaseError(f"private report failed validation: {ticker}") from exc
        if binding != position["report_binding"]:
            raise PreviewReleaseError(f"private report does not match portfolio binding: {ticker}")
        (target / f"{ticker}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8",
        )


def _write_deterministic_zip(path: Path, root: Path, members: list[str]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(members):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, (root / name).read_bytes())


def build_research_pack(state: Path, reports: Path, current: dict, target: Path) -> dict:
    target.mkdir(parents=True, exist_ok=True)
    (target / "reports").mkdir()
    sources = {
        "portfolio.json": state / "versions" / f"{current['portfolio_id']}.json",
        "diff.json": state / "latest-diff.json",
        "ledger.json": state / "latest-ledger.json",
        "ledger-history.json": state / "ledger-history.json",
    }
    for position in current["positions"]:
        ticker = position["ticker"]
        sources[f"reports/{ticker}.json"] = reports / f"{ticker}.json"
    for name, source in sources.items():
        if not source.is_file() or source.is_symlink():
            raise PreviewReleaseError(f"research-pack source is unavailable: {name}")
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    report_hashes = {
        position["ticker"]: load_json(reports / f"{position['ticker']}.json")["report_hash"]
        for position in current["positions"]
    }
    core = {
        "schema_version": "canonical-research-pack-v1",
        "portfolio_id": current["portfolio_id"],
        "portfolio_payload_hash": current["payload_hash"],
        "snapshot_id": current["snapshot"]["snapshot_id"],
        "report_bundle_hash": hashlib.sha256(canonical_json(report_hashes).encode()).hexdigest(),
        "files": {name: sha256_file(target / name) for name in sorted(sources)},
        "truth_boundary": {
            "model_portfolio_not_user_holdings": True,
            "broker_execution": False,
            "manual_paid_pilot": True,
        },
    }
    manifest = {**core, "pack_hash": hashlib.sha256(canonical_json(core).encode()).hexdigest()}
    manifest_path = target / "pack-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    members = [*sources, "pack-manifest.json"]
    _write_deterministic_zip(target / "research-pack.zip", target, members)
    return manifest


def verify_research_pack(target: Path, state: Path, current: dict, reports: Path) -> dict:
    manifest = load_json(target / "pack-manifest.json")
    pack_hash = manifest.pop("pack_hash", None)
    if not isinstance(pack_hash, str) or pack_hash != hashlib.sha256(canonical_json(manifest).encode()).hexdigest():
        raise PreviewReleaseError("research-pack identity is invalid")
    if (
        manifest.get("schema_version") != "canonical-research-pack-v1"
        or manifest.get("portfolio_id") != current["portfolio_id"]
        or manifest.get("portfolio_payload_hash") != current["payload_hash"]
        or manifest.get("snapshot_id") != current["snapshot"]["snapshot_id"]
    ):
        raise PreviewReleaseError("research-pack portfolio identity mismatch")
    files = manifest.get("files")
    if not isinstance(files, dict) or len(files) != 4 + len(current["positions"]):
        raise PreviewReleaseError("research-pack file manifest is incomplete")
    canonical_sources = {
        "portfolio.json": state / "versions" / f"{current['portfolio_id']}.json",
        "diff.json": state / "latest-diff.json",
        "ledger.json": state / "latest-ledger.json",
        "ledger-history.json": state / "ledger-history.json",
        **{
            f"reports/{position['ticker']}.json": reports / f"{position['ticker']}.json"
            for position in current["positions"]
        },
    }
    if set(files) != set(canonical_sources):
        raise PreviewReleaseError("research-pack file set differs from canonical release inputs")
    actual: dict[str, str] = {}
    for name in sorted(files):
        path = research_pack_path(target, name)
        if path.is_file() and not path.is_symlink():
            actual[name] = sha256_file(path)
    if actual != files:
        raise PreviewReleaseError("research-pack files differ from the manifest")
    for name, source in canonical_sources.items():
        if not source.is_file() or source.is_symlink() or actual[name] != sha256_file(source):
            raise PreviewReleaseError(f"research-pack member differs from canonical release input: {name}")
    archive_path = target / "research-pack.zip"
    if not archive_path.is_file() or archive_path.is_symlink():
        raise PreviewReleaseError("research-pack archive is unavailable")
    expected_members = sorted([*files, "pack-manifest.json"])
    try:
        with zipfile.ZipFile(archive_path) as archive:
            if sorted(archive.namelist()) != expected_members or archive.testzip() is not None:
                raise PreviewReleaseError("research-pack archive membership is invalid")
            for name in expected_members:
                if archive.read(name) != research_pack_path(target, name).read_bytes():
                    raise PreviewReleaseError(f"research-pack archive member differs: {name}")
    except zipfile.BadZipFile as exc:
        raise PreviewReleaseError("research-pack archive is invalid") from exc
    return {**manifest, "pack_hash": pack_hash, "archive_sha256": sha256_file(archive_path)}


def verify_release(
    release: Path, *, expected_release_id: str | None = None, require_manifest: bool = False,
) -> dict:
    research_db = release / "research.db"
    state = release / "canonical"
    product = release / "product"
    reports = release / "canonical-reports"
    research_pack = release / "research-pack"
    if not (product / "server.py").is_file() or not (product / "static" / "index.html").is_file():
        raise PreviewReleaseError("private preview product code is incomplete")
    manifest_path = release / "manifest.json"
    if require_manifest and (not manifest_path.is_file() or manifest_path.is_symlink()):
        raise PreviewReleaseError("private preview release manifest is required")
    manifest = load_json(manifest_path) if manifest_path.is_file() else None
    current = load_portfolio_state(state)
    history = load_portfolio_history(state)
    diff = load_json(state / "latest-diff.json")
    ledger = load_json(state / "latest-ledger.json")
    ledger_history = load_json(state / "ledger-history.json")
    verify_ledger_payload(ledger, expected_portfolio_id=current["portfolio_id"])
    verify_ledger_matches_portfolio(ledger, current)
    verify_ledger_history(ledger_history, expected_current_portfolio_id=current["portfolio_id"])
    if len(history) != len(ledger_history["versions"]):
        raise PreviewReleaseError("portfolio and ledger history lengths differ")
    for portfolio, ledger_version in zip(history, ledger_history["versions"]):
        verify_ledger_matches_portfolio(ledger_version, portfolio)
    verify_ledger_fills_against_source(ledger_history, research_db)
    if len(history) < 2 or diff != portfolio_diff(history[-2], current):
        raise PreviewReleaseError("portfolio diff is invalid or stale")
    with closing(connect(research_db)) as connection:
        attested = verify_snapshot_content_attestation(connection, current["snapshot"]["snapshot_id"])
    if attested != current["snapshot"]["normalized_content_hash"]:
        raise PreviewReleaseError("research database attestation differs from portfolio")
    expected_report_files = {f"{item['ticker']}.json" for item in current["positions"]}
    actual_report_files = {
        path.name for path in reports.glob("*.json") if path.is_file() and not path.is_symlink()
    }
    if actual_report_files != expected_report_files:
        raise PreviewReleaseError("private report bundle does not match the canonical portfolio")
    report_hashes: dict[str, str] = {}
    for position in current["positions"]:
        ticker = position["ticker"]
        report = load_json(reports / f"{ticker}.json")
        try:
            binding = _report_binding(report, current["snapshot"]["snapshot_id"])
        except CanonicalPortfolioError as exc:
            raise PreviewReleaseError(f"private report failed validation: {ticker}") from exc
        if binding != position["report_binding"]:
            raise PreviewReleaseError(f"private report binding mismatch: {ticker}")
        report_hashes[ticker] = binding["report_hash"]
    report_bundle_hash = hashlib.sha256(canonical_json(report_hashes).encode()).hexdigest()
    verified_pack = verify_research_pack(research_pack, state, current, reports)
    code_files = {
        str(path.relative_to(product)): sha256_file(path)
        for path in sorted(product.rglob("*"))
        if path.is_file() and is_release_payload_file(path.relative_to(product))
    }
    code_hash = hashlib.sha256(canonical_json(code_files).encode()).hexdigest()
    identity_payload = {
        "schema_version": SCHEMA_VERSION,
        "portfolio_id": current["portfolio_id"],
        "portfolio_payload_hash": current["payload_hash"],
        "snapshot_id": current["snapshot"]["snapshot_id"],
        "normalized_content_hash": attested,
        "diff_hash": diff["diff_hash"],
        "ledger_hash": ledger["ledger_hash"],
        "ledger_history_hash": ledger_history["ledger_history_hash"],
        "product_code_hash": code_hash,
        "report_bundle_hash": report_bundle_hash,
        "research_pack_hash": verified_pack["pack_hash"],
    }
    release_id = f"preview_{hashlib.sha256(canonical_json(identity_payload).encode()).hexdigest()[:16]}"
    if expected_release_id and release_id != expected_release_id:
        raise PreviewReleaseError("release directory does not match verified identity")
    files = {
        str(path.relative_to(release)): sha256_file(path)
        for path in sorted(release.rglob("*"))
        if path.is_file()
        and path.name != "manifest.json"
        and is_release_payload_file(path.relative_to(release))
    }
    if manifest:
        if manifest.get("schema_version") != SCHEMA_VERSION or manifest.get("release_id") != release_id:
            raise PreviewReleaseError("release manifest identity mismatch")
        if manifest.get("files") != files or manifest.get("identity") != identity_payload:
            raise PreviewReleaseError("release files differ from manifest")
    return {"release_id": release_id, "identity": identity_payload, "files": files}


def point_current(runtime: Path, release_id: str) -> None:
    release = runtime / "releases" / release_id
    if not release.is_dir():
        raise PreviewReleaseError("requested release does not exist")
    verify_release(release, expected_release_id=release_id, require_manifest=True)
    link = runtime / "current"
    temporary = runtime / f".current-{os.getpid()}"
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(Path("releases") / release_id, target_is_directory=True)
    os.replace(temporary, link)


def write_runtime_env(runtime: Path) -> None:
    env = runtime / "preview.env"
    content = "\n".join([
        f"PARK_DASHBOARD_DB={runtime / 'current' / 'research.db'}",
        f"PARK_AUTH_DB={runtime / 'auth.db'}",
        f"PARK_CANONICAL_PORTFOLIO_ROOT={runtime / 'current' / 'canonical'}",
        f"PARK_CANONICAL_PORTFOLIO_SOURCE_DB={runtime / 'current' / 'research.db'}",
        f"PARK_PRIVATE_REPORT_ROOT={runtime / 'current' / 'canonical-reports'}",
        f"PARK_PRIVATE_RESEARCH_PACK={runtime / 'current' / 'research-pack'}",
        "PARK_AUTH_REQUIRED=1",
        "PARK_COOKIE_SECURE=1",
        "PARK_PRIVATE_PREVIEW=1",
        "PARK_MANUAL_PAID_PILOT=1",
    ]) + "\n"
    temporary = runtime / f".preview-env-{os.getpid()}"
    temporary.write_text(content, encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, env)


def sanitize_auth_store(runtime: Path) -> dict:
    """Atomically retain only member/feedback state in the external auth database."""
    source = runtime / "auth.db"
    if not source.is_file() or source.is_symlink():
        raise PreviewReleaseError("private preview auth database is unavailable or unsafe")
    snapshot = runtime / f".auth-source-{os.getpid()}.db"
    sanitized = runtime / f".auth-sanitized-{os.getpid()}.db"
    backup_dir = runtime / "auth-backups"
    backup_dir.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup = backup_dir / f"auth-{stamp}.db"
    try:
        copy_sqlite(source, snapshot)
        initialize_feedback(sanitized)
        initialize_billing(sanitized)
        counts: dict[str, int] = {}
        with closing(connect(sanitized)) as connection:
            connection.execute("ATTACH DATABASE ? AS legacy", (str(snapshot),))
            for table in AUTH_TABLES:
                exists = connection.execute(
                    "SELECT 1 FROM legacy.sqlite_master WHERE type='table' AND name=?", (table,),
                ).fetchone()
                if not exists:
                    continue
                target_columns = [row["name"] for row in connection.execute(f"PRAGMA main.table_info({table})")]
                source_columns = [row["name"] for row in connection.execute(f"PRAGMA legacy.table_info({table})")]
                if target_columns != source_columns:
                    raise PreviewReleaseError(f"auth table schema mismatch: {table}")
                columns = ",".join(target_columns)
                connection.execute(
                    f"INSERT INTO main.{table} ({columns}) SELECT {columns} FROM legacy.{table}"
                )
                counts[table] = connection.execute(f"SELECT COUNT(*) AS total FROM main.{table}").fetchone()["total"]
            connection.commit()
        copy_sqlite(snapshot, backup)
        os.chmod(backup, 0o600)
        os.chmod(sanitized, 0o600)
        os.replace(sanitized, source)
        initialize_feedback(source)
        return {
            "status": "sanitized",
            "auth_database": str(source),
            "backup": str(backup),
            "preserved_rows": counts,
            "research_tables_removed": True,
        }
    finally:
        snapshot.unlink(missing_ok=True)
        sanitized.unlink(missing_ok=True)


def prepare(source_db: Path, source_state: Path, deep_reports: Path, runtime: Path) -> dict:
    staging = runtime / f".staging-{os.getpid()}"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    try:
        copy_sqlite(source_db.resolve(), staging / "research.db")
        copy_state(source_state.resolve(), staging / "canonical")
        copy_product_code(PRODUCT, staging / "product")
        current = load_portfolio_state(staging / "canonical")
        copy_report_bundle(staging / "research.db", current, deep_reports.resolve(), staging / "canonical-reports")
        build_research_pack(
            staging / "canonical", staging / "canonical-reports", current, staging / "research-pack",
        )
        verified = verify_release(staging)
        release_id = verified["release_id"]
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "release_id": release_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "identity": verified["identity"],
            "files": verified["files"],
            "truth_boundary": {
                "private_preview": True,
                "accepts_payment": False,
                "manual_external_fulfillment": True,
                "online_checkout": False,
                "paid_pilot_ready": False,
                "broker_connected": False,
                "auth_database_separate": True,
            },
        }
        (staging / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        os.chmod(staging / "manifest.json", 0o600)
        verify_release(staging, expected_release_id=release_id, require_manifest=True)
        destination = runtime / "releases" / release_id
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            verify_release(destination, expected_release_id=release_id, require_manifest=True)
            shutil.rmtree(staging)
        else:
            os.replace(staging, destination)
        auth_db = runtime / "auth.db"
        initialize_auth(auth_db)
        os.chmod(auth_db, 0o600)
        point_current(runtime, release_id)
        write_runtime_env(runtime)
        return {
            "status": "prepared",
            "release_id": release_id,
            "portfolio_id": verified["identity"]["portfolio_id"],
            "snapshot_id": verified["identity"]["snapshot_id"],
            "runtime": str(runtime),
            "auth_database": "separate_and_preserved",
        }
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare or roll back the isolated private-preview runtime")
    parser.add_argument("--runtime", type=Path, default=DEFAULT_RUNTIME)
    subcommands = parser.add_subparsers(dest="command", required=True)
    build = subcommands.add_parser("prepare")
    build.add_argument("--source-db", type=Path, default=DEFAULT_SOURCE_DB)
    build.add_argument("--source-state", type=Path, default=DEFAULT_SOURCE_STATE)
    build.add_argument("--deep-reports", type=Path, default=DEFAULT_DEEP_REPORTS)
    rollback = subcommands.add_parser("rollback")
    rollback.add_argument("release_id")
    subcommands.add_parser("sanitize-auth")
    args = parser.parse_args()
    runtime = ensure_external_runtime(args.runtime)
    try:
        if args.command == "prepare":
            result = prepare(args.source_db, args.source_state, args.deep_reports, runtime)
        elif args.command == "rollback":
            point_current(runtime, args.release_id)
            write_runtime_env(runtime)
            result = {"status": "rolled_back", "release_id": args.release_id, "runtime": str(runtime)}
        else:
            result = sanitize_auth_store(runtime)
    except (CanonicalPortfolioError, PortfolioLedgerError, PreviewReleaseError, RuntimeError, sqlite3.Error) as exc:
        raise SystemExit(f"private preview preparation failed: {exc}") from exc
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
