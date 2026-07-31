from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from data_store import DB_PATH


AUTH_DB_PATH = Path(os.environ.get("PARK_AUTH_DB", DB_PATH))


PBKDF2_ROUNDS = 310_000
SESSION_HOURS = 72
TIER_ENTITLEMENTS = {
    "preview": ["dashboard"],
    "member": ["dashboard", "deep_reports"],
    "paid": ["dashboard", "deep_reports", "publication_downloads"],
    "owner": ["dashboard", "deep_reports", "publication_downloads", "approve_publication", "manage_members"],
}

AUTH_SCHEMA = """
CREATE TABLE IF NOT EXISTS members (
  id TEXT PRIMARY KEY,
  email TEXT NOT NULL UNIQUE,
  display_name TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('owner','member')),
  access_role TEXT NOT NULL DEFAULT 'member' CHECK (access_role IN ('owner','editor','member')),
  tier TEXT NOT NULL CHECK (tier IN ('preview','member','paid','owner')),
  password_hash TEXT NOT NULL,
  password_salt TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','suspended')),
  entitlements_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS invite_codes (
  id TEXT PRIMARY KEY,
  code_hash TEXT NOT NULL UNIQUE,
  tier TEXT NOT NULL CHECK (tier IN ('preview','member','paid')),
  entitlements_json TEXT NOT NULL,
  max_uses INTEGER NOT NULL CHECK (max_uses > 0),
  use_count INTEGER NOT NULL DEFAULT 0 CHECK (use_count >= 0),
  expires_at TEXT NOT NULL,
  created_by TEXT NOT NULL REFERENCES members(id),
  created_at TEXT NOT NULL,
  revoked_at TEXT
);
CREATE TABLE IF NOT EXISTS member_sessions (
  id TEXT PRIMARY KEY,
  member_id TEXT NOT NULL REFERENCES members(id),
  token_hash TEXT NOT NULL UNIQUE,
  csrf_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  revoked_at TEXT
);
CREATE TABLE IF NOT EXISTS member_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  member_id TEXT,
  event_type TEXT NOT NULL,
  detail_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS member_events_no_update
BEFORE UPDATE ON member_events
BEGIN
  SELECT RAISE(ABORT, 'member events are append-only');
END;
CREATE TRIGGER IF NOT EXISTS member_events_no_delete
BEFORE DELETE ON member_events
BEGIN
  SELECT RAISE(ABORT, 'member events are append-only');
END;
CREATE INDEX IF NOT EXISTS idx_member_sessions_token ON member_sessions(token_hash);
CREATE INDEX IF NOT EXISTS idx_member_sessions_member ON member_sessions(member_id, expires_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_single_active_owner ON members(role) WHERE role='owner' AND status='active';
"""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def connect(db_path: Path = AUTH_DB_PATH) -> sqlite3.Connection:
    """Open the identity store without creating or seeding research tables."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _iso(value: datetime) -> str:
    return value.isoformat()


def _normalize_email(email: str) -> str:
    if not isinstance(email, str):
        raise ValueError("valid email is required")
    value = email.strip().lower()
    if "@" not in value or len(value) > 254:
        raise ValueError("valid email is required")
    return value


def _password_digest(password: str, salt_hex: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), PBKDF2_ROUNDS).hex()


def _validate_password(password: str) -> None:
    if not isinstance(password, str) or len(password) < 12 or len(password) > 256:
        raise ValueError("password must contain 12-256 characters")


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def initialize_auth(db_path: Path = AUTH_DB_PATH) -> None:
    with closing(connect(db_path)) as conn:
        conn.executescript(AUTH_SCHEMA)
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(members)")}
        if "access_role" not in columns:
            conn.execute(
                "ALTER TABLE members ADD COLUMN access_role TEXT NOT NULL DEFAULT 'member' "
                "CHECK (access_role IN ('owner','editor','member'))"
            )
        conn.execute("UPDATE members SET access_role='owner' WHERE role='owner' AND access_role='member'")
        conn.commit()


def _public_member(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    value = dict(row)
    return {
        "id": value["id"], "email": value["email"], "display_name": value["display_name"],
        "role": value.get("access_role", value["role"]), "tier": value["tier"], "status": value["status"],
        "entitlements": json.loads(value["entitlements_json"]),
    }


_SENSITIVE_AUDIT_KEYS = frozenset({
    "password", "password_hash", "password_salt", "token", "csrf", "csrf_token",
    "code", "invite_code", "secret", "credential", "authorization", "cookie",
})


def _safe_audit_detail(value: Any, *, depth: int = 0) -> Any:
    """Keep audit receipts useful without providing a future secret sink."""
    if depth > 4:
        return "[truncated]"
    if isinstance(value, dict):
        return {
            str(key): "[redacted]" if str(key).lower() in _SENSITIVE_AUDIT_KEYS
            else _safe_audit_detail(item, depth=depth + 1)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_safe_audit_detail(item, depth=depth + 1) for item in value[:50]]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:512]


def _record(conn: sqlite3.Connection, member_id: str | None, event_type: str, detail: dict[str, Any]) -> None:
    conn.execute(
        "INSERT INTO member_events (member_id,event_type,detail_json,created_at) VALUES (?,?,?,?)",
        (member_id, event_type, json.dumps(_safe_audit_detail(detail), ensure_ascii=False, sort_keys=True), _iso(_now())),
    )


def create_owner(email: str, password: str, display_name: str, db_path: Path = AUTH_DB_PATH) -> dict[str, Any]:
    initialize_auth(db_path)
    email = _normalize_email(email)
    _validate_password(password)
    salt = secrets.token_hex(16)
    member_id = f"member_{secrets.token_hex(10)}"
    with closing(connect(db_path)) as conn:
        conn.execute("BEGIN IMMEDIATE")
        if conn.execute("SELECT 1 FROM members WHERE role='owner' AND status='active'").fetchone():
            raise ValueError("an active owner already exists")
        conn.execute(
            """INSERT INTO members
               (id,email,display_name,role,tier,access_role,password_hash,password_salt,status,entitlements_json,created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (member_id, email, display_name.strip() if isinstance(display_name, str) and display_name.strip() else "Park", "owner", "owner", "owner", _password_digest(password, salt), salt,
             "active", json.dumps(TIER_ENTITLEMENTS["owner"]), _iso(_now())),
        )
        _record(conn, member_id, "owner_created", {"email": email})
        conn.commit()
        row = conn.execute("SELECT * FROM members WHERE id=?", (member_id,)).fetchone()
    return _public_member(row)


