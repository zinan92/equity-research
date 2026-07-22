#!/usr/bin/env python3
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import hashlib
import http.client
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
PRODUCT = ROOT / "product"
SCRIPTS = ROOT / "scripts"
for item in (PRODUCT, SCRIPTS):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from auth_store import create_owner  # noqa: E402
from feedback_store import FeedbackError, initialize_feedback  # noqa: E402
from portfolio_allocation import digest  # noqa: E402
from prepare_private_preview import (  # noqa: E402
    DEFAULT_RUNTIME,
    PreviewReleaseError,
    ensure_external_runtime,
    verify_release,
)


PUBLIC_URL = os.environ.get("PARK_PRIVATE_PREVIEW_URL", "https://research.park-ai-intel.com")
CREDENTIALS = Path(os.environ.get(
    "PARK_PRIVATE_PREVIEW_CREDENTIALS",
    "/Users/wendy/park-io/_secrets/equity-research-preview-credentials.json",
))
OUTPUT = ROOT / "evidence" / "m6-private-preview" / "adversarial-review.json"


class AdversarialFailure(RuntimeError):
    pass


def http_request(
    method: str,
    path: str,
    payload: dict | None = None,
    *,
    cookie: str | None = None,
    csrf: str | None = None,
) -> tuple[int, dict | bytes, dict[str, str]]:
    parsed = urlparse(PUBLIC_URL)
    headers: dict[str, str] = {}
    body = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload, ensure_ascii=False).encode()
    if cookie:
        headers["Cookie"] = cookie
    if csrf:
        headers["X-CSRF-Token"] = csrf
    last_error: OSError | http.client.HTTPException | None = None
    for attempt in range(3):
        connection = http.client.HTTPSConnection(parsed.hostname, parsed.port, timeout=20)
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            raw = response.read()
            value = json.loads(raw) if response.getheader("Content-Type", "").startswith("application/json") else raw
            response_headers = {name.lower(): value for name, value in response.getheaders()}
            return response.status, value, response_headers
        except (OSError, http.client.HTTPException) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(0.5 * (attempt + 1))
        finally:
            connection.close()
    assert last_error is not None
    raise last_error


def login(email: str, password: str) -> tuple[dict, str]:
    status, payload, headers = http_request("POST", "/api/auth/login", {"email": email, "password": password})
    if status != 200 or not isinstance(payload, dict):
        raise AdversarialFailure("acceptance identity could not log in")
    return payload, headers["set-cookie"].split(";", 1)[0]


def must_reject(label: str, operation, expected: type[BaseException]) -> dict:
    try:
        operation()
    except expected as exc:
        return {"attack": label, "status": "rejected", "failure_class": type(exc).__name__}
    raise AdversarialFailure(f"attack was accepted: {label}")


