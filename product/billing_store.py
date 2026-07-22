from __future__ import annotations

from contextlib import closing
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from auth_store import AUTH_DB_PATH, TIER_ENTITLEMENTS, initialize_auth
from data_store import connect


BILLING_SCHEMA_VERSION = "manual-paid-community-v1"
ALLOWED_PROVIDERS = {"manual_external", "acceptance_test"}
REFERENCE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{5,127}$")

BILLING_SCHEMA = """
CREATE TABLE IF NOT EXISTS billing_events (
  id TEXT PRIMARY KEY,
  member_id TEXT NOT NULL REFERENCES members(id),
  event_type TEXT NOT NULL CHECK (event_type IN ('payment_confirmed','refund_confirmed')),
  provider TEXT NOT NULL CHECK (provider IN ('manual_external','acceptance_test')),
  provider_event_id TEXT NOT NULL,
  payment_reference TEXT NOT NULL,
  original_event_id TEXT REFERENCES billing_events(id),
  amount_minor INTEGER NOT NULL CHECK (amount_minor BETWEEN 100 AND 100000000),
  currency TEXT NOT NULL CHECK (currency='CNY'),
  test_mode INTEGER NOT NULL CHECK (test_mode IN (0,1)),
  portfolio_id TEXT NOT NULL,
  research_pack_hash TEXT NOT NULL,
  occurred_at TEXT NOT NULL,
  recorded_by TEXT NOT NULL REFERENCES members(id),
  event_hash TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL,
  UNIQUE(provider, provider_event_id),
  CHECK (
    (event_type='payment_confirmed' AND original_event_id IS NULL)
    OR (event_type='refund_confirmed' AND original_event_id IS NOT NULL)
  )
);
CREATE INDEX IF NOT EXISTS idx_billing_member ON billing_events(member_id,created_at,id);
CREATE INDEX IF NOT EXISTS idx_billing_original ON billing_events(original_event_id,event_type);
CREATE UNIQUE INDEX IF NOT EXISTS uq_billing_payment_reference
ON billing_events(provider,payment_reference) WHERE event_type='payment_confirmed';
CREATE UNIQUE INDEX IF NOT EXISTS uq_billing_refund_reference
ON billing_events(provider,payment_reference) WHERE event_type='refund_confirmed';
CREATE TABLE IF NOT EXISTS billing_settings (
  id INTEGER PRIMARY KEY CHECK (id=1),
  accept_new_payments INTEGER NOT NULL CHECK (accept_new_payments IN (0,1)),
  updated_at TEXT NOT NULL,
  updated_by TEXT NOT NULL REFERENCES members(id)
);
CREATE TABLE IF NOT EXISTS billing_control_events (
  id TEXT PRIMARY KEY,
  control_type TEXT NOT NULL CHECK (control_type IN ('accept_new_payments')),
  enabled INTEGER NOT NULL CHECK (enabled IN (0,1)),
  recorded_by TEXT NOT NULL REFERENCES members(id),
  event_hash TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS billing_events_no_update
BEFORE UPDATE ON billing_events BEGIN SELECT RAISE(ABORT, 'billing events are append-only'); END;
CREATE TRIGGER IF NOT EXISTS billing_events_no_delete
BEFORE DELETE ON billing_events BEGIN SELECT RAISE(ABORT, 'billing events are append-only'); END;
CREATE TRIGGER IF NOT EXISTS billing_control_events_no_update
BEFORE UPDATE ON billing_control_events BEGIN SELECT RAISE(ABORT, 'billing control events are append-only'); END;
CREATE TRIGGER IF NOT EXISTS billing_control_events_no_delete
BEFORE DELETE ON billing_control_events BEGIN SELECT RAISE(ABORT, 'billing control events are append-only'); END;
"""

EXPECTED_TRIGGERS = {
    "billing_events_no_update": "CREATE TRIGGER billing_events_no_update BEFORE UPDATE ON billing_events BEGIN SELECT RAISE(ABORT, 'billing events are append-only'); END",
    "billing_events_no_delete": "CREATE TRIGGER billing_events_no_delete BEFORE DELETE ON billing_events BEGIN SELECT RAISE(ABORT, 'billing events are append-only'); END",
    "billing_control_events_no_update": "CREATE TRIGGER billing_control_events_no_update BEFORE UPDATE ON billing_control_events BEGIN SELECT RAISE(ABORT, 'billing control events are append-only'); END",
    "billing_control_events_no_delete": "CREATE TRIGGER billing_control_events_no_delete BEFORE DELETE ON billing_control_events BEGIN SELECT RAISE(ABORT, 'billing control events are append-only'); END",
}
EXPECTED_INDEXES = {
    "uq_billing_payment_reference": "CREATE UNIQUE INDEX uq_billing_payment_reference ON billing_events(provider,payment_reference) WHERE event_type='payment_confirmed'",
    "uq_billing_refund_reference": "CREATE UNIQUE INDEX uq_billing_refund_reference ON billing_events(provider,payment_reference) WHERE event_type='refund_confirmed'",
}


