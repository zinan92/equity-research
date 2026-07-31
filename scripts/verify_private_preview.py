#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import time
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
PRODUCT = ROOT / "product"
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from prepare_private_preview import DEFAULT_RUNTIME, activate_release, verify_release  # noqa: E402


PUBLIC_URL = os.environ.get("PARK_PRIVATE_PREVIEW_URL", "https://research.park-ai-intel.com")
CREDENTIALS = Path(os.environ.get(
    "PARK_PRIVATE_PREVIEW_CREDENTIALS",
    "/Users/wendy/park-io/_secrets/equity-research-preview-credentials.json",
))
OUTPUT = ROOT / "evidence" / "m6-private-preview"
TUNNEL_ID = "edb2db0b-b5c7-4870-825b-bd9203e37ea5"
APP_LABEL = "com.park.equity-research-preview"
TUNNEL_LABEL = "com.park.equity-research-tunnel"


class VerificationError(RuntimeError):
    pass


def digest_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest_json(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def request(
    base_url: str,
    method: str,
    path: str,
    payload: dict | None = None,
    *,
    cookie: str | None = None,
    csrf: str | None = None,
) -> tuple[int, dict | bytes, dict[str, str]]:
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise VerificationError("invalid preview URL")
    headers: dict[str, str] = {}
    body = None
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode()
        headers["Content-Type"] = "application/json"
    if cookie:
        headers["Cookie"] = cookie
    if csrf:
        headers["X-CSRF-Token"] = csrf
    connection_type = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    last_error: OSError | http.client.HTTPException | None = None
    for attempt in range(3):
        connection = connection_type(parsed.hostname, parsed.port, timeout=20)
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


def login(base_url: str, email: str, password: str) -> tuple[dict, str, dict[str, str]]:
    status, payload, headers = request(base_url, "POST", "/api/auth/login", {"email": email, "password": password})
    if status != 200 or not isinstance(payload, dict):
        raise VerificationError(f"acceptance login failed with HTTP {status}")
    set_cookie = headers.get("set-cookie", "")
    if not set_cookie.startswith("__Host-park_session=") or "Secure" not in set_cookie or "HttpOnly" not in set_cookie or "SameSite=Strict" not in set_cookie:
        raise VerificationError("external session cookie is missing required security attributes")
    return payload, set_cookie.split(";", 1)[0], headers


def launchd_status(label: str) -> dict:
    target = f"gui/{os.getuid()}/{label}"
    result = subprocess.run(["launchctl", "print", target], text=True, capture_output=True, check=False)
    if result.returncode != 0 or "state = running" not in result.stdout:
        raise VerificationError(f"launchd service is not running: {label}")
    match = re.search(r"\n\s*pid = (\d+)", result.stdout)
    if not match:
        raise VerificationError(f"launchd service has no live PID: {label}")
    return {"label": label, "state": "running", "pid": int(match.group(1))}


def tunnel_inventory() -> list[dict]:
    listed = subprocess.run(
        ["cloudflared", "tunnel", "list", "--output", "json"],
        text=True, capture_output=True, check=True,
    )
    try:
        tunnels = json.loads(listed.stdout)
    except json.JSONDecodeError as exc:
        raise VerificationError("Cloudflare tunnel inventory is not valid JSON") from exc
    if not isinstance(tunnels, list):
        raise VerificationError("Cloudflare tunnel inventory is invalid")
    inventory: list[dict] = []
    for item in tunnels:
        tunnel_id = item.get("id") if isinstance(item, dict) else None
        if not isinstance(tunnel_id, str):
            raise VerificationError("Cloudflare tunnel inventory omitted an identity")
        detail = subprocess.run(
            ["cloudflared", "tunnel", "info", "--output", "json", tunnel_id],
            text=True, capture_output=True, check=True,
        )
        try:
            payload = json.loads(detail.stdout)
        except json.JSONDecodeError as exc:
            raise VerificationError("Cloudflare tunnel detail is not valid JSON") from exc
        connectors = payload.get("conns") if isinstance(payload, dict) else None
        if not isinstance(connectors, list):
            raise VerificationError("Cloudflare tunnel detail omitted connectors")
        inventory.append({"id": tunnel_id, "connector_count": len(connectors)})
    return sorted(inventory, key=lambda row: row["id"])


def tunnel_isolation_snapshot(inventory: list[dict]) -> dict:
    dedicated = [item for item in inventory if item["id"] == TUNNEL_ID]
    others = [item for item in inventory if item["id"] != TUNNEL_ID]
    if len(dedicated) != 1 or dedicated[0]["connector_count"] < 1:
        raise VerificationError("dedicated preview tunnel is absent or disconnected")
    return {
        "dedicated_tunnel_id": TUNNEL_ID,
        "dedicated_connector_count": dedicated[0]["connector_count"],
        "other_tunnel_count": len(others),
        "other_tunnel_ids_sha256": digest_json(sorted(item["id"] for item in others)),
        "all_other_tunnels_active": all(item["connector_count"] > 0 for item in others),
    }


def wait_external_health(attempts: int = 20) -> tuple[dict, list[int | str]]:
    observations: list[int | str] = []
    for _ in range(attempts):
        try:
            status, payload, _ = request(PUBLIC_URL, "GET", "/api/health")
            observations.append(status)
            if status == 200 and isinstance(payload, dict) and all((
                payload.get("status") == "ok",
                payload.get("product") == "park-equity-research-preview",
                payload.get("auth_required") is True,
                set(payload).issubset({"status", "product", "auth_required", "public_read_only"}),
            )):
                return payload, observations
        except (OSError, http.client.HTTPException) as exc:
            observations.append(type(exc).__name__)
        time.sleep(1)
    raise VerificationError("external health did not recover after service transition")


def restart_launchd_service(domain: str, label: str, attempts: int = 12) -> dict:
    target = f"{domain}/{label}"
    kickstart_codes: list[int] = []
    for attempt in range(attempts):
        status = subprocess.run(
            ["launchctl", "print", target], text=True, capture_output=True, check=False,
        )
        if attempt == 0 or status.returncode != 0 or "state = running" not in status.stdout:
            kicked = subprocess.run(
                ["launchctl", "kickstart", "-k", target], text=True, capture_output=True, check=False,
            )
            kickstart_codes.append(kicked.returncode)
        time.sleep(0.5)
        status = subprocess.run(
            ["launchctl", "print", target], text=True, capture_output=True, check=False,
        )
        if status.returncode == 0 and "state = running" in status.stdout:
            match = re.search(r"\n\s*pid = (\d+)", status.stdout)
            if match:
                return {"label": label, "pid": int(match.group(1)), "kickstart_codes": kickstart_codes}
    raise VerificationError(f"launchd service did not recover after restart: {label}")


def rehearse_ops(rollback_release_id: str) -> dict:
    runtime = DEFAULT_RUNTIME.resolve()
    current_manifest = json.loads((runtime / "current" / "manifest.json").read_text(encoding="utf-8"))
    current_id = current_manifest["release_id"]
    env_lines = (runtime / "preview.env").read_text(encoding="utf-8").splitlines()
    current_public_read_only = any(line == "PARK_PUBLIC_READ_ONLY=1" for line in env_lines)
    if rollback_release_id == current_id:
        raise VerificationError("rollback rehearsal requires a different prior release")
    verify_release(runtime / "releases" / current_id, expected_release_id=current_id, require_manifest=True)
    verify_release(
        runtime / "releases" / rollback_release_id,
        expected_release_id=rollback_release_id,
        require_manifest=True,
    )
    before = {item["label"]: item for item in (launchd_status(APP_LABEL), launchd_status(TUNNEL_LABEL))}
    tunnel_isolation_before = tunnel_isolation_snapshot(tunnel_inventory())
    domain = f"gui/{os.getuid()}"
    rollback_health: dict | None = None
    rollback_observations: list[int | str] = []
    try:
        activate_release(runtime, rollback_release_id, public_read_only=False)
        restart_launchd_service(domain, APP_LABEL)
        rollback_health, rollback_observations = wait_external_health()
    finally:
        activate_release(runtime, current_id, public_read_only=current_public_read_only)
        restart_launchd_service(domain, APP_LABEL)
    forward_health, forward_observations = wait_external_health()
    tunnel_restart = restart_launchd_service(domain, TUNNEL_LABEL)
    tunnel_health, tunnel_observations = wait_external_health()
    after = {item["label"]: item for item in (launchd_status(APP_LABEL), launchd_status(TUNNEL_LABEL))}
    tunnel_isolation_after = tunnel_isolation_snapshot(tunnel_inventory())
    if (
        tunnel_isolation_before["other_tunnel_count"] != tunnel_isolation_after["other_tunnel_count"]
        or tunnel_isolation_before["other_tunnel_ids_sha256"] != tunnel_isolation_after["other_tunnel_ids_sha256"]
        or not tunnel_isolation_before["all_other_tunnels_active"]
        or not tunnel_isolation_after["all_other_tunnels_active"]
    ):
        raise VerificationError("another Cloudflare tunnel changed or became inactive during rehearsal")
    app_print = subprocess.run(
        ["launchctl", "print", f"{domain}/{APP_LABEL}"], text=True, capture_output=True, check=True,
    ).stdout
    runner = str(runtime / "bin" / "run_private_preview.py")
    if runner not in app_print or f"working directory = {runtime}" not in app_print:
        raise VerificationError("installed app service still depends on the repository working tree")
    receipt = {
        "schema_version": "private-preview-ops-rehearsal-v1",
        "status": "passed",
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "public_url": PUBLIC_URL,
        "before": {
            "release_id": current_id,
            "app_pid": before[APP_LABEL]["pid"],
            "tunnel_pid": before[TUNNEL_LABEL]["pid"],
        },
        "rollback": {
            "release_id": rollback_release_id,
            "public_read_only": False,
            "release_identity_verified": True,
            "external_health_http": 200,
            "health_contract": rollback_health,
            "transition_observations": rollback_observations,
        },
        "roll_forward": {
            "release_id": current_id,
            "public_read_only": current_public_read_only,
            "release_identity_verified": True,
            "external_health_http": 200,
            "health_contract": forward_health,
            "app_pid": after[APP_LABEL]["pid"],
            "tunnel_pid": after[TUNNEL_LABEL]["pid"],
        },
        "tunnel_restart": {
            "external_health_http": 200,
            "health_contract": tunnel_health,
            "transition_observations": tunnel_observations,
            "pid": tunnel_restart["pid"],
            "kickstart_codes": tunnel_restart["kickstart_codes"],
        },
        "tunnel_isolation": {
            "before": tunnel_isolation_before,
            "after": tunnel_isolation_after,
            "other_tunnels_unchanged_and_active": True,
        },
        "runtime_runner": {"external": True, "path_recorded": False},
        "secrets_recorded": False,
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    path = OUTPUT / "restart-rollback-receipt.json"
    path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    return receipt


def verify() -> dict:
    if not CREDENTIALS.is_file():
        raise VerificationError("private preview acceptance credential file is unavailable")
    credentials = json.loads(CREDENTIALS.read_text(encoding="utf-8"))
    required = {
        "owner_email", "owner_password", "acceptance_email", "acceptance_password",
        "member_email", "member_password",
    }
    if not required.issubset(credentials):
        raise VerificationError("private preview acceptance credentials are incomplete")

    health_status, health, health_headers = request(PUBLIC_URL, "GET", "/api/health")
    if health_status != 200 or health != {"status": "ok", "product": "park-equity-research-preview", "auth_required": True}:
        raise VerificationError("external health contract failed")
    required_headers = {
        "strict-transport-security": "max-age=31536000; includeSubDomains",
        "x-content-type-options": "nosniff",
        "x-frame-options": "DENY",
        "cache-control": "no-store",
    }
    for name, expected in required_headers.items():
        if health_headers.get(name) != expected:
            raise VerificationError(f"external security header failed: {name}")
    if "frame-ancestors 'none'" not in health_headers.get("content-security-policy", ""):
        raise VerificationError("external CSP does not fail closed")

    root_status, root, _ = request(PUBLIC_URL, "GET", "/")
    if root_status != 200 or not isinstance(root, bytes) or b"PRIVATE PREVIEW" not in root:
        raise VerificationError("external login shell is unavailable")
    if "宁德时代".encode() in root or b"canonical_portfolio_" in root:
        raise VerificationError("anonymous login shell leaked research data")
    anonymous_matrix: dict[str, int] = {}
    for path in (
        "/api/private-preview", "/api/canonical/portfolio", "/api/canonical/portfolio/ledger",
        "/api/reports/300750.SZ", "/api/feedback", "/api/feedback/export",
        "/api/dashboard", "/api/committee", "/api/publications", "/api/refresh/status",
        "/api/canonical/active", "/api/canonical/portfolio/history",
        "/api/canonical/portfolio/ledger/history", "/api/stocks/300750.SZ",
        "/api/research/batches/latest", "/api/publication-packs/latest",
        "/downloads/publication-packs/fake/fake.zip",
    ):
        status, payload, _ = request(PUBLIC_URL, "GET", path)
        if status != 401 or not isinstance(payload, dict) or payload.get("error") != "authentication_required":
            raise VerificationError(f"anonymous route did not fail closed: {path}")
        anonymous_matrix[path] = status

    preview_auth, preview_cookie, _ = login(PUBLIC_URL, credentials["acceptance_email"], credentials["acceptance_password"])
    status, preview_payload, _ = request(PUBLIC_URL, "GET", "/api/private-preview", cookie=preview_cookie)
    if status != 200 or not isinstance(preview_payload, dict):
        raise VerificationError("preview member cannot load canonical first screen")
    if preview_payload.get("schema_version") != "private-preview-v1":
        raise VerificationError("private preview contract version is unexpected")
    if preview_payload.get("preview", {}).get("exact_report_bindings_verified") is not True:
        raise VerificationError("private preview did not attest exact report bindings")
    if preview_payload.get("preview", {}).get("route_surface") != "explicit_allowlist":
        raise VerificationError("private preview did not attest its explicit route allowlist")
    portfolio = preview_payload["portfolio"]
    if portfolio["portfolio_role"] != "canonical_current" or portfolio["snapshot"]["data_mode"] != "REAL" or len(portfolio["positions"]) != 8:
        raise VerificationError("external canonical portfolio truth boundary failed")
    status, denied, _ = request(PUBLIC_URL, "GET", "/api/reports/300750.SZ", cookie=preview_cookie)
    if status != 403 or not isinstance(denied, dict) or denied.get("error") != "entitlement_required":
        raise VerificationError("preview member could bypass report entitlement")
    preview_legacy_matrix: dict[str, int] = {}
    for path in (
        "/api/dashboard", "/api/committee", "/api/publications", "/api/refresh/status",
        "/api/canonical/active", "/api/canonical/portfolio", "/api/canonical/portfolio/history",
        "/api/canonical/portfolio/ledger", "/api/canonical/portfolio/ledger/history",
        "/api/stocks/300750.SZ", "/api/research/batches/latest", "/api/publication-packs/latest",
        "/downloads/publication-packs/fake/fake.zip",
    ):
        status, legacy, _ = request(PUBLIC_URL, "GET", path, cookie=preview_cookie)
        if status != 404 or not isinstance(legacy, dict) or legacy.get("error") != "private_preview_route_unavailable":
            raise VerificationError(f"preview member could read a legacy route: {path}")
        preview_legacy_matrix[path] = status

    member_auth, member_cookie, _ = login(PUBLIC_URL, credentials["member_email"], credentials["member_password"])
    report_hashes: dict[str, str] = {}
    for position in portfolio["positions"]:
        ticker = position["ticker"]
        status, report, _ = request(PUBLIC_URL, "GET", f"/api/reports/{ticker}", cookie=member_cookie)
        expected_hash = position["report_binding"]["report_hash"]
        if (
            status != 200 or not isinstance(report, dict) or report.get("ticker") != ticker
            or report.get("report_hash") != expected_hash
        ):
            raise VerificationError(f"research member report differs from canonical binding: {ticker}")
        report_hashes[ticker] = expected_hash
    feedback = {
        "page_type": "portfolio", "category": "clarity", "rating": 5,
        "message": "M6 外部 HTTPS 验收反馈：组合身份、动作与风险字段均可读取。",
    }
    status, no_csrf, _ = request(PUBLIC_URL, "POST", "/api/feedback", feedback, cookie=member_cookie)
    if status != 403 or not isinstance(no_csrf, dict) or no_csrf.get("error") != "csrf_rejected":
        raise VerificationError("external feedback accepted a request without CSRF")
    status, feedback_result, _ = request(
        PUBLIC_URL, "POST", "/api/feedback", feedback, cookie=member_cookie, csrf=member_auth["csrf_token"],
    )
    feedback_status = status
    if status not in {201, 400}:
        raise VerificationError("external feedback flow failed")

    owner_auth, owner_cookie, _ = login(PUBLIC_URL, credentials["owner_email"], credentials["owner_password"])
    status, members, _ = request(PUBLIC_URL, "GET", "/api/members", cookie=owner_cookie)
    if status != 200 or len(members.get("members", [])) < 3:
        raise VerificationError("owner member view failed")
    status, feedback_rows, _ = request(PUBLIC_URL, "GET", "/api/feedback", cookie=owner_cookie)
    matching = [item for item in feedback_rows.get("feedback", []) if item.get("message") == feedback["message"]]
    if status != 200 or not matching or matching[0].get("page_identity") != portfolio["payload_hash"]:
        raise VerificationError("owner feedback audit does not bind the canonical page identity")
    if feedback_result.get("error") not in {None, "feedback_rejected"}:
        raise VerificationError("unexpected feedback verifier result")
    if feedback_status == 400 and "duplicate feedback" not in str(feedback_result.get("detail", "")):
        raise VerificationError("feedback acceptance was masked by an unrelated rejection")
    status, owner_download, _ = request(
        PUBLIC_URL, "GET", "/downloads/publication-packs/fake/fake.zip", cookie=owner_cookie,
    )
    if status != 404 or not isinstance(owner_download, dict) or owner_download.get("error") != "private_preview_route_unavailable":
        raise VerificationError("private preview owner retained a legacy download surface")

    signup_email = f"preview-flow-{int(time.time())}-{secrets.token_hex(3)}@example.com"
    status, invite, _ = request(
        PUBLIC_URL, "POST", "/api/invites", {"tier": "preview", "max_uses": 1, "valid_days": 1},
        cookie=owner_cookie, csrf=owner_auth["csrf_token"],
    )
    if status != 201 or not isinstance(invite, dict) or not invite.get("code"):
        raise VerificationError("owner could not create a one-use acceptance invite")
    signup_password = secrets.token_urlsafe(18)
    status, signup_auth, signup_headers = request(
        PUBLIC_URL, "POST", "/api/auth/signup",
        {"invite_code": invite["code"], "email": signup_email, "password": signup_password, "display_name": "Acceptance Flow"},
    )
    signup_cookie = signup_headers.get("set-cookie", "").split(";", 1)[0]
    if status != 200 or not isinstance(signup_auth, dict) or not signup_cookie:
        raise VerificationError("invite signup flow failed")
    status, signed_out, clear_headers = request(
        PUBLIC_URL, "POST", "/api/auth/logout", {}, cookie=signup_cookie, csrf=signup_auth["csrf_token"],
    )
    if status != 200 or signed_out.get("status") != "signed_out" or "Max-Age=0" not in clear_headers.get("set-cookie", ""):
        raise VerificationError("member logout flow failed")
    status, after_logout, _ = request(PUBLIC_URL, "GET", "/api/private-preview", cookie=signup_cookie)
    if status != 401 or after_logout.get("error") != "authentication_required":
        raise VerificationError("logged-out session remained usable")
    status, suspended, _ = request(
        PUBLIC_URL, "POST", "/api/members/status", {"email": signup_email, "status": "suspended"},
        cookie=owner_cookie, csrf=owner_auth["csrf_token"],
    )
    if status != 200 or suspended.get("status") != "suspended":
        raise VerificationError("acceptance member cleanup failed")

    runtime = DEFAULT_RUNTIME.resolve()
    manifest = json.loads((runtime / "current" / "manifest.json").read_text(encoding="utf-8"))
    release = verify_release(runtime / "current", expected_release_id=manifest["release_id"], require_manifest=True)
    if release["identity"]["portfolio_id"] != portfolio["portfolio_id"]:
        raise VerificationError("external portfolio differs from active runtime release")
    if set(report_hashes) != {item["ticker"] for item in portfolio["positions"]}:
        raise VerificationError("external report bundle coverage differs from the portfolio")
    ops_path = OUTPUT / "restart-rollback-receipt.json"
    ops = json.loads(ops_path.read_text(encoding="utf-8"))
    rollback_id = ops.get("rollback", {}).get("release_id")
    if (
        ops.get("status") != "passed" or ops.get("public_url") != PUBLIC_URL
        or ops.get("roll_forward", {}).get("release_id") != manifest["release_id"]
        or ops.get("rollback", {}).get("external_health_http") != 200
        or ops.get("roll_forward", {}).get("external_health_http") != 200
        or ops.get("tunnel_restart", {}).get("external_health_http") != 200
        or ops.get("runtime_runner", {}).get("external") is not True
        or ops.get("tunnel_isolation", {}).get("other_tunnels_unchanged_and_active") is not True
        or not isinstance(rollback_id, str)
    ):
        raise VerificationError("restart/rollback rehearsal receipt is incomplete or stale")
    verify_release(runtime / "releases" / rollback_id, expected_release_id=rollback_id, require_manifest=True)
    services = [launchd_status(APP_LABEL), launchd_status(TUNNEL_LABEL)]
    isolation = tunnel_isolation_snapshot(tunnel_inventory())
    recorded_isolation = ops["tunnel_isolation"]["after"]
    if (
        isolation["other_tunnel_count"] != recorded_isolation.get("other_tunnel_count")
        or isolation["other_tunnel_ids_sha256"] != recorded_isolation.get("other_tunnel_ids_sha256")
        or not isolation["all_other_tunnels_active"]
    ):
        raise VerificationError("Cloudflare tunnel isolation evidence is stale")
    runtime_config = runtime / "cloudflared.yml"
    config_text = runtime_config.read_text(encoding="utf-8")
    tunnel_service = subprocess.run(
        ["launchctl", "print", f"gui/{os.getuid()}/{TUNNEL_LABEL}"],
        text=True, capture_output=True, check=True,
    ).stdout
    if (
        f"tunnel: {TUNNEL_ID}" not in config_text
        or "hostname: research.park-ai-intel.com" not in config_text
        or str(runtime_config) not in tunnel_service
        or TUNNEL_ID not in tunnel_service
    ):
        raise VerificationError("dedicated tunnel service is not bound to its isolated config")
    tunnel = subprocess.run(
        ["cloudflared", "tunnel", "info", TUNNEL_ID], text=True, capture_output=True, check=False,
    )
    if tunnel.returncode != 0 or TUNNEL_ID not in tunnel.stdout or "CONNECTOR ID" not in tunnel.stdout:
        raise VerificationError("dedicated Cloudflare tunnel has no active connector")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    capture = subprocess.run(
        [
            "node", str(PRODUCT / "deployment" / "capture_private_preview.mjs"), PUBLIC_URL,
            str(CREDENTIALS), str(OUTPUT),
        ],
        text=True, capture_output=True, check=False, timeout=90,
    )
    if capture.returncode != 0:
        raise VerificationError("independent authenticated browser capture failed")
    visual = json.loads(capture.stdout)
    if visual.get("status") != "passed" or visual["desktop"]["portfolioId"] != portfolio["portfolio_id"] or visual["mobile"]["portfolioId"] != portfolio["portfolio_id"]:
        raise VerificationError("browser capture does not match canonical portfolio")

    safe_health_headers = {
        name: health_headers[name]
        for name in set(required_headers) | {"content-security-policy"}
        if name in health_headers
    }
    return {
        "schema_version": "private-preview-verification-v1",
        "status": "passed",
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "public_url": PUBLIC_URL,
        "health": health,
        "security_headers": safe_health_headers,
        "anonymous_matrix": anonymous_matrix,
        "entitlement_matrix": {
            "preview": {"canonical_portfolio": 200, "deep_report": 403},
            "member": {"canonical_portfolio": 200, "deep_report": 200, "feedback": "accepted_or_idempotently_reused"},
            "owner": {"members": 200, "feedback_audit": 200},
        },
        "preview_legacy_route_matrix": preview_legacy_matrix,
        "cookie_contract": "__Host + Secure + HttpOnly + SameSite=Strict",
        "csrf_negative_path": "rejected_403",
        "portfolio_id": portfolio["portfolio_id"],
        "snapshot_id": portfolio["snapshot"]["snapshot_id"],
        "release_id": manifest["release_id"],
        "product_code_hash": release["identity"]["product_code_hash"],
        "report_bundle_hash": release["identity"]["report_bundle_hash"],
        "exact_report_hashes": report_hashes,
        "signup_logout_flow": "passed_and_session_revoked",
        "restart_rollback_receipt": {"status": "verified", "rollback_release_id": rollback_id},
        "feedback_page_identity_verified": True,
        "services": services,
        "tunnel": {
            "id": TUNNEL_ID,
            "active_connector": True,
            "config_sha256": digest_file(runtime_config),
            "launchd_config_binding_verified": True,
            "isolation": isolation,
        },
        "visual": visual,
        "credential_values_recorded": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify the private preview or rehearse its reversible operations")
    parser.add_argument("--rehearse-ops", action="store_true")
    parser.add_argument("--rollback-release")
    args = parser.parse_args()
    if args.rehearse_ops:
        if not args.rollback_release:
            raise SystemExit("--rollback-release is required with --rehearse-ops")
        try:
            receipt = rehearse_ops(args.rollback_release)
        except (OSError, KeyError, ValueError, json.JSONDecodeError, VerificationError, subprocess.SubprocessError) as exc:
            raise SystemExit(f"private preview ops rehearsal failed: {exc}") from exc
        print(json.dumps({
            "status": receipt["status"],
            "rollback_release_id": receipt["rollback"]["release_id"],
            "roll_forward_release_id": receipt["roll_forward"]["release_id"],
            "tunnel_restart": "passed",
        }, ensure_ascii=False, indent=2))
        return
    try:
        receipt = verify()
    except (OSError, KeyError, ValueError, json.JSONDecodeError, VerificationError, subprocess.SubprocessError) as exc:
        raise SystemExit(f"private preview verification failed: {exc}") from exc
    path = OUTPUT / "verification-receipt.json"
    path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": receipt["status"],
        "public_url": receipt["public_url"],
        "portfolio_id": receipt["portfolio_id"],
        "release_id": receipt["release_id"],
        "desktop": receipt["visual"]["desktop"]["screenshot"],
        "mobile": receipt["visual"]["mobile"]["screenshot"],
        "receipt_sha256": digest_file(path),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
