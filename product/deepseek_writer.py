from __future__ import annotations

import argparse
from copy import deepcopy
import json
import os
import re
import ssl
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from data_store import DB_PATH
from company_research import CROSS_COMPANY_PROMPT_VERSION
from research_artifact_store import PROMPT_VERSION, artifact_path, load_artifact, write_artifact
from research_evidence import load_evidence_set
from research_reports import build_evidence_pack, report_payload, research_logic_hash, research_profile_hash, writer_logic_hash


API_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_KEY_FILE = Path.home() / ".park-secrets" / "deepseek" / "api-key"
DEFAULT_MODEL = "deepseek-v4-pro"
SECTION_KEYS = (
    "industry_chain",
    "business_quality",
    "competitive_moat",
    "financial_quality",
    "valuation_debate",
    "risk_falsification",
)
VALIDATION_VERSION = "metric-source-v2"
EDITORIAL_RULES = (
    {
        "id": "receivables_not_observed",
        "before": "应收与库存同步上升。",
        "after": "库存同比上升，应收是否同步恶化仍需下一份正式财报验证。",
        "reason": "证据包确认库存上升，但没有提供应收账款当前同比变化。",
    },
    {
        "id": "no_automatic_stop_loss",
        "before": "若恶化则严格止损。",
        "after": "若验证条件恶化，则不再加仓并重新审查基准假设。",
        "reason": "产品提供研究仓位条件，不连接券商，也不生成自动止损指令。",
    },
    {
        "id": "quarterly_segment_driver_unproven",
        "before": "动力电池出货为主要驱动。",
        "after": "最新季度缺少分产品拆分，具体增长驱动仍待正式披露验证。",
        "reason": "当前冻结证据没有最新季度的分产品增长归因。",
    },
    {
        "id": "quarterly_segment_driver_unproven_detail",
        "before": "主要受动力电池出货量大幅提升驱动。",
        "after": "但当前冻结证据没有最新季度分产品数据，具体驱动仍待正式披露验证。",
        "reason": "当前冻结证据没有最新季度的分产品增长归因。",
    },
    {
        "id": "mou_not_delivery",
        "before": "储能和海外订单的持续交付。",
        "after": "储能合作计划推进及后续实际订单验证。",
        "reason": "冻结证据只有合作备忘录，不等同于确认订单或收入。",
    },
    {
        "id": "mou_not_confirmed_order",
        "before": "海外储能订单超预期放量",
        "after": "海外储能合作计划推进并转化为可核验订单",
        "reason": "冻结证据只有合作备忘录，不等同于确认订单或收入。",
    },
    {
        "id": "credit_sales_is_hypothesis",
        "before": "强劲的利润增长或部分源自激进的信用销售或提前备货，这会在后续季度形成回款与去库存压力。",
        "after": "需核验这种背离是否与信用期变化或备货有关；只有后续同时出现回款与去库存压力时，才应下修盈利质量。",
        "reason": "当前证据没有信用期变化或提前备货的直接事实。",
    },
    {
        "id": "customer_concentration_not_binding",
        "before": "主要客户贡献显著比例收入，深度绑定头部车企，形成稳固的订单基本盘。",
        "after": "主要客户贡献显著比例收入，只能确认客户集中度较高；是否形成稳定订单仍需订单与客户续约证据。",
        "reason": "前五大客户收入占比不能单独证明深度绑定或未来订单稳定。",
    },
    {
        "id": "ess_long_term_growth_unproven",
        "before": "已连续多年高速扩张",
        "after": "本期保持增长，长期增速仍需时间序列验证",
        "reason": "当前 evidence pack 没有支持连续多年高速增长的完整序列。",
    },
    {
        "id": "industry_leading_profitability_unproven",
        "before": "公司年度净资产收益率和净利率均处行业领先水平",
        "after": "公司年度净资产收益率和净利率构成当前盈利质量基线，但缺少同行样本，不能判断行业排名",
        "reason": "冻结证据没有同行盈利指标。",
    },
    {
        "id": "profitability_does_not_prove_moat",
        "before": "年度净资产收益率、毛利率和净利率均显示其制造业成本优势和产品溢价",
        "after": "年度净资产收益率、毛利率和净利率构成盈利质量观察基线，但不能单凭这些指标推断成本优势或产品溢价",
        "reason": "单公司财务指标不能独立证明相对成本优势或产品溢价。",
    },
    {
        "id": "industry_average_not_in_evidence",
        "before": "大致与公司历史增速及行业平均水平匹配",
        "after": "仍需结合后续盈利兑现验证；当前冻结证据未提供行业平均水平",
        "reason": "冻结证据没有行业平均估值或增速数据。",
    },
    {
        "id": "ess_margin_direction_corrected",
        "before": "储能利润率不如动力",
        "after": "储能毛利率高于动力，但其收入体量仍较小",
        "reason": "冻结年报显示储能毛利率高于动力电池。",
    },
    {
        "id": "unfrozen_iea_claim",
        "before": "IEA数据表明新电池工厂达产通常需多年时间，进度可能慢于国内。",
        "after": "海外工厂爬坡进度仍需以后续产能利用率和项目披露持续验证。",
        "reason": "IEA 页面未进入当前冻结 evidence set。",
    },
    {
        "id": "battery_price_trend_unproven",
        "before": "电芯价格仍呈下行趋势，毛利率能否维持取决于制造效率提升和材料成本下降的赛跑。",
        "after": "下游降本压力可能向上传导，但当前冻结证据没有电芯价格序列；毛利率能否维持仍需后续财报验证。",
        "reason": "冻结证据没有电芯价格时间序列。",
    },
    {
        "id": "integration_premium_unproven",
        "before": "系统集成端的CTP与定制化方案虽可提供溢价，但随着标准化推进，溢价空间也在收窄。",
        "after": "系统集成端的定制化能力是否形成可持续溢价，当前证据不足，需结合分产品毛利和客户续约继续验证。",
        "reason": "冻结证据没有系统集成溢价或其变化趋势。",
    },
    {
        "id": "market_credit_view_unproven",
        "before": "市场担忧公司可能以放宽信用或增加备货来换取出货增长，若后续经营性现金流无法同步改善，看似强劲的利润增长将缺乏现金内涵。",
        "after": "信用期变化或备货是否参与解释当前背离，现有证据不足；若后续经营性现金流无法同步改善，利润增长的现金内涵需要下修。",
        "reason": "冻结证据没有市场调查、信用政策变化或备货成因。",
    },
    {
        "id": "profitability_causality_unproven",
        "before": "，反映了强议价能力和成本控制",
        "after": "",
        "reason": "单公司盈利指标不能直接证明议价能力或相对成本控制。",
    },
    {
        "id": "absolute_valuation_not_percentile",
        "before": "当前市盈率和市净率均处于较高水平，对于制造业龙头而言并不低廉，但也未出现显著泡沫。",
        "after": "当前市盈率和市净率只提供绝对估值读数；冻结证据没有历史分位或同行基准，不能据此判断高低或泡沫程度。",
        "reason": "冻结证据没有历史估值分位或同行比较。",
    },
    {
        "id": "investor_views_not_observed",
        "before": "市场分歧在于：部分投资者认为动力电池增速将放缓，储能毛利率高于动力，但其收入体量仍较小，且大规模资本开支将稀释回报；另一部分则相信全球电气化趋势和公司系统能力可支撑较长成长期，当前估值存在低估。",
        "after": "估值分歧可拆成两种待验证情景：谨慎情景关注动力增速放缓、扩产回报和储能体量；积极情景依赖份额稳定、储能增长及现金转化改善。二者均是研究假设，不代表已观察到的投资者观点。",
        "reason": "冻结证据没有投资者调查或市场观点样本。",
    },
    {
        "id": "segment_causality_separated",
        "before": "动力电池系统占据公司营收的绝大比例，且得益于全球电动车渗透率提升和市场份额扩大，该板块营收同比大幅增长，毛利率也在规模效应下小幅回升。储能电池系统作为另一增长极，营收增速虽不及动力，但受益于全球储能装机放量，本期保持增长，长期增速仍需时间序列验证，毛利率亦保持在较好水平。电池材料及回收业务受金属价格影响，营收下滑但毛利率较高，体现了其调节原材料成本的功能。矿产资源及其他业务体量尚小，财务影响有限。",
        "after": "年报显示动力电池系统是最大收入来源，该板块本期收入增长；储能系统本期同样增长且毛利率高于动力，但收入体量更小。冻结资料不足以把这些变化直接归因于渗透率、份额或规模效应。材料及回收本期收入下滑且毛利率较高，但其成本调节作用与矿产板块影响仍需更多分部和价格数据验证。",
        "reason": "分部财务事实与经营因果必须分开，当前证据不足以识别具体驱动。",
    },
    {
        "id": "new_app_commercialization_unproven",
        "before": "新应用场景如数据中心、船舶等正从验证走向小批量，尚未形成决定性的利润贡献。",
        "after": "数据中心、船舶等已被公司列为应用场景，但当前证据不足以判断其商业化阶段或利润贡献。",
        "reason": "冻结证据没有产量、客户或商业化阶段数据。",
    },
    {
        "id": "governance_role_not_personal_label",
        "before": "创始人集权的治理结构",
        "after": "创始人兼任董事长和总经理所形成的治理角色集中",
        "reason": "正式资料只支持治理角色集中，不支持人格化的集权标签。",
    },
    {
        "id": "balance_sheet_acceptability_unproven",
        "before": "资产负债率虽处于较高水平，但结合其重资产模式及扩大海外产能的资金需求，尚属可接受范围。经营活动现金流每股金额可观，表明正常年份造血能力强劲。",
        "after": "资产负债率是重资产扩产下的观察项；没有行业基准和表外承诺，不能判断其是否处于可接受区间。经营活动现金流每股构成当前观察基线，也不能单凭单期数据推断长期造血能力。",
        "reason": "冻结证据没有同行资本结构或长期现金流序列。",
    },
    {
        "id": "cash_gap_causes_are_hypotheses",
        "before": "这种背离可能源于季节性备货、海外项目集中交付或客户信用期调整，但若后续报告期出现类似信号，就不能简单归因于暂时性因素。",
        "after": "当前证据不能解释这种背离的成因；季节性、备货、项目交付或信用期变化都只能作为待排查假设，需用后续附注和周转指标验证。",
        "reason": "冻结证据没有现金流背离的成因拆分。",
    },
    {
        "id": "manufacturing_leadership_needs_peer_data",
        "before": "公司已投产的电池产能规模全球居首，且产能利用率保持在极高水平，这带来的不仅是规模成本优势，更是工艺经验与良率控制的数据壁垒。",
        "after": "年报披露了大规模电池产能与较高产能利用率，这支持其规模制造能力；但相对成本优势和良率数据壁垒仍需同行成本与良率证据验证。",
        "reason": "冻结证据没有全球产能排名、同行单位成本或良率比较。",
    },
    {
        "id": "resource_volatility_scope_limited",
        "before": "但锂资源价格历史波幅极大，地缘政治和矿产开发周期仍可能阶段性冲击成本与供应安全。",
        "after": "原材料价格、地缘政治和矿产开发周期被公司列为风险，但当前证据没有价格序列来量化冲击幅度。",
        "reason": "冻结证据没有锂资源价格历史序列。",
    },
    {
        "id": "yield_leadership_unproven",
        "before": "凭借超级拉线和极限制造，良率与一致性持续领先，规模化降本效应显著。",
        "after": "公司将超级拉线和极限制造作为制造能力，但冻结证据未提供同行良率或单位成本，领先程度与降本效果仍需验证。",
        "reason": "冻结证据没有同行良率或单位成本比较。",
    },
    {
        "id": "scenario_not_valuation_label",
        "before": "基于情景假设的估值分析显示，当前市盈率处于合理但非低估区间，基准情景下相对现价提供温和上行空间。",
        "after": "情景估值显示基准假设相对现价提供温和上行空间，但结果来自盈利与倍数假设，不能据此形成历史或同行低估判断。",
        "reason": "情景估值不是历史分位或同行估值证据。",
    },
    {
        "id": "market_reaction_not_observed",
        "before": "市场亦可能转向更谨慎的估值倍数",
        "after": "估值模型中的合理倍数假设可能需要下修",
        "reason": "冻结证据没有市场参与者观点或未来反应证据。",
    },
    {
        "id": "risk_disclosure_scope_separated",
        "before": "原材料价格、地缘政治和矿产开发周期被公司列为风险，但当前证据没有价格序列来量化冲击幅度。",
        "after": "公司明确列出原材料价格与供应风险；地缘变化和矿产开发周期只作为分析师待验证情景，当前证据不足以量化其影响。",
        "reason": "年报风险章节没有把地缘政治和矿产开发周期列为同一项正式风险。",
    },
    {
        "id": "overseas_labor_culture_unproven",
        "before": "但海外建厂面临地缘政策、劳工文化等额外复杂性",
        "after": "但海外建厂面临政策与执行复杂性",
        "reason": "冻结证据没有劳工文化相关资料。",
    },
    {
        "id": "valuation_conclusion_not_market_view",
        "before": "当前估值隐含市场成长顾虑，基准情景提供温和上行空间，但高度依赖盈利兑现与风险偏好。",
        "after": "情景估值对成长兑现和合理倍数假设敏感；基准情景提供温和上行空间，但不代表已观察到市场观点。",
        "reason": "冻结证据没有历史分位、同行基准或投资者观点调查。",
    },
    {
        "id": "market_compensation_not_deterministic",
        "before": "市场将被迫为盈利质量安全系数要求补偿，从而压制估值中枢。",
        "after": "盈利质量折价可能压制估值中枢。",
        "reason": "未来市场行为只能写成条件情景，不能写成确定性反应。",
    },
    {
        "id": "downstream_pressure_deduplicated",
        "before": "但下游车企降本压力向上传导，下游降本压力可能向上传导",
        "after": "下游降本压力是否向上传导仍需价格和毛利率序列验证",
        "reason": "删除重复表述，并把未证实因果改为待验证判断。",
    },
    {
        "id": "base_case_language_fixed",
        "before": "盈利实现中速度提升",
        "after": "盈利保持中速增长",
        "reason": "修正语病。",
    },
)