class BillingError(RuntimeError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _canonical_sql(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).removesuffix(";")


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode()).hexdigest()


def initialize_billing(db_path: Path = AUTH_DB_PATH) -> None:
    initialize_auth(db_path)
    with closing(connect(db_path)) as conn:
        conn.executescript(BILLING_SCHEMA)
        rows = conn.execute(
            "SELECT name,sql FROM sqlite_master WHERE type='trigger' AND name IN (?,?,?,?)",
            tuple(EXPECTED_TRIGGERS),
        ).fetchall()
        actual = {row["name"]: _canonical_sql(row["sql"] or "") for row in rows}
        expected = {name: _canonical_sql(sql) for name, sql in EXPECTED_TRIGGERS.items()}
        if actual != expected:
            raise BillingError("billing append-only guard is missing or altered")
        rows = conn.execute(
            "SELECT name,sql FROM sqlite_master WHERE type='index' AND name IN (?,?)",
            tuple(EXPECTED_INDEXES),
        ).fetchall()
        actual_indexes = {row["name"]: _canonical_sql(row["sql"] or "") for row in rows}
        expected_indexes = {name: _canonical_sql(sql) for name, sql in EXPECTED_INDEXES.items()}
        if actual_indexes != expected_indexes:
            raise BillingError("billing reference uniqueness guard is missing or altered")
        conn.commit()


