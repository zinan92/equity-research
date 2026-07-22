from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sqlite3
import time
from http.cookies import SimpleCookie
from threading import Lock
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from data_store import (
    DB_PATH, dashboard_payload, dump_json, initialize, publication_history,
    stock_payload, transition_publication, validate_invariants,
)
from batch_research import latest_batch, run_batch
from research_reports import report_payload
from research_evidence import evidence_coverage
from deepseek_writer import editorial_queue, editorial_status
from data_core import CanonicalPublicationError, canonical_active_report, canonical_active_summary
from refresh_engine import RefreshInProgressError, refresh_status, run_refresh
from report_versions import report_version_history
from portfolio_committee import committee_payload
from publication_pack import latest_pack
from auth_store import (
    authenticate, create_session, has_entitlement, initialize_auth, redeem_invite,
    revoke_session, rotate_csrf, session_member, verify_csrf,
)


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
REFRESH_LOCK = Lock()
LOGIN_LOCK = Lock()
LOGIN_ATTEMPTS: dict[str, list[float]] = {}
AUTH_REQUIRED = os.getenv("PARK_AUTH_REQUIRED", "0") == "1"
COOKIE_SECURE = os.getenv("PARK_COOKIE_SECURE", "0") == "1"
SESSION_COOKIE = "__Host-park_session" if COOKIE_SECURE else "park_session"


def product_report_payload(ticker: str) -> dict | None:
    """Resolve the product report without hiding a corrupt canonical active version."""
    return canonical_active_report(ticker) or report_payload(ticker)


def route_entitlement(route: str) -> str:
    if route.startswith("/api/research/batches") or route == "/api/research/editorial-queue":
        return "manage_members"
    if route.startswith("/api/publication-packs") or route.startswith("/downloads/publication-packs"):
        return "publication_downloads"
    if route.startswith(("/api/reports/", "/api/research/evidence/", "/api/research/editorial", "/api/report-versions/")):
        return "deep_reports"
    return "dashboard"


def public_pack(payload: dict) -> dict:
    pack_id = payload["pack_id"]
    files = {
        name: f"/downloads/publication-packs/{pack_id}/{name}"
        for name in ("report.html", "report-long.png", "report.pdf", "manifest.json")
    }
    files["archive"] = f"/downloads/publication-packs/{pack_id}/{pack_id}.zip"
    return {
        "pack_id": pack_id, "status": payload["status"], "created_at": payload["created_at"],
        "integrity_status": payload["integrity_status"], "integrity_errors": payload["integrity_errors"],
        "manifest_hash": payload["manifest_hash"], "archive_hash": payload["archive_hash"], "downloads": files,
    }


