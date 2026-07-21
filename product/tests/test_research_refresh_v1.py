from __future__ import annotations

import base64
import copy
import fcntl
import hashlib
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from functools import partial
from io import StringIO
from pathlib import Path
from unittest.mock import patch


PRODUCT = Path(__file__).resolve().parents[1]
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from data_core import (  # noqa: E402
    CanonicalComponent,
    CanonicalPublicationError,
    CanonicalResearchRefresh,
    CollectedBundle,
    DataFoundation,
    FileBundleFallbackAdapter,
    InjectedInterruption,
    LegacyCollectorAdapter,
    RefreshInProgressError,
    SnapshotReader,
    SourceManifest,
    canonical_active_report,
)
from data_core.fixtures import fixture_payload  # noqa: E402
from data_core.research_refresh import (  # noqa: E402
    _default_research_builder,
    latest_completed_trade_date,
    normalize_legacy_collector_bundle,
)
from data_store import DEMO_POSITIONS  # noqa: E402
from real_pipeline import replay_snapshot  # noqa: E402
from refresh_engine import main as refresh_cli_main  # noqa: E402
from server import product_report_payload  # noqa: E402


SHANGHAI = timezone(timedelta(hours=8))
DAY_ONE = "2026-07-17"
DAY_TWO = "2026-07-20"
UNIVERSE = tuple(item["ticker"] for item in DEMO_POSITIONS)
MANIFEST = SourceManifest(
    source_key="m3_acceptance_bundle_v1",
    domain_scope="a_share_market_bundle",
    authority_tier="canonical",
    provider_version="fixture-two-day-v1",
    schema_version="canonical-research-refresh-v1",
    license_status="internal_test_only",
    source_url="fixture://m3-research-refresh",
    quality_flags=("fixture", "not_real_time"),
)


def legacy_inputs(bar_count: int = 2) -> dict:
    def raw_fields(label: str) -> dict:
        raw = label.encode("utf-8")
        return {
            "raw_hash": hashlib.sha256(raw).hexdigest(),
            "raw_payload_b64": base64.b64encode(raw).decode("ascii"),
        }

    dates = []
    cursor = datetime.fromisoformat(DAY_TWO).date()
    while len(dates) < bar_count:
        if cursor.weekday() < 5:
            dates.append(cursor.isoformat())
        cursor -= timedelta(days=1)
    dates.reverse()
    quotes, klines, financials = {}, {}, {}
    for index, item in enumerate(DEMO_POSITIONS):
        ticker = item["ticker"]
        quotes[ticker] = {
            "ticker": ticker, "quote_time": f"{DAY_TWO}T15:00:00+08:00",
            "price": 100 + index, "change_pct": 1.0, "high": 101 + index,
            "low": 99 + index, "pe_ttm": 20.0, "pb": 2.0,
            "market_cap_yi": 1000.0, "circulating_cap_yi": 800.0,
            "source_key": "tencent_quote", "source_url": "https://qt.gtimg.cn/",
            "raw_hash": hashlib.sha256(f"quote:{ticker}".encode()).hexdigest(),
        }
        klines[ticker] = {
            "ticker": ticker, "source_url": f"https://web.ifzq.gtimg.cn/kline/{ticker}",
            **raw_fields(f"kline:{ticker}:{bar_count}"), "bars": [
                {
                    "trade_date": trade_date, "open": 99.0 + offset / 10,
                    "close": 100.0 + offset / 10, "high": 101.0 + offset / 10,
                    "low": 98.0 + offset / 10, "volume_lots": 1000.0 + offset,
                }
                for offset, trade_date in enumerate(dates)
            ],
        }
        financials[ticker] = {
            "ticker": ticker, "source_url": f"https://datacenter.eastmoney.com/finance/{ticker}",
            **raw_fields(f"financial:{ticker}"), "rows": [{
                "report_date": "2026-03-31", "notice_date": "2026-04-20",
                "revenue": 1_000_000_000.0, "net_profit": 100_000_000.0,
                "revenue_yoy": 5.0, "net_profit_yoy": 6.0, "roe": 4.0,
                "gross_margin": 20.0, "net_margin": 10.0, "debt_ratio": 40.0,
                "operating_cash_per_share": 1.0,
            }],
        }
    calendar_raw = "calendar:" + ",".join(dates)
    return {
        "quotes": quotes, "klines": klines, "financials": financials,
        "quote_raw": {"source_url": "https://qt.gtimg.cn/", **raw_fields("quotes:all")},
        "exchange_calendar": {
            "trade_dates": dates,
            "source_url": "https://finance.sina.com.cn/realstock/company/klc_td_sh.txt",
            **raw_fields(calendar_raw),
        },
        "finished_at": f"{DAY_TWO}T16:00:00+08:00",
    }


