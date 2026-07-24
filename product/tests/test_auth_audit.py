from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


PRODUCT = Path(__file__).resolve().parents[1]
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from auth_store import (  # noqa: E402
    _record,
    connect,
    create_invite,
    create_owner,
    list_audit_events,
    redeem_invite,
    set_member_access_role,
)


class AuthAuditTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "auth.db"
        self.owner = create_owner("owner@example.com", "owner-password-2026", "Owner", self.db)
        invite = create_invite(self.owner["id"], "member", self.db)
        self.member = redeem_invite(invite["code"], "member@example.com", "member-password-2026", "Member", self.db)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_owner_assigns_editor_without_role_escalation(self) -> None:
        editor = set_member_access_role(self.owner["id"], self.member["email"], "editor", self.db)
        self.assertEqual(editor["role"], "editor")
        with self.assertRaises(ValueError):
            set_member_access_role(self.owner["id"], self.member["email"], "owner", self.db)
        with self.assertRaises(PermissionError):
            set_member_access_role(self.member["id"], self.member["email"], "member", self.db)

    def test_audit_is_append_only_actor_scoped_and_redacts_secret_keys(self) -> None:
        with connect(self.db) as conn:
            _record(conn, self.owner["id"], "security_probe", {"password": "never-store", "token": "never-store", "safe": "kept"})
            conn.commit()
            event_id = conn.execute("SELECT MAX(id) FROM member_events").fetchone()[0]
            with self.assertRaises(sqlite3.DatabaseError):
                conn.execute("UPDATE member_events SET event_type='rewritten' WHERE id=?", (event_id,))
            with self.assertRaises(sqlite3.DatabaseError):
                conn.execute("DELETE FROM member_events WHERE id=?", (event_id,))
        events = list_audit_events(self.owner["id"], self.db)
        event = next(item for item in events if item["id"] == event_id)
        self.assertEqual(event["actor_member_id"], self.owner["id"])
        self.assertEqual(event["detail"], {"password": "[redacted]", "safe": "kept", "token": "[redacted]"})
        with self.assertRaises(PermissionError):
            list_audit_events(self.member["id"], self.db)


if __name__ == "__main__":
    unittest.main()
