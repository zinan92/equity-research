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


PROMPT_VERSION = "editorial-v4-whole-report-prompt-v3"
GENERATOR_VERSION = "editorial-v4-whole-report-generator-v3"


SYSTEM_PROMPT = """你是 Park Equity Research 的资深中文研究员。你要把一个已经冻结的、官方 PDF 页级绑定的 evidence packet 写成一篇爱牛式 V4 读者报告。

这是一次全报告调用。只允许使用用户 JSON 中的 evidence、derived_metrics 和 gaps；不得联网，不得调用外部知识，不得读取旧报告、模板或 benchmark。任何年份、历史沿革、客户、价格、产能、排名、份额等事实只要没有对应的输入 evidence，就必须删掉或写成 gap；不能凭模型记忆补全。行业地位、护城河、管理风格和市场反应可以作为 aggressive judgment，但必须写入 judgment claim、引用相关底层 evidence、带 `[J-xx]` 和 falsifier，不能伪装成事实。官方年报/季报属于“公司披露”，不是独立验证；只要是公司自述，claim kind 必须是 issuer_self_report，正文必须写“公司披露/年报自述/公告披露”。第三方统计（例如 Euromonitor/欧睿、产业在线、奥维云网、MIR 睿工业）如果只出现在公司年报中，必须写成“年报引……数据/公司披露年报引用……”，不能写成“根据某第三方数据”而让读者误以为输入含有该第三方原始报告。没有证据就写“输入未提供/证据不足”，不要猜；gap 只能说明材料缺失，不得夹带“公开资料显示”等未绑定事实。用户 JSON 里的 repair_feedback 是上一轮机器校验发现的阻断项；必须逐条修复，不得只换 marker 或删掉 claims 来规避。

修复执行：repair_feedback 是上一轮机器校验发现的阻断项，必须逐条修复，不得只换 marker 或删掉 claims 来规避。若 repair_directives 指出某章低于字数下限，必须在该章新增有证据支撑的完整段落（证据链、经营因果、缺口或待验证问题），把该章补到下限以上；不能原样复制 prior_dossier，也不能以“材料不足”为由保持短章。修复请求的首要目标是同时满足所有 section_min 与 total_body_chars_min。

写作目标：定位要有锋芒，必须指出资产角色、核心矛盾和兑现程度；用具体业务、团队、时间线和财务因果链支撑判断；最后用白话告诉读者这是什么样的资产、靠什么赢、代价是什么、什么会证伪。你必须保留独特、aggressive 的 AI 定位（例如“绝对龙头”“强定价权”“品牌护城河”“精密制造杂货铺”等），但把它作为 judgment 写入 claims，引用相关底层 evidence，并在同一句放 `[J-xx]`，给出 falsifier；不要把这些判断改写成公司披露或页级事实。可以有鲜明词汇，但不能把公司自述包装成事实，不能用未经证据支持的客户、订单、排名、份额、估值、股价或目标价。若用户 JSON 提供 prior_dossier，先保留其中已被证据支持的具体内容，再做定点修复和扩写；若同时提供 repair_directives，必须逐条执行，尤其要把第三方统计的原始事实拆成 C claim，J claim 只保留研究综合判断；不要因为修复一个标记而删除整章或把完整报告缩成摘要。

篇幅和结构不是摘要：请贴近输入 JSON 标注的 Round 7 V4 参考档案（总正文约 2429 字）。用户 JSON 的 length_contract 是硬验收，不是建议：总正文少于 2200 字或任一章低于其中的 per_section_min 就是失败。七章都必须有实质内容，不能用空泛同义句填充；每章至少包含一个具体证据或一个明确缺口；当材料不足时，写出缺口、为什么不能判断、下一步要验证什么。

硬规则：
1. 每个事实/数字都要在 claims 中列出 evidence_ids；evidence_ids 只能来自输入包；数字必须和 cited evidence 的 quoted_anchor/事实 value+unit 一致。官方表格的单位可能在表头而不在 quoted_anchor 中，此时沿用输入 evidence 的 unit，不要自行换算或补造精度。负数利润/亏损可以写成“净亏损 885.56 亿元”等语义金额，括号负号由“亏损/净亏损”承担；不得把正数伪装成利润，且必须仍绑定原始负值 evidence。若把元/千元换成亿元/万元显示，只能按 evidence 的 unit 做确定性换算并保留 derived_ids（比较数字必须绑定 derived_metrics），不得自行计算新指标。derived_metrics 的增长/下滑方向和幅度是确定性输入，模型不得自行计算。引用一个 derived_metric 时，evidence_ids 必须同时包含它的 current_evidence_id 和 previous_evidence_id，不能只引当前值。任何分析假设、证伪阈值或条件句中的数字（例如利率冲击阈值、份额下限）若未在 packet 中出现就不要写；改写为不带未经证据支持的数字的条件句。最新数据卡中的每个数字必须和该句中显示的事实 claim marker 一一对应，不能只挂增长 claim 而漏掉当期值 claim。
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
    feedback = repair_feedback or []
    directives: list[str] = []
    for item in feedback:
        code = str(item.get("code") or "")
        claim_id = str(item.get("claim_id") or "")
        if code == "third_party_attribution_missing":
            directives.append(f"{claim_id or '相关 claim'}：把第三方统计的原文事实拆成 issuer_self_report 的 C claim；正文先写‘公司披露/年报引……数据’，再写提供者和数字；J claim 只保留基于这些 C/F facts 的研究判断，不要在 J claim 中复述第三方数字。")
        elif code in {"judgment_numeric_unbound", "numeric_claim_unbound", "judgment_specific_unbound"}:
            if claim_id == "J-20" and code == "numeric_claim_unbound":
                directives.append("J-20：必须删除‘归母净利率由14.0%提升至17.0%’这一整条自算利润率判断；输入包没有净利率 derived metric，不能保留14.0%或17.0%，改写为不含任何净利率数字的定性判断，或删除该 claim 及其 marker。")
            else:
                directives.append(f"{claim_id or '相关 claim'}：删除未出现在该 claim 引用页中的数字、阈值或具体市场/业务事实（如批价、黄牛价、客户、订单、份额、估值），或改引包含它的 evidence；没有页级依据时改成不带具体事实的定性证伪条件，不要用别的 claim 的材料来闭包。")
        elif code in {"body_numeric_unbound", "latest_card_numeric_closure"}:
            directives.append(f"{claim_id or '当前句'}：让句内数字紧邻并绑定包含该数字的 F/C claim marker；最新数据卡同时挂当期值和同比方向两个 claim，不能只挂增长 claim。")
        elif code == "comparison_direction_missing":
            directives.append(f"{claim_id or '相关 claim'}：若保留 derived_ids，正文必须明确写 deterministic 输入给出的增长/下滑/持平方向及幅度；若改成纯定性判断，就删除 derived_ids 和比较性措辞，不要留下无方向的派生引用。")
        elif code in {"self_report_body_unmarked", "self_report_unmarked", "self_report_not_attributed"}:
            directives.append(f"{claim_id or '相关公司披露'}：在正文同一句、数字或第三方名称之前明确写‘公司披露/年报自述/年报引’，不得只在 claim registry 里标记。")
        elif code in {"numeric_quote_mismatch", "numeric_mismatch"}:
            directives.append(f"{claim_id or '相关 claim'}：删除证据锚文本没有的数字，或改为被引用页逐字/单位换算可闭包的数字；不要四舍五入到无法验证的精度。")
        elif code == "claim_refs":
            directives.append(f"{claim_id or '相关 claim'}：evidence_ids 只能填写输入 packet 中真实存在的 evidence_id；不要把 C-/J-/F- claim_id 当作 evidence_id。若没有页级证据，把内容改成 gap，而不是伪造引用。")
        elif code in {"derived_refs", "derived_binding"}:
            directives.append(f"{claim_id or '相关 claim'}：derived_ids 只能填写 packet 中的 deterministic derived_id，并同时引用该 derived metric 的 current_evidence_id 与 previous_evidence_id；不能自行计算或借用别的 claim。")
        elif code in {"evidence_id_mismatch", "evidence_id_not_found", "missing_evidence_id"}:
            directives.append(f"{claim_id or '相关 claim'}：逐项从当前输入 packet 复制真实存在的完整 evidence_id（包括 official/document 前缀）；不得缩短、猜测或把来源页码拼成不存在的 ID。若 packet 没有对应页级证据，改成 gap 或删除该具体事实。")
        elif str(item.get("category") or "").lower() == "provenance" or code.upper().startswith("E"):
            directives.append(f"{claim_id or '相关 claim'}：逐字核对 cited evidence 的 quoted_anchor；删除该页没有的具体词/数字，或改用包含该表述的正确页级 evidence。不要用语义相近但页内没有的改写冒充可核验事实。")
        elif code == "overall_judgment_marker_missing":
            directives.append("所有锋利定位、核心矛盾和白话结论判断都要有对应 [J-xx] claim、底层 refs 和 falsifier；overall_conclusion 也要带 marker。")
        elif code == "gap_unbound_source":
            directives.append(f"{claim_id or '相关 gap'}：只写输入包缺少什么、为什么不能判断和下一步验证，不要写‘公开资料显示/公开信息称’等无 refs 的事实。")
        elif code == "historical_condition":
            directives.append(f"{claim_id or '相关 claim'}：已披露历史实际值改为陈述句；条件句只保留未来或待验证假设。")
        elif code == "section_short":
            section = str(item.get("section") or "该章")
            minimum = item.get("minimum") or "合同下限"
            directives.append(f"{section}：当前正文只有 {item.get('chars', '未知')} 字，低于 {minimum} 字；在保留现有具体证据和 aggressive [J] 定位的前提下，补充同一章的证据链、因果解释、缺口边界和待验证问题，禁止用空泛重复句凑字数。")
        elif code == "dossier_short":
            directives.append("整篇正文低于 Round 7 V4 篇幅合同；逐章补足具体官方 evidence、财务因果、风险证伪和白话解释，保留 aggressive [J] 判断，不要删章、压缩成摘要或用无证据数字扩写。")
        elif code == "judgment_marker_missing":
            excerpt = str(item.get("excerpt") or "").strip()
            target_ids = []
            if prior_dossier and excerpt:
                for prior_claim in prior_dossier.get("claims") or []:
                    if not isinstance(prior_claim, Mapping):
                        continue
                    claim_text = str(prior_claim.get("text") or "")
                    if excerpt[:24] and excerpt[:24] in claim_text:
                        target_ids.append(str(prior_claim.get("claim_id") or ""))
            marker_hint = f"对应 marker 为 [{target_ids[0]}]" if target_ids and target_ids[0] else "对应已有的 [J-xx] marker"
            directives.append(f"机器指出以下句子缺少同句判断标记：{excerpt or '见上一轮错误'}。必须把 {marker_hint} 直接放在这一个句子的末尾（不要只放在后一个句子或段落末尾），保留 aggressive 词汇；对应 judgment claim 仍须有底层 evidence_ids 与 falsifier。")
        elif code == "overall_judgment_marker_missing":
            directives.append("overall_conclusion 必须保留研究判断并在同一句加已有 [J-xx] 或 [F-xx] marker；不要删除结论来规避门禁，也不要加入行动指令。")
        elif code in {"claim_not_rendered", "orphan_marker", "claim_identity"}:
            directives.append(f"{claim_id or 'claims registry'}：每条非 gap claim 必须在对应正文中出现且只使用真实 [F/C/J-xx] marker；把遗漏的 marker 补回对应句，或删除没有正文与证据支撑的重复 registry 行，不能留下未渲染 claim。")
    return {
        "request_schema": "editorial-v4-generation-request-v2",
        "prompt_version": PROMPT_VERSION,
        "generator_version": GENERATOR_VERSION,
        "iteration": iteration,
        "input_packet_hash": packet.get("packet_hash"),
        "model_packet_hash": canonical_hash(model_packet),
        "model_packet": model_packet,
        "repair_feedback": feedback,
        "repair_directives": directives,
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
