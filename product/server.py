from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import mimetypes
import os
import sqlite3
import time
import zipfile
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
from portfolio_allocation import (
    CanonicalPortfolioError, _report_binding,
    load_portfolio_history,
    load_portfolio_state,
    portfolio_diff,
    portfolio_state_root,
)
from portfolio_ledger import (
    PortfolioLedgerError,
    verify_ledger_history,
    verify_ledger_fills_against_source,
    verify_ledger_matches_portfolio,
    verify_ledger_payload,
)
from publication_pack import latest_pack
from auth_store import (
    AUTH_DB_PATH, authenticate, create_invite, create_session, has_entitlement, initialize_auth, list_members,
    list_audit_events, redeem_access_code, redeem_invite, revoke_session, rotate_csrf, session_member,
    set_member_access_role, set_member_status, verify_csrf,
)
from industry_intelligence import IndustryIntelligenceError, dossier_payload, overview_payload
from feedback_store import FeedbackError, feedback_export, initialize_feedback, list_feedback, submit_feedback
from claim_review_store import ClaimReviewError, append_claim_review, export_claim_review_decisions, initialize_claim_reviews
from spot_audit_store import SpotAuditReviewError, append_spot_audit_review, export_spot_audit_reviews, initialize_spot_audit_reviews
from spot_audit_assignment_reader import SpotAuditAssignmentReadError, load_assignment
from partial_model_store import PartialModelStoreError, load_partial_model
from billing_store import (
    BillingError, billing_export, billing_status, effective_member, initialize_billing,
    payment_controls, record_payment, record_refund, set_payment_controls,
)


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
REFRESH_LOCK = Lock()
LOGIN_LOCK = Lock()
LOGIN_ATTEMPTS: dict[str, list[float]] = {}
LOGIN_IP_ATTEMPTS: dict[str, list[float]] = {}
AUTH_REQUIRED = os.getenv("PARK_AUTH_REQUIRED", "0") == "1"
COOKIE_SECURE = os.getenv("PARK_COOKIE_SECURE", "0") == "1"
PRIVATE_PREVIEW = os.getenv("PARK_PRIVATE_PREVIEW", "0") == "1"
MANUAL_PAID_PILOT = PRIVATE_PREVIEW and os.getenv("PARK_MANUAL_PAID_PILOT", "0") == "1"
PRIVATE_PREVIEW_SCHEMA_VERSION = "private-preview-v1"
SESSION_COOKIE = "__Host-park_session" if COOKIE_SECURE else "park_session"


def canonical_portfolio_source_db() -> Path:
    return Path(os.environ.get("PARK_CANONICAL_PORTFOLIO_SOURCE_DB", ROOT / "runtime" / "m4-live.db"))


def canonical_portfolio_root() -> Path:
    return Path(os.environ.get("PARK_CANONICAL_PORTFOLIO_ROOT", ROOT / "runtime" / "canonical_portfolio"))


def private_report_root() -> Path:
    return Path(os.environ.get("PARK_PRIVATE_REPORT_ROOT", ROOT / "runtime" / "private-preview-reports"))


def private_research_pack_root() -> Path:
    return Path(os.environ.get("PARK_PRIVATE_RESEARCH_PACK", ROOT / "runtime" / "private-preview-research-pack"))


def claim_review_candidate_receipt() -> Path:
    root = Path(os.environ.get("PARK_SELL_SIDE_EVIDENCE_ROOT", ROOT / "runtime" / "sell-side-evidence")).resolve()
    try:
        pointer = json.loads((root / "sell-side-claim-candidates-latest.json").read_text(encoding="utf-8"))
        name = str(pointer.get("receipt") or "")
        if not name or Path(name).name != name:
            raise ValueError("unsafe candidate receipt pointer")
        target = (root / name).resolve()
        target.relative_to(root)
        if not target.is_file() or target.is_symlink():
            raise ValueError("candidate receipt unavailable")
        return target
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise ClaimReviewError("sell-side candidate receipt is unavailable") from exc


def partial_model_root() -> Path:
    return Path(os.environ.get("PARK_PARTIAL_MODELS_ROOT", ROOT / "runtime" / "partial-report-models"))


