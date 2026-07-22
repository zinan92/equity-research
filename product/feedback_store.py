from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from auth_store import AUTH_DB_PATH, initialize_auth
from data_store import connect


FEEDBACK_SCHEMA_VERSION = "private-preview-feedback-v1"
MAX_FEEDBACK_PER_HOUR = 5
ALLOWED_CATEGORIES = {"clarity", "actionability", "risk", "data", "bug", "other"}
ALLOWED_PAGE_TYPES = {"portfolio", "report"}

FEEDBACK_SCHEMA = """
CREATE TABLE IF NOT EXISTS member_feedback (
  id TEXT PRIMARY KEY,
  member_id TEXT NOT NULL REFERENCES members(id),
  page_type TEXT NOT NULL CHECK (page_type IN ('portfolio','report')),
  ticker TEXT,
  category TEXT NOT NULL CHECK (category IN ('clarity','actionability','risk','data','bug','other')),
  rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
  message TEXT NOT NULL,
  portfolio_id TEXT NOT NULL,
  snapshot_id TEXT NOT NULL,
  report_hash TEXT,
  page_identity TEXT NOT NULL,
  dedupe_key TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_member_feedback_created ON member_feedback(created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_member_feedback_member ON member_feedback(member_id, created_at DESC);
CREATE TRIGGER IF NOT EXISTS member_feedback_no_update
BEFORE UPDATE ON member_feedback BEGIN SELECT RAISE(ABORT, 'feedback audit rows are append-only'); END;
CREATE TRIGGER IF NOT EXISTS member_feedback_no_delete
BEFORE DELETE ON member_feedback BEGIN SELECT RAISE(ABORT, 'feedback audit rows are append-only'); END;
"""

EXPECTED_TRIGGERS = {
    "member_feedback_no_update": "CREATE TRIGGER member_feedback_no_update BEFORE UPDATE ON member_feedback BEGIN SELECT RAISE(ABORT, 'feedback audit rows are append-only'); END",
    "member_feedback_no_delete": "CREATE TRIGGER member_feedback_no_delete BEFORE DELETE ON member_feedback BEGIN SELECT RAISE(ABORT, 'feedback audit rows are append-only'); END",
}


