from __future__ import annotations

import http.client
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


PRODUCT = Path(__file__).resolve().parents[1]
ROOT = PRODUCT.parent
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))
if str(PRODUCT / "deployment") not in sys.path:
    sys.path.insert(0, str(PRODUCT / "deployment"))

from auth_store import create_invite, create_owner, redeem_invite  # noqa: E402
from data_store import initialize, stock_payload  # noqa: E402
from feedback_store import initialize_feedback  # noqa: E402
from install_private_preview import app_plist  # noqa: E402
from run_private_preview import load_env, verify_packaged_release  # noqa: E402
from portfolio_allocation import digest, portfolio_diff  # noqa: E402
from portfolio_ledger import PortfolioLedger, build_ledger_history  # noqa: E402
from prepare_private_preview import PreviewReleaseError, point_current, prepare, sanitize_auth_store  # noqa: E402
from research_reports import _baseline_report  # noqa: E402
from tests import test_canonical_portfolio_v1 as canonical_fixture  # noqa: E402


class PrivatePreviewV1Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = canonical_fixture.CanonicalPortfolioV1Test(methodName="runTest")
        cls.fixture.setUp()
        cls.root = cls.fixture.root
        cls.db = cls.fixture.db_path
        cls.auth_db = cls.root / "private-preview-auth.db"
        first, current = cls.fixture.two_versions()
        cls.first = first
        cls.current = current
        cls.state = cls.root / "canonical"
        (cls.state / "versions").mkdir(parents=True)
        for item in (first, current):
            (cls.state / "versions" / f"{item['portfolio_id']}.json").write_text(
                json.dumps(item, ensure_ascii=False), encoding="utf-8",
            )
        pointer = {
            "portfolio_id": current["portfolio_id"],
            "payload_hash": current["payload_hash"],
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
                ledger.append_event(order_id, "pending", event_at=portfolio["generated_at"], reason="acceptance pending")
        current_ledger = ledger.payload(current["portfolio_id"])
        (cls.state / "latest-ledger.json").write_text(json.dumps(current_ledger), encoding="utf-8")
        history = build_ledger_history([ledger.payload(first["portfolio_id"]), current_ledger])
        (cls.state / "ledger-history.json").write_text(json.dumps(history), encoding="utf-8")

        cls.reports = cls.root / "canonical-reports"
        cls.reports.mkdir()
        for position in current["positions"]:
            stock = stock_payload(position["ticker"], cls.db, snapshot_id=current["snapshot"]["snapshot_id"])
            report = _baseline_report(stock, cls.db)
            if report["report_hash"] != position["report_binding"]["report_hash"]:
                raise RuntimeError("private preview test report differs from portfolio binding")
            (cls.reports / f"{position['ticker']}.json").write_text(
                json.dumps(report, ensure_ascii=False), encoding="utf-8",
            )

        owner = create_owner("park@example.com", "owner-password-2026", "Park", cls.auth_db)
        preview_invite = create_invite(owner["id"], "preview", cls.auth_db)
        member_invite = create_invite(owner["id"], "member", cls.auth_db)
        cls.preview = redeem_invite(preview_invite["code"], "preview@example.com", "preview-password-2026", "Preview", cls.auth_db)
        cls.member = redeem_invite(member_invite["code"], "member@example.com", "member-password-2026", "Member", cls.auth_db)

        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            cls.port = sock.getsockname()[1]
        env = dict(os.environ)
        env.update({
            "PARK_DASHBOARD_DB": str(cls.db),
            "PARK_AUTH_DB": str(cls.auth_db),
            "PARK_CANONICAL_PORTFOLIO_ROOT": str(cls.state),
            "PARK_CANONICAL_PORTFOLIO_SOURCE_DB": str(cls.db),
            "PARK_PRIVATE_REPORT_ROOT": str(cls.reports),
            "PARK_AUTH_REQUIRED": "1",
            "PARK_COOKIE_SECURE": "1",
            "PARK_PRIVATE_PREVIEW": "1",
        })
        cls.server = subprocess.Popen(
            [sys.executable, str(PRODUCT / "server.py"), "--host", "127.0.0.1", "--port", str(cls.port)],
            cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if cls.server.poll() is not None:
                raise RuntimeError("private preview server exited during startup")
            try:
                if cls.request("GET", "/api/health")[0] == 200:
                    break
            except OSError:
                time.sleep(0.05)
        else:
            raise RuntimeError("private preview server did not start")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.terminate()
        cls.server.wait(timeout=5)
        cls.fixture.tearDown()

    @classmethod
    def request(
        cls,
        method: str,
        path: str,
        payload: dict | None = None,
        *,
        cookie: str | None = None,
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
    def login(cls, email: str, password: str) -> tuple[dict, str, str]:
        status, payload, headers = cls.request("POST", "/api/auth/login", {"email": email, "password": password})
        if status != 200:
            raise AssertionError(f"login failed: {status} {payload}")
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        return payload, cookie, headers["Set-Cookie"]

    def test_anonymous_health_is_minimal_and_every_research_route_is_closed(self) -> None:
        status, health, _ = self.request("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(health, {"auth_required": True, "product": "park-equity-research-preview", "status": "ok"})
        for path in (
            "/api/private-preview", "/api/canonical/portfolio", "/api/canonical/portfolio/ledger",
            "/api/reports/300750.SZ", "/api/feedback", "/api/feedback/export",
            "/api/dashboard", "/api/committee", "/api/publications", "/api/refresh/status",
            "/api/canonical/active", "/api/canonical/portfolio/history",
            "/api/canonical/portfolio/ledger/history", "/api/stocks/300750.SZ",
            "/api/research/batches/latest", "/api/publication-packs/latest",
            "/downloads/publication-packs/fake/fake.zip",
        ):
            status, payload, _ = self.request("GET", path)
            self.assertEqual((status, payload["error"]), (401, "authentication_required"), path)

    def test_auth_and_feedback_state_remain_outside_the_research_database(self) -> None:
        with sqlite3.connect(self.db) as research, sqlite3.connect(self.auth_db) as auth:
            research_tables = {row[0] for row in research.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            auth_tables = {row[0] for row in auth.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertFalse({"members", "member_sessions", "member_feedback"} & research_tables)
        self.assertTrue({"members", "member_sessions", "member_feedback"}.issubset(auth_tables))
        self.assertFalse({"dataset_snapshots", "publications", "portfolio_items"} & auth_tables)

    def test_auth_sanitizer_preserves_members_and_removes_legacy_research_tables(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            runtime = Path(temporary)
            auth_db = runtime / "auth.db"
            initialize(auth_db)
            create_owner("legacy-owner@example.com", "legacy-owner-password", "Legacy", auth_db)
            initialize_feedback(auth_db)
            receipt = sanitize_auth_store(runtime)
            with sqlite3.connect(auth_db) as connection:
                tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                members = connection.execute("SELECT COUNT(*) FROM members").fetchone()[0]
            self.assertEqual((receipt["status"], members), ("sanitized", 1))
            self.assertTrue({"members", "member_feedback"}.issubset(tables))
            self.assertFalse({"dataset_snapshots", "publications", "portfolio_items"} & tables)
            self.assertTrue(Path(receipt["backup"]).is_file())

    def test_installed_service_executes_only_the_external_runtime_runner(self) -> None:
        runtime = Path("/private/tmp/park-equity-preview")
        payload = app_plist(runtime, Path(sys.executable), 8878)
        self.assertEqual(payload["ProgramArguments"][1], str(runtime / "bin" / "run_private_preview.py"))
        self.assertEqual(payload["WorkingDirectory"], str(runtime))
        self.assertNotIn(str(ROOT), " ".join(payload["ProgramArguments"]))

    def test_packaged_runner_rejects_missing_manifest_and_active_code_tamper(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            runtime = Path(temporary) / "runtime"
            runtime.mkdir()
            deep = Path(temporary) / "deep"
            deep.mkdir()
            receipt = prepare(self.db, self.state, deep, runtime)
            values = load_env(runtime / "preview.env")
            self.assertEqual(verify_packaged_release(runtime, values)["release_id"], receipt["release_id"])
            self.assertTrue((runtime / "current" / "product" / "data" / "industry-intelligence-v1.json").is_file())
            manifest = runtime / "current" / "manifest.json"
            hidden = manifest.with_suffix(".hidden")
            manifest.rename(hidden)
            with self.assertRaises(RuntimeError):
                verify_packaged_release(runtime, values)
            with self.assertRaises(PreviewReleaseError):
                point_current(runtime, receipt["release_id"])
            hidden.rename(manifest)
            with (runtime / "current" / "product" / "server.py").open("a", encoding="utf-8") as handle:
                handle.write("\n# active tamper\n")
            with self.assertRaises(RuntimeError):
                verify_packaged_release(runtime, values)

    def test_private_preview_startup_rejects_shared_auth_and_research_database(self) -> None:
        env = dict(os.environ)
        env.update({
            "PARK_DASHBOARD_DB": str(self.db), "PARK_AUTH_DB": str(self.db),
            "PARK_CANONICAL_PORTFOLIO_ROOT": str(self.state),
            "PARK_CANONICAL_PORTFOLIO_SOURCE_DB": str(self.db),
            "PARK_PRIVATE_REPORT_ROOT": str(self.reports),
            "PARK_AUTH_REQUIRED": "1", "PARK_COOKIE_SECURE": "1", "PARK_PRIVATE_PREVIEW": "1",
        })
        result = subprocess.run(
            [sys.executable, str(PRODUCT / "server.py"), "--host", "127.0.0.1", "--port", "18879"],
            cwd=ROOT, env=env, text=True, capture_output=True, timeout=15, check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("auth database must be separate", result.stderr)
        env["PARK_AUTH_DB"] = str(ROOT / "unsafe-private-auth.db")
        result = subprocess.run(
            [sys.executable, str(PRODUCT / "server.py"), "--host", "127.0.0.1", "--port", "18879"],
            cwd=ROOT, env=env, text=True, capture_output=True, timeout=15, check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("outside packaged product code", result.stderr)
        self.assertFalse((ROOT / "unsafe-private-auth.db").exists())

    def test_preview_receives_exact_canonical_first_screen_but_not_reports(self) -> None:
        auth, cookie, set_cookie = self.login("preview@example.com", "preview-password-2026")
        self.assertTrue(auth["private_preview"])
        self.assertIn("Secure", set_cookie)
        self.assertIn("HttpOnly", set_cookie)
        self.assertIn("SameSite=Strict", set_cookie)
        self.assertTrue(set_cookie.startswith("__Host-park_session="))
        status, payload, _ = self.request("GET", "/api/private-preview", cookie=cookie)
        self.assertEqual(status, 200)
        self.assertEqual(payload["schema_version"], "private-preview-v1")
        self.assertEqual(payload["portfolio"]["portfolio_id"], self.current["portfolio_id"])
        self.assertEqual(payload["portfolio"]["snapshot"]["data_mode"], "REAL")
        self.assertEqual(len(payload["portfolio"]["positions"]), 8)
        self.assertFalse(payload["preview"]["accepts_payment"])
        self.assertTrue(payload["preview"]["exact_report_bindings_verified"])
        self.assertEqual(payload["preview"]["route_surface"], "explicit_allowlist")
        status, industry, _ = self.request("GET", "/api/industry-intelligence", cookie=cookie)
        self.assertEqual(status, 200)
        self.assertEqual(industry["summary"]["dossier_count"], 489)
        self.assertEqual(industry["summary"]["materials_node_count"], 94)
        status, dossier, _ = self.request(
            "GET", "/api/industry-intelligence/dossiers/300223", cookie=cookie,
        )
        self.assertEqual(status, 200)
        self.assertEqual(dossier["dossier"]["code"], "300223")
        status, error, _ = self.request("GET", "/api/reports/300750.SZ", cookie=cookie)
        self.assertEqual((status, error["error"]), (403, "entitlement_required"))
        for path in (
            "/api/dashboard", "/api/committee", "/api/publications", "/api/refresh/status",
            "/api/canonical/active", "/api/canonical/portfolio", "/api/canonical/portfolio/history",
            "/api/canonical/portfolio/ledger", "/api/canonical/portfolio/ledger/history",
            "/api/stocks/300750.SZ", "/api/research/batches/latest", "/api/publication-packs/latest",
            "/downloads/publication-packs/fake/fake.zip",
        ):
            status, legacy, _ = self.request("GET", path, cookie=cookie)
            self.assertEqual((status, legacy["error"]), (404, "private_preview_route_unavailable"), path)

    def test_feedback_is_csrf_bound_deduplicated_and_owner_readable(self) -> None:
        auth, cookie, _ = self.login("member@example.com", "member-password-2026")
        feedback = {"page_type": "portfolio", "category": "clarity", "rating": 4, "message": "组合结论清楚，但希望动作理由更具体一些。"}
        status, payload, _ = self.request("POST", "/api/feedback", feedback, cookie=cookie)
        self.assertEqual((status, payload["error"]), (403, "csrf_rejected"))
        status, payload, _ = self.request("POST", "/api/feedback", feedback, cookie=cookie, csrf=auth["csrf_token"])
        self.assertEqual((status, payload["status"]), (201, "accepted"))
        self.assertEqual(payload["feedback"]["portfolio_id"], self.current["portfolio_id"])
        status, payload, _ = self.request("POST", "/api/feedback", feedback, cookie=cookie, csrf=auth["csrf_token"])
        self.assertEqual((status, payload["error"]), (400, "feedback_rejected"))
        owner_auth, owner_cookie, _ = self.login("park@example.com", "owner-password-2026")
        status, payload, _ = self.request("GET", "/api/feedback", cookie=owner_cookie)
        self.assertEqual(status, 200)
        self.assertEqual(payload["feedback"][0]["member_email"], "member@example.com")
        status, exported, headers = self.request("GET", "/api/feedback/export", cookie=owner_cookie)
        self.assertEqual(status, 200)
        self.assertEqual(exported["feedback"][0]["page_identity"], self.current["payload_hash"])
        self.assertRegex(exported["export_hash"], r"^[0-9a-f]{64}$")
        self.assertIn("attachment", headers["Content-Disposition"])
        self.assertIn("csrf_token", owner_auth)

    def test_feedback_rejects_overlong_content_and_rate_limits_each_member(self) -> None:
        auth, cookie, _ = self.login("preview@example.com", "preview-password-2026")
        base = {"page_type": "portfolio", "category": "clarity", "rating": 4}
        status, payload, _ = self.request(
            "POST", "/api/feedback", {**base, "message": "字" * 2_001},
            cookie=cookie, csrf=auth["csrf_token"],
        )
        self.assertEqual((status, payload["error"]), (400, "feedback_rejected"))
        for index in range(5):
            status, payload, _ = self.request(
                "POST", "/api/feedback", {**base, "message": f"第 {index + 1} 条独立反馈，用于验证每小时提交上限。"},
                cookie=cookie, csrf=auth["csrf_token"],
            )
            self.assertEqual((status, payload["status"]), (201, "accepted"))
        status, payload, _ = self.request(
            "POST", "/api/feedback", {**base, "message": "第六条反馈必须触发限流，而不是写入审计库。"},
            cookie=cookie, csrf=auth["csrf_token"],
        )
        self.assertEqual((status, payload["error"]), (429, "feedback_rejected"))

    def test_member_can_read_reports_but_cannot_manage_members(self) -> None:
        _, cookie, _ = self.login("member@example.com", "member-password-2026")
        status, report, _ = self.request("GET", "/api/reports/300750.SZ", cookie=cookie)
        self.assertEqual(status, 200)
        self.assertEqual(report["ticker"], "300750.SZ")
        binding = next(item["report_binding"] for item in self.current["positions"] if item["ticker"] == "300750.SZ")
        self.assertEqual(report["report_hash"], binding["report_hash"])
        status, payload, _ = self.request("GET", "/api/members", cookie=cookie)
        self.assertEqual((status, payload["error"]), (403, "entitlement_required"))

    def test_http_invite_signup_logout_flow_is_complete(self) -> None:
        owner_auth, owner_cookie, _ = self.login("park@example.com", "owner-password-2026")
        status, invite, _ = self.request(
            "POST", "/api/invites", {"tier": "preview", "max_uses": 1, "valid_days": 2},
            cookie=owner_cookie, csrf=owner_auth["csrf_token"],
        )
        self.assertEqual(status, 201)
        status, auth, headers = self.request(
            "POST", "/api/auth/signup",
            {"invite_code": invite["code"], "email": "signup@example.com", "password": "signup-password-2026", "display_name": "Signup"},
        )
        self.assertEqual(status, 200)
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        status, payload, _ = self.request("GET", "/api/private-preview", cookie=cookie)
        self.assertEqual(status, 200)
        status, payload, headers = self.request(
            "POST", "/api/auth/logout", {}, cookie=cookie, csrf=auth["csrf_token"],
        )
        self.assertEqual((status, payload["status"]), (200, "signed_out"))
        self.assertIn("Max-Age=0", headers["Set-Cookie"])
        status, payload, _ = self.request("GET", "/api/private-preview", cookie=cookie)
        self.assertEqual((status, payload["error"]), (401, "authentication_required"))

    def test_owner_cannot_mutate_research_release_in_private_preview(self) -> None:
        auth, cookie, _ = self.login("park@example.com", "owner-password-2026")
        for path, body in (
            ("/api/refresh", {}),
            ("/api/research/batches", {}),
            ("/api/publications/legacy/approve", {}),
            ("/api/publications/legacy/publish", {}),
        ):
            status, payload, _ = self.request("POST", path, body, cookie=cookie, csrf=auth["csrf_token"])
            self.assertEqual((status, payload["error"]), (404, "private_preview_route_unavailable"), path)
        status, payload, _ = self.request(
            "GET", "/downloads/publication-packs/fake/fake.zip", cookie=cookie,
        )
        self.assertEqual((status, payload["error"]), (404, "private_preview_route_unavailable"))

    def test_repeated_and_rotating_identity_failed_logins_are_rate_limited(self) -> None:
        body = {"email": "rate-limit-probe@example.com", "password": "invalid-password-value"}
        for _ in range(10):
            status, payload, _ = self.request("POST", "/api/auth/login", body)
            self.assertEqual((status, payload["error"]), (401, "invalid_credentials"))
        status, payload, _ = self.request("POST", "/api/auth/login", body)
        self.assertEqual((status, payload["error"]), (429, "too_many_attempts"))
        for index in range(20):
            status, payload, _ = self.request(
                "POST", "/api/auth/login",
                {"email": f"rotating-{index}@example.com", "password": "invalid-password-value"},
            )
            self.assertEqual((status, payload["error"]), (401, "invalid_credentials"))
        status, payload, _ = self.request(
            "POST", "/api/auth/login",
            {"email": "rotating-final@example.com", "password": "invalid-password-value"},
        )
        self.assertEqual((status, payload["error"]), (429, "too_many_attempts"))

    def test_owner_can_create_invite_and_suspension_revokes_existing_session(self) -> None:
        preview_auth, preview_cookie, _ = self.login("preview@example.com", "preview-password-2026")
        owner_auth, owner_cookie, _ = self.login("park@example.com", "owner-password-2026")
        status, invite, _ = self.request(
            "POST", "/api/invites", {"tier": "member", "max_uses": 1, "valid_days": 3},
            cookie=owner_cookie, csrf=owner_auth["csrf_token"],
        )
        self.assertEqual(status, 201)
        self.assertEqual((invite["tier"], invite["max_uses"]), ("member", 1))
        self.assertGreater(len(invite["code"]), 20)
        status, payload, _ = self.request(
            "POST", "/api/members/status", {"email": "preview@example.com", "status": "suspended"},
            cookie=owner_cookie, csrf=owner_auth["csrf_token"],
        )
        self.assertEqual((status, payload["status"]), (200, "suspended"))
        status, payload, _ = self.request("GET", "/api/private-preview", cookie=preview_cookie)
        self.assertEqual((status, payload["error"]), (401, "authentication_required"))
        status, payload, _ = self.request(
            "POST", "/api/members/status", {"email": "preview@example.com", "status": "active"},
            cookie=owner_cookie, csrf=owner_auth["csrf_token"],
        )
        self.assertEqual((status, payload["status"]), (200, "active"))
        self.assertIn("csrf_token", preview_auth)

    def test_static_contract_contains_truth_labels_feedback_and_mobile_rules(self) -> None:
        html = (PRODUCT / "static" / "index.html").read_text(encoding="utf-8")
        css = (PRODUCT / "static" / "styles.css").read_text(encoding="utf-8")
        js = (PRODUCT / "static" / "app.js").read_text(encoding="utf-8")
        for marker in ("PRIVATE PREVIEW", "不收款", "不连接券商", "canonical-positions", "feedback-form"):
            self.assertIn(marker, html)
        self.assertIn("@media (max-width: 720px)", css)
        self.assertIn('/api/private-preview', js)
        self.assertIn('/api/feedback', js)
        self.assertIn('payload.schema_version !== "private-preview-v1"', js)


if __name__ == "__main__":
    unittest.main()
