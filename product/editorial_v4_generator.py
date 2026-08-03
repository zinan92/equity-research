"""Whole-report DeepSeek writer for the review-only Ainiu/V4 dossier."""
from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from deepseek_writer import DEFAULT_KEY_FILE, DEFAULT_MODEL, call_structured_deepseek
from editorial_v4_contract import EDITORIAL_V4_SCHEMA, SECTION_IDS, SECTION_TITLES, canonical_hash, validate_evidence_packet


PROMPT_VERSION = "editorial-v4-whole-report-prompt-v1"
GENERATOR_VERSION = "editorial-v4-whole-report-generator-v1"


SYSTEM_PROMPT = """你是 Park Equity Research 的资深中文研究员。你要把一个已经冻结的、官方 PDF 页级绑定的 evidence packet 写成一篇爱牛式 V4 读者报告。

这是一次全报告调用。只允许使用用户 JSON 中的 evidence、derived_metrics 和 gaps；不得联网，不得调用外部知识，不得读取旧报告、模板或 benchmark。任何年份、历史沿革、客户、价格、产能、排名、份额等事实只要没有对应的输入 evidence，就必须删掉或写成 gap；不能凭模型记忆补全。行业地位、护城河、管理风格和市场反应可以作为 aggressive judgment，但必须写入 judgment claim、引用相关底层 evidence、带 `[J-xx]` 和 falsifier，不能伪装成事实。官方年报/季报属于“公司披露”，不是独立验证；只要是公司自述，claim kind 必须是 issuer_self_report，正文必须写“公司披露/年报自述/公告披露”。没有证据就写“输入未提供/证据不足”，不要猜。用户 JSON 里的 repair_feedback 是上一轮机器校验发现的阻断项；必须逐条修复，不得只换 marker 或删掉 claims 来规避。

写作目标：定位要有锋芒，必须指出资产角色、核心矛盾和兑现程度；用具体业务、团队、时间线和财务因果链支撑判断；最后用白话告诉读者这是什么样的资产、靠什么赢、代价是什么、什么会证伪。你必须保留独特、aggressive 的 AI 定位（例如“绝对龙头”“强定价权”“品牌护城河”“精密制造杂货铺”等），但把它作为 judgment 写入 claims，引用相关底层 evidence，并在同一句放 `[J-xx]`，给出 falsifier；不要把这些判断改写成公司披露或页级事实。可以有鲜明词汇，但不能把公司自述包装成事实，不能用未经证据支持的客户、订单、排名、份额、估值、股价或目标价。若用户 JSON 提供 prior_dossier，先保留其中已被证据支持的具体内容，再做定点修复和扩写；不要因为修复一个标记而删除整章或把完整报告缩成摘要。

篇幅和结构不是摘要：请贴近输入 JSON 标注的 Round 7 V4 参考档案（总正文约 2429 字）。用户 JSON 的 length_contract 是硬验收，不是建议：总正文少于 2200 字或任一章低于其中的 per_section_min 就是失败。七章都必须有实质内容，不能用空泛同义句填充；每章至少包含一个具体证据或一个明确缺口；当材料不足时，写出缺口、为什么不能判断、下一步要验证什么。

硬规则：
1. 每个事实/数字都要在 claims 中列出 evidence_ids；evidence_ids 只能来自输入包；数字必须和 cited evidence 的 quoted_anchor/事实 value+unit 一致。官方表格的单位可能在表头而不在 quoted_anchor 中，此时沿用输入 evidence 的 unit，不要自行换算或补造精度。derived_metrics 的增长/下滑方向和幅度是确定性输入，模型不得自行计算。引用一个 derived_metric 时，evidence_ids 必须同时包含它的 current_evidence_id 和 previous_evidence_id，不能只引当前值。任何分析假设中的数字（例如利率冲击阈值）若未在 packet 中出现就不要写；可以改写为不带未经证据支持的数字的条件句。
2. 只要 claim 引用了 derived_metrics，就必须在 claim text 中同时写方向（增长/下滑/持平）和幅度（百分比或绝对差额），并填写 derived_ids。历史已披露实际值不得作为“如果……那么……”的结论；条件句只写未来/待验证假设。
3. judgement 必须有证据 refs 和 falsifier；issuer_self_report 必须有显式自述措辞（如“公司披露”“年报自述”“公告披露”“年报引/年报提及”），且正文在同一完整句中保留对应的公司/年报归因；gap 必须说明具体缺口。不要把同一个 claim 同时标成多个概念：每条 claim 只选一个 kind。
4. 不得输出目标价数字、仓位、买卖/加减仓/止损或执行动作；可以在 gap 中明确说明“未提供目标价/估值证据缺失”，但不能给出任何目标价或行动建议。
5. 每个正文段落和最新数据卡中的事实后面放 `[F-01]`、判断放 `[J-01]`、公司自述放 `[C-01]`、缺口放 `[G-01]`，且这些 marker 必须与 claims.claim_id 完全对应。所有非 gap claims 都必须在正文中出现一次；所有 aggressive 定位句、overall_conclusion 也必须带对应 marker。不要输出 [S] source marker，Sources 由渲染器根据 packet 生成。
6. 只输出 JSON，不要 Markdown code fence。章节顺序必须严格是：
   one_line_position / founder_team / timeline / technology_products / financial_valuation / risks_commentary / plain_language。

返回 JSON：
{
  "latest_card": "带 claim markers 的一行最新数据卡；没有可靠最新财务就写输入未提供",
  "sections": [
    {"id":"one_line_position","title":"一句话定位","body":"...","claim_ids":["F-01","J-01"]},
    {"id":"founder_team","title":"创始人与团队","body":"...","claim_ids":[]},
    {"id":"timeline","title":"发展时间线","body":"...","claim_ids":[]},
    {"id":"technology_products","title":"技术与产品","body":"...","claim_ids":[]},
    {"id":"financial_valuation","title":"财务与估值","body":"...","claim_ids":[]},
    {"id":"risks_commentary","title":"风险与点评","body":"...","claim_ids":[]},
    {"id":"plain_language","title":"大白话结论","body":"...","claim_ids":[]}
  ],
  "claims": [
    {"claim_id":"F-01","kind":"fact","text":"...","evidence_ids":["..."],"derived_ids":[],"falsifier":""},
    {"claim_id":"J-01","kind":"judgment","text":"...","evidence_ids":["..."],"derived_ids":[],"falsifier":"..."},
    {"claim_id":"C-01","kind":"issuer_self_report","text":"公司披露……","evidence_ids":["..."],"derived_ids":[],"falsifier":""},
    {"claim_id":"G-01","kind":"gap","text":"输入未提供……","evidence_ids":[],"derived_ids":[],"falsifier":""}
  ],
  "missing_inputs": ["..."],
  "overall_conclusion": "不超过两句的研究判断，不含行动指令"
}
"""