class FeedbackError(RuntimeError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _canonical_sql(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).removesuffix(";")


def initialize_feedback(db_path: Path = AUTH_DB_PATH) -> None:
    initialize_auth(db_path)
    with closing(connect(db_path)) as conn:
        conn.executescript(FEEDBACK_SCHEMA)
        rows = conn.execute(
            "SELECT name,sql FROM sqlite_master WHERE type='trigger' AND name IN (?,?)",
            tuple(EXPECTED_TRIGGERS),
        ).fetchall()
        actual = {row["name"]: _canonical_sql(row["sql"] or "") for row in rows}
        expected = {name: _canonical_sql(sql) for name, sql in EXPECTED_TRIGGERS.items()}
        if actual != expected:
            raise FeedbackError("feedback append-only guard is missing or altered")
        conn.commit()


def _clean_message(value: Any) -> str:
    if not isinstance(value, str):
        raise FeedbackError("feedback message is required")
    message = " ".join(value.split())
    if len(message) < 10 or len(message) > 2_000:
        raise FeedbackError("feedback message must contain 10-2000 characters")
    return message


def _feedback_id(dedupe_key: str) -> str:
    return f"feedback_{dedupe_key[:20]}"


def _public_row(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    value = dict(row)
    return {
        "id": value["id"],
        "member_id": value["member_id"],
        "member_email": value.get("member_email"),
        "member_name": value.get("member_name"),
        "page_type": value["page_type"],
        "ticker": value["ticker"],
        "category": value["category"],
        "rating": value["rating"],
        "message": value["message"],
        "portfolio_id": value["portfolio_id"],
        "snapshot_id": value["snapshot_id"],
        "report_hash": value["report_hash"],
        "page_identity": value["page_identity"],
        "created_at": value["created_at"],
    }


def submit_feedback(
    member: dict[str, Any],
    payload: dict[str, Any],
    page_context: dict[str, Any],
    db_path: Path = AUTH_DB_PATH,
) -> dict[str, Any]:
    initialize_feedback(db_path)
    if not isinstance(member, dict) or not member.get("id"):
        raise FeedbackError("authenticated member is required")
    category = payload.get("category")
    page_type = payload.get("page_type")
    if category not in ALLOWED_CATEGORIES:
        raise FeedbackError("invalid feedback category")
    if page_type not in ALLOWED_PAGE_TYPES or page_context.get("page_type") != page_type:
        raise FeedbackError("invalid feedback page")
    try:
        rating = int(payload.get("rating"))
    except (TypeError, ValueError) as exc:
        raise FeedbackError("feedback rating must be 1-5") from exc
    if rating < 1 or rating > 5:
        raise FeedbackError("feedback rating must be 1-5")
    message = _clean_message(payload.get("message"))
    ticker = page_context.get("ticker")
    portfolio_id = page_context.get("portfolio_id")
    snapshot_id = page_context.get("snapshot_id")
    report_hash = page_context.get("report_hash")
    page_identity = page_context.get("page_identity")
    if not all(isinstance(item, str) and item for item in (portfolio_id, snapshot_id, page_identity)):
        raise FeedbackError("verified page identity is required")
    normalized = {
        "member_id": member["id"],
        "page_type": page_type,
        "ticker": ticker,
        "category": category,
        "rating": rating,
        "message": message.casefold(),
        "page_identity": page_identity,
    }
    dedupe_key = hashlib.sha256(
        json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    created_at = _now().isoformat()
    cutoff = (_now() - timedelta(hours=1)).isoformat()
    with closing(connect(db_path)) as conn:
        conn.execute("BEGIN IMMEDIATE")
        active = conn.execute("SELECT status FROM members WHERE id=?", (member["id"],)).fetchone()
        if not active or active["status"] != "active":
            raise FeedbackError("member is unavailable")
        count = conn.execute(
            "SELECT COUNT(*) AS total FROM member_feedback WHERE member_id=? AND created_at>=?",
            (member["id"], cutoff),
        ).fetchone()["total"]
        if count >= MAX_FEEDBACK_PER_HOUR:
            raise FeedbackError("feedback rate limit exceeded")
        try:
            conn.execute(
                """INSERT INTO member_feedback
                   (id,member_id,page_type,ticker,category,rating,message,portfolio_id,snapshot_id,report_hash,page_identity,dedupe_key,created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    _feedback_id(dedupe_key), member["id"], page_type, ticker, category, rating, message,
                    portfolio_id, snapshot_id, report_hash, page_identity, dedupe_key, created_at,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise FeedbackError("duplicate feedback") from exc
        conn.commit()
        row = conn.execute("SELECT * FROM member_feedback WHERE dedupe_key=?", (dedupe_key,)).fetchone()
    return _public_row(row)


def list_feedback(owner_id: str, db_path: Path = AUTH_DB_PATH) -> list[dict[str, Any]]:
    initialize_feedback(db_path)
    with closing(connect(db_path)) as conn:
        owner = conn.execute("SELECT role,status FROM members WHERE id=?", (owner_id,)).fetchone()
        if not owner or owner["role"] != "owner" or owner["status"] != "active":
            raise PermissionError("owner access required")
        rows = conn.execute(
            """SELECT f.*,m.email AS member_email,m.display_name AS member_name
               FROM member_feedback f JOIN members m ON m.id=f.member_id
               ORDER BY f.created_at DESC,f.id DESC"""
        ).fetchall()
    return [_public_row(row) for row in rows]


def feedback_export(owner_id: str, db_path: Path = AUTH_DB_PATH) -> dict[str, Any]:
    rows = list_feedback(owner_id, db_path)
    payload = {
        "schema_version": FEEDBACK_SCHEMA_VERSION,
        "feedback": rows,
    }
    payload["export_hash"] = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return payload