def authenticate(
    email: str,
    password: str,
    db_path: Path = AUTH_DB_PATH,
    *,
    required_role: str | None = None,
) -> dict[str, Any] | None:
    initialize_auth(db_path)
    email = _normalize_email(email)
    invalid_password = not isinstance(password, str) or len(password) > 256
    candidate = password if isinstance(password, str) else ""
    with closing(connect(db_path)) as conn:
        row = conn.execute("SELECT * FROM members WHERE email=?", (email,)).fetchone()
        if not row:
            _password_digest(candidate, "00" * 16)
            return None
        expected = _password_digest(candidate, row["password_salt"])
        if (
            invalid_password
            or row["status"] != "active"
            or not hmac.compare_digest(expected, row["password_hash"])
            or (required_role is not None and row["role"] != required_role)
        ):
            _record(conn, row["id"], "login_failed", {"role_restricted": required_role is not None})
            conn.commit()
            return None
        _record(conn, row["id"], "login_succeeded", {})
        conn.commit()
        return _public_member(row)


def create_session(member_id: str, db_path: Path = AUTH_DB_PATH) -> dict[str, Any]:
    initialize_auth(db_path)
    token = secrets.token_urlsafe(48)
    csrf = secrets.token_urlsafe(32)
    created = _now()
    expires = created + timedelta(hours=SESSION_HOURS)
    session_id = f"session_{secrets.token_hex(12)}"
    with closing(connect(db_path)) as conn:
        member = conn.execute("SELECT * FROM members WHERE id=? AND status='active'", (member_id,)).fetchone()
        if not member:
            raise ValueError("member is unavailable")
        conn.execute(
            """INSERT INTO member_sessions
               (id,member_id,token_hash,csrf_hash,created_at,expires_at,last_seen_at,revoked_at)
               VALUES (?,?,?,?,?,?,?,NULL)""",
            (session_id, member_id, _hash_token(token), _hash_token(csrf), _iso(created), _iso(expires), _iso(created)),
        )
        _record(conn, member_id, "session_created", {"session_id": session_id})
        conn.commit()
    return {"token": token, "csrf_token": csrf, "expires_at": _iso(expires), "member": _public_member(member)}


