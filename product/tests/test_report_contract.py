from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path


PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT))

from report_contract import (  # noqa: E402
    MODULE_SPECS,
    ReportContractError,
    attach_report_contract,
    build_report_contract,
    build_structure_truth_set,
    validate_report_contract,
)


FIXTURES = Path(__file__).parent / "fixtures" / "report_contract"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def sample_runtime_report() -> dict:
    return {
        "ticker": "TSLA",
        "name": "Tesla, Inc.",
        "exchange": "NASDAQ",
        "title": "Tesla research contract fixture",
        "industry": "Automobiles",
        "as_of": "2026-07-20",
        "known_at": "2026-07-20T20:00:00+00:00",
        "data_mode": "REAL",
        "research_status": "baseline",
        "research_depth": "quantitative_baseline",
        "report_version": "fixture-v1",
        "generated_from": {"snapshot_id": "snap_fixture"},
        "market": {
            "price": 100, "change_pct": None, "pe_ttm": None, "pb": None, "market_cap_yi": None,
            "return_20d": None, "return_60d": None, "return_250d": None, "volatility_60d": None,
            "max_drawdown_250d": None, "ma20": None, "ma60": None, "ma200": None, "composite_score": None,
        },
        "executive": {
            "stance": "research_only", "summary": "Schema fixture", "action": "research_only", "score": 50,
            "current_price": 100, "key_contradiction": "Evidence incomplete", "execution_range": "No execution",
            "position_plan": [{"stage": "Research", "weight": 0, "condition": "Complete evidence"}],
        },
        "thesis": [{"title": "Fixture", "body": "Schema fixture", "claim_type": "fact", "source_ids": ["market_snapshot"]}],
        "business_model": {
            "description": "Missing evidence boundary", "source_ids": ["market_snapshot"], "segments": [],
            "value_chain": [{"layer": "Pending", "items": "Missing evidence", "question": "What is supported?"}],
        },
        "industry_position": {"headline": "Missing evidence boundary", "source_ids": ["market_snapshot"], "metrics": []},
        "management": {"score": None, "strengths": [], "watchouts": ["Missing evidence boundary"], "source_ids": ["market_snapshot"]},
        "financials": {
            "headline": "Fixture financials",
            "annual_quality": {"roe": None, "gross_margin": None, "net_margin": None, "debt_ratio": None},
            "series": [{"report_date": "2026-03-31", "report_type": "10-Q", "revenue_yi": None, "net_profit_yi": None, "revenue_yoy": None, "net_profit_yoy": None, "gross_margin": None}],
            "quality_notes": ["Structure fixture"],
        },
        "serenity": {
            "raw_score": 50, "penalty": 0, "final_score": 50, "label": "fixture", "meaning": "Method fixture", "method": "deterministic fixture",
            "factors": [{"label": "Evidence", "score": 2.5, "contribution": 50, "reason": "Fixture", "source_ids": ["market_snapshot"]}],
            "penalties": [],
        },
        "valuation": {"status": "pending_company_research", "reason": "Missing evidence", "current_price": 100, "method": "not available", "pe_ttm": None, "pb": None},
        "quant_signals": [{"name": "Evidence", "score": 0, "proof": "Fixture only", "source_ids": ["market_snapshot"]}],
        "stress_test": {
            "method": "fixture stress", "price_basis": 100, "formula": "price × multiple",
            "scenarios": [{"case": "base", "label": "Base", "price_basis": 100, "stress_multiple": 1, "stress_price": 100, "change_pct": 0, "assumption": "Fixture"}],
            "warning": "Not a target price",
        },
        "catalysts": [{"date": "Next filing", "title": "Next filing", "body": "Complete evidence", "source_ids": ["market_snapshot"]}],
        "risks": [{"rank": 1, "title": "Evidence incomplete", "impact": "high", "probability": "high", "trigger": "New evidence", "evidence": "Fixture", "source_ids": ["market_snapshot"]}],
        "falsification": ["Fixture invalidated"],
        "watchlist": [{"metric": "Evidence coverage", "current": "partial", "threshold": "complete", "frequency": "next update"}],
        "sources": [{"id": "market_snapshot", "document_id": "snapshot_snap_fixture", "title": "Fixture snapshot", "kind": "market_snapshot", "strength": "strong", "known_at": "2026-07-20T20:00:00+00:00", "url": None, "note": "snapshot snap_fixture", "snapshot_id": "snap_fixture", "provider": "fixture_provider", "quote_time": "2026-07-20T20:00:00+00:00"}],
        "evidence_summary": {"document_count": 1, "independent_document_count": 0, "claim_locator_count": 1, "boundary": "Fixture only"},
        "source_contract": {"execution": ["market_snapshot"]},
    }


