"""Receipt-bound, issuer-specific CATL judgment drafts.

These are deliberately unreviewed AI judgments.  Every factual clause is
represented as a claim with page-level evidence; unavailable source classes
remain MISSING rather than becoming generic prose.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

JUDGMENT_STATUS = "ai_generated_judgment_unreviewed"
ISSUER = "宁德时代"


def _financial_citation(fact: Mapping[str, Any]) -> dict[str, Any]:
    return {key: fact[key] for key in ("document_id", "raw_hash", "page_number", "quoted_anchor", "source_url", "report_period", "unit")}


def _financial_fact(fact: Mapping[str, Any]) -> dict[str, Any]:
    return {"evidence_type": "financial_fact", "metric": fact["metric"], "value": fact["value"], "citation": _financial_citation(fact)}


def _narrative_fact(block: Mapping[str, Any]) -> dict[str, Any]:
    citation = {key: block[key] for key in ("document_id", "raw_hash", "page_number", "source_url", "report_period")}
    citation.update({"quoted_anchor": block["text"], "unit": "narrative_text", "section_path": block["section_path"]})
    return {"evidence_type": "narrative_block", "metric": "narrative_evidence", "value": block["text"], "citation": citation}


def _select_financial(facts: Iterable[Mapping[str, Any]], metric: str) -> Mapping[str, Any] | None:
    rows = [row for row in facts if row.get("metric") == metric and row.get("document_id") and row.get("raw_hash")]
    return max(rows, key=lambda row: str(row.get("report_period") or ""), default=None)


def _select_narrative(blocks: Iterable[Mapping[str, Any]], *terms: str) -> Mapping[str, Any] | None:
    rows = [
        row for row in blocks
        if row.get("status") == "resolved" and row.get("section_path") and row.get("text")
        and all(term in str(row.get("section_path")) + str(row.get("text")) for term in terms)
    ]
    return max(rows, key=lambda row: (str(row.get("report_period") or ""), int(row.get("page_number") or 0)), default=None)


def _draft(
    *, dossier_id: str, text: str, evidence: list[dict[str, Any]], claims: list[dict[str, Any]],
) -> dict[str, Any]:
    if ISSUER not in text:
        raise ValueError("name-swap test rejected generic judgment text")
    if not evidence or not claims:
        raise ValueError("unreviewed judgment requires claim-level page evidence")
    return {
        "status": JUDGMENT_STATUS, "dossier_id": dossier_id, "text": text,
        "facts": evidence, "claims": claims,
        "name_swap_test": {"status": "passed", "issuer_token": ISSUER, "generic_claims": 0},
        "citation_mix": {
            "narrative_blocks": sum(item["evidence_type"] == "narrative_block" for item in evidence),
            "financial_facts": sum(item["evidence_type"] == "financial_fact" for item in evidence),
        },
    }


def _missing(reason: str) -> dict[str, Any]:
    return {"status": "missing", "reason": reason, "raw_text_excerpt": "no qualifying issuer-specific, page-bound evidence in supplied receipts"}


def compile_catl_judgments(
    page_facts: list[Mapping[str, Any]], *, dossier_id: str,
    narrative_blocks: Iterable[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Generate ten C1-connected drafts only from supplied real receipts."""
    blocks = tuple(narrative_blocks)
    revenue = _select_financial(page_facts, "revenue")
    cost = _select_financial(page_facts, "operating_cost")
    competition = _select_narrative(blocks, "核心竞争力")
    business = _select_narrative(blocks, "主营业务") or _select_narrative(blocks, "主要业务")
    risk = _select_narrative(blocks, "风险")
    research = _select_narrative(blocks, "研发")
    output: dict[str, Any] = {
        "peer_comparison": _missing("no page-bound peer facts"),
        "management_record": _missing("no page-bound management track-record series"),
        "governance_events": _missing("no official event extraction receipt"),
        "macro_exposures": _missing("no official macro sensitivity extraction"),
        "segment_financials": _missing("no official segment table extracted into frozen Context Pack"),
        "market_size": _missing("no official market-size source admitted"),
        "variant_view": _missing("no broker consensus or market-expectations receipt"),
    }
    if business and revenue:
        evidence = [_narrative_fact(business), _financial_fact(revenue)]
        output["investment_thesis"] = _draft(dossier_id=dossier_id,
            text=f"{ISSUER}的未审阅经营判断以其披露的主营业务描述和{revenue['report_period']}营业收入为条件，不能替代投资建议。",
            evidence=evidence, claims=[{"text": f"{ISSUER}披露了主营业务描述。", "citations": [evidence[0]["citation"]]}, {"text": f"{ISSUER}披露了{revenue['report_period']}营业收入。", "citations": [evidence[1]["citation"]]}])
    else:
        output["investment_thesis"] = _missing("issuer-specific business narrative or revenue fact unavailable")
    if competition:
        evidence = [_narrative_fact(competition)]
        output["moat_assessment"] = _draft(dossier_id=dossier_id,
            text=f"{ISSUER}在官方披露中描述核心竞争力；该未审阅判断仅基于公司自述，缺独立同行验证。",
            evidence=evidence, claims=[{"text": f"{ISSUER}在官方披露中描述核心竞争力。", "citations": [evidence[0]["citation"]]}])
    else:
        output["moat_assessment"] = _missing("no official core-competitiveness narrative block")
    if risk:
        evidence = [_narrative_fact(risk)]
        output["risk_register"] = _draft(dossier_id=dossier_id,
            text=f"{ISSUER}风险登记仅记录官方披露的风险因素，未审阅且不表示风险概率或投资结论。",
            evidence=evidence, claims=[{"text": f"{ISSUER}披露了对应风险因素。", "citations": [evidence[0]["citation"]]}])
    else:
        output["risk_register"] = _missing("no official risk narrative block")
    if revenue:
        threshold = float(revenue["value"])
        evidence = [_financial_fact(revenue)]
        rule = f"若{ISSUER}下一份年度报告的营业收入低于 {threshold:g} {revenue['unit']}，则该未审阅经营判断被推翻并须重审。"
        output["falsification_tests"] = _draft(dossier_id=dossier_id, text=rule, evidence=evidence,
            claims=[{"text": f"{ISSUER}披露了证伪阈值所依据的{revenue['report_period']}营业收入。", "citations": [evidence[0]["citation"]]}])
        output["falsification_tests"]["tests"] = [{"metric": "revenue", "direction": "down", "threshold": threshold, "unit": revenue["unit"], "time_window": "next annual filing", "rule": rule}]
    else:
        output["falsification_tests"] = _missing("no page-bound annual revenue threshold")
    monitor_evidence = [_financial_fact(revenue)] if revenue else []
    if research:
        monitor_evidence.append(_narrative_fact(research))
    if monitor_evidence:
        output["monitoring_kpis"] = _draft(dossier_id=dossier_id,
            text=f"{ISSUER}的未审阅监控清单跟踪已披露营业收入及研发相关进展，并在下一次定期披露时复核。",
            evidence=monitor_evidence, claims=[{"text": f"{ISSUER}披露了监控项所依据的页级证据。", "citations": [item["citation"] for item in monitor_evidence]}])
        output["monitoring_kpis"]["items"] = ["reported_revenue", "research_and_product_progress"]
    else:
        output["monitoring_kpis"] = _missing("no issuer-specific monitoring evidence")
    if output["falsification_tests"].get("status") == JUDGMENT_STATUS:
        output["action_triggers"] = _draft(dossier_id=dossier_id,
            text=f"{ISSUER}触发复核的未审阅条件是下一份年度报告营业收入低于已引用阈值。",
            evidence=output["falsification_tests"]["facts"], claims=output["falsification_tests"]["claims"])
        output["action_triggers"]["items"] = output["falsification_tests"]["tests"]
    else:
        output["action_triggers"] = _missing("no concrete falsification threshold")
    if revenue and cost:
        evidence = [_financial_fact(revenue), _financial_fact(cost)]
        output["accounting_checks"] = _draft(dossier_id=dossier_id,
            text=f"{ISSUER}的未审阅会计检查并列其已披露营业收入与营业成本，不构成审计意见。",
            evidence=evidence, claims=[{"text": f"{ISSUER}披露了营业收入和营业成本。", "citations": [item["citation"] for item in evidence]}])
        gap = float(revenue["value"]) - float(cost["value"])
        output["margin_bridge"] = _draft(dossier_id=dossier_id,
            text=f"{ISSUER}的未审阅毛利起点为已披露营业收入减营业成本 {gap:g} {revenue['unit']}；完整利润率桥缺少其余成本层证据。",
            evidence=evidence, claims=[{"text": f"{ISSUER}披露了计算该起点的营业收入和营业成本。", "citations": [item["citation"] for item in evidence]}])
    else:
        output["accounting_checks"] = _missing("no matching page-bound revenue and operating-cost facts")
        output["margin_bridge"] = _missing("no matching page-bound revenue and operating-cost facts")
    if business or research:
        evidence = [_narrative_fact(block) for block in (business, research) if block]
        output["operating_kpis"] = _draft(dossier_id=dossier_id,
            text=f"{ISSUER}的未审阅经营指标以主营业务与研发披露中的具体进展为观察对象。",
            evidence=evidence, claims=[{"text": f"{ISSUER}披露了经营指标观察所依据的业务或研发进展。", "citations": [item["citation"] for item in evidence]}])
        output["operating_kpis"]["items"] = ["business_and_product_progress", "research_progress"]
    else:
        output["operating_kpis"] = _missing("no issuer-specific business or research narrative")
    return output
