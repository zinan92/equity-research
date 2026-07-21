from __future__ import annotations

import copy
from contextlib import closing
from hashlib import sha256
from html import escape as html_escape
import json
import re
import sys
import tempfile
from types import SimpleNamespace
import unittest
from pathlib import Path
from unittest.mock import patch


PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT))

from company_research import (  # noqa: E402
    COMPANY_ADAPTERS,
    CrossCompanyResearchError,
    acceptance_baseline,
    acceptance_evidence,
    baseline_payload_hash,
    build_cross_company_report,
    company_adapter,
    default_company_claims,
    freeze_evidence,
    frozen_model_input,
    load_verified_evidence_packet,
    production_input_identity,
    report_payload_hash,
    render_standalone_html,
    snapshot_binding_for_report,
    validate_frozen_evidence,
)
from deepseek_writer import (  # noqa: E402
    _cross_company_artifact_provenance_hash,
    apply_cross_company_narrative,
    approve_cross_company_narrative,
    build_cross_company_frozen_request,
    generate_cross_company_narrative,
    revise_cross_company_narrative,
)
from data_store import (  # noqa: E402
    DEMO_POSITIONS, connect, create_snapshot_content_attestation, initialize,
)
from report_contract import MODULE_SPECS, validate_report_contract  # noqa: E402
from research_evidence import _capture_remote  # noqa: E402


CUTOFF = "2026-07-20T07:00:00+00:00"


def ingredients(ticker: str):
    adapter = company_adapter(ticker)
    snapshot_id = f"acceptance_{ticker.replace('.', '_')}"
    baseline = acceptance_baseline(adapter, snapshot_id=snapshot_id, cutoff=CUTOFF)
    evidence = acceptance_evidence(adapter, snapshot_id=snapshot_id, cutoff=CUTOFF)
    return adapter, baseline, evidence


def fixture_binding(ticker: str) -> dict[str, str]:
    return snapshot_binding_for_report(ingredients(ticker)[1])


def real_ingredients(ticker: str, root: Path):
    adapter, baseline, _ = ingredients(ticker)
    manifest_hash = sha256(f"snapshot-manifest:{ticker}".encode()).hexdigest()
    snapshot_id = f"snap_real_{manifest_hash[:12]}"
    baseline["generated_from"]["snapshot_id"] = snapshot_id
    baseline["data_mode"] = "REAL"
    baseline["data_status"] = "verified"
    baseline["sources"][0]["snapshot_id"] = snapshot_id
    baseline["sources"][0]["document_id"] = f"market_{snapshot_id}_{ticker}"
    packet = verified_packet(ticker, snapshot_id, root)
    return adapter, baseline, packet, manifest_hash


def verified_packet(ticker: str, snapshot_id: str, root: Path, *, date_only: bool = False):
    documents = []
    for index, (kind, role, domain) in enumerate((
        ("primary", "primary", "cninfo.com.cn"),
        ("primary", "primary", "sse.com.cn" if ticker.endswith(".SH") else "szse.cn"),
        ("independent", "independent", "csindex.com.cn"),
    ), 1):
        raw = f"captured production evidence {ticker} document {index}".encode()
        path = root / f"document-{index}.html"
        path.write_bytes(raw)
        documents.append({
            "id": f"stored_{index}", "title": f"Stored source {index}", "raw_path": str(path),
            "source_key": f"source_{index}",
            "raw_sha256": sha256(raw).hexdigest(), "content_hash": sha256(b"content" + raw).hexdigest(),
            "canonical_url": f"https://www.{domain}/report/{ticker}/{index}",
            "document_kind": kind,
            "published_at": "2026-07-19" if date_only else CUTOFF,
            "role": role,
        })
    stored = {
        "evidence_set_id": "rset_verified", "ticker": ticker, "snapshot_id": snapshot_id,
        "manifest_hash": "c" * 64, "gate_hash": "d" * 64, "knowledge_cutoff": CUTOFF,
        "status": "passed", "documents": documents,
    }
    claims = [
        {"id": "real_thesis", "section": "thesis", "title": "Verified thesis", "statement": "A statement derived from captured evidence.", "claim_type": "fact", "source_ids": ["source_1"]},
        {"id": "real_business", "section": "business", "statement": "A business statement derived from captured evidence.", "claim_type": "inference", "source_ids": ["source_2"]},
        {"id": "real_risk", "section": "risk", "title": "Verified risk", "statement": "A risk derived from captured evidence.", "claim_type": "risk", "trigger": "The disclosed condition changes", "source_ids": ["source_3"]},
    ]
    with patch("research_evidence.load_evidence_set", return_value=stored):
        return load_verified_evidence_packet(ticker, snapshot_id, claims, root / "research.db")