def build_cross_company_frozen_request(
    packet: dict[str, Any], *, model: str = DEFAULT_MODEL,
    prompt_version: str = CROSS_COMPANY_PROMPT_VERSION,
    snapshot_binding: dict[str, str],
) -> dict[str, Any]:
    """Build the only permitted M4 model input: an integrity-checked frozen pack.

    This function performs no network call.  The caller may send the returned
    object to DeepSeek only after preserving its input_identity in the receipt.
    """
    from company_research import frozen_model_input

    return frozen_model_input(
        packet, model=model, prompt_version=prompt_version, snapshot_binding=snapshot_binding,
    )


def validate_cross_company_narrative(
    narrative: dict[str, Any], frozen_request: dict[str, Any],
) -> dict[str, Any]:
    """Validate M4 prose against exactly the frozen request sent to the model."""
    from report_contract import validate_public_ai_narrative

    errors = validate_public_ai_narrative(narrative)
    source_ids = {
        item["id"] for item in frozen_request["frozen_evidence"].get("documents") or []
    }
    cited: set[str] = set()
    blocks = [narrative.get("executive_summary"), *((narrative.get("sections") or {}).values()), narrative.get("investment_committee")]
    for index, block in enumerate(blocks):
        if not isinstance(block, dict):
            errors.append(f"narrative block {index} must be an object")
            continue
        refs = block.get("source_ids")
        if not isinstance(refs, list) or not refs:
            errors.append(f"narrative block {index} requires source_ids")
            continue
        unknown = set(refs) - source_ids
        if unknown:
            errors.append(f"narrative block {index} cites unknown source IDs: {sorted(unknown)}")
        cited.update(set(refs) & source_ids)
    narrative_text = " ".join(_visible_texts(narrative))
    if len(re.findall(r"[\u4e00-\u9fff]", narrative_text)) < 80:
        errors.append("model narrative must be substantive Simplified Chinese")
    for term in ("买入", "卖出", "加仓", "减仓", "清仓", "满仓", "重仓", "止损", "仓位", "持仓"):
        if term in narrative_text:
            errors.append(f"model narrative contains forbidden execution language: {term}")
    if re.search(r"https?://|www\.", narrative_text, re.IGNORECASE):
        errors.append("model narrative may not introduce URLs")
    numeric_tokens = sorted(set(re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?\s*%?", narrative_text)))
    if numeric_tokens:
        errors.append(
            "model narrative must not contain numeric literals; deterministic report components own metrics: "
            + ", ".join(token.strip() for token in numeric_tokens)
        )
    chinese_quantity = re.findall(
        r"(?:百分之[零〇一二两三四五六七八九十百千万亿点]+|"
        r"[零〇一二两三四五六七八九十百千万亿点]+(?:个百分点|倍|元|亿元|年|日|期|季|月|周|成))",
        narrative_text,
    )
    if chinese_quantity:
        errors.append(
            "model narrative must not contain Chinese-number quantities: "
            + ", ".join(sorted(set(chinese_quantity)))
        )
    return {
        "status": "passed" if not errors else "needs_review",
        "errors": sorted(set(errors)),
        "cited_source_count": len(cited),
        "available_source_count": len(source_ids),
        "input_identity": frozen_request["input_identity"],
    }


def generate_cross_company_narrative(
    packet: Any,
    key_file: Path,
    *,
    model: str = DEFAULT_MODEL,
    prompt_version: str = CROSS_COMPANY_PROMPT_VERSION,
    snapshot_binding: dict[str, str],
    transport: Any = None,
) -> dict[str, Any]:
    """Run the M4 DeepSeek path with no input beyond the frozen request.

    ``transport`` exists for deterministic contract tests.  Production leaves it
    unset and uses the same DeepSeek endpoint as the existing writer.
    """
    frozen_request = build_cross_company_frozen_request(
        packet, model=model, prompt_version=prompt_version, snapshot_binding=snapshot_binding,
    )
    shape = {
        "report_title": "string without numeric literals",
        "executive_summary": {
            "conclusion": "string", "paragraphs": ["substantive string", "substantive string"],
            "source_ids": ["document id from frozen_evidence"],
        },
        "sections": {
            key: {
                "title": "string", "conclusion": "string",
                "paragraphs": ["substantive string", "substantive string"],
                "source_ids": ["document id from frozen_evidence"],
            }
            for key in (
                "industry_chain", "business_quality", "competitive_moat",
                "financial_quality", "valuation_debate", "risk_falsification",
            )
        },
        "investment_committee": {
            "bull_case": "string", "base_case": "string", "bear_case": "string",
            "source_ids": ["document id from frozen_evidence"],
        },
    }
    system = (
        "You are an institutional equity-research editor. Return only one JSON object with exactly "
        "the supplied output_shape keys. Use only frozen_evidence and cite its document ids on every "
        "block. Do not introduce URLs. Do not write any Arabic digits, percentages, years, quantities, "
        "or Chinese-number quantities in any human-readable narrative field; deterministic report components "
        "own all metrics. Source_ids are the sole exception: preserve those machine identifiers exactly. "
        "Write the entire narrative in professional Simplified Chinese. "
        "Treat frozen_evidence.limitations as hard prohibitions. A legal source id is not proof that the "
        "source entails a sentence: every factual assertion must be directly supported by the cited excerpt. "
        "Every sentence must be either a direct paraphrase of an excerpt, an explicitly conditional scenario "
        "using only source-supported variables, or exactly Missing evidence. Do not infer causality from a "
        "change, and do not infer quality from scale. Words such as stable, strong, leading, ample, advantage, "
        "moat, control, safe, reasonable valuation, or their Chinese equivalents require direct comparative "
        "evidence. Investment-committee cases are hypotheses, not permission to fill evidence gaps. "
        "If a limitation prohibits a concept anywhere in the report, omit it or write Missing evidence. "
        "Do not turn management targets into achieved advantages, operating cash flow into free cash flow, "
        "a memorandum into a contract, or market share into customer lock-in. Do not claim peer superiority, "
        "moat strength, current valuation, safety margin, or liquidity coverage without direct comparative, "
        "valuation, or financing evidence. Unsupported sections must explicitly say Missing evidence. "
        "Write Missing evidence when support is absent. Do not add markdown or extra keys."
    )
    frozen_request_with_shape = {**frozen_request, "output_shape": shape}
    user = json.dumps(frozen_request_with_shape, ensure_ascii=False, sort_keys=True)
    api_payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "response_format": {"type": "json_object"},
        "temperature": 0.1,
    }
    key = _read_secret(key_file)
    def send(payload: dict[str, Any]) -> dict[str, Any]:
        if transport is not None:
            return transport(deepcopy(payload), key)
        for attempt in range(3):
            request = urllib.request.Request(
                API_URL,
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=180) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                if exc.code not in {429, 500, 502, 503, 504}:
                    detail = exc.read().decode(errors="replace")[:500]
                    raise RuntimeError(f"cross-company DeepSeek HTTP {exc.code}: {detail}") from exc
                failure: Exception = exc
            except (urllib.error.URLError, TimeoutError, ssl.SSLError) as exc:
                failure = exc
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(
            f"cross-company DeepSeek unavailable after retries: {type(failure).__name__}"
        ) from failure

    def unpack(response_payload: dict[str, Any]) -> tuple[Any, str, dict[str, Any]]:
        if isinstance(response_payload, dict) and "choices" in response_payload:
            raw_content = response_payload["choices"][0]["message"]["content"]
            return (
                json.loads(raw_content) if isinstance(raw_content, str) else raw_content,
                response_payload.get("model") or model,
                response_payload.get("usage") or {},
            )
        return response_payload, model, {}

    response_payload = send(api_payload)
    narrative, response_model, usage = unpack(response_payload)
    if not isinstance(narrative, dict):
        raise RuntimeError("cross-company DeepSeek response is not a JSON object")
    validation = validate_cross_company_narrative(narrative, frozen_request)
    receipts = [{"purpose": "draft", "model": response_model, "usage": usage}]
    for repair_index in range(2):
        if validation["status"] == "passed":
            break
        repair_payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps({
                    "task": (
                        "Repair the rejected draft. Return the exact output_shape only. "
                        "Remove every numeric literal from every human-readable prose field, including dates. "
                        "Before returning, verify that no prose string contains an Arabic digit. Preserve every "
                        "source_ids value exactly because those are machine identifiers, not prose."
                    ),
                    "validation_errors": validation["errors"],
                    "rejected_draft": narrative,
                    "request": frozen_request_with_shape,
                }, ensure_ascii=False, sort_keys=True)},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
        }
        repaired_payload = send(repair_payload)
        narrative, response_model, usage = unpack(repaired_payload)
        if not isinstance(narrative, dict):
            raise RuntimeError("cross-company DeepSeek repair is not a JSON object")
        validation = validate_cross_company_narrative(narrative, frozen_request)
        receipts.append({
            "purpose": f"schema_and_fact_repair_{repair_index + 1}",
            "model": response_model, "usage": usage,
        })
    artifact = {
        "artifact_version": "cross-company-narrative-v1",
        "provider": "DeepSeek", "model": response_model, "prompt_version": prompt_version,
        "input_identity": frozen_request["input_identity"],
        "evidence_manifest_hash": frozen_request["frozen_evidence"]["manifest_hash"],
        "prompt_hash": _canonical_hash({"system": system, "user": user}),
        "narrative_hash": _canonical_hash(narrative), "validation": validation,
        "usage": usage, "receipts": receipts, "narrative": narrative,
        "editorial_approval": {"status": "pending", "reason": "independent editorial approval required"},
    }
    if validation["status"] != "passed":
        raise RuntimeError(f"cross-company DeepSeek output rejected: {validation}")
    return artifact