def verify() -> dict:
    if not CREDENTIALS.is_file():
        raise AdversarialFailure("acceptance credentials are unavailable")
    credentials = json.loads(CREDENTIALS.read_text(encoding="utf-8"))
    checks: list[dict] = []

    for path in (
        "/api/private-preview", "/api/reports/300750.SZ", "/api/feedback/export",
        "/downloads/publication-packs/fake/fake.zip",
    ):
        status, payload, _ = http_request("GET", path)
        if status != 401 or not isinstance(payload, dict) or payload.get("error") != "authentication_required":
            raise AdversarialFailure(f"anonymous data attack succeeded: {path}")
        checks.append({"attack": f"anonymous:{path}", "status": "rejected", "http": status})

    status, payload, _ = http_request("GET", "/api/private-preview", cookie="__Host-park_session=forged")
    if status != 401 or not isinstance(payload, dict) or payload.get("error") != "authentication_required":
        raise AdversarialFailure("forged session attack succeeded")
    checks.append({"attack": "forged_session", "status": "rejected", "http": status})

    preview_auth, preview_cookie = login(credentials["acceptance_email"], credentials["acceptance_password"])
    status, payload, _ = http_request("GET", "/api/reports/300750.SZ", cookie=preview_cookie)
    if status != 403 or not isinstance(payload, dict) or payload.get("error") != "entitlement_required":
        raise AdversarialFailure("preview entitlement escalation succeeded")
    checks.append({"attack": "preview_reads_member_report", "status": "rejected", "http": status})
    status, payload, _ = http_request("GET", "/api/members", cookie=preview_cookie)
    if status != 403:
        raise AdversarialFailure("preview owner escalation succeeded")
    checks.append({"attack": "preview_reads_owner_members", "status": "rejected", "http": status})
    for path in (
        "/api/dashboard", "/api/committee", "/api/publications", "/api/refresh/status",
        "/api/canonical/active", "/api/canonical/portfolio", "/api/canonical/portfolio/history",
        "/api/canonical/portfolio/ledger", "/api/canonical/portfolio/ledger/history",
        "/api/stocks/300750.SZ", "/api/research/batches/latest", "/api/publication-packs/latest",
        "/downloads/publication-packs/fake/fake.zip",
    ):
        status, payload, _ = http_request("GET", path, cookie=preview_cookie)
        if status != 404 or not isinstance(payload, dict) or payload.get("error") != "private_preview_route_unavailable":
            raise AdversarialFailure(f"preview legacy-route access succeeded: {path}")
        checks.append({"attack": f"preview_legacy_route:{path}", "status": "rejected", "http": status})

    feedback = {
        "page_type": "portfolio", "category": "risk", "rating": 3,
        "message": "对抗验收：没有 CSRF 的反馈请求必须被拒绝。",
    }
    status, payload, _ = http_request("POST", "/api/feedback", feedback, cookie=preview_cookie)
    if status != 403 or not isinstance(payload, dict) or payload.get("error") != "csrf_rejected":
        raise AdversarialFailure("CSRF bypass succeeded")
    checks.append({"attack": "feedback_without_csrf", "status": "rejected", "http": status})
    if not preview_auth.get("csrf_token"):
        raise AdversarialFailure("preview session omitted CSRF binding")

    owner_auth, owner_cookie = login(credentials["owner_email"], credentials["owner_password"])
    for path in ("/api/refresh", "/api/research/batches", "/api/publications/legacy/approve"):
        status, payload, _ = http_request("POST", path, {}, cookie=owner_cookie, csrf=owner_auth["csrf_token"])
        if status != 404 or not isinstance(payload, dict) or payload.get("error") != "private_preview_route_unavailable":
            raise AdversarialFailure(f"owner mutated an immutable private release: {path}")
        checks.append({"attack": f"owner_research_mutation:{path}", "status": "rejected", "http": status})
    status, payload, _ = http_request(
        "GET", "/downloads/publication-packs/fake/fake.zip", cookie=owner_cookie,
    )
    if status != 404 or not isinstance(payload, dict) or payload.get("error") != "private_preview_route_unavailable":
        raise AdversarialFailure("owner retained a legacy publication download surface")
    checks.append({"attack": "owner_legacy_download", "status": "rejected", "http": status})

    active = DEFAULT_RUNTIME.resolve() / "current"
    manifest = json.loads((active / "manifest.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="m6-adversarial-") as temporary:
        temp = Path(temporary)
        code_tamper = temp / "code-tamper"
        shutil.copytree(active, code_tamper, symlinks=False)
        with (code_tamper / "product" / "static" / "index.html").open("ab") as handle:
            handle.write(b"\n<!-- tampered -->\n")
        checks.append(must_reject(
            "packaged_code_tamper",
            lambda: verify_release(code_tamper, expected_release_id=manifest["release_id"], require_manifest=True),
            PreviewReleaseError,
        ))

        missing_manifest = temp / "missing-manifest"
        shutil.copytree(active, missing_manifest, symlinks=False)
        (missing_manifest / "manifest.json").unlink()
        checks.append(must_reject(
            "release_without_manifest",
            lambda: verify_release(missing_manifest, expected_release_id=manifest["release_id"], require_manifest=True),
            PreviewReleaseError,
        ))

        diff_tamper = temp / "diff-tamper"
        shutil.copytree(active, diff_tamper, symlinks=False)
        diff_path = diff_tamper / "canonical" / "latest-diff.json"
        false_diff = json.loads(diff_path.read_text(encoding="utf-8"))
        false_diff["changes"][0]["reason"] += " 伪造理由"
        false_diff.pop("diff_hash", None)
        false_diff["diff_hash"] = digest(false_diff)
        diff_path.write_text(json.dumps(false_diff, ensure_ascii=False), encoding="utf-8")
        (diff_tamper / "manifest.json").unlink()
        checks.append(must_reject(
            "self_consistent_false_portfolio_diff",
            lambda: verify_release(diff_tamper),
            PreviewReleaseError,
        ))

        report_tamper = temp / "report-tamper"
        shutil.copytree(active, report_tamper, symlinks=False)
        report_path = next((report_tamper / "canonical-reports").glob("*.json"))
        report_path.unlink()
        (report_tamper / "manifest.json").unlink()
        checks.append(must_reject(
            "canonical_report_bundle_missing_member",
            lambda: verify_release(report_tamper),
            PreviewReleaseError,
        ))

        data_tamper = temp / "data-tamper"
        shutil.copytree(active, data_tamper, symlinks=False)
        with closing(sqlite3.connect(data_tamper / "research.db")) as connection:
            connection.execute(
                "UPDATE stock_features SET value_score=value_score+0.001 "
                "WHERE rowid=(SELECT rowid FROM stock_features LIMIT 1)"
            )
            connection.commit()
        checks.append(must_reject(
            "attested_research_row_tamper",
            lambda: verify_release(data_tamper, expected_release_id=manifest["release_id"]),
            RuntimeError,
        ))

        auth_db = temp / "auth.db"
        create_owner("adversary@example.com", "adversarial-password", "Adversary", auth_db)
        initialize_feedback(auth_db)
        with closing(sqlite3.connect(auth_db)) as connection:
            connection.execute("DROP TRIGGER member_feedback_no_delete")
            connection.execute(
                "CREATE TRIGGER member_feedback_no_delete BEFORE DELETE ON member_feedback BEGIN SELECT 1; END"
            )
            connection.commit()
        checks.append(must_reject(
            "feedback_append_only_guard_replaced",
            lambda: initialize_feedback(auth_db),
            FeedbackError,
        ))

    checks.append(must_reject(
        "runtime_inside_repository",
        lambda: ensure_external_runtime(ROOT / ".unsafe-preview-runtime"),
        PreviewReleaseError,
    ))
    environment = dict(os.environ)
    environment.update({
        "PARK_PRIVATE_PREVIEW": "1", "PARK_AUTH_REQUIRED": "0", "PARK_COOKIE_SECURE": "0",
        "PARK_DASHBOARD_DB": str(DEFAULT_RUNTIME / "current" / "research.db"),
    })
    insecure = subprocess.run(
        [sys.executable, str(PRODUCT / "server.py"), "--host", "127.0.0.1", "--port", "18878"],
        text=True, capture_output=True, env=environment, timeout=15, check=False,
    )
    if insecure.returncode == 0 or "private preview requires" not in insecure.stderr:
        raise AdversarialFailure("insecure private-preview startup did not fail closed")
    checks.append({"attack": "insecure_private_preview_startup", "status": "rejected", "exit_code": insecure.returncode})

    shared = dict(os.environ)
    shared.update({
        "PARK_PRIVATE_PREVIEW": "1", "PARK_AUTH_REQUIRED": "1", "PARK_COOKIE_SECURE": "1",
        "PARK_DASHBOARD_DB": str(DEFAULT_RUNTIME / "current" / "research.db"),
        "PARK_AUTH_DB": str(DEFAULT_RUNTIME / "current" / "research.db"),
        "PARK_CANONICAL_PORTFOLIO_ROOT": str(DEFAULT_RUNTIME / "current" / "canonical"),
        "PARK_CANONICAL_PORTFOLIO_SOURCE_DB": str(DEFAULT_RUNTIME / "current" / "research.db"),
        "PARK_PRIVATE_REPORT_ROOT": str(DEFAULT_RUNTIME / "current" / "canonical-reports"),
    })
    shared_db = subprocess.run(
        [sys.executable, str(PRODUCT / "server.py"), "--host", "127.0.0.1", "--port", "18880"],
        text=True, capture_output=True, env=shared, timeout=15, check=False,
    )
    if shared_db.returncode == 0 or "auth database must be separate" not in shared_db.stderr:
        raise AdversarialFailure("private preview accepted a shared research/auth database")
    checks.append({"attack": "shared_research_auth_database", "status": "rejected", "exit_code": shared_db.returncode})

    verification = json.loads((ROOT / "evidence" / "m6-private-preview" / "verification-receipt.json").read_text(encoding="utf-8"))
    for device in ("desktop", "mobile"):
        screenshot = Path(verification["visual"][device]["screenshot"]["path"])
        actual = hashlib.sha256(screenshot.read_bytes()).hexdigest()
        recorded = verification["visual"][device]["screenshot"]["sha256"]
        if actual != recorded:
            raise AdversarialFailure(f"{device} screenshot differs from the browser receipt")
        with tempfile.NamedTemporaryFile(prefix=f"m6-{device}-", suffix=".png") as modified:
            modified.write(screenshot.read_bytes() + b"tamper")
            modified.flush()
            if hashlib.sha256(Path(modified.name).read_bytes()).hexdigest() == recorded:
                raise AdversarialFailure(f"modified {device} screenshot was not detectable")
        checks.append({"attack": f"modified_{device}_screenshot", "status": "detected", "original_sha256_matches": True})

    return {
        "schema_version": "private-preview-adversarial-review-v1",
        "status": "passed",
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "public_url": PUBLIC_URL,
        "release_id": manifest["release_id"],
        "attacks": checks,
        "summary": {"P0": 0, "P1": 0, "P2": 0, "attacks_rejected_or_detected": len(checks)},
        "credential_values_recorded": False,
    }


def main() -> None:
    try:
        receipt = verify()
    except (OSError, KeyError, ValueError, json.JSONDecodeError, sqlite3.Error, subprocess.SubprocessError, AdversarialFailure) as exc:
        raise SystemExit(f"private preview adversarial verification failed: {exc}") from exc
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": receipt["status"], "release_id": receipt["release_id"], **receipt["summary"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