def _model_evidence(packet: Mapping[str, Any], *, max_narrative: int = 42, max_facts: int = 32) -> list[dict[str, Any]]:
    narratives = [item for item in packet.get("evidence", []) if isinstance(item, Mapping) and item.get("metric") is None]
    facts = [item for item in packet.get("evidence", []) if isinstance(item, Mapping) and item.get("metric") is not None]
    # Keep each metric's newest pair, then fill with bounded narrative pages.
    by_metric: dict[str, list[dict[str, Any]]] = {}
    for fact in facts:
        by_metric.setdefault(str(fact.get("metric")), []).append(dict(fact))
    chosen_facts: list[dict[str, Any]] = []
    for metric, rows in sorted(by_metric.items()):
        rows = sorted(rows, key=lambda row: str(row.get("report_period") or ""), reverse=True)
        chosen_facts.extend(rows[: max(2, max_facts // max(1, len(by_metric)))])
    chosen_facts = chosen_facts[:max_facts]
    # The parser may retain a neighbouring balance-sheet header on a
    # validated income-statement row.  It is provenance for humans, not an
    # admissible input fact; withholding it prevents the model from promoting a
    # composite-page fragment into a new financial claim.
    def model_item(item: Mapping[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in dict(item).items() if key != "column_header_excerpt"}

    return [model_item(item) for item in chosen_facts] + [model_item(item) for item in narratives[:max_narrative]]


def build_request(packet: Mapping[str, Any], *, iteration: int = 0, repair_feedback: list[dict[str, Any]] | None = None, prior_dossier: Mapping[str, Any] | None = None) -> dict[str, Any]:
    packet_result = validate_evidence_packet(packet)
    if packet_result["status"] != "passed":
        raise ValueError(f"evidence packet failed validation: {packet_result['errors'][:2]}")
    model_packet = {
        "schema_version": packet.get("schema_version"),
        "ticker": packet.get("ticker"),
        "issuer_name": packet.get("issuer_name"),
        "evidence_cutoff": packet.get("evidence_cutoff"),
        "sources": packet.get("sources"),
        "evidence": _model_evidence(packet),
        "financial_facts": [
            {key: value for key, value in dict(item).items() if key != "column_header_excerpt"}
            for item in packet.get("financial_facts") or []
            if isinstance(item, Mapping)
        ],
        "derived_metrics": packet.get("derived_metrics"),
        "gaps": packet.get("gaps"),
        "truth_boundary": packet.get("truth_boundary"),
    }
    return {
        "request_schema": "editorial-v4-generation-request-v1",
        "prompt_version": PROMPT_VERSION,
        "generator_version": GENERATOR_VERSION,
        "iteration": iteration,
        "input_packet_hash": packet.get("packet_hash"),
        "model_packet_hash": canonical_hash(model_packet),
        "model_packet": model_packet,
        "repair_feedback": repair_feedback or [],
        "length_contract": {
            "total_body_chars_min": 2200,
            "total_body_chars_target": 2429,
            "per_section_min": {
                "one_line_position": 100,
                "founder_team": 100,
                "timeline": 300,
                "technology_products": 400,
                "financial_valuation": 350,
                "risks_commentary": 350,
                "plain_language": 150,
            },
            "paragraphs_per_section_min": 2,
        },
        "prior_dossier": (
            {
                key: prior_dossier.get(key)
                for key in ("latest_card", "sections", "claims", "missing_inputs", "overall_conclusion")
                if key in prior_dossier
            }
            if prior_dossier else None
        ),
    }


def _normalise_result(raw: Mapping[str, Any], packet: Mapping[str, Any], provider_receipt: Mapping[str, Any], request: Mapping[str, Any], run_id: str) -> dict[str, Any]:
    result = deepcopy(dict(raw))
    result["schema_version"] = EDITORIAL_V4_SCHEMA
    result["ticker"] = str(packet["ticker"]).upper()
    result["issuer_name"] = packet.get("issuer_name")
    result["input_packet_hash"] = packet.get("packet_hash")
    result["prompt_version"] = PROMPT_VERSION
    result["generation_receipt"] = {
        "run_id": run_id,
        "provider": "DeepSeek",
        "model": provider_receipt.get("model") or DEFAULT_MODEL,
        "request_id": provider_receipt.get("request_id"),
        "usage": provider_receipt.get("usage") or {},
        "finish_reason": provider_receipt.get("finish_reason"),
        "prompt_version": PROMPT_VERSION,
        "request_hash": canonical_hash(request),
        "response_hash": hashlib.sha256(json.dumps(raw, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest(),
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }
    result["production_record"] = {
        "run_id": run_id, "generator_version": GENERATOR_VERSION, "prompt_version": PROMPT_VERSION,
        "model_provider": "DeepSeek", "model": provider_receipt.get("model") or DEFAULT_MODEL,
        "request_id": provider_receipt.get("request_id"), "input_packet_sha256": packet.get("packet_hash"),
        "model_packet_sha256": request.get("model_packet_hash"), "review_status": "pending",
        "editorial_status": "draft", "action_state": "blocked", "tier_credit": False,
    }
    result["sources"] = packet.get("sources", [])
    result["boundary"] = {"review_only": True, "no_tier_credit": True, "no_b6_credit": True, "no_decision_policy_credit": True, "no_publication_credit": True}
    return result


def generate_once(packet: Mapping[str, Any], *, key_file: Path = DEFAULT_KEY_FILE, model: str = DEFAULT_MODEL, iteration: int = 0, repair_feedback: list[dict[str, Any]] | None = None, prior_dossier: Mapping[str, Any] | None = None, reasoning_effort: str = "high", max_tokens: int = 22000, thinking_type: str = "enabled", transport: Any = None) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    request = build_request(packet, iteration=iteration, repair_feedback=repair_feedback, prior_dossier=prior_dossier)
    raw, provider_receipt = call_structured_deepseek(system_prompt=SYSTEM_PROMPT, request_object=request, key_file=key_file, model=model, max_tokens=max_tokens, reasoning_effort=reasoning_effort, temperature=0.1, thinking_type=thinking_type, transport=transport)
    run_id = f"editorial-v4-run:{provider_receipt.get('request_id') or canonical_hash(request)[:24]}"
    result = _normalise_result(raw, packet, provider_receipt, request, run_id)
    return result, provider_receipt, request


def write_draft(result: Mapping[str, Any], out_dir: Path) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = dict(result)
    payload_hash = canonical_hash(payload)
    json_path = out_dir / "report.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"json_path": str(json_path), "report_hash": payload_hash}
