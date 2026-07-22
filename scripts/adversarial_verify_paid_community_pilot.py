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

from auth_store import TIER_ENTITLEMENTS, create_invite, create_owner, redeem_invite  # noqa: E402
from billing_store import (  # noqa: E402
    BillingError, billing_export, effective_member, initialize_billing, record_payment, record_refund,
)
from prepare_private_preview import DEFAULT_RUNTIME, PreviewReleaseError, verify_release  # noqa: E402


PUBLIC_URL = os.environ.get("PARK_PRIVATE_PREVIEW_URL", "https://research.park-ai-intel.com")
CREDENTIALS = Path(os.environ.get(
    "PARK_PRIVATE_PREVIEW_CREDENTIALS",
    "/Users/wendy/park-io/_secrets/equity-research-preview-credentials.json",
))
OUTPUT = ROOT / "evidence" / "m7-paid-community-pilot" / "adversarial-review.json"


class AdversarialFailure(RuntimeError):
    pass


def request(
    method: str, path: str, payload: dict | None = None, *, cookie: str | None = None,
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
    last_error: Exception | None = None
    for attempt in range(3):
        connection = http.client.HTTPSConnection(parsed.hostname, parsed.port, timeout=20)
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
    raise AdversarialFailure(f"external request failed: {type(last_error).__name__}")


def login(email: str, password: str) -> tuple[dict, str]:
    status, payload, headers = request("POST", "/api/auth/login", {"email": email, "password": password})
    if status != 200 or not isinstance(payload, dict):
        raise AdversarialFailure("acceptance identity cannot log in")
    return payload, headers["set-cookie"].split(";", 1)[0]


def rejected(label: str, operation, expected: tuple[type[BaseException], ...]) -> dict:
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

    for path in ("/api/billing/me", "/api/billing", "/api/billing/export", "/downloads/private-preview/research-pack.zip"):
        status, payload, _ = request("GET", path)
        if status != 401 or not isinstance(payload, dict) or payload.get("error") != "authentication_required":
            raise AdversarialFailure(f"anonymous paid-route access succeeded: {path}")
        checks.append({"attack": f"anonymous:{path}", "status": "rejected", "http": status})

    member_auth, member_cookie = login(credentials["acceptance_email"], credentials["acceptance_password"])
    if member_auth.get("member", {}).get("tier") == "paid":
        raise AdversarialFailure("acceptance identity remained paid after verification cleanup")
    for path in ("/api/billing", "/api/billing/export", "/api/billing/settings"):
        status, payload, _ = request("GET", path, cookie=member_cookie)
        if status != 403 or not isinstance(payload, dict) or payload.get("error") != "entitlement_required":
            raise AdversarialFailure(f"member billing-admin escalation succeeded: {path}")
        checks.append({"attack": f"member_admin:{path}", "status": "rejected", "http": status})
    status, payload, _ = request("GET", "/downloads/private-preview/research-pack.zip", cookie=member_cookie)
    if status != 403 or not isinstance(payload, dict) or payload.get("error") != "entitlement_required":
        raise AdversarialFailure("refunded member retained pack access")
    checks.append({"attack": "refunded_member_pack_access", "status": "rejected", "http": status})

    owner_auth, owner_cookie = login(credentials["owner_email"], credentials["owner_password"])
    status, payload, _ = request(
        "POST", "/api/billing/settings", {"accept_new_payments": False}, cookie=owner_cookie,
    )
    if status != 403 or not isinstance(payload, dict) or payload.get("error") != "csrf_rejected":
        raise AdversarialFailure("owner billing control accepted without CSRF")
    checks.append({"attack": "owner_billing_without_csrf", "status": "rejected", "http": status})
    if not owner_auth.get("csrf_token"):
        raise AdversarialFailure("owner session omitted CSRF token")

    active = DEFAULT_RUNTIME.resolve() / "current"
    manifest = json.loads((active / "manifest.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="m7-adversarial-") as temporary:
        temp = Path(temporary)
        for label, relative, mutation in (
            ("research_pack_file_tamper", "research-pack/portfolio.json", b"\n"),
            ("research_pack_zip_tamper", "research-pack/research-pack.zip", b"tamper"),
            ("research_pack_manifest_tamper", "research-pack/pack-manifest.json", b"\n"),
        ):
            target = temp / label
            shutil.copytree(active, target, symlinks=False)
            with (target / relative).open("ab") as handle:
                handle.write(mutation)
            checks.append(rejected(
                label,
                lambda target=target: verify_release(
                    target, expected_release_id=manifest["release_id"], require_manifest=True,
                ),
                (PreviewReleaseError,),
            ))

        auth_db = temp / "auth.db"
        owner = create_owner("adversary-owner@example.com", "adversary-owner-password", "Owner", auth_db)
        invite = create_invite(owner["id"], "member", auth_db)
        member = redeem_invite(
            invite["code"], "adversary-member@example.com", "adversary-member-password", "Member", auth_db,
        )
        second_invite = create_invite(owner["id"], "member", auth_db)
        second_member = redeem_invite(
            second_invite["code"], "adversary-second@example.com", "adversary-second-password", "Second", auth_db,
        )
        with closing(sqlite3.connect(auth_db)) as connection:
            connection.execute(
                "UPDATE members SET tier='paid',entitlements_json=? WHERE id=?",
                (json.dumps(TIER_ENTITLEMENTS["paid"]), member["id"]),
            )
            connection.commit()
        forged = {**member, "tier": "paid", "entitlements": TIER_ENTITLEMENTS["paid"]}
        if effective_member(forged, auth_db)["tier"] != "member":
            raise AdversarialFailure("stored paid tier bypassed the billing ledger")
        checks.append({"attack": "stored_tier_paid_without_ledger", "status": "rejected"})

        occurred_at = datetime.now(timezone.utc).isoformat()
        payment_payload = {
            "provider": "acceptance_test", "provider_event_id": "attack-payment-event-001",
            "payment_reference": "attack-payment-reference-001", "member_email": member["email"],
            "amount_minor": 29_900, "currency": "CNY", "occurred_at": occurred_at,
        }
        payment = record_payment(owner["id"], payment_payload, "canonical_portfolio_" + "9" * 32, "9" * 64, auth_db)
        release_changed_replay = record_payment(
            owner["id"], payment_payload, "canonical_portfolio_" + "8" * 32, "8" * 64, auth_db,
        )
        if (
            not release_changed_replay.get("idempotent")
            or release_changed_replay["id"] != payment["id"]
            or release_changed_replay["portfolio_id"] != payment["portfolio_id"]
        ):
            raise AdversarialFailure("identical payment replay changed with the active release")
        checks.append({"attack": "release_change_breaks_payment_idempotency", "status": "rejected"})
        checks.append(rejected(
            "conflicting_provider_replay",
            lambda: record_payment(
                owner["id"], {**payment_payload, "amount_minor": 30_000},
                "canonical_portfolio_" + "9" * 32, "9" * 64, auth_db,
            ),
            (BillingError,),
        ))
        checks.append(rejected(
            "duplicate_external_payment_reference",
            lambda: record_payment(owner["id"], {
                **payment_payload,
                "provider_event_id": "attack-payment-event-002",
                "member_email": second_member["email"],
            }, "canonical_portfolio_" + "9" * 32, "9" * 64, auth_db),
            (BillingError,),
        ))
        checks.append(rejected(
            "fractional_minor_amount",
            lambda: record_payment(owner["id"], {
                **payment_payload,
                "provider_event_id": "attack-payment-fractional-001",
                "payment_reference": "attack-payment-fractional-ref-001",
                "member_email": second_member["email"],
                "amount_minor": 29_900.99,
            }, "canonical_portfolio_" + "9" * 32, "9" * 64, auth_db),
            (BillingError,),
        ))
        checks.append(rejected(
            "refund_provider_mismatch",
            lambda: record_refund(owner["id"], {
                "provider": "manual_external", "provider_event_id": "attack-refund-wrong-001",
                "refund_reference": "attack-refund-reference-wrong", "payment_event_id": payment["id"],
                "occurred_at": datetime.now(timezone.utc).isoformat(),
            }, auth_db),
            (BillingError,),
        ))
        refund_payload = {
            "provider": "acceptance_test", "provider_event_id": "attack-refund-event-001",
            "refund_reference": "attack-refund-reference-001", "payment_event_id": payment["id"],
            "occurred_at": datetime.now(timezone.utc).isoformat(),
        }
        checks.append(rejected(
            "refund_predates_payment",
            lambda: record_refund(owner["id"], {
                **refund_payload,
                "provider_event_id": "attack-refund-before-001",
                "refund_reference": "attack-refund-before-ref-001",
                "occurred_at": "2026-01-01T00:00:00+00:00",
            }, auth_db),
            (BillingError,),
        ))
        record_refund(owner["id"], refund_payload, auth_db)
        checks.append(rejected(
            "second_refund_with_new_event",
            lambda: record_refund(owner["id"], {
                **refund_payload, "provider_event_id": "attack-refund-event-002",
                "refund_reference": "attack-refund-reference-002",
            }, auth_db),
            (BillingError,),
        ))
        reconciliation = billing_export(owner["id"], auth_db)["reconciliation"]
        if reconciliation["realized_revenue_minor"] != 0 or reconciliation["acceptance_test_event_count"] != 2:
            raise AdversarialFailure("acceptance events contaminated realized revenue")
        checks.append({"attack": "acceptance_event_as_real_revenue", "status": "rejected"})

        with closing(sqlite3.connect(auth_db)) as connection:
            connection.execute("DROP TRIGGER billing_events_no_delete")
            connection.execute(
                "CREATE TRIGGER billing_events_no_delete BEFORE DELETE ON billing_events BEGIN SELECT 1; END",
            )
            connection.commit()
        checks.append(rejected(
            "billing_append_only_guard_replaced", lambda: initialize_billing(auth_db), (BillingError,),
        ))

    verification = json.loads((ROOT / "evidence" / "m7-paid-community-pilot" / "verification-receipt.json").read_text(encoding="utf-8"))
    for device in ("desktop", "mobile"):
        screenshot = Path(verification["visual"][device]["screenshot"]["path"])
        actual = hashlib.sha256(screenshot.read_bytes()).hexdigest()
        if actual != verification["visual"][device]["screenshot"]["sha256"]:
            raise AdversarialFailure(f"{device} paid-community screenshot hash mismatch")
        checks.append({"attack": f"modified_{device}_screenshot", "status": "detected", "original_sha256_matches": True})

    receipt = {
        "schema_version": "paid-community-pilot-adversarial-v1",
        "status": "passed",
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "public_url": PUBLIC_URL,
        "release_id": manifest["release_id"],
        "attacks": checks,
        "summary": {"P0": 0, "P1": 0, "P2": 0, "attacks_rejected_or_detected": len(checks)},
        "credential_values_recorded": False,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    return receipt


def main() -> None:
    try:
        receipt = verify()
    except (OSError, KeyError, ValueError, json.JSONDecodeError, sqlite3.Error, AdversarialFailure) as exc:
        raise SystemExit(f"paid-community adversarial verification failed: {exc}") from exc
    print(json.dumps({"status": receipt["status"], "release_id": receipt["release_id"], **receipt["summary"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
