from __future__ import annotations

import copy
from contextlib import closing
from datetime import datetime, timezone
import http.client
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch


PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT))

from data_store import (  # noqa: E402
    DEMO_POSITIONS,
    connect,
    create_snapshot_content_attestation,
    initialize,
)
from portfolio_allocation import (  # noqa: E402
    CanonicalPortfolioError,
    build_portfolio_version,
    digest,
    load_portfolio_history,
    load_portfolio_state,
    portfolio_diff,
    render_portfolio_html,
    validate_portfolio_version,
)
from portfolio_ledger import (  # noqa: E402
    PortfolioLedger,
    PortfolioLedgerError,
    build_ledger_history,
)


class CanonicalPortfolioV1Test(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.db_path = self.root / "source.db"
        initialize(self.db_path, force_seed=True)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def seed_snapshot(
        self,
        suffix: str,
        *,
        as_of: str,
        weights: tuple[float, ...] = (8, 10, 13, 12, 10, 9, 11, 9),
        created_at: str,
        attest: bool = True,
    ) -> str:
        manifest = (suffix * 64)[:64]
        snapshot_id = f"snap_real_{manifest[:12]}"
        publication_id = f"pub_real_{manifest[:12]}"
        known_at = f"{as_of}T15:00:00+08:00"
        with closing(connect(self.db_path)) as connection:
            connection.execute(
                "INSERT INTO dataset_snapshots VALUES (?, 'REAL', ?, ?, 'passed', ?, ?, ?)",
                (snapshot_id, as_of, known_at, "test REAL snapshot", manifest, created_at),
            )
            connection.execute(
                """INSERT INTO publications (
                   id,snapshot_id,status,title,market_regime,regime_note,equity_weight,
                   cash_weight,model_version
                   ) VALUES (?,?,'quality_passed',?,'均衡','质量与估值共同决定仓位',82,18,'long-horizon-test-v1')""",
                (publication_id, snapshot_id, f"{as_of} model portfolio"),
            )
            for index, (meta, weight) in enumerate(zip(DEMO_POSITIONS, weights, strict=True)):
                price = 100 + index * 10
                connection.execute(
                    """INSERT INTO portfolio_items VALUES (
                       ?,?,?,?,?,?,?,'持有',?,? ,?,'accepted',?,?,?,?,?,?,?
                       )""",
                    (
                        publication_id, meta["ticker"], meta["name"], meta["exchange"], meta["industry"],
                        weight, weight, price, f"¥{price-2:.2f}–¥{price+2:.2f}（分批观察）", 70 + index,
                        as_of, meta["thesis"], meta["primary_risk"], meta["valuation"],
                        meta["bull_case"], meta["base_case"], meta["bear_case"],
                    ),
                )
                connection.execute(
                    "INSERT INTO evidence VALUES (?,?,'fact','snapshot evidence',?,'test',?,'accepted')",
                    (publication_id, meta["ticker"], str(price), known_at),
                )
                connection.execute(
                    """INSERT INTO market_quotes VALUES (
                       ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'accepted')""",
                    (
                        snapshot_id, meta["ticker"], meta["name"], price, 0, price + 1, price - 1,
                        20 + index, 3 + index / 10, 10000, 9000, known_at, "test_quote",
                        "https://qt.gtimg.cn/", f"q{suffix}{index}".ljust(64, "0"), known_at,
                    ),
                )
                connection.execute(
                    """INSERT INTO financial_metrics VALUES (
                       ?,?,'2025-12-31','2026-03-31','年报',100,20,8,10,15,40,20,30,5,'test_fin',?,'accepted')""",
                    (snapshot_id, meta["ticker"], f"f{suffix}{index}".ljust(64, "0")),
                )
                connection.execute(
                    "INSERT INTO daily_bars VALUES (?,?,?,?,?,?,?,?,?,?, 'accepted')",
                    (
                        snapshot_id, meta["ticker"], as_of, price, price + 1, price + 2,
                        price - 1, 10000, "test_bar", f"b{suffix}{index}".ljust(64, "0"),
                    ),
                )
                connection.execute(
                    """INSERT INTO stock_features VALUES (
                       ?,?,1,2,3,10,-5,100,99,98,10,70,75,65,70,72,100,'test-feature-v1')""",
                    (snapshot_id, meta["ticker"]),
                )
            for rank, title in enumerate(("估值风险", "波动风险", "版本风险"), 1):
                connection.execute(
                    "INSERT INTO portfolio_risks VALUES (?,?,?,?,?)",
                    (publication_id, rank, title, f"{title}需要持续验证", "medium"),
                )
            if attest:
                create_snapshot_content_attestation(connection, snapshot_id, created_at=created_at)
            connection.commit()
        return snapshot_id

    def two_versions(self) -> tuple[dict, dict]:
        first_id = self.seed_snapshot(
            "a", as_of="2026-07-17", created_at="2026-07-17T09:00:00+00:00",
        )
        second_id = self.seed_snapshot(
            "b", as_of="2026-07-21", weights=(9, 10, 13, 12, 10, 9, 11, 8),
            created_at="2026-07-21T09:00:00+00:00",
        )
        first = build_portfolio_version(first_id, self.db_path)
        second = build_portfolio_version(second_id, self.db_path, previous=first)
        return first, second

    def test_builds_eight_stock_real_portfolio_with_hard_constraints(self) -> None:
        _, current = self.two_versions()
        self.assertEqual(validate_portfolio_version(current), [])
        self.assertEqual(len(current["positions"]), 8)
        self.assertEqual(current["allocation"], {"equity_weight": 82.0, "cash_weight": 18.0, "total": 100.0})
        self.assertTrue(all(5 <= item["target_weight"] <= 15 for item in current["positions"]))
        self.assertTrue(all(item["weight_semantics"] == "model_suggested_non_executable" for item in current["positions"]))
        self.assertEqual(current["portfolio_role"], "canonical_current")
        self.assertTrue(all(item["drifted_weight"] is not None for item in current["positions"]))

    def test_every_position_binds_same_snapshot_report_identity(self) -> None:
        _, current = self.two_versions()
        for item in current["positions"]:
            binding = item["report_binding"]
            self.assertEqual(binding["snapshot_id"], current["snapshot"]["snapshot_id"])
            self.assertRegex(binding["report_hash"], r"^[0-9a-f]{64}$")
            self.assertEqual(binding["evidence_status"], "verified")
            self.assertEqual(binding["model_version"], current["model_version"])
            self.assertEqual(binding["allocation_config_version"], current["allocation_config_version"])
            self.assertRegex(binding["evidence_identity"], r"^[0-9a-f]{64}$")

    def test_same_snapshot_replay_has_same_portfolio_identity(self) -> None:
        snapshot_id = self.seed_snapshot(
            "c", as_of="2026-07-21", created_at="2026-07-21T09:00:00+00:00",
        )
        first = build_portfolio_version(snapshot_id, self.db_path)
        second = build_portfolio_version(snapshot_id, self.db_path)
        self.assertEqual(first, second)

    def test_weight_or_report_tamper_fails_closed(self) -> None:
        _, current = self.two_versions()
        changed = copy.deepcopy(current)
        changed["positions"][0]["target_weight"] = 30
        self.assertTrue(any("single-stock" in item or "total" in item for item in validate_portfolio_version(changed)))
        changed = copy.deepcopy(current)
        changed["positions"][0]["report_binding"]["snapshot_id"] = "wrong"
        self.assertTrue(any("report snapshot mismatch" in item for item in validate_portfolio_version(changed)))
        changed = copy.deepcopy(current)
        changed["positions"][0]["report_binding"].update({
            "is_live_research": False, "research_status": "blocked",
            "research_depth": "fixture", "contract_version": "forged",
        })
        clean = {key: value for key, value in changed.items() if key not in {"portfolio_id", "payload_hash"}}
        changed["payload_hash"] = digest(clean)
        changed["portfolio_id"] = f"canonical_portfolio_{changed['payload_hash'][:16]}"
        self.assertTrue(any("research" in item or "contract" in item for item in validate_portfolio_version(changed)))

    def test_retrospective_snapshot_is_explicit_not_immutable_attestation(self) -> None:
        snapshot_id = self.seed_snapshot(
            "d", as_of="2026-07-17", created_at="2026-07-17T09:00:00+00:00", attest=False,
        )
        version = build_portfolio_version(snapshot_id, self.db_path)
        self.assertEqual(version["snapshot"]["attestation_status"], "retrospective_hash_only")
        self.assertEqual(version["portfolio_role"], "retrospective_reference_only")
        self.assertEqual(version["publication_state"], "retrospective_replay_not_publishable")

    def test_period_diff_is_deterministic_and_readable(self) -> None:
        first, second = self.two_versions()
        change = portfolio_diff(first, second)
        self.assertEqual({item["ticker"] for item in change["changes"]}, {"600519.SH", "688036.SH"})
        self.assertEqual(digest({key: value for key, value in change.items() if key != "diff_hash"}), change["diff_hash"])

    def test_ledger_versions_and_orders_are_append_only(self) -> None:
        first, _ = self.two_versions()
        ledger = PortfolioLedger(self.root / "ledger.db")
        order_ids = ledger.stage_orders(first)
        self.assertEqual(len(order_ids), 8)
        self.assertEqual(ledger.stage_orders(first), order_ids)
        with closing(ledger.connect()) as connection:
            with self.assertRaisesRegex(sqlite3.DatabaseError, "append-only"):
                connection.execute("UPDATE model_portfolio_versions SET payload_hash='forged'")

    def test_ledger_requires_pending_before_filled_or_unfilled(self) -> None:
        first, second = self.two_versions()
        ledger = PortfolioLedger(self.root / "ledger.db")
        order_id = ledger.stage_orders(first)[0]
        with self.assertRaisesRegex(PortfolioLedgerError, "invalid order transition"):
            ledger.append_event(
                order_id, "filled", event_at="2026-07-20T01:30:00+00:00",
                effective_trade_date="2026-07-20", fill_price=100,
                source_snapshot_id="source", source_row_hash="a" * 64, reason="invalid direct fill",
            )
        ledger.append_event(order_id, "pending", event_at=first["generated_at"], reason="wait")
        with self.assertRaisesRegex(PortfolioLedgerError, "source snapshot|source bar"):
            ledger.append_event(
                order_id, "filled", event_at="2099-01-01T01:30:00+00:00",
                effective_trade_date="2099-01-01", fill_price=999999,
                source_snapshot_id="fake", source_row_hash="a" * 64,
                source_db_path=self.db_path, reason="forged future fill",
            )
        with closing(connect(self.db_path)) as connection:
            order_ticker = next(
                item["ticker"] for item in ledger.payload(first["portfolio_id"])["orders"]
                if item["order_id"] == order_id
            )
            bar = connection.execute(
                "SELECT * FROM daily_bars WHERE snapshot_id=? AND ticker=?",
                (second["snapshot"]["snapshot_id"], order_ticker),
            ).fetchone()
        ledger.append_event(
            order_id, "filled", event_at="2026-07-21T01:30:00+00:00",
            effective_trade_date=bar["trade_date"], fill_price=bar["open"],
            source_snapshot_id=bar["snapshot_id"], source_row_hash=bar["raw_hash"],
            source_db_path=self.db_path, reason="next open",
        )
        row = next(item for item in ledger.payload(first["portfolio_id"])["orders"] if item["order_id"] == order_id)
        self.assertEqual(row["status"], "filled")

    def test_unfilled_path_never_invents_a_fill_price(self) -> None:
        first, _ = self.two_versions()
        ledger = PortfolioLedger(self.root / "ledger.db")
        order_id = ledger.stage_orders(first)[0]
        ledger.append_event(order_id, "pending", event_at=first["generated_at"], reason="suspended")
        ledger.append_event(
            order_id, "unfilled", event_at="2026-07-27T01:30:00+00:00",
            reason="five trading days without an executable opening price",
        )
        row = next(item for item in ledger.payload(first["portfolio_id"])["orders"] if item["order_id"] == order_id)
        self.assertEqual(row["status"], "unfilled")
        self.assertIsNone(row["fill_price"])

    def test_ledger_rejects_replaced_append_only_guard(self) -> None:
        first, _ = self.two_versions()
        ledger = PortfolioLedger(self.root / "ledger.db")
        ledger.stage_orders(first)
        with closing(ledger.connect()) as connection:
            connection.execute("DROP TRIGGER model_portfolio_orders_no_update")
            connection.execute(
                "CREATE TRIGGER model_portfolio_orders_no_update BEFORE UPDATE ON model_portfolio_orders BEGIN SELECT 1; END"
            )
            connection.commit()
        with self.assertRaisesRegex(PortfolioLedgerError, "guard"):
            ledger.payload(first["portfolio_id"])

    def test_state_pointer_and_history_reject_tampering(self) -> None:
        first, second = self.two_versions()
        state = self.root / "state"
        (state / "versions").mkdir(parents=True)
        for item in (first, second):
            (state / "versions" / f"{item['portfolio_id']}.json").write_text(
                json.dumps(item, ensure_ascii=False), encoding="utf-8",
            )
        pointer = {
            "portfolio_id": second["portfolio_id"], "payload_hash": second["payload_hash"],
            "snapshot_id": second["snapshot"]["snapshot_id"],
        }
        pointer["pointer_hash"] = digest(pointer)
        (state / "current.json").write_text(json.dumps(pointer), encoding="utf-8")
        self.assertEqual(load_portfolio_state(state)["portfolio_id"], second["portfolio_id"])
        self.assertEqual(len(load_portfolio_history(state)), 2)
        rollback = {
            "portfolio_id": first["portfolio_id"], "payload_hash": first["payload_hash"],
            "snapshot_id": first["snapshot"]["snapshot_id"],
        }
        rollback["pointer_hash"] = digest(rollback)
        (state / "current.json").write_text(json.dumps(rollback), encoding="utf-8")
        with self.assertRaisesRegex(CanonicalPortfolioError, "not the latest"):
            load_portfolio_state(state)
        (state / "current.json").write_text(json.dumps(pointer), encoding="utf-8")
        bad_history = state / "versions" / "canonical_portfolio_bad.json"
        bad_history.write_text("{broken", encoding="utf-8")
        with self.assertRaisesRegex(CanonicalPortfolioError, "unreadable"):
            load_portfolio_history(state)
        bad_history.unlink()
        pointer["payload_hash"] = "0" * 64
        (state / "current.json").write_text(json.dumps(pointer), encoding="utf-8")
        with self.assertRaisesRegex(CanonicalPortfolioError, "pointer/version mismatch"):
            load_portfolio_state(state)

    def test_html_exposes_names_weights_actions_and_boundary(self) -> None:
        first, second = self.two_versions()
        change = portfolio_diff(first, second)
        ledger = PortfolioLedger(self.root / "ledger.db")
        ledger.stage_orders(second)
        html = render_portfolio_html(second, [first, second], change, ledger.payload(second["portfolio_id"]))
        for item in second["positions"]:
            self.assertIn(item["ticker"], html)
            self.assertIn(item["name"], html)
            self.assertIn(f"{item['target_weight']:.0f}%", html)
        self.assertIn("No broker connection", html)

    def test_http_api_serves_verified_current_history_and_ledger(self) -> None:
        first, second = self.two_versions()
        state = self.root / "state"
        (state / "versions").mkdir(parents=True)
        for item in (first, second):
            (state / "versions" / f"{item['portfolio_id']}.json").write_text(
                json.dumps(item, ensure_ascii=False), encoding="utf-8",
            )
        pointer = {
            "portfolio_id": second["portfolio_id"], "payload_hash": second["payload_hash"],
            "snapshot_id": second["snapshot"]["snapshot_id"],
        }
        pointer["pointer_hash"] = digest(pointer)
        (state / "current.json").write_text(json.dumps(pointer), encoding="utf-8")
        ledger = PortfolioLedger(self.root / "ledger.db")
        ledger.stage_orders(first)
        ledger.stage_orders(second)
        ledger_payload = ledger.payload(second["portfolio_id"])
        (state / "latest-ledger.json").write_text(json.dumps(ledger_payload), encoding="utf-8")
        ledger_history = build_ledger_history([
            ledger.payload(first["portfolio_id"]), ledger_payload,
        ])
        (state / "ledger-history.json").write_text(json.dumps(ledger_history), encoding="utf-8")

        from server import DashboardHandler  # noqa: E402
        from http.server import ThreadingHTTPServer

        with patch.dict(os.environ, {"PARK_CANONICAL_PORTFOLIO_ROOT": str(state)}):
            server = ThreadingHTTPServer(("127.0.0.1", 0), DashboardHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                for route in (
                    "/api/canonical/portfolio",
                    "/api/canonical/portfolio/history",
                    "/api/canonical/portfolio/ledger",
                    "/api/canonical/portfolio/ledger/history",
                ):
                    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
                    connection.request("GET", route)
                    response = connection.getresponse()
                    payload = json.loads(response.read())
                    connection.close()
                    self.assertEqual(response.status, 200, payload)
                self.assertEqual(load_portfolio_state(state)["portfolio_id"], second["portfolio_id"])
                forged_ledger = {
                    "schema_version": "model-portfolio-ledger-v1",
                    "portfolio_id": second["portfolio_id"], "orders": [],
                }
                forged_ledger["ledger_hash"] = digest(forged_ledger)
                (state / "latest-ledger.json").write_text(json.dumps(forged_ledger), encoding="utf-8")
                connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
                connection.request("GET", "/api/canonical/portfolio/ledger")
                response = connection.getresponse()
                payload = json.loads(response.read())
                connection.close()
                self.assertEqual((response.status, payload["error"]), (409, "canonical_portfolio_ledger_unavailable"))
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
