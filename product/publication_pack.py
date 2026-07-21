from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import shutil
import socket
import stat
import struct
import subprocess
import sys
import time
import urllib.request
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from PIL import Image, UnidentifiedImageError

from data_store import DB_PATH, dump_json
from deepseek_writer import editorial_status
from research_reports import report_payload


ROOT = Path(__file__).resolve().parent
RUNTIME_DIR = ROOT / "runtime"
PACK_ROOT = RUNTIME_DIR / "publication_packs"
RENDER_VERSION = "park-report-export-v3"
NODE = Path("/Users/wendy/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node")
NODE_MODULES = Path("/Users/wendy/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules")
# Use stable Homebrew binaries for unattended LaunchAgent runs. Codex runtime
# wrappers are session-scoped and may disappear after the desktop process exits.
PDFINFO = Path("/opt/homebrew/bin/pdfinfo")
PDFTOTEXT = Path("/opt/homebrew/bin/pdftotext")
ARTIFACT_NAMES = ("report.html", "report-long.png", "report.pdf", "report.json", "render-receipt.json")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _hash_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _hash_file(path: Path) -> str:
    return _hash_bytes(path.read_bytes())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def render_logic_hash() -> str:
    digest = hashlib.sha256()
    for path in (
        ROOT / "render_publication.mjs", ROOT / "static" / "index.html",
        ROOT / "static" / "app.js", ROOT / "static" / "styles.css",
    ):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_health(base_url: str, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}/api/health", timeout=1.0) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(0.15)
    raise RuntimeError("temporary report server did not become healthy")


def publication_identity(ticker: str, db_path: Path = DB_PATH) -> tuple[dict[str, Any], dict[str, Any]]:
    report = report_payload(ticker, db_path)
    if not report or report.get("research_status") != "verified" or report.get("research_depth") != "deep":
        raise RuntimeError("publication pack requires a verified company-level deep report")
    editorial = editorial_status(ticker, db_path, snapshot_id=report["generated_from"]["snapshot_id"])
    if editorial.get("status") != "approved" or editorial.get("integrity_errors"):
        raise RuntimeError("publication pack requires a current, integrity-passed editorial approval")
    if report.get("executive", {}).get("decision_review_weight") is None:
        raise RuntimeError("publication pack cannot expose a position before the decision-review gate")
    identity = {
        "ticker": report["ticker"], "name": report["name"], "snapshot_id": report["generated_from"]["snapshot_id"],
        "publication_id": report["generated_from"]["publication_id"], "report_hash": report["report_hash"],
        "report_payload_hash": _hash_bytes(_canonical(report)), "api_payload_hash": _hash_bytes(dump_json(report)),
        "research_logic_hash": report["research_logic_hash"], "research_profile_hash": report["research_profile_hash"],
        "evidence_set_id": report["generated_from"]["evidence_set_id"],
        "evidence_manifest_hash": report["generated_from"]["evidence_manifest_hash"],
        "narrative_hash": editorial["narrative_hash"], "render_version": RENDER_VERSION,
        "render_logic_hash": render_logic_hash(),
        "release_scope": "single_report_editorial_approved_not_portfolio_executed",
    }
    return report, identity


def pack_id(identity: dict[str, Any]) -> str:
    return f"pack_{identity['ticker'].replace('.', '_')}_{_hash_bytes(_canonical(identity))[:16]}"


def _pdf_page_count(path: Path) -> int | None:
    try:
        binary = str(PDFINFO) if PDFINFO.is_file() else "pdfinfo"
        result = subprocess.run([binary, str(path)], check=True, capture_output=True, text=True, timeout=10)
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    match = re.search(r"^Pages:\s+(\d+)\s*$", result.stdout, re.MULTILINE)
    return int(match.group(1)) if match else None