def _owner(conn: sqlite3.Connection, owner_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT id,role,status FROM members WHERE id=?", (owner_id,)).fetchone()
    if not row or row["role"] != "owner" or row["status"] != "active":
        raise PermissionError("owner access required")
    return row


def _reference(value: Any, field: str) -> str:
    if not isinstance(value, str) or not REFERENCE_PATTERN.fullmatch(value.strip()):
        raise BillingError(f"{field} must contain 6-128 safe reference characters")
    return value.strip()


def _occurred_at(value: Any, *, enforce_window: bool = True) -> str:
    if not isinstance(value, str):
        raise BillingError("occurred_at must be an ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise BillingError("occurred_at must be an ISO timestamp") from exc
    if parsed.tzinfo is None:
        raise BillingError("occurred_at must include a timezone")
    utc = parsed.astimezone(timezone.utc)
    now = _now()
    if enforce_window and (utc > now + timedelta(minutes=5) or utc < now - timedelta(days=366)):
        raise BillingError("occurred_at is outside the paid-pilot window")
    return utc.isoformat()


def _money(payload: dict[str, Any]) -> tuple[int, str]:
    amount = payload.get("amount_minor")
    if type(amount) is not int:
        raise BillingError("amount_minor must be an integer")
    currency = str(payload.get("currency", "")).upper()
    if amount < 100 or amount > 100_000_000 or currency != "CNY":
        raise BillingError("manual pilot supports CNY 1.00-1,000,000.00 only")
    return amount, currency


def _context(portfolio_id: str, research_pack_hash: str) -> tuple[str, str]:
    if not isinstance(portfolio_id, str) or not portfolio_id.startswith("canonical_portfolio_"):
        raise BillingError("verified portfolio identity is required")
    if not isinstance(research_pack_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", research_pack_hash):
        raise BillingError("verified research-pack identity is required")
    return portfolio_id, research_pack_hash


def _public_event(row: sqlite3.Row | dict[str, Any], *, idempotent: bool = False) -> dict[str, Any]:
    value = dict(row)
    return {
        "id": value["id"],
        "member_id": value["member_id"],
        "member_email": value.get("member_email"),
        "event_type": value["event_type"],
        "provider": value["provider"],
        "provider_event_id": value["provider_event_id"],
        "payment_reference": value["payment_reference"],
        "original_event_id": value["original_event_id"],
        "amount_minor": value["amount_minor"],
        "currency": value["currency"],
        "test_mode": bool(value["test_mode"]),
        "portfolio_id": value["portfolio_id"],
        "research_pack_hash": value["research_pack_hash"],
        "occurred_at": value["occurred_at"],
        "event_hash": value["event_hash"],
        "created_at": value["created_at"],
        "idempotent": idempotent,
    }


def _active_payment(conn: sqlite3.Connection, member_id: str) -> sqlite3.Row | None:
    return conn.execute(
        """SELECT p.* FROM billing_events p
           WHERE p.member_id=? AND p.event_type='payment_confirmed'
             AND NOT EXISTS (
               SELECT 1 FROM billing_events r
               WHERE r.event_type='refund_confirmed' AND r.original_event_id=p.id
             )
           ORDER BY p.created_at DESC,p.id DESC LIMIT 1""",
        (member_id,),
    ).fetchone()


def billing_status(member_id: str, db_path: Path = AUTH_DB_PATH) -> dict[str, Any]:
    initialize_billing(db_path)
    with closing(connect(db_path)) as conn:
        member = conn.execute("SELECT id,status FROM members WHERE id=?", (member_id,)).fetchone()
        if not member:
            raise BillingError("member is unavailable")
        payment = _active_payment(conn, member_id)
        last = conn.execute(
            "SELECT * FROM billing_events WHERE member_id=? ORDER BY created_at DESC,id DESC LIMIT 1",
            (member_id,),
        ).fetchone()
    if member["status"] != "active":
        status = "suspended"
    elif payment:
        status = "active_paid_test" if payment["test_mode"] else "active_paid"
    elif last and last["event_type"] == "refund_confirmed":
        status = "refunded"
    else:
        status = "unpaid"
    return {
        "schema_version": BILLING_SCHEMA_VERSION,
        "status": status,
        "paid": bool(payment) and member["status"] == "active",
        "test_mode": bool(payment["test_mode"]) if payment else False,
        "payment_event_id": payment["id"] if payment else None,
        "paid_at": payment["occurred_at"] if payment else None,
        "amount_minor": payment["amount_minor"] if payment else None,
        "currency": payment["currency"] if payment else None,
        "truth_boundary": "manual_external_fulfillment_no_online_checkout",
    }


def effective_member(member: dict[str, Any] | None, db_path: Path = AUTH_DB_PATH) -> dict[str, Any] | None:
    if not member:
        return None
    value = dict(member)
    if value.get("role") == "owner":
        value["tier"] = "owner"
        value["entitlements"] = list(TIER_ENTITLEMENTS["owner"])
        value["billing"] = {"status": "owner", "paid": True, "test_mode": False}
        return value
    status = billing_status(value["id"], db_path)
    if status["paid"]:
        value["tier"] = "paid"
        value["entitlements"] = list(TIER_ENTITLEMENTS["paid"])
    else:
        base = "preview" if value.get("tier") == "preview" else "member"
        value["tier"] = base
        value["entitlements"] = list(TIER_ENTITLEMENTS[base])
    value["billing"] = status
    return value


def record_payment(
    owner_id: str,
    payload: dict[str, Any],
    portfolio_id: str,
    research_pack_hash: str,
    db_path: Path = AUTH_DB_PATH,
) -> dict[str, Any]:
    initialize_billing(db_path)
    provider = str(payload.get("provider", ""))
    if provider not in ALLOWED_PROVIDERS:
        raise BillingError("unsupported manual payment provider")
    provider_event_id = _reference(payload.get("provider_event_id"), "provider_event_id")
    payment_reference = _reference(payload.get("payment_reference"), "payment_reference")
    email = str(payload.get("member_email", "")).strip().lower()
    if "@" not in email or len(email) > 254:
        raise BillingError("valid member_email is required")
    amount, currency = _money(payload)
    occurred_at = _occurred_at(payload.get("occurred_at"), enforce_window=False)
    portfolio_id, research_pack_hash = _context(portfolio_id, research_pack_hash)
    test_mode = provider == "acceptance_test"
    created_at = _now().isoformat()
    with closing(connect(db_path)) as conn:
        conn.execute("BEGIN IMMEDIATE")
        _owner(conn, owner_id)
        member = conn.execute(
            "SELECT id,role,status FROM members WHERE email=?", (email,),
        ).fetchone()
        if not member:
            raise BillingError("active non-owner member is required")
        event_core = {
            "member_id": member["id"], "event_type": "payment_confirmed", "provider": provider,
            "provider_event_id": provider_event_id, "payment_reference": payment_reference,
            "original_event_id": None, "amount_minor": amount, "currency": currency,
            "test_mode": test_mode, "occurred_at": occurred_at, "recorded_by": owner_id,
        }
        existing = conn.execute(
            "SELECT * FROM billing_events WHERE provider=? AND provider_event_id=?",
            (provider, provider_event_id),
        ).fetchone()
        if existing:
            replay_payload = {
                **event_core,
                "portfolio_id": existing["portfolio_id"],
                "research_pack_hash": existing["research_pack_hash"],
            }
            if existing["event_hash"] != _digest(replay_payload):
                raise BillingError("provider event replay differs from the original payload")
            return _public_event(existing, idempotent=True)
        _occurred_at(occurred_at)
        if member["role"] == "owner" or member["status"] != "active":
            raise BillingError("active non-owner member is required")
        setting = conn.execute("SELECT accept_new_payments FROM billing_settings WHERE id=1").fetchone()
        if setting and not setting["accept_new_payments"]:
            raise BillingError("new payment confirmations are stopped")
        reused_reference = conn.execute(
            """SELECT id FROM billing_events
               WHERE provider=? AND payment_reference=? AND event_type='payment_confirmed'""",
            (provider, payment_reference),
        ).fetchone()
        if reused_reference:
            raise BillingError("payment reference is already recorded")
        if _active_payment(conn, member["id"]):
            raise BillingError("member already has an active paid entitlement")
        event_payload = {
            **event_core,
            "portfolio_id": portfolio_id,
            "research_pack_hash": research_pack_hash,
        }
        event_hash = _digest(event_payload)
        event_id = f"billing_{event_hash[:20]}"
        conn.execute(
            """INSERT INTO billing_events
               (id,member_id,event_type,provider,provider_event_id,payment_reference,original_event_id,
                amount_minor,currency,test_mode,portfolio_id,research_pack_hash,occurred_at,recorded_by,event_hash,created_at)
               VALUES (?,?,?,?,?,?,NULL,?,?,?,?,?,?,?,?,?)""",
            (
                event_id, member["id"], "payment_confirmed", provider, provider_event_id, payment_reference,
                amount, currency, int(test_mode), portfolio_id, research_pack_hash, occurred_at,
                owner_id, event_hash, created_at,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM billing_events WHERE id=?", (event_id,)).fetchone()
    return _public_event(row)


def record_refund(
    owner_id: str,
    payload: dict[str, Any],
    db_path: Path = AUTH_DB_PATH,
) -> dict[str, Any]:
    initialize_billing(db_path)
    provider = str(payload.get("provider", ""))
    if provider not in ALLOWED_PROVIDERS:
        raise BillingError("unsupported manual refund provider")
    provider_event_id = _reference(payload.get("provider_event_id"), "provider_event_id")
    refund_reference = _reference(payload.get("refund_reference"), "refund_reference")
    payment_event_id = _reference(payload.get("payment_event_id"), "payment_event_id")
    occurred_at = _occurred_at(payload.get("occurred_at"), enforce_window=False)
    created_at = _now().isoformat()
    with closing(connect(db_path)) as conn:
        conn.execute("BEGIN IMMEDIATE")
        _owner(conn, owner_id)
        payment = conn.execute(
            "SELECT * FROM billing_events WHERE id=? AND event_type='payment_confirmed'",
            (payment_event_id,),
        ).fetchone()
        if not payment or payment["provider"] != provider:
            raise BillingError("original payment event is unavailable or provider-mismatched")
        event_payload = {
            "member_id": payment["member_id"], "event_type": "refund_confirmed", "provider": provider,
            "provider_event_id": provider_event_id, "payment_reference": refund_reference,
            "original_event_id": payment_event_id, "amount_minor": payment["amount_minor"],
            "currency": payment["currency"], "test_mode": bool(payment["test_mode"]),
            "portfolio_id": payment["portfolio_id"], "research_pack_hash": payment["research_pack_hash"],
            "occurred_at": occurred_at, "recorded_by": owner_id,
        }
        event_hash = _digest(event_payload)
        existing = conn.execute(
            "SELECT * FROM billing_events WHERE provider=? AND provider_event_id=?",
            (provider, provider_event_id),
        ).fetchone()
        if existing:
            if existing["event_hash"] != event_hash:
                raise BillingError("provider event replay differs from the original payload")
            return _public_event(existing, idempotent=True)
        _occurred_at(occurred_at)
        if datetime.fromisoformat(occurred_at) < datetime.fromisoformat(payment["occurred_at"]):
            raise BillingError("refund occurred_at cannot precede the original payment")
        reused_reference = conn.execute(
            """SELECT id FROM billing_events
               WHERE provider=? AND payment_reference=? AND event_type='refund_confirmed'""",
            (provider, refund_reference),
        ).fetchone()
        if reused_reference:
            raise BillingError("refund reference is already recorded")
        prior_refund = conn.execute(
            "SELECT id FROM billing_events WHERE event_type='refund_confirmed' AND original_event_id=?",
            (payment_event_id,),
        ).fetchone()
        if prior_refund:
            raise BillingError("payment is already refunded")
        event_id = f"billing_{event_hash[:20]}"
        conn.execute(
            """INSERT INTO billing_events
               (id,member_id,event_type,provider,provider_event_id,payment_reference,original_event_id,
                amount_minor,currency,test_mode,portfolio_id,research_pack_hash,occurred_at,recorded_by,event_hash,created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                event_id, payment["member_id"], "refund_confirmed", provider, provider_event_id,
                refund_reference, payment_event_id, payment["amount_minor"], payment["currency"],
                payment["test_mode"], payment["portfolio_id"], payment["research_pack_hash"], occurred_at, owner_id,
                event_hash, created_at,
            ),
        )
        conn.execute(
            "UPDATE member_sessions SET revoked_at=? WHERE member_id=? AND revoked_at IS NULL",
            (created_at, payment["member_id"]),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM billing_events WHERE id=?", (event_id,)).fetchone()
    return _public_event(row)


def payment_controls(owner_id: str, db_path: Path = AUTH_DB_PATH) -> dict[str, Any]:
    initialize_billing(db_path)
    with closing(connect(db_path)) as conn:
        _owner(conn, owner_id)
        row = conn.execute("SELECT * FROM billing_settings WHERE id=1").fetchone()
    return {
        "accept_new_payments": True if row is None else bool(row["accept_new_payments"]),
        "updated_at": row["updated_at"] if row else None,
        "truth_boundary": "controls_manual_confirmations_only",
    }


def set_payment_controls(owner_id: str, enabled: bool, db_path: Path = AUTH_DB_PATH) -> dict[str, Any]:
    initialize_billing(db_path)
    if not isinstance(enabled, bool):
        raise BillingError("accept_new_payments must be boolean")
    created_at = _now().isoformat()
    event_payload = {
        "control_type": "accept_new_payments", "enabled": enabled,
        "recorded_by": owner_id, "created_at": created_at,
    }
    event_hash = _digest(event_payload)
    event_id = f"billing_control_{event_hash[:20]}"
    with closing(connect(db_path)) as conn:
        conn.execute("BEGIN IMMEDIATE")
        _owner(conn, owner_id)
        current = conn.execute("SELECT accept_new_payments FROM billing_settings WHERE id=1").fetchone()
        if current is not None and bool(current["accept_new_payments"]) == enabled:
            conn.rollback()
            return {**payment_controls(owner_id, db_path), "idempotent": True}
        conn.execute(
            "INSERT INTO billing_control_events (id,control_type,enabled,recorded_by,event_hash,created_at) VALUES (?,?,?,?,?,?)",
            (event_id, "accept_new_payments", int(enabled), owner_id, event_hash, created_at),
        )
        conn.execute(
            """INSERT INTO billing_settings (id,accept_new_payments,updated_at,updated_by)
               VALUES (1,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                 accept_new_payments=excluded.accept_new_payments,
                 updated_at=excluded.updated_at,
                 updated_by=excluded.updated_by""",
            (int(enabled), created_at, owner_id),
        )
        conn.commit()
    return {"accept_new_payments": enabled, "updated_at": created_at, "truth_boundary": "controls_manual_confirmations_only", "idempotent": False}


def billing_export(owner_id: str, db_path: Path = AUTH_DB_PATH) -> dict[str, Any]:
    initialize_billing(db_path)
    with closing(connect(db_path)) as conn:
        _owner(conn, owner_id)
        rows = conn.execute(
            """SELECT e.*,m.email AS member_email
               FROM billing_events e JOIN members m ON m.id=e.member_id
               ORDER BY e.created_at,e.id"""
        ).fetchall()
        controls = conn.execute(
            "SELECT id,control_type,enabled,event_hash,created_at FROM billing_control_events ORDER BY created_at,id"
        ).fetchall()
    events = [_public_event(row) for row in rows]
    real_revenue = sum(
        (1 if item["event_type"] == "payment_confirmed" else -1) * item["amount_minor"]
        for item in events if not item["test_mode"]
    )
    payload = {
        "schema_version": BILLING_SCHEMA_VERSION,
        "events": events,
        "control_events": [dict(row) for row in controls],
        "reconciliation": {
            "currency": "CNY",
            "realized_revenue_minor": real_revenue,
            "acceptance_test_event_count": sum(1 for item in events if item["test_mode"]),
            "real_event_count": sum(1 for item in events if not item["test_mode"]),
        },
        "truth_boundary": "manual_external_records_not_provider_webhooks",
    }
    payload["export_hash"] = _digest(payload)
    return payload
