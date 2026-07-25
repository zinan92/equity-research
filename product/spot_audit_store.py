"""Append-only human decisions for E4 spot-audit assignments."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from auth_store import AUTH_DB_PATH, initialize_auth
from data_store import connect
from data_core.contracts import digest
from data_core.e4_spot_audit_assignments import E4_SPOT_AUDIT_ASSIGNMENTS_SCHEMA_VERSION


class SpotAuditReviewError(RuntimeError): pass


SCHEMA = """
CREATE TABLE IF NOT EXISTS e4_spot_audit_reviews (
 id TEXT PRIMARY KEY, assignment_receipt_sha256 TEXT NOT NULL, ticker TEXT NOT NULL, assignment_identity_json TEXT NOT NULL,
 reviewer_id TEXT NOT NULL REFERENCES members(id), numeric_result TEXT NOT NULL CHECK (numeric_result IN ('pass','fail')),
 page_result TEXT NOT NULL CHECK (page_result IN ('pass','fail')), page_number INTEGER NOT NULL CHECK (page_number > 0),
 quoted_label TEXT NOT NULL, rationale TEXT NOT NULL, decided_at TEXT NOT NULL,
 UNIQUE(assignment_receipt_sha256,ticker));
CREATE TRIGGER IF NOT EXISTS e4_spot_audit_reviews_no_update BEFORE UPDATE ON e4_spot_audit_reviews BEGIN SELECT RAISE(ABORT, 'spot audit rows are append-only'); END;
CREATE TRIGGER IF NOT EXISTS e4_spot_audit_reviews_no_delete BEFORE DELETE ON e4_spot_audit_reviews BEGIN SELECT RAISE(ABORT, 'spot audit rows are append-only'); END;
"""


def _now() -> str: return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
def _sha(value: object) -> str: return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def initialize_spot_audit_reviews(db_path: Path = AUTH_DB_PATH) -> None:
    initialize_auth(db_path)
    with closing(connect(db_path)) as conn:
        conn.executescript(SCHEMA)
        triggers = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'e4_spot_audit_reviews_%'")}
        if triggers != {"e4_spot_audit_reviews_no_update", "e4_spot_audit_reviews_no_delete"}:
            raise SpotAuditReviewError("spot-audit append-only guards are unavailable")
        conn.commit()


def _owner(member: Mapping[str, Any], conn: sqlite3.Connection) -> None:
    row = conn.execute("SELECT role,status FROM members WHERE id=?", (member.get("id"),)).fetchone()
    if not row or row["role"] != "owner" or row["status"] != "active": raise PermissionError("owner access required")


def _assignment(path: Path, ticker: str) -> tuple[bytes, dict[str, Any]]:
    raw = path.read_bytes(); receipt = json.loads(raw)
    if receipt.get("schema_version") != E4_SPOT_AUDIT_ASSIGNMENTS_SCHEMA_VERSION or receipt.get("data_kind") != "runtime_only_audit": raise SpotAuditReviewError("valid audit assignment receipt is required")
    if receipt.get("receipt_hash") != digest({key: value for key, value in receipt.items() if key != "receipt_hash"}): raise SpotAuditReviewError("audit assignment receipt identity is invalid")
    matches = [row for row in receipt.get("assignments", []) if isinstance(row, Mapping) and row.get("ticker") == ticker and row.get("review_status") == "pending_human_review"]
    if len(matches) != 1: raise SpotAuditReviewError("audit assignment is unavailable or ambiguous")
    row = matches[0]; identity = {key: row[key] for key in ("ticker", "report_model_hash", "document_identity", "numeric_check", "page_citation_check")}
    return raw, identity


def append_spot_audit_review(member: Mapping[str, Any], assignment_path: Path, payload: Mapping[str, Any], db_path: Path = AUTH_DB_PATH) -> dict[str, Any]:
    initialize_spot_audit_reviews(db_path)
    ticker = str(payload.get("ticker") or "").upper(); raw, identity = _assignment(assignment_path, ticker)
    numeric, page = str(payload.get("numeric_result") or ""), str(payload.get("page_result") or "")
    try: page_number = int(payload.get("page_number"))
    except (TypeError, ValueError) as exc: raise SpotAuditReviewError("page_number must be a positive integer") from exc
    label, rationale = " ".join(str(payload.get("quoted_label") or "").split()), " ".join(str(payload.get("rationale") or "").split())
    if numeric not in {"pass", "fail"} or page not in {"pass", "fail"} or page_number < 1 or not label or not 10 <= len(rationale) <= 2000: raise SpotAuditReviewError("review payload is incomplete")
    lineage = hashlib.sha256(raw).hexdigest(); review_id = "spot_audit_" + _sha({"lineage": lineage, "ticker": ticker})[:20]
    with closing(connect(db_path)) as conn:
        conn.execute("BEGIN IMMEDIATE"); _owner(member, conn)
        try: conn.execute("INSERT INTO e4_spot_audit_reviews VALUES (?,?,?,?,?,?,?,?,?,?,?)", (review_id, lineage, ticker, json.dumps(identity, ensure_ascii=False, sort_keys=True), member["id"], numeric, page, page_number, label, rationale, _now()))
        except sqlite3.IntegrityError as exc: raise SpotAuditReviewError("audit assignment already has a review decision") from exc
        conn.commit(); return {"review_id": review_id, "ticker": ticker, "assignment_identity": identity, "reviewer_id": member["id"], "numeric_result": numeric, "page_result": page, "page_number": page_number, "quoted_label": label, "rationale": rationale}


def export_spot_audit_reviews(member: Mapping[str, Any], assignment_path: Path, db_path: Path = AUTH_DB_PATH) -> dict[str, Any]:
    initialize_spot_audit_reviews(db_path)
    raw = assignment_path.read_bytes(); receipt = json.loads(raw); _assignment(assignment_path, str(receipt.get("assignments", [{}])[0].get("ticker") or ""))
    lineage = hashlib.sha256(raw).hexdigest()
    with closing(connect(db_path)) as conn:
        _owner(member, conn); rows = conn.execute("SELECT * FROM e4_spot_audit_reviews WHERE assignment_receipt_sha256=? ORDER BY decided_at,id", (lineage,)).fetchall()
        decisions = [{**{key: row[key] for key in ("ticker", "reviewer_id", "numeric_result", "page_result", "page_number", "quoted_label", "rationale", "decided_at")}, "assignment_identity": json.loads(row["assignment_identity_json"])} for row in rows]
    output = {"schema_version": "e4-s4-spot-audit-review-decisions-v1", "data_kind": "runtime_only_audit", "assignment_receipt_sha256": lineage, "decisions": decisions, "truth_boundary": {"decisions_are_explicit_human_reviews": True, "does_not_change_e4_acceptance": True, "no_auto_pass": True}}
    output["receipt_hash"] = _sha(output); return output