def _cross_company_artifact_provenance_payload(artifact: dict[str, Any]) -> dict[str, Any]:
    payload = deepcopy(artifact)
    payload.pop("editorial_approval", None)
    return payload


def _cross_company_artifact_provenance_hash(artifact: dict[str, Any]) -> str:
    return _canonical_hash(_cross_company_artifact_provenance_payload(artifact))


def _validate_cross_company_revision_chain(artifact: dict[str, Any]) -> bool:
    revision = artifact.get("editorial_revision")
    provider = artifact.get("provider")
    if provider == "DeepSeek":
        return revision is None
    if provider != "DeepSeek draft + evidence editor" or not isinstance(revision, dict):
        return False
    base_hash = revision.get("base_narrative_hash")
    return bool(
        revision.get("status") == "revised"
        and revision.get("revision_version") == "cross-company-editorial-revision-v1"
        and revision.get("base_provider") == "DeepSeek"
        and revision.get("base_model") == artifact.get("model")
        and isinstance(base_hash, str) and re.fullmatch(r"[0-9a-f]{64}", base_hash)
        and base_hash != artifact.get("narrative_hash")
        and revision.get("revised_narrative_hash") == artifact.get("narrative_hash")
        and isinstance(revision.get("base_artifact_provenance_hash"), str)
        and re.fullmatch(r"[0-9a-f]{64}", revision["base_artifact_provenance_hash"])
        and isinstance(revision.get("revised_by"), str) and revision["revised_by"].strip()
        and isinstance(revision.get("findings"), list) and revision["findings"]
    )


def approve_cross_company_narrative(
    artifact: dict[str, Any], *, reviewer: str, expected_narrative_hash: str,
    expected_evidence_manifest_hash: str, expected_artifact_provenance_hash: str,
) -> dict[str, Any]:
    if not reviewer.strip():
        raise ValueError("reviewer is required")
    if artifact.get("narrative_hash") != expected_narrative_hash:
        raise RuntimeError("reviewed narrative hash changed")
    if artifact.get("evidence_manifest_hash") != expected_evidence_manifest_hash:
        raise RuntimeError("reviewed evidence manifest changed")
    provenance_hash = _cross_company_artifact_provenance_hash(artifact)
    if provenance_hash != expected_artifact_provenance_hash:
        raise RuntimeError("reviewed artifact provenance changed")
    if (artifact.get("validation") or {}).get("status") != "passed":
        raise RuntimeError("cannot approve an invalid cross-company narrative")
    if artifact.get("narrative_hash") != _canonical_hash(artifact.get("narrative")):
        raise RuntimeError("cannot approve a narrative with stale content hash")
    if not _validate_cross_company_revision_chain(artifact):
        raise RuntimeError("cannot approve an invalid narrative provenance chain")
    approved = deepcopy(artifact)
    approved["editorial_approval"] = {
        "status": "approved", "approval_version": "cross-company-editorial-v2",
        "narrative_hash": expected_narrative_hash,
        "evidence_manifest_hash": expected_evidence_manifest_hash,
        "artifact_provenance_hash": provenance_hash,
        "input_identity": artifact.get("input_identity"),
        "provider": artifact.get("provider"), "model": artifact.get("model"),
        "prompt_version": artifact.get("prompt_version"),
        "prompt_hash": artifact.get("prompt_hash"),
        "approved_by": reviewer.strip(), "approved_at": datetime.now(timezone.utc).isoformat(),
    }
    return approved