def session_member(token: str | None, db_path: Path = AUTH_DB_PATH) -> dict[str, Any] | None:
    if not token:
        return None
    initialize_auth(db_path)
    now = _iso(_now())
    with closing(connect(db_path)) as conn:
        row = conn.execute(
            """SELECT m.*, s.id AS session_id, s.csrf_hash, s.expires_at
               FROM member_sessions s JOIN members m ON m.id=s.member_id
               WHERE s.token_hash=? AND s.revoked_at IS NULL AND s.expires_at>? AND m.status='active'""",
            (_hash_token(token), now),
        ).fetchone()
        if not row:
            return None
        conn.execute("UPDATE member_sessions SET last_seen_at=? WHERE id=?", (now, row["session_id"]))
        conn.commit()
    member = _public_member(row)
    member["session_id"] = row["session_id"]
    member["csrf_hash"] = row["csrf_hash"]
    member["expires_at"] = row["expires_at"]
    return member


def verify_csrf(member: dict[str, Any], csrf_token: str | None) -> bool:
    return bool(csrf_token) and hmac.compare_digest(member.get("csrf_hash", ""), _hash_token(csrf_token))


def rotate_csrf(token: str | None, db_path: Path = AUTH_DB_PATH) -> str | None:
    if not token:
        return None
    initialize_auth(db_path)
    csrf = secrets.token_urlsafe(32)
    with closing(connect(db_path)) as conn:
        row = conn.execute(
            "SELECT id FROM member_sessions WHERE token_hash=? AND revoked_at IS NULL AND expires_at>?",
            (_hash_token(token), _iso(_now())),
        ).fetchone()
        if not row:
            return None
        conn.execute("UPDATE member_sessions SET csrf_hash=? WHERE id=?", (_hash_token(csrf), row["id"]))
        conn.commit()
    return csrf


def revoke_session(token: str | None, db_path: Path = AUTH_DB_PATH) -> None:
    if not token:
        return
    initialize_auth(db_path)
    with closing(connect(db_path)) as conn:
        row = conn.execute("SELECT member_id,id FROM member_sessions WHERE token_hash=?", (_hash_token(token),)).fetchone()
        if row:
            conn.execute("UPDATE member_sessions SET revoked_at=? WHERE id=?", (_iso(_now()), row["id"]))
            _record(conn, row["member_id"], "session_revoked", {"session_id": row["id"]})
            conn.commit()


def create_invite(
    owner_id: str,
    tier: str,
    db_path: Path = AUTH_DB_PATH,
    *,
    max_uses: int = 1,
    valid_days: int = 7,
) -> dict[str, Any]:
    initialize_auth(db_path)
    if tier not in {"preview", "member", "paid"}:
        raise ValueError("invalid invite tier")
    if max_uses < 1 or max_uses > 100 or valid_days < 1 or valid_days > 90:
        raise ValueError("invalid invite limits")
    code = secrets.token_urlsafe(24)
    invite_id = f"invite_{secrets.token_hex(10)}"
    expires = _now() + timedelta(days=valid_days)
    with closing(connect(db_path)) as conn:
        owner = conn.execute("SELECT role,status FROM members WHERE id=?", (owner_id,)).fetchone()
        if not owner or owner["role"] != "owner" or owner["status"] != "active":
            raise PermissionError("owner access required")
        conn.execute(
            """INSERT INTO invite_codes
               (id,code_hash,tier,entitlements_json,max_uses,use_count,expires_at,created_by,created_at,revoked_at)
               VALUES (?,?,?,?,?,0,?,?,?,NULL)""",
            (invite_id, _hash_token(code), tier, json.dumps(TIER_ENTITLEMENTS[tier]), max_uses, _iso(expires), owner_id, _iso(_now())),
        )
        _record(conn, owner_id, "invite_created", {"invite_id": invite_id, "tier": tier, "max_uses": max_uses})
        conn.commit()
    return {"invite_id": invite_id, "code": code, "tier": tier, "max_uses": max_uses, "expires_at": _iso(expires)}


