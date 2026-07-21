from __future__ import annotations

from contextlib import closing
from datetime import date, datetime, timezone
import json
import math
from pathlib import Path
import re
import sqlite3
from typing import Any

from data_store import connect as connect_source, verify_snapshot_content_attestation
from portfolio_allocation import canonical_json, digest, validate_portfolio_version


LEDGER_SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS model_portfolio_versions (
    portfolio_id TEXT PRIMARY KEY,
    snapshot_id TEXT NOT NULL,
    previous_portfolio_id TEXT,
    payload_hash TEXT NOT NULL,
    manifest_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS model_portfolio_orders (
    order_id TEXT PRIMARY KEY,
    portfolio_id TEXT NOT NULL REFERENCES model_portfolio_versions(portfolio_id),
    ticker TEXT NOT NULL,
    name TEXT NOT NULL,
    previous_target_weight REAL NOT NULL,
    drifted_weight REAL NOT NULL,
    target_weight REAL NOT NULL,
    planned_change REAL NOT NULL,
    scheduled_after TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS model_portfolio_order_events (
    event_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL REFERENCES model_portfolio_orders(order_id),
    status TEXT NOT NULL CHECK(status IN ('pending','filled','unfilled')),
    event_at TEXT NOT NULL,
    effective_trade_date TEXT,
    fill_price REAL,
    source_snapshot_id TEXT,
    source_row_hash TEXT,
    reason TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS model_portfolio_versions_no_update BEFORE UPDATE ON model_portfolio_versions BEGIN SELECT RAISE(ABORT, 'model portfolio versions are append-only'); END;
CREATE TRIGGER IF NOT EXISTS model_portfolio_versions_no_delete BEFORE DELETE ON model_portfolio_versions BEGIN SELECT RAISE(ABORT, 'model portfolio versions are append-only'); END;
CREATE TRIGGER IF NOT EXISTS model_portfolio_orders_no_update BEFORE UPDATE ON model_portfolio_orders BEGIN SELECT RAISE(ABORT, 'model portfolio orders are append-only'); END;
CREATE TRIGGER IF NOT EXISTS model_portfolio_orders_no_delete BEFORE DELETE ON model_portfolio_orders BEGIN SELECT RAISE(ABORT, 'model portfolio orders are append-only'); END;
CREATE TRIGGER IF NOT EXISTS model_portfolio_order_events_no_update BEFORE UPDATE ON model_portfolio_order_events BEGIN SELECT RAISE(ABORT, 'model portfolio order events are append-only'); END;
CREATE TRIGGER IF NOT EXISTS model_portfolio_order_events_no_delete BEFORE DELETE ON model_portfolio_order_events BEGIN SELECT RAISE(ABORT, 'model portfolio order events are append-only'); END;
"""

LEDGER_TRIGGER_SQL = {
    "model_portfolio_versions_no_update": "CREATE TRIGGER model_portfolio_versions_no_update BEFORE UPDATE ON model_portfolio_versions BEGIN SELECT RAISE(ABORT, 'model portfolio versions are append-only'); END",
    "model_portfolio_versions_no_delete": "CREATE TRIGGER model_portfolio_versions_no_delete BEFORE DELETE ON model_portfolio_versions BEGIN SELECT RAISE(ABORT, 'model portfolio versions are append-only'); END",
    "model_portfolio_orders_no_update": "CREATE TRIGGER model_portfolio_orders_no_update BEFORE UPDATE ON model_portfolio_orders BEGIN SELECT RAISE(ABORT, 'model portfolio orders are append-only'); END",
    "model_portfolio_orders_no_delete": "CREATE TRIGGER model_portfolio_orders_no_delete BEFORE DELETE ON model_portfolio_orders BEGIN SELECT RAISE(ABORT, 'model portfolio orders are append-only'); END",
    "model_portfolio_order_events_no_update": "CREATE TRIGGER model_portfolio_order_events_no_update BEFORE UPDATE ON model_portfolio_order_events BEGIN SELECT RAISE(ABORT, 'model portfolio order events are append-only'); END",
    "model_portfolio_order_events_no_delete": "CREATE TRIGGER model_portfolio_order_events_no_delete BEFORE DELETE ON model_portfolio_order_events BEGIN SELECT RAISE(ABORT, 'model portfolio order events are append-only'); END",
}


class PortfolioLedgerError(RuntimeError):
    pass


class PortfolioLedger:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect(verify_guards=False)) as connection:
            connection.executescript(LEDGER_SCHEMA)
            self._verify_guards(connection)

    @staticmethod
    def _verify_guards(connection: sqlite3.Connection) -> None:
        normalize = lambda value: " ".join(value.replace("IF NOT EXISTS ", "").strip().rstrip(";").split())
        placeholders = ",".join("?" for _ in LEDGER_TRIGGER_SQL)
        rows = connection.execute(
            f"SELECT name,sql FROM sqlite_master WHERE type='trigger' AND name IN ({placeholders})",
            tuple(LEDGER_TRIGGER_SQL),
        ).fetchall()
        actual = {row["name"]: normalize(str(row["sql"] or "")) for row in rows}
        expected = {name: normalize(sql) for name, sql in LEDGER_TRIGGER_SQL.items()}
        if actual != expected:
            raise PortfolioLedgerError("model ledger append-only guard is missing or modified")

    def connect(self, *, verify_guards: bool = True) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        if verify_guards:
            try:
                self._verify_guards(connection)
            except Exception:
                connection.close()
                raise
        return connection

    def append_version(self, portfolio: dict[str, Any]) -> str:
        errors = validate_portfolio_version(portfolio)
        if errors:
            raise PortfolioLedgerError("invalid portfolio version: " + "; ".join(errors))
        portfolio_id = portfolio["portfolio_id"]
        manifest = canonical_json(portfolio)
        with closing(self.connect()) as connection:
            existing = connection.execute(
                "SELECT payload_hash,manifest_json FROM model_portfolio_versions WHERE portfolio_id=?",
                (portfolio_id,),
            ).fetchone()
            if existing:
                if existing["payload_hash"] != portfolio["payload_hash"] or existing["manifest_json"] != manifest:
                    raise PortfolioLedgerError("portfolio identity collision")
                return portfolio_id
            connection.execute(
                "INSERT INTO model_portfolio_versions VALUES (?,?,?,?,?,?)",
                (
                    portfolio_id,
                    portfolio["snapshot"]["snapshot_id"],
                    portfolio.get("previous_portfolio_id"),
                    portfolio["payload_hash"],
                    manifest,
                    portfolio["generated_at"],
                ),
            )
            connection.commit()
        return portfolio_id

    def stage_orders(self, portfolio: dict[str, Any]) -> list[str]:
        self.append_version(portfolio)
        order_ids = []
        with closing(self.connect()) as connection:
            for item in portfolio["positions"]:
                previous_target = float(item.get("previous_target_weight") or 0)
                drifted = float(item.get("drifted_weight") or 0)
                target = float(item["target_weight"])
                if drifted == target:
                    continue
                base = {
                    "portfolio_id": portfolio["portfolio_id"],
                    "ticker": item["ticker"],
                    "previous_target_weight": previous_target,
                    "drifted_weight": drifted,
                    "target_weight": target,
                }
                order_id = f"model_order_{digest(base)[:18]}"
                order_ids.append(order_id)
                existing = connection.execute(
                    "SELECT * FROM model_portfolio_orders WHERE order_id=?", (order_id,),
                ).fetchone()
                if not existing:
                    connection.execute(
                        "INSERT INTO model_portfolio_orders VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (
                            order_id, portfolio["portfolio_id"], item["ticker"], item["name"],
                            previous_target, drifted, target, round(target - drifted, 4),
                            portfolio["snapshot"]["as_of"], portfolio["generated_at"],
                        ),
                    )
            connection.commit()
        return order_ids

    def append_event(
        self,
        order_id: str,
        status: str,
        *,
        event_at: str,
        effective_trade_date: str | None = None,
        fill_price: float | None = None,
        source_snapshot_id: str | None = None,
        source_row_hash: str | None = None,
        source_db_path: Path | None = None,
        reason: str,
    ) -> str:
        if status not in {"pending", "filled", "unfilled"}:
            raise PortfolioLedgerError("invalid order event status")
        if not isinstance(reason, str) or not reason.strip():
            raise PortfolioLedgerError("order event reason is required")
        try:
            event_instant = datetime.fromisoformat(event_at.replace("Z", "+00:00"))
        except (AttributeError, ValueError) as exc:
            raise PortfolioLedgerError("order event time must be ISO-8601") from exc
        if event_instant.tzinfo is None:
            raise PortfolioLedgerError("order event time must include a timezone")
        with closing(self.connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            order = connection.execute(
                "SELECT ticker,scheduled_after FROM model_portfolio_orders WHERE order_id=?", (order_id,),
            ).fetchone()
            if not order:
                raise PortfolioLedgerError("unknown model order")
            prior = connection.execute(
                "SELECT status FROM model_portfolio_order_events WHERE order_id=? ORDER BY rowid DESC LIMIT 1",
                (order_id,),
            ).fetchone()
            previous = prior["status"] if prior else None
            if (previous, status) not in {(None, "pending"), ("pending", "filled"), ("pending", "unfilled")}:
                raise PortfolioLedgerError(f"invalid order transition: {previous} -> {status}")
            execution_values = (effective_trade_date, fill_price, source_snapshot_id, source_row_hash)
            if status == "filled":
                try:
                    parsed_fill_price = float(fill_price)
                except (TypeError, ValueError) as exc:
                    raise PortfolioLedgerError("filled event price must be numeric") from exc
                if (
                    not effective_trade_date or parsed_fill_price <= 0
                    or not math.isfinite(parsed_fill_price)
                    or not source_snapshot_id or not isinstance(source_row_hash, str)
                    or not re.fullmatch(r"[0-9a-f]{64}", source_row_hash)
                ):
                    raise PortfolioLedgerError("filled event requires trade date, positive price, source snapshot and row hash")
                try:
                    effective_day = date.fromisoformat(effective_trade_date)
                    scheduled_day = date.fromisoformat(order["scheduled_after"])
                except ValueError as exc:
                    raise PortfolioLedgerError("filled event trade date must be ISO date") from exc
                if effective_day <= scheduled_day:
                    raise PortfolioLedgerError("filled event must use a trade date after the source portfolio date")
                if source_db_path is None:
                    raise PortfolioLedgerError("filled event requires an authoritative source database")
                try:
                    with closing(connect_source(Path(source_db_path))) as source:
                        bar = source.execute(
                            """SELECT b.snapshot_id,b.trade_date,b.open,b.raw_hash,
                                      s.data_mode,s.quality_status
                               FROM daily_bars b JOIN dataset_snapshots s ON s.id=b.snapshot_id
                               WHERE b.ticker=? AND b.trade_date>? AND b.quality_status='accepted'
                                 AND s.data_mode='REAL' AND s.quality_status='passed'
                               ORDER BY b.trade_date ASC,s.created_at DESC LIMIT 1""",
                            (order["ticker"], order["scheduled_after"]),
                        ).fetchone()
                        if bar:
                            verify_snapshot_content_attestation(source, bar["snapshot_id"])
                except (OSError, sqlite3.DatabaseError, RuntimeError, ValueError) as exc:
                    raise PortfolioLedgerError("filled event source snapshot is not immutable and verified") from exc
                if (
                    not bar or bar["snapshot_id"] != source_snapshot_id
                    or bar["trade_date"] != effective_trade_date
                    or bar["data_mode"] != "REAL" or bar["quality_status"] != "passed"
                    or abs(float(bar["open"]) - parsed_fill_price) > 1e-9
                    or bar["raw_hash"] != source_row_hash
                ):
                    raise PortfolioLedgerError("filled event source bar does not match authoritative REAL data")
            elif any(value is not None for value in execution_values):
                raise PortfolioLedgerError(f"{status} event cannot contain execution evidence")
            event = {
                "order_id": order_id,
                "status": status,
                "event_at": event_at,
                "effective_trade_date": effective_trade_date,
                "fill_price": fill_price,
                "source_snapshot_id": source_snapshot_id,
                "source_row_hash": source_row_hash,
                "reason": reason,
            }
            event_id = f"model_event_{digest(event)[:18]}"
            connection.execute(
                "INSERT INTO model_portfolio_order_events VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    event_id, order_id, status, event_at, effective_trade_date, fill_price,
                    source_snapshot_id, source_row_hash, reason,
                ),
            )
            connection.commit()
        return event_id

    def payload(self, portfolio_id: str | None = None) -> dict[str, Any]:
        with closing(self.connect()) as connection:
            if portfolio_id is None:
                row = connection.execute(
                    "SELECT portfolio_id FROM model_portfolio_versions ORDER BY created_at DESC, portfolio_id DESC LIMIT 1"
                ).fetchone()
                if not row:
                    return {"schema_version": "model-portfolio-ledger-v1", "portfolio_id": None, "orders": []}
                portfolio_id = row["portfolio_id"]
            rows = connection.execute(
                """SELECT o.*, e.status, e.event_at, e.effective_trade_date, e.fill_price,
                          e.source_snapshot_id, e.source_row_hash, e.reason
                   FROM model_portfolio_orders o
                   LEFT JOIN model_portfolio_order_events e ON e.rowid=(
                       SELECT MAX(e2.rowid) FROM model_portfolio_order_events e2 WHERE e2.order_id=o.order_id
                   ) WHERE o.portfolio_id=? ORDER BY o.ticker""",
                (portfolio_id,),
            ).fetchall()
        orders = []
        for source in rows:
            row = dict(source)
            row["status"] = row.get("status") or "planned"
            row["weight_drift"] = row["planned_change"]
            orders.append(row)
        payload = {
            "schema_version": "model-portfolio-ledger-v1",
            "portfolio_id": portfolio_id,
            "orders": orders,
        }
        payload["ledger_hash"] = digest(payload)
        return payload


def verify_ledger_payload(payload: dict[str, Any], *, expected_portfolio_id: str | None = None) -> None:
    if not isinstance(payload, dict) or payload.get("schema_version") != "model-portfolio-ledger-v1":
        raise PortfolioLedgerError("model ledger schema mismatch")
    declared_hash = payload.get("ledger_hash")
    clean = dict(payload)
    clean.pop("ledger_hash", None)
    if declared_hash != digest(clean):
        raise PortfolioLedgerError("model ledger payload hash mismatch")
    if expected_portfolio_id is not None and payload.get("portfolio_id") != expected_portfolio_id:
        raise PortfolioLedgerError("model ledger does not match current portfolio")
    orders = payload.get("orders")
    if not isinstance(orders, list):
        raise PortfolioLedgerError("model ledger orders are invalid")
    seen: set[str] = set()
    for item in orders:
        if not isinstance(item, dict) or not isinstance(item.get("order_id"), str):
            raise PortfolioLedgerError("model ledger order identity is invalid")
        if item["order_id"] in seen:
            raise PortfolioLedgerError("model ledger contains duplicate orders")
        seen.add(item["order_id"])
        status = item.get("status")
        if status not in {"planned", "pending", "filled", "unfilled"}:
            raise PortfolioLedgerError("model ledger order status is invalid")
        try:
            target = float(item.get("target_weight"))
            drifted = float(item.get("drifted_weight"))
            weight_drift = float(item.get("weight_drift"))
        except (TypeError, ValueError) as exc:
            raise PortfolioLedgerError("model ledger weights must be numeric") from exc
        if not all(math.isfinite(value) for value in (target, drifted, weight_drift)):
            raise PortfolioLedgerError("model ledger weights must be finite")
        if round(target - drifted, 4) != weight_drift:
            raise PortfolioLedgerError("model ledger weight drift does not reconcile")
        execution_values = tuple(item.get(key) for key in (
            "effective_trade_date", "fill_price", "source_snapshot_id", "source_row_hash",
        ))
        if status == "filled":
            try:
                fill = float(execution_values[1])
            except (TypeError, ValueError) as exc:
                raise PortfolioLedgerError("filled model ledger price is invalid") from exc
            if (
                not execution_values[0] or not math.isfinite(fill) or fill <= 0
                or not execution_values[2] or not isinstance(execution_values[3], str)
                or not re.fullmatch(r"[0-9a-f]{64}", execution_values[3])
            ):
                raise PortfolioLedgerError("filled model ledger order lacks execution evidence")
        elif any(value is not None for value in execution_values):
            raise PortfolioLedgerError("unexecuted model ledger order contains execution evidence")


def verify_ledger_matches_portfolio(payload: dict[str, Any], portfolio: dict[str, Any]) -> None:
    verify_ledger_payload(payload, expected_portfolio_id=portfolio.get("portfolio_id"))
    expected = {
        item["ticker"]: item for item in portfolio.get("positions", [])
        if float(item.get("drifted_weight") or 0) != float(item["target_weight"])
    }
    actual = {item["ticker"]: item for item in payload["orders"]}
    if len(actual) != len(payload["orders"]) or set(actual) != set(expected):
        raise PortfolioLedgerError("model ledger orders do not match portfolio drift-to-target changes")
    for ticker, position in expected.items():
        order = actual[ticker]
        previous_target = float(position.get("previous_target_weight") or 0)
        drifted = float(position.get("drifted_weight") or 0)
        target = float(position["target_weight"])
        identity = {
            "portfolio_id": portfolio["portfolio_id"],
            "ticker": ticker,
            "previous_target_weight": previous_target,
            "drifted_weight": drifted,
            "target_weight": target,
        }
        expected_order_id = f"model_order_{digest(identity)[:18]}"
        numeric_pairs = (
            (order.get("previous_target_weight"), previous_target),
            (order.get("drifted_weight"), drifted),
            (order.get("target_weight"), target),
            (order.get("planned_change"), round(target - drifted, 4)),
            (order.get("weight_drift"), round(target - drifted, 4)),
        )
        try:
            numeric_match = all(abs(float(actual_value) - expected_value) <= 1e-6 for actual_value, expected_value in numeric_pairs)
        except (TypeError, ValueError):
            numeric_match = False
        if (
            order.get("order_id") != expected_order_id
            or order.get("name") != position.get("name")
            or order.get("scheduled_after") != portfolio["snapshot"]["as_of"]
            or not numeric_match
        ):
            raise PortfolioLedgerError(f"model ledger order does not reconcile: {ticker}")


def build_ledger_history(versions: list[dict[str, Any]]) -> dict[str, Any]:
    if len(versions) < 2:
        raise PortfolioLedgerError("model ledger history requires at least two versions")
    for item in versions:
        verify_ledger_payload(item)
    payload = {
        "schema_version": "model-portfolio-ledger-history-v1",
        "current_portfolio_id": versions[-1]["portfolio_id"],
        "versions": versions,
        "status_counts": {
            status: sum(
                order.get("status") == status
                for version in versions for order in version["orders"]
            )
            for status in ("planned", "pending", "filled", "unfilled")
        },
    }
    payload["ledger_history_hash"] = digest(payload)
    return payload


def verify_ledger_history(payload: dict[str, Any], *, expected_current_portfolio_id: str | None = None) -> None:
    if not isinstance(payload, dict) or payload.get("schema_version") != "model-portfolio-ledger-history-v1":
        raise PortfolioLedgerError("model ledger history schema mismatch")
    clean = dict(payload)
    declared_hash = clean.pop("ledger_history_hash", None)
    if declared_hash != digest(clean):
        raise PortfolioLedgerError("model ledger history hash mismatch")
    versions = payload.get("versions")
    if not isinstance(versions, list) or len(versions) < 2:
        raise PortfolioLedgerError("model ledger history requires at least two versions")
    for item in versions:
        verify_ledger_payload(item)
    current = versions[-1].get("portfolio_id")
    if payload.get("current_portfolio_id") != current:
        raise PortfolioLedgerError("model ledger history current identity mismatch")
    if expected_current_portfolio_id is not None and current != expected_current_portfolio_id:
        raise PortfolioLedgerError("model ledger history does not match current portfolio")
    calculated_counts = {
        status: sum(
            order.get("status") == status
            for version in versions for order in version["orders"]
        )
        for status in ("planned", "pending", "filled", "unfilled")
    }
    if payload.get("status_counts") != calculated_counts:
        raise PortfolioLedgerError("model ledger history status counts do not reconcile")


def verify_ledger_fills_against_source(payload: dict[str, Any], source_db_path: Path) -> None:
    versions = payload.get("versions") if payload.get("schema_version") == "model-portfolio-ledger-history-v1" else [payload]
    if not isinstance(versions, list):
        raise PortfolioLedgerError("model ledger source verification input is invalid")
    filled = [
        order for version in versions for order in version.get("orders", [])
        if order.get("status") == "filled"
    ]
    if not filled:
        return
    attested: set[str] = set()
    try:
        with closing(connect_source(Path(source_db_path))) as source:
            for order in filled:
                bar = source.execute(
                    """SELECT b.snapshot_id,b.trade_date,b.open,b.raw_hash,
                              s.data_mode,s.quality_status
                       FROM daily_bars b JOIN dataset_snapshots s ON s.id=b.snapshot_id
                       WHERE b.ticker=? AND b.trade_date>? AND b.quality_status='accepted'
                         AND s.data_mode='REAL' AND s.quality_status='passed'
                       ORDER BY b.trade_date ASC,s.created_at DESC LIMIT 1""",
                    (order["ticker"], order["scheduled_after"]),
                ).fetchone()
                if not bar:
                    raise PortfolioLedgerError(f"model ledger source bar is missing: {order['ticker']}")
                if bar["snapshot_id"] not in attested:
                    verify_snapshot_content_attestation(source, bar["snapshot_id"])
                    attested.add(bar["snapshot_id"])
                if (
                    bar["snapshot_id"] != order.get("source_snapshot_id")
                    or bar["trade_date"] != order.get("effective_trade_date")
                    or abs(float(bar["open"]) - float(order.get("fill_price"))) > 1e-9
                    or bar["raw_hash"] != order.get("source_row_hash")
                ):
                    raise PortfolioLedgerError(f"model ledger fill does not match the next authoritative open: {order['ticker']}")
    except PortfolioLedgerError:
        raise
    except (OSError, sqlite3.DatabaseError, RuntimeError, TypeError, ValueError) as exc:
        raise PortfolioLedgerError("model ledger source verification failed") from exc
