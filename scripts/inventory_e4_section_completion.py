#!/usr/bin/env python3
"""Read three Round 7 contracts and render completion and leverage inventory."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product"))

from report_contract import RESEARCH_SECTION_SPECS_V3


# A source owner is deliberately not a claim that the module already supplies
# the whole typed input; ``未建`` means no existing product module is its owner.
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
    if set(by_ticker) != {"300750.SZ", "600519.SH", "000001.SZ"}:
        raise ValueError("receipt must contain the three intended Tier-B vertical slices")
    contracts = {ticker: {item["section_id"]: item for item in result["section_contract"]["sections"]} for ticker, result in by_ticker.items()}
    sections = []
    leverage: Counter[str] = Counter()
    for spec in RESEARCH_SECTION_SPECS_V3:
        issuer_rows = {}
        for ticker, by_section in contracts.items():
            assessment = by_section[spec.section_id]
            issuer_rows[ticker] = {
                "status": assessment["status"], "present": assessment["present_required"],
                "missing": assessment["missing_required"],
            }
        # Contract inputs are canonical, so dependencies are counted by the
        # distinct affected section, never tripled for three identical issuers.
        for key in spec.required_inputs:
            if any(key.key in issuer_rows[ticker]["missing"] for ticker in issuer_rows):
                leverage[key.key] += 1
        sections.append({
            "section_id": spec.section_id,
            "required_inputs": [item.key for item in spec.required_inputs],
            "issuers": issuer_rows,
        })
    ranked = [
        {"input": key, "dependent_sections": count, "owner": OWNERS.get(key, "未建"),
         "existing_module": key in OWNERS}
        for key, count in sorted(leverage.items(), key=lambda item: (-item[1], item[0] not in OWNERS, item[0]))
    ]
    return {"tickers": sorted(by_ticker), "sections": sections, "leverage": ranked,
            "independent_missing_required_inputs": len(ranked)}


def markdown(inventory: dict) -> str:
    tickers = inventory["tickers"]
    lines = ["# E4 三家 Round 7 章节完成度盘点", "", "本文件只读取 9 章 C1 合同；不改变任何输入、Tier 或 B6 policy。", "",
             "## 9 章 × 缺什么", "", "| section_id | required_inputs | 300750.SZ status / present / missing | 600519.SH status / present / missing | 000001.SZ status / present / missing | blocking source |", "|---|---|---|---|---|---|"]
    for row in inventory["sections"]:
        states = []
        missing = set()
        for ticker in tickers:
            item = row["issuers"][ticker]; states.append(f"{item['status'].upper()} / {', '.join(item['present']) or '—'} / {', '.join(item['missing']) or '—'}")
            missing.update(item["missing"])
        owners = "; ".join(f"{key}: {OWNERS.get(key, '未建')}" for key in sorted(missing)) or "—"
        lines.append(f"| {row['section_id']} | {', '.join(row['required_inputs'])} | {' | '.join(states)} | {owners} |")
    lines += ["", "## 缺失输入杠杆排序", "", "所有项的依赖章节数均为 1；以下仅以“已有模块可接”作为同分时的次序。", "", "| rank | input | dependent sections | source/module |", "|---:|---|---:|---|"]
    for index, item in enumerate(inventory["leverage"], 1):
        lines.append(f"| {index} | {item['input']} | {item['dependent_sections']} | {item['owner']} |")
    existing = sum(item["existing_module"] for item in inventory["leverage"])
    lines += ["", "## 一句话结论", "",
              f"距离 Tier A 的真实缺口是 **{inventory['independent_missing_required_inputs']} 项独立 required inputs**：其中 {existing} 项已有模块可作为接线起点，{inventory['independent_missing_required_inputs'] - existing} 项在当前产品路径仍为未建；9 章合同按章节完整性计分，任何未审阅草稿都不能获得 FULL。"]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("receipt", type=Path); parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(); inventory = build_inventory(json.loads(args.receipt.read_text(encoding="utf-8")))
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(markdown(inventory), encoding="utf-8")
    print(args.output); return 0


if __name__ == "__main__":
    raise SystemExit(main())