def redeem_invite(
    code: str,
    email: str,
    password: str,
    display_name: str,
    db_path: Path = AUTH_DB_PATH,
) -> dict[str, Any]:
    initialize_auth(db_path)
    if not isinstance(code, str):
        raise ValueError("invite is invalid, expired, revoked, or exhausted")
    email = _normalize_email(email)
    _validate_password(password)
    now = _iso(_now())
    salt = secrets.token_hex(16)
    member_id = f"member_{secrets.token_hex(10)}"
    with closing(connect(db_path)) as conn:
        conn.execute("BEGIN IMMEDIATE")
        invite = conn.execute(
            """SELECT * FROM invite_codes WHERE code_hash=? AND revoked_at IS NULL
               AND expires_at>? AND use_count<max_uses""",
            (_hash_token(code.strip()), now),
        ).fetchone()
        if not invite:
            raise ValueError("invite is invalid, expired, revoked, or exhausted")
        conn.execute(
            """INSERT INTO members
               (id,email,display_name,role,tier,access_role,password_hash,password_salt,status,entitlements_json,created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (member_id, email, display_name.strip() if isinstance(display_name, str) and display_name.strip() else email.split("@", 1)[0], "member", invite["tier"],
             "member", _password_digest(password, salt), salt, "active", invite["entitlements_json"], now),
        )
        conn.execute("UPDATE invite_codes SET use_count=use_count+1 WHERE id=?", (invite["id"],))
        _record(conn, member_id, "invite_redeemed", {"invite_id": invite["id"], "tier": invite["tier"]})
        conn.commit()
        row = conn.execute("SELECT * FROM members WHERE id=?", (member_id,)).fetchone()
    return _public_member(row)


def redeem_access_code(code: str, db_path: Path = AUTH_DB_PATH) -> dict[str, Any]:
    """Consume a single-use invite without collecting email, name, or password."""
    initialize_auth(db_path)
    if not isinstance(code, str) or not code.strip() or len(code) > 256:
        raise ValueError("access code is invalid, expired, revoked, or already used")
    now = _iso(_now())
    member_id = f"member_{secrets.token_hex(10)}"
    guest_suffix = secrets.token_hex(3).upper()
    internal_email = f"guest-{member_id.removeprefix('member_')}@access.invalid"
    salt = secrets.token_hex(16)
    unavailable_password = secrets.token_urlsafe(48)
    with closing(connect(db_path)) as conn:
        conn.execute("BEGIN IMMEDIATE")
        invite = conn.execute(
            """SELECT * FROM invite_codes WHERE code_hash=? AND revoked_at IS NULL
               AND expires_at>? AND use_count<max_uses""",
            (_hash_token(code.strip()), now),
        ).fetchone()
        if not invite or invite["max_uses"] != 1:
            raise ValueError("access code is invalid, expired, revoked, or already used")
        conn.execute(
            """INSERT INTO members
               (id,email,display_name,role,tier,access_role,password_hash,password_salt,status,entitlements_json,created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                member_id, internal_email, f"访客 {guest_suffix}", "member", invite["tier"],
                "member", _password_digest(unavailable_password, salt), salt, "active", invite["entitlements_json"], now,
            ),
        )
        conn.execute("UPDATE invite_codes SET use_count=use_count+1 WHERE id=?", (invite["id"],))
        _record(conn, member_id, "access_code_redeemed", {"invite_id": invite["id"], "tier": invite["tier"]})
        conn.commit()
        row = conn.execute("SELECT * FROM members WHERE id=?", (member_id,)).fetchone()
    return _public_member(row)


def has_entitlement(member: dict[str, Any] | None, entitlement: str) -> bool:
    return bool(member) and entitlement in (member.get("entitlements") or [])


def list_members(owner_id: str, db_path: Path = AUTH_DB_PATH) -> list[dict[str, Any]]:
    initialize_auth(db_path)
    with closing(connect(db_path)) as conn:
        owner = conn.execute("SELECT role,status FROM members WHERE id=?", (owner_id,)).fetchone()
        if not owner or owner["role"] != "owner" or owner["status"] != "active":
            raise PermissionError("owner access required")
        rows = conn.execute("SELECT * FROM members ORDER BY created_at,id").fetchall()
    return [_public_member(row) for row in rows]


