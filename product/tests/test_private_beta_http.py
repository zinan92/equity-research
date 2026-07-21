from __future__ import annotations

import http.client
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


PRODUCT = Path(__file__).resolve().parents[1]
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from auth_store import create_invite, create_owner, redeem_invite  # noqa: E402
from data_store import initialize  # noqa: E402


class PrivateBetaHttpTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.db = Path(cls.tmp.name) / "private-beta.db"
        initialize(cls.db, force_seed=True)
        owner = create_owner("park@example.com", "owner-password-2026", "Park", cls.db)
        preview = create_invite(owner["id"], "preview", cls.db)
        paid = create_invite(owner["id"], "paid", cls.db)
        redeem_invite(preview["code"], "preview@example.com", "preview-password-2026", "Preview", cls.db)
        redeem_invite(paid["code"], "paid@example.com", "paid-password-2026", "Paid", cls.db)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            cls.port = sock.getsockname()[1]
        env = dict(os.environ)
        env.update({"PARK_DASHBOARD_DB": str(cls.db), "PARK_AUTH_REQUIRED": "1", "PARK_COOKIE_SECURE": "0"})
        cls.server = subprocess.Popen(
            [sys.executable, str(PRODUCT / "server.py"), "--host", "127.0.0.1", "--port", str(cls.port)],
            cwd=PRODUCT.parent, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                status, _, _ = cls.request("GET", "/api/health")
                if status == 200:
                    break
            except OSError:
                time.sleep(0.05)
        else:
            raise RuntimeError("private beta test server did not start")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.terminate()
        cls.server.wait(timeout=5)
        cls.tmp.cleanup()

    @classmethod
    def request(cls, method: str, path: str, payload: dict | None = None, *, cookie: str | None = None, csrf: str | None = None):
        conn = http.client.HTTPConnection("127.0.0.1", cls.port, timeout=5)
        headers = {}
        body = None
        if payload is not None:
            body = json.dumps(payload).encode()
            headers["Content-Type"] = "application/json"
        if cookie:
            headers["Cookie"] = cookie
        if csrf:
            headers["X-CSRF-Token"] = csrf
        conn.request(method, path, body=body, headers=headers)
        response = conn.getresponse()
        raw = response.read()
        result = json.loads(raw) if response.getheader("Content-Type", "").startswith("application/json") else raw
        headers_out = dict(response.getheaders())
        conn.close()
        return response.status, result, headers_out

    @classmethod
    def login(cls, email: str, password: str):
        status, payload, headers = cls.request("POST", "/api/auth/login", {"email": email, "password": password})
        if status != 200:
            raise AssertionError(f"login failed: {status} {payload}")
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        return payload, cookie, headers["Set-Cookie"]

    def test_anonymous_api_is_closed_but_login_bootstrap_is_open(self) -> None:
        status, payload, _ = self.request("GET", "/api/auth/me")
        self.assertEqual(status, 200)
        self.assertTrue(payload["auth_required"])
        self.assertIsNone(payload["member"])
        status, payload, _ = self.request("GET", "/api/dashboard")
        self.assertEqual((status, payload["error"]), (401, "authentication_required"))
        status, payload, _ = self.request("POST", "/api/auth/login", {"email": None, "password": None})
        self.assertEqual((status, payload["error"]), (400, "auth_rejected"))

    def test_owner_cookie_and_csrf_gate_state_changes(self) -> None:
        auth, cookie, set_cookie = self.login("park@example.com", "owner-password-2026")
        self.assertIn("HttpOnly", set_cookie)
        self.assertIn("SameSite=Strict", set_cookie)
        self.assertIn("approve_publication", auth["member"]["entitlements"])
        status, _, _ = self.request("GET", "/api/dashboard", cookie=cookie)
        self.assertEqual(status, 200)
        status, payload, _ = self.request("POST", "/api/refresh", {}, cookie=cookie)
        self.assertEqual((status, payload["error"]), (403, "csrf_rejected"))

    def test_preview_can_open_dashboard_but_not_deep_reports(self) -> None:
        _, cookie, _ = self.login("preview@example.com", "preview-password-2026")
        self.assertEqual(self.request("GET", "/api/dashboard", cookie=cookie)[0], 200)
        status, payload, _ = self.request("GET", "/api/reports/300750.SZ", cookie=cookie)
        self.assertEqual((status, payload["error"]), (403, "entitlement_required"))
        status, payload, _ = self.request("GET", "/api/research/batches/latest", cookie=cookie)
        self.assertEqual((status, payload["error"]), (403, "entitlement_required"))

    def test_paid_member_can_open_deep_reports(self) -> None:
        auth, cookie, _ = self.login("paid@example.com", "paid-password-2026")
        self.assertIn("publication_downloads", auth["member"]["entitlements"])
        status, payload, _ = self.request("GET", "/api/reports/300750.SZ", cookie=cookie)
        self.assertEqual(status, 200)
        self.assertEqual(payload["ticker"], "300750.SZ")


if __name__ == "__main__":
    unittest.main()