def spot_audit_assignment_receipt() -> Path:
    root = Path(os.environ.get("PARK_SPOT_AUDIT_ROOT", ROOT / "runtime" / "spot-audits")).resolve()
    try:
        pointer = json.loads((root / "spot-audit-assignments-latest.json").read_text(encoding="utf-8")); name = str(pointer.get("receipt") or "")
        if not name or Path(name).name != name: raise ValueError("unsafe audit assignment pointer")
        target = (root / name).resolve(); target.relative_to(root)
        if not target.is_file() or target.is_symlink(): raise ValueError("audit assignment unavailable")
        return target
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise SpotAuditReviewError("spot-audit assignment receipt is unavailable") from exc


def _sha256_file(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def private_research_pack_info(portfolio: dict | None = None) -> dict:
    current = portfolio or load_portfolio_state()
    root = private_research_pack_root().resolve()
    manifest_path = root / "pack-manifest.json"
    archive_path = root / "research-pack.zip"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CanonicalPortfolioError("private research pack manifest is unavailable") from exc
    if not isinstance(manifest, dict):
        raise CanonicalPortfolioError("private research pack manifest is invalid")
    pack_hash = manifest.pop("pack_hash", None)
    expected_hash = hashlib.sha256(_canonical_json(manifest).encode()).hexdigest()
    if (
        pack_hash != expected_hash
        or manifest.get("schema_version") != "canonical-research-pack-v1"
        or manifest.get("portfolio_id") != current["portfolio_id"]
        or manifest.get("portfolio_payload_hash") != current["payload_hash"]
        or manifest.get("snapshot_id") != current["snapshot"]["snapshot_id"]
    ):
        raise CanonicalPortfolioError("private research pack identity mismatch")
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise CanonicalPortfolioError("private research pack files are invalid")
    canonical_root = canonical_portfolio_root().resolve()
    reports = private_report_root().resolve()
    canonical_sources = {
        "portfolio.json": canonical_root / "versions" / f"{current['portfolio_id']}.json",
        "diff.json": canonical_root / "latest-diff.json",
        "ledger.json": canonical_root / "latest-ledger.json",
        "ledger-history.json": canonical_root / "ledger-history.json",
        **{
            f"reports/{position['ticker']}.json": reports / f"{position['ticker']}.json"
            for position in current["positions"]
        },
    }
    if set(files) != set(canonical_sources):
        raise CanonicalPortfolioError("private research pack file set differs from canonical release inputs")
    actual: dict[str, str] = {}
    pack_paths: dict[str, Path] = {}
    for name in sorted(files):
        target = (root / name).resolve()
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise CanonicalPortfolioError("private research pack path escapes its root") from exc
        if not target.is_file() or target.is_symlink():
            raise CanonicalPortfolioError("private research pack file is unavailable")
        pack_paths[name] = target
        actual[name] = _sha256_file(target)
    if actual != files or not archive_path.is_file() or archive_path.is_symlink():
        raise CanonicalPortfolioError("private research pack differs from its manifest")
    for name, source in canonical_sources.items():
        if not source.is_file() or source.is_symlink() or actual[name] != _sha256_file(source):
            raise CanonicalPortfolioError(f"private research pack member differs from canonical release input: {name}")
    try:
        with zipfile.ZipFile(archive_path) as archive:
            expected_members = sorted([*files, "pack-manifest.json"])
            if sorted(archive.namelist()) != expected_members or archive.testzip() is not None:
                raise CanonicalPortfolioError("private research pack archive membership is invalid")
            if any(
                archive.read(name) != (manifest_path if name == "pack-manifest.json" else pack_paths[name]).read_bytes()
                for name in expected_members
            ):
                raise CanonicalPortfolioError("private research pack archive member mismatch")
    except (OSError, zipfile.BadZipFile) as exc:
        raise CanonicalPortfolioError("private research pack archive is invalid") from exc
    return {
        "schema_version": manifest["schema_version"],
        "portfolio_id": manifest["portfolio_id"],
        "snapshot_id": manifest["snapshot_id"],
        "report_bundle_hash": manifest["report_bundle_hash"],
        "pack_hash": pack_hash,
        "archive_sha256": _sha256_file(archive_path),
        "report_count": sum(1 for name in files if name.startswith("reports/")),
        "download": "/downloads/private-preview/research-pack.zip",
        "truth_boundary": manifest["truth_boundary"],
    }


def private_report_payload(ticker: str, portfolio: dict | None = None) -> dict:
    current = portfolio or load_portfolio_state()
    symbol = ticker.upper()
    position = next((item for item in current["positions"] if item["ticker"] == symbol), None)
    if position is None:
        raise CanonicalPublicationError(f"private preview report is outside the canonical portfolio: {symbol}")
    root = private_report_root().resolve()
    path = (root / f"{symbol}.json").resolve()
    try:
        path.relative_to(root)
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise CanonicalPublicationError(f"private preview report is unavailable: {symbol}") from exc
    if not isinstance(report, dict):
        raise CanonicalPublicationError(f"private preview report is invalid: {symbol}")
    try:
        binding = _report_binding(report, current["snapshot"]["snapshot_id"])
    except CanonicalPortfolioError as exc:
        raise CanonicalPublicationError(f"private preview report failed validation: {symbol}") from exc
    if binding != position["report_binding"]:
        raise CanonicalPublicationError(f"private preview report binding mismatch: {symbol}")
    return report


def product_report_payload(ticker: str) -> dict | None:
    """Resolve the product report without hiding a corrupt canonical active version."""
    if PRIVATE_PREVIEW:
        return private_report_payload(ticker)
    return canonical_active_report(ticker) or report_payload(ticker)


def route_entitlement(route: str) -> str:
    if route.startswith(("/api/members", "/api/invites", "/api/feedback")):
        return "manage_members"
    if route.startswith("/api/research/batches") or route == "/api/research/editorial-queue":
        return "manage_members"
    if route.startswith("/api/research/sell-side-claim-review"):
        return "manage_members"
    if route.startswith("/api/research/spot-audit-review"):
        return "manage_members"
    if route.startswith("/api/research/spot-audit-assignment/"):
        return "manage_members"
    if route.startswith("/api/research/partial-model/"):
        return "deep_reports"
    if route.startswith("/api/publication-packs") or route.startswith("/downloads/publication-packs"):
        return "publication_downloads"
    if route.startswith(("/api/reports/", "/api/research/evidence/", "/api/research/editorial", "/api/report-versions/")):
        return "deep_reports"
    return "dashboard"


def private_preview_get_entitlement(route: str) -> str | None:
    if route == "/api/private-preview":
        return "dashboard"
    if route == "/api/industry-intelligence" or route.startswith("/api/industry-intelligence/dossiers/"):
        return "dashboard"
    if route.startswith("/api/reports/"):
        return "deep_reports"
    if route in {"/api/members", "/api/members/audit", "/api/feedback", "/api/feedback/export", "/api/research/sell-side-claim-review/export"}:
        return "manage_members"
    if MANUAL_PAID_PILOT and route == "/api/billing/me":
        return "dashboard"
    if MANUAL_PAID_PILOT and route in {"/api/billing", "/api/billing/export", "/api/billing/settings"}:
        return "manage_members"
    return None


def canonical_private_preview_payload() -> dict:
    current = load_portfolio_state()
    history = load_portfolio_history()
    root = portfolio_state_root()
    try:
        diff = json.loads((root / "latest-diff.json").read_text(encoding="utf-8"))
        ledger = json.loads((root / "latest-ledger.json").read_text(encoding="utf-8"))
        ledger_history = json.loads((root / "ledger-history.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CanonicalPortfolioError("canonical preview state is incomplete") from exc
    verify_ledger_payload(ledger, expected_portfolio_id=current["portfolio_id"])
    verify_ledger_matches_portfolio(ledger, current)
    verify_ledger_history(ledger_history, expected_current_portfolio_id=current["portfolio_id"])
    if len(history) != len(ledger_history["versions"]):
        raise PortfolioLedgerError("model ledger history length mismatch")
    for portfolio, ledger_version in zip(history, ledger_history["versions"]):
        verify_ledger_matches_portfolio(ledger_version, portfolio)
    verify_ledger_fills_against_source(ledger_history, canonical_portfolio_source_db())
    if len(history) < 2 or diff != portfolio_diff(history[-2], current):
        raise CanonicalPortfolioError("canonical preview diff is invalid or stale")
    for position in current["positions"]:
        private_report_payload(position["ticker"], current)
    payload = {
        "schema_version": PRIVATE_PREVIEW_SCHEMA_VERSION,
        "preview": {
            "label": "MANUAL PAID PILOT" if MANUAL_PAID_PILOT else "PRIVATE PREVIEW",
            "accepts_payment": False,
            "broker_connected": False,
            "personalized_portfolio": False,
            "feedback_enabled": True,
            "exact_report_bindings_verified": True,
            "route_surface": "explicit_allowlist",
        },
        "paid_pilot": {
            "enabled": MANUAL_PAID_PILOT,
            "contract_version": "manual-paid-community-v1" if MANUAL_PAID_PILOT else None,
            "fulfillment_mode": "manual_external" if MANUAL_PAID_PILOT else None,
            "online_checkout": False,
            "payment_provider_connected": False,
            "paid_pilot_ready": False,
            "entitlements_derived_from_billing": MANUAL_PAID_PILOT,
        },
        "portfolio": current,
        "history": history,
        "diff": diff,
        "ledger": ledger,
        "ledger_history": ledger_history,
    }
    if MANUAL_PAID_PILOT:
        payload["research_pack"] = private_research_pack_info(current)
    return payload


def feedback_page_context(payload: dict) -> dict:
    portfolio = canonical_private_preview_payload()["portfolio"]
    page_type = payload.get("page_type")
    if page_type == "portfolio":
        return {
            "page_type": "portfolio",
            "ticker": None,
            "portfolio_id": portfolio["portfolio_id"],
            "snapshot_id": portfolio["snapshot"]["snapshot_id"],
            "report_hash": None,
            "page_identity": portfolio["payload_hash"],
        }
    ticker = str(payload.get("ticker", "")).upper()
    position = next((item for item in portfolio["positions"] if item["ticker"] == ticker), None)
    if page_type != "report" or position is None:
        raise FeedbackError("feedback report is outside the current portfolio")
    report = product_report_payload(ticker)
    expected_hash = position["report_binding"]["report_hash"]
    if not report or report.get("report_hash") != expected_hash:
        raise FeedbackError("feedback report identity is unavailable")
    return {
        "page_type": "report",
        "ticker": ticker,
        "portfolio_id": portfolio["portfolio_id"],
        "snapshot_id": portfolio["snapshot"]["snapshot_id"],
        "report_hash": expected_hash,
        "page_identity": expected_hash,
    }


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
        member = session_member(self._session_token()) if AUTH_REQUIRED else {
            "id": "local-owner", "email": "local@park.invalid", "display_name": "Park",
            "role": "owner", "tier": "owner",
            "entitlements": ["dashboard", "deep_reports", "publication_downloads", "approve_publication", "manage_members"],
        }
        return effective_member(member) if AUTH_REQUIRED and MANUAL_PAID_PILOT else member

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
        member = effective_member(member) if AUTH_REQUIRED and MANUAL_PAID_PILOT and member else member
        public = None if member is None else {
            key: member[key] for key in ("id", "email", "display_name", "role", "tier", "entitlements", "billing")
            if key in member
        }
        return {
            "auth_required": AUTH_REQUIRED,
            "private_preview": PRIVATE_PREVIEW,
            "manual_paid_pilot": MANUAL_PAID_PILOT,
            "member": public,
            "csrf_token": csrf_token,
        }

    def do_GET(self) -> None:  # noqa: N802
        route = urlparse(self.path).path
        if route == "/api/health":
            if PRIVATE_PREVIEW:
                try:
                    canonical_private_preview_payload()
                except (CanonicalPortfolioError, CanonicalPublicationError, PortfolioLedgerError):
                    self._json(
                        {"status": "blocked", "product": "park-equity-research-preview", "auth_required": True},
                        HTTPStatus.SERVICE_UNAVAILABLE,
                    )
                else:
                    self._json({"status": "ok", "product": "park-equity-research-preview", "auth_required": True})
                return
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
        if route == "/downloads/private-preview/research-pack.zip":
            if not MANUAL_PAID_PILOT:
                if self._authorize("dashboard") is None:
                    return
                self._json({"error": "private_preview_route_unavailable"}, HTTPStatus.NOT_FOUND)
                return
            if self._authorize("publication_downloads") is None:
                return
            self._private_research_pack_download()
            return
        if route.startswith("/downloads/publication-packs/"):
            if PRIVATE_PREVIEW:
                if self._authorize("dashboard") is None:
                    return
                self._json({"error": "private_preview_route_unavailable"}, HTTPStatus.NOT_FOUND)
                return
            if self._authorize("publication_downloads") is None:
                return
            self._publication_download(route)
            return
        if route.startswith("/api/"):
            if PRIVATE_PREVIEW:
                entitlement = private_preview_get_entitlement(route)
                if entitlement is None:
                    if self._authorize("dashboard") is None:
                        return
                    self._json({"error": "private_preview_route_unavailable"}, HTTPStatus.NOT_FOUND)
                    return
                if self._authorize(entitlement) is None:
                    return
            elif self._authorize(route_entitlement(route)) is None:
                return
        if route == "/api/private-preview":
            try:
                payload = canonical_private_preview_payload()
                if MANUAL_PAID_PILOT:
                    member = self._member()
                    payload["billing"] = member.get("billing") or billing_status(member["id"])
                self._json(payload)
            except (BillingError, CanonicalPortfolioError, CanonicalPublicationError, PortfolioLedgerError) as exc:
                self._json({"error": "private_preview_unavailable", "detail": str(exc)}, HTTPStatus.CONFLICT)
            return
        if route == "/api/industry-intelligence":
            try:
                self._json(overview_payload())
            except IndustryIntelligenceError as exc:
                self._json({"error": "industry_intelligence_unavailable", "detail": str(exc)}, HTTPStatus.CONFLICT)
            return
        if route.startswith("/api/industry-intelligence/dossiers/"):
            code = unquote(route.removeprefix("/api/industry-intelligence/dossiers/"))
            try:
                payload = dossier_payload(code)
            except IndustryIntelligenceError as exc:
                self._json({"error": "industry_intelligence_unavailable", "detail": str(exc)}, HTTPStatus.CONFLICT)
                return
            if payload is None:
                self._json({"error": "dossier_not_found", "code": code}, HTTPStatus.NOT_FOUND)
            else:
                self._json(payload)
            return
        if route == "/api/billing/me":
            try:
                member = self._member()
                self._json({
                    "billing": member.get("billing") or billing_status(member["id"]),
                    "research_pack": private_research_pack_info(),
                })
            except (BillingError, CanonicalPortfolioError) as exc:
                self._json({"error": "billing_unavailable", "detail": str(exc)}, HTTPStatus.CONFLICT)
            return
        if route == "/api/billing/settings":
            try:
                member = self._member()
                self._json(payment_controls(member["id"]))
            except (BillingError, PermissionError) as exc:
                self._json({"error": "billing_unavailable", "detail": str(exc)}, HTTPStatus.CONFLICT)
            return
        if route in {"/api/billing", "/api/billing/export"}:
            try:
                member = self._member()
                payload = billing_export(member["id"])
                headers = {"Content-Disposition": "attachment; filename=paid-community-billing.json"} if route.endswith("/export") else None
                self._json(payload, headers=headers)
            except (BillingError, PermissionError) as exc:
                self._json({"error": "billing_unavailable", "detail": str(exc)}, HTTPStatus.CONFLICT)
            return
        if route == "/api/members":
            member = self._member()
            try:
                members = list_members(member["id"])
                self._json({"members": [effective_member(item) for item in members] if MANUAL_PAID_PILOT else members})
            except PermissionError:
                self._json({"error": "owner_required"}, HTTPStatus.FORBIDDEN)
            return
        if route == "/api/members/audit":
            member = self._member()
            try:
                self._json({"events": list_audit_events(member["id"])})
            except PermissionError:
                self._json({"error": "owner_required"}, HTTPStatus.FORBIDDEN)
            return
        if route == "/api/feedback":
            member = self._member()
            try:
                self._json({"feedback": list_feedback(member["id"])})
            except PermissionError:
                self._json({"error": "owner_required"}, HTTPStatus.FORBIDDEN)
            return
        if route == "/api/feedback/export":
            member = self._member()
            try:
                payload = feedback_export(member["id"])
            except PermissionError:
                self._json({"error": "owner_required"}, HTTPStatus.FORBIDDEN)
            else:
                self._json(payload, headers={"Content-Disposition": "attachment; filename=private-preview-feedback.json"})
            return
        if route == "/api/research/sell-side-claim-review/export":
            member = self._member()
            try:
                self._json(export_claim_review_decisions(member, claim_review_candidate_receipt()), headers={"Content-Disposition": "attachment; filename=sell-side-claim-review-decisions.json"})
            except (ClaimReviewError, PermissionError) as exc:
                self._json({"error": "claim_review_unavailable", "detail": str(exc)}, HTTPStatus.CONFLICT)
            return
        if route == "/api/research/spot-audit-review/export":
            member = self._member()
            try: self._json(export_spot_audit_reviews(member, spot_audit_assignment_receipt()), headers={"Content-Disposition": "attachment; filename=spot-audit-review-decisions.json"})
            except (SpotAuditReviewError, PermissionError) as exc: self._json({"error": "spot_audit_unavailable", "detail": str(exc)}, HTTPStatus.CONFLICT)
            return
        if route.startswith("/api/research/spot-audit-assignment/"):
            ticker = unquote(route.removeprefix("/api/research/spot-audit-assignment/"))
            try: self._json(load_assignment(ticker, spot_audit_assignment_receipt()))
            except SpotAuditAssignmentReadError as exc: self._json({"error":"spot_audit_assignment_unavailable","detail":str(exc)}, HTTPStatus.CONFLICT)
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
        if route == "/api/canonical/portfolio":
            try:
                self._json(load_portfolio_state())
            except CanonicalPortfolioError as exc:
                self._json({"error": "canonical_portfolio_unavailable", "detail": str(exc)}, HTTPStatus.CONFLICT)
            return
        if route == "/api/canonical/portfolio/history":
            try:
                self._json({"portfolios": load_portfolio_history()})
            except CanonicalPortfolioError as exc:
                self._json({"error": "canonical_portfolio_history_unavailable", "detail": str(exc)}, HTTPStatus.CONFLICT)
            return
        if route == "/api/canonical/portfolio/ledger/history":
            path = portfolio_state_root() / "ledger-history.json"
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                current = load_portfolio_state()
                verify_ledger_history(payload, expected_current_portfolio_id=current["portfolio_id"])
                history = load_portfolio_history()
                if len(history) != len(payload["versions"]):
                    raise PortfolioLedgerError("model ledger history length mismatch")
                for portfolio, ledger_version in zip(history, payload["versions"]):
                    verify_ledger_matches_portfolio(ledger_version, portfolio)
                verify_ledger_fills_against_source(payload, canonical_portfolio_source_db())
            except (OSError, json.JSONDecodeError, CanonicalPortfolioError, PortfolioLedgerError):
                self._json({"error": "canonical_portfolio_ledger_history_unavailable"}, HTTPStatus.CONFLICT)
            else:
                self._json(payload)
            return
        if route == "/api/canonical/portfolio/ledger":
            path = portfolio_state_root() / "latest-ledger.json"
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                current = load_portfolio_state()
                verify_ledger_payload(payload, expected_portfolio_id=current["portfolio_id"])
                verify_ledger_matches_portfolio(payload, current)
                verify_ledger_fills_against_source(payload, canonical_portfolio_source_db())
            except (OSError, json.JSONDecodeError, CanonicalPortfolioError, PortfolioLedgerError):
                self._json({"error": "canonical_portfolio_ledger_unavailable"}, HTTPStatus.CONFLICT)
            else:
                self._json(payload)
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
        if route.startswith("/api/research/partial-model/"):
            ticker = unquote(route.removeprefix("/api/research/partial-model/"))
            try:
                self._json(load_partial_model(ticker, partial_model_root()))
            except PartialModelStoreError as exc:
                self._json({"error": "partial_model_unavailable", "detail": str(exc)}, HTTPStatus.CONFLICT)
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
        if route in {"/api/auth/access-code", "/api/auth/login", "/api/auth/signup"}:
            self._auth_entry(route)
            return
        member = self._authorize("dashboard")
        if member is None:
            return
        if AUTH_REQUIRED and not verify_csrf(member, self.headers.get("X-CSRF-Token")):
            self._json({"error": "csrf_rejected"}, HTTPStatus.FORBIDDEN)
            return
        private_post_routes = {"/api/auth/logout", "/api/feedback", "/api/invites", "/api/members/status", "/api/members/role", "/api/research/sell-side-claim-review", "/api/research/spot-audit-review"}
        if MANUAL_PAID_PILOT:
            private_post_routes.update({"/api/billing/payment", "/api/billing/refund", "/api/billing/settings"})
        if PRIVATE_PREVIEW and route not in private_post_routes:
            self._json({"error": "private_preview_route_unavailable"}, HTTPStatus.NOT_FOUND)
            return
        if route == "/api/auth/logout":
            revoke_session(self._session_token())
            self._json({"status": "signed_out"}, headers={"Set-Cookie": self._cookie("", clear=True)})
            return
        if route == "/api/feedback":
            try:
                body = self._read_json()
                if body.get("page_type") == "report" and not has_entitlement(member, "deep_reports"):
                    self._json({"error": "entitlement_required", "entitlement": "deep_reports"}, HTTPStatus.FORBIDDEN)
                    return
                result = submit_feedback(member, body, feedback_page_context(body))
            except FeedbackError as exc:
                status = HTTPStatus.TOO_MANY_REQUESTS if "rate limit" in str(exc) else HTTPStatus.BAD_REQUEST
                self._json({"error": "feedback_rejected", "detail": str(exc)}, status)
            except (CanonicalPortfolioError, PortfolioLedgerError) as exc:
                self._json({"error": "private_preview_unavailable", "detail": str(exc)}, HTTPStatus.CONFLICT)
            else:
                self._json({"status": "accepted", "feedback": result}, HTTPStatus.CREATED)
            return
        if route == "/api/research/sell-side-claim-review":
            if not has_entitlement(member, "manage_members"):
                self._json({"error": "owner_required"}, HTTPStatus.FORBIDDEN)
                return
            try:
                result = append_claim_review(member, claim_review_candidate_receipt(), self._read_json())
            except (ClaimReviewError, PermissionError) as exc:
                self._json({"error": "claim_review_rejected", "detail": str(exc)}, HTTPStatus.BAD_REQUEST)
            else:
                self._json({"status": "accepted", "review": result}, HTTPStatus.CREATED)
            return
        if route == "/api/research/spot-audit-review":
            if not has_entitlement(member, "manage_members"):
                self._json({"error": "owner_required"}, HTTPStatus.FORBIDDEN); return
            try: result = append_spot_audit_review(member, spot_audit_assignment_receipt(), self._read_json())
            except (SpotAuditReviewError, PermissionError) as exc: self._json({"error": "spot_audit_rejected", "detail": str(exc)}, HTTPStatus.BAD_REQUEST)
            else: self._json({"status": "accepted", "review": result}, HTTPStatus.CREATED)
            return
        if route == "/api/invites":
            if not has_entitlement(member, "manage_members"):
                self._json({"error": "owner_required"}, HTTPStatus.FORBIDDEN)
                return
            try:
                body = self._read_json()
                if MANUAL_PAID_PILOT and body.get("tier") == "paid":
                    raise ValueError("paid entitlement is derived from the billing ledger")
                result = create_invite(
                    member["id"], str(body.get("tier", "")),
                    max_uses=int(body.get("max_uses", 1)), valid_days=int(body.get("valid_days", 7)),
                )
            except (TypeError, ValueError, PermissionError) as exc:
                self._json({"error": "invite_rejected", "detail": str(exc)}, HTTPStatus.BAD_REQUEST)
            else:
                self._json(result, HTTPStatus.CREATED)
            return
        if route == "/api/members/status":
            if not has_entitlement(member, "manage_members"):
                self._json({"error": "owner_required"}, HTTPStatus.FORBIDDEN)
                return
            try:
                body = self._read_json()
                result = set_member_status(member["id"], body.get("email", ""), body.get("status", ""))
            except (ValueError, PermissionError) as exc:
                self._json({"error": "member_update_rejected", "detail": str(exc)}, HTTPStatus.BAD_REQUEST)
            else:
                self._json(result)
            return
        if route == "/api/members/role":
            if not has_entitlement(member, "manage_members"):
                self._json({"error": "owner_required"}, HTTPStatus.FORBIDDEN)
                return
            try:
                body = self._read_json()
                result = set_member_access_role(member["id"], body.get("email", ""), body.get("role", ""))
            except (ValueError, PermissionError) as exc:
                self._json({"error": "member_role_rejected", "detail": str(exc)}, HTTPStatus.BAD_REQUEST)
            else:
                self._json(result)
            return
        if MANUAL_PAID_PILOT and route in {"/api/billing/payment", "/api/billing/refund", "/api/billing/settings"}:
            if not has_entitlement(member, "manage_members"):
                self._json({"error": "owner_required"}, HTTPStatus.FORBIDDEN)
                return
            try:
                body = self._read_json()
                if route == "/api/billing/settings":
                    result = set_payment_controls(member["id"], body.get("accept_new_payments"))
                elif route == "/api/billing/refund":
                    # Refunds inherit immutable release context from the original payment and
                    # must remain available during a portfolio or research-pack outage.
                    result = record_refund(member["id"], body)
                else:
                    portfolio = load_portfolio_state()
                    pack = private_research_pack_info(portfolio)
                    result = record_payment(
                        member["id"], body, portfolio["portfolio_id"], pack["pack_hash"],
                    )
            except (BillingError, CanonicalPortfolioError, PermissionError, sqlite3.IntegrityError) as exc:
                status = HTTPStatus.CONFLICT if isinstance(exc, BillingError) else HTTPStatus.BAD_REQUEST
                self._json({"error": "billing_rejected", "detail": str(exc)}, status)
            else:
                self._json(result, HTTPStatus.CREATED if route.endswith("/payment") or route.endswith("/refund") else HTTPStatus.OK)
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
            if route.endswith("/access-code"):
                code = str(body.get("code", "")).strip()
                identity = f"code:{hashlib.sha256(code.encode()).hexdigest()[:24]}"
            else:
                identity = str(body.get("email", "")).strip().lower()[:254]
            forwarded = self.headers.get("CF-Connecting-IP", "") if self.client_address[0] in {"127.0.0.1", "::1"} else ""
            try:
                client_ip = str(ipaddress.ip_address(forwarded or self.client_address[0]))
            except ValueError:
                client_ip = self.client_address[0]
            key = f"{client_ip}:{identity}"
            with LOGIN_LOCK:
                if len(LOGIN_ATTEMPTS) > 10_000 or len(LOGIN_IP_ATTEMPTS) > 10_000:
                    LOGIN_ATTEMPTS.clear()
                    LOGIN_IP_ATTEMPTS.clear()
                attempts = [stamp for stamp in LOGIN_ATTEMPTS.get(key, []) if now - stamp < 900]
                ip_attempts = [stamp for stamp in LOGIN_IP_ATTEMPTS.get(client_ip, []) if now - stamp < 900]
                if len(attempts) >= 10 or len(ip_attempts) >= 30:
                    self._json({"error": "too_many_attempts"}, HTTPStatus.TOO_MANY_REQUESTS)
                    return
                attempts.append(now)
                ip_attempts.append(now)
                LOGIN_ATTEMPTS[key] = attempts
                LOGIN_IP_ATTEMPTS[client_ip] = ip_attempts
            if route.endswith("/access-code"):
                member = redeem_access_code(body.get("code", ""))
            elif route.endswith("/signup"):
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
            LOGIN_IP_ATTEMPTS[client_ip] = [stamp for stamp in LOGIN_IP_ATTEMPTS.get(client_ip, []) if stamp != now]
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

    def _private_research_pack_download(self) -> None:
        info = private_research_pack_info()
        target = private_research_pack_root().resolve() / "research-pack.zip"
        body = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Disposition", 'attachment; filename="park-equity-research-pack.zip"')
        self.send_header("X-Research-Pack-Hash", info["pack_hash"])
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
    if PRIVATE_PREVIEW and (not AUTH_REQUIRED or not COOKIE_SECURE):
        raise RuntimeError("private preview requires PARK_AUTH_REQUIRED=1 and PARK_COOKIE_SECURE=1")
    if PRIVATE_PREVIEW and args.host not in {"127.0.0.1", "::1", "localhost"}:
        raise RuntimeError("private preview origin must bind to loopback")
    if PRIVATE_PREVIEW:
        research_db = DB_PATH.expanduser().resolve()
        auth_db = AUTH_DB_PATH.expanduser().resolve()
        code_boundary = ROOT.resolve().parent
        if auth_db == research_db or auth_db == code_boundary or code_boundary in auth_db.parents:
            raise RuntimeError("private preview auth database must be separate and outside packaged product code")
    initialize(DB_PATH, force_seed=args.reset_demo)
    if AUTH_REQUIRED:
        initialize_auth()
        initialize_claim_reviews()
    if MANUAL_PAID_PILOT:
        initialize_feedback()
        initialize_billing()
    elif PRIVATE_PREVIEW:
        initialize_feedback()
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
