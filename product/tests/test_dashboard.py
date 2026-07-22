from __future__ import annotations

import hashlib
import json
import copy
import tempfile
import unittest
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from datetime import date, timedelta
from contextlib import closing
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import research_reports  # noqa: E402
import real_pipeline  # noqa: E402
import batch_research  # noqa: E402
from batch_research import latest_batch, run_batch  # noqa: E402
from deepseek_writer import _user_prompt, apply_editorial_guardrails, approve_artifact, editorial_status, generate, validate_narrative  # noqa: E402
from data_store import DEMO_POSITIONS, connect, dashboard_payload, initialize, publication_approval_state, publication_content_hash, publication_history, save_market_quotes, stock_payload, transition_publication, validate_invariants  # noqa: E402
from ingest_quotes import parse_response  # noqa: E402
from real_pipeline import _retry, allocate_weights, compute_features, replay_snapshot, validate_real_input_coverage  # noqa: E402
from research_artifact_store import artifact_path, load_artifact, write_artifact  # noqa: E402
from research_reports import CATL_PROFILE, build_evidence_pack, report_payload, research_logic_hash, research_profile_hash, writer_logic_hash  # noqa: E402
from refresh_engine import RefreshInProgressError, _process_refresh_lock, refresh_status, run_refresh  # noqa: E402
from research_evidence import build_evidence_set, evidence_coverage, import_uzi_raw, load_evidence_set, sync_profile_sources  # noqa: E402
from report_versions import archive_report, compare_reports, report_version_history  # noqa: E402
from portfolio_committee import committee_payload, validate_committee_payload  # noqa: E402
from publication_pack import ARTIFACT_NAMES, validate_archive, validate_pack  # noqa: E402
from report_contract import ReportContractError, validate_report_contract  # noqa: E402
from auth_store import authenticate, create_invite, create_owner, create_session, has_entitlement, list_members, redeem_access_code, redeem_invite, session_member, set_member_status, verify_csrf  # noqa: E402


class DashboardContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "test.db"
        initialize(self.db_path)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    @staticmethod
    def captured_sources(sources: list[dict]) -> list[dict]:
        return copy.deepcopy(sources)

    def sync_captured(self, ticker: str, sources: list[dict], *, observed_at: str) -> dict:
        def fake_remote(url: str, timeout: float = 30.0) -> tuple[bytes, str, int]:
            mime = "application/pdf" if url.lower().endswith(".pdf") else "text/html"
            identity = {
                "300750.SZ": "宁德时代新能源科技股份有限公司 季度报告 证券代码：300750 证券简称：宁德时代",
                "600519.SH": "贵州茅台酒股份有限公司 年度报告 公司代码：600519 公司简称：贵州茅台",
            }.get(ticker.upper(), ticker.upper())
            return f"{identity} frozen test source fetched from {url}".encode(), mime, 200

        with patch("research_evidence._capture_remote", side_effect=fake_remote):
            return sync_profile_sources(
                ticker, self.captured_sources(sources), self.db_path,
                capture_remote=True, observed_at=observed_at,
            )

    def promote_catl_fixture_to_real(self, *, with_evidence: bool = True) -> None:
        with closing(connect(self.db_path)) as conn:
            snapshot_id = "snap_demo_20260717_v1"
            conn.execute(
                "UPDATE dataset_snapshots SET data_mode='REAL', quality_status='passed', as_of='2026-07-17', known_at='2026-07-17T15:00:00+08:00' WHERE id=?",
                (snapshot_id,),
            )
            conn.execute("UPDATE publications SET status='quality_passed' WHERE id='pub_demo_2026w29'")
            conn.execute("UPDATE evidence SET quality_status='accepted' WHERE publication_id='pub_demo_2026w29'")
            conn.execute("UPDATE portfolio_items SET target_weight=8 WHERE publication_id='pub_demo_2026w29' AND ticker='300750.SZ'")
            conn.execute("UPDATE portfolio_items SET target_weight=14 WHERE publication_id='pub_demo_2026w29' AND ticker='600519.SH'")
            for index, item in enumerate(DEMO_POSITIONS):
                price = 360 if item["ticker"] == "300750.SZ" else 100 + index
                conn.execute(
                    "INSERT INTO market_quotes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (snapshot_id, item["ticker"], item["name"], price, -0.5, price + 2, price - 2, 21.09, 5.1, 16000, 12000,
                     "2026-07-17T15:00:00+08:00", "tencent_quote", "https://example.test/quote", f"qhash-{index}", "2026-07-17T15:01:00+08:00", "accepted"),
                )
                conn.executemany(
                    "INSERT INTO daily_bars VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [(snapshot_id, item["ticker"], (date(2026, 7, 17) - timedelta(days=249 - day)).isoformat(), price, price, price + 1, price - 1, 100000, "tencent_qfq_daily", f"bhash-{index}", "accepted") for day in range(250)],
                )
                conn.execute(
                    "INSERT INTO financial_metrics VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (snapshot_id, item["ticker"], "2025-12-31", "2026-03-10", "年报", 4237e8, 722e8, 17.04, 42.28, 24.91, 24.4, 17.0, 61.94, 30.0, "eastmoney_f10_main", f"fhash-{index}", "accepted"),
                )
                if item["ticker"] != "300750.SZ":
                    conn.execute(
                        "INSERT INTO financial_metrics VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (snapshot_id, item["ticker"], "2026-03-31", "2026-04-16", "一季报", 1100e8, 180e8,
                         8 + index, 10 + index, 5.0, 24.0, 16.0, 55.0, 2.0,
                         "eastmoney_f10_main", f"fhash-q1-{index}", "accepted"),
                    )
            conn.execute(
                "INSERT INTO stock_features VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (snapshot_id, "300750.SZ", -3, -15.4, 42.3, 39.9, -24, 350, 370, 380, 50, 60, 85, 42, 70, 56.6, 100, "test-v1"),
            )
            for index, item in enumerate(DEMO_POSITIONS):
                if item["ticker"] == "300750.SZ":
                    continue
                price = 100 + index
                conn.execute(
                    "INSERT INTO stock_features VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (snapshot_id, item["ticker"], 2 + index, 5 + index, 10 + index, 20 + index, -12,
                     price - 1, price - 2, price - 3, 10, 65, 70, 68, 72, 68.5, 100, "test-v1"),
                )
            conn.execute(
                "INSERT INTO financial_metrics VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (snapshot_id, "300750.SZ", "2026-03-31", "2026-04-16", "一季报", 847e8, 155e8, 52.45, 48.52, 5.0, 24.82, 18.3, 61.0, 5.7, "eastmoney_f10_main", "fhash-q1", "accepted"),
            )
            conn.executemany(
                "INSERT INTO source_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    ("run-q", snapshot_id, "tencent_quote", "2026-07-17T07:00:00+00:00", "2026-07-17T07:01:00+00:00", "success", 8, 8, None),
                    ("run-b", snapshot_id, "tencent_qfq_daily", "2026-07-17T07:00:00+00:00", "2026-07-17T07:01:00+00:00", "success", 2000, 2000, None),
                    ("run-f", snapshot_id, "eastmoney_f10_main", "2026-07-17T07:00:00+00:00", "2026-07-17T07:01:00+00:00", "success", 16, 16, None),
                ],
            )
            conn.commit()
        if with_evidence:
            self.sync_captured("300750.SZ", CATL_PROFILE["sources"], observed_at="2026-07-17T14:00:00+08:00")
            build_evidence_set("300750.SZ", "snap_demo_20260717_v1", self.db_path)

    def catl_artifact_binding(self, deterministic: dict) -> tuple[dict, str]:
        evidence_set = load_evidence_set("300750.SZ", "snap_demo_20260717_v1", self.db_path)
        assert evidence_set is not None
        evidence_hash = hashlib.sha256(json.dumps(build_evidence_pack(deterministic, evidence_set), ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()
        return evidence_set, evidence_hash

    @staticmethod
    def valid_narrative() -> dict:
        paragraph = "这是基于已列明证据形成的定性判断，重点解释经营驱动、竞争约束和后续验证路径。事实与推断分别表达，证据不足之处保持空白，不使用外部知识填补，也不把模型文本当成交易指令。"
        section = {"title": "分析", "conclusion": "需要持续验证", "paragraphs": [paragraph, paragraph], "source_ids": ["annual_business"]}
        return {
            "report_title": "宁德时代深度研究测试稿",
            "executive_summary": {"conclusion": "审慎观察", "paragraphs": [paragraph, paragraph], "source_ids": ["annual_business"]},
            "sections": {key: dict(section) for key in (
                "industry_chain", "business_quality", "competitive_moat", "financial_quality", "valuation_debate", "risk_falsification"
            )},
            "investment_committee": {
                "bull_case": paragraph, "bear_case": paragraph, "base_case": paragraph, "decision": paragraph,
                "source_ids": ["annual_business"],
            },
        }

    def test_portfolio_invariants(self) -> None:
        payload = dashboard_payload(self.db_path)
        self.assertEqual(validate_invariants(payload), [])
        self.assertEqual(payload["allocation"]["total"], 100)
        self.assertEqual(len(payload["positions"]), 8)

    def test_committee_home_separates_model_observation_from_executable_research(self) -> None:
        self.promote_catl_fixture_to_real()
        payload = committee_payload(self.db_path)
        self.assertEqual(payload["validation_errors"], [])
        self.assertEqual(validate_committee_payload(payload), [])
        self.assertEqual(payload["metrics"]["stock_count"], 8)
        self.assertEqual(payload["metrics"]["deep_research_count"], 1)
        self.assertEqual(payload["metrics"]["baseline_count"], 7)
        self.assertEqual(payload["metrics"]["model_observation_equity"], 82)
        self.assertEqual(payload["metrics"]["decision_review_equity"], 0)
        self.assertEqual(payload["metrics"]["current_executable_equity"], 0)
        self.assertEqual(payload["metrics"]["research_pending_equity"], 82)
        catl = next(item for item in payload["items"] if item["ticker"] == "300750.SZ")
        self.assertIsNone(catl["decision_review_weight"])
        self.assertIsNone(catl["current_executable_weight"])
        self.assertTrue(all(
            item["current_executable_weight"] is None
            for item in payload["items"] if item["ticker"] != "300750.SZ"
        ))

    def test_committee_home_fails_closed_when_deep_company_evidence_is_missing(self) -> None:
        self.promote_catl_fixture_to_real(with_evidence=False)
        payload = committee_payload(self.db_path)
        catl = next(item for item in payload["items"] if item["ticker"] == "300750.SZ")
        self.assertEqual(payload["decision_status"], "blocked")
        self.assertEqual(catl["decision_state"], "blocked")
        self.assertIsNone(catl["current_executable_weight"])

    def test_publication_pack_manifest_detects_tampering(self) -> None:
        pack_dir = Path(self.tmpdir.name) / "pack_test"
        pack_dir.mkdir()
        payloads = {
            "report.html": b"<html><body>verified report</body></html>",
            "report-long.png": b"\x89PNG\r\n\x1a\nverified",
            "report.pdf": b"%PDF-1.4\nverified",
            "report.json": json.dumps({"ticker": "TSLA", "name": "Tesla, Inc.", "report_hash": "bad", "report_contract": {}}, separators=(",", ":")).encode(),
            "render-receipt.json": b"{}",
        }
        for name, body in payloads.items():
            (pack_dir / name).write_bytes(body)
        manifest = {
            "pack_id": pack_dir.name,
            "files": {name: hashlib.sha256(body).hexdigest() for name, body in payloads.items()},
        }
        (pack_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        initial_errors = validate_pack(pack_dir)
        self.assertTrue(any(error.startswith("report contract invalid:") for error in initial_errors))
        self.assertIn("report HTML content contract failed", initial_errors)
        self.assertIn("PDF structure or page count is invalid", initial_errors)
        self.assertIn("PNG structure or dimensions are invalid", initial_errors)
        (pack_dir / "report.json").write_bytes(b"tampered")
        self.assertIn("file hash mismatch: report.json", validate_pack(pack_dir))

    def test_publication_archive_must_be_a_readable_exact_copy(self) -> None:
        pack_dir = Path(self.tmpdir.name) / "pack_archive"
        pack_dir.mkdir()
        for name in (*ARTIFACT_NAMES, "manifest.json"):
            (pack_dir / name).write_bytes(f"valid-{name}".encode())
        archive = pack_dir.with_suffix(".zip")
        import zipfile
        with zipfile.ZipFile(archive, "w") as bundle:
            for name in (*ARTIFACT_NAMES, "manifest.json"):
                bundle.write(pack_dir / name, arcname=f"{pack_dir.name}/{name}")
        self.assertEqual(validate_archive(archive, pack_dir), [])
        archive.write_bytes(b"not-a-zip")
        self.assertIn("archive is unreadable", validate_archive(archive, pack_dir))

    def test_private_beta_invites_sessions_and_entitlements_fail_closed(self) -> None:
        owner = create_owner("park@example.com", "correct horse battery staple", "Park", self.db_path)
        self.assertIsNone(authenticate("park@example.com", "wrong password value", self.db_path))
        authenticated = authenticate("PARK@example.com", "correct horse battery staple", self.db_path)
        self.assertEqual(authenticated["id"], owner["id"])
        session = create_session(owner["id"], self.db_path)
        current = session_member(session["token"], self.db_path)
        self.assertEqual(current["role"], "owner")
        self.assertTrue(verify_csrf(current, session["csrf_token"]))
        self.assertFalse(verify_csrf(current, "forged-csrf-token"))
        with closing(connect(self.db_path)) as conn:
            stored = conn.execute("SELECT token_hash,csrf_hash FROM member_sessions WHERE member_id=?", (owner["id"],)).fetchone()
        self.assertNotEqual(stored["token_hash"], session["token"])
        self.assertNotEqual(stored["csrf_hash"], session["csrf_token"])

        invite = create_invite(owner["id"], "paid", self.db_path, max_uses=1, valid_days=3)
        member = redeem_invite(invite["code"], "friend@example.com", "another strong password", "Friend", self.db_path)
        self.assertTrue(has_entitlement(member, "publication_downloads"))
        self.assertFalse(has_entitlement(member, "approve_publication"))
        member_session = create_session(member["id"], self.db_path)
        self.assertEqual(len(list_members(owner["id"], self.db_path)), 2)
        suspended = set_member_status(owner["id"], "friend@example.com", "suspended", self.db_path)
        self.assertEqual(suspended["status"], "suspended")
        self.assertIsNone(session_member(member_session["token"], self.db_path))
        with self.assertRaisesRegex(ValueError, "invite is invalid"):
            redeem_invite(invite["code"], "second@example.com", "another strong password", "Second", self.db_path)

    def test_private_beta_allows_only_one_owner_under_concurrency(self) -> None:
        def attempt(index: int) -> bool:
            try:
                create_owner(f"owner{index}@example.com", "concurrent-owner-password", f"Owner {index}", self.db_path)
                return True
            except (ValueError, sqlite3.IntegrityError):
                return False

        with ThreadPoolExecutor(max_workers=6) as pool:
            outcomes = list(pool.map(attempt, range(6)))
        self.assertEqual(outcomes.count(True), 1)
        with closing(connect(self.db_path)) as conn:
            count = conn.execute("SELECT COUNT(*) FROM members WHERE role='owner' AND status='active'").fetchone()[0]
        self.assertEqual(count, 1)

    def test_single_use_access_code_creates_guest_without_collecting_identity(self) -> None:
        owner = create_owner("park@example.com", "correct horse battery staple", "Park", self.db_path)
        access = create_invite(owner["id"], "member", self.db_path, max_uses=1, valid_days=2)
        guest = redeem_access_code(access["code"], self.db_path)
        self.assertTrue(guest["email"].endswith("@access.invalid"))
        self.assertTrue(guest["display_name"].startswith("访客 "))
        self.assertTrue(has_entitlement(guest, "deep_reports"))
        self.assertIsNone(authenticate(guest["email"], "not-a-real-password", self.db_path))
        with self.assertRaisesRegex(ValueError, "access code is invalid"):
            redeem_access_code(access["code"], self.db_path)

        shared = create_invite(owner["id"], "preview", self.db_path, max_uses=2, valid_days=2)
        with self.assertRaisesRegex(ValueError, "access code is invalid"):
            redeem_access_code(shared["code"], self.db_path)

    def test_demo_mode_is_explicit(self) -> None:
        payload = dashboard_payload(self.db_path)
        self.assertEqual(payload["snapshot"]["data_mode"], "DEMO")
        self.assertEqual(payload["snapshot"]["quality_status"], "degraded")
        self.assertIn("not live market data", payload["snapshot"]["source_summary"])

    def test_stock_detail_has_evidence(self) -> None:
        stock = stock_payload("600519.SH", self.db_path)
        self.assertIsNotNone(stock)
        assert stock is not None
        self.assertEqual(stock["name"], "贵州茅台")
        self.assertEqual({row["evidence_type"] for row in stock["evidence"]}, {"fact", "inference", "risk"})

    def test_unknown_stock_returns_none(self) -> None:
        self.assertIsNone(stock_payload("000000.SZ", self.db_path))

    def test_catl_deep_report_is_traceable_and_math_is_auditable(self) -> None:
        self.promote_catl_fixture_to_real()
        report = report_payload("300750.SZ", self.db_path)
        self.assertIsNotNone(report)
        assert report is not None
        self.assertEqual(report["research_status"], "verified")
        self.assertGreaterEqual(report["evidence_summary"]["document_count"], 7)
        self.assertGreaterEqual(report["evidence_summary"]["independent_document_count"], 2)
        self.assertEqual(report["executive"]["target_weight"], 8)
        self.assertEqual(sum(item["weight"] for item in report["executive"]["position_plan"]), 8)
        self.assertEqual([item["weight"] for item in report["executive"]["position_plan"]], [4, 2, 2])
        self.assertAlmostEqual(report["serenity"]["final_score"], report["serenity"]["raw_score"] - report["serenity"]["penalty"])
        for scenario in report["valuation"]["scenarios"]:
            self.assertAlmostEqual(scenario["target_price"], scenario["eps"] * scenario["pe"])
        self.assertEqual(len(report["serenity"]["penalties"]), 8)
        self.assertEqual(sum(item["weight"] for item in report["serenity"]["factors"]), 100)
        self.assertEqual(len(report["report_hash"]), 64)
        self.assertEqual(report["report_contract"]["schema_version"], "research-report-v1")
        self.assertEqual(validate_report_contract(report["report_contract"], report), [])
        self.assertEqual(
            [item["order"] for item in report["report_contract"]["module_manifest"]],
            list(range(1, 9)),
        )
        source_ids = {source["id"] for source in report["sources"]}
        for section in (report["thesis"], report["catalysts"], report["risks"]):
            for item in section:
                self.assertTrue(set(item["source_ids"]).issubset(source_ids))

    def test_final_api_payload_is_revalidated_after_version_diff_is_added(self) -> None:
        self.promote_catl_fixture_to_real()
        with patch("report_versions.latest_report_diff", return_value={"status": "tampered"}):
            with self.assertRaisesRegex(ReportContractError, "final report payload rejected"):
                report_payload("300750.SZ", self.db_path)

    def test_valid_deepseek_artifact_is_bound_to_snapshot_and_report(self) -> None:
        self.promote_catl_fixture_to_real()
        deterministic = report_payload("300750.SZ", self.db_path)
        assert deterministic is not None
        evidence_set, evidence_hash = self.catl_artifact_binding(deterministic)
        with closing(connect(self.db_path)) as conn:
            approval_before = publication_content_hash(conn, "pub_demo_2026w29")
        narrative = self.valid_narrative()
        narrative_hash = hashlib.sha256(json.dumps(narrative, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        target = artifact_path(self.db_path, "300750.SZ", "snap_demo_20260717_v1")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({
            "artifact_version": "deepseek-narrative-v1",
            "validation_version": "metric-source-v2",
            "prompt_version": "deepseek-equity-writer-v1",
            "provider": "DeepSeek",
            "model": "deepseek-v4-pro",
            "generated_at": "2026-07-17T12:00:00+00:00",
            "ticker": "300750.SZ",
            "snapshot_id": "snap_demo_20260717_v1",
            "profile_hash": research_profile_hash(),
            "research_logic_hash": research_logic_hash(), "writer_logic_hash": writer_logic_hash(),
            "evidence_set_id": evidence_set["evidence_set_id"],
            "evidence_manifest_hash": evidence_set["manifest_hash"],
            "evidence_hash": evidence_hash,
            "narrative_hash": narrative_hash,
            "editorial_approval": {"status": "approved", "approval_version": "human-editorial-v1", "narrative_hash": narrative_hash, "evidence_manifest_hash": evidence_set["manifest_hash"], "approved_by": "test reviewer"},
            "validation": {"status": "passed", "errors": [], "numeric_warnings": [], "cited_source_count": 1, "available_source_count": 1},
            "narrative": narrative,
        }, ensure_ascii=False), encoding="utf-8")
        report = report_payload("300750.SZ", self.db_path)
        assert report is not None
        self.assertEqual(report["ai_narrative"]["report_title"], "宁德时代深度研究测试稿")
        self.assertEqual(report["narrative_provider"]["model"], "deepseek-v4-pro")
        self.assertEqual(len(report["narrative_provider"]["artifact_hash"]), 64)
        with closing(connect(self.db_path)) as conn:
            approval_after = publication_content_hash(conn, "pub_demo_2026w29")
        self.assertNotEqual(approval_before, approval_after)
        stale = json.loads(target.read_text(encoding="utf-8"))
        stale["writer_logic_hash"] = "stale-writer-logic"
        target.write_text(json.dumps(stale, ensure_ascii=False), encoding="utf-8")
        self.assertNotIn("ai_narrative", report_payload("300750.SZ", self.db_path))

    def test_model_authored_position_is_never_exposed(self) -> None:
        self.promote_catl_fixture_to_real()
        deterministic = report_payload("300750.SZ", self.db_path)
        assert deterministic is not None
        narrative = self.valid_narrative()
        narrative["position_conclusion"] = {
            "action": "立即清仓，永久回避", "reasoning": "模型越权", "conditions": ["清仓"], "source_ids": ["annual_business"]
        }
        evidence_set, evidence_hash = self.catl_artifact_binding(deterministic)
        write_artifact(self.db_path, "300750.SZ", "snap_demo_20260717_v1", {
            "artifact_version": "deepseek-narrative-v1", "validation_version": "metric-source-v2", "prompt_version": "deepseek-equity-writer-v1",
            "provider": "DeepSeek", "model": "deepseek-v4-pro", "generated_at": "2026-07-17T12:00:00+00:00",
            "ticker": "300750.SZ", "snapshot_id": "snap_demo_20260717_v1",
            "profile_hash": research_profile_hash(), "research_logic_hash": research_logic_hash(), "writer_logic_hash": writer_logic_hash(),
            "evidence_set_id": evidence_set["evidence_set_id"], "evidence_manifest_hash": evidence_set["manifest_hash"],
            "evidence_hash": evidence_hash,
            "narrative_hash": hashlib.sha256(json.dumps(narrative, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
            "editorial_approval": {"status": "approved", "approval_version": "human-editorial-v1", "narrative_hash": hashlib.sha256(json.dumps(narrative, ensure_ascii=False, sort_keys=True).encode()).hexdigest(), "evidence_manifest_hash": evidence_set["manifest_hash"], "approved_by": "test reviewer"},
            "validation": {"status": "passed", "errors": [], "numeric_warnings": []}, "narrative": narrative,
        })
        report = report_payload("300750.SZ", self.db_path)
        assert report is not None
        self.assertNotIn("ai_narrative", report)
        self.assertEqual(report["executive"]["proposed_initial_weight"], 4)
        self.assertIsNone(report["executive"]["decision_review_weight"])
        self.assertIsNone(report["executive"]["current_executable_weight"])
        self.assertEqual(report["executive"]["max_target_weight"], 8)

    def test_numeric_validator_preserves_sign_and_excludes_source_page_numbers(self) -> None:
        self.promote_catl_fixture_to_real()
        report = report_payload("300750.SZ", self.db_path)
        assert report is not None
        evidence = build_evidence_pack(report)
        wrong_sign = self.valid_narrative()
        wrong_sign["sections"]["business_quality"]["paragraphs"][0] += "收入增长 +23.83%。"
        wrong_sign["sections"]["business_quality"]["source_ids"] = ["annual_segments"]
        result = validate_narrative(wrong_sign, evidence)
        self.assertEqual(result["status"], "needs_review")
        self.assertTrue(any("+23.83%" in warning for warning in result["numeric_warnings"]))

        page_number = self.valid_narrative()
        page_number["sections"]["financial_quality"]["paragraphs"][0] += "收入增长 42%。"
        page_number["sections"]["financial_quality"]["source_ids"] = ["annual_risks"]
        result = validate_narrative(page_number, evidence)
        self.assertEqual(result["status"], "needs_review")
        self.assertTrue(any("42%" in warning for warning in result["numeric_warnings"]))

    def test_evidence_change_deactivates_old_ai_artifact(self) -> None:
        self.promote_catl_fixture_to_real()
        deterministic = report_payload("300750.SZ", self.db_path)
        assert deterministic is not None
        narrative = self.valid_narrative()
        evidence_set, evidence_hash = self.catl_artifact_binding(deterministic)
        write_artifact(self.db_path, "300750.SZ", "snap_demo_20260717_v1", {
            "artifact_version": "deepseek-narrative-v1", "validation_version": "metric-source-v2", "prompt_version": "deepseek-equity-writer-v1",
            "provider": "DeepSeek", "model": "deepseek-v4-pro", "generated_at": "2026-07-17T12:00:00+00:00",
            "ticker": "300750.SZ", "snapshot_id": "snap_demo_20260717_v1",
            "profile_hash": research_profile_hash(), "research_logic_hash": research_logic_hash(), "writer_logic_hash": writer_logic_hash(),
            "evidence_set_id": evidence_set["evidence_set_id"], "evidence_manifest_hash": evidence_set["manifest_hash"],
            "evidence_hash": evidence_hash,
            "narrative_hash": hashlib.sha256(json.dumps(narrative, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
            "editorial_approval": {"status": "approved", "approval_version": "human-editorial-v1", "narrative_hash": hashlib.sha256(json.dumps(narrative, ensure_ascii=False, sort_keys=True).encode()).hexdigest(), "evidence_manifest_hash": evidence_set["manifest_hash"], "approved_by": "test reviewer"},
            "validation": {"status": "passed", "errors": [], "numeric_warnings": []}, "narrative": narrative,
        })
        approved_report = report_payload("300750.SZ", self.db_path)
        self.assertIn("ai_narrative", approved_report)
        self.assertEqual(approved_report["executive"]["decision_review_weight"], 4)
        self.assertIsNone(approved_report["executive"]["current_executable_weight"])
        with closing(connect(self.db_path)) as conn:
            conn.execute("UPDATE market_quotes SET price=460 WHERE snapshot_id='snap_demo_20260717_v1' AND ticker='300750.SZ'")
            conn.commit()
        self.assertNotIn("ai_narrative", report_payload("300750.SZ", self.db_path))

    def test_unapproved_model_execution_synonyms_never_reach_public_report(self) -> None:
        self.promote_catl_fixture_to_real()
        deterministic = report_payload("300750.SZ", self.db_path)
        assert deterministic is not None
        narrative = self.valid_narrative()
        narrative["executive_summary"]["conclusion"] = "建议扩大风险敞口并立即执行"
        evidence_set, _ = self.catl_artifact_binding(deterministic)
        evidence = build_evidence_pack(deterministic, evidence_set)
        validation = validate_narrative(narrative, evidence)
        self.assertEqual(validation["status"], "passed")
        narrative_hash = hashlib.sha256(json.dumps(narrative, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        write_artifact(self.db_path, "300750.SZ", "snap_demo_20260717_v1", {
            "artifact_version": "deepseek-narrative-v3", "validation_version": "metric-source-v2", "prompt_version": "deepseek-equity-writer-v1",
            "provider": "DeepSeek", "model": "deepseek-v4-pro", "generated_at": "2026-07-17T12:00:00+00:00",
            "ticker": "300750.SZ", "snapshot_id": "snap_demo_20260717_v1",
            "profile_hash": research_profile_hash(), "research_logic_hash": research_logic_hash(), "writer_logic_hash": writer_logic_hash(),
            "evidence_set_id": evidence_set["evidence_set_id"], "evidence_manifest_hash": evidence_set["manifest_hash"],
            "evidence_hash": hashlib.sha256(json.dumps(evidence, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest(),
            "narrative_hash": narrative_hash, "validation": validation,
            "editorial_approval": {"status": "pending", "reason": "independent review required"}, "narrative": narrative,
        })
        report = report_payload("300750.SZ", self.db_path)
        assert report is not None
        self.assertNotIn("ai_narrative", report)

    def test_ai_prose_cannot_reassign_a_real_number_to_the_wrong_metric(self) -> None:
        self.promote_catl_fixture_to_real()
        report = report_payload("300750.SZ", self.db_path)
        assert report is not None
        narrative = self.valid_narrative()
        narrative["sections"]["financial_quality"]["paragraphs"][0] += "归母净利润同比增长 17.0%。"
        narrative["sections"]["financial_quality"]["source_ids"] = ["annual_financials"]
        result = validate_narrative(narrative, build_evidence_pack(report))
        self.assertEqual(result["status"], "needs_review")
        self.assertTrue(any("17.0%" in warning for warning in result["numeric_warnings"]))

    def test_corrupt_ai_artifact_never_breaks_deterministic_report(self) -> None:
        self.promote_catl_fixture_to_real()
        target = artifact_path(self.db_path, "300750.SZ", "snap_demo_20260717_v1")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('{"truncated":', encoding="utf-8")
        self.assertIsNone(load_artifact(self.db_path, "300750.SZ", "snap_demo_20260717_v1"))
        report = report_payload("300750.SZ", self.db_path)
        assert report is not None
        self.assertEqual(report["research_status"], "verified")
        self.assertNotIn("ai_narrative", report)

    def test_unknown_ai_fields_cannot_be_approved_or_take_down_base_report(self) -> None:
        self.promote_catl_fixture_to_real()
        deterministic = report_payload("300750.SZ", self.db_path)
        assert deterministic is not None
        evidence_set, evidence_hash = self.catl_artifact_binding(deterministic)
        narrative = self.valid_narrative()
        narrative["harmless_extra"] = "editor note"
        narrative["sections"]["business_quality"]["nested_extra"] = {"note": "not contracted"}
        validation = validate_narrative(narrative, build_evidence_pack(deterministic, evidence_set))
        self.assertEqual(validation["status"], "needs_review")
        self.assertTrue(any("public narrative schema" in error for error in validation["errors"]))
        narrative_hash = hashlib.sha256(json.dumps(narrative, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        artifact = {
            "artifact_version": "deepseek-narrative-v1", "validation_version": "metric-source-v2",
            "prompt_version": "deepseek-equity-writer-v1", "provider": "DeepSeek", "model": "test-model",
            "generated_at": "2026-07-17T12:00:00+00:00", "ticker": "300750.SZ", "snapshot_id": "snap_demo_20260717_v1",
            "profile_hash": research_profile_hash(), "research_logic_hash": research_logic_hash(), "writer_logic_hash": writer_logic_hash(),
            "evidence_set_id": evidence_set["evidence_set_id"], "evidence_manifest_hash": evidence_set["manifest_hash"],
            "evidence_hash": evidence_hash, "narrative_hash": narrative_hash, "validation": {"status": "passed"},
            "editorial_approval": {"status": "pending"}, "receipts": [], "narrative": narrative,
        }
        write_artifact(self.db_path, "300750.SZ", "snap_demo_20260717_v1", artifact)
        with self.assertRaisesRegex(RuntimeError, "narrative validation is not passed"):
            approve_artifact(
                "300750.SZ", self.db_path, reviewer="independent editor",
                expected_narrative_hash=narrative_hash,
                expected_evidence_manifest_hash=evidence_set["manifest_hash"],
            )
        artifact["editorial_approval"] = {
            "status": "approved", "approval_version": "human-editorial-v1", "approved_by": "legacy editor",
            "narrative_hash": narrative_hash, "evidence_manifest_hash": evidence_set["manifest_hash"],
        }
        write_artifact(self.db_path, "300750.SZ", "snap_demo_20260717_v1", artifact)
        safe_report = report_payload("300750.SZ", self.db_path)
        assert safe_report is not None
        self.assertEqual(safe_report["research_status"], "verified")
        self.assertNotIn("ai_narrative", safe_report)
        for invalid_narrative in ("not-an-object", ["not-an-object"], None):
            artifact["narrative"] = invalid_narrative
            artifact["narrative_hash"] = None
            artifact["editorial_approval"]["narrative_hash"] = None
            write_artifact(self.db_path, "300750.SZ", "snap_demo_20260717_v1", artifact)
            safe_report = report_payload("300750.SZ", self.db_path)
            assert safe_report is not None
            self.assertEqual(safe_report["research_status"], "verified")
            self.assertNotIn("ai_narrative", safe_report)

    def test_report_versions_are_immutable_and_diff_key_inputs(self) -> None:
        self.promote_catl_fixture_to_real()
        baseline = report_payload("300750.SZ", self.db_path)
        assert baseline is not None
        archived = archive_report(baseline, self.db_path)
        changed_same_snapshot = copy.deepcopy(baseline)
        changed_same_snapshot["market"]["price"] = 999
        with self.assertRaisesRegex(ValueError, "report_hash"):
            archive_report(changed_same_snapshot, self.db_path)
        changed_same_snapshot.pop("update_diff", None)
        changed_same_snapshot.pop("report_hash", None)
        changed_same_snapshot["report_hash"] = research_reports._report_hash(changed_same_snapshot)
        changed_archive = archive_report(changed_same_snapshot, self.db_path)
        self.assertNotEqual(changed_archive["report_hash"], archived["report_hash"])
        self.assertEqual(len(report_version_history("300750.SZ", self.db_path)), 2)

        current = copy.deepcopy(baseline)
        current["generated_from"]["snapshot_id"] = "snap_next"
        current["market"]["price"] = float(baseline["market"]["price"]) + 10
        current["financials"]["series"][0]["revenue_yoy"] = float(baseline["financials"]["series"][0]["revenue_yoy"]) + 5
        diff = compare_reports(current, baseline)
        self.assertEqual(diff["status"], "changed")
        self.assertEqual(diff["previous_snapshot_id"], baseline["generated_from"]["snapshot_id"])
        self.assertEqual({item["label"] for item in diff["changes"]}, {"参考价", "最新收入增速"})

    def test_refresh_reuses_identical_snapshot_without_duplicate_report(self) -> None:
        self.promote_catl_fixture_to_real()
        result = run_refresh(
            self.db_path,
            builder=lambda _db, timeout: {
                "snapshot_id": "snap_demo_20260717_v1", "publication_id": "pub_demo_2026w29", "reused": True
            },
        )
        self.assertEqual(result["status"], "reused")
        self.assertTrue(result["reused"])
        self.assertEqual(len(report_version_history("300750.SZ", self.db_path)), 1)
        receipt = refresh_status(self.db_path)["runs"][0]
        self.assertEqual(receipt["status"], "reused")
        with closing(connect(self.db_path)) as conn:
            expected_manifest = conn.execute(
                "SELECT manifest_hash FROM dataset_snapshots WHERE id='snap_demo_20260717_v1'"
            ).fetchone()["manifest_hash"]
        self.assertEqual(receipt["manifest_hash"], expected_manifest)

    def test_refresh_retries_one_transient_collection_failure(self) -> None:
        self.promote_catl_fixture_to_real()
        calls = []

        def transient(_db, timeout):
            calls.append(1)
            if len(calls) == 1:
                raise TimeoutError("temporary timeout")
            return {"snapshot_id": "snap_demo_20260717_v1", "publication_id": "pub_demo_2026w29", "reused": True}

        result = run_refresh(self.db_path, builder=transient)
        self.assertEqual(result["status"], "reused")
        self.assertEqual(len(calls), 2)

    def test_failed_refresh_preserves_previous_snapshot_and_records_receipt(self) -> None:
        self.promote_catl_fixture_to_real()
        before = dashboard_payload(self.db_path)["snapshot"]["id"]

        def fail(_db, timeout):
            raise RuntimeError("upstream unavailable")

        with self.assertRaisesRegex(RuntimeError, "previous snapshot preserved"):
            run_refresh(self.db_path, builder=fail)
        after = dashboard_payload(self.db_path)["snapshot"]["id"]
        self.assertEqual(after, before)
        receipt = refresh_status(self.db_path)["runs"][0]
        self.assertEqual(receipt["status"], "failed")
        self.assertIn("upstream unavailable", receipt["error_summary"])

    def test_failure_after_partial_snapshot_write_is_quarantined(self) -> None:
        self.promote_catl_fixture_to_real()
        previous_snapshot = dashboard_payload(self.db_path)["snapshot"]["id"]

        def partial_then_fail(db_path, timeout):
            with closing(connect(db_path)) as conn:
                conn.execute(
                    "INSERT INTO dataset_snapshots VALUES (?, 'REAL', ?, ?, 'passed', ?, ?, ?)",
                    (
                        "snap_partial_attack",
                        "2026-07-18",
                        "2026-07-18T08:00:00+00:00",
                        "incomplete injected refresh",
                        "partial-manifest",
                        "2026-07-18T08:00:00+00:00",
                    ),
                )
                conn.execute(
                    """INSERT INTO publications (
                        id, snapshot_id, status, title, market_regime, regime_note,
                        equity_weight, cash_weight, model_version, blocked_reason
                    ) VALUES (?, ?, 'quality_passed', ?, ?, ?, ?, ?, ?, NULL)""",
                    (
                        "pub_partial_attack",
                        "snap_partial_attack",
                        "should never be visible",
                        "unknown",
                        "incomplete",
                        0,
                        100,
                        "attack-test",
                    ),
                )
                conn.commit()
            raise RuntimeError("post-write failure")

        with self.assertRaisesRegex(RuntimeError, "previous snapshot preserved"):
            run_refresh(self.db_path, builder=partial_then_fail)

        self.assertEqual(dashboard_payload(self.db_path)["snapshot"]["id"], previous_snapshot)
        with closing(connect(self.db_path)) as conn:
            snapshot_status = conn.execute(
                "SELECT quality_status FROM dataset_snapshots WHERE id='snap_partial_attack'"
            ).fetchone()["quality_status"]
            publication_status = conn.execute(
                "SELECT status FROM publications WHERE id='pub_partial_attack'"
            ).fetchone()["status"]
        self.assertEqual(snapshot_status, "blocked")
        self.assertEqual(publication_status, "blocked")
        replay = replay_snapshot("snap_partial_attack", self.db_path)
        self.assertEqual(replay["status"], "failed")
        self.assertEqual(replay["replayed_tickers"], 0)

    def test_invalidated_real_publication_is_not_active(self) -> None:
        self.promote_catl_fixture_to_real()
        with closing(connect(self.db_path)) as conn:
            conn.execute("UPDATE publications SET status='invalidated' WHERE id='pub_demo_2026w29'")
            conn.commit()
        with self.assertRaisesRegex(RuntimeError, "No portfolio publication"):
            dashboard_payload(self.db_path)
        self.assertIsNone(stock_payload("300750.SZ", self.db_path))

    def test_refresh_result_must_match_active_dashboard_identity(self) -> None:
        self.promote_catl_fixture_to_real()
        before = dashboard_payload(self.db_path)["snapshot"]["id"]
        with self.assertRaisesRegex(RuntimeError, "previous snapshot preserved"):
            run_refresh(
                self.db_path,
                builder=lambda _db, timeout: {
                    "snapshot_id": "snap_wrong_identity",
                    "publication_id": "pub_demo_2026w29",
                    "reused": True,
                },
            )
        self.assertEqual(dashboard_payload(self.db_path)["snapshot"]["id"], before)
        self.assertEqual(refresh_status(self.db_path)["runs"][0]["status"], "failed")

    def test_refresh_is_serialized_across_process_lock_boundary(self) -> None:
        self.promote_catl_fixture_to_real()
        with _process_refresh_lock(self.db_path):
            with self.assertRaises(RefreshInProgressError):
                run_refresh(
                    self.db_path,
                    builder=lambda _db, timeout: {
                        "snapshot_id": "snap_demo_20260717_v1",
                        "publication_id": "pub_demo_2026w29",
                        "reused": True,
                    },
                )

    def test_stale_quote_or_bar_alignment_blocks_verified_report(self) -> None:
        self.promote_catl_fixture_to_real()
        with closing(connect(self.db_path)) as conn:
            conn.execute(
                "UPDATE market_quotes SET quote_time='2026-06-17T15:00:00+08:00' WHERE snapshot_id='snap_demo_20260717_v1' AND ticker='300750.SZ'"
            )
            conn.commit()
        report = report_payload("300750.SZ", self.db_path)
        assert report is not None
        self.assertEqual(report["research_status"], "unverified")
        self.assertIn("portfolio data freshness or point-in-time alignment failed", report["available"]["gate_failures"])
        with self.assertRaisesRegex(ValueError, "freshness"):
            transition_publication("pub_demo_2026w29", "approve", self.db_path)

    def test_replay_rejects_rows_not_marked_accepted(self) -> None:
        self.promote_catl_fixture_to_real()
        with closing(connect(self.db_path)) as conn:
            conn.execute(
                "UPDATE market_quotes SET quality_status='rejected' WHERE snapshot_id='snap_demo_20260717_v1' AND ticker='300750.SZ'"
            )
            conn.commit()
        replay = replay_snapshot("snap_demo_20260717_v1", self.db_path)
        self.assertEqual(replay["status"], "failed")
        self.assertIn("300750.SZ: stored input incomplete", replay["errors"])

    def test_future_research_source_blocks_report_and_release(self) -> None:
        self.promote_catl_fixture_to_real()
        source = CATL_PROFILE["sources"][0]
        original = source["known_at"]
        source["known_at"] = "2099-01-01"
        try:
            report = report_payload("300750.SZ", self.db_path)
            assert report is not None
            self.assertEqual(report["research_status"], "unverified")
            self.assertIn("research source is newer than the snapshot knowledge boundary", report["available"]["gate_failures"])
            with self.assertRaisesRegex(ValueError, "research source"):
                transition_publication("pub_demo_2026w29", "approve", self.db_path)
        finally:
            source["known_at"] = original

    def test_future_evidence_ledger_entry_blocks_release_and_is_hidden(self) -> None:
        self.promote_catl_fixture_to_real()
        with closing(connect(self.db_path)) as conn:
            conn.execute(
                "UPDATE evidence SET known_at='2099-01-01' WHERE publication_id='pub_demo_2026w29' AND ticker='300750.SZ' AND label='组合目标仓位'"
            )
            conn.commit()
        stock = stock_payload("300750.SZ", self.db_path)
        assert stock is not None
        self.assertFalse(any(item["label"] == "组合目标仓位" for item in stock["evidence"]))
        with self.assertRaisesRegex(ValueError, "evidence ledger"):
            transition_publication("pub_demo_2026w29", "approve", self.db_path)

    def test_rejected_evidence_ledger_entry_blocks_release_and_is_hidden(self) -> None:
        self.promote_catl_fixture_to_real()
        with closing(connect(self.db_path)) as conn:
            conn.execute(
                "UPDATE evidence SET quality_status='rejected' WHERE publication_id='pub_demo_2026w29' AND ticker='300750.SZ' AND label='组合目标仓位'"
            )
            conn.commit()
        stock = stock_payload("300750.SZ", self.db_path)
        assert stock is not None
        self.assertFalse(any(item["label"] == "组合目标仓位" for item in stock["evidence"]))
        with self.assertRaisesRegex(ValueError, "evidence ledger"):
            transition_publication("pub_demo_2026w29", "approve", self.db_path)

    def test_demo_snapshot_cannot_emit_verified_catl_conclusions(self) -> None:
        report = report_payload("300750.SZ", self.db_path)
        assert report is not None
        self.assertEqual(report["research_status"], "unverified")
        self.assertNotIn("valuation", report)
        self.assertNotIn("executive", report)
        self.assertNotIn("target_weight", report["available"]["stock"])
        self.assertNotIn("reference_price", report["available"]["stock"])

    def test_relabelled_empty_snapshot_still_fails_research_gate(self) -> None:
        with closing(connect(self.db_path)) as conn:
            snapshot_id = "snap_demo_20260717_v1"
            conn.execute("UPDATE dataset_snapshots SET data_mode='REAL', quality_status='passed' WHERE id=?", (snapshot_id,))
            conn.execute("UPDATE publications SET status='quality_passed' WHERE id='pub_demo_2026w29'")
            conn.execute(
                "INSERT INTO market_quotes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (snapshot_id, "300750.SZ", "宁德时代", 360, 0, 360, 360, None, None, None, None, "", "", "", "", "", "rejected"),
            )
            conn.execute(
                "INSERT INTO stock_features VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (snapshot_id, "300750.SZ", None, None, None, None, None, None, None, None, None, 0, 0, 0, 0, 0, 1, ""),
            )
            conn.execute(
                "INSERT INTO financial_metrics VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (snapshot_id, "300750.SZ", "2025-12-31", "", "", None, None, None, None, None, None, None, None, None, "", "", "rejected"),
            )
            conn.commit()
        report = report_payload("300750.SZ", self.db_path)
        assert report is not None
        self.assertEqual(report["research_status"], "unverified")
        self.assertGreaterEqual(len(report["available"]["gate_failures"]), 5)

    def test_shifted_coverage_between_tickers_still_fails_gate(self) -> None:
        self.promote_catl_fixture_to_real()
        with closing(connect(self.db_path)) as conn:
            snapshot_id = "snap_demo_20260717_v1"
            conn.execute("DELETE FROM daily_bars WHERE snapshot_id=? AND ticker='600519.SH'", (snapshot_id,))
            conn.executemany(
                "INSERT INTO daily_bars VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [(snapshot_id, "600036.SH", f"extra{day:03d}", 100, 100, 101, 99, 100000, "tencent_qfq_daily", "extra-bars", "accepted") for day in range(250)],
            )
            conn.execute("DELETE FROM financial_metrics WHERE snapshot_id=? AND ticker='600519.SH'", (snapshot_id,))
            conn.execute(
                "INSERT INTO financial_metrics VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (snapshot_id, "600036.SH", "2024-12-31", "2025-03-10", "年报", 100e8, 10e8, 5, 5, 10, 30, 10, 40, 1, "eastmoney_f10_main", "extra-fin", "accepted"),
            )
            conn.commit()
        report = report_payload("300750.SZ", self.db_path)
        assert report is not None
        self.assertEqual(report["research_status"], "unverified")
        self.assertIn("one or more portfolio tickers fail per-ticker coverage", report["available"]["gate_failures"])

    def test_non_sample_stock_is_blocked_until_real_gate_passes(self) -> None:
        report = report_payload("600519.SH", self.db_path)
        self.assertIsNotNone(report)
        assert report is not None
        self.assertEqual(report["research_status"], "unverified")
        self.assertIn("missing_modules", report["available"])

    def test_all_eight_real_stocks_have_auditable_research_reports(self) -> None:
        self.promote_catl_fixture_to_real()
        reports = {item["ticker"]: report_payload(item["ticker"], self.db_path) for item in DEMO_POSITIONS}
        self.assertEqual(len(reports), 8)
        self.assertEqual(reports["300750.SZ"]["research_status"], "verified")
        self.assertEqual(reports["300750.SZ"]["research_depth"], "deep")
        baselines = [report for ticker, report in reports.items() if ticker != "300750.SZ"]
        self.assertTrue(all(report["research_depth"] == "quantitative_baseline" for report in baselines))
        self.assertTrue(all(report["research_status"] == "baseline" and report["data_status"] == "verified" for report in baselines))
        self.assertTrue(all("depth_disclosure" in report for report in baselines))
        for report in reports.values():
            source_ids = {source["id"] for source in report["sources"]}
            for section in (report["thesis"], report["catalysts"], report["risks"]):
                for item in section:
                    self.assertTrue(set(item["source_ids"]).issubset(source_ids))

    def test_quantitative_baseline_does_not_impersonate_valuation_moat_or_execution_contract(self) -> None:
        self.promote_catl_fixture_to_real()
        report = report_payload("600519.SH", self.db_path)
        assert report is not None
        self.assertEqual(report["research_status"], "baseline")
        self.assertEqual(report["data_status"], "verified")
        self.assertIsNone(report["executive"]["target_weight"])
        self.assertEqual(report["executive"]["action"], "research_only")
        self.assertIsNone(report["executive"]["current_executable_weight"])
        self.assertEqual(report["executive"]["weight_semantics"], "model_observation_only")
        visible_contract = json.dumps({"title": report["title"], "executive": report["executive"], "thesis": report["thesis"]}, ensure_ascii=False)
        self.assertNotIn("条件目标仓位", visible_contract)
        self.assertNotIn("持有", visible_contract)
        self.assertEqual(report["moat"], [])
        self.assertEqual(len(report["quant_signals"]), 4)
        self.assertEqual(report["valuation"]["status"], "pending_company_research")
        self.assertEqual(report["report_contract"]["identity"]["currency"], "CNY")
        states = {item["id"]: item["status"] for item in report["report_contract"]["module_manifest"]}
        self.assertEqual(states["business_and_industry"], "missing_evidence")
        self.assertEqual(states["valuation"], "missing_evidence")
        self.assertEqual(validate_report_contract(report["report_contract"], report), [])
        for scenario in report["stress_test"]["scenarios"]:
            self.assertNotIn("eps", scenario)
            self.assertNotIn("pe", scenario)
            self.assertNotIn("target_price", scenario)
            self.assertAlmostEqual(scenario["stress_price"], scenario["price_basis"] * scenario["stress_multiple"])

    def test_company_evidence_gate_requires_primary_and_independent_documents(self) -> None:
        self.promote_catl_fixture_to_real()
        sync_profile_sources("300750.SZ", [{
            "id": "future_release", "document_id": "future_release", "title": "未来公告",
            "kind": "company_release", "strength": "强", "known_at": "2026-07-18",
            "url": "https://example.test/future",
        }], self.db_path)
        receipt = self.sync_captured("300750.SZ", CATL_PROFILE["sources"], observed_at="2026-07-17T14:00:00+08:00")
        self.assertGreaterEqual(receipt["document_count"], 6)
        evidence_set = build_evidence_set("300750.SZ", "snap_demo_20260717_v1", self.db_path)
        self.assertEqual(evidence_set["status"], "passed")
        self.assertGreaterEqual(evidence_set["gate"]["primary_document_count"], 2)
        self.assertGreaterEqual(evidence_set["gate"]["independent_document_count"], 1)
        self.assertTrue(all(item["published_at"] <= "2026-07-17T15:00:00+08:00" for item in evidence_set["documents"]))
        self.assertNotIn("未来公告", {item["title"] for item in evidence_set["documents"]})

    def test_deep_report_and_publication_approval_fail_closed_without_evidence_set(self) -> None:
        self.promote_catl_fixture_to_real(with_evidence=False)
        report = report_payload("300750.SZ", self.db_path)
        assert report is not None
        self.assertEqual(report["research_status"], "unverified")
        self.assertNotIn("executive", report)
        self.assertNotIn("valuation", report)
        with self.assertRaisesRegex(ValueError, "evidence set"):
            transition_publication("pub_demo_2026w29", "approve", self.db_path)

    def test_publication_approval_hash_directly_binds_evidence_manifest(self) -> None:
        self.promote_catl_fixture_to_real(with_evidence=False)
        with closing(connect(self.db_path)) as conn:
            before = publication_content_hash(conn, "pub_demo_2026w29")
        self.sync_captured("300750.SZ", CATL_PROFILE["sources"], observed_at="2026-07-17T14:00:00+08:00")
        build_evidence_set("300750.SZ", "snap_demo_20260717_v1", self.db_path)
        with closing(connect(self.db_path)) as conn:
            after = publication_content_hash(conn, "pub_demo_2026w29")
        self.assertNotEqual(before, after)

    def test_uzi_dimensions_are_stored_as_leads_and_cannot_pass_company_evidence_gate(self) -> None:
        self.promote_catl_fixture_to_real()
        raw_path = Path(self.tmpdir.name) / "raw_data.json"
        raw_path.write_text(json.dumps({
            "ticker": "600519.SH", "full": "600519.SH", "dimensions": {
                "0_basic": {
                    "data": {"name": "贵州茅台", "notice_date": "2026-04-01", "url": "https://example.test/source"},
                    "source": "akshare:stock_individual_info_em", "fallback": False,
                    "_pipeline": {"dim_key": "0_basic", "quality": "full", "data_gaps": []},
                },
                "10_valuation": {
                    "data": {}, "source": "unknown", "fallback": True,
                    "_pipeline": {"dim_key": "10_valuation", "quality": "missing", "data_gaps": ["pe"]},
                },
            },
        }, ensure_ascii=False), encoding="utf-8")
        receipt = import_uzi_raw(raw_path, self.db_path)
        self.assertEqual(receipt["dimension_count"], 2)
        self.assertEqual(receipt["quality_counts"], {"accepted": 1, "degraded": 0, "rejected": 1})
        evidence_set = build_evidence_set("600519.SH", "snap_demo_20260717_v1", self.db_path)
        self.assertEqual(evidence_set["status"], "insufficient")
        self.assertEqual(evidence_set["documents"], [])
        self.assertEqual(evidence_set["gate"]["lead_documents_excluded"], 2)
        coverage = evidence_coverage("600519.SH", self.db_path)
        self.assertEqual(sum(item["count"] for item in coverage["document_counts"]), 2)

    def test_model_evidence_pack_contains_frozen_set_but_excludes_uzi_leads(self) -> None:
        self.promote_catl_fixture_to_real()
        raw_path = Path(self.tmpdir.name) / "raw_data.json"
        raw_path.write_text(json.dumps({
            "ticker": "300750.SZ", "dimensions": {
                "0_basic": {"data": {"url": "https://example.test/uzi-lead"}, "source": "uzi-test", "_pipeline": {"quality": "full"}},
            },
        }), encoding="utf-8")
        import_uzi_raw(raw_path, self.db_path)
        evidence_set = build_evidence_set("300750.SZ", "snap_demo_20260717_v1", self.db_path)
        report = report_payload("300750.SZ", self.db_path)
        assert report is not None
        pack = build_evidence_pack(report, evidence_set)
        self.assertEqual(pack["evidence_set"]["manifest_hash"], evidence_set["manifest_hash"])
        self.assertTrue(all(item["evidence_strength"] in {"strong", "medium"} for item in pack["evidence_set"]["documents"]))
        self.assertNotIn("https://example.test/uzi-lead", json.dumps(pack, ensure_ascii=False))

    def test_stale_company_evidence_blocks_deep_research_gate(self) -> None:
        self.promote_catl_fixture_to_real()
        self.sync_captured("600519.SH", [
            {"document_id": "old_annual", "title": "旧年报", "kind": "primary", "strength": "强", "known_at": "2024-03-01", "url": "https://www.moutaichina.com/old-annual"},
            {"document_id": "old_release", "title": "旧公告", "kind": "company_release", "strength": "强", "known_at": "2024-04-01", "url": "https://www.moutaichina.com/old-release"},
            {"document_id": "old_independent", "title": "旧独立来源", "kind": "independent", "strength": "中", "known_at": "2024-05-01", "url": "https://www.iea.org/old-independent"},
        ], observed_at="2026-07-17T14:00:00+08:00")
        evidence_set = build_evidence_set("600519.SH", "snap_demo_20260717_v1", self.db_path)
        self.assertEqual(evidence_set["status"], "insufficient")
        self.assertTrue(any("recent" in failure for failure in evidence_set["gate"]["failures"]))

    def test_same_day_future_and_post_cutoff_observation_are_excluded(self) -> None:
        self.promote_catl_fixture_to_real()
        with closing(connect(self.db_path)) as conn:
            conn.execute("UPDATE dataset_snapshots SET known_at='2026-07-17T05:30:00+08:00' WHERE id='snap_demo_20260717_v1'")
            conn.commit()
        sources = self.captured_sources([
            {"document_id": "late_primary_1", "title": "同日未来财报", "kind": "primary", "strength": "强", "known_at": "2026-07-17T23:50:00+08:00", "url": "https://static.cninfo.com.cn/late-1.pdf"},
            {"document_id": "late_primary_2", "title": "同日未来公告", "kind": "company_release", "strength": "强", "known_at": "2026-07-17T23:51:00+08:00", "url": "https://www.catl.com/late-2"},
            {"document_id": "late_independent", "title": "同日未来独立资料", "kind": "independent", "strength": "中", "known_at": "2026-07-17T23:52:00+08:00", "url": "https://www.iea.org/late-3"},
        ])
        self.sync_captured("300750.SZ", sources, observed_at="2026-07-17T04:00:00+08:00")
        post_cutoff = self.captured_sources([
            {"document_id": "observed_late", "title": "截止后才看到", "kind": "primary", "strength": "强", "known_at": "2026-07-16", "url": "https://static.cninfo.com.cn/observed-late.pdf"},
        ])
        self.sync_captured("300750.SZ", post_cutoff, observed_at="2026-07-17T06:00:00+08:00")
        evidence_set = build_evidence_set("300750.SZ", "snap_demo_20260717_v1", self.db_path)
        self.assertEqual(evidence_set["status"], "insufficient")
        self.assertEqual(evidence_set["documents"], [])

    def test_duplicate_raw_document_cannot_satisfy_two_primary_slots(self) -> None:
        self.promote_catl_fixture_to_real()
        duplicate = [
            {"document_id": "duplicate_a", "title": "同一财报 A", "kind": "primary", "strength": "强", "known_at": "2026-04-01", "url": "https://www.moutaichina.com/same.pdf"},
            {"document_id": "duplicate_b", "title": "同一财报 B", "kind": "primary", "strength": "强", "known_at": "2026-04-01", "url": "https://www.moutaichina.com/same.pdf"},
            {"document_id": "independent_a", "title": "独立资料", "kind": "independent", "strength": "中", "known_at": "2026-05-01", "url": "https://www.iea.org/independent"},
        ]
        self.sync_captured("600519.SH", duplicate, observed_at="2026-07-17T14:00:00+08:00")
        evidence_set = build_evidence_set("600519.SH", "snap_demo_20260717_v1", self.db_path)
        self.assertEqual(evidence_set["status"], "insufficient")
        self.assertEqual(evidence_set["gate"]["primary_document_count"], 1)

    def test_aggregator_labels_and_missing_urls_cannot_impersonate_core_evidence(self) -> None:
        self.promote_catl_fixture_to_real()
        sources = [
            {"document_id": "agg_a", "title": "聚合器 A", "kind": "primary", "strength": "强", "known_at": "2026-05-01", "url": "https://eastmoney.com/a"},
            {"document_id": "agg_b", "title": "聚合器 B", "kind": "company_release", "strength": "强", "known_at": "2026-05-02", "url": "https://xueqiu.com/b"},
            {"document_id": "agg_c", "title": "聚合器 C", "kind": "independent", "strength": "中", "known_at": "2026-05-03", "url": None},
        ]
        receipt = self.sync_captured("600519.SH", sources, observed_at="2026-07-17T14:00:00+08:00")
        self.assertTrue(all(item["evidence_strength"] == "lead" for item in receipt["documents"]))
        evidence_set = build_evidence_set("600519.SH", "snap_demo_20260717_v1", self.db_path)
        self.assertEqual(evidence_set["status"], "insufficient")
        self.assertEqual(evidence_set["documents"], [])

    def test_company_website_primary_label_cannot_satisfy_regulatory_filing_gate(self) -> None:
        self.promote_catl_fixture_to_real()
        sources = [
            {"document_id": "company_primary", "title": "公司网页伪装财报", "kind": "primary", "strength": "强", "known_at": "2026-05-01", "url": "https://www.moutaichina.com/company-primary"},
            {"document_id": "company_release", "title": "公司公告", "kind": "company_release", "strength": "中", "known_at": "2026-05-02", "url": "https://www.moutaichina.com/company-release"},
            {"document_id": "independent", "title": "独立来源", "kind": "independent", "strength": "中", "known_at": "2026-05-03", "url": "https://www.news.cn/independent"},
        ]
        self.sync_captured("600519.SH", sources, observed_at="2026-07-17T14:00:00+08:00")
        evidence_set = build_evidence_set("600519.SH", "snap_demo_20260717_v1", self.db_path)
        self.assertEqual(evidence_set["status"], "insufficient")
        self.assertEqual(evidence_set["gate"]["regulatory_primary_count"], 0)

    def test_regulatory_pdf_for_another_company_cannot_satisfy_identity_gate(self) -> None:
        self.promote_catl_fixture_to_real()
        sources = [
            {"document_id": "wrong_company_filing", "title": "错误公司财报", "kind": "primary", "strength": "强", "known_at": "2026-04-01", "url": "https://static.cninfo.com.cn/wrong.pdf"},
            {"document_id": "company_release_ok", "title": "公司公告", "kind": "company_release", "strength": "中", "known_at": "2026-05-02", "url": "https://www.moutaichina.com/company-release-ok"},
            {"document_id": "independent_ok", "title": "独立来源", "kind": "independent", "strength": "中", "known_at": "2026-05-03", "url": "https://www.news.cn/independent-ok"},
        ]

        def mismatched_remote(url: str, timeout: float = 30.0) -> tuple[bytes, str, int]:
            if url.endswith("wrong.pdf"):
                return (
                    "平安银行股份有限公司年度报告 证券代码：000001 证券简称：平安银行。"
                    "正文行业比较提到贵州茅台酒股份有限公司、公司代码：600519、公司简称：贵州茅台。"
                ).encode(), "application/pdf", 200
            return "贵州茅台 frozen source".encode(), "text/html", 200

        with patch("research_evidence._capture_remote", side_effect=mismatched_remote):
            receipt = sync_profile_sources(
                "600519.SH", sources, self.db_path, capture_remote=True,
                observed_at="2026-07-17T14:00:00+08:00",
            )
        filing = receipt["documents"][0]
        self.assertEqual(filing["evidence_strength"], "lead")
        evidence_set = build_evidence_set("600519.SH", "snap_demo_20260717_v1", self.db_path)
        self.assertEqual(evidence_set["status"], "insufficient")
        self.assertEqual(evidence_set["gate"]["regulatory_primary_count"], 0)

    def test_old_document_is_kept_in_archive_but_excluded_from_current_evidence_manifest(self) -> None:
        self.promote_catl_fixture_to_real()
        sources = [
            {"document_id": "current_filing", "title": "当前财报", "kind": "primary", "strength": "强", "known_at": "2026-04-01", "url": "https://static.cninfo.com.cn/current.pdf"},
            {"document_id": "current_release", "title": "当前公告", "kind": "company_release", "strength": "中", "known_at": "2026-05-02", "url": "https://www.moutaichina.com/current-release"},
            {"document_id": "current_independent", "title": "当前独立来源", "kind": "independent", "strength": "中", "known_at": "2026-05-03", "url": "https://www.news.cn/current-independent"},
            {"document_id": "stale_filing", "title": "过期财报", "kind": "primary", "strength": "强", "known_at": "2020-04-01", "url": "https://static.cninfo.com.cn/stale.pdf"},
        ]
        self.sync_captured("600519.SH", sources, observed_at="2026-07-17T14:00:00+08:00")
        evidence_set = build_evidence_set("600519.SH", "snap_demo_20260717_v1", self.db_path)
        self.assertEqual(evidence_set["status"], "passed")
        self.assertNotIn("过期财报", {item["title"] for item in evidence_set["documents"]})
        self.assertEqual(evidence_set["gate"]["document_count"], 3)

    def test_inline_raw_text_cannot_bypass_remote_capture(self) -> None:
        self.promote_catl_fixture_to_real()
        receipt = sync_profile_sources("600519.SH", [{
            "document_id": "forged", "title": "伪造财报", "kind": "primary", "strength": "强",
            "known_at": "2026-04-01", "url": "https://static.cninfo.com.cn/forged.pdf",
            "raw_text": "this is not a regulatory filing",
        }], self.db_path, observed_at="2026-07-17T14:00:00+08:00")
        self.assertEqual(receipt["documents"][0]["evidence_strength"], "lead")
        self.assertFalse(receipt["documents"][0].get("raw_sha256"))

    def test_deep_report_discloses_market_and_research_knowledge_cutoffs(self) -> None:
        self.promote_catl_fixture_to_real()
        build_evidence_set(
            "300750.SZ", "snap_demo_20260717_v1", self.db_path,
            knowledge_cutoff="2026-07-17T16:00:00+08:00",
        )
        report = report_payload("300750.SZ", self.db_path)
        assert report is not None
        self.assertEqual(report["market_known_at"], "2026-07-17T15:00:00+08:00")
        self.assertEqual(report["research_known_at"], "2026-07-17T16:00:00+08:00")
        self.assertEqual(report["known_at"], "2026-07-17T16:00:00+08:00")

    def test_research_evidence_tables_are_database_enforced_append_only(self) -> None:
        self.promote_catl_fixture_to_real()
        evidence_set = load_evidence_set("300750.SZ", "snap_demo_20260717_v1", self.db_path)
        assert evidence_set is not None
        with closing(connect(self.db_path)) as conn:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("UPDATE research_documents SET evidence_strength='lead' WHERE id=?", (evidence_set["documents"][0]["id"],))
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("DELETE FROM research_evidence_sets WHERE id=?", (evidence_set["evidence_set_id"],))

    def test_self_consistent_empty_passed_set_is_rejected_by_policy_revalidation(self) -> None:
        self.promote_catl_fixture_to_real()
        legitimate = load_evidence_set("300750.SZ", "snap_demo_20260717_v1", self.db_path)
        assert legitimate is not None
        canonical = lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
        manifest = {
            "ticker": "300750.SZ", "snapshot_id": "snap_demo_20260717_v1",
            "knowledge_cutoff": "2026-07-17T15:00:00+08:00",
            "policy_version": "company-evidence-gate-v1", "documents": [],
        }
        manifest_hash = hashlib.sha256(canonical(manifest).encode()).hexdigest()
        gate = {
            "status": "passed", "failures": [], "document_count": 0,
            "primary_document_count": 0, "regulatory_primary_count": 0,
            "independent_document_count": 0,
        }
        gate_hash = hashlib.sha256(canonical(gate).encode()).hexdigest()
        forged_id = f"rset_{manifest_hash[:20]}"
        with closing(connect(self.db_path)) as conn:
            conn.execute(
                """INSERT INTO research_evidence_sets
                   (id, ticker, snapshot_id, knowledge_cutoff, policy_version, manifest_hash, status, gate_json, gate_hash, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, 'passed', ?, ?, ?)""",
                (forged_id, "300750.SZ", "snap_demo_20260717_v1", manifest["knowledge_cutoff"],
                 manifest["policy_version"], manifest_hash, canonical(gate), gate_hash, "2099-01-01T00:00:00+00:00"),
            )
            conn.commit()
        loaded = load_evidence_set("300750.SZ", "snap_demo_20260717_v1", self.db_path)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["evidence_set_id"], legitimate["evidence_set_id"])

    def test_deep_report_sources_are_strictly_bounded_by_frozen_evidence_set(self) -> None:
        self.promote_catl_fixture_to_real()
        evidence_set = load_evidence_set("300750.SZ", "snap_demo_20260717_v1", self.db_path)
        assert evidence_set is not None
        report = report_payload("300750.SZ", self.db_path)
        assert report is not None
        self.assertEqual(report["research_status"], "verified")
        frozen_keys = {item["source_key"] for item in evidence_set["documents"]}
        report_source_ids = {item["id"] for item in report["sources"]}
        self.assertTrue(all(
            item["kind"] == "market_snapshot" or item["document_id"] in frozen_keys
            for item in report["sources"]
        ))
        self.assertTrue(research_reports._claim_source_ids(report).issubset(report_source_ids))
        serialized = json.dumps(build_evidence_pack(report, evidence_set), ensure_ascii=False)
        self.assertNotIn("iea_2026_batteries", serialized)
        self.assertNotIn("IEA", serialized)

    def test_deepseek_prompt_uses_report_identity_instead_of_hardcoded_company(self) -> None:
        prompt = _user_prompt({"identity": {"ticker": "600519.SH", "name": "贵州茅台"}, "sources": []})
        self.assertIn("贵州茅台深度研报", prompt)
        self.assertNotIn("宁德时代", prompt)

    def test_editorial_guardrails_block_and_rewrite_known_unsupported_assertions(self) -> None:
        self.promote_catl_fixture_to_real()
        report = report_payload("300750.SZ", self.db_path)
        assert report is not None
        evidence_set = load_evidence_set("300750.SZ", "snap_demo_20260717_v1", self.db_path)
        assert evidence_set is not None
        evidence = build_evidence_pack(report, evidence_set)
        narrative = self.valid_narrative()
        narrative["sections"]["valuation_debate"]["paragraphs"][0] += "储能利润率不如动力。"
        self.assertEqual(validate_narrative(narrative, evidence)["status"], "needs_review")
        repaired, rules = apply_editorial_guardrails(narrative)
        self.assertEqual(validate_narrative(repaired, evidence)["status"], "passed")
        self.assertIn("ess_margin_direction_corrected", {rule["id"] for rule in rules})

    def test_editorial_approval_is_bound_to_exact_narrative_and_evidence_manifest(self) -> None:
        self.promote_catl_fixture_to_real()
        report = report_payload("300750.SZ", self.db_path)
        assert report is not None
        evidence_set, evidence_hash = self.catl_artifact_binding(report)
        evidence = build_evidence_pack(report, evidence_set)
        narrative = self.valid_narrative()
        validation = validate_narrative(narrative, evidence)
        self.assertEqual(validation["status"], "passed")
        narrative_hash = hashlib.sha256(json.dumps(narrative, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()
        write_artifact(self.db_path, "300750.SZ", "snap_demo_20260717_v1", {
            "artifact_version": "deepseek-narrative-v1", "validation_version": "metric-source-v2",
            "prompt_version": "deepseek-equity-writer-v1", "provider": "DeepSeek", "model": "test-model",
            "generated_at": "2026-07-17T12:00:00+00:00", "ticker": "300750.SZ", "snapshot_id": "snap_demo_20260717_v1",
            "profile_hash": research_profile_hash(), "research_logic_hash": research_logic_hash(), "writer_logic_hash": writer_logic_hash(),
            "evidence_set_id": evidence_set["evidence_set_id"], "evidence_manifest_hash": evidence_set["manifest_hash"],
            "evidence_hash": evidence_hash, "narrative_hash": narrative_hash, "validation": validation,
            "editorial_approval": {"status": "pending"}, "receipts": [], "narrative": narrative,
        })
        with self.assertRaises(RuntimeError):
            approve_artifact(
                "300750.SZ", self.db_path, reviewer="independent editor",
                expected_narrative_hash=narrative_hash, expected_evidence_manifest_hash="wrong-hash",
            )
        approve_artifact(
            "300750.SZ", self.db_path, reviewer="independent editor",
            expected_narrative_hash=narrative_hash, expected_evidence_manifest_hash=evidence_set["manifest_hash"],
        )
        self.assertEqual(editorial_status("300750.SZ", self.db_path)["status"], "approved")
        self.assertIn("ai_narrative", report_payload("300750.SZ", self.db_path))
        committee = committee_payload(self.db_path)
        catl = next(item for item in committee["items"] if item["ticker"] == "300750.SZ")
        self.assertEqual(committee["metrics"]["decision_review_equity"], 4)
        self.assertEqual(committee["metrics"]["current_executable_equity"], 0)
        self.assertEqual(catl["decision_review_weight"], 4)
        self.assertIsNone(catl["current_executable_weight"])

        artifact = load_artifact(self.db_path, "300750.SZ", "snap_demo_20260717_v1")
        assert artifact is not None
        artifact["editorial_approval"].pop("approval_version")
        write_artifact(self.db_path, "300750.SZ", "snap_demo_20260717_v1", artifact)
        self.assertEqual(editorial_status("300750.SZ", self.db_path)["status"], "invalidated")
        versionless_committee = committee_payload(self.db_path)
        versionless_catl = next(item for item in versionless_committee["items"] if item["ticker"] == "300750.SZ")
        self.assertIsNone(versionless_catl["decision_review_weight"])

        artifact["editorial_approval"]["approval_version"] = "human-editorial-v1"
        artifact["evidence_manifest_hash"] = "stale-manifest"
        write_artifact(self.db_path, "300750.SZ", "snap_demo_20260717_v1", artifact)
        self.assertEqual(editorial_status("300750.SZ", self.db_path)["status"], "invalidated")
        stale_committee = committee_payload(self.db_path)
        stale_catl = next(item for item in stale_committee["items"] if item["ticker"] == "300750.SZ")
        self.assertIsNone(stale_catl["decision_review_weight"])

    def test_failed_automatic_repair_preserves_pending_draft_and_receipt(self) -> None:
        self.promote_catl_fixture_to_real()
        receipt = {"request_id": "req-test", "model": "test-model", "finish_reason": "stop", "usage": {}}
        with patch("deepseek_writer.call_deepseek", return_value=({"report_title": "短"}, receipt)), patch(
            "deepseek_writer.repair_deepseek", side_effect=RuntimeError("truncated repair")
        ):
            with self.assertRaises(RuntimeError):
                generate("300750.SZ", self.db_path, Path(self.tmpdir.name) / "unused-key", "test-model", force=True)
        artifact = load_artifact(self.db_path, "300750.SZ", "snap_demo_20260717_v1")
        assert artifact is not None
        self.assertEqual(artifact["editorial_approval"]["status"], "pending")
        self.assertEqual(artifact["validation"]["status"], "needs_review")
        self.assertIn("truncated repair", artifact["generation_error"])
        self.assertEqual(artifact["receipts"][0]["request_id"], "req-test")

    def test_batch_materializes_eight_reports_and_second_run_reuses_versions(self) -> None:
        self.promote_catl_fixture_to_real()
        output_root = Path(self.tmpdir.name) / "batches"
        first = run_batch(self.db_path, refresh=False, output_root=output_root)
        self.assertEqual(first["status"], "success")
        self.assertEqual(first["requested_count"], 8)
        self.assertEqual(first["success_count"], 8)
        self.assertEqual(first["failed_count"], 0)
        self.assertTrue(all(Path(item["artifact_path"]).is_file() for item in first["reports"]))
        second = run_batch(self.db_path, refresh=False, output_root=output_root)
        self.assertEqual(second["status"], "success")
        self.assertEqual(second["reused_count"], 8)
        self.assertEqual(latest_batch(self.db_path, output_root)["batch_id"], second["batch_id"])

    def test_batch_isolates_one_report_failure_without_losing_other_reports(self) -> None:
        self.promote_catl_fixture_to_real()

        def injected_builder(ticker: str, db_path: Path, *, snapshot_id: str | None = None):
            if ticker == "600036.SH":
                raise RuntimeError("injected report failure")
            return report_payload(ticker, db_path, snapshot_id=snapshot_id)

        result = run_batch(
            self.db_path, refresh=False, output_root=Path(self.tmpdir.name) / "isolated-batches",
            report_builder=injected_builder,
        )
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["failed_count"], 1)
        self.assertEqual(result["success_count"], 7)
        failed = next(item for item in result["reports"] if item["ticker"] == "600036.SH")
        self.assertIn("injected report failure", failed["error"])
        self.assertEqual(sum(Path(item["artifact_path"]).is_file() for item in result["reports"] if item["status"] == "success"), 7)

    def test_batch_rejects_report_returned_for_the_wrong_ticker(self) -> None:
        self.promote_catl_fixture_to_real()

        def wrong_identity_builder(_ticker: str, db_path: Path, *, snapshot_id: str | None = None):
            return report_payload("600519.SH", db_path, snapshot_id=snapshot_id)

        result = run_batch(
            self.db_path, refresh=False, output_root=Path(self.tmpdir.name) / "wrong-identity",
            report_builder=wrong_identity_builder,
        )
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["success_count"], 1)
        self.assertEqual(result["failed_count"], 7)
        self.assertTrue(all(
            "identity mismatch" in item["error"]
            for item in result["reports"] if item["ticker"] != "600519.SH"
        ))

    def test_production_batch_cannot_pass_with_a_ticker_subset(self) -> None:
        self.promote_catl_fixture_to_real()
        with self.assertRaisesRegex(ValueError, "exact configured eight-stock universe"):
            run_batch(
                self.db_path, tickers=["300750.SZ"], refresh=False,
                output_root=Path(self.tmpdir.name) / "subset",
            )

    def test_report_file_failure_does_not_create_a_ghost_version(self) -> None:
        self.promote_catl_fixture_to_real()

        def failing_writer(path: Path, payload: dict) -> None:
            if path.name == "600036.SH.json":
                raise OSError("injected disk failure")
            batch_research._write_json_atomic(path, payload)

        result = run_batch(
            self.db_path, refresh=False, output_root=Path(self.tmpdir.name) / "disk-failure",
            artifact_writer=failing_writer,
        )
        failed = next(item for item in result["reports"] if item["ticker"] == "600036.SH")
        self.assertEqual(result["status"], "partial")
        self.assertEqual(failed["status"], "failed")
        self.assertIn("injected disk failure", failed["error"])
        self.assertEqual(report_version_history("600036.SH", self.db_path), [])

    def test_real_quote_parser_and_storage(self) -> None:
        raw = (
            'v_sh600519="1~贵州茅台~600519~1253.00~1258.99~1269.01~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~20260717152224~-5.99~-0.48~1269.33~1238.98~";\n'
        ).encode("gbk")
        quotes = parse_response(raw, "https://example.test/quote")
        self.assertEqual(len(quotes), 1)
        self.assertEqual(quotes[0]["ticker"], "600519.SH")
        self.assertEqual(quotes[0]["price"], 1253.0)
        self.assertEqual(quotes[0]["quote_time"], "2026-07-17T15:22:24+08:00")
        self.assertEqual(save_market_quotes(quotes, self.db_path), 1)
        stock = stock_payload("600519.SH", self.db_path)
        assert stock is not None
        self.assertEqual(stock["market_quote"]["price"], 1253.0)
        self.assertTrue(any(row["label"] == "最新行情参考价" for row in stock["evidence"]))

    def test_feature_scoring_and_allocation_are_constrained(self) -> None:
        bars = []
        for index in range(321):
            close = 100 + index * 0.08
            bars.append({"trade_date": f"d{index}", "open": close - 0.2, "close": close, "high": close + 0.5, "low": close - 0.5, "volume_lots": 100000})
        quote = {"price": bars[-1]["close"], "pe_ttm": 18, "pb": 2.2, "market_cap_yi": 1000}
        financial = {"roe": 16, "revenue_yoy": 10, "net_profit_yoy": 12, "debt_ratio": 35}
        feature = compute_features(quote, bars, financial)
        self.assertGreater(feature["composite_score"], 50)
        features = {item["ticker"]: dict(feature, composite_score=feature["composite_score"] + i) for i, item in enumerate(DEMO_POSITIONS)}
        weights, cash, _, _ = allocate_weights(features)
        self.assertEqual(sum(weights.values()) + cash, 100)
        self.assertTrue(all(5 <= weight <= 15 for weight in weights.values()))

    def test_real_data_gate_fails_closed_on_incomplete_coverage(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "coverage"):
            validate_real_input_coverage({"a": {}}, {"a": {}}, {}, expected=1)

    def test_transient_source_failure_is_retried_once(self) -> None:
        calls = []

        def flaky():
            calls.append(1)
            if len(calls) == 1:
                raise OSError("transient")
            return "ok"

        self.assertEqual(_retry(flaky), "ok")
        self.assertEqual(len(calls), 2)

    def test_snapshot_manifest_changes_when_portfolio_model_changes(self) -> None:
        inputs = {
            "quotes": {"300750.SZ": {"raw_hash": "quote"}},
            "klines": {"300750.SZ": {"raw_hash": "bars"}},
            "financials": {"300750.SZ": {"raw_hash": "financials"}},
        }
        original = real_pipeline.MODEL_VERSION
        try:
            first = real_pipeline._manifest_hash(inputs)
            real_pipeline.MODEL_VERSION = f"{original}-changed"
            second = real_pipeline._manifest_hash(inputs)
        finally:
            real_pipeline.MODEL_VERSION = original
        self.assertNotEqual(first, second)

    def test_approval_and_publish_state_machine(self) -> None:
        self.promote_catl_fixture_to_real()
        with patch("portfolio_committee.portfolio_release_errors", return_value=[]):
            approved = transition_publication("pub_demo_2026w29", "approve", self.db_path)
            self.assertEqual(approved["status"], "approved")
            published = transition_publication("pub_demo_2026w29", "publish", self.db_path)
        self.assertEqual(published["status"], "published")
        self.assertEqual(publication_history(self.db_path)[0]["status"], "published")

    def test_real_publication_cannot_be_approved_until_all_eight_reports_are_ready(self) -> None:
        self.promote_catl_fixture_to_real()
        with self.assertRaisesRegex(ValueError, "release research gate failed"):
            transition_publication("pub_demo_2026w29", "approve", self.db_path)

    def test_approval_is_invalidated_if_content_changes(self) -> None:
        self.promote_catl_fixture_to_real()
        with patch("portfolio_committee.portfolio_release_errors", return_value=[]):
            transition_publication("pub_demo_2026w29", "approve", self.db_path)
            self.assertTrue(publication_approval_state("pub_demo_2026w29", self.db_path)["is_current"])
            with closing(connect(self.db_path)) as conn:
                conn.execute("UPDATE portfolio_items SET target_weight=11 WHERE publication_id='pub_demo_2026w29' AND ticker='600519.SH'")
                conn.commit()
            self.assertFalse(publication_approval_state("pub_demo_2026w29", self.db_path)["is_current"])
            self.assertEqual(committee_payload(self.db_path)["decision_status"], "blocked")
            stale_report = report_payload("300750.SZ", self.db_path)
            self.assertIsNone(stale_report["executive"]["decision_review_weight"])
            self.assertIsNone(stale_report["executive"]["current_executable_weight"])
            self.assertTrue(stale_report["decision_blockers"])
            with self.assertRaisesRegex(ValueError, "approval package changed"):
                transition_publication("pub_demo_2026w29", "publish", self.db_path)
        self.assertEqual(publication_history(self.db_path)[0]["status"], "invalidated")

    def test_demo_publication_cannot_be_approved_by_relabelling_status(self) -> None:
        with closing(connect(self.db_path)) as conn:
            conn.execute("UPDATE publications SET status='quality_passed' WHERE id='pub_demo_2026w29'")
            conn.commit()
        with self.assertRaisesRegex(ValueError, "release data gate failed"):
            transition_publication("pub_demo_2026w29", "approve", self.db_path)

    def test_research_profile_is_part_of_approval_hash(self) -> None:
        with closing(connect(self.db_path)) as conn:
            before = publication_content_hash(conn, "pub_demo_2026w29")
            original = CATL_PROFILE["report_title"]
            try:
                CATL_PROFILE["report_title"] = f"{original} · changed"
                after = publication_content_hash(conn, "pub_demo_2026w29")
            finally:
                CATL_PROFILE["report_title"] = original
        self.assertNotEqual(before, after)

    def test_report_generator_logic_is_part_of_approval_hash(self) -> None:
        with closing(connect(self.db_path)) as conn:
            before = publication_content_hash(conn, "pub_demo_2026w29")
            original = research_reports.research_logic_hash
            try:
                research_reports.research_logic_hash = lambda: "changed-generator"
                after = publication_content_hash(conn, "pub_demo_2026w29")
            finally:
                research_reports.research_logic_hash = original
        self.assertNotEqual(before, after)

    def test_research_market_input_change_invalidates_approval(self) -> None:
        self.promote_catl_fixture_to_real()
        with closing(connect(self.db_path)) as conn:
            conn.execute("UPDATE publications SET status='quality_passed' WHERE id='pub_demo_2026w29'")
            conn.commit()
        with patch("portfolio_committee.portfolio_release_errors", return_value=[]):
            transition_publication("pub_demo_2026w29", "approve", self.db_path)
            with closing(connect(self.db_path)) as conn:
                conn.execute("UPDATE market_quotes SET price=361 WHERE snapshot_id='snap_demo_20260717_v1' AND ticker='300750.SZ'")
                conn.commit()
            with self.assertRaisesRegex(ValueError, "approval package changed"):
                transition_publication("pub_demo_2026w29", "publish", self.db_path)


if __name__ == "__main__":
    unittest.main()