def market_payload(day: str = DAY_ONE) -> dict:
    payload = fixture_payload()
    mobile = {
        "instrument_id": "CN:600941.SH", "ticker": "600941.SH", "name": "中国移动",
        "exchange": "SSE", "board": "MAIN", "industry": "通信",
        "listed_at": "2022-01-05", "case": "normal",
    }
    payload["instruments"].append(mobile)
    payload["statuses"].append({
        "instrument_id": mobile["instrument_id"], "trade_date": DAY_ONE, "trading_status": "normal",
    })
    payload["factors"].append({
        "instrument_id": mobile["instrument_id"], "trade_date": DAY_ONE, "factor": 1.0, "version": 1,
    })
    payload["bars"].append({
        "instrument_id": mobile["instrument_id"], "trade_date": DAY_ONE,
        "open": 110.0, "high": 113.0, "low": 109.0, "close": 112.0,
        "volume": 2_000_000.0, "amount": 224_000_000.0, "adjustment_version": 1,
    })
    payload["financials"].append({
        "fact_id": "fact:600941.SH:20260331:revenue:r1", "instrument_id": mobile["instrument_id"],
        "report_date": "2026-03-31", "announced_at": "2026-04-22T18:00:00+08:00",
        "revision": 1, "metric_key": "revenue", "metric_value": 263_700_000_000.0, "unit": "CNY",
    })
    end = datetime.fromisoformat(DAY_ONE).date()
    history = []
    cursor = end
    while len(history) < 2:
        if cursor.weekday() < 5:
            history.append(cursor.isoformat())
        cursor -= timedelta(days=1)
    history.reverse()
    base_factors = {
        row["instrument_id"]: row for row in payload["factors"]
    }
    expanded_bars = []
    expanded_factors = []
    for bar in payload["bars"]:
        base_close = float(bar["close"])
        for index, trade_date in enumerate(history):
            close = max(1.0, base_close - (len(history) - 1 - index) * 0.03)
            expanded_bars.append({
                **bar, "trade_date": trade_date, "open": close - 0.2,
                "high": close + 0.5, "low": close - 0.5, "close": close,
                "amount": close * float(bar["volume"]),
            })
            factor = base_factors[bar["instrument_id"]]
            expanded_factors.append({
                **factor, "trade_date": trade_date,
                "factor": factor["factor"] if trade_date == DAY_ONE else 1.0,
            })
    suspended_factors = [
        row for row in payload["factors"]
        if row["instrument_id"] not in {bar["instrument_id"] for bar in payload["bars"]}
    ]
    payload["bars"] = expanded_bars
    payload["factors"] = [*expanded_factors, *suspended_factors]
    payload["intelligence"] = [
        {
            "item_id": f"quote:{item['ticker']}:{DAY_ONE}",
            "instrument_id": f"CN:{item['ticker']}", "title": f"{item['ticker']} market quote",
            "published_at": f"{DAY_ONE}T15:00:00+08:00",
            "evidence": {"price": float(20 + index), "source_key": "fixture_quote"},
            "is_llm_inferred": False,
        }
        for index, item in enumerate(DEMO_POSITIONS)
    ]
    if day == DAY_TWO:
        payload["as_of"] = DAY_TWO
        payload["known_at"] = f"{DAY_TWO}T16:30:00+08:00"
        for row in payload["calendar"]:
            row["trade_date"] = DAY_TWO
            row["previous_open_date"] = DAY_ONE
        for row in payload["statuses"]:
            row["trade_date"] = DAY_TWO
        latest_factors = {}
        for row in payload["factors"]:
            latest_factors[row["instrument_id"]] = row
        payload["factors"] = [
            {**row, "trade_date": DAY_TWO, "factor": 1.0}
            for row in latest_factors.values()
        ]
        latest_bars = {}
        for row in payload["bars"]:
            latest_bars[row["instrument_id"]] = row
        payload["bars"] = [
            {
                **row, "trade_date": DAY_TWO, "open": row["open"] + 1.0,
                "high": row["high"] + 1.0, "low": row["low"] + 1.0,
                "close": row["close"] + 1.0,
                "amount": (row["close"] + 1.0) * row["volume"],
            }
            for row in latest_bars.values()
        ]
        payload["actions"] = []
        for row in payload["intelligence"]:
            row["item_id"] = row["item_id"].replace(DAY_ONE, DAY_TWO)
            row["published_at"] = row["published_at"].replace(DAY_ONE, DAY_TWO)
    return payload