class DashboardHandler(BaseHTTPRequestHandler):
    server_version = "ParkResearchDashboard/0.1"

    def _session_token(self) -> str | None:
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        morsel = cookie.get(SESSION_COOKIE)
        return morsel.value if morsel else None

    def _member(self) -> dict | None:
        return session_member(self._session_token()) if AUTH_REQUIRED else {
            "id": "local-owner", "email": "local@park.invalid", "display_name": "Park",
            "role": "owner", "tier": "owner",
            "entitlements": ["dashboard", "deep_reports", "publication_downloads", "approve_publication", "manage_members"],
        }

    def _authorize(self, entitlement: str) -> dict | None:
        member = self._member()
        if not member:
            self._json({"error": "authentication_required"}, HTTPStatus.UNAUTHORIZED)
            return None
        if not has_entitlement(member, entitlement):
            self._json({"error": "entitlement_required", "entitlement": entitlement}, HTTPStatus.FORBIDDEN)
            return None
        return member

    def _read_json(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("invalid content length") from exc
        if length < 2 or length > 16_384:
            raise ValueError("request body must be 2-16384 bytes")
        try:
            value = json.loads(self.rfile.read(length))
        except Exception as exc:
            raise ValueError("valid JSON body is required") from exc
        if not isinstance(value, dict):
            raise ValueError("JSON object is required")
        return value

    def _cookie(self, token: str, *, clear: bool = False) -> str:
        parts = [f"{SESSION_COOKIE}={token}", "Path=/", "HttpOnly", "SameSite=Strict"]
        if COOKIE_SECURE:
            parts.append("Secure")
        if clear:
            parts.extend(["Max-Age=0", "Expires=Thu, 01 Jan 1970 00:00:00 GMT"])
        else:
            parts.append("Max-Age=259200")
        return "; ".join(parts)

    def _auth_payload(self, member: dict | None, csrf_token: str | None = None) -> dict:
        public = None if member is None else {key: member[key] for key in ("id", "email", "display_name", "role", "tier", "entitlements")}
        return {"auth_required": AUTH_REQUIRED, "member": public, "csrf_token": csrf_token}

    def do_GET(self) -> None:  # noqa: N802
        route = urlparse(self.path).path
        if route == "/api/health":
            payload = dashboard_payload()
            errors = validate_invariants(payload)
            self._json({
                "status": "ok" if not errors else "blocked", "errors": errors,
                "data_mode": payload["snapshot"]["data_mode"],
                "canonical_research": canonical_active_summary(),
            })
            return
        if route == "/api/auth/me":
            member = self._member()
            csrf = rotate_csrf(self._session_token()) if AUTH_REQUIRED and member else None
            self._json(self._auth_payload(member, csrf))
            return
        if route.startswith("/downloads/publication-packs/"):
            if self._authorize("publication_downloads") is None:
                return
            self._publication_download(route)
            return
        if route.startswith("/api/") and self._authorize(route_entitlement(route)) is None:
            return
        if route == "/api/dashboard":
            payload = dashboard_payload()
            payload["validation_errors"] = validate_invariants(payload)
            self._json(payload)
            return
        if route == "/api/committee":
            self._json(committee_payload())
            return
        if route == "/api/publications":
            self._json({"publications": publication_history()})
            return
        if route == "/api/refresh/status":
            self._json(refresh_status())
            return
        if route == "/api/canonical/active":
            self._json(canonical_active_summary())
            return
        if route == "/api/research/batches/latest":
            payload = latest_batch()
            if payload is None:
                self._json({"error": "batch_not_found"}, HTTPStatus.NOT_FOUND)
            else:
                self._json(payload)
            return
        if route == "/api/publication-packs/latest":
            payload = latest_pack()
            if payload is None:
                self._json({"error": "publication_pack_not_found"}, HTTPStatus.NOT_FOUND)
            elif payload.get("integrity_status") != "passed":
                self._json({"error": "publication_pack_unavailable", "integrity_status": payload.get("integrity_status"), "detail": payload.get("integrity_errors")}, HTTPStatus.CONFLICT)
            else:
                self._json(public_pack(payload))
            return
        if route == "/api/research/editorial-queue":
            self._json(editorial_queue())
            return
        if route.startswith("/api/research/evidence/"):
            ticker = unquote(route.removeprefix("/api/research/evidence/"))
            self._json(evidence_coverage(ticker))
            return
        if route.startswith("/api/research/editorial-status/"):
            ticker = unquote(route.removeprefix("/api/research/editorial-status/"))
            try:
                self._json(editorial_status(ticker))
            except KeyError:
                self._json({"error": "stock_not_found", "ticker": ticker}, HTTPStatus.NOT_FOUND)
            return
        if route.startswith("/api/report-versions/"):
            ticker = unquote(route.removeprefix("/api/report-versions/"))
            self._json({"ticker": ticker.upper(), "versions": report_version_history(ticker)})
            return
        if route.startswith("/api/stocks/"):
            ticker = unquote(route.removeprefix("/api/stocks/"))
            payload = stock_payload(ticker)
            if payload is None:
                self._json({"error": "stock_not_found", "ticker": ticker}, HTTPStatus.NOT_FOUND)
            else:
                self._json(payload)
            return
        if route.startswith("/api/reports/"):
            ticker = unquote(route.removeprefix("/api/reports/"))
            try:
                payload = product_report_payload(ticker)
            except CanonicalPublicationError as exc:
                self._json(
                    {"error": "canonical_publication_invalid", "ticker": ticker.upper(), "detail": str(exc)},
                    HTTPStatus.CONFLICT,
                )
                return
            if payload is None:
                self._json({"error": "stock_not_found", "ticker": ticker}, HTTPStatus.NOT_FOUND)
            else:
                self._json(payload)
            return
        if route.startswith("/api/"):
            self._json({"error": "not_found"}, HTTPStatus.NOT_FOUND)
            return
        self._static(route)

    def do_POST(self) -> None:  # noqa: N802
        route = urlparse(self.path).path
        if route in {"/api/auth/login", "/api/auth/signup"}:
            self._auth_entry(route)
            return
        member = self._authorize("dashboard")
        if member is None:
            return
        if AUTH_REQUIRED and not verify_csrf(member, self.headers.get("X-CSRF-Token")):
            self._json({"error": "csrf_rejected"}, HTTPStatus.FORBIDDEN)
            return
        if route == "/api/auth/logout":
            revoke_session(self._session_token())
            self._json({"status": "signed_out"}, headers={"Set-Cookie": self._cookie("", clear=True)})
            return
        if route == "/api/refresh":
            if not has_entitlement(member, "manage_members"):
                self._json({"error": "owner_required"}, HTTPStatus.FORBIDDEN)
                return
            if not REFRESH_LOCK.acquire(blocking=False):
                self._json({"error": "refresh_in_progress"}, HTTPStatus.CONFLICT)
                return
            try:
                result = run_refresh(timeout=12.0)
            except RefreshInProgressError as exc:
                self._json({"error": "refresh_in_progress", "detail": str(exc)}, HTTPStatus.CONFLICT)
            except RuntimeError as exc:
                self._json({"error": "refresh_failed_closed", "detail": str(exc)}, HTTPStatus.SERVICE_UNAVAILABLE)
            else:
                self._json(result)
            finally:
                REFRESH_LOCK.release()
            return
        if route == "/api/research/batches":
            if not has_entitlement(member, "manage_members"):
                self._json({"error": "owner_required"}, HTTPStatus.FORBIDDEN)
                return
            if not REFRESH_LOCK.acquire(blocking=False):
                self._json({"error": "refresh_in_progress"}, HTTPStatus.CONFLICT)
                return
            try:
                try:
                    result = run_batch(timeout=12.0)
                except Exception as exc:
                    self._json(
                        {"error": "batch_failed", "detail": f"{type(exc).__name__}: {exc}"},
                        HTTPStatus.SERVICE_UNAVAILABLE,
                    )
                else:
                    status = HTTPStatus.OK if result["status"] == "success" else HTTPStatus.SERVICE_UNAVAILABLE
                    self._json(result, status)
            finally:
                REFRESH_LOCK.release()
            return
        parts = route.strip("/").split("/")
        if len(parts) == 4 and parts[0] == "api" and parts[1] == "publications" and parts[3] in {"approve", "publish"}:
            if not has_entitlement(member, "approve_publication"):
                self._json({"error": "owner_required"}, HTTPStatus.FORBIDDEN)
                return
            publication_id, action = unquote(parts[2]), parts[3]
            try:
                result = transition_publication(publication_id, action)
            except KeyError:
                self._json({"error": "publication_not_found", "publication_id": publication_id}, HTTPStatus.NOT_FOUND)
            except ValueError as exc:
                self._json({"error": "transition_rejected", "detail": str(exc)}, HTTPStatus.CONFLICT)
            else:
                self._json(result)
            return
        self._json({"error": "not_found"}, HTTPStatus.NOT_FOUND)

    def _auth_entry(self, route: str) -> None:
        if not AUTH_REQUIRED:
            self._json({"error": "auth_disabled_in_local_mode"}, HTTPStatus.CONFLICT)
            return
        try:
            body = self._read_json()
            now = time.monotonic()
            identity = str(body.get("email", "")).strip().lower()[:254]
            key = f"{self.client_address[0]}:{identity}"
            with LOGIN_LOCK:
                if len(LOGIN_ATTEMPTS) > 10_000:
                    LOGIN_ATTEMPTS.clear()
                attempts = [stamp for stamp in LOGIN_ATTEMPTS.get(key, []) if now - stamp < 900]
                if len(attempts) >= 10:
                    self._json({"error": "too_many_attempts"}, HTTPStatus.TOO_MANY_REQUESTS)
                    return
                attempts.append(now)
                LOGIN_ATTEMPTS[key] = attempts
            if route.endswith("/signup"):
                member = redeem_invite(body.get("invite_code", ""), body.get("email", ""), body.get("password", ""), body.get("display_name", ""))
            else:
                member = authenticate(body.get("email", ""), body.get("password", ""))
                if not member:
                    self._json({"error": "invalid_credentials"}, HTTPStatus.UNAUTHORIZED)
                    return
            session = create_session(member["id"])
        except (ValueError, PermissionError, sqlite3.IntegrityError) as exc:
            self._json({"error": "auth_rejected", "detail": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        with LOGIN_LOCK:
            LOGIN_ATTEMPTS.pop(key, None)
        self._json(
            self._auth_payload(session["member"], session["csrf_token"]),
            headers={"Set-Cookie": self._cookie(session["token"])},
        )

    def _publication_download(self, route: str) -> None:
        parts = [unquote(part) for part in route.strip("/").split("/")]
        if len(parts) != 4:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        _, _, pack_id, filename = parts
        payload = latest_pack()
        if not payload or payload.get("integrity_status") != "passed" or payload.get("pack_id") != pack_id:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        pack_dir = Path(payload["pack_dir"]).resolve()
        allowed = {"report.html", "report-long.png", "report.pdf", "manifest.json", f"{pack_id}.zip"}
        if filename not in allowed:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        target = Path(payload["archive"]).resolve() if filename.endswith(".zip") else (pack_dir / filename).resolve()
        if (not filename.endswith(".zip") and target.parent != pack_dir) or not target.is_file() or target.is_symlink():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        body = target.read_bytes()
        content_type, _ = mimetypes.guess_type(target.name)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Disposition", f'attachment; filename="{target.name}"')
        self.send_header("Cache-Control", "private, no-store")
        self._security_headers()
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK, *, headers: dict[str, str] | None = None) -> None:
        body = dump_json(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self._security_headers()
        self.end_headers()
        self.wfile.write(body)

    def _static(self, route: str) -> None:
        requested = "index.html" if route in {"", "/"} else route.lstrip("/")
        target = (STATIC_DIR / requested).resolve()
        if STATIC_DIR.resolve() not in target.parents and target != STATIC_DIR.resolve():
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        if not target.is_file() and Path(requested).suffix:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if not target.is_file():
            target = STATIC_DIR / "index.html"
        body = target.read_bytes()
        content_type, _ = mimetypes.guess_type(target.name)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{content_type or 'application/octet-stream'}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self._security_headers()
        self.end_headers()
        self.wfile.write(body)

    def _security_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if COOKIE_SECURE:
            self.send_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'",
        )

    def log_message(self, format: str, *args: object) -> None:
        print(f"[dashboard] {self.address_string()} {format % args}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the A-share investment committee dashboard")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8877)
    parser.add_argument("--reset-demo", action="store_true")
    args = parser.parse_args()
    initialize(DB_PATH, force_seed=args.reset_demo)
    if AUTH_REQUIRED:
        initialize_auth(DB_PATH)
    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    print(f"A股长期投委会面板: http://{args.host}:{args.port}")
    payload = dashboard_payload(DB_PATH)
    print(f"数据模式: {payload['snapshot']['data_mode']} · 数据库: {DB_PATH}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
