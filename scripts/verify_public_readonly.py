#!/usr/bin/env python3
from __future__ import annotations

import argparse
import http.client
import json
from pathlib import Path
import sqlite3
from urllib.parse import urlparse


class VerificationError(RuntimeError):
    pass


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
        raise VerificationError("invalid public read-only URL")
    connection_type = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    connection = connection_type(parsed.hostname, parsed.port, timeout=30)
    try:
        headers = {"Accept": "application/json"}
        body = None
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode()
            headers["Content-Type"] = "application/json"
        if cookie:
            headers["Cookie"] = cookie
        if csrf:
            headers["X-CSRF-Token"] = csrf
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        payload = json.loads(raw) if response.getheader("Content-Type", "").startswith("application/json") else raw
        return response.status, payload, {name.lower(): value for name, value in response.getheaders()}
    finally:
        connection.close()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


MUTABLE_AUTH_TABLES = (
    "members", "invite_codes", "member_sessions", "member_events", "member_feedback",
    "billing_events", "billing_settings", "billing_control_events",
)


def auth_counts(path: Path) -> dict[str, int]:
    resolved = path.expanduser().resolve()
    if not resolved.is_file() or resolved.is_symlink():
        raise VerificationError("auth database is unavailable or unsafe")
    with sqlite3.connect(f"{resolved.as_uri()}?mode=ro", uri=True) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        require(set(MUTABLE_AUTH_TABLES).issubset(tables), "auth database schema is incomplete")
        return {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in MUTABLE_AUTH_TABLES
        }