def sample_narrative() -> dict:
    block = {
        "conclusion": "冻结证据只支持有边界的研究结论，任何超出已捕获资料的判断都必须保持为待验证假设。",
        "paragraphs": [
            "本段严格区分正式披露、独立交叉核验与研究推断，不把模型记忆或外部常识伪装成已经验证的公司事实；资料不足处继续显示 Missing evidence。",
            "下一次正式披露需要重新检查经营质量、竞争位置、现金转化与风险触发条件，只有新增证据通过同一完整性门后才允许更新结论。",
        ],
        "source_ids": ["source_1"],
    }
    return {
        "report_title": "Frozen evidence research narrative",
        "executive_summary": copy.deepcopy(block),
        "sections": {
            key: copy.deepcopy(block) for key in (
                "industry_chain", "business_quality", "competitive_moat",
                "financial_quality", "valuation_debate", "risk_falsification",
            )
        },
        "investment_committee": {
            "bull_case": "乐观情景只建立在已捕获的一手证据与独立交叉核验之上，不引入冻结资料以外的事实或数字。",
            "base_case": "基准情景仍以同一冻结证据和明确列出的缺失资料为前提，新增结论需要重新通过证据门。",
            "bear_case": "悲观情景在后续正式披露改变关键经营或风险条件时触发，并要求研究假设整体重估。",
            "source_ids": ["source_1"],
        },
    }


