from __future__ import annotations

from datetime import datetime, timedelta, timezone
from io import BytesIO
import http.client
import hashlib
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import zipfile


PRODUCT = Path(__file__).resolve().parents[1]
ROOT = PRODUCT.parent
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))
if str(PRODUCT / "deployment") not in sys.path:
    sys.path.insert(0, str(PRODUCT / "deployment"))

from auth_store import (  # noqa: E402
    TIER_ENTITLEMENTS, create_invite, create_owner, create_session, redeem_invite, session_member,
)
from billing_store import (  # noqa: E402
    BillingError, billing_export, billing_status, effective_member, initialize_billing,
    record_payment, record_refund, set_payment_controls,
)
from data_store import stock_payload  # noqa: E402
from portfolio_allocation import digest, portfolio_diff  # noqa: E402
from portfolio_ledger import PortfolioLedger, build_ledger_history  # noqa: E402
from prepare_private_preview import (  # noqa: E402
    PreviewReleaseError, build_research_pack, prepare, verify_release, verify_research_pack,
)
from research_reports import _baseline_report  # noqa: E402
from run_private_preview import load_env, verify_packaged_release  # noqa: E402
from tests import test_canonical_portfolio_v1 as canonical_fixture  # noqa: E402


PORTFOLIO_ID = "canonical_portfolio_" + "1" * 32
PACK_HASH = "a" * 64


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class BillingStoreV1Test(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.db = Path(self.temporary.name) / "auth.db"
        self.owner = create_owner("owner@example.com", "owner-password-2026", "Owner", self.db)
        invite = create_invite(self.owner["id"], "member", self.db)
        self.member = redeem_invite(
            invite["code"], "member@example.com", "member-password-2026", "Member", self.db,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def payment(self, **overrides: object) -> dict:
        payload = {
            "provider": "manual_external",
            "provider_event_id": "payment-event-001",
            "payment_reference": "external-reference-001",
            "member_email": self.member["email"],
            "amount_minor": 29_900,
            "currency": "CNY",
            "occurred_at": now_iso(),
        }
        payload.update(overrides)
        return payload

    def test_paid_entitlement_is_derived_only_from_an_append_only_event(self) -> None:
        with sqlite3.connect(self.db) as connection:
            connection.execute(
                "UPDATE members SET tier='paid',entitlements_json=? WHERE id=?",
                (json.dumps(TIER_ENTITLEMENTS["paid"]), self.member["id"]),
            )
        stored = {**self.member, "tier": "paid", "entitlements": TIER_ENTITLEMENTS["paid"]}
        self.assertEqual(effective_member(stored, self.db)["tier"], "member")

        payment_payload = self.payment()
        event = record_payment(self.owner["id"], payment_payload, PORTFOLIO_ID, PACK_HASH, self.db)
        self.assertFalse(event["test_mode"])
        self.assertEqual(effective_member(stored, self.db)["tier"], "paid")
        replay = record_payment(self.owner["id"], payment_payload, PORTFOLIO_ID, PACK_HASH, self.db)
        self.assertTrue(replay["idempotent"])
        self.assertEqual(replay["id"], event["id"])
        release_changed_replay = record_payment(
            self.owner["id"], payment_payload,
            "canonical_portfolio_" + "2" * 32, "b" * 64, self.db,
        )
        self.assertEqual(
            (release_changed_replay["id"], release_changed_replay["portfolio_id"], release_changed_replay["research_pack_hash"]),
            (event["id"], PORTFOLIO_ID, PACK_HASH),
        )
        with patch("billing_store._now", return_value=datetime.now(timezone.utc) + timedelta(days=400)):
            expired_window_replay = record_payment(
                self.owner["id"], payment_payload, PORTFOLIO_ID, PACK_HASH, self.db,
            )
        self.assertEqual((expired_window_replay["id"], expired_window_replay["idempotent"]), (event["id"], True))
        with self.assertRaises(BillingError):
            record_payment(
                self.owner["id"], self.payment(amount_minor=30_000), PORTFOLIO_ID, PACK_HASH, self.db,
            )
        with sqlite3.connect(self.db) as connection, self.assertRaises(sqlite3.IntegrityError):
            connection.execute("UPDATE billing_events SET amount_minor=100 WHERE id=?", (event["id"],))

    def test_payment_reference_amount_and_refund_chronology_fail_closed(self) -> None:
        payment_time = datetime.now(timezone.utc) - timedelta(hours=1)
        first_payload = self.payment(occurred_at=payment_time.isoformat())
        payment = record_payment(self.owner["id"], first_payload, PORTFOLIO_ID, PACK_HASH, self.db)
        invite = create_invite(self.owner["id"], "member", self.db)
        second = redeem_invite(
            invite["code"], "second@example.com", "second-password-2026", "Second", self.db,
        )
        with self.assertRaisesRegex(BillingError, "reference"):
            record_payment(self.owner["id"], {
                **first_payload,
                "provider_event_id": "payment-event-002",
                "member_email": second["email"],
            }, PORTFOLIO_ID, PACK_HASH, self.db)
        for invalid in (29_900.99, "29900", True):
            with self.subTest(amount_minor=invalid), self.assertRaisesRegex(BillingError, "integer"):
                record_payment(self.owner["id"], self.payment(
                    provider_event_id=f"invalid-amount-{type(invalid).__name__}",
                    payment_reference=f"invalid-reference-{type(invalid).__name__}",
                    member_email=second["email"], amount_minor=invalid,
                ), PORTFOLIO_ID, PACK_HASH, self.db)
        with self.assertRaisesRegex(BillingError, "precede"):
            record_refund(self.owner["id"], {
                "provider": "manual_external", "provider_event_id": "refund-before-payment-001",
                "refund_reference": "refund-reference-before-001", "payment_event_id": payment["id"],
                "occurred_at": (payment_time - timedelta(minutes=1)).isoformat(),
            }, self.db)

    def test_refund_reuses_original_context_revokes_sessions_and_reconciles(self) -> None:
        payment = record_payment(self.owner["id"], self.payment(), PORTFOLIO_ID, PACK_HASH, self.db)
        session = create_session(self.member["id"], self.db)
        refund_payload = {
            "provider": "manual_external",
            "provider_event_id": "refund-event-001",
            "refund_reference": "external-refund-001",
            "payment_event_id": payment["id"],
            "occurred_at": now_iso(),
        }
        refund = record_refund(self.owner["id"], refund_payload, self.db)
        self.assertEqual((refund["portfolio_id"], refund["research_pack_hash"]), (PORTFOLIO_ID, PACK_HASH))
        self.assertIsNone(session_member(session["token"], self.db))
        self.assertEqual(billing_status(self.member["id"], self.db)["status"], "refunded")
        self.assertEqual(effective_member(self.member, self.db)["tier"], "member")
        replay = record_refund(self.owner["id"], refund_payload, self.db)
        self.assertTrue(replay["idempotent"])
        with patch("billing_store._now", return_value=datetime.now(timezone.utc) + timedelta(days=400)):
            expired_window_replay = record_refund(self.owner["id"], refund_payload, self.db)
        self.assertEqual((expired_window_replay["id"], expired_window_replay["idempotent"]), (refund["id"], True))
        exported = billing_export(self.owner["id"], self.db)
        self.assertEqual(exported["reconciliation"]["realized_revenue_minor"], 0)
        self.assertEqual(exported["reconciliation"]["real_event_count"], 2)

    def test_stop_new_payments_blocks_opening_but_not_refunds(self) -> None:
        disabled = set_payment_controls(self.owner["id"], False, self.db)
        self.assertFalse(disabled["accept_new_payments"])
        with self.assertRaisesRegex(BillingError, "stopped"):
            record_payment(self.owner["id"], self.payment(), PORTFOLIO_ID, PACK_HASH, self.db)
        self.assertTrue(set_payment_controls(self.owner["id"], True, self.db)["accept_new_payments"])
        payment_payload = self.payment()
        payment = record_payment(self.owner["id"], payment_payload, PORTFOLIO_ID, PACK_HASH, self.db)
        set_payment_controls(self.owner["id"], False, self.db)
        replay = record_payment(self.owner["id"], payment_payload, PORTFOLIO_ID, PACK_HASH, self.db)
        self.assertTrue(replay["idempotent"])
        refund = record_refund(self.owner["id"], {
            "provider": "manual_external", "provider_event_id": "refund-event-002",
            "refund_reference": "external-refund-002", "payment_event_id": payment["id"],
            "occurred_at": now_iso(),
        }, self.db)
        self.assertEqual(refund["event_type"], "refund_confirmed")

    def test_acceptance_events_never_count_as_real_revenue(self) -> None:
        payment = record_payment(
            self.owner["id"], self.payment(provider="acceptance_test"), PORTFOLIO_ID, PACK_HASH, self.db,
        )
        record_refund(self.owner["id"], {
            "provider": "acceptance_test", "provider_event_id": "acceptance-refund-001",
            "refund_reference": "acceptance-ref-001", "payment_event_id": payment["id"],
            "occurred_at": now_iso(),
        }, self.db)
        reconciliation = billing_export(self.owner["id"], self.db)["reconciliation"]
        self.assertEqual(reconciliation["realized_revenue_minor"], 0)
        self.assertEqual(reconciliation["acceptance_test_event_count"], 2)

    def test_guards_fail_closed(self) -> None:
        initialize_billing(self.db)
        with sqlite3.connect(self.db) as connection:
            connection.execute("DROP TRIGGER billing_events_no_update")
            connection.execute(
                "CREATE TRIGGER billing_events_no_update BEFORE UPDATE ON billing_events BEGIN SELECT 1; END",
            )
        with self.assertRaisesRegex(BillingError, "guard"):
            initialize_billing(self.db)

    def test_reference_uniqueness_guard_cannot_be_replaced_by_name(self) -> None:
        initialize_billing(self.db)
        with sqlite3.connect(self.db) as connection:
            connection.execute("DROP INDEX uq_billing_payment_reference")
            connection.execute(
                "CREATE INDEX uq_billing_payment_reference ON billing_events(provider,payment_reference)",
            )
        with self.assertRaisesRegex(BillingError, "uniqueness guard"):
            initialize_billing(self.db)


class PaidCommunityPilotHTTPTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = canonical_fixture.CanonicalPortfolioV1Test(methodName="runTest")
        cls.fixture.setUp()
        cls.root = cls.fixture.root
        cls.db = cls.fixture.db_path
        cls.auth_db = cls.root / "m7-auth.db"
        first, current = cls.fixture.two_versions()
        cls.current = current
        cls.state = cls.root / "canonical"
        (cls.state / "versions").mkdir(parents=True)
        for item in (first, current):
            (cls.state / "versions" / f"{item['portfolio_id']}.json").write_text(
                json.dumps(item, ensure_ascii=False), encoding="utf-8",
            )
        pointer = {
            "portfolio_id": current["portfolio_id"], "payload_hash": current["payload_hash"],
            "snapshot_id": current["snapshot"]["snapshot_id"],
        }
        pointer["pointer_hash"] = digest(pointer)
        (cls.state / "current.json").write_text(json.dumps(pointer), encoding="utf-8")
        (cls.state / "latest-diff.json").write_text(
            json.dumps(portfolio_diff(first, current), ensure_ascii=False), encoding="utf-8",
        )
        ledger = PortfolioLedger(cls.state / "portfolio-ledger.db")
        for portfolio in (first, current):
            order_ids = ledger.stage_orders(portfolio)
            for order_id in order_ids:
                ledger.append_event(order_id, "pending", event_at=portfolio["generated_at"], reason="m7 acceptance pending")
        current_ledger = ledger.payload(current["portfolio_id"])
        (cls.state / "latest-ledger.json").write_text(json.dumps(current_ledger), encoding="utf-8")
        (cls.state / "ledger-history.json").write_text(json.dumps(build_ledger_history([
            ledger.payload(first["portfolio_id"]), current_ledger,
        ])), encoding="utf-8")

        cls.reports = cls.root / "canonical-reports"
        cls.reports.mkdir()
        for position in current["positions"]:
            stock = stock_payload(position["ticker"], cls.db, snapshot_id=current["snapshot"]["snapshot_id"])
            report = _baseline_report(stock, cls.db)
            if report["report_hash"] != position["report_binding"]["report_hash"]:
                raise RuntimeError("M7 report differs from portfolio binding")
            (cls.reports / f"{position['ticker']}.json").write_text(json.dumps(report), encoding="utf-8")
        cls.pack = cls.root / "research-pack"
        cls.pack_manifest = build_research_pack(cls.state, cls.reports, current, cls.pack)

        cls.owner = create_owner("park-m7@example.com", "owner-password-2026", "Park", cls.auth_db)
        for tier, email, name in (
            ("member", "pilot@example.com", "Pilot"),
            ("member", "legacy-paid@example.com", "Legacy Paid"),
            ("preview", "preview-m7@example.com", "Preview"),
        ):
            invite = create_invite(cls.owner["id"], tier, cls.auth_db)
            redeem_invite(invite["code"], email, f"{name.lower().replace(' ', '-')}-password-2026", name, cls.auth_db)
        with sqlite3.connect(cls.auth_db) as connection:
            connection.execute(
                "UPDATE members SET tier='paid',entitlements_json=? WHERE email='legacy-paid@example.com'",
                (json.dumps(TIER_ENTITLEMENTS["paid"]),),
            )

        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            cls.port = sock.getsockname()[1]
        env = dict(os.environ)
        env.update({
            "PARK_DASHBOARD_DB": str(cls.db), "PARK_AUTH_DB": str(cls.auth_db),
            "PARK_CANONICAL_PORTFOLIO_ROOT": str(cls.state),
            "PARK_CANONICAL_PORTFOLIO_SOURCE_DB": str(cls.db),
            "PARK_PRIVATE_REPORT_ROOT": str(cls.reports),
            "PARK_PRIVATE_RESEARCH_PACK": str(cls.pack),
            "PARK_AUTH_REQUIRED": "1", "PARK_COOKIE_SECURE": "1", "PARK_PRIVATE_PREVIEW": "1",
            "PARK_MANUAL_PAID_PILOT": "1",
        })
        cls.server = subprocess.Popen(
            [sys.executable, str(PRODUCT / "server.py"), "--host", "127.0.0.1", "--port", str(cls.port)],
            cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if cls.server.poll() is not None:
                raise RuntimeError("M7 server exited during startup")
            try:
                if cls.request("GET", "/api/health")[0] == 200:
                    break
            except OSError:
                time.sleep(0.05)
        else:
            raise RuntimeError("M7 server did not start")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.terminate()
        cls.server.wait(timeout=5)
        cls.fixture.tearDown()

    @classmethod
    def request(
        cls, method: str, path: str, payload: dict | None = None, *, cookie: str | None = None,
        csrf: str | None = None,
    ) -> tuple[int, dict | bytes, dict[str, str]]:
        connection = http.client.HTTPConnection("127.0.0.1", cls.port, timeout=8)
        headers: dict[str, str] = {}
        body = None
        if payload is not None:
            body = json.dumps(payload).encode()
            headers["Content-Type"] = "application/json"
        if cookie:
            headers["Cookie"] = cookie
        if csrf:
            headers["X-CSRF-Token"] = csrf
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        value = json.loads(raw) if response.getheader("Content-Type", "").startswith("application/json") else raw
        response_headers = dict(response.getheaders())
        status = response.status
        connection.close()
        return status, value, response_headers

    @classmethod
    def login(cls, email: str, password: str) -> tuple[dict, str]:
        status, payload, headers = cls.request("POST", "/api/auth/login", {"email": email, "password": password})
        if status != 200:
            raise AssertionError(f"login failed: {status} {payload}")
        return payload, headers["Set-Cookie"].split(";", 1)[0]

    def test_manual_paid_lifecycle_grants_exact_pack_then_refund_revokes_it(self) -> None:
        member_auth, member_cookie = self.login("pilot@example.com", "pilot-password-2026")
        owner_auth, owner_cookie = self.login("park-m7@example.com", "owner-password-2026")
        status, unpaid, _ = self.request("GET", "/api/billing/me", cookie=member_cookie)
        self.assertEqual((status, unpaid["billing"]["status"]), (200, "unpaid"))
        self.assertEqual(unpaid["research_pack"]["report_count"], 8)
        status, denied, _ = self.request("GET", "/downloads/private-preview/research-pack.zip", cookie=member_cookie)
        self.assertEqual((status, denied["error"]), (403, "entitlement_required"))

        payment_payload = {
            "provider": "acceptance_test", "provider_event_id": "http-payment-acceptance-001",
            "payment_reference": "http-reference-acceptance-001", "member_email": "pilot@example.com",
            "amount_minor": 29_900, "currency": "CNY", "occurred_at": now_iso(),
        }
        status, payment, _ = self.request(
            "POST", "/api/billing/payment", payment_payload, cookie=owner_cookie, csrf=owner_auth["csrf_token"],
        )
        self.assertEqual((status, payment["event_type"], payment["test_mode"]), (201, "payment_confirmed", True))
        status, preview, _ = self.request("GET", "/api/private-preview", cookie=member_cookie)
        self.assertEqual((status, preview["billing"]["status"]), (200, "active_paid_test"))
        self.assertEqual(preview["paid_pilot"]["contract_version"], "manual-paid-community-v1")
        self.assertFalse(preview["paid_pilot"]["paid_pilot_ready"])
        self.assertFalse(preview["paid_pilot"]["online_checkout"])

        status, archive, headers = self.request(
            "GET", "/downloads/private-preview/research-pack.zip", cookie=member_cookie,
        )
        self.assertEqual(status, 200)
        self.assertEqual(headers["X-Research-Pack-Hash"], self.pack_manifest["pack_hash"])
        with zipfile.ZipFile(BytesIO(archive)) as bundle:
            self.assertIsNone(bundle.testzip())
            self.assertEqual(len(bundle.namelist()), 13)
            self.assertEqual(json.loads(bundle.read("pack-manifest.json"))["pack_hash"], self.pack_manifest["pack_hash"])

        status, replay, _ = self.request(
            "POST", "/api/billing/payment", payment_payload, cookie=owner_cookie, csrf=owner_auth["csrf_token"],
        )
        self.assertEqual((status, replay["idempotent"], replay["id"]), (201, True, payment["id"]))
        status, exported, _ = self.request("GET", "/api/billing", cookie=owner_cookie)
        self.assertEqual(status, 200)
        self.assertEqual(exported["reconciliation"]["realized_revenue_minor"], 0)
        self.assertGreaterEqual(exported["reconciliation"]["acceptance_test_event_count"], 1)

        refund_payload = {
            "provider": "acceptance_test", "provider_event_id": "http-refund-acceptance-001",
            "refund_reference": "http-refund-reference-001", "payment_event_id": payment["id"],
            "occurred_at": now_iso(),
        }
        pack_manifest = self.pack / "pack-manifest.json"
        unavailable_manifest = self.pack / "pack-manifest.unavailable"
        pack_manifest.replace(unavailable_manifest)
        try:
            status, refund, _ = self.request(
                "POST", "/api/billing/refund", refund_payload,
                cookie=owner_cookie, csrf=owner_auth["csrf_token"],
            )
        finally:
            unavailable_manifest.replace(pack_manifest)
        self.assertEqual((status, refund["event_type"]), (201, "refund_confirmed"))
        status, revoked, _ = self.request("GET", "/api/billing/me", cookie=member_cookie)
        self.assertEqual((status, revoked["error"]), (401, "authentication_required"))
        new_auth, new_cookie = self.login("pilot@example.com", "pilot-password-2026")
        self.assertEqual(new_auth["member"]["tier"], "member")
        status, denied, _ = self.request("GET", "/downloads/private-preview/research-pack.zip", cookie=new_cookie)
        self.assertEqual((status, denied["error"]), (403, "entitlement_required"))
        self.assertIn("csrf_token", member_auth)

    def test_stored_paid_tier_and_non_owner_admin_requests_do_not_grant_paid_access(self) -> None:
        auth, cookie = self.login("legacy-paid@example.com", "legacy-paid-password-2026")
        self.assertEqual(auth["member"]["tier"], "member")
        self.assertNotIn("publication_downloads", auth["member"]["entitlements"])
        status, denied, _ = self.request("GET", "/downloads/private-preview/research-pack.zip", cookie=cookie)
        self.assertEqual((status, denied["error"]), (403, "entitlement_required"))
        status, denied, _ = self.request("GET", "/api/billing", cookie=cookie)
        self.assertEqual((status, denied["error"]), (403, "entitlement_required"))
        status, denied, _ = self.request(
            "POST", "/api/billing/settings", {"accept_new_payments": False},
            cookie=cookie, csrf=auth["csrf_token"],
        )
        self.assertEqual((status, denied["error"]), (403, "owner_required"))
        owner_auth, owner_cookie = self.login("park-m7@example.com", "owner-password-2026")
        status, denied, _ = self.request(
            "POST", "/api/invites", {"tier": "paid", "max_uses": 1, "valid_days": 7},
            cookie=owner_cookie, csrf=owner_auth["csrf_token"],
        )
        self.assertEqual((status, denied["error"]), (400, "invite_rejected"))

    def test_release_and_runner_bind_exact_research_pack_and_required_flag(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            runtime = Path(temporary) / "runtime"
            runtime.mkdir()
            deep = Path(temporary) / "deep"
            deep.mkdir()
            receipt = prepare(self.db, self.state, deep, runtime)
            values = load_env(runtime / "preview.env")
            self.assertEqual(values["PARK_MANUAL_PAID_PILOT"], "1")
            self.assertEqual(verify_packaged_release(runtime, values)["release_id"], receipt["release_id"])
            self.assertEqual(verify_release(runtime / "current")["release_id"], receipt["release_id"])
            with (runtime / "current" / "research-pack" / "research-pack.zip").open("ab") as handle:
                handle.write(b"tamper")
            with self.assertRaises((RuntimeError, PreviewReleaseError)):
                verify_packaged_release(runtime, values)

    def test_research_pack_manifest_cannot_escape_its_release_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            pack = Path(temporary) / "research-pack"
            manifest = build_research_pack(self.state, self.reports, self.current, pack)
            files = dict(manifest["files"])
            original = next(iter(files))
            files["../outside.json"] = files.pop(original)
            core = {**manifest, "files": files}
            core.pop("pack_hash")
            core["pack_hash"] = digest(core)
            (pack / "pack-manifest.json").write_text(json.dumps(core), encoding="utf-8")
            with self.assertRaisesRegex(PreviewReleaseError, "canonical release inputs"):
                verify_research_pack(pack, self.state, self.current, self.reports)

    def test_self_consistent_research_pack_cannot_diverge_from_canonical_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            pack = Path(temporary) / "research-pack"
            manifest = build_research_pack(self.state, self.reports, self.current, pack)
            portfolio_path = pack / "portfolio.json"
            portfolio = json.loads(portfolio_path.read_text(encoding="utf-8"))
            portfolio["positions"][0]["target_weight"] = 99
            portfolio_path.write_text(json.dumps(portfolio), encoding="utf-8")
            core = {**manifest, "files": dict(manifest["files"])}
            core.pop("pack_hash")
            core["files"]["portfolio.json"] = hashlib.sha256(portfolio_path.read_bytes()).hexdigest()
            core["pack_hash"] = digest(core)
            (pack / "pack-manifest.json").write_text(json.dumps(core), encoding="utf-8")
            with self.assertRaisesRegex(PreviewReleaseError, "canonical release input"):
                verify_research_pack(pack, self.state, self.current, self.reports)

    def test_static_contract_exposes_manual_truth_and_owner_controls(self) -> None:
        html = (PRODUCT / "static" / "index.html").read_text(encoding="utf-8")
        css = (PRODUCT / "static" / "styles.css").read_text(encoding="utf-8")
        js = (PRODUCT / "static" / "app.js").read_text(encoding="utf-8")
        for marker in (
            "MANUAL PAID PILOT", "不提供在线 checkout", "billing-payment-form", "billing-refund-form",
            "billing-control-form", "research-pack-download",
        ):
            self.assertIn(marker, html)
        for marker in ("renderBillingPilot", "/api/billing/payment", "/api/billing/refund", "/api/billing/settings"):
            self.assertIn(marker, js)
        self.assertIn(".billing-pilot-panel", css)
        self.assertIn(".owner-billing-grid", css)


if __name__ == "__main__":
    unittest.main()