def revise_cross_company_narrative(
    artifact: dict[str, Any], revised_narrative: dict[str, Any], frozen_request: dict[str, Any],
    *, editor: str, findings: list[str],
) -> dict[str, Any]:
    """Apply a provenance-preserving evidence edit before independent approval."""

    if artifact.get("artifact_version") != "cross-company-narrative-v1":
        raise RuntimeError("unsupported cross-company narrative artifact")
    if artifact.get("input_identity") != frozen_request.get("input_identity"):
        raise RuntimeError("editorial revision input identity mismatch")
    evidence_manifest_hash = (frozen_request.get("frozen_evidence") or {}).get("manifest_hash")
    if artifact.get("evidence_manifest_hash") != evidence_manifest_hash:
        raise RuntimeError("editorial revision evidence manifest mismatch")
    if not editor.strip() or not findings or any(not str(item).strip() for item in findings):
        raise ValueError("editor and non-empty findings are required")
    validation = validate_cross_company_narrative(revised_narrative, frozen_request)
    if validation["status"] != "passed":
        raise RuntimeError(f"editorial revision rejected: {validation}")
    revised = deepcopy(artifact)
    base_artifact_provenance_hash = _cross_company_artifact_provenance_hash(artifact)
    base_narrative_hash = str(artifact.get("narrative_hash") or "")
    revised["narrative"] = deepcopy(revised_narrative)
    revised["narrative_hash"] = _canonical_hash(revised_narrative)
    revised["validation"] = validation
    revised["provider"] = "DeepSeek draft + evidence editor"
    revised["editorial_revision"] = {
        "status": "revised",
        "revision_version": "cross-company-editorial-revision-v1",
        "base_provider": artifact.get("provider"),
        "base_model": artifact.get("model"),
        "base_narrative_hash": base_narrative_hash,
        "base_artifact_provenance_hash": base_artifact_provenance_hash,
        "revised_narrative_hash": revised["narrative_hash"],
        "revised_by": editor.strip(),
        "findings": [str(item).strip() for item in findings],
        "revised_at": datetime.now(timezone.utc).isoformat(),
    }
    revised["editorial_approval"] = {
        "status": "pending", "reason": "independent editorial approval required after revision",
    }
    return revised