def set_member_status(owner_id: str, email: str, status: str, db_path: Path = AUTH_DB_PATH) -> dict[str, Any]:
    initialize_auth(db_path)
    if status not in {"active", "suspended"}:
        raise ValueError("invalid member status")
    email = _normalize_email(email)
    with closing(connect(db_path)) as conn:
        conn.execute("BEGIN IMMEDIATE")
        owner = conn.execute("SELECT role,status FROM members WHERE id=?", (owner_id,)).fetchone()
        target = conn.execute("SELECT * FROM members WHERE email=?", (email,)).fetchone()
        if not owner or owner["role"] != "owner" or owner["status"] != "active":
            raise PermissionError("owner access required")
        if not target:
            raise ValueError("member not found")
        if target["role"] == "owner":
            raise ValueError("owner status cannot be changed here")
        conn.execute("UPDATE members SET status=? WHERE id=?", (status, target["id"]))
        if status == "suspended":
            conn.execute("UPDATE member_sessions SET revoked_at=? WHERE member_id=? AND revoked_at IS NULL", (_iso(_now()), target["id"]))
        _record(conn, owner_id, "member_status_changed", {"member_id": target["id"], "status": status})
        conn.commit()
        updated = conn.execute("SELECT * FROM members WHERE id=?", (target["id"],)).fetchone()
    return _public_member(updated)


def set_member_access_role(owner_id: str, email: str, access_role: str, db_path: Path = AUTH_DB_PATH) -> dict[str, Any]:
    """Assign the non-escalating product role; only the durable owner may do so."""
    initialize_auth(db_path)
    if access_role not in {"editor", "member"}:
        raise ValueError("invalid member access role")
    email = _normalize_email(email)
    with closing(connect(db_path)) as conn:
        conn.execute("BEGIN IMMEDIATE")
        owner = conn.execute("SELECT role,status FROM members WHERE id=?", (owner_id,)).fetchone()
        target = conn.execute("SELECT * FROM members WHERE email=?", (email,)).fetchone()
        if not owner or owner["role"] != "owner" or owner["status"] != "active":
            raise PermissionError("owner access required")
        if not target:
            raise ValueError("member not found")
        if target["role"] == "owner":
            raise ValueError("owner role cannot be changed here")
        conn.execute("UPDATE members SET access_role=? WHERE id=?", (access_role, target["id"]))
        _record(conn, owner_id, "member_role_changed", {"member_id": target["id"], "access_role": access_role})
        conn.commit()
        updated = conn.execute("SELECT * FROM members WHERE id=?", (target["id"],)).fetchone()
    return _public_member(updated)


def list_audit_events(owner_id: str, db_path: Path = AUTH_DB_PATH, *, limit: int = 100) -> list[dict[str, Any]]:
    """Return bounded, actor-scoped audit rows to the active owner only."""
    initialize_auth(db_path)
    if not isinstance(limit, int) or not 1 <= limit <= 500:
        raise ValueError("audit limit must be 1-500")
    with closing(connect(db_path)) as conn:
        owner = conn.execute("SELECT role,status FROM members WHERE id=?", (owner_id,)).fetchone()
        if not owner or owner["role"] != "owner" or owner["status"] != "active":
            raise PermissionError("owner access required")
        rows = conn.execute(
            "SELECT id,member_id,event_type,detail_json,created_at FROM member_events ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [
        {
            "id": row["id"], "actor_member_id": row["member_id"], "event_type": row["event_type"],
            "detail": json.loads(row["detail_json"]), "created_at": row["created_at"],
        }
        for row in rows
    ]


def revoke_invite(owner_id: str, invite_id: str, db_path: Path = AUTH_DB_PATH) -> dict[str, Any]:
    initialize_auth(db_path)
    with closing(connect(db_path)) as conn:
        conn.execute("BEGIN IMMEDIATE")
        owner = conn.execute("SELECT role,status FROM members WHERE id=?", (owner_id,)).fetchone()
        invite = conn.execute("SELECT * FROM invite_codes WHERE id=?", (invite_id,)).fetchone()
        if not owner or owner["role"] != "owner" or owner["status"] != "active":
            raise PermissionError("owner access required")
        if not invite:
            raise ValueError("invite not found")
        revoked_at = invite["revoked_at"] or _iso(_now())
        conn.execute("UPDATE invite_codes SET revoked_at=? WHERE id=?", (revoked_at, invite_id))
        _record(conn, owner_id, "invite_revoked", {"invite_id": invite_id})
        conn.commit()
    return {"invite_id": invite_id, "status": "revoked", "revoked_at": revoked_at}