class CrossCompanyResearchV1Test(unittest.TestCase):
    def test_draft_generation_preserves_base_artifact_and_per_company_receipt(self) -> None:
        from scripts import generate_cross_company_research as generator

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            key_file = root / "key"
            key_file.write_text("transport-only", encoding="utf-8")
            previous = root / "600036.SH"
            previous.mkdir()
            (previous / "draft-receipt.json").write_text(json.dumps({
                "schema_version": "cross-company-draft-company-receipt-v1",
                "ticker": "600036.SH",
            }), encoding="utf-8")
            artifact = {
                "artifact_version": "cross-company-narrative-v1",
                "provider": "DeepSeek", "model": "deepseek-test",
                "prompt_version": "writer-test", "input_identity": "identity",
                "evidence_manifest_hash": "e" * 64, "prompt_hash": "p" * 64,
                "narrative_hash": "n" * 64, "validation": {"status": "passed"},
                "usage": {}, "receipts": [], "narrative": {"title": "base"},
                "editorial_approval": {"status": "pending"},
            }
            report = {
                "generated_from": {
                    "snapshot_id": "snap_real_test",
                    "snapshot_manifest_hash": "a" * 64,
                    "baseline_payload_hash": "b" * 64,
                    "production_input_identity": "identity",
                }
            }
            args = SimpleNamespace(
                key_file=key_file, ticker=["600519.SH"], db=root / "unused.db",
                output=root, model="deepseek-test", prompt_version="writer-test",
            )
            with (
                patch.object(generator, "_inputs", return_value=({}, {}, "a" * 64)),
                patch.object(generator, "build_cross_company_report", return_value=report),
                patch.object(generator, "generate_cross_company_narrative", return_value=artifact),
                patch("builtins.print"),
            ):
                generator.generate_drafts(args)
            self.assertEqual(
                json.loads((root / "600519.SH" / "base-narrative-draft.json").read_text()),
                artifact,
            )
            company_receipt = json.loads(
                (root / "600519.SH" / "draft-receipt.json").read_text(encoding="utf-8")
            )
            self.assertRegex(company_receipt["artifact_provenance_hash"], r"^[0-9a-f]{64}$")
            aggregate = json.loads((root / "draft-receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(
                {item["ticker"] for item in aggregate["companies"]},
                {"600036.SH", "600519.SH"},
            )

    def test_inputs_reject_snapshot_rows_changed_after_content_attestation(self) -> None:
        from scripts import generate_cross_company_research as generator

        with tempfile.TemporaryDirectory() as temporary:
            db_path = Path(temporary) / "snapshot.db"
            initialize(db_path, force_seed=True)
            manifest = "a" * 64
            snapshot_id = f"snap_real_{manifest[:12]}"
            with closing(connect(db_path)) as connection:
                connection.execute(
                    "INSERT INTO dataset_snapshots VALUES (?, 'REAL', ?, ?, 'passed', ?, ?, ?)",
                    (snapshot_id, "2026-07-20", CUTOFF, "test", manifest, CUTOFF),
                )
                connection.execute(
                    """INSERT INTO market_quotes VALUES (
                       ?, '600519.SH', '贵州茅台', 1308, 0, 1310, 1300, 20, 5,
                       10000, 9000, ?, 'test', 'https://qt.gtimg.cn/', ?, ?, 'accepted'
                       )""",
                    (snapshot_id, CUTOFF, "q" * 64, CUTOFF),
                )
                create_snapshot_content_attestation(connection, snapshot_id, created_at=CUTOFF)
                connection.commit()
                connection.execute(
                    "UPDATE market_quotes SET price=2308 WHERE snapshot_id=? AND ticker='600519.SH'",
                    (snapshot_id,),
                )
                connection.commit()
            baseline = {
                "ticker": "600519.SH", "data_mode": "REAL", "data_status": "verified",
                "generated_from": {"snapshot_id": snapshot_id},
            }
            with (
                patch.object(
                    generator, "stock_payload",
                    return_value={"ticker": "600519.SH", "snapshot_id": snapshot_id},
                ),
                patch.object(generator, "_baseline_report", return_value=baseline),
            ):
                with self.assertRaisesRegex(RuntimeError, "changed after their immutable attestation"):
                    generator._inputs("600519.SH", db_path)

    def test_snapshot_content_attestation_is_append_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            db_path = Path(temporary) / "snapshot.db"
            initialize(db_path, force_seed=True)
            with closing(connect(db_path)) as connection:
                create_snapshot_content_attestation(
                    connection, "snap_demo_20260717_v1", created_at=CUTOFF,
                )
                connection.commit()
                for statement in (
                    "UPDATE snapshot_content_attestations SET content_hash='forged'",
                    "DELETE FROM snapshot_content_attestations",
                ):
                    with self.subTest(statement=statement):
                        with self.assertRaisesRegex(Exception, "append-only"):
                            connection.execute(statement)

    def test_inputs_reject_replaced_attestation_guard(self) -> None:
        from scripts import generate_cross_company_research as generator

        with tempfile.TemporaryDirectory() as temporary:
            db_path = Path(temporary) / "snapshot.db"
            initialize(db_path, force_seed=True)
            manifest = "a" * 64
            snapshot_id = f"snap_real_{manifest[:12]}"
            with closing(connect(db_path)) as connection:
                connection.execute(
                    "INSERT INTO dataset_snapshots VALUES (?, 'REAL', ?, ?, 'passed', ?, ?, ?)",
                    (snapshot_id, "2026-07-20", CUTOFF, "test", manifest, CUTOFF),
                )
                create_snapshot_content_attestation(connection, snapshot_id, created_at=CUTOFF)
                connection.commit()
                connection.execute("DROP TRIGGER snapshot_content_attestations_no_update")
                connection.execute(
                    """CREATE TRIGGER snapshot_content_attestations_no_update
                       BEFORE UPDATE ON snapshot_content_attestations BEGIN SELECT 1; END"""
                )
                connection.commit()
            baseline = {
                "ticker": "600519.SH", "data_mode": "REAL", "data_status": "verified",
                "generated_from": {"snapshot_id": snapshot_id},
            }
            with (
                patch.object(
                    generator, "stock_payload",
                    return_value={"ticker": "600519.SH", "snapshot_id": snapshot_id},
                ),
                patch.object(generator, "_baseline_report", return_value=baseline),
            ):
                with self.assertRaisesRegex(RuntimeError, "append-only guard is missing or modified"):
                    generator._inputs("600519.SH", db_path)

    def test_inputs_real_path_reads_and_attests_without_database_lock(self) -> None:
        from scripts import generate_cross_company_research as generator

        with tempfile.TemporaryDirectory() as temporary:
            db_path = Path(temporary) / "snapshot.db"
            initialize(db_path, force_seed=True)
            manifest = "b" * 64
            snapshot_id = f"snap_real_{manifest[:12]}"
            publication_id = f"pub_real_{manifest[:12]}"
            item = DEMO_POSITIONS[0]
            with closing(connect(db_path)) as connection:
                connection.execute(
                    "INSERT INTO dataset_snapshots VALUES (?, 'REAL', ?, ?, 'passed', ?, ?, ?)",
                    (snapshot_id, "2026-07-20", CUTOFF, "test", manifest, "2099-01-01T00:00:00+00:00"),
                )
                connection.execute(
                    """INSERT INTO publications (
                       id, snapshot_id, status, title, market_regime, regime_note,
                       equity_weight, cash_weight, model_version
                       ) VALUES (?, ?, 'quality_passed', ?, 'neutral', 'test', 80, 20, 'test-v1')""",
                    (publication_id, snapshot_id, "attested integration snapshot"),
                )
                connection.execute(
                    """INSERT INTO portfolio_items VALUES (
                       ?, ?, ?, ?, ?, 10, 0, '新建', 1308, 'research only', 70,
                       'accepted', '2026-07-20', ?, ?, ?, ?, ?, ?
                       )""",
                    (
                        publication_id, item["ticker"], item["name"], item["exchange"], item["industry"],
                        item["thesis"], item["primary_risk"], item["valuation"],
                        item["bull_case"], item["base_case"], item["bear_case"],
                    ),
                )
                connection.execute(
                    """INSERT INTO market_quotes VALUES (
                       ?, '600519.SH', '贵州茅台', 1308, 0, 1310, 1300, 20, 5,
                       10000, 9000, ?, 'test', 'https://qt.gtimg.cn/', ?, ?, 'accepted'
                       )""",
                    (snapshot_id, CUTOFF, "q" * 64, CUTOFF),
                )
                connection.execute(
                    """INSERT INTO financial_metrics VALUES (
                       ?, '600519.SH', '2025-12-31', '2026-03-31', '年报',
                       100, 50, 10, 12, 30, 90, 50, 20, 10, 'test', ?, 'accepted'
                       )""",
                    (snapshot_id, "f" * 64),
                )
                connection.execute(
                    """INSERT INTO stock_features VALUES (
                       ?, '600519.SH', 1, 2, 3, 10, -5, 1300, 1290, 1280,
                       10, 80, 90, 70, 75, 80, 100, 'test-v1'
                       )""",
                    (snapshot_id,),
                )
                create_snapshot_content_attestation(connection, snapshot_id, created_at=CUTOFF)
                connection.commit()
            stored = {
                "documents": [{"source_key": "test-source"}], "status": "passed",
            }
            with (
                patch.object(generator, "load_evidence_set", return_value=stored),
                patch.object(generator, "default_company_claims", return_value=[]),
                patch.object(generator, "load_verified_evidence_packet", return_value={"status": "passed"}),
            ):
                baseline, packet, resolved_manifest = generator._inputs("600519.SH", db_path)
            self.assertEqual(baseline["generated_from"]["snapshot_id"], snapshot_id)
            self.assertEqual(packet["status"], "passed")
            self.assertEqual(resolved_manifest, manifest)

    def test_five_cross_industry_adapters_are_explicit_and_unique(self) -> None:
        self.assertEqual(len(COMPANY_ADAPTERS), 5)
        self.assertEqual(len({item.industry_key for item in COMPANY_ADAPTERS.values()}), 5)
        self.assertEqual(
            set(COMPANY_ADAPTERS),
            {"600519.SH", "600036.SH", "600900.SH", "000333.SZ", "300750.SZ"},
        )

    def test_each_adapter_has_fail_closed_default_evidence_questions(self) -> None:
        for ticker in COMPANY_ADAPTERS:
            claims = default_company_claims(ticker)
            self.assertEqual([item["section"] for item in claims], ["thesis", "business", "risk"])
            with self.assertRaisesRegex(CrossCompanyResearchError, "required company evidence"):
                default_company_claims(ticker, available_source_ids=[])

    def test_all_five_reports_pass_one_contract_with_one_module_order(self) -> None:
        expected = [item.id for item in MODULE_SPECS]
        for ticker in COMPANY_ADAPTERS:
            with self.subTest(ticker=ticker):
                _, baseline, evidence = ingredients(ticker)
                report = build_cross_company_report(baseline, evidence)
                self.assertEqual(validate_report_contract(report["report_contract"], report), [])
                self.assertEqual(
                    [item["id"] for item in report["report_contract"]["module_manifest"]], expected,
                )
                self.assertEqual(report["research_depth"], "deep")

    def test_acceptance_outputs_cannot_masquerade_as_live_research(self) -> None:
        _, baseline, evidence = ingredients("300750.SZ")
        report = build_cross_company_report(baseline, evidence)
        self.assertEqual(report["data_mode"], "ACCEPTANCE_FIXTURE")
        self.assertFalse(report["report_contract"]["truth_set"]["is_live_research"])
        self.assertIn("NOT LIVE RESEARCH", render_standalone_html(report))

    def test_real_input_uses_runtime_truth_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            _, baseline, packet, manifest_hash = real_ingredients("600519.SH", Path(temporary))
            report = build_cross_company_report(
                baseline, packet, snapshot_manifest_hash=manifest_hash,
            )
            self.assertTrue(report["report_contract"]["truth_set"]["is_live_research"])
            self.assertEqual(validate_report_contract(report["report_contract"], report), [])

    def test_evidence_store_publication_dates_become_timezone_aware_instants(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, baseline, _, manifest_hash = real_ingredients("600519.SH", root)
            packet = verified_packet(
                "600519.SH", baseline["generated_from"]["snapshot_id"], root, date_only=True,
            )
            report = build_cross_company_report(
                baseline, packet, snapshot_manifest_hash=manifest_hash,
            )
            captured = [source for source in report["sources"] if str(source.get("id", "")).startswith("source_")]
            self.assertEqual(len(captured), 3)
            self.assertTrue(all("T23:59:59+08:00" in source["known_at"] for source in captured))

    def test_real_input_rejects_acceptance_fixture_evidence(self) -> None:
        _, baseline, evidence = ingredients("600519.SH")
        baseline["data_mode"] = "REAL"
        baseline["data_status"] = "verified"
        with self.assertRaisesRegex(CrossCompanyResearchError, "evidence-store packet"):
            build_cross_company_report(baseline, evidence, snapshot_manifest_hash="a" * 64)

    def test_cached_demo_and_unknown_modes_never_become_live(self) -> None:
        _, baseline, evidence = ingredients("600519.SH")
        for mode in ("CACHED", "DEMO", "FIXTURE", "anything"):
            with self.subTest(mode=mode):
                changed = copy.deepcopy(baseline)
                changed["data_mode"] = mode
                with self.assertRaisesRegex(CrossCompanyResearchError, "allow only REAL"):
                    build_cross_company_report(changed, evidence)

    def test_frozen_evidence_requires_company_snapshot_identity(self) -> None:
        _, _, evidence = ingredients("600036.SH")
        evidence["snapshot_id"] = "wrong_snapshot"
        baseline = ingredients("600036.SH")[1]
        with self.assertRaisesRegex(CrossCompanyResearchError, "identities disagree"):
            build_cross_company_report(baseline, evidence)

    def test_dangerous_or_unapproved_source_url_fails_closed(self) -> None:
        _, _, evidence = ingredients("600900.SH")
        evidence["documents"][0]["url"] = "http://127.0.0.1/private"
        self.assertTrue(any("approved public HTTPS" in item for item in validate_frozen_evidence(evidence)))
        evidence["documents"][0]["url"] = "https://evil.example/report"
        self.assertTrue(any("approved public HTTPS" in item for item in validate_frozen_evidence(evidence)))

    def test_unknown_claim_citation_fails_closed(self) -> None:
        _, _, evidence = ingredients("000333.SZ")
        evidence["claims"][0]["source_ids"] = ["invented"]
        self.assertTrue(any("unknown source IDs" in item for item in validate_frozen_evidence(evidence)))

    def test_deep_gate_requires_two_primary_and_one_independent_document(self) -> None:
        _, _, evidence = ingredients("300750.SZ")
        evidence["documents"] = evidence["documents"][:2]
        self.assertTrue(any("two primary" in item for item in validate_frozen_evidence(evidence)))

    def test_frozen_manifest_detects_post_freeze_mutation(self) -> None:
        _, _, evidence = ingredients("300750.SZ")
        binding = fixture_binding("300750.SZ")
        frozen = freeze_evidence(evidence)
        frozen["claims"][0]["statement"] = "mutated after freeze"
        with self.assertRaisesRegex(CrossCompanyResearchError, "modified after freeze"):
            production_input_identity(
                frozen, model="deepseek-test", prompt_version="v1", snapshot_binding=binding,
            )
        frozen = freeze_evidence(evidence)
        frozen["limitations"][0] = "removed editorial boundary"
        with self.assertRaisesRegex(CrossCompanyResearchError, "modified after freeze"):
            production_input_identity(
                frozen, model="deepseek-test", prompt_version="v1", snapshot_binding=binding,
            )

    def test_same_inputs_replay_identity_and_changes_are_versioned(self) -> None:
        _, _, evidence = ingredients("600519.SH")
        binding = fixture_binding("600519.SH")
        first = production_input_identity(
            evidence, model="deepseek-test", prompt_version="v1", snapshot_binding=binding,
        )
        second = production_input_identity(
            copy.deepcopy(evidence), model="deepseek-test", prompt_version="v1", snapshot_binding=binding,
        )
        changed = production_input_identity(
            evidence, model="deepseek-test", prompt_version="v2", snapshot_binding=binding,
        )
        self.assertEqual(first, second)
        self.assertNotEqual(first, changed)

    def test_snapshot_payload_mutation_changes_production_identity(self) -> None:
        _, baseline, evidence = ingredients("600519.SH")
        original = build_cross_company_report(baseline, evidence)
        mutated = copy.deepcopy(baseline)
        mutated["market"]["price"] = 999.0
        mutated["executive"]["current_price"] = 999.0
        changed = build_cross_company_report(mutated, evidence)
        self.assertNotEqual(baseline_payload_hash(baseline), baseline_payload_hash(mutated))
        self.assertNotEqual(
            original["generated_from"]["production_input_identity"],
            changed["generated_from"]["production_input_identity"],
        )

    def test_real_snapshot_manifest_must_match_snapshot_id(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            _, baseline, packet, manifest_hash = real_ingredients("600519.SH", Path(temporary))
            with self.assertRaisesRegex(CrossCompanyResearchError, "snapshot ID disagrees"):
                build_cross_company_report(
                    baseline, packet, snapshot_manifest_hash="f" * 64,
                )
            report = build_cross_company_report(
                baseline, packet, snapshot_manifest_hash=manifest_hash,
            )
            self.assertEqual(report["generated_from"]["snapshot_manifest_hash"], manifest_hash)

    def test_deepseek_boundary_contains_only_frozen_input_and_no_runtime_locator(self) -> None:
        _, _, evidence = ingredients("600036.SH")
        binding = fixture_binding("600036.SH")
        request = build_cross_company_frozen_request(
            evidence, model="deepseek-test", prompt_version="v1", snapshot_binding=binding,
        )
        self.assertEqual(request, frozen_model_input(
            evidence, model="deepseek-test", prompt_version="v1", snapshot_binding=binding,
        ))
        self.assertEqual(request["instructions"]["network_access"], "forbidden")
        text = str(request).lower()
        self.assertNotIn("api_key", text)
        self.assertNotIn("database", text)
        self.assertNotIn("filesystem", text)

    def test_deepseek_generation_approval_and_report_attachment_share_one_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, baseline, packet, manifest_hash = real_ingredients("600519.SH", root)
            report = build_cross_company_report(
                baseline, packet, model="deepseek-test", prompt_version="writer-test",
                snapshot_manifest_hash=manifest_hash,
            )
            key_file = root / "key"
            key_file.write_text("secret-for-transport-only", encoding="utf-8")
            captured = {}

            def transport(payload, key):
                captured["payload"] = payload
                captured["key"] = key
                return sample_narrative()

            artifact = generate_cross_company_narrative(
                packet, key_file, model="deepseek-test", prompt_version="writer-test",
                snapshot_binding={
                    key: report["generated_from"][key] for key in (
                        "snapshot_id", "snapshot_manifest_hash", "baseline_payload_hash",
                    )
                }, transport=transport,
            )
            self.assertEqual(artifact["input_identity"], report["generated_from"]["production_input_identity"])
            self.assertIn("captured production evidence", captured["payload"]["messages"][1]["content"])
            self.assertNotIn(str(root), captured["payload"]["messages"][1]["content"])
            self.assertNotIn(captured["key"], str(captured["payload"]))
            with self.assertRaisesRegex(RuntimeError, "identity or validation"):
                apply_cross_company_narrative(report, artifact)
            approved = approve_cross_company_narrative(
                artifact, reviewer="Park",
                expected_narrative_hash=artifact["narrative_hash"],
                expected_evidence_manifest_hash=artifact["evidence_manifest_hash"],
                expected_artifact_provenance_hash=_cross_company_artifact_provenance_hash(artifact),
            )
            enriched = apply_cross_company_narrative(report, approved)
            self.assertEqual(enriched["narrative_provider"]["provider"], "DeepSeek")
            self.assertEqual(enriched["narrative_provider"]["editorial_approval"]["status"], "approved")
            self.assertEqual(enriched["report_hash"], report_payload_hash(enriched))
            rendered = render_standalone_html(enriched)
            self.assertIn("冻结证据只支持有边界的研究结论", rendered)
            self.assertIn("悲观情景在后续正式披露改变关键经营或风险条件时触发", rendered)

    def test_evidence_editor_revision_preserves_model_provenance_and_requires_new_approval(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, baseline, packet, manifest_hash = real_ingredients("600519.SH", root)
            report = build_cross_company_report(
                baseline, packet, model="deepseek-test", prompt_version="writer-test",
                snapshot_manifest_hash=manifest_hash,
            )
            binding = {
                key: report["generated_from"][key] for key in (
                    "snapshot_id", "snapshot_manifest_hash", "baseline_payload_hash",
                )
            }
            key_file = root / "key"
            key_file.write_text("secret-for-transport-only", encoding="utf-8")
            artifact = generate_cross_company_narrative(
                packet, key_file, model="deepseek-test", prompt_version="writer-test",
                snapshot_binding=binding, transport=lambda payload, key: sample_narrative(),
            )
            request = build_cross_company_frozen_request(
                packet, model="deepseek-test", prompt_version="writer-test",
                snapshot_binding=binding,
            )
            narrowed = copy.deepcopy(artifact["narrative"])
            narrowed["executive_summary"]["conclusion"] = "冻结证据仅支持有边界的研究结论"
            revised = revise_cross_company_narrative(
                artifact, narrowed, request, editor="evidence editor",
                findings=["删除引用不能蕴含的结论"],
            )
            self.assertEqual(revised["provider"], "DeepSeek draft + evidence editor")
            self.assertNotEqual(revised["narrative_hash"], artifact["narrative_hash"])
            self.assertEqual(
                revised["editorial_revision"]["base_narrative_hash"], artifact["narrative_hash"],
            )
            with self.assertRaisesRegex(RuntimeError, "identity or validation"):
                apply_cross_company_narrative(report, revised)
            reviewed_provenance = _cross_company_artifact_provenance_hash(revised)
            tampered_before_approval = copy.deepcopy(revised)
            tampered_before_approval["editorial_revision"]["revised_by"] = "forged editor"
            with self.assertRaisesRegex(RuntimeError, "reviewed artifact provenance changed"):
                approve_cross_company_narrative(
                    tampered_before_approval, reviewer="independent reviewer",
                    expected_narrative_hash=revised["narrative_hash"],
                    expected_evidence_manifest_hash=revised["evidence_manifest_hash"],
                    expected_artifact_provenance_hash=reviewed_provenance,
                )
            approved = approve_cross_company_narrative(
                revised, reviewer="independent reviewer",
                expected_narrative_hash=revised["narrative_hash"],
                expected_evidence_manifest_hash=revised["evidence_manifest_hash"],
                expected_artifact_provenance_hash=reviewed_provenance,
            )
            enriched = apply_cross_company_narrative(report, approved)
            self.assertEqual(
                enriched["narrative_provider"]["provider"], "DeepSeek draft + evidence editor",
            )
            self.assertEqual(
                enriched["narrative_provider"]["editorial_review"]["applied_rules"][0]["id"],
                "evidence_entailment_revision",
            )
            for mutation in ("provider", "model", "revision"):
                tampered = copy.deepcopy(approved)
                if mutation == "provider":
                    tampered["provider"] = "DeepSeek"
                elif mutation == "model":
                    tampered["model"] = "forged-model"
                else:
                    tampered.pop("editorial_revision", None)
                with self.subTest(mutation=mutation), self.assertRaisesRegex(
                    RuntimeError, "identity or validation",
                ):
                    apply_cross_company_narrative(report, tampered)

    def test_missing_evidence_remains_visible_in_deep_structure(self) -> None:
        _, baseline, evidence = ingredients("600900.SH")
        evidence["claims"] = [item for item in evidence["claims"] if item["section"] == "risk"]
        report = build_cross_company_report(baseline, evidence)
        self.assertIn("Missing evidence", report["thesis"][0]["title"])
        self.assertIn("Missing evidence", report["business_model"]["description"])
        self.assertIn("Missing evidence", report["valuation"]["reason"])
        valuation_module = next(
            item for item in report["report_contract"]["module_manifest"]
            if item["id"] == "valuation"
        )
        self.assertEqual(valuation_module["status"], "missing_evidence")
        forged = copy.deepcopy(report)
        forged["report_contract"]["module_manifest"][5]["status"] = "available"
        forged["report_contract"]["module_manifest"][5]["status_reason"] = None
        self.assertTrue(any(
            "valuation status disagrees" in error
            for error in validate_report_contract(forged["report_contract"], forged)
        ))

    def test_html_has_exact_eight_modules_and_print_css(self) -> None:
        _, baseline, evidence = ingredients("000333.SZ")
        evidence["documents"][0]["url"] += "?scope=annual&lang=zh"
        html = render_standalone_html(build_cross_company_report(baseline, evidence))
        rendered = re.findall(r'data-report-module="([^"]+)"', html)
        self.assertEqual(rendered, [item.id for item in MODULE_SPECS])
        self.assertIn("@media(max-width:700px)", html)
        self.assertIn("@media print", html)
        for source in build_cross_company_report(baseline, evidence)["sources"]:
            self.assertIn(f'data-evidence-id="{source["id"]}"', html)
            self.assertIn(f'id="evidence-{source["id"]}"', html)
            if source.get("url"):
                self.assertIn(html_escape(source["url"], quote=True), html)

    def test_capture_rejects_redirect_to_unapproved_or_private_destination(self) -> None:
        class Headers:
            @staticmethod
            def get_content_type():
                return "text/html"

        class Response:
            status = 200
            headers = Headers()

            def __init__(self, final_url: str):
                self.final_url = final_url

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def geturl(self):
                return self.final_url

            def read(self, size):
                return b"should never be accepted"

        class Opener:
            def __init__(self, final_url: str):
                self.final_url = final_url

            def open(self, request, timeout):
                return Response(self.final_url)

        def addresses(host, port, type):
            address = "127.0.0.1" if host == "127.0.0.1" else "93.184.216.34"
            return [(2, 1, 6, "", (address, port))]

        with patch("research_evidence.socket.getaddrinfo", side_effect=addresses):
            with patch("research_evidence.urllib.request.build_opener", return_value=Opener("https://evil.example/steal")):
                with self.assertRaisesRegex(RuntimeError, "allowlist"):
                    _capture_remote(
                        "https://trusted.example/start", allowed_domains={"trusted.example"},
                    )
            with patch("research_evidence.urllib.request.build_opener", return_value=Opener("https://127.0.0.1/private")):
                with self.assertRaisesRegex(RuntimeError, "non-public"):
                    _capture_remote(
                        "https://trusted.example/start",
                        allowed_domains={"trusted.example", "127.0.0.1"},
                    )

    def test_cross_company_schema_requires_complete_production_identity(self) -> None:
        _, baseline, evidence = ingredients("300750.SZ")
        report = build_cross_company_report(baseline, evidence)
        report["generated_from"].pop("baseline_payload_hash")
        errors = validate_report_contract(report["report_contract"], report)
        self.assertTrue(any("baseline_payload_hash" in error for error in errors))

    def test_render_rechecks_report_hash_after_any_mutation(self) -> None:
        _, baseline, evidence = ingredients("300750.SZ")
        report = build_cross_company_report(baseline, evidence)
        self.assertEqual(report["report_hash"], report_payload_hash(report))
        report["title"] = "mutated after hash"
        with self.assertRaisesRegex(CrossCompanyResearchError, "changed after"):
            render_standalone_html(report)


if __name__ == "__main__":
    unittest.main()