def verify(base_url: str, dossier_code: str, *, credentials_path: Path | None, auth_db: Path | None) -> dict:
    before_counts = auth_counts(auth_db) if auth_db else None
    status, auth, headers = request(base_url, "GET", "/api/auth/me")
    require(status == 200 and isinstance(auth, dict), "public auth bootstrap is unavailable")
    require(auth.get("auth_required") is True, "server-side auth gate is not enabled")
    require(auth.get("public_read_only") is True and auth.get("authenticated") is False, "anonymous public projection is invalid")
    require(auth.get("member", {}).get("role") == "public_reader", "anonymous reader role is invalid")
    require("id" not in auth["member"] and "email" not in auth["member"], "public projection leaked member identity")
    require("noindex" in headers.get("x-robots-tag", ""), "public archive is missing noindex header")

    status, preview, _ = request(base_url, "GET", "/api/private-preview")
    require(status == 200 and isinstance(preview, dict), "public portfolio is unavailable")
    require(preview.get("preview", {}).get("public_read_only") is True, "portfolio projection is not public read-only")
    require("billing" not in preview and "research_pack" not in preview, "public portfolio leaked private fulfillment fields")
    positions = preview.get("portfolio", {}).get("positions", [])
    require(len(positions) == 8, "public portfolio position count is invalid")

    status, industry, _ = request(base_url, "GET", "/api/industry-intelligence")
    require(status == 200 and isinstance(industry, dict), "public industry overview is unavailable")
    require(industry.get("summary", {}).get("dossier_count") == 489, "public dossier count is invalid")
    require(len(industry.get("three_high_map", {}).get("nodes", [])) == 38, "public segment map count is invalid")
    require(len(industry.get("materials_map", {}).get("nodes", [])) == 94, "public materials map count is invalid")

    status, dossier, _ = request(base_url, "GET", f"/api/industry-intelligence/dossiers/{dossier_code}")
    require(status == 200 and dossier.get("dossier", {}).get("code") == dossier_code, "public dossier is unavailable")
    ticker = positions[0]["ticker"]
    status, report, _ = request(base_url, "GET", f"/api/reports/{ticker}")
    require(status == 200 and report.get("ticker") == ticker, "public current report is unavailable")

    protected = (
        "/api/members", "/api/members/audit", "/api/feedback", "/api/feedback/export",
        "/api/billing", "/api/billing/export", "/api/billing/settings", "/api/billing/me",
        "/api/dashboard", "/api/canonical/portfolio", "/api/research/batches/latest",
        "/downloads/private-preview/research-pack.zip",
        "/downloads/publication-packs/fake/fake.zip",
    )
    for path in protected:
        closed_status, payload, _ = request(base_url, "GET", path)
        require(
            closed_status == 401 and isinstance(payload, dict) and payload.get("error") == "authentication_required",
            f"protected route is not closed: {path}",
        )
    for path, body in (
        ("/api/auth/access-code", {"code": "public-verifier-disabled"}),
        ("/api/auth/signup", {"invite_code": "public-verifier-disabled"}),
    ):
        closed_status, payload, _ = request(base_url, "POST", path, body)
        require(
            closed_status == 404 and isinstance(payload, dict)
            and payload.get("error") == "public_read_only_auth_route_disabled",
            f"disabled public auth route is not closed: {path}",
        )
    anonymous_writes = ("/api/feedback", "/api/invites", "/api/refresh", "/api/billing/payment")
    for path in anonymous_writes:
        closed_status, payload, _ = request(base_url, "POST", path, {})
        require(
            closed_status == 401 and isinstance(payload, dict) and payload.get("error") == "authentication_required",
            f"anonymous write route is not closed: {path}",
        )
    if before_counts is not None:
        require(auth_counts(auth_db) == before_counts, "anonymous verification mutated the auth database")

    owner_verified = False
    if credentials_path is not None:
        credentials = json.loads(credentials_path.expanduser().read_text(encoding="utf-8"))
        required = {"owner_email", "owner_password", "member_email", "member_password"}
        require(required.issubset(credentials), "public verifier credentials are incomplete")
        member_status, member_auth, member_headers = request(base_url, "POST", "/api/auth/login", {
            "email": credentials["member_email"], "password": credentials["member_password"],
        })
        require(
            member_status == 401 and isinstance(member_auth, dict) and member_auth.get("error") == "invalid_credentials"
            and "set-cookie" not in member_headers,
            "non-owner login is not disabled in public mode",
        )
        owner_status, owner_auth, owner_headers = request(base_url, "POST", "/api/auth/login", {
            "email": credentials["owner_email"], "password": credentials["owner_password"],
        })
        set_cookie = owner_headers.get("set-cookie", "")
        require(
            owner_status == 200 and isinstance(owner_auth, dict) and owner_auth.get("authenticated") is True
            and owner_auth.get("member", {}).get("role") == "owner" and set_cookie,
            "Owner login regression failed",
        )
        owner_cookie = set_cookie.split(";", 1)[0]
        require(request(base_url, "GET", "/api/members", cookie=owner_cookie)[0] == 200, "Owner member view failed")
        require(request(base_url, "GET", "/api/members/audit", cookie=owner_cookie)[0] == 200, "Owner audit view failed")
        csrf_status, csrf_payload, _ = request(base_url, "POST", "/api/feedback", {}, cookie=owner_cookie)
        require(
            csrf_status == 403 and isinstance(csrf_payload, dict) and csrf_payload.get("error") == "csrf_rejected",
            "Owner write route accepted a request without CSRF",
        )
        logout_status, _, _ = request(
            base_url, "POST", "/api/auth/logout", {}, cookie=owner_cookie, csrf=owner_auth["csrf_token"],
        )
        require(logout_status == 200, "Owner logout failed")
        return_status, return_auth, _ = request(base_url, "GET", "/api/auth/me")
        require(
            return_status == 200 and return_auth.get("public_read_only") is True
            and return_auth.get("authenticated") is False,
            "Owner logout did not return to public visitor mode",
        )
        owner_verified = True
    return {
        "status": "verified_public_read_only",
        "url": base_url,
        "portfolio_id": preview["portfolio"]["portfolio_id"],
        "report_ticker": ticker,
        "dossier_code": dossier_code,
        "counts": {"positions": 8, "segments": 38, "materials": 94, "dossiers": 489},
        "protected_get_routes_verified": len(protected),
        "anonymous_write_routes_verified": len(anonymous_writes) + 2,
        "anonymous_auth_database_unchanged": before_counts is not None,
        "owner_regression_verified": owner_verified,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify the anonymous read-only frozen research release")
    parser.add_argument("--url", default="https://research.park-ai-intel.com")
    parser.add_argument("--dossier", default="300223")
    parser.add_argument("--credentials", type=Path)
    parser.add_argument("--auth-db", type=Path)
    args = parser.parse_args()
    try:
        receipt = verify(
            args.url.rstrip("/"), args.dossier,
            credentials_path=args.credentials, auth_db=args.auth_db,
        )
    except (OSError, http.client.HTTPException, json.JSONDecodeError, KeyError, TypeError, VerificationError) as exc:
        raise SystemExit(f"public read-only verification failed: {exc}") from exc
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