def _png_size(path: Path) -> tuple[int, int] | None:
    try:
        raw = path.read_bytes()[:24]
        if len(raw) < 24 or raw[:8] != b"\x89PNG\r\n\x1a\n" or raw[12:16] != b"IHDR":
            return None
        return struct.unpack(">II", raw[16:24])
    except OSError:
        return None


def _pdf_text(path: Path) -> str | None:
    try:
        binary = str(PDFTOTEXT) if PDFTOTEXT.is_file() else "pdftotext"
        # LaunchAgents inherit a minimal C locale. Decode explicitly so Chinese
        # PDF text validation behaves exactly like an interactive run.
        result = subprocess.run(
            [binary, str(path), "-"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
        return result.stdout
    except (FileNotFoundError, subprocess.SubprocessError, UnicodeError):
        return None


def _png_has_report_code(path: Path, report_hash: str) -> bool:
    try:
        with Image.open(path) as source:
            image = source.convert("RGB")
            if image.width != 1200 or image.height < 4_000:
                return False
            bits = "".join(f"{int(digit, 16):04b}" for digit in report_hash[:16])
            colors = {"0": (0, 94, 184), "1": (11, 31, 58)}
            for y in range(min(48, image.height)):
                for x in range(max(0, image.width - 300), image.width - 128 + 1):
                    if all(image.getpixel((x + index * 2 + 1, y)) == colors[bit] for index, bit in enumerate(bits)):
                        return True
    except (OSError, UnidentifiedImageError, ValueError):
        return False
    return False


def _cross_pack_render_reuse_errors(pack_dir: Path, manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    identity = manifest.get("identity") or {}
    current_report_hash = identity.get("report_hash")
    files = manifest.get("files") or {}
    if not current_report_hash or PACK_ROOT.resolve() not in pack_dir.resolve().parents:
        return errors
    for other_manifest_path in PACK_ROOT.glob("pack_*/manifest.json"):
        if other_manifest_path.parent.resolve() == pack_dir.resolve() or other_manifest_path.is_symlink():
            continue
        try:
            other = json.loads(other_manifest_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if (other.get("identity") or {}).get("report_hash") in {None, current_report_hash}:
            continue
        other_files = other.get("files") or {}
        for name in ("report.html", "report-long.png", "report.pdf"):
            if files.get(name) and files.get(name) == other_files.get(name):
                errors.append(f"rendered artifact reused across report identities: {name}")
    return errors


def validate_pack(pack_dir: Path, *, expected_pack_id: str | None = None) -> list[str]:
    errors: list[str] = []
    pack_dir = pack_dir.resolve()
    manifest_path = pack_dir / "manifest.json"
    if not manifest_path.is_file():
        return ["manifest is missing"]
    if manifest_path.is_symlink() or manifest_path.resolve().parent != pack_dir:
        return ["manifest path is unsafe"]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return ["manifest is unreadable"]
    if manifest.get("pack_id") != (expected_pack_id or pack_dir.name):
        errors.append("pack identity mismatch")
    files = manifest.get("files") or {}
    if set(files) != set(ARTIFACT_NAMES):
        errors.append("manifest file contract mismatch")
    for name in ARTIFACT_NAMES:
        expected = files.get(name)
        path = pack_dir / name
        if path.is_symlink() or path.resolve().parent != pack_dir:
            errors.append(f"unsafe file path: {name}")
            continue
        if not path.is_file():
            errors.append(f"missing file: {name}")
        elif not isinstance(expected, str) or _hash_file(path) != expected:
            errors.append(f"file hash mismatch: {name}")
    identity = manifest.get("identity") or {}
    try:
        report = json.loads((pack_dir / "report.json").read_text(encoding="utf-8"))
    except Exception:
        report = {}
        errors.append("report JSON is unreadable")
    if report:
        for key, actual in (("ticker", report.get("ticker")), ("name", report.get("name")), ("report_hash", report.get("report_hash"))):
            if identity.get(key) != actual:
                errors.append(f"report identity mismatch: {key}")
    try:
        receipt = json.loads((pack_dir / "render-receipt.json").read_text(encoding="utf-8"))
    except Exception:
        receipt = {}
        errors.append("render receipt is unreadable")
    if receipt:
        if receipt.get("renderer") != "playwright-chromium-v3":
            errors.append("renderer version mismatch")
        for key, expected in (("ticker", identity.get("ticker")), ("companyName", identity.get("name")), ("reportHash", identity.get("report_hash"))):
            if receipt.get(key) != expected:
                errors.append(f"render receipt identity mismatch: {key}")
        expected_payload_hash = identity.get("report_payload_hash")
        if expected_payload_hash != files.get("report.json") or receipt.get("reportPayloadHash") != expected_payload_hash or receipt.get("apiPayloadHash") != identity.get("api_payload_hash"):
            errors.append("render receipt report payload mismatch")
        if not isinstance(receipt.get("textLength"), int) or receipt["textLength"] < 1_000:
            errors.append("rendered body is too short")
        if not re.fullmatch(r"[0-9a-f]{64}", str(receipt.get("bodyTextHash", ""))):
            errors.append("rendered body hash is invalid")
        audit = receipt.get("printAudit") or {}
        if audit.get("overflowCount") != 0 or not 680 <= int(audit.get("printableWidth", 0)) <= 740:
            errors.append("print layout audit failed")
    try:
        html = (pack_dir / "report.html").read_text(encoding="utf-8")
    except Exception:
        html = ""
        errors.append("report HTML is unreadable")
    if html:
        required_html = (
            identity.get("ticker", ""), identity.get("name", ""), identity.get("report_hash", ""),
            files.get("report.json", ""), f"报告指纹 {str(identity.get('report_hash', ''))[:12]}",
            'name="park-report-hash"', 'name="park-report-payload-hash"', 'class="research-report"',
        )
        if len(html) < 20_000 or any(not value or str(value) not in html for value in required_html):
            errors.append("report HTML content contract failed")
    pages = _pdf_page_count(pack_dir / "report.pdf")
    if pages is None or not 4 <= pages <= 30:
        errors.append("PDF structure or page count is invalid")
    pdf_text = _pdf_text(pack_dir / "report.pdf")
    if pdf_text is None or f"报告指纹 {str(identity.get('report_hash', ''))[:12]}" not in pdf_text:
        errors.append("PDF report fingerprint is missing")
    png_size = _png_size(pack_dir / "report-long.png")
    if png_size is None or png_size[0] != 1200 or png_size[1] < 4_000:
        errors.append("PNG structure or dimensions are invalid")
    if not _png_has_report_code(pack_dir / "report-long.png", str(identity.get("report_hash", ""))):
        errors.append("PNG report fingerprint is missing")
    errors.extend(_cross_pack_render_reuse_errors(pack_dir, manifest))
    return errors


def validate_archive(archive: Path, pack_dir: Path, *, expected_pack_id: str | None = None) -> list[str]:
    errors: list[str] = []
    pack_id_value = expected_pack_id or pack_dir.name
    required = {f"{pack_id_value}/{name}" for name in (*ARTIFACT_NAMES, "manifest.json")}
    if archive.is_symlink() or not archive.is_file():
        return ["archive is missing or unsafe"]
    try:
        with zipfile.ZipFile(archive) as bundle:
            infos = bundle.infolist()
            names = {info.filename for info in infos}
            if names != required or len(infos) != len(required):
                errors.append("archive member contract mismatch")
            if bundle.testzip() is not None:
                errors.append("archive CRC validation failed")
            for info in infos:
                mode = (info.external_attr >> 16) & 0o170000
                if info.is_dir() or mode == stat.S_IFLNK or info.filename not in required:
                    errors.append(f"unsafe archive member: {info.filename}")
                    continue
                local_name = info.filename.removeprefix(f"{pack_id_value}/")
                local = pack_dir / local_name
                if not local.is_file() or _hash_bytes(bundle.read(info)) != _hash_file(local):
                    errors.append(f"archive content mismatch: {local_name}")
    except (OSError, zipfile.BadZipFile, RuntimeError):
        errors.append("archive is unreadable")
    return errors


def latest_pack() -> dict[str, Any] | None:
    latest_path = PACK_ROOT / "latest.json"
    if not latest_path.is_file():
        return None
    try:
        receipt = json.loads(latest_path.read_text(encoding="utf-8"))
        pack_dir = Path(receipt["pack_dir"]).resolve()
        archive = Path(receipt["archive"]).resolve()
    except Exception:
        return None
    expected_archive = (PACK_ROOT / f"{receipt.get('pack_id')}.zip").resolve()
    if PACK_ROOT.resolve() not in pack_dir.parents or pack_dir.name != receipt.get("pack_id") or archive != expected_archive:
        return None
    errors = validate_pack(pack_dir)
    if archive.is_symlink() or not archive.is_file() or _hash_file(archive) != receipt.get("archive_hash"):
        errors.append("archive hash mismatch")
    else:
        errors.extend(validate_archive(archive, pack_dir))
    if not (pack_dir / "manifest.json").is_file() or _hash_file(pack_dir / "manifest.json") != receipt.get("manifest_hash"):
        errors.append("manifest receipt hash mismatch")
    try:
        manifest = json.loads((pack_dir / "manifest.json").read_text(encoding="utf-8"))
        current_identity = publication_identity(manifest["identity"]["ticker"])[1]
        if manifest.get("identity") != current_identity:
            errors.append("publication pack is stale against the current approved report")
    except Exception as exc:
        errors.append(f"current publication identity unavailable: {type(exc).__name__}")
    integrity = "passed" if not errors else ("stale" if any("stale" in item for item in errors) else "failed")
    return {**receipt, "integrity_status": integrity, "integrity_errors": errors}


def _default_renderer(base_url: str, ticker: str, output_dir: Path, report: dict[str, Any]) -> None:
    env = dict(os.environ)
    env["NODE_PATH"] = str(NODE_MODULES)
    subprocess.run([
        str(NODE), str(ROOT / "render_publication.mjs"), "--base-url", base_url,
        "--ticker", ticker, "--out-dir", str(output_dir), "--css", str(ROOT / "static" / "styles.css"),
        "--report-hash", report["report_hash"], "--report-payload-hash", _hash_file(output_dir / "report.json"),
        "--api-payload-hash", _hash_bytes(dump_json(report)),
        "--company-name", report["name"],
    ], check=True, env=env, timeout=90)


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_bytes(_canonical(payload))
    with temporary.open("rb") as handle:
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    _fsync_dir(path.parent)


def _fsync_dir(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _receipt_for(target: Path, archive: Path, manifest: dict[str, Any], status: str) -> dict[str, Any]:
    return {
        "pack_id": target.name, "status": status, "pack_dir": str(target), "archive": str(archive),
        "manifest_hash": _hash_file(target / "manifest.json"), "archive_hash": _hash_file(archive),
        "files": manifest["files"], "created_at": manifest["created_at"],
    }


def build_pack(
    ticker: str = "300750.SZ",
    db_path: Path = DB_PATH,
    *,
    renderer: Callable[[str, str, Path, dict[str, Any]], None] = _default_renderer,
) -> dict[str, Any]:
    report, identity = publication_identity(ticker, db_path)
    PACK_ROOT.mkdir(parents=True, exist_ok=True)
    target = PACK_ROOT / pack_id(identity)
    archive = target.with_suffix(".zip")
    lock_path = PACK_ROOT / ".build.lock"
    with lock_path.open("a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        for abandoned in PACK_ROOT.glob(".pack_*.staging"):
            if abandoned.is_dir() and not abandoned.is_symlink():
                shutil.rmtree(abandoned)
        if target.exists():
            existing_errors = validate_pack(target)
            if existing_errors:
                raise RuntimeError("existing deterministic pack is invalid; refusing to overwrite: " + "; ".join(existing_errors))
            if not archive.is_file():
                raise RuntimeError("existing deterministic pack archive is missing; refusing to overwrite")
            archive_errors = validate_archive(archive, target)
            if archive_errors:
                raise RuntimeError("existing deterministic pack archive is invalid; refusing to reuse: " + "; ".join(archive_errors))
            manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
            receipt = _receipt_for(target, archive, manifest, "reused")
            _atomic_json(PACK_ROOT / "latest.json", receipt)
            return receipt
        staging = PACK_ROOT / f".{target.name}.{uuid.uuid4().hex}.staging"
        staging.mkdir()
        (staging / "report.json").write_bytes(_canonical(report))

        port = _free_port()
        base_url = f"http://127.0.0.1:{port}/"
        env = dict(os.environ)
        env["PARK_DASHBOARD_DB"] = str(db_path)
        env["PARK_AUTH_REQUIRED"] = "0"
        server = subprocess.Popen(
            [sys.executable, str(ROOT / "server.py"), "--host", "127.0.0.1", "--port", str(port)],
            cwd=ROOT.parent, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            _wait_health(base_url)
            try:
                renderer(base_url, ticker.upper(), staging, report)
            except Exception:
                shutil.rmtree(staging, ignore_errors=True)
                raise
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)

        missing = [name for name in ARTIFACT_NAMES if not (staging / name).is_file()]
        if missing:
            shutil.rmtree(staging, ignore_errors=True)
            raise RuntimeError("publication renderer did not create: " + ", ".join(missing))
        current_identity = publication_identity(ticker, db_path)[1]
        if current_identity != identity:
            shutil.rmtree(staging, ignore_errors=True)
            raise RuntimeError("publication identity changed during rendering; refusing to publish a mixed-version pack")
        manifest = {
            "pack_id": target.name, "created_at": _now(), "status": "ready_for_private_distribution",
            "identity": identity, "files": {name: _hash_file(staging / name) for name in ARTIFACT_NAMES},
            "distribution_note": "单股研报已通过证据与编辑门；建议仓位仍需 Park 复核，不能解释为整期组合已批准执行。",
        }
        (staging / "manifest.json").write_bytes(_canonical(manifest))
        errors = validate_pack(staging, expected_pack_id=target.name)
        if errors:
            shutil.rmtree(staging, ignore_errors=True)
            raise RuntimeError("publication pack validation failed: " + "; ".join(errors))
        staging_archive = PACK_ROOT / f".{target.name}.{uuid.uuid4().hex}.zip.tmp"
        try:
            with zipfile.ZipFile(staging_archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
                for path in sorted(staging.iterdir()):
                    if path.is_file():
                        bundle.write(path, arcname=f"{target.name}/{path.name}")
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            staging_archive.unlink(missing_ok=True)
            raise
        archive_errors = validate_archive(staging_archive, staging, expected_pack_id=target.name)
        if archive_errors:
            shutil.rmtree(staging, ignore_errors=True)
            staging_archive.unlink(missing_ok=True)
            raise RuntimeError("publication archive validation failed: " + "; ".join(archive_errors))
        os.replace(staging, target)
        os.replace(staging_archive, archive)
        _fsync_dir(PACK_ROOT)
        receipt = _receipt_for(target, archive, manifest, "success")
        _atomic_json(PACK_ROOT / "latest.json", receipt)
        return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a fail-closed private distribution pack for an approved deep report")
    parser.add_argument("ticker", nargs="?", default="300750.SZ")
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--validate", type=Path)
    args = parser.parse_args()
    if args.validate:
        errors = validate_pack(args.validate)
        print(json.dumps({"status": "passed" if not errors else "failed", "errors": errors}, ensure_ascii=False))
        raise SystemExit(0 if not errors else 1)
    print(json.dumps(build_pack(args.ticker, args.db), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
