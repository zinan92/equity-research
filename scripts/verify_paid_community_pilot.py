#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import http.client
from io import BytesIO
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
from urllib.parse import urlparse
import zipfile

from prepare_private_preview import DEFAULT_RUNTIME, PreviewReleaseError, verify_release


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_URL = os.environ.get("PARK_PRIVATE_PREVIEW_URL", "https://research.park-ai-intel.com")
CREDENTIALS = Path(os.environ.get(
    "PARK_PRIVATE_PREVIEW_CREDENTIALS",
    "/Users/wendy/park-io/_secrets/equity-research-preview-credentials.json",
))
OUTPUT = ROOT / "evidence" / "m7-paid-community-pilot"


class VerificationError(RuntimeError):
    pass


def request(
    method: str, path: str, payload: dict | None = None, *, cookie: str | None = None,
    csrf: str | None = None,
) -> tuple[int, dict | bytes, dict[str, str]]:
    parsed = urlparse(PUBLIC_URL)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise VerificationError("invalid paid-community URL")
    headers: dict[str, str] = {}
    body = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload, ensure_ascii=False).encode()
    if cookie:
        headers["Cookie"] = cookie
    if csrf:
        headers["X-CSRF-Token"] = csrf
    connection_type = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    last_error: Exception | None = None
    for attempt in range(3):
        connection = connection_type(parsed.hostname, parsed.port, timeout=20)
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            raw = response.read()
            value = json.loads(raw) if response.getheader("Content-Type", "").startswith("application/json") else raw
            return response.status, value, {name.lower(): value for name, value in response.getheaders()}
        except (OSError, http.client.HTTPException) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(0.5 * (attempt + 1))
        finally:
            connection.close()
    raise VerificationError(f"external request failed: {type(last_error).__name__}")


def login(email: str, password: str) -> tuple[dict, str]:
    status, payload, headers = request("POST", "/api/auth/login", {"email": email, "password": password})
    if status != 200 or not isinstance(payload, dict):
        raise VerificationError(f"external login failed with HTTP {status}")
    set_cookie = headers.get("set-cookie", "")
    if not set_cookie.startswith("__Host-park_session=") or not all(item in set_cookie for item in ("Secure", "HttpOnly", "SameSite=Strict")):
        raise VerificationError("external paid-community cookie is unsafe")
    return payload, set_cookie.split(";", 1)[0]


def billing_event(cookie: str, event_type: str, provider_event_id: str) -> dict | None:
    status, payload, _ = request("GET", "/api/billing", cookie=cookie)
    if status != 200 or not isinstance(payload, dict) or not isinstance(payload.get("events"), list):
        raise VerificationError("billing event reconciliation is unavailable")
    matches = [
        event for event in payload["events"]
        if isinstance(event, dict)
        and event.get("event_type") == event_type
        and event.get("provider") == "acceptance_test"
        and event.get("provider_event_id") == provider_event_id
    ]
    if len(matches) > 1:
        raise VerificationError("billing event reconciliation found duplicate stable references")
    return matches[0] if matches else None


