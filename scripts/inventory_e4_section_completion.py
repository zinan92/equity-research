#!/usr/bin/env python3
"""Legacy read-only E4 section inventory used by the compatibility test.

This helper does not feed V4 generation, Tier evaluation, or publication. It
is retained only because old evidence receipts still use the 18-section
input vocabulary; M4 will retire the helper together with that vocabulary.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product"))

from report_contract import RESEARCH_SECTION_SPECS_V3  # noqa: E402


OWNERS = {
    "issuer_identity": "data_core.security_master",
    "positioning_evidence": "data_core.official_filing_ingest",
    "industry_evidence": "data_core.e4_r2_industry_wiring",
    "company_position": "data_core.e4_r2_industry_wiring",
    "management_evidence": "data_core.e4_l1_m4_governance_events",
    "governance_evidence": "data_core.e4_l1_m4_governance_events",
    "timeline_evidence": "data_core.official_filing_ingest",
    "business_evidence": "data_core.e4_r2_industry_wiring",
    "operating_evidence": "data_core.official_filing_ingest",
    "financial_evidence": "data_core.e4_page_level_filing_facts",
    "valuation_evidence": "data_core.e4_market_fundamentals_batch",
    "moat_evidence": "data_core.official_filing_ingest",
    "falsification_evidence": "data_core.e4_model_judgments",
    "risk_evidence": "data_core.official_filing_ingest",
    "trigger_evidence": "data_core.e4_model_judgments",
    "synthesis_evidence": "round7_chapter_generator",
    "decision_policy_output": "data_core.decision_policy",
    "chapter_draft": "round7_chapter_generator",
    "run_receipt": "round7_dossier_runner",
    "source_manifest": "data_core.official_filing_ingest",
}


def build_inventory(receipt: dict) -> dict:
    rows = receipt.get("rows") or []
    by_ticker = {str(row.get("ticker")): row.get("result") for row in rows if row.get("status") == "available"}
    expected = {"300750.SZ", "600519.SH", "000001.SZ"}
    if set(by_ticker) != expected:
        raise ValueError("receipt must contain the three intended Tier-B vertical slices")
    contracts = {
        ticker: {item["section_id"]: item for item in result["section_contract"]["sections"]}
        for ticker, result in by_ticker.items()
    }
    leverage: Counter[str] = Counter()
    sections = []
    for spec in RESEARCH_SECTION_SPECS_V3:
        issuers = {}
        for ticker, by_section in contracts.items():
            assessment = by_section[spec.section_id]
            issuers[ticker] = {
                "status": assessment["status"],
                "present": assessment["present_required"],
                "missing": assessment["missing_required"],
            }
        for required in spec.required_inputs:
            if any(required.key in item["missing"] for item in issuers.values()):
                leverage[required.key] += 1
        sections.append({
            "section_id": spec.section_id,
            "required_inputs": [item.key for item in spec.required_inputs],
            "issuers": issuers,
        })
    ranked = [
        {
            "input": key,
            "dependent_sections": count,
            "owner": OWNERS.get(key, "未建"),
            "existing_module": key in OWNERS,
        }
        for key, count in sorted(leverage.items(), key=lambda item: (-item[1], item[0]))
    ]
    return {
        "tickers": sorted(by_ticker),
        "sections": sections,
        "leverage": ranked,
        "independent_missing_required_inputs": len(ranked),
    }


def markdown(inventory: dict) -> str:
    lines = ["# E4 legacy section completion inventory", "", "This is a read-only compatibility artifact; it is not the V4 contract.", ""]
    lines.append(f"Tickers: {', '.join(inventory['tickers'])}")
    lines.append(f"Independent missing required inputs: {inventory['independent_missing_required_inputs']}")
    lines.extend(["", "| section_id | required_inputs |", "|---|---|"])
    for row in inventory["sections"]:
        lines.append(f"| {row['section_id']} | {', '.join(row['required_inputs'])} |")
    lines.extend(["", "| input | dependent_sections | owner |", "|---|---:|---|"])
    for row in inventory["leverage"]:
        lines.append(f"| {row['input']} | {row['dependent_sections']} | {row['owner']} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    value = build_inventory(json.loads(args.receipt.read_text(encoding="utf-8")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(markdown(value), encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