class StaticAdapter:
    def __init__(
        self, payload: dict | None, *, name: str, role: str, error: str | None = None,
        components: tuple[CanonicalComponent, ...] = (),
    ) -> None:
        self.payload = payload
        self.name = name
        self.role = role
        self.error = error
        self.components = components
        self.calls = 0

    def collect(self, now: datetime) -> CollectedBundle:
        self.calls += 1
        if self.error:
            raise RuntimeError(self.error)
        assert self.payload is not None
        return CollectedBundle(
            adapter=self.name, role=self.role, payload=copy.deepcopy(self.payload),
            manifest=SourceManifest(
                **{**MANIFEST.__dict__, "source_key": self.name, "source_url": f"fixture://{self.name}"}
            ),
            data_kind="fixture", components=self.components,
        )


class ResearchRefreshV1Test(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db_path = self.root / "canonical.db"
        self.state_root = self.root / "refresh"
        self.foundation = DataFoundation(self.db_path)
        self.now_one = datetime(2026, 7, 17, 16, 30, tzinfo=SHANGHAI)
        self.now_two = datetime(2026, 7, 20, 16, 30, tzinfo=SHANGHAI)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def engine(self, adapters, builder=None) -> CanonicalResearchRefresh:
        kwargs = {
            "research_builder": builder or partial(_default_research_builder, minimum_bars=2)
        }
        return CanonicalResearchRefresh(
            self.foundation, self.state_root, adapters, universe=UNIVERSE, **kwargs
        )

    def test_two_day_incremental_refresh_and_same_input_reuse(self) -> None:
        adapter = StaticAdapter(market_payload(), name="primary_fixture", role="primary")
        engine = self.engine([adapter])
        first = engine.run(now=self.now_one)
        same = engine.run(now=self.now_one)
        self.assertEqual(first["status"], "success")
        self.assertEqual(first["report_gate"], {"required": 8, "passed": 8, "status": "passed"})
        publication = json.loads((self.state_root / first["publication_manifest"]).read_text())
        self.assertEqual(publication["report_schema_version"], "research-report-v1")
        self.assertEqual(len(publication["report_hashes"]), 8)
        self.assertEqual(first["active"]["publication_id"], publication["publication_id"])
        self.assertTrue(same["ingestion_reused"])
        self.assertEqual(same["snapshot_id"], first["snapshot_id"])
        adapter.payload = market_payload(DAY_TWO)
        second = engine.run(now=self.now_two)
        self.assertEqual(second["status"], "success")
        self.assertNotEqual(second["snapshot_id"], first["snapshot_id"])
        reader = SnapshotReader(self.foundation, second["snapshot_id"])
        catl_bars = reader.research_context("300750.SZ")["daily_bars"]
        self.assertEqual(len(catl_bars), 3)
        self.assertEqual([row["trade_date"] for row in catl_bars][-2:], [DAY_ONE, DAY_TWO])
        self.assertEqual(engine.status()["status"], "healthy")

    def test_gap_repair_uses_canonical_key_not_global_max_date(self) -> None:
        incomplete = market_payload()
        missing_date = "2026-07-16"
        incomplete["bars"] = [
            row for row in incomplete["bars"]
            if not (row["instrument_id"] == "CN:600519.SH" and row["trade_date"] == missing_date)
        ]
        incomplete["factors"] = [
            row for row in incomplete["factors"]
            if not (row["instrument_id"] == "CN:600519.SH" and row["trade_date"] == missing_date)
        ]
        adapter = StaticAdapter(incomplete, name="primary_gap", role="primary")
        engine = self.engine([adapter])
        engine.run(now=self.now_one)
        adapter.payload = market_payload()
        repaired = engine.run(now=self.now_one + timedelta(minutes=1))
        rows = SnapshotReader(self.foundation, repaired["snapshot_id"]).research_context("600519.SH")["daily_bars"]
        self.assertEqual([row["trade_date"] for row in rows], [missing_date, DAY_ONE])

    def test_primary_failure_uses_only_explicit_fallback_and_traces_selection(self) -> None:
        primary = StaticAdapter(None, name="primary", role="primary", error="source unavailable")
        fallback = StaticAdapter(market_payload(), name="fallback", role="fallback")
        result = self.engine([primary, fallback]).run(now=self.now_one)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["selected_adapter"], "fallback")
        self.assertEqual([item["status"] for item in result["attempts"]], ["failed", "success"])
        self.assertEqual([item["role"] for item in result["attempts"]], ["primary", "fallback"])

    def test_primary_quality_failure_uses_fallback_before_selection(self) -> None:
        broken = market_payload()
        broken["bars"] = [
            row for row in broken["bars"]
            if not (row["instrument_id"] == "CN:600519.SH" and row["trade_date"] == DAY_ONE)
        ]
        primary = StaticAdapter(broken, name="primary_bad_quality", role="primary")
        fallback = StaticAdapter(market_payload(), name="fallback_good", role="fallback")
        result = self.engine([primary, fallback]).run(now=self.now_one)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["selected_adapter"], "fallback_good")
        self.assertEqual([item["status"] for item in result["attempts"]], ["failed", "success"])
        self.assertIn("normal instruments missing bars", result["attempts"][0]["error"])
        audit = result["attempts"][0]["canonical_quality"]
        self.assertEqual(audit["status"], "failed")
        self.assertTrue(audit["evaluation_id"])
        self.assertTrue(audit["gate_hash"])
        self.assertTrue(audit["checks"])
        self.assertTrue(audit["blockers"])
        failed_bundle = self.state_root / result["attempts"][0]["bundle_path"]
        self.assertTrue(failed_bundle.is_file())
        self.assertEqual(
            hashlib.sha256(
                json.dumps(
                    json.loads(failed_bundle.read_text()), ensure_ascii=False,
                    sort_keys=True, separators=(",", ":"), default=str,
                ).encode()
            ).hexdigest(),
            result["attempts"][0]["bundle_hash"],
        )

    def test_all_sources_failed_preserves_previous_active_snapshot(self) -> None:
        first = self.engine([
            StaticAdapter(market_payload(), name="primary_good", role="primary")
        ]).run(now=self.now_one)
        failed = self.engine([
            StaticAdapter(None, name="primary_bad", role="primary", error="primary down"),
            StaticAdapter(None, name="fallback_bad", role="fallback", error="fallback down"),
        ]).run(now=self.now_two)
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["active_preserved"]["snapshot_id"], first["snapshot_id"])
        active = json.loads((self.state_root / "active.json").read_text())
        self.assertEqual(active["snapshot_id"], first["snapshot_id"])

    def test_one_report_failure_isolated_and_does_not_switch_active(self) -> None:
        first = self.engine([
            StaticAdapter(market_payload(), name="primary_one", role="primary")
        ]).run(now=self.now_one)

        def fail_one(reader: SnapshotReader, ticker: str) -> dict:
            if ticker == "600941.SH":
                raise RuntimeError("injected company research failure")
            return _default_research_builder(reader, ticker, minimum_bars=2)

        partial = self.engine([
            StaticAdapter(market_payload(DAY_TWO), name="primary_two", role="primary")
        ], builder=fail_one).run(now=self.now_two)
        self.assertEqual(partial["status"], "partial")
        self.assertEqual(partial["report_gate"], {"required": 8, "passed": 7, "status": "failed"})
        self.assertEqual(json.loads((self.state_root / "active.json").read_text())["snapshot_id"], first["snapshot_id"])
        self.assertEqual(sum(item["status"] == "failed" for item in partial["reports"]), 1)

    def test_bogus_report_hash_cannot_pass_activation_gate(self) -> None:
        def bogus_hash(reader: SnapshotReader, ticker: str) -> dict:
            artifact = _default_research_builder(reader, ticker, minimum_bars=2)
            artifact["report_hash"] = "bogus"
            artifact["report"]["report_hash"] = "bogus"
            return artifact

        result = self.engine([
            StaticAdapter(market_payload(), name="primary_bogus_hash", role="primary")
        ], builder=bogus_hash).run(now=self.now_one)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["report_gate"]["passed"], 0)
        self.assertFalse((self.state_root / "active.json").exists())

    def test_interrupted_run_resumes_from_snapshot_without_recollecting(self) -> None:
        adapter = StaticAdapter(market_payload(), name="primary_resume", role="primary")
        engine = self.engine([adapter])
        with self.assertRaises(InjectedInterruption):
            engine.run(now=self.now_one, interrupt_after="snapshotted")
        self.assertEqual(adapter.calls, 1)
        resumed = engine.run(now=self.now_one)
        self.assertTrue(resumed["resumed"])
        self.assertEqual(adapter.calls, 1)
        self.assertEqual(resumed["status"], "success")
        with self.foundation.connect() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM core_ingestion_runs").fetchone()[0], 1)

    def test_dry_run_and_status_do_not_call_network_adapter(self) -> None:
        adapter = StaticAdapter(None, name="primary_dry", role="primary", error="must not run")
        engine = self.engine([adapter])
        plan = engine.run(now=self.now_one, dry_run=True)
        self.assertEqual(plan["status"], "dry_run")
        self.assertFalse(plan["network_called"])
        self.assertEqual(adapter.calls, 0)
        self.assertEqual(engine.status()["status"], "attention")

    def test_unhealthy_status_returns_nonzero_for_scheduler(self) -> None:
        argv = [
            "refresh_engine.py", "--canonical", "--status",
            "--canonical-db", str(self.db_path), "--state-root", str(self.state_root),
        ]
        with patch.object(sys, "argv", argv), redirect_stdout(StringIO()):
            with self.assertRaises(SystemExit) as caught:
                refresh_cli_main()
        self.assertEqual(caught.exception.code, 1)

    def test_snapshot_replay_and_research_are_network_free(self) -> None:
        result = self.engine([
            StaticAdapter(market_payload(), name="primary_replay", role="primary")
        ]).run(now=self.now_one)
        with patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden")):
            replay = replay_snapshot(result["snapshot_id"], self.db_path)
            context = SnapshotReader(self.foundation, result["snapshot_id"]).research_context("300750.SZ")
        self.assertEqual(replay["status"], "passed")
        self.assertTrue(replay["canonical"])
        self.assertEqual(context["snapshot_id"], result["snapshot_id"])
        self.assertEqual(result["no_network_replay"]["status"], "passed")

    def test_tampered_active_report_fails_health_and_is_not_reused(self) -> None:
        adapter = StaticAdapter(market_payload(), name="primary_integrity", role="primary")
        engine = self.engine([adapter])
        first = engine.run(now=self.now_one)
        publication = json.loads((self.state_root / first["publication_manifest"]).read_text())
        report_path = self.state_root / publication["report_artifacts"]["300750.SZ"]
        artifact = json.loads(report_path.read_text())
        artifact["report"]["title"] = "tampered"
        report_path.write_text(json.dumps(artifact, ensure_ascii=False), encoding="utf-8")
        self.assertEqual(engine.status()["status"], "attention")
        repaired = engine.run(now=self.now_one + timedelta(minutes=1))
        self.assertEqual(repaired["status"], "success")
        self.assertFalse(repaired.get("reuse_active", False))
        self.assertEqual(engine.status()["status"], "healthy")

    def test_active_date_and_kind_must_match_publication(self) -> None:
        engine = self.engine([
            StaticAdapter(market_payload(), name="primary_active_identity", role="primary")
        ])
        engine.run(now=self.now_one)
        active_path = self.state_root / "active.json"
        active = json.loads(active_path.read_text())
        active["target_trade_date"] = "1999-01-01"
        active["snapshot_kind"] = "real"
        active_path.write_text(json.dumps(active, ensure_ascii=False), encoding="utf-8")
        self.assertEqual(engine.status()["status"], "attention")
        with self.assertRaises(CanonicalPublicationError):
            canonical_active_report("300750.SZ", self.state_root)

    def test_research_builder_socket_access_is_blocked_before_activation(self) -> None:
        import socket

        def network_builder(reader: SnapshotReader, ticker: str) -> dict:
            socket.create_connection(("example.com", 443), timeout=0.01)
            return _default_research_builder(reader, ticker, minimum_bars=2)

        result = self.engine([
            StaticAdapter(market_payload(), name="primary_network_attack", role="primary")
        ], builder=network_builder).run(now=self.now_one)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["report_gate"]["passed"], 0)
        self.assertFalse((self.state_root / "active.json").exists())
        self.assertTrue(all("network access is forbidden" in item["error"] for item in result["reports"]))

    def test_research_builder_connect_ex_and_external_processes_are_blocked(self) -> None:
        import socket
        import subprocess
        import _socket

        def connect_ex_attack() -> None:
            sock = socket.socket()
            try:
                sock.connect_ex(("127.0.0.1", 9))
            finally:
                sock.close()

        for attack in (
            connect_ex_attack,
            lambda: _socket.socket().connect(("127.0.0.1", 9)),
            lambda: subprocess.run(["curl", "https://example.com"], check=False),
            lambda: os.spawnv(os.P_WAIT, "/usr/bin/true", ["true"]),
        ):
            def network_builder(reader: SnapshotReader, ticker: str, call=attack) -> dict:
                call()
                return _default_research_builder(reader, ticker, minimum_bars=2)

            root = self.root / hashlib.sha256(repr(attack).encode()).hexdigest()[:8]
            result = CanonicalResearchRefresh(
                self.foundation, root,
                [StaticAdapter(market_payload(), name="primary_escape", role="primary")],
                universe=UNIVERSE, research_builder=network_builder,
            ).run(now=self.now_one)
            self.assertEqual(result["status"], "partial")
            self.assertEqual(result["report_gate"]["passed"], 0)

    def test_process_lock_rejects_duplicate_trigger(self) -> None:
        engine = self.engine([
            StaticAdapter(market_payload(), name="primary_lock", role="primary")
        ])
        self.state_root.mkdir(parents=True)
        with (self.state_root / "refresh.lock").open("a+") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(RefreshInProgressError, "already"):
                engine.run(now=self.now_one)

    def test_calendar_rejects_current_day_before_market_close(self) -> None:
        with self.assertRaisesRegex(ValueError, "no completed trading date"):
            latest_completed_trade_date(
                market_payload(), datetime(2026, 7, 17, 14, 59, tzinfo=SHANGHAI)
            )

    def test_legacy_normalizer_uses_newer_common_date_as_target(self) -> None:
        payload = normalize_legacy_collector_bundle(legacy_inputs())
        self.assertEqual(payload["as_of"], DAY_TWO)
        target_rows = [row for row in payload["calendar"] if row["trade_date"] == DAY_TWO]
        self.assertTrue(target_rows)
        self.assertTrue(all(row["previous_open_date"] == DAY_ONE for row in target_rows))
        self.assertEqual(latest_completed_trade_date(payload, self.now_two), DAY_TWO)

    def test_qfq_version_identity_is_chronological_before_hash_suffix(self) -> None:
        older = legacy_inputs(250)
        newer = copy.deepcopy(older)
        for quote in older["quotes"].values():
            quote["quote_time"] = f"{DAY_TWO}T15:00:00+08:00"
        for quote in newer["quotes"].values():
            quote["quote_time"] = f"{DAY_TWO}T15:01:00+08:00"
        old_payload = normalize_legacy_collector_bundle(older)
        new_payload = normalize_legacy_collector_bundle(newer)
        old_version = next(row["adjustment_version"] for row in old_payload["bars"])
        new_version = next(row["adjustment_version"] for row in new_payload["bars"])
        self.assertGreater(new_version, old_version)

    def test_missing_bar_is_not_silently_relabelled_as_suspension(self) -> None:
        inputs = legacy_inputs(3)
        inputs["klines"]["600519.SH"]["bars"] = [
            row for row in inputs["klines"]["600519.SH"]["bars"] if row["trade_date"] != DAY_TWO
        ]
        payload = normalize_legacy_collector_bundle(inputs)
        status = next(
            row for row in payload["statuses"] if row["instrument_id"] == "CN:600519.SH"
        )
        self.assertEqual(payload["as_of"], DAY_TWO)
        self.assertEqual(status["trading_status"], "normal")
        self.assertFalse(any(
            row["instrument_id"] == "CN:600519.SH" and row["trade_date"] == DAY_TWO
            for row in payload["bars"]
        ))

    def test_legacy_production_adapter_builds_real_standard_reports(self) -> None:
        engine = CanonicalResearchRefresh(
            self.foundation, self.state_root, [LegacyCollectorAdapter(timeout=0.01)],
            universe=UNIVERSE,
        )
        with patch("real_pipeline.collect_real_inputs", return_value=legacy_inputs(250)):
            result = engine.run(now=self.now_two)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["snapshot_kind"], "real")
        self.assertEqual(result["report_gate"], {"required": 8, "passed": 8, "status": "passed"})
        self.assertEqual(
            [item["source_key"] for item in result["ingestion_runs"]],
            ["sina_exchange_calendar_v1", "tencent_qfq_daily_v1", "tencent_quote_v1", "eastmoney_f10_main_v1"],
        )
        self.assertTrue(all(item["report"]["report_contract"]["schema_version"] == "research-report-v1" for item in result["reports"]))

    def test_explicit_file_bundle_fallback_is_cached_not_real(self) -> None:
        with patch("real_pipeline.collect_real_inputs", return_value=legacy_inputs(250)):
            frozen = LegacyCollectorAdapter(timeout=0.01).collect(self.now_two)
        bundle_path = self.root / "fallback-bundle.json"
        bundle_path.write_text(json.dumps(frozen.as_json(), ensure_ascii=False), encoding="utf-8")
        result = CanonicalResearchRefresh(
            self.foundation, self.state_root,
            [
                StaticAdapter(None, name="failed_primary", role="primary", error="primary down"),
                FileBundleFallbackAdapter(bundle_path),
            ],
            universe=UNIVERSE,
        ).run(now=self.now_two)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["selected_role"], "fallback")
        self.assertEqual(result["snapshot_kind"], "cached")
        self.assertTrue(all(item["report"]["data_mode"] == "CACHED" for item in result["reports"]))

    def test_product_consumer_reads_only_integrity_checked_canonical_active(self) -> None:
        result = self.engine([
            StaticAdapter(market_payload(), name="primary_product_path", role="primary")
        ]).run(now=self.now_one)
        report = canonical_active_report("300750.SZ", self.state_root)
        self.assertIsNotNone(report)
        self.assertEqual(report["data_status"], "verified")
        self.assertEqual(report["generated_from"]["snapshot_id"], result["snapshot_id"])
        with patch.dict(os.environ, {"PARK_CANONICAL_STATE_ROOT": str(self.state_root)}):
            served = product_report_payload("300750.SZ")
        self.assertEqual(served["report_hash"], report["report_hash"])
        publication = json.loads((self.state_root / result["publication_manifest"]).read_text())
        path = self.state_root / publication["report_artifacts"]["300750.SZ"]
        artifact = json.loads(path.read_text())
        artifact["report_hash"] = "tampered"
        path.write_text(json.dumps(artifact, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(CanonicalPublicationError):
            canonical_active_report("300750.SZ", self.state_root)
        with patch.dict(os.environ, {"PARK_CANONICAL_STATE_ROOT": str(self.state_root)}):
            with self.assertRaises(CanonicalPublicationError):
                product_report_payload("300750.SZ")

    def test_cached_fallback_cannot_reuse_real_ingestion_identity(self) -> None:
        with patch("real_pipeline.collect_real_inputs", return_value=legacy_inputs(250)):
            frozen = LegacyCollectorAdapter(timeout=0.01).collect(self.now_two)
        primary = CanonicalResearchRefresh(
            self.foundation, self.state_root, [StaticAdapter(None, name="unused", role="primary", error="unused")],
            universe=UNIVERSE,
        )
        for component in frozen.components:
            primary.foundation.ingest_payload(component.payload, component.manifest, data_kind="real")
        bundle_path = self.root / "same-real-bundle.json"
        bundle_path.write_text(json.dumps(frozen.as_json(), ensure_ascii=False), encoding="utf-8")
        result = CanonicalResearchRefresh(
            self.foundation, self.root / "fallback-state",
            [
                StaticAdapter(None, name="failed_primary", role="primary", error="primary down"),
                FileBundleFallbackAdapter(bundle_path),
            ],
            universe=UNIVERSE,
        ).run(now=self.now_two)
        self.assertEqual(result["status"], "failed")
        self.assertIn("mixes trust kinds", result["error"])
        self.assertFalse((self.root / "fallback-state" / "active.json").exists())

    def test_stale_candidate_cannot_replace_newer_active(self) -> None:
        adapter = StaticAdapter(market_payload(), name="primary_new", role="primary")
        engine = self.engine([adapter])
        engine.run(now=self.now_one)
        adapter.payload = market_payload(DAY_TWO)
        newer = engine.run(now=self.now_two)
        stale = self.engine([
            StaticAdapter(market_payload(), name="primary_new", role="primary")
        ]).run(now=self.now_two + timedelta(minutes=1))
        self.assertEqual(stale["status"], "failed")
        self.assertIn("older than the current active", stale["error"])
        self.assertEqual(json.loads((self.state_root / "active.json").read_text())["snapshot_id"], newer["snapshot_id"])

    def test_non_fixture_kind_cannot_ingest_fixture_payload(self) -> None:
        with self.assertRaisesRegex(ValueError, "disagree"):
            self.foundation.ingest_payload(market_payload(), MANIFEST, data_kind="real")

    def test_non_allowlisted_normalized_bundle_cannot_claim_real(self) -> None:
        payload = market_payload()
        payload["fixture"] = False
        manifest = SourceManifest(
            **{
                **MANIFEST.__dict__, "source_key": "real_acceptance_bundle",
                "license_status": "configured_internal_use", "source_url": "bundle://acceptance-real",
                "quality_flags": ("normalized_bundle",),
            }
        )
        with self.assertRaisesRegex(ValueError, "not allowlisted"):
            self.foundation.ingest_payload(payload, manifest, data_kind="real")

    def test_real_component_rows_are_bound_to_provider_bytes_and_urls(self) -> None:
        with patch("real_pipeline.collect_real_inputs", return_value=legacy_inputs(250)):
            bundle = LegacyCollectorAdapter(timeout=0.01).collect(self.now_two)
        component = copy.deepcopy(bundle.components[1])
        component.payload["bars"][0]["close"] += 1.0
        with self.assertRaisesRegex(ValueError, "not bound"):
            self.foundation.ingest_payload(component.payload, component.manifest, data_kind="real")
        component = copy.deepcopy(bundle.components[1])
        component.payload["provider_raw_objects"][0]["source_url"] = "https://example.com/fake"
        with self.assertRaisesRegex(ValueError, "URL is not allowed"):
            self.foundation.ingest_payload(component.payload, component.manifest, data_kind="real")

    def test_component_sources_get_separate_manifests_runs_and_observations(self) -> None:
        payload = market_payload()
        empty = {
            "fixture": True, "as_of": payload["as_of"], "known_at": payload["known_at"],
            "instruments": [], "calendar": [], "statuses": [], "factors": [],
            "actions": [], "bars": [], "financials": [], "intelligence": [],
        }
        components = (
            CanonicalComponent(
                SourceManifest(**{**MANIFEST.__dict__, "source_key": "bars_component"}),
                {
                    **empty, "instruments": payload["instruments"], "calendar": payload["calendar"],
                    "statuses": payload["statuses"], "factors": payload["factors"],
                    "actions": payload["actions"], "bars": payload["bars"],
                },
            ),
            CanonicalComponent(
                SourceManifest(**{**MANIFEST.__dict__, "source_key": "quote_component"}),
                {**empty, "intelligence": payload["intelligence"]},
            ),
            CanonicalComponent(
                SourceManifest(**{**MANIFEST.__dict__, "source_key": "financial_component"}),
                {**empty, "financials": payload["financials"]},
            ),
        )
        result = self.engine([
            StaticAdapter(
                payload, name="aggregate", role="primary", components=components
            )
        ]).run(now=self.now_one)
        self.assertEqual(result["status"], "success")
        self.assertEqual(
            [item["source_key"] for item in result["ingestion_runs"]],
            ["bars_component", "quote_component", "financial_component"],
        )
        with self.foundation.connect() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM core_ingestion_runs").fetchone()[0], 3)
            observed = {
                row[0] for row in connection.execute("SELECT DISTINCT source_key FROM core_source_observations")
            }
        self.assertEqual(observed, {"bars_component", "quote_component", "financial_component"})


if __name__ == "__main__":
    unittest.main()