def verify_archive(raw: bytes, pack: dict) -> dict:
    try:
        with zipfile.ZipFile(BytesIO(raw)) as archive:
            names = sorted(archive.namelist())
            if archive.testzip() is not None or len(names) != 13:
                raise VerificationError("downloaded research pack is corrupt or incomplete")
            portfolio = json.loads(archive.read("portfolio.json"))
            positions = portfolio.get("positions") if isinstance(portfolio, dict) else None
            if not isinstance(positions, list) or len(positions) != 8:
                raise VerificationError("downloaded research pack portfolio is not the canonical 8-stock set")
            expected = sorted([
                "diff.json", "ledger-history.json", "ledger.json", "pack-manifest.json", "portfolio.json",
                *[f"reports/{position['ticker']}.json" for position in positions],
            ])
            if names != expected:
                raise VerificationError("downloaded research pack membership differs from the 8-stock contract")
            manifest = json.loads(archive.read("pack-manifest.json"))
            if not isinstance(manifest, dict):
                raise VerificationError("downloaded research pack manifest is invalid")
            pack_hash = manifest.pop("pack_hash", None)
            calculated_pack_hash = hashlib.sha256(
                json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode(),
            ).hexdigest()
            if (
                pack_hash != calculated_pack_hash
                or pack_hash != pack.get("pack_hash")
                or manifest.get("portfolio_id") != pack.get("portfolio_id")
                or manifest.get("portfolio_payload_hash") != portfolio.get("payload_hash")
                or manifest.get("snapshot_id") != portfolio.get("snapshot", {}).get("snapshot_id")
            ):
                raise VerificationError("downloaded research pack identity mismatch")
            files = manifest.get("files")
            if not isinstance(files, dict) or set(files) != set(expected) - {"pack-manifest.json"}:
                raise VerificationError("downloaded research pack file manifest differs from ZIP membership")
            actual_files = {name: hashlib.sha256(archive.read(name)).hexdigest() for name in sorted(files)}
            if actual_files != files:
                raise VerificationError("downloaded research pack member hash mismatch")
            report_hashes: dict[str, str] = {}
            for position in positions:
                report = json.loads(archive.read(f"reports/{position['ticker']}.json"))
                if report.get("report_hash") != position.get("report_binding", {}).get("report_hash"):
                    raise VerificationError(f"downloaded report binding mismatch: {position['ticker']}")
                report_hashes[position["ticker"]] = report["report_hash"]
            report_bundle_hash = hashlib.sha256(
                json.dumps(report_hashes, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(),
            ).hexdigest()
            if manifest.get("report_bundle_hash") != report_bundle_hash:
                raise VerificationError("downloaded research pack report bundle hash mismatch")
    except zipfile.BadZipFile as exc:
        raise VerificationError("downloaded research pack is not ZIP") from exc
    archive_sha256 = hashlib.sha256(raw).hexdigest()
    if archive_sha256 != pack.get("archive_sha256"):
        raise VerificationError("downloaded research pack archive hash mismatch")
    return {
        "archive_sha256": archive_sha256,
        "pack_hash": pack_hash,
        "report_bundle_hash": report_bundle_hash,
        "members": 13,
        "reports": 8,
        "all_member_hashes_verified": True,
    }


def capture_visuals() -> dict:
    command = [
        "/opt/homebrew/bin/node", str(ROOT / "product" / "deployment" / "capture_paid_community_pilot.mjs"),
        PUBLIC_URL, str(CREDENTIALS), str(OUTPUT),
    ]
    result = subprocess.run(command, cwd=ROOT / "product", text=True, capture_output=True, timeout=120, check=False)
    if result.returncode != 0:
        raise VerificationError(f"paid-community browser capture failed: {result.stderr[-500:]}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise VerificationError("paid-community browser receipt is invalid") from exc
    if payload.get("status") != "passed":
        raise VerificationError("paid-community browser capture did not pass")
    return payload


def verify_operations(final_release_id: str) -> dict:
    path = OUTPUT / "restart-rollback-receipt.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VerificationError("safe M7 rollback receipt is unavailable") from exc
    rollback = payload.get("rollback", {})
    forward = payload.get("roll_forward", {})
    tunnel = payload.get("tunnel_isolation", {})
    if (
        payload.get("schema_version") != "private-preview-ops-rehearsal-v1"
        or payload.get("status") != "passed"
        or rollback.get("release_id") == final_release_id
        or rollback.get("release_identity_verified") is not True
        or rollback.get("external_health_http") != 200
        or forward.get("release_id") != final_release_id
        or forward.get("release_identity_verified") is not True
        or forward.get("external_health_http") != 200
        or payload.get("tunnel_restart", {}).get("external_health_http") != 200
        or tunnel.get("other_tunnels_unchanged_and_active") is not True
        or payload.get("runtime_runner", {}).get("external") is not True
    ):
        raise VerificationError("safe M7 rollback/roll-forward contract failed")
    runtime = DEFAULT_RUNTIME.resolve()
    try:
        rollback_release = verify_release(
            runtime / "releases" / rollback["release_id"],
            expected_release_id=rollback["release_id"], require_manifest=True,
        )
        forward_release = verify_release(
            runtime / "releases" / final_release_id,
            expected_release_id=final_release_id, require_manifest=True,
        )
    except PreviewReleaseError as exc:
        raise VerificationError("M7 rollback release identity cannot be reproduced") from exc
    for release in (rollback_release, forward_release):
        research_pack_hash = release.get("identity", {}).get("research_pack_hash")
        if not isinstance(research_pack_hash, str) or len(research_pack_hash) != 64:
            raise VerificationError("M7 rollback release lacks a research-pack identity")
    return {
        "status": "passed",
        "rollback_release_id": rollback["release_id"],
        "roll_forward_release_id": final_release_id,
        "rollback_external_health_http": 200,
        "roll_forward_external_health_http": 200,
        "tunnel_restart_external_health_http": 200,
        "other_tunnels_unchanged_and_active": True,
        "rollback_research_pack_hash": rollback_release["identity"]["research_pack_hash"],
        "roll_forward_research_pack_hash": forward_release["identity"]["research_pack_hash"],
    }


def verify() -> dict:
    if not CREDENTIALS.is_file():
        raise VerificationError("paid-community acceptance credentials are unavailable")
    credentials = json.loads(CREDENTIALS.read_text(encoding="utf-8"))
    required = {"owner_email", "owner_password", "acceptance_email", "acceptance_password", "member_email"}
    if not required.issubset(credentials):
        raise VerificationError("paid-community acceptance credentials are incomplete")

    status, health, headers = request("GET", "/api/health")
    if status != 200 or health != {"status": "ok", "product": "park-equity-research-preview", "auth_required": True}:
        raise VerificationError("external paid-community health failed")
    for name in ("strict-transport-security", "content-security-policy", "cache-control"):
        if name not in headers:
            raise VerificationError(f"external security header missing: {name}")

    owner_auth, owner_cookie = login(credentials["owner_email"], credentials["owner_password"])
    member_auth, member_cookie = login(credentials["acceptance_email"], credentials["acceptance_password"])
    status, before_export, _ = request("GET", "/api/billing", cookie=owner_cookie)
    if status != 200 or not isinstance(before_export, dict):
        raise VerificationError("owner cannot read billing reconciliation")
    revenue_before = before_export["reconciliation"]["realized_revenue_minor"]
    status, before, _ = request("GET", "/api/billing/me", cookie=member_cookie)
    if status != 200 or not isinstance(before, dict):
        raise VerificationError("acceptance member cannot read billing status")
    existing = before["billing"]
    if existing.get("status") == "active_paid":
        raise VerificationError("acceptance identity has a real manual payment; verifier will not mutate it")
    if existing.get("status") == "active_paid_test":
        cleanup = {
            "provider": "acceptance_test", "provider_event_id": f"cleanup-refund-{secrets.token_hex(8)}",
            "refund_reference": f"cleanup-reference-{secrets.token_hex(8)}",
            "payment_event_id": existing["payment_event_id"], "occurred_at": datetime.now(timezone.utc).isoformat(),
        }
        status, _, _ = request(
            "POST", "/api/billing/refund", cleanup, cookie=owner_cookie, csrf=owner_auth["csrf_token"],
        )
        if status != 201:
            raise VerificationError("stale acceptance entitlement could not be safely cleaned up")
        member_auth, member_cookie = login(credentials["acceptance_email"], credentials["acceptance_password"])

    nonce = secrets.token_hex(8)
    occurred_at = datetime.now(timezone.utc).isoformat()
    payment_payload = {
        "provider": "acceptance_test", "provider_event_id": f"acceptance-payment-{nonce}",
        "payment_reference": f"acceptance-reference-{nonce}",
        "member_email": credentials["acceptance_email"], "amount_minor": 29_900,
        "currency": "CNY", "occurred_at": occurred_at,
    }
    status, no_csrf, _ = request("POST", "/api/billing/payment", payment_payload, cookie=owner_cookie)
    if status != 403 or not isinstance(no_csrf, dict) or no_csrf.get("error") != "csrf_rejected":
        raise VerificationError("billing payment accepted without CSRF")
    payment: dict | None = None
    controls_closed = False
    visual: dict | None = None
    archive_receipt: dict | None = None
    conflicting_replay_http: int | None = None
    old_session_revoked = False
    refund: dict | None = None
    try:
        status, value, _ = request(
            "POST", "/api/billing/payment", payment_payload, cookie=owner_cookie, csrf=owner_auth["csrf_token"],
        )
        if status != 201 or not isinstance(value, dict) or not value.get("test_mode"):
            raise VerificationError("acceptance payment did not create a test-only event")
        payment = value
        status, replay, _ = request(
            "POST", "/api/billing/payment", payment_payload, cookie=owner_cookie, csrf=owner_auth["csrf_token"],
        )
        if status != 201 or not isinstance(replay, dict) or not replay.get("idempotent") or replay.get("id") != payment["id"]:
            raise VerificationError("identical payment replay was not idempotent")
        conflict = {**payment_payload, "amount_minor": 30_000}
        conflicting_replay_http, conflict_payload, _ = request(
            "POST", "/api/billing/payment", conflict, cookie=owner_cookie, csrf=owner_auth["csrf_token"],
        )
        if conflicting_replay_http != 409 or not isinstance(conflict_payload, dict):
            raise VerificationError("conflicting payment replay did not fail closed")

        status, preview, _ = request("GET", "/api/private-preview", cookie=member_cookie)
        if (
            status != 200 or not isinstance(preview, dict) or preview.get("billing", {}).get("status") != "active_paid_test"
            or preview.get("paid_pilot", {}).get("paid_pilot_ready") is not False
            or preview.get("paid_pilot", {}).get("online_checkout") is not False
            or preview.get("research_pack", {}).get("report_count") != 8
        ):
            raise VerificationError("existing member session did not receive truthful paid entitlement")
        pack = preview["research_pack"]
        status, archive, download_headers = request(
            "GET", "/downloads/private-preview/research-pack.zip", cookie=member_cookie,
        )
        if status != 200 or not isinstance(archive, bytes) or download_headers.get("x-research-pack-hash") != pack["pack_hash"]:
            raise VerificationError("paid member could not download the bound research pack")
        archive_receipt = verify_archive(archive, pack)

        status, closed, _ = request(
            "POST", "/api/billing/settings", {"accept_new_payments": False},
            cookie=owner_cookie, csrf=owner_auth["csrf_token"],
        )
        if status != 200 or not isinstance(closed, dict) or closed.get("accept_new_payments") is not False:
            raise VerificationError("stop-new-payments control did not close")
        controls_closed = True
        blocked_payload = {
            **payment_payload, "provider_event_id": f"blocked-payment-{nonce}",
            "payment_reference": f"blocked-reference-{nonce}", "member_email": credentials["member_email"],
        }
        status, blocked, _ = request(
            "POST", "/api/billing/payment", blocked_payload, cookie=owner_cookie, csrf=owner_auth["csrf_token"],
        )
        if status != 409 or not isinstance(blocked, dict) or "stopped" not in blocked.get("detail", ""):
            raise VerificationError("stop-new-payments control did not block a new confirmation")
        status, reopened, _ = request(
            "POST", "/api/billing/settings", {"accept_new_payments": True},
            cookie=owner_cookie, csrf=owner_auth["csrf_token"],
        )
        if status != 200 or reopened.get("accept_new_payments") is not True:
            raise VerificationError("payment control did not reopen after the test")
        controls_closed = False

        visual = capture_visuals()
    finally:
        if controls_closed:
            request(
                "POST", "/api/billing/settings", {"accept_new_payments": True},
                cookie=owner_cookie, csrf=owner_auth["csrf_token"],
            )
        if payment is None:
            payment = billing_event(owner_cookie, "payment_confirmed", payment_payload["provider_event_id"])
        if payment:
            refund_payload = {
                "provider": "acceptance_test", "provider_event_id": f"acceptance-refund-{nonce}",
                "refund_reference": f"acceptance-refund-reference-{nonce}",
                "payment_event_id": payment["id"], "occurred_at": datetime.now(timezone.utc).isoformat(),
            }
            try:
                status, refund_value, _ = request(
                    "POST", "/api/billing/refund", refund_payload,
                    cookie=owner_cookie, csrf=owner_auth["csrf_token"],
                )
            except VerificationError:
                refund_value = billing_event(owner_cookie, "refund_confirmed", refund_payload["provider_event_id"])
                status = 201 if refund_value else 0
            if status != 201 or not isinstance(refund_value, dict):
                refund_value = billing_event(owner_cookie, "refund_confirmed", refund_payload["provider_event_id"])
            if not isinstance(refund_value, dict):
                raise VerificationError("acceptance refund did not complete or reconcile")
            refund = refund_value
            status, revoked, _ = request("GET", "/api/billing/me", cookie=member_cookie)
            old_session_revoked = status == 401 and isinstance(revoked, dict) and revoked.get("error") == "authentication_required"

    if not payment or not refund or not visual or not archive_receipt or not old_session_revoked:
        raise VerificationError("paid lifecycle did not reach all acceptance states")
    new_auth, new_cookie = login(credentials["acceptance_email"], credentials["acceptance_password"])
    if new_auth.get("member", {}).get("tier") == "paid":
        raise VerificationError("refunded member retained paid tier")
    status, denied, _ = request("GET", "/downloads/private-preview/research-pack.zip", cookie=new_cookie)
    if status != 403 or not isinstance(denied, dict) or denied.get("error") != "entitlement_required":
        raise VerificationError("refunded member retained research-pack entitlement")
    status, after_export, _ = request("GET", "/api/billing", cookie=owner_cookie)
    if status != 200 or after_export["reconciliation"]["realized_revenue_minor"] != revenue_before:
        raise VerificationError("acceptance lifecycle changed realized revenue")

    active_manifest = json.loads((Path("/Users/wendy/Library/Application Support/Park Equity Research Preview") / "current" / "manifest.json").read_text(encoding="utf-8"))
    operations = verify_operations(active_manifest["release_id"])
    receipt = {
        "schema_version": "paid-community-pilot-verification-v1",
        "status": "passed",
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "public_url": PUBLIC_URL,
        "release_id": active_manifest["release_id"],
        "truth_boundary": {
            "manual_external_fulfillment": True,
            "online_checkout": False,
            "payment_provider_connected": False,
            "paid_pilot_ready": False,
            "acceptance_events_are_revenue": False,
        },
        "lifecycle": {
            "payment_test_event_recorded": True,
            "idempotent_replay": True,
            "conflicting_replay_http": conflicting_replay_http,
            "existing_session_gained_entitlement": True,
            "research_pack": archive_receipt,
            "stop_new_payments_blocked_confirmation": True,
            "refund_revoked_entitlement_and_session": True,
            "realized_revenue_unchanged": True,
            "event_ids_recorded": False,
        },
        "operations": operations,
        "visual": visual,
        "credentials_recorded": False,
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "verification-receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    return receipt


def main() -> None:
    try:
        receipt = verify()
    except (OSError, KeyError, ValueError, json.JSONDecodeError, subprocess.SubprocessError, VerificationError) as exc:
        raise SystemExit(f"paid-community verification failed: {exc}") from exc
    print(json.dumps({
        "status": receipt["status"], "release_id": receipt["release_id"],
        "paid_pilot_ready": receipt["truth_boundary"]["paid_pilot_ready"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
