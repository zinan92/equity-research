"""CATL-only E3-S7 dossier extension with explicit unreviewed judgments."""
from __future__ import annotations
from typing import Any, Mapping

JUDGMENT_STATUS = "ai_generated_judgment_unreviewed"

def _citation(fact: Mapping[str, Any]) -> dict[str, Any]:
    return {key: fact[key] for key in ("document_id", "raw_hash", "page_number", "quoted_anchor", "source_url", "report_period", "unit")}

def compile_catl_judgments(page_facts: list[Mapping[str, Any]], *, dossier_id: str) -> dict[str, Any]:
    """Produce only assertions whose factual components point to a filing page.

    This is an extension of the existing E3-S7 dossier lineage, not a new fact
    collector.  Missing source classes remain missing.
    """
    ordered = sorted(page_facts, key=lambda item: str(item.get("report_period", "")), reverse=True)
    revenue = next((x for x in ordered if x.get("metric") == "revenue"), None)
    profit = next((x for x in ordered if x.get("metric") == "net_profit_parent"), None)
    cited = [item for item in (revenue, profit) if item]
    facts = [{"metric": item["metric"], "value": item["value"], "citation": _citation(item)} for item in cited]
    available = {"status": JUDGMENT_STATUS, "dossier_id": dossier_id, "facts": facts}
    missing = lambda reason: {"status": "missing", "reason": reason, "raw_text_excerpt": "no qualifying official page-bound input in frozen Context Pack"}
    output = {
        "investment_thesis": {**available, "text": "The evidence-bound thesis is conditional on the issuer sustaining the operating trajectory shown in its official filings; this is an unreviewed AI judgment, not an investment recommendation."},
        "variant_view": {**available, "text": "No sell-side consensus is admitted, so the only defensible variant view is a conditional reading of filing evidence rather than a claim about market expectations."},
        "moat_assessment": {**available, "text": "A durable-advantage conclusion requires independent peer evidence; current wording records only an unreviewed hypothesis anchored to company filings."},
        "peer_comparison": missing("no page-bound peer facts"),
        "management_record": missing("no page-bound management track-record series"),
        "governance_events": missing("no official event extraction receipt"),
        "risk_register": {**available, "text": "Risk remains elevated if reported earnings or operating cash conversion deteriorate versus the cited filing baseline."},
        "falsification_tests": {**available, "tests": [{"direction": "down", "threshold": "below the cited annual revenue baseline", "time_window": "next annual filing", "rule": "If reported annual revenue is below the cited baseline, reassess the conditional operating-thesis judgment."}]},
        "monitoring_kpis": {**available, "items": ["annual revenue", "parent net profit", "operating cash flow"]},
        "action_triggers": {**available, "items": ["review on next annual filing", "review if the falsification condition occurs"]},
        "macro_exposures": missing("no official macro sensitivity extraction"),
        "accounting_checks": {**available, "text": "This is a mechanical filing-based check only; it is not an audit opinion."},
        "segment_financials": missing("no official segment table extracted into frozen Context Pack"),
        "market_size": missing("no official market-size source admitted"),
        "operating_kpis": {**available, "items": [{"name": "reported revenue", "facts": facts}]},
        "margin_bridge": {**available, "text": "A complete margin bridge is unavailable; cited revenue and parent-profit facts are retained as the auditable starting point."},
    }
    return output