class ReportContractTest(unittest.TestCase):
    def test_catl_and_tesla_truth_sets_are_generated_and_validate(self) -> None:
        catl = load_fixture("catl.structure.json")
        tesla = load_fixture("tesla.structure.json")
        self.assertEqual(catl, build_structure_truth_set(
            ticker="300750.SZ", name="宁德时代", exchange="深圳证券交易所", market="CN",
        ))
        self.assertEqual(tesla, build_structure_truth_set(
            ticker="TSLA", name="Tesla, Inc.", exchange="NASDAQ", market="US",
        ))
        self.assertEqual(validate_report_contract(catl), [])
        self.assertEqual(validate_report_contract(tesla), [])
        self.assertEqual(
            [(m["id"], m["order"], m["anchor"], m["content_paths"]) for m in catl["module_manifest"]],
            [(m["id"], m["order"], m["anchor"], m["content_paths"]) for m in tesla["module_manifest"]],
        )
        self.assertFalse(catl["truth_set"]["is_live_research"])
        self.assertFalse(tesla["truth_set"]["is_live_research"])

    def test_market_specific_disclosures_use_not_applicable_not_missing(self) -> None:
        catl = load_fixture("catl.structure.json")
        tesla = load_fixture("tesla.structure.json")
        self.assertEqual(catl["market_specific_disclosures"]["sec_filings"]["status"], "not_applicable")
        self.assertEqual(tesla["market_specific_disclosures"]["cninfo_filings"]["status"], "not_applicable")
        self.assertEqual(tesla["market_specific_disclosures"]["sec_filings"]["status"], "available")

    def test_hk_regime_uses_the_same_manifest_and_explicit_disclosures(self) -> None:
        catl = load_fixture("catl.structure.json")
        hk = build_structure_truth_set(ticker="00700.HK", name="腾讯控股", exchange="HKEX", market="HK")
        self.assertEqual(validate_report_contract(hk), [])
        self.assertEqual(
            [(item["id"], item["order"], item["content_paths"]) for item in hk["module_manifest"]],
            [(item["id"], item["order"], item["content_paths"]) for item in catl["module_manifest"]],
        )
        self.assertEqual(hk["identity"]["currency"], "HKD")
        self.assertEqual(hk["market_specific_disclosures"]["cninfo_filings"]["status"], "not_applicable")
        self.assertEqual(hk["market_specific_disclosures"]["sec_filings"]["status"], "not_applicable")
        unknown_hk = build_structure_truth_set(ticker="09988.HK", name="Unknown", exchange="HKEX", market="HK")
        self.assertIn(
            "HK issuer identity is not registered in the v1 security master",
            validate_report_contract(unknown_hk),
        )

    def test_runtime_adapter_attaches_contract_and_visible_missing_evidence(self) -> None:
        report = attach_report_contract(sample_runtime_report())
        self.assertEqual(validate_report_contract(report["report_contract"], report), [])
        self.assertEqual(report["valuation"]["currency"], "USD")
        states = {item["id"]: item["status"] for item in report["report_contract"]["module_manifest"]}
        self.assertEqual(states["valuation"], "missing_evidence")
        self.assertEqual(states["business_and_industry"], "missing_evidence")
        self.assertEqual(states["financial_quality"], "available")

    def test_missing_required_module_or_wrong_order_fails_closed(self) -> None:
        contract = load_fixture("tesla.structure.json")
        contract["module_manifest"].pop(2)
        self.assertIn("module IDs or order do not match research-report-v1", validate_report_contract(contract))
        reordered = load_fixture("tesla.structure.json")
        reordered["module_manifest"][0], reordered["module_manifest"][1] = reordered["module_manifest"][1], reordered["module_manifest"][0]
        self.assertIn("module IDs or order do not match research-report-v1", validate_report_contract(reordered))
        renamed = load_fixture("tesla.structure.json")
        renamed["module_manifest"][0]["title"] = "Ad hoc title"
        self.assertIn("executive_summary rendering contract changed", validate_report_contract(renamed))

    def test_wrong_ticker_market_currency_or_reporting_standard_fails_closed(self) -> None:
        contract = load_fixture("tesla.structure.json")
        contract["identity"]["ticker"] = "300750.SZ"
        self.assertIn("ticker and issuer market disagree", validate_report_contract(contract))
        contract = load_fixture("tesla.structure.json")
        contract["identity"]["currency"] = "CNY"
        self.assertIn("currency does not match issuer market", validate_report_contract(contract))
        contract = load_fixture("tesla.structure.json")
        contract["identity"]["reporting_standard"] = "PRC_GAAP"
        self.assertIn("reporting standard does not match issuer market", validate_report_contract(contract))

    def test_measurement_semantics_cannot_mix_percent_and_percentage_points(self) -> None:
        contract = load_fixture("catl.structure.json")
        contract["measurement_policy"]["percentage_point_unit"] = "percent"
        self.assertIn("percent and percentage-point semantics changed", validate_report_contract(contract))

    def test_not_applicable_and_missing_evidence_require_visible_reasons(self) -> None:
        contract = load_fixture("tesla.structure.json")
        contract["market_specific_disclosures"]["cninfo_filings"]["reason"] = ""
        self.assertIn("cninfo_filings requires a not-applicable reason", validate_report_contract(contract))
        contract = load_fixture("tesla.structure.json")
        contract["module_manifest"][0]["status_reason"] = None
        self.assertIn("executive_summary requires a visible absence reason", validate_report_contract(contract))

    def test_available_module_without_payload_content_is_rejected(self) -> None:
        report = sample_runtime_report()
        attached = attach_report_contract(report)
        broken = copy.deepcopy(attached)
        broken["financials"] = {}
        errors = validate_report_contract(broken["report_contract"], broken)
        self.assertIn("financial_quality is available but content is missing: financials", errors)
        broken = copy.deepcopy(attached)
        broken["disclaimer"] = ""
        self.assertIn(
            "evidence_ledger is available but content is missing: disclaimer",
            validate_report_contract(broken["report_contract"], broken),
        )

    def test_claim_without_support_or_with_unknown_support_is_rejected(self) -> None:
        report = attach_report_contract(sample_runtime_report())
        report["thesis"][0]["source_ids"] = []
        self.assertIn("report.thesis[0] fact requires source_ids", validate_report_contract(report["report_contract"], report))
        report = attach_report_contract(sample_runtime_report())
        report["thesis"][0]["source_ids"] = ["invented_source"]
        self.assertIn(
            "report.thesis[0] references unknown source_ids: invented_source",
            validate_report_contract(report["report_contract"], report),
        )
        report = attach_report_contract(sample_runtime_report())
        report["thesis"][0].pop("claim_type")
        self.assertTrue(any("claim_type" in item for item in validate_report_contract(report["report_contract"], report)))
        report = attach_report_contract(sample_runtime_report())
        report["thesis"][0]["source_ids"] = "market_snapshot"
        self.assertTrue(any("source_ids" in item for item in validate_report_contract(report["report_contract"], report)))

    def test_risk_without_trigger_or_support_is_rejected(self) -> None:
        report = attach_report_contract(sample_runtime_report())
        report["risks"][0]["trigger"] = ""
        report["risks"][0]["source_ids"] = []
        errors = validate_report_contract(report["report_contract"], report)
        self.assertIn("report.risks[0] requires trigger", errors)
        self.assertIn("report.risks[0] requires source_ids", errors)

    def test_contract_identity_must_match_payload(self) -> None:
        report = attach_report_contract(sample_runtime_report())
        report["name"] = "Wrong Company"
        self.assertIn("contract identity does not match report payload", validate_report_contract(report["report_contract"], report))
        report = attach_report_contract(sample_runtime_report())
        report["exchange"] = "深交所"
        report["report_contract"]["identity"]["exchange"] = "深交所"
        self.assertIn("exchange does not match ticker listing", validate_report_contract(report["report_contract"], report))

    def test_policy_downgrade_or_unknown_contract_field_fails_schema(self) -> None:
        contract = load_fixture("tesla.structure.json")
        contract["claim_policy"]["fact_requires_source_ids"] = False
        self.assertTrue(any("fact_requires_source_ids" in item for item in validate_report_contract(contract)))
        contract = load_fixture("tesla.structure.json")
        contract["unexpected"] = "fail open"
        self.assertTrue(any("Additional properties" in item for item in validate_report_contract(contract)))

    def test_meaningless_module_payload_fails_executable_payload_schema(self) -> None:
        report = attach_report_contract(sample_runtime_report())
        report["executive"] = {"foo": "bar"}
        errors = validate_report_contract(report["report_contract"], report)
        self.assertTrue(any("executive" in item and "required property" in item for item in errors))
        report = attach_report_contract(sample_runtime_report())
        report["invented_module"] = {"claim_type": "fact", "source_ids": "invented"}
        errors = validate_report_contract(report["report_contract"], report)
        self.assertTrue(any("Additional properties" in item for item in errors))
        self.assertIn("report.invented_module fact requires source_ids array", errors)

    def test_renderer_consumed_shapes_fail_closed(self) -> None:
        report = attach_report_contract(sample_runtime_report())
        report["executive"]["target_weight"] = "bad"
        self.assertTrue(any("target_weight" in item for item in validate_report_contract(report["report_contract"], report)))
        report = attach_report_contract(sample_runtime_report())
        report["valuation"]["earnings_bridge"] = {}
        self.assertTrue(any("earnings_bridge" in item for item in validate_report_contract(report["report_contract"], report)))
        report = attach_report_contract(sample_runtime_report())
        report["moat"] = [{"nonsense": True}]
        self.assertTrue(any("moat" in item for item in validate_report_contract(report["report_contract"], report)))
        report = attach_report_contract(sample_runtime_report())
        report["ai_narrative"] = {"garbage": True}
        self.assertTrue(any("ai_narrative" in item for item in validate_report_contract(report["report_contract"], report)))

    def test_source_provenance_duplicates_cutoff_and_url_are_fail_closed(self) -> None:
        report = attach_report_contract(sample_runtime_report())
        report["sources"].append(copy.deepcopy(report["sources"][0]))
        self.assertIn("source IDs must be unique", validate_report_contract(report["report_contract"], report))
        report = attach_report_contract(sample_runtime_report())
        report["sources"][0] = {"id": "market_snapshot"}
        self.assertTrue(any("report.sources.0" in item or "report.sources[0]" in item for item in validate_report_contract(report["report_contract"], report)))
        report = attach_report_contract(sample_runtime_report())
        report["sources"][0]["known_at"] = "2099-01-01T00:00:00+00:00"
        self.assertIn("report.sources[0] is newer than research cutoff", validate_report_contract(report["report_contract"], report))
        report = attach_report_contract(sample_runtime_report())
        report["sources"][0]["url"] = "javascript:alert(1)"
        self.assertIn("report.sources[0] URL must use https", validate_report_contract(report["report_contract"], report))
        report = attach_report_contract(sample_runtime_report())
        report["sources"][0].pop("provider")
        self.assertIn("report.sources[0] requires provider", validate_report_contract(report["report_contract"], report))

    def test_cutoff_order_and_nested_currency_override_are_fail_closed(self) -> None:
        report = attach_report_contract(sample_runtime_report())
        report["report_contract"]["as_of"]["market_data_at"] = "not-a-date"
        self.assertIn("runtime report cutoffs must be timezone-aware ISO datetimes", validate_report_contract(report["report_contract"], report))
        report = attach_report_contract(sample_runtime_report())
        report["report_contract"]["as_of"]["market_data_at"] = "2026-07-21T00:00:00+00:00"
        report["report_contract"]["as_of"]["research_cutoff"] = "2026-07-20T00:00:00+00:00"
        self.assertIn("market data time cannot be newer than research cutoff", validate_report_contract(report["report_contract"], report))
        report = attach_report_contract(sample_runtime_report())
        report["valuation"]["nested_scenario"] = {"currency": "CNY"}
        self.assertIn("report.valuation.nested_scenario.currency disagrees with report contract", validate_report_contract(report["report_contract"], report))
        report = attach_report_contract(sample_runtime_report())
        report["report_contract"]["as_of"]["market_data_at"] = "2099-01-01T00:00:00+00:00"
        report["report_contract"]["as_of"]["research_cutoff"] = "2099-01-02T00:00:00+00:00"
        report["sources"][0]["known_at"] = "2099-01-01T00:00:00+00:00"
        report["sources"][0]["quote_time"] = "2099-01-01T00:00:00+00:00"
        self.assertIn("research cutoff cannot be in the future", validate_report_contract(report["report_contract"], report))

    def test_evidence_counts_and_source_contract_are_recomputed(self) -> None:
        report = attach_report_contract(sample_runtime_report())
        report["evidence_summary"]["document_count"] = 999
        report["source_contract"]["execution"] = ["invented"]
        errors = validate_report_contract(report["report_contract"], report)
        self.assertIn("report.evidence_summary.document_count does not match source ledger", errors)
        self.assertIn("report.source_contract.execution references unknown source_ids: invented", errors)

    def test_us_exchange_and_financial_unit_are_bound_to_security_identity(self) -> None:
        report = attach_report_contract(sample_runtime_report())
        report["exchange"] = "NYSE"
        report["report_contract"]["identity"]["exchange"] = "NYSE"
        self.assertIn("US issuer identity disagrees with the v1 security master", validate_report_contract(report["report_contract"], report))
        contract = load_fixture("tesla.structure.json")
        contract["measurement_policy"]["financial_statement_unit_label"] = "亿元"
        self.assertIn("financial statement unit label disagrees with currency", validate_report_contract(contract))

    def test_builder_rejects_unsupported_market(self) -> None:
        with self.assertRaises(ReportContractError):
            build_report_contract(sample_runtime_report(), market="EU")
        unsupported = sample_runtime_report()
        unsupported["ticker"] = "VOW3.DE"
        with self.assertRaises(ReportContractError):
            build_report_contract(unsupported)

    def test_manifest_is_exactly_eight_required_modules(self) -> None:
        self.assertEqual(len(MODULE_SPECS), 8)
        self.assertEqual([spec.order for spec in MODULE_SPECS], list(range(1, 9)))


if __name__ == "__main__":
    unittest.main()