def apply_cross_company_narrative(report: dict[str, Any], artifact: dict[str, Any]) -> dict[str, Any]:
    """Attach only the narrative generated for this exact production identity."""
    from company_research import report_payload_hash, verify_report_integrity
    from report_contract import public_ai_narrative, validate_report_contract

    verify_report_integrity(report)
    expected_identity = (report.get("generated_from") or {}).get("production_input_identity")
    expected_manifest = (report.get("generated_from") or {}).get("evidence_manifest_hash")
    generated = report.get("generated_from") or {}
    narrative = artifact.get("narrative")
    approval = artifact.get("editorial_approval") or {}
    if (
        artifact.get("artifact_version") != "cross-company-narrative-v1"
        or artifact.get("input_identity") != expected_identity
        or artifact.get("evidence_manifest_hash") != expected_manifest
        or (artifact.get("validation") or {}).get("status") != "passed"
        or artifact.get("narrative_hash") != _canonical_hash(narrative)
        or artifact.get("model") != generated.get("narrative_model")
        or artifact.get("prompt_version") != generated.get("prompt_version")
        or not _validate_cross_company_revision_chain(artifact)
        or approval.get("status") != "approved"
        or approval.get("approval_version") != "cross-company-editorial-v2"
        or approval.get("narrative_hash") != artifact.get("narrative_hash")
        or approval.get("evidence_manifest_hash") != expected_manifest
        or approval.get("input_identity") != expected_identity
        or approval.get("provider") != artifact.get("provider")
        or approval.get("model") != artifact.get("model")
        or approval.get("prompt_version") != artifact.get("prompt_version")
        or approval.get("prompt_hash") != artifact.get("prompt_hash")
        or approval.get("artifact_provenance_hash") != _cross_company_artifact_provenance_hash(artifact)
    ):
        raise RuntimeError("cross-company narrative identity or validation is stale")
    output = deepcopy(report)
    output.pop("report_hash", None)
    output["ai_narrative"] = public_ai_narrative(narrative)
    provider_validation = deepcopy(artifact["validation"])
    provider_validation.pop("input_identity", None)
    revision = artifact.get("editorial_revision") or {}
    applied_rules = []
    if revision.get("status") == "revised":
        applied_rules.append({
            "id": "evidence_entailment_revision",
            "base_narrative_hash": revision.get("base_narrative_hash"),
            "revised_narrative_hash": revision.get("revised_narrative_hash"),
            "findings": revision.get("findings") or [],
        })
    output["narrative_provider"] = {
        "provider": artifact["provider"], "model": artifact["model"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "prompt_version": artifact["prompt_version"], "artifact_version": artifact["artifact_version"],
        "validation": provider_validation,
        "editorial_review": {"reviewer": approval["approved_by"], "applied_rules": applied_rules},
        "editorial_approval": approval,
        "artifact_hash": _canonical_hash(artifact),
    }
    errors = validate_report_contract(output["report_contract"], output)
    if errors:
        raise RuntimeError("cross-company narrative broke report contract: " + "; ".join(errors))
    output["report_hash"] = report_payload_hash(output)
    return output

UNSUPPORTED_ASSERTION_FRAGMENTS = tuple(rule["before"] for rule in EDITORIAL_RULES if rule["id"] not in {"no_automatic_stop_loss"})
CATL_SOURCE_AUGMENTATIONS = {
    "executive_summary": ("annual_segments", "annual_risks", "annual_capacity"),
    "investment_committee": ("annual_segments", "annual_risks"),
    "business_quality": ("annual_segments",),
    "competitive_moat": ("annual_risks",),
    "financial_quality": ("annual_capacity",),
    "industry_chain": ("annual_risks",),
    "valuation_debate": ("annual_segments", "annual_capacity"),
}


def _canonical_hash(value: Any) -> str:
    import hashlib

    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


def apply_editorial_guardrails(value: Any) -> tuple[Any, list[dict[str, str]]]:
    applied: list[dict[str, str]] = []

    def walk(item: Any) -> Any:
        if isinstance(item, dict):
            return {key: walk(child) for key, child in item.items()}
        if isinstance(item, list):
            return [walk(child) for child in item]
        if not isinstance(item, str):
            return item
        updated = item
        for rule in EDITORIAL_RULES:
            if rule["before"] in updated:
                updated = updated.replace(rule["before"], rule["after"])
                if rule not in applied:
                    applied.append(rule)
            elif rule["after"] in updated and rule not in applied:
                applied.append(rule)
        return updated

    updated_value = walk(value)
    if isinstance(updated_value, dict) and "宁德时代" in str(updated_value.get("report_title") or ""):
        sections = updated_value.get("sections") or {}
        for block_name, additions in CATL_SOURCE_AUGMENTATIONS.items():
            block = updated_value.get(block_name) if block_name in {"executive_summary", "investment_committee"} else sections.get(block_name)
            if not isinstance(block, dict) or not isinstance(block.get("source_ids"), list):
                continue
            added = [source_id for source_id in additions if source_id not in block["source_ids"]]
            if not added:
                continue
            block["source_ids"].extend(added)
            applied.append({
                "id": f"source_scope_{block_name}",
                "before": "",
                "after": ",".join(added),
                "reason": "段落事实范围超出原引用，补充当前冻结证据集中的直接来源。",
            })
    return updated_value, applied


def _read_secret(path: Path) -> str:
    secret = path.read_text(encoding="utf-8").strip()
    if not secret:
        raise RuntimeError(f"DeepSeek key file is empty: {path}")
    if "=" in secret and "\n" not in secret:
        secret = secret.split("=", 1)[1].strip().strip('"').strip("'")
    return secret


def call_structured_deepseek(
    *,
    system_prompt: str,
    request_object: Mapping[str, Any],
    key_file: Path,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 14000,
    reasoning_effort: str = "high",
    temperature: float = 0.1,
    transport: Any = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Call the repository's DeepSeek JSON path for a frozen request object.

    This is the shared transport boundary for product-specific structured
    generation.  Callers own their prompt and output validation; this function
    owns credential loading, retries, response parsing, and the provider
    receipt.  ``transport`` is test-only and receives the exact payload plus
    the loaded secret.
    """
    api_key = _read_secret(key_file)
    request_payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": json.dumps(
                    request_object,
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                ),
            },
        ],
        "thinking": {"type": "enabled"},
        "reasoning_effort": reasoning_effort,
        "response_format": {"type": "json_object"},
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }

    response_payload: dict[str, Any] | None = None
    failure: BaseException | None = None
    for attempt in range(3):
        try:
            if transport is not None:
                response_payload = transport(deepcopy(request_payload), api_key)
            else:
                request = urllib.request.Request(
                    API_URL,
                    data=json.dumps(request_payload, ensure_ascii=False).encode(),
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=360) as response:
                    response_payload = json.loads(response.read().decode())
            break
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:1000]
            if exc.code not in {429, 500, 502, 503, 504}:
                raise RuntimeError(
                    f"DeepSeek structured API HTTP {exc.code}: {detail}"
                ) from exc
            failure = exc
        except (urllib.error.URLError, TimeoutError, ssl.SSLError) as exc:
            failure = exc
        if attempt < 2:
            time.sleep(1.5 * (attempt + 1))
    if response_payload is None:
        raise RuntimeError(
            "DeepSeek structured API unavailable after retries: "
            + type(failure).__name__
        ) from failure

    if "choices" in response_payload:
        choice = response_payload["choices"][0]
        finish_reason = choice.get("finish_reason")
        content = choice.get("message", {}).get("content") or ""
        if finish_reason != "stop" or not str(content).strip():
            raise RuntimeError(
                "DeepSeek structured response did not finish cleanly: "
                + str(finish_reason)
            )
        result = json.loads(content) if isinstance(content, str) else content
        receipt = {
            "request_id": response_payload.get("id"),
            "model": response_payload.get("model") or model,
            "finish_reason": finish_reason,
            "usage": response_payload.get("usage") or {},
            "system_fingerprint": response_payload.get("system_fingerprint"),
        }
    else:
        result = response_payload
        receipt = {
            "request_id": None,
            "model": model,
            "finish_reason": "test_transport",
            "usage": {},
            "system_fingerprint": None,
        }
    if not isinstance(result, dict):
        raise RuntimeError("DeepSeek structured response is not a JSON object")
    return result, receipt


def _system_prompt() -> str:
    return """你是中国公募基金的资深行业研究员，负责把已经验证的数据底稿写成机构级中文深度研报。

硬规则：
1. 只能使用用户提供的 JSON evidence pack；不得调用外部知识，不得补写任何未提供的事实、数字、机构观点或预测。
2. 每一节必须区分事实与推断。事实必须由 source_ids 支撑；证据不足时明确写“证据不足”，不能用行业常识填空。
3. 不要重复数据表。重点解释因果链：什么驱动什么、约束在哪里、市场为何存在分歧、后续财报如何验证。
4. 正文禁止出现阿拉伯数字、中文数字、百分比、金额、年份、倍数或排名；所有量化事实由确定性数据组件单独展示。禁止输出任何仓位动作、买卖指令或止损指令；仓位由确定性系统单独生成。
5. 写作风格是冷静、克制、有判断的中文机构研报；不要写广告词、口号、人格化专家或空泛宏观叙事。
6. 输出必须是合法 JSON，不要使用 Markdown 代码围栏。

JSON schema：
{
  "report_title": "string",
  "executive_summary": {"conclusion": "string", "paragraphs": ["string", "string", "string"], "source_ids": ["source_id"]},
  "sections": {
    "industry_chain": {"title": "string", "conclusion": "string", "paragraphs": ["string", "string"], "source_ids": ["source_id"]},
    "business_quality": {"title": "string", "conclusion": "string", "paragraphs": ["string", "string"], "source_ids": ["source_id"]},
    "competitive_moat": {"title": "string", "conclusion": "string", "paragraphs": ["string", "string"], "source_ids": ["source_id"]},
    "financial_quality": {"title": "string", "conclusion": "string", "paragraphs": ["string", "string"], "source_ids": ["source_id"]},
    "valuation_debate": {"title": "string", "conclusion": "string", "paragraphs": ["string", "string"], "source_ids": ["source_id"]},
    "risk_falsification": {"title": "string", "conclusion": "string", "paragraphs": ["string", "string"], "source_ids": ["source_id"]}
  },
  "investment_committee": {"bull_case": "string", "bear_case": "string", "base_case": "string", "source_ids": ["source_id"]}
}

篇幅要求：executive_summary 的每段 120–220 个中文字符；每个 sections 项至少两段，每段 180–350 个中文字符。不要为了长度重复同一句话。"""


def _user_prompt(evidence: dict[str, Any]) -> str:
    identity = evidence.get("identity") or {}
    return (
        f"请基于以下 evidence pack 撰写{identity.get('name') or identity.get('ticker') or '该公司'}深度研报。输出 JSON。"
        "所有 source_ids 必须来自 sources 列表；不要创造新 source_id。\n\n"
        + json.dumps(evidence, ensure_ascii=False, sort_keys=True, default=str)
    )


def call_deepseek(evidence: dict[str, Any], key_file: Path, model: str = DEFAULT_MODEL) -> tuple[dict[str, Any], dict[str, Any]]:
    api_key = _read_secret(key_file)
    request_payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": _user_prompt(evidence)},
        ],
        "thinking": {"type": "enabled"},
        "reasoning_effort": "high",
        "response_format": {"type": "json_object"},
        "max_tokens": 14000,
        "stream": False,
    }
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(request_payload, ensure_ascii=False).encode(),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=360) as response:
            response_payload = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:1000]
        raise RuntimeError(f"DeepSeek API HTTP {exc.code}: {detail}") from exc
    choice = response_payload["choices"][0]
    if choice.get("finish_reason") != "stop":
        raise RuntimeError(f"DeepSeek response did not finish cleanly: {choice.get('finish_reason')}")
    content = choice["message"].get("content") or ""
    if not content.strip():
        raise RuntimeError("DeepSeek returned empty content")
    narrative = json.loads(content)
    receipt = {
        "request_id": response_payload.get("id"),
        "model": response_payload.get("model") or model,
        "finish_reason": choice.get("finish_reason"),
        "usage": response_payload.get("usage") or {},
        "system_fingerprint": response_payload.get("system_fingerprint"),
    }
    return narrative, receipt


def repair_deepseek(
    evidence: dict[str, Any],
    narrative: dict[str, Any],
    validation: dict[str, Any],
    key_file: Path,
    model: str = DEFAULT_MODEL,
) -> tuple[dict[str, Any], dict[str, Any]]:
    api_key = _read_secret(key_file)
    allowed_ids = [source["id"] for source in evidence["sources"]]
    repair_prompt = {
        "task": "把 draft 修复为最终研报对象。响应顶层第一个字段必须是 report_title，禁止回显本任务对象。",
        "rules": [
            "只能使用 allowed_source_ids；risks、falsification 等章节名不是 source_id。",
            "正文不得出现任何数字或量化表达；量化事实由确定性组件展示。",
            "不得输出 position_conclusion、仓位动作或止损指令；执行契约由确定性系统渲染。",
            "保留原稿中有价值的因果分析，不要降低段落深度。",
            "输出必须保持原 JSON schema，且是合法 JSON。",
        ],
        "validation_failures": {
            "errors": validation.get("errors") or [],
            "numeric_warnings": validation.get("numeric_warnings") or [],
        },
        "allowed_source_ids": allowed_ids,
        "draft": narrative,
    }
    request_payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是机构研报事实核查编辑。只输出修复后的研报对象。顶层键只能是 report_title、executive_summary、sections、investment_committee；禁止返回 task、rules、draft、validation_failures 或解释文字。"},
            {"role": "user", "content": json.dumps(repair_prompt, ensure_ascii=False, sort_keys=True, default=str)},
        ],
        "thinking": {"type": "enabled"},
        "reasoning_effort": "medium",
        "response_format": {"type": "json_object"},
        "max_tokens": 22000,
        "stream": False,
    }
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(request_payload, ensure_ascii=False).encode(),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=360) as response:
            response_payload = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:1000]
        raise RuntimeError(f"DeepSeek repair HTTP {exc.code}: {detail}") from exc
    choice = response_payload["choices"][0]
    content = choice["message"].get("content") or ""
    if choice.get("finish_reason") != "stop" or not content.strip():
        raise RuntimeError(f"DeepSeek repair did not finish cleanly: {choice.get('finish_reason')}")
    receipt = {
        "request_id": response_payload.get("id"),
        "model": response_payload.get("model") or model,
        "finish_reason": choice.get("finish_reason"),
        "usage": response_payload.get("usage") or {},
        "system_fingerprint": response_payload.get("system_fingerprint"),
        "purpose": "repair",
    }
    repaired = json.loads(content)
    if not isinstance(repaired, dict) or "report_title" not in repaired or "sections" not in repaired:
        raise RuntimeError(f"DeepSeek repair echoed or violated the report schema: {list(repaired) if isinstance(repaired, dict) else type(repaired).__name__}")
    return repaired, receipt


def repair_position_conclusion(
    evidence: dict[str, Any],
    current: dict[str, Any],
    key_file: Path,
    model: str = DEFAULT_MODEL,
) -> tuple[dict[str, Any], dict[str, Any]]:
    api_key = _read_secret(key_file)
    relevant = {
        "execution_contract": evidence["execution_contract"],
        "market": evidence["market"],
        "valuation": evidence["valuation"],
        "financials": evidence["financials"],
        "risks": evidence["risks"],
        "watchlist": evidence["watchlist"],
        "allowed_source_ids": [source["id"] for source in evidence["sources"]],
        "current": current,
    }
    prompt = (
        "请只重写 position_conclusion JSON 对象。reasoning 写 180–260 个中文字符，"
        "解释为何当前只执行 4% 而条件上限为 8%，以及后续两次 2% 需要什么验证。"
        "只能使用下方证据和 allowed_source_ids，不得增加新数字。conditions 必须恰好三条。\n"
        + json.dumps(relevant, ensure_ascii=False, sort_keys=True, default=str)
    )
    request_payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是机构研报主编。输出合法 JSON，只包含 action、reasoning、conditions、source_ids。"},
            {"role": "user", "content": prompt},
        ],
        "thinking": {"type": "disabled"},
        "response_format": {"type": "json_object"},
        "max_tokens": 4000,
        "stream": False,
    }
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(request_payload, ensure_ascii=False).encode(),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            response_payload = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:1000]
        raise RuntimeError(f"DeepSeek position repair HTTP {exc.code}: {detail}") from exc
    choice = response_payload["choices"][0]
    content = choice["message"].get("content") or ""
    if choice.get("finish_reason") != "stop" or not content.strip():
        raise RuntimeError(f"DeepSeek position repair did not finish cleanly: {choice.get('finish_reason')}")
    receipt = {
        "request_id": response_payload.get("id"),
        "model": response_payload.get("model") or model,
        "finish_reason": choice.get("finish_reason"),
        "usage": response_payload.get("usage") or {},
        "system_fingerprint": response_payload.get("system_fingerprint"),
        "purpose": "position_repair",
    }
    return json.loads(content), receipt


NUMERIC_TOKEN = re.compile(
    r"(?P<sign>[+\-−]?)\s*(?P<value>(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)\s*(?P<unit>个百分点|亿元|GWh|％|%|倍|[xX]|元|亿|年|日|pct)?"
)
NEGATIVE_WORDS = ("下降", "减少", "下滑", "下行", "跌幅", "回落", "亏损", "为负")
CHINESE_DIGITS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
IGNORED_METRIC_KEYS = {
    "source_ids", "id", "document_id", "snapshot_id", "ticker", "url", "known_at",
    "as_of", "date", "report_date", "latest_period", "period", "generated_at",
}


def _normalise_unit(unit: str | None) -> str:
    if unit in ("％", "%", "pct", "个百分点"):
        return "%"
    if unit in ("x", "X", "倍"):
        return "倍"
    if unit in ("亿", "亿元"):
        return "亿元"
    return unit or ""


def _unit_for_key(key: str) -> str:
    key = key.lower()
    if key.endswith("_yi") or "market_cap" in key:
        return "亿元"
    if any(part in key for part in ("pct", "yoy", "margin", "share", "growth", "return", "volatility", "drawdown", "roe", "ratio", "weight")):
        return "%"
    if key in {"pe", "pb", "pe_ttm"} or key.endswith("_pe"):
        return "倍"
    if key in {"price", "eps", "ma20", "ma60", "ma200", "target_price", "implied_eps"} or key.endswith("_price"):
        return "元"
    return ""


def _claim_from_match(match: re.Match[str], text: str) -> tuple[str, float, str, str]:
    raw_sign = match.group("sign").replace("−", "-")
    value = float(match.group("value").replace(",", ""))
    context = text[max(0, match.start() - 8):match.start()]
    sign = raw_sign or ("-" if any(word in context for word in NEGATIVE_WORDS) else "")
    unit = _normalise_unit(match.group("unit"))
    if not unit and 1900 <= value <= 2100:
        unit = "年"
    if not unit and context.rstrip().endswith(("¥", "￥")):
        unit = "元"
    return sign, value, unit, match.group(0).strip()


def build_metric_registry(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    """Create field-level numeric facts; source metadata is deliberately excluded."""
    registry: list[dict[str, Any]] = []

    def add(metric_id: str, sign: str, value: float, unit: str, source_ids: set[str], raw: str) -> None:
        if not source_ids:
            return
        claim = {
            "metric_id": metric_id,
            "sign": sign,
            "value": value,
            "unit": unit,
            "source_ids": sorted(source_ids),
            "raw": raw,
        }
        if claim not in registry:
            registry.append(claim)

    def walk(item: Any, path: str, inherited_sources: set[str], field_key: str = "") -> None:
        if isinstance(item, dict):
            local_sources = inherited_sources
            if isinstance(item.get("source_ids"), list):
                local_sources = {str(value) for value in item["source_ids"]}
            for key, value in item.items():
                if key in IGNORED_METRIC_KEYS or key == "sources":
                    continue
                walk(value, f"{path}.{key}" if path else key, local_sources, key)
            return
        if isinstance(item, list):
            for index, value in enumerate(item):
                walk(value, f"{path}[{index}]", inherited_sources, field_key)
            return
        if isinstance(item, bool) or item is None:
            return
        if isinstance(item, (int, float)):
            numeric = float(item)
            add(path, "-" if numeric < 0 else "", abs(numeric), _unit_for_key(field_key), inherited_sources, str(item))
            return
        if isinstance(item, str):
            for index, match in enumerate(NUMERIC_TOKEN.finditer(item)):
                sign, value, unit, raw = _claim_from_match(match, item)
                add(f"{path}#{index}", sign, value, unit, inherited_sources, raw)
            for index, match in enumerate(re.finditer(r"([一二三四五六七八九十])\s*(年|日)", item)):
                add(
                    f"{path}#cn{index}",
                    "",
                    float(CHINESE_DIGITS[match.group(1)]),
                    match.group(2),
                    inherited_sources,
                    match.group(0),
                )

    for key, value in evidence.items():
        if key not in {"identity", "sources"}:
            walk(value, key, set())
    return registry


def _numeric_claims_from_block(block: dict[str, Any]) -> list[tuple[str, float, str, str]]:
    values: list[str] = []

    def walk(item: Any, key: str = "") -> None:
        if key in {"source_ids", "title"}:
            return
        if isinstance(item, dict):
            for child_key, child in item.items():
                walk(child, child_key)
        elif isinstance(item, list):
            for child in item:
                walk(child, key)
        elif isinstance(item, str):
            values.append(item)

    walk(block)
    claims: list[tuple[str, float, str, str]] = []
    for text in values:
        claims.extend(_claim_from_match(match, text) for match in NUMERIC_TOKEN.finditer(text))
    return claims


def _visible_texts(value: Any, key: str = "") -> list[str]:
    if key == "source_ids":
        return []
    if isinstance(value, dict):
        return [text for child_key, child in value.items() for text in _visible_texts(child, child_key)]
    if isinstance(value, list):
        return [text for child in value for text in _visible_texts(child, key)]
    return [value] if isinstance(value, str) else []


def _same_metric(claim: tuple[str, float, str, str], fact: dict[str, Any]) -> bool:
    sign, value, unit, _ = claim
    fact_sign = fact["sign"]
    sign_matches = sign == fact_sign or (sign == "" and fact_sign == "+")
    if not sign_matches or unit != fact["unit"]:
        return False
    raw_value = claim[3].replace(",", "")
    raw_number = re.search(r"\d+(?:\.\d+)?", raw_value)
    decimals = len(raw_number.group(0).split(".", 1)[1]) if raw_number and "." in raw_number.group(0) else 0
    tolerance = 0.5 if decimals == 0 else 0.051 if decimals == 1 else 1e-9
    return abs(value - float(fact["value"])) <= tolerance


def validate_narrative(narrative: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    source_ids = {source["id"] for source in evidence["sources"]}
    errors: list[str] = []
    cited: set[str] = set()

    from report_contract import validate_public_ai_narrative

    errors.extend(validate_public_ai_narrative(narrative))

    if not isinstance(narrative.get("report_title"), str) or len(narrative["report_title"].strip()) < 8:
        errors.append("report_title is missing or too short")

    blocks: list[tuple[str, Any]] = [("executive_summary", narrative.get("executive_summary"))]
    sections = narrative.get("sections") or {}
    if set(sections) != set(SECTION_KEYS):
        errors.append(f"sections must be exactly {SECTION_KEYS}")
    blocks.extend((key, sections.get(key)) for key in SECTION_KEYS)
    blocks.append(("investment_committee", narrative.get("investment_committee")))
    for name, block in blocks:
        if not isinstance(block, dict):
            errors.append(f"{name} must be an object")
            continue
        ids = block.get("source_ids")
        if not isinstance(ids, list) or not ids:
            errors.append(f"{name}.source_ids must be non-empty")
        else:
            unknown = set(ids) - source_ids
            if unknown:
                errors.append(f"{name} has unknown source_ids: {sorted(unknown)}")
            cited.update(set(ids) & source_ids)
        if name == "executive_summary" or name in SECTION_KEYS:
            paragraphs = block.get("paragraphs")
            if not isinstance(paragraphs, list) or len(paragraphs) < 2 or any(not isinstance(item, str) or len(item.strip()) < 80 for item in paragraphs):
                errors.append(f"{name}.paragraphs must contain at least two substantive paragraphs")
        elif name == "investment_committee":
            for key in ("bull_case", "bear_case", "base_case"):
                if not isinstance(block.get(key), str) or len(block[key].strip()) < 40:
                    errors.append(f"investment_committee.{key} is missing or too short")
    forbidden_execution_terms = ("买入", "卖出", "加仓", "减仓", "清仓", "满仓", "重仓", "止损", "仓位", "持仓", "研究仓")
    narrative_text = json.dumps(narrative, ensure_ascii=False, default=str)
    for term in forbidden_execution_terms:
        if term in narrative_text:
            errors.append(f"model narrative contains forbidden execution language: {term}")
    for fragment in UNSUPPORTED_ASSERTION_FRAGMENTS:
        if fragment in narrative_text:
            errors.append(f"model narrative contains an unsupported assertion: {fragment}")
    registry = build_metric_registry(evidence)
    numeric_warnings: list[str] = []
    chinese_quantity = re.compile(
        r"(?:百分之[零〇一二两三四五六七八九十百千万亿点]+|"
        r"[零〇一二两三四五六七八九十百千万亿点]+(?:个百分点|倍|元|亿元|年|日|GWh|名|位|家|期|季|月|周|成))"
    )
    for name, block in blocks:
        if not isinstance(block, dict):
            continue
        for claim in _numeric_claims_from_block(block):
            numeric_warnings.append(f"{name}:{claim[3]} (literal model number forbidden)")
        for text in _visible_texts(block):
            match = chinese_quantity.search(text)
            if match:
                numeric_warnings.append(f"{name}:{match.group(0)} (Chinese quantity forbidden)")
    numeric_warnings = sorted(set(numeric_warnings))
    return {
        "status": "passed" if not errors and not numeric_warnings else "needs_review",
        "errors": errors,
        "numeric_warnings": numeric_warnings,
        "cited_source_count": len(cited),
        "available_source_count": len(source_ids),
        "metric_registry_count": len(registry),
        "numeric_policy": "deterministic_components_only",
    }


def generate(ticker: str, db_path: Path, key_file: Path, model: str, force: bool = False) -> Path:
    report = report_payload(ticker, db_path)
    if not report or report.get("research_status") != "verified":
        raise RuntimeError("DeepSeek writing requires a verified deterministic report")
    snapshot_id = report["generated_from"]["snapshot_id"]
    target = artifact_path(db_path, ticker, snapshot_id)
    evidence_set = load_evidence_set(ticker, snapshot_id, db_path)
    if not evidence_set:
        raise RuntimeError("DeepSeek evidence gate failed: no current integrity-passed evidence set")
    evidence = build_evidence_pack(report, evidence_set)
    evidence_hash = _canonical_hash(evidence)
    if target.exists() and not force:
        existing = load_artifact(db_path, ticker, snapshot_id)
        if (
            existing
            and existing.get("validation_version") == VALIDATION_VERSION
            and existing.get("validation", {}).get("status") == "passed"
            and existing.get("profile_hash") == research_profile_hash(ticker)
            and existing.get("research_logic_hash") == research_logic_hash()
            and existing.get("writer_logic_hash") == writer_logic_hash()
            and existing.get("evidence_hash") == evidence_hash
            and existing.get("evidence_set_id") == evidence_set["evidence_set_id"]
            and existing.get("evidence_manifest_hash") == evidence_set["manifest_hash"]
        ):
            return target
    narrative, first_receipt = call_deepseek(evidence, key_file, model)
    narrative.pop("position_conclusion", None)
    narrative, editorial_review = apply_editorial_guardrails(narrative)
    validation = validate_narrative(narrative, evidence)
    receipts = [first_receipt]
    if validation["status"] != "passed":
        try:
            narrative, repair_receipt = repair_deepseek(evidence, narrative, validation, key_file, model)
        except Exception as exc:
            failed_artifact = {
                "artifact_version": "deepseek-narrative-v1", "validation_version": VALIDATION_VERSION,
                "prompt_version": PROMPT_VERSION, "provider": "DeepSeek", "model": first_receipt["model"],
                "generated_at": datetime.now(timezone.utc).isoformat(), "ticker": ticker.upper(),
                "snapshot_id": snapshot_id, "profile_hash": research_profile_hash(ticker),
                "research_logic_hash": research_logic_hash(), "writer_logic_hash": writer_logic_hash(),
                "evidence_set_id": evidence_set["evidence_set_id"],
                "evidence_manifest_hash": evidence_set["manifest_hash"], "evidence_hash": evidence_hash,
                "prompt_hash": _canonical_hash({"system": _system_prompt(), "user": _user_prompt(evidence)}),
                "narrative_hash": _canonical_hash(narrative), "validation": validation,
                "editorial_approval": {"status": "pending", "reason": "automatic repair failed"},
                "editorial_review": {"reviewer": "Codex fact audit", "applied_rules": editorial_review},
                "generation_error": f"{type(exc).__name__}: {exc}", "receipts": receipts, "narrative": narrative,
            }
            write_artifact(db_path, ticker, snapshot_id, failed_artifact)
            raise
        narrative, repaired_edits = apply_editorial_guardrails(narrative)
        editorial_review.extend(rule for rule in repaired_edits if rule not in editorial_review)
        receipts.append(repair_receipt)
        validation = validate_narrative(narrative, evidence)
    artifact = {
        "artifact_version": "deepseek-narrative-v1",
        "validation_version": VALIDATION_VERSION,
        "prompt_version": PROMPT_VERSION,
        "provider": "DeepSeek",
        "model": receipts[-1]["model"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ticker": ticker.upper(),
        "snapshot_id": snapshot_id,
        "profile_hash": research_profile_hash(ticker),
        "research_logic_hash": research_logic_hash(),
        "writer_logic_hash": writer_logic_hash(),
        "evidence_set_id": evidence_set["evidence_set_id"],
        "evidence_manifest_hash": evidence_set["manifest_hash"],
        "evidence_hash": evidence_hash,
        "prompt_hash": _canonical_hash({"system": _system_prompt(), "user": _user_prompt(evidence)}),
        "narrative_hash": _canonical_hash(narrative),
        "validation": validation,
        "editorial_approval": {"status": "pending", "reason": "independent editorial approval required before display"},
        "editorial_review": {"reviewer": "Codex fact audit", "applied_rules": editorial_review},
        "receipts": receipts,
        "narrative": narrative,
    }
    write_artifact(db_path, ticker, snapshot_id, artifact)
    if validation["status"] != "passed":
        raise RuntimeError(f"DeepSeek artifact needs review; saved at {target}: {validation}")
    return target


def repair_existing(ticker: str, db_path: Path, key_file: Path, model: str) -> Path:
    report = report_payload(ticker, db_path)
    if not report or report.get("research_status") != "verified":
        raise RuntimeError("DeepSeek repair requires a verified deterministic report")
    target = artifact_path(db_path, ticker, report["generated_from"]["snapshot_id"])
    if not target.exists():
        raise RuntimeError(f"DeepSeek artifact does not exist: {target}")
    artifact = load_artifact(db_path, ticker, report["generated_from"]["snapshot_id"])
    if artifact is None:
        raise RuntimeError(f"DeepSeek artifact is unreadable: {target}")
    evidence_set = load_evidence_set(ticker, report["generated_from"]["snapshot_id"], db_path)
    if not evidence_set:
        raise RuntimeError("DeepSeek evidence gate failed: no current integrity-passed evidence set")
    evidence = build_evidence_pack(report, evidence_set)
    narrative = artifact["narrative"]
    if isinstance(narrative, dict) and isinstance(narrative.get("draft"), dict):
        narrative = narrative["draft"]
    nested_position = narrative.get("position_conclusion")
    if isinstance(nested_position, dict) and set(nested_position) == {"position_conclusion"} and isinstance(nested_position["position_conclusion"], dict):
        narrative["position_conclusion"] = nested_position["position_conclusion"]
    narrative.pop("position_conclusion", None)
    allowed_ids = {source["id"] for source in evidence["sources"]}
    blocks = [narrative.get("executive_summary"), *((narrative.get("sections") or {}).values()), narrative.get("investment_committee")]
    for block in blocks:
        if isinstance(block, dict) and isinstance(block.get("source_ids"), list):
            block["source_ids"] = [source_id for source_id in block["source_ids"] if source_id in allowed_ids]
    narrative, editorial_review = apply_editorial_guardrails(narrative)
    current_validation = validate_narrative(narrative, evidence)
    if current_validation["status"] == "passed":
        artifact["narrative"] = narrative
        artifact["validation"] = current_validation
        artifact["validation_version"] = VALIDATION_VERSION
        artifact["editorial_approval"] = {"status": "pending", "reason": "narrative changed; re-approval required"}
        artifact["narrative_hash"] = _canonical_hash(narrative)
        artifact["evidence_hash"] = _canonical_hash(evidence)
        artifact["profile_hash"] = research_profile_hash(ticker)
        artifact["research_logic_hash"] = research_logic_hash()
        artifact["writer_logic_hash"] = writer_logic_hash()
        artifact["evidence_set_id"] = evidence_set["evidence_set_id"]
        artifact["evidence_manifest_hash"] = evidence_set["manifest_hash"]
        artifact["editorial_review"] = {"reviewer": "Codex fact audit", "applied_rules": editorial_review}
        write_artifact(db_path, ticker, report["generated_from"]["snapshot_id"], artifact)
        return target
    narrative, receipt = repair_deepseek(evidence, narrative, current_validation, key_file, model)
    narrative.pop("position_conclusion", None)
    validation = validate_narrative(narrative, evidence)
    narrative, repaired_edits = apply_editorial_guardrails(narrative)
    editorial_review.extend(rule for rule in repaired_edits if rule not in editorial_review)
    validation = validate_narrative(narrative, evidence)
    receipts = artifact.get("receipts") or ([artifact["receipt"]] if artifact.get("receipt") else [])
    artifact.pop("receipt", None)
    artifact.update({
        "model": receipt["model"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "evidence_hash": _canonical_hash(evidence),
        "profile_hash": research_profile_hash(ticker),
        "research_logic_hash": research_logic_hash(),
        "writer_logic_hash": writer_logic_hash(),
        "evidence_set_id": evidence_set["evidence_set_id"],
        "evidence_manifest_hash": evidence_set["manifest_hash"],
        "narrative_hash": _canonical_hash(narrative),
        "validation": validation,
        "validation_version": VALIDATION_VERSION,
        "editorial_approval": {"status": "pending", "reason": "narrative changed; re-approval required"},
        "editorial_review": {"reviewer": "Codex fact audit", "applied_rules": editorial_review},
        "receipts": [*receipts, receipt],
        "narrative": narrative,
    })
    write_artifact(db_path, ticker, report["generated_from"]["snapshot_id"], artifact)
    if validation["status"] != "passed":
        raise RuntimeError(f"DeepSeek repaired artifact still needs review; saved at {target}: {validation}")
    return target


def editorial_status(
    ticker: str,
    db_path: Path = DB_PATH,
    *,
    snapshot_id: str | None = None,
) -> dict[str, Any]:
    """Return the effective editorial state after revalidating the current artifact binding.

    The approval field inside an artifact is only a historical assertion.  It is not
    decision-ready unless the narrative, evidence set, report/profile logic, writer
    logic and approval hashes still match the report being requested.
    """
    report = report_payload(ticker, db_path, snapshot_id=snapshot_id)
    if not report or not report.get("generated_from"):
        raise KeyError(ticker.upper())
    snapshot_id = report["generated_from"]["snapshot_id"]
    artifact = load_artifact(db_path, ticker, snapshot_id)
    evidence_set = load_evidence_set(ticker, snapshot_id, db_path)
    if not artifact:
        return {"ticker": ticker.upper(), "snapshot_id": snapshot_id, "status": "not_generated"}
    raw_status = (artifact.get("editorial_approval") or {}).get("status", "pending")
    integrity_errors: list[str] = []
    current_validation = {"status": "needs_review"}
    narrative = artifact.get("narrative")
    evidence: dict[str, Any] | None = None
    if not evidence_set:
        integrity_errors.append("current evidence set is unavailable")
    elif not isinstance(narrative, dict):
        integrity_errors.append("narrative is unavailable")
    else:
        evidence = build_evidence_pack(report, evidence_set)
        current_validation = validate_narrative(narrative, evidence)
        if current_validation.get("status") != "passed":
            integrity_errors.append("current narrative validation is not passed")
    approval = artifact.get("editorial_approval") or {}
    narrative_hash = _canonical_hash(narrative) if isinstance(narrative, dict) else None
    checks = (
        (artifact.get("ticker") == ticker.upper(), "artifact ticker changed"),
        (artifact.get("snapshot_id") == snapshot_id, "artifact snapshot changed"),
        (artifact.get("validation_version") == VALIDATION_VERSION, "validation version changed"),
        (artifact.get("prompt_version") == PROMPT_VERSION, "prompt version changed"),
        (artifact.get("profile_hash") == research_profile_hash(ticker), "research profile changed"),
        (artifact.get("research_logic_hash") == research_logic_hash(), "research logic changed"),
        (artifact.get("writer_logic_hash") == writer_logic_hash(), "writer logic changed"),
        (artifact.get("narrative_hash") == narrative_hash, "narrative hash changed"),
        (artifact.get("evidence_hash") == (_canonical_hash(evidence) if evidence else None), "evidence pack changed"),
        (artifact.get("evidence_set_id") == (evidence_set or {}).get("evidence_set_id"), "evidence set changed"),
        (artifact.get("evidence_manifest_hash") == (evidence_set or {}).get("manifest_hash"), "evidence manifest changed"),
    )
    integrity_errors.extend(message for passed, message in checks if not passed)
    if raw_status == "approved":
        if approval.get("approval_version") != "human-editorial-v1":
            integrity_errors.append("approval version changed")
        if approval.get("narrative_hash") != narrative_hash:
            integrity_errors.append("approved narrative hash changed")
        if approval.get("evidence_manifest_hash") != (evidence_set or {}).get("manifest_hash"):
            integrity_errors.append("approved evidence manifest changed")
    effective_status = "invalidated" if raw_status == "approved" and integrity_errors else raw_status
    return {
        "ticker": ticker.upper(), "snapshot_id": snapshot_id,
        "status": effective_status,
        "raw_status": raw_status,
        "integrity_errors": sorted(set(integrity_errors)),
        "validation_status": current_validation.get("status"),
        "narrative_hash": artifact.get("narrative_hash"),
        "evidence_set_id": artifact.get("evidence_set_id"),
        "evidence_manifest_hash": artifact.get("evidence_manifest_hash"),
        "current_evidence_manifest_hash": evidence_set.get("manifest_hash") if evidence_set else None,
        "generated_at": artifact.get("generated_at"), "model": artifact.get("model"),
    }


def editorial_queue(db_path: Path = DB_PATH) -> dict[str, Any]:
    from research_reports import research_profile_tickers

    items = []
    for ticker in research_profile_tickers():
        try:
            item = editorial_status(ticker, db_path)
        except (KeyError, RuntimeError):
            continue
        if item["status"] != "not_generated":
            items.append(item)
    return {
        "items": items,
        "counts": {
            status: sum(item["status"] == status for item in items)
            for status in ("pending", "approved", "rejected")
        },
    }


def approve_artifact(
    ticker: str,
    db_path: Path,
    *,
    reviewer: str,
    expected_narrative_hash: str,
    expected_evidence_manifest_hash: str,
) -> Path:
    """Approve only the exact validated narrative and evidence manifest the editor reviewed."""
    if not reviewer.strip():
        raise ValueError("reviewer is required")
    report = report_payload(ticker, db_path)
    if not report or report.get("research_status") != "verified":
        raise RuntimeError("editorial approval requires a verified deterministic report")
    snapshot_id = report["generated_from"]["snapshot_id"]
    artifact = load_artifact(db_path, ticker, snapshot_id)
    if not artifact:
        raise RuntimeError("DeepSeek artifact does not exist")
    evidence_set = load_evidence_set(ticker, snapshot_id, db_path)
    if not evidence_set:
        raise RuntimeError("no passed evidence set exists for this report")
    evidence = build_evidence_pack(report, evidence_set)
    narrative = artifact.get("narrative")
    narrative_hash = _canonical_hash(narrative)
    evidence_hash = _canonical_hash(evidence)
    validation = validate_narrative(narrative, evidence) if isinstance(narrative, dict) else {"status": "needs_review"}
    failures = []
    if validation.get("status") != "passed": failures.append("narrative validation is not passed")
    if artifact.get("ticker") != ticker.upper() or artifact.get("snapshot_id") != snapshot_id: failures.append("artifact identity mismatch")
    if artifact.get("profile_hash") != research_profile_hash(ticker): failures.append("research profile changed")
    if artifact.get("research_logic_hash") != research_logic_hash(): failures.append("research logic changed")
    if artifact.get("writer_logic_hash") != writer_logic_hash(): failures.append("writer validation logic changed")
    if artifact.get("prompt_version") != PROMPT_VERSION: failures.append("prompt version changed")
    if artifact.get("narrative_hash") != narrative_hash or expected_narrative_hash != narrative_hash: failures.append("narrative hash mismatch")
    if artifact.get("evidence_hash") != evidence_hash: failures.append("evidence pack changed")
    if artifact.get("evidence_set_id") != evidence_set["evidence_set_id"]: failures.append("evidence set changed")
    if artifact.get("evidence_manifest_hash") != evidence_set["manifest_hash"] or expected_evidence_manifest_hash != evidence_set["manifest_hash"]: failures.append("evidence manifest hash mismatch")
    if failures:
        raise RuntimeError("editorial approval rejected: " + "; ".join(failures))
    artifact["validation"] = validation
    artifact["editorial_approval"] = {
        "status": "approved", "approval_version": "human-editorial-v1",
        "approved_by": reviewer.strip(), "approved_at": datetime.now(timezone.utc).isoformat(),
        "narrative_hash": narrative_hash, "evidence_manifest_hash": evidence_set["manifest_hash"],
    }
    return write_artifact(db_path, ticker, snapshot_id, artifact)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a source-constrained DeepSeek narrative for a verified report")
    parser.add_argument("ticker", nargs="?", default="300750.SZ")
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--key-file", type=Path, default=Path(os.environ.get("DEEPSEEK_API_KEY_FILE", DEFAULT_KEY_FILE)))
    parser.add_argument("--model", default=os.environ.get("DEEPSEEK_MODEL", DEFAULT_MODEL))
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--repair-existing", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--approve", action="store_true")
    parser.add_argument("--reviewer")
    parser.add_argument("--expected-narrative-hash")
    parser.add_argument("--expected-evidence-manifest-hash")
    args = parser.parse_args()
    if args.status:
        print(json.dumps(editorial_status(args.ticker, args.db), ensure_ascii=False))
        return
    if args.approve:
        if not args.reviewer or not args.expected_narrative_hash or not args.expected_evidence_manifest_hash:
            parser.error("--approve requires --reviewer, --expected-narrative-hash, and --expected-evidence-manifest-hash")
        path = approve_artifact(
            args.ticker, args.db, reviewer=args.reviewer,
            expected_narrative_hash=args.expected_narrative_hash,
            expected_evidence_manifest_hash=args.expected_evidence_manifest_hash,
        )
    else:
        path = repair_existing(args.ticker, args.db, args.key_file, args.model) if args.repair_existing else generate(args.ticker, args.db, args.key_file, args.model, args.force)
    artifact = json.loads(path.read_text(encoding="utf-8"))
    print(json.dumps({
        "status": artifact["validation"]["status"],
        "artifact": str(path),
        "model": artifact["model"],
        "snapshot_id": artifact["snapshot_id"],
        "usage": [receipt.get("usage") for receipt in artifact["receipts"]],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
