from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from data_store import DB_PATH, DEMO_POSITIONS, stock_payload
from research_artifact_store import PROMPT_VERSION, artifact_hash, load_artifact
from research_evidence import load_evidence_set
from report_contract import (
    ReportContractError,
    attach_report_contract,
    public_ai_narrative,
    validate_report_contract,
)


AI_VALIDATION_VERSION = "metric-source-v2"


def _latest_timestamp(*values: str | None) -> str | None:
    available = [value for value in values if value]
    if not available:
        return None
    return max(
        available,
        key=lambda value: datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc),
    )


ANNUAL_REPORT_URL = "https://www.catl.com/uploads/1/file/public/202603/20260310105829_c5p2l3q9ll.pdf"
Q1_REPORT_URL = "https://static.cninfo.com.cn/finalpage/2026-04-16/1225107946.PDF"
ANNUAL_RELEASE_URL = "https://www.catl.com/news/9654.html"
SODIUM_CONTRACT_URL = "https://www.catl.com/news/10075.html"
SNE_EV_URL = "https://www.sneresearch.com/en/insight/release_view/663/page/0?s_cat=%7C&s_keyword="
SNE_ESS_URL = "https://www.sneresearch.com/en/insight/release_view/583/page/24?s_cat=%7C&s_keyword="


CATL_PROFILE: dict[str, Any] = {
    "report_title": "宁德时代：龙头地位仍硬，但扩产、库存与现金转化必须一起看",
    "research_status": "verified",
    "research_depth": "deep",
    "summary": (
        "2025 年销量、利润和市场份额同步提升，2026 一季度收入与利润继续高增；"
        "但股价中期趋势仍弱，2025 年库存增长快于销量，且在建产能很大。"
        "这不是一张追涨票，而是一张用验证条件分批建立的长期核心仓。"
    ),
    "key_contradiction": "基本面与产业卡位很强，但市场正在为扩产、库存、技术路线和现金转化打折。",
    "position_plan": [
        {"stage": "初始仓", "weight": 4, "condition": "当前价位进入观察区，只建立研究仓，不因单日波动追价。"},
        {"stage": "验证仓", "weight": 2, "condition": "下一次正式披露确认利润增长未以现金转化持续恶化为代价。"},
        {"stage": "趋势仓", "weight": 2, "condition": "股价重新站稳 200 日均线，且储能合作计划推进并出现可核验订单。"},
    ],
    "thesis": [
        {
            "title": "龙头份额不是静态标签",
            "body": "2025 年全球动力电池使用量市占率 39.2%，同比提升 1.2 个百分点；海外市占率提升至 30.0%。",
            "claim_type": "fact",
            "source_ids": ["annual_market_share", "sne_2026_ev"],
        },
        {
            "title": "利润增速高于收入，质量暂时改善",
            "body": "2025 年收入同比增长 17.0%，归母净利润增长 42.3%；2026 一季度两者分别增长 52.4% 和 48.5%。",
            "claim_type": "fact",
            "source_ids": ["annual_financials", "q1_financials"],
        },
        {
            "title": "最大分歧不是有没有增长，而是增长能否消化扩产",
            "body": "2025 年电池系统产能利用率 96.9%，但库存量同比增加 75.47%，同时还有 321GWh 在建产能。",
            "claim_type": "inference",
            "source_ids": ["annual_capacity"],
        },
    ],
    "business_model": {
        "description": (
            "宁德时代的收入核心仍是动力电池，储能提供第二增长曲线，材料回收和零碳/换电生态用于"
            "降低资源波动、延长客户关系和扩大应用边界。真正的经济护城河不是单一化学配方，而是研发、"
            "工程化、规模制造、客户验证和全球服务共同形成的系统能力。"
        ),
        "segments": [
            {"name": "动力电池系统", "revenue_yi": 3165.1, "revenue_share": 74.70, "growth": 25.08, "gross_margin": 23.84},
            {"name": "储能电池系统", "revenue_yi": 624.4, "revenue_share": 14.74, "growth": 8.99, "gross_margin": 26.71},
            {"name": "电池材料及回收", "revenue_yi": 218.6, "revenue_share": 5.16, "growth": -23.83, "gross_margin": 27.27},
            {"name": "矿产资源及其他", "revenue_yi": 228.9, "revenue_share": 5.40, "growth": None, "gross_margin": None},
        ],
        "value_chain": [
            {"layer": "资源", "items": "锂、镍、钴、磷、石墨；自供、投资、长协与回收并行", "question": "资源价格和供应安全是否侵蚀利润"},
            {"layer": "材料", "items": "正极、负极、隔膜、电解液与材料体系", "question": "新化学体系能否降低资源依赖"},
            {"layer": "电芯与制造", "items": "LFP、三元、钠离子；绿色极限制造与超级拉线", "question": "良率、成本和一致性是否继续领先"},
            {"layer": "系统", "items": "CTP/电池包、储能柜/集装箱、BMS 与热管理", "question": "系统集成能否维持溢价"},
            {"layer": "应用与生态", "items": "乘用车、商用车、储能、数据中心、船舶、航空、换电", "question": "新场景能否从验证变成规模收入"},
        ],
        "source_ids": ["annual_business", "annual_segments"],
    },
    "industry_position": {
        "headline": "动力电池连续九年全球第一，储能电池连续五年全球第一；但强地位不会自动消灭周期。",
        "metrics": [
            {"label": "全球动力电池份额", "value": "39.2%", "note": "2025 年，同比 +1.2pct"},
            {"label": "国内动力电池份额", "value": "43.42%", "note": "2025 年"},
            {"label": "海外动力电池份额", "value": "30.0%", "note": "2025 年"},
            {"label": "锂电池销量", "value": "661GWh", "note": "同比 +39.16%"},
        ],
        "source_ids": ["annual_market_share", "sne_2026_ev", "sne_2025_ess"],
    },
    "moat": [
        {"name": "规模制造", "score": 9.0, "proof": "772GWh 产能、96.9% 利用率、748GWh 产量；规模和良率共同决定成本。", "source_ids": ["annual_capacity"]},
        {"name": "研发与工程化", "score": 8.8, "proof": "2025 年研发投入 221.5 亿元，占收入 5.23%；从材料到系统和制造全链条研发。", "source_ids": ["annual_rd"]},
        {"name": "客户与验证", "score": 8.5, "proof": "前五大客户占收入 38.96%，说明客户深度高，也带来集中度与议价风险。", "source_ids": ["annual_customers"]},
        {"name": "技术组合", "score": 8.2, "proof": "LFP、三元、钠电与双核/多核架构并行，降低押注单一路线的风险。", "source_ids": ["annual_products"]},
        {"name": "资本与全球交付", "score": 7.8, "proof": "H 股上市补充海外产能资金与资本平台；海外建设同时增加执行和地缘复杂度。", "source_ids": ["annual_h_share"]},
    ],
    "management": {
        "score": 7.3,
        "strengths": [
            "创始人曾毓群同时任董事长和总经理，战略一致性强、执行链条短。",
            "连续三年以净利润 50% 实施现金分红，2025 年度拟每 10 股派 69.57 元。",
            "2025 年完成 H 股上市，为匈牙利项目和全球化提供资本。",
        ],
        "watchouts": [
            "董事长与总经理合一带来关键人和制衡风险，需持续看董事会独立性与授权边界。",
            "全球扩产、换电、零碳生态和新化学体系并行，对资本配置提出很高要求。",
        ],
        "source_ids": ["annual_governance", "annual_dividend", "annual_h_share"],
    },
    "serenity_factors": [
        {"key": "demand_inflection", "label": "需求拐点", "score": 4.7, "weight": 15, "reason": "销量 +39%，2026Q1 收入 +52%，储能和新场景继续打开需求。", "source_ids": ["annual_financials", "q1_financials"]},
        {"key": "architecture_coupling", "label": "架构耦合", "score": 4.6, "weight": 10, "reason": "电池是电动车和储能系统的核心性能、成本与安全单元。", "source_ids": ["annual_business"]},
        {"key": "chokepoint_severity", "label": "卡位强度", "score": 4.5, "weight": 15, "reason": "客户验证、工程化和量产一致性使头部供应商短期难被完全替换。", "source_ids": ["annual_market_share", "annual_capacity"]},
        {"key": "supplier_concentration", "label": "供应集中", "score": 4.4, "weight": 12, "reason": "SNE 统计显示 2026 年 1–4 月 CATL 份额 40.1%，与 BYD 合计 54.3%。", "source_ids": ["sne_2026_ev"]},
        {"key": "expansion_difficulty", "label": "扩产难度", "score": 4.2, "weight": 12, "reason": "772GWh 既有产能与 321GWh 在建产能体现规模门槛；客户认证、良率和全球服务能力仍需持续验证。", "source_ids": ["annual_rd", "annual_capacity"]},
        {"key": "evidence_quality", "label": "证据质量", "score": 4.6, "weight": 15, "reason": "核心事实来自审计年报、监管披露、不可变行情快照，并用 SNE 原始发布做外部交叉验证。", "source_ids": ["annual_financials", "q1_financials", "market_snapshot", "sne_2026_ev"]},
        {"key": "valuation_disconnect", "label": "估值错配", "score": 3.3, "weight": 11, "reason": "约 21 倍 TTM PE 不贵到失真，但 PB 约 5.1 倍且扩产周期仍要求安全边际。", "source_ids": ["market_snapshot"]},
        {"key": "catalyst_timing", "label": "催化剂时点", "score": 4.2, "weight": 10, "reason": "Q1 高增、欧洲钠电储能合作计划与后续财报形成近中期验证窗口；MOU 不等同于确认订单。", "source_ids": ["q1_financials", "sodium_contract"]},
    ],
    "serenity_penalties": [
        {"key": "dilution_financing", "label": "融资/摊薄", "rating": 0.0, "reason": "当前未见足以单独扣分的新增摊薄证据；后续融资计划需持续复核。"},
        {"key": "governance", "label": "治理/关键人", "rating": 1.5, "reason": "董事长兼总经理，战略效率与制衡风险并存。"},
        {"key": "geopolitics", "label": "地缘与海外执行", "rating": 2.0, "reason": "海外工厂、技术合作和贸易政策增加不确定性。"},
        {"key": "liquidity", "label": "流动性", "rating": 0.0, "reason": "A/H 两地上市且成交活跃，当前未见流动性折价证据。"},
        {"key": "hype_risk", "label": "叙事拥挤", "rating": 1.0, "reason": "零碳、换电、低空与 AI 数据中心叙事多，需区分收入贡献和远期故事。"},
        {"key": "accounting_quality", "label": "会计与现金转化", "rating": 0.5, "reason": "审计意见标准，但 Q1 经营现金流增速显著慢于利润。"},
        {"key": "cyclicality", "label": "行业周期", "rating": 1.5, "reason": "产能、库存和原材料价格仍会放大盈利波动。"},
        {"key": "alternative_design_risk", "label": "替代路线", "rating": 1.5, "reason": "新电池体系、整车厂自研和系统架构变化可能削弱现有优势。"},
    ],
    "valuation_scenarios": [
        {"case": "bear", "label": "悲观", "eps": 16.5, "pe": 16.0, "assumption": "增长回落，扩产和库存压制资本回报；市场按成熟制造龙头定价。"},
        {"case": "base", "label": "基准", "eps": 18.8, "pe": 21.0, "assumption": "2026 盈利保持中高速增长，动力与储能份额稳定，估值维持当前中枢。"},
        {"case": "bull", "label": "乐观", "eps": 21.0, "pe": 24.0, "assumption": "海外、储能和新产品共振，现金转化改善，市场重新给予成长溢价。"},
    ],
    "catalysts": [
        {"date": "2026-07-16", "title": "欧洲 5GWh 钠电储能 MOU", "body": "与 Alfen 签署谅解备忘录，计划自 2027 年起在西欧部署 5GWh 天恒钠电储能系统；这是商业化验证信号，但不等同于已确认订单或收入。", "source_ids": ["sodium_contract"]},
        {"date": "下一份正式财报", "title": "现金转化验证", "body": "重点不是只看收入和利润，而是经营现金流、应收与库存能否同步改善。", "source_ids": ["q1_financials", "annual_capacity"]},
        {"date": "2026H2–2027", "title": "在建产能和海外工厂爬坡", "body": "如果产能利用率保持高位、海外份额继续提升，扩产会变成份额壁垒；反之会成为折旧和减值风险。", "source_ids": ["annual_capacity", "annual_h_share"]},
    ],
    "risks": [
        {"rank": 1, "title": "扩产与库存错配", "impact": "高", "probability": "中", "trigger": "产能利用率跌破 90%，或库存增速连续两个报告期显著快于销量。", "evidence": "2025 年库存 +75.47%，在建产能 321GWh。", "source_ids": ["annual_capacity"]},
        {"rank": 2, "title": "技术路线和整车厂自研替代", "impact": "高", "probability": "中", "trigger": "全球份额同比下降 2pct 以上，或关键客户转向替代供应商/自研体系。", "evidence": "公司年报也把新产品和新技术开发列为明确风险。", "source_ids": ["annual_risks"]},
        {"rank": 3, "title": "现金转化弱于利润", "impact": "中", "probability": "中", "trigger": "经营现金流增速连续两个季度落后于利润，且应收/库存同步上升。", "evidence": "2026Q1 经营现金流同比 +2.47%，明显低于净利润 +48.52%。", "source_ids": ["q1_financials"]},
        {"rank": 4, "title": "全球化与地缘执行", "impact": "高", "probability": "中", "trigger": "海外项目延期、贸易限制升级或海外客户认证进度放缓。", "evidence": "海外份额和海外产能已成为增长的重要部分。", "source_ids": ["annual_market_share", "annual_h_share"]},
        {"rank": 5, "title": "原材料价格和供应", "impact": "中", "probability": "中", "trigger": "锂镍钴价格快速上行且产品传导滞后，导致毛利率显著下滑。", "evidence": "公司在年报中将原材料价格和供应列为明确风险。", "source_ids": ["annual_risks"]},
        {"rank": 6, "title": "创始人治理集中", "impact": "中", "probability": "低", "trigger": "重大资本配置缺乏清晰回报门槛，或管理层/董事会出现异常变动。", "evidence": "实际控制人同时担任董事长和总经理。", "source_ids": ["annual_governance"]},
    ],
    "falsification": [
        "全球动力电池份额跌破 36%，且无法用主动放弃低质量订单解释。",
        "连续两个正式报告期出现库存增长显著快于销量、产能利用率跌破 90%。",
        "经营现金流/净利润持续低于 1，且应收、库存同步恶化。",
        "关键新产品无法量产或客户认证推迟，研发投入上升但商业转化下降。",
        "Base Case 依赖的 18.8 元 EPS 明显不可达，或市场风险要求使合理 PE 低于 18 倍。",
    ],
    "watchlist": [
        {"metric": "动力/储能销量与份额", "current": "661GWh；动力份额 39.2%", "threshold": "份额不低于 37%", "frequency": "半年/年度"},
        {"metric": "产能利用率与库存", "current": "96.9%；库存 186GWh", "threshold": "利用率 ≥90%，库存增速不持续高于销量", "frequency": "半年/年度"},
        {"metric": "经营现金流/净利润", "current": "2026Q1 约 1.62x", "threshold": "TTM 保持 ≥1.0x", "frequency": "季度"},
        {"metric": "毛利率", "current": "2026Q1 24.82%", "threshold": "不连续两季低于 23%", "frequency": "季度"},
        {"metric": "价格趋势", "current": "低于 200 日均线", "threshold": "站稳 200 日均线再完成最后 2%", "frequency": "周"},
    ],
    "sources": [
        {"id": "annual_business", "document_id": "catl_2025_annual", "title": "2025 年年度报告 · 主要业务", "kind": "primary", "strength": "强", "known_at": "2026-03-10", "url": ANNUAL_REPORT_URL, "note": "年报第 13–14 页"},
        {"id": "annual_products", "document_id": "catl_2025_annual", "title": "2025 年年度报告 · 产品与技术路线", "kind": "primary", "strength": "强", "known_at": "2026-03-10", "url": ANNUAL_REPORT_URL, "note": "年报第 14、20、25 页"},
        {"id": "annual_market_share", "document_id": "catl_2025_annual", "title": "2025 年年度报告 · 市场份额与销量", "kind": "primary", "strength": "强", "known_at": "2026-03-10", "url": ANNUAL_REPORT_URL, "note": "年报第 16–20 页；公司转引 SNE Research，另以 SNE 原始发布交叉验证"},
        {"id": "annual_segments", "document_id": "catl_2025_annual", "title": "2025 年年度报告 · 分产品收入与毛利率", "kind": "primary", "strength": "强", "known_at": "2026-03-10", "url": ANNUAL_REPORT_URL, "note": "年报第 23–24 页"},
        {"id": "annual_capacity", "document_id": "catl_2025_annual", "title": "2025 年年度报告 · 产能、产量、销量与库存", "kind": "primary", "strength": "强", "known_at": "2026-03-10", "url": ANNUAL_REPORT_URL, "note": "年报第 25–26 页"},
        {"id": "annual_customers", "document_id": "catl_2025_annual", "title": "2025 年年度报告 · 主要客户", "kind": "primary", "strength": "强", "known_at": "2026-03-10", "url": ANNUAL_REPORT_URL, "note": "年报第 27 页"},
        {"id": "annual_rd", "document_id": "catl_2025_annual", "title": "2025 年年度报告 · 研发投入与现金流", "kind": "primary", "strength": "强", "known_at": "2026-03-10", "url": ANNUAL_REPORT_URL, "note": "年报第 29 页"},
        {"id": "annual_financials", "document_id": "catl_2025_annual", "title": "2025 年年度报告 · 主要财务指标", "kind": "primary", "strength": "强", "known_at": "2026-03-10", "url": ANNUAL_REPORT_URL, "note": "标准无保留审计意见"},
        {"id": "annual_risks", "document_id": "catl_2025_annual", "title": "2025 年年度报告 · 可能面对的风险", "kind": "primary", "strength": "强", "known_at": "2026-03-10", "url": ANNUAL_REPORT_URL, "note": "年报第 38–39 页"},
        {"id": "annual_governance", "document_id": "catl_2025_annual", "title": "2025 年年度报告 · 管理层和治理", "kind": "primary", "strength": "强", "known_at": "2026-03-10", "url": ANNUAL_REPORT_URL, "note": "年报第 49–53 页"},
        {"id": "annual_dividend", "document_id": "catl_2025_release", "title": "2025 年度分红方案与年报发布", "kind": "company_release", "strength": "中", "known_at": "2026-03-10", "url": ANNUAL_RELEASE_URL, "note": "公司官网摘要；关键分红数字与年报摘要一致"},
        {"id": "annual_h_share", "document_id": "catl_2025_annual", "title": "2025 年年度报告 · H 股上市", "kind": "primary", "strength": "强", "known_at": "2026-03-10", "url": ANNUAL_REPORT_URL, "note": "年报第 19 页"},
        {"id": "q1_financials", "document_id": "catl_2026_q1", "title": "2026 年第一季度报告", "kind": "primary", "strength": "强", "known_at": "2026-04-16", "url": Q1_REPORT_URL, "note": "未经审计季度报告；收入、利润、现金流和资产负债表"},
        {"id": "sodium_contract", "document_id": "catl_alfen_mou_20260716", "title": "宁德时代与 Alfen 签署 5GWh 钠电储能 MOU", "kind": "company_release", "strength": "中", "known_at": "2026-07-16", "url": SODIUM_CONTRACT_URL, "note": "谅解备忘录及计划部署，不等同于已确认订单或收入"},
        {"id": "sne_2026_ev", "document_id": "sne_2026_ev_jan_apr", "title": "SNE Research · 2026 年 1–4 月全球动力电池装机", "kind": "independent", "strength": "强", "known_at": "2026-06-03", "url": SNE_EV_URL, "note": "CATL 141.4GWh、同比 +19.8%、份额 40.1%；CATL 与 BYD 合计 54.3%"},
        {"id": "sne_2025_ess", "document_id": "sne_2025_ess", "title": "SNE Research · 2025 全球储能电芯出货", "kind": "independent", "strength": "中", "known_at": "2026-03-05", "url": SNE_ESS_URL, "note": "全球 ESS 电芯出货约 550GWh，CATL 位列第一、份额约 30%"},
    ],
}


def _round_or_none(value: Any, digits: int = 2) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def _serenity_score(profile: dict[str, Any]) -> dict[str, Any]:
    factors = []
    raw = 0.0
    for factor in profile["serenity_factors"]:
        contribution = float(factor["score"]) / 5.0 * float(factor["weight"])
        raw += contribution
        factors.append({**factor, "contribution": round(contribution, 2)})
    penalties = []
    total_penalty = 0.0
    for penalty in profile["serenity_penalties"]:
        points = float(penalty["rating"]) * 2.0
        total_penalty += points
        penalties.append({**penalty, "points": round(points, 2)})
    final = max(0.0, raw - total_penalty)
    if final >= 85:
        label = "最高研究优先级"
    elif final >= 70:
        label = "高优先级继续研究"
    elif final >= 55:
        label = "值得跟踪"
    else:
        label = "证据或卡位不足"
    return {
        "method": "Serenity bottleneck scorecard v1",
        "raw_score": round(raw, 1),
        "penalty": round(total_penalty, 1),
        "final_score": round(final, 1),
        "label": label,
        "meaning": "这是基于当前单公司底稿的暂定研究优先级，不是预期收益、买入信号或仓位公式；缺失证据必须在下一次更新时重新评分。",
        "factors": factors,
        "penalties": penalties,
    }


def _financial_view(stock: dict[str, Any]) -> dict[str, Any]:
    rows = stock.get("financials") or []
    latest = rows[0] if rows else {}
    annual = next((row for row in rows if row.get("report_type") == "年报"), {})
    return {
        "latest_period": latest.get("report_date"),
        "latest_type": latest.get("report_type"),
        "headline": (
            f"{latest.get('report_type', '最新披露')}收入同比 {_round_or_none(latest.get('revenue_yoy'), 1)}%，"
            f"归母净利润同比 {_round_or_none(latest.get('net_profit_yoy'), 1)}%，"
            f"毛利率 {_round_or_none(latest.get('gross_margin'), 1)}%。"
            if latest else "Missing evidence：当前快照没有财务记录。"
        ),
        "annual_quality": {
            "roe": _round_or_none(annual.get("roe"), 2),
            "gross_margin": _round_or_none(annual.get("gross_margin"), 2),
            "net_margin": _round_or_none(annual.get("net_margin"), 2),
            "debt_ratio": _round_or_none(annual.get("debt_ratio"), 2),
            "operating_cash_per_share": _round_or_none(annual.get("operating_cash_per_share"), 2),
        },
        "series": [
            {
                "report_date": row.get("report_date"),
                "report_type": row.get("report_type"),
                "revenue_yi": _round_or_none(float(row["revenue"]) / 1e8 if row.get("revenue") else None, 1),
                "net_profit_yi": _round_or_none(float(row["net_profit"]) / 1e8 if row.get("net_profit") else None, 1),
                "revenue_yoy": _round_or_none(row.get("revenue_yoy"), 1),
                "net_profit_yoy": _round_or_none(row.get("net_profit_yoy"), 1),
                "gross_margin": _round_or_none(row.get("gross_margin"), 1),
                "net_margin": _round_or_none(row.get("net_margin"), 1),
                "roe": _round_or_none(row.get("roe"), 1),
            }
            for row in rows
        ],
        "quality_notes": _financial_quality_notes(latest, annual),
    }


def _financial_quality_notes(latest: dict[str, Any], annual: dict[str, Any]) -> list[str]:
    """Describe only metrics present in the immutable financial snapshot."""
    notes: list[str] = []
    if annual:
        notes.append(
            f"年度 ROE {_round_or_none(annual.get('roe'), 1)}%，毛利率 "
            f"{_round_or_none(annual.get('gross_margin'), 1)}%，净利率 "
            f"{_round_or_none(annual.get('net_margin'), 1)}%；这是盈利质量基线，不等同于护城河结论。"
        )
        notes.append(
            f"年度资产负债率 {_round_or_none(annual.get('debt_ratio'), 1)}%，"
            "后续需结合行业口径、现金流量表和表外承诺判断资本结构。"
        )
    if latest:
        notes.append(
            f"最新披露营收同比 {_round_or_none(latest.get('revenue_yoy'), 1)}%，"
            f"归母净利润同比 {_round_or_none(latest.get('net_profit_yoy'), 1)}%；"
            "下一版重点核验增长是否伴随毛利率和现金转化改善。"
        )
    return notes or ["当前快照没有足够财务字段形成质量判断。"]


def _valuation_view(stock: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    quote = stock.get("market_quote") or {}
    current = float(quote.get("price") or stock.get("reference_price") or 0)
    scenarios = []
    for item in profile["valuation_scenarios"]:
        target = float(item["eps"]) * float(item["pe"])
        upside = (target / current - 1) * 100 if current else None
        scenarios.append({**item, "target_price": round(target, 1), "upside_pct": _round_or_none(upside, 1)})
    base = next(item for item in scenarios if item["case"] == "base")
    trailing_eps = 16.14
    return {
        "method": "2026E EPS × 情景 PE（非 DCF）",
        "current_price": _round_or_none(current, 2),
        "pe_ttm": _round_or_none(quote.get("pe_ttm"), 2),
        "pb": _round_or_none(quote.get("pb"), 2),
        "scenarios": scenarios,
        "earnings_bridge": {
            "base_period": "2025A",
            "base_eps": trailing_eps,
            "basis": "2025 年归母净利润 ÷ 期末总股本的近似口径；用于显示假设跨度，不替代正式盈利预测模型。",
            "cases": [
                {"case": item["case"], "label": item["label"], "eps": item["eps"], "growth_pct": round((float(item["eps"]) / trailing_eps - 1) * 100, 1)}
                for item in scenarios
            ],
        },
        "base_view": f"基准目标价 ¥{base['target_price']:.1f}，相对当前价 {base['upside_pct']:+.1f}%。",
        "reverse_implied": (
            f"当前价 ¥{current:.2f} 若按 21 倍 PE 反推，需要约 ¥{current / 21:.2f} 的年度 EPS；"
            "真正要判断的是这个盈利是否能在扩产和现金转化压力下持续。"
            if current else "Missing evidence：没有当前价格，无法反推市场隐含盈利。"
        ),
        "warning": "目标价是显式假设的结果，不是事实。EPS 或合理倍数变化会直接改变结论。",
    }


def _position_plan(profile: dict[str, Any], target_weight: float) -> list[dict[str, Any]]:
    target = float(target_weight)
    first = round(target * 0.5, 1)
    second = round(target * 0.25, 1)
    weights = [first, second, round(target - first - second, 1)]
    return [{**item, "weight": weight} for item, weight in zip(profile["position_plan"], weights, strict=True)]


def research_profile_hash(ticker: str | None = None) -> str:
    """Hash one report family's policy; use '*' only for the portfolio approval package."""
    normalized = (ticker or "300750.SZ").upper()
    catalogue = {item["ticker"]: item for item in DEMO_POSITIONS}
    if normalized == "300750.SZ":
        payload = {"report_version": "deep-research-v1.2", "ticker": normalized, "profile": CATL_PROFILE}
    elif normalized == "*":
        payload = {
            "portfolio_research_policy": "portfolio-eight-v1",
            "profile_hashes": {item["ticker"]: research_profile_hash(item["ticker"]) for item in DEMO_POSITIONS},
        }
    elif normalized in catalogue:
        item = catalogue[normalized]
        payload = {
            "report_version": "quant-research-baseline-v1.0",
            "policy": "data-verified-research-incomplete-model-observation-only",
            "ticker": normalized, "name": item["name"], "industry": item["industry"],
        }
    else:
        raise ValueError(f"unsupported research profile ticker: {normalized}")
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


def research_profile_tickers() -> tuple[str, ...]:
    return tuple(item["ticker"] for item in DEMO_POSITIONS)


def research_logic_hash() -> str:
    """Bind approvals to the exact report generator, including derived valuation logic."""
    digest = hashlib.sha256()
    for path in (
        Path(__file__),
        Path(__file__).with_name("report_contract.py"),
        Path(__file__).with_name("schemas") / "research-report-v1.schema.json",
        Path(__file__).with_name("schemas") / "research-report-payload-v1.schema.json",
    ):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def writer_logic_hash() -> str:
    """Bind display approval to the current prompt, validator and editorial rules."""
    return hashlib.sha256(Path(__file__).with_name("deepseek_writer.py").read_bytes()).hexdigest()


def _report_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


def build_evidence_pack(report: dict[str, Any], evidence_set: dict[str, Any] | None = None) -> dict[str, Any]:
    """The exact deterministic evidence boundary supplied to a narrative model."""
    contract = report.get("source_contract") or {}
    pack = {
        "identity": {
            "ticker": report["ticker"],
            "name": report["name"],
            "industry": report["industry"],
            "as_of": report["as_of"],
            "snapshot_id": report["generated_from"]["snapshot_id"],
        },
        "execution_contract": {
            "proposed_initial_weight": report["executive"].get("proposed_initial_weight"),
            "conditional_max_weight": report["executive"].get("max_target_weight"),
            "model_observation_weight": report["executive"].get("model_observation_weight"),
            "weight_semantics": report["executive"].get("weight_semantics", "execution_contract"),
            "position_plan": report["executive"]["position_plan"],
            "key_contradiction": report["executive"]["key_contradiction"],
            "source_ids": contract.get("execution") or ["market_snapshot"],
        },
        "market": {**report["market"], "source_ids": ["market_snapshot"]},
        "financials": {**report["financials"], "source_ids": contract.get("financials") or ["market_snapshot"]},
        "business_model": report["business_model"],
        "industry_position": report["industry_position"],
        "moat": report["moat"],
        "quant_signals": report.get("quant_signals") or [],
        "management": report["management"],
        "serenity": report["serenity"],
        "valuation": {**report["valuation"], "source_ids": contract.get("valuation") or ["market_snapshot"]},
        "stress_test": (
            {**report["stress_test"], "source_ids": contract.get("stress_test") or ["market_snapshot"]}
            if report.get("stress_test") else None
        ),
        "catalysts": report["catalysts"],
        "risks": report["risks"],
        "falsification": {
            "items": report["falsification"],
            "source_ids": contract.get("falsification") or ["market_snapshot"],
        },
        "watchlist": {
            "items": report["watchlist"],
            "source_ids": contract.get("watchlist") or ["market_snapshot"],
        },
        "sources": report["sources"],
    }
    if evidence_set is not None:
        if evidence_set.get("ticker") != report["ticker"] or evidence_set.get("snapshot_id") != report["generated_from"]["snapshot_id"]:
            raise ValueError("evidence set identity does not match report")
        if evidence_set.get("status") != "passed":
            raise ValueError("only a passed evidence set may enter the model boundary")
        pack["evidence_set"] = {
            "id": evidence_set["evidence_set_id"],
            "manifest_hash": evidence_set["manifest_hash"],
            "policy_version": evidence_set["policy_version"],
            "knowledge_cutoff": evidence_set["knowledge_cutoff"],
            "documents": evidence_set["documents"],
        }
    return pack


def _active_ai_artifact(
    db_path: Path,
    ticker: str,
    snapshot_id: str,
    deterministic_report: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    artifact = load_artifact(db_path, ticker, snapshot_id)
    if not artifact:
        return None
    narrative = artifact.get("narrative")
    if not isinstance(narrative, dict):
        return None
    expected_narrative_hash = _report_hash(narrative)
    if not expected_narrative_hash or not isinstance(artifact.get("narrative_hash"), str):
        return None
    evidence_set = load_evidence_set(ticker, snapshot_id, db_path)
    if not evidence_set:
        return None
    expected_evidence_hash = (
        _report_hash(build_evidence_pack(deterministic_report, evidence_set)) if deterministic_report is not None else artifact.get("evidence_hash")
    )
    current_validation = artifact.get("validation") or {}
    if deterministic_report is not None:
        from deepseek_writer import validate_narrative

        current_validation = validate_narrative(narrative, build_evidence_pack(deterministic_report, evidence_set))
    approval = artifact.get("editorial_approval") or {}
    if (
        current_validation.get("status") != "passed"
        or artifact.get("validation_version") != AI_VALIDATION_VERSION
        or approval.get("status") != "approved"
        or approval.get("approval_version") != "human-editorial-v1"
        or not isinstance(approval.get("narrative_hash"), str)
        or approval.get("narrative_hash") != expected_narrative_hash
        or approval.get("evidence_manifest_hash") != evidence_set["manifest_hash"]
        or artifact.get("ticker") != ticker.upper()
        or artifact.get("snapshot_id") != snapshot_id
        or artifact.get("profile_hash") != research_profile_hash(ticker)
        or artifact.get("research_logic_hash") != research_logic_hash()
        or artifact.get("writer_logic_hash") != writer_logic_hash()
        or artifact.get("prompt_version") != PROMPT_VERSION
        or artifact.get("evidence_hash") != expected_evidence_hash
        or artifact.get("evidence_set_id") != evidence_set["evidence_set_id"]
        or artifact.get("evidence_manifest_hash") != evidence_set["manifest_hash"]
        or artifact.get("narrative_hash") != expected_narrative_hash
    ):
        return None
    active = deepcopy(artifact)
    active["validation"] = current_validation
    return active


def active_research_artifact_hash(db_path: Path, ticker: str, snapshot_id: str) -> str | None:
    return artifact_hash(db_path, ticker, snapshot_id) if _active_ai_artifact(db_path, ticker, snapshot_id) else None


def _safe_stock_status(stock: dict[str, Any]) -> dict[str, Any]:
    return {
        "ticker": stock.get("ticker"),
        "name": stock.get("name"),
        "snapshot_id": stock.get("snapshot_id"),
        "data_mode": stock.get("data_mode"),
        "snapshot_quality": stock.get("snapshot_quality"),
        "publication_status": stock.get("publication_status"),
        "has_market_quote": bool(stock.get("market_quote")),
        "has_features": bool(stock.get("features")),
        "financial_record_count": len(stock.get("financials") or []),
    }


def _research_gate(stock: dict[str, Any], profile_sources: list[dict[str, Any]] | None = None) -> tuple[bool, list[str]]:
    quote = stock.get("market_quote") or {}
    features = stock.get("features") or {}
    financials = stock.get("financials") or []
    gate = stock.get("data_gate") or {}
    runs = {row.get("source_key"): row for row in gate.get("source_runs") or []}
    failures: list[str] = []

    if stock.get("data_mode") != "REAL": failures.append("snapshot is not REAL")
    if stock.get("snapshot_quality") != "passed": failures.append("snapshot quality is not passed")
    if stock.get("publication_status") not in {"quality_passed", "approved", "published"}: failures.append("publication has not passed quality review")
    required_quote_fields = ("price", "quote_time", "source_key", "source_url", "raw_hash", "fetched_at")
    if quote.get("quality_status") != "accepted" or any(quote.get(key) in {None, ""} for key in required_quote_fields):
        failures.append("quote row is incomplete or not accepted")
    required_feature_fields = ("return_60d", "return_250d", "volatility_60d", "ma20", "ma60", "ma200", "composite_score", "feature_version")
    if float(features.get("data_completeness") or 0) < 100 or any(features.get(key) is None for key in required_feature_fields):
        failures.append("feature row is incomplete")
    required_financial_fields = ("report_date", "notice_date", "report_type", "revenue", "net_profit", "revenue_yoy", "net_profit_yoy", "source_key", "raw_hash")
    if len(financials) < 2 or any(row.get("quality_status") != "accepted" or any(row.get(key) in {None, ""} for key in required_financial_fields) for row in financials):
        failures.append("financial rows are incomplete or not accepted")
    positions = int(gate.get("position_count") or 0)
    if positions < 1 or int(gate.get("accepted_quote_count") or 0) != positions:
        failures.append("portfolio quote coverage is incomplete")
    if int(gate.get("accepted_bar_count") or 0) < int(gate.get("required_bar_count") or positions * 250) or int(gate.get("ticker_bar_count") or 0) < 250:
        failures.append("daily bar coverage is incomplete")
    if int(gate.get("accepted_financial_count") or 0) < int(gate.get("required_financial_count") or positions):
        failures.append("portfolio financial coverage is incomplete")
    coverage = gate.get("portfolio_coverage") or []
    if len(coverage) != positions or any(
        int(row.get("quote_count") or 0) != 1
        or int(row.get("bar_count") or 0) < 250
        or int(row.get("financial_count") or 0) < 1
        for row in coverage
    ):
        failures.append("one or more portfolio tickers fail per-ticker coverage")
    snapshot_as_of = str(gate.get("snapshot_as_of") or "")[:10]
    snapshot_known_date = str(gate.get("snapshot_known_at") or "")[:10]
    if not snapshot_as_of or not snapshot_known_date or any(
        str(row.get("max_trade_date") or "")[:10] != snapshot_as_of
        or str(row.get("quote_time") or "")[:10] != snapshot_known_date
        or str(row.get("quote_time") or "")[:10] < snapshot_as_of
        or str(row.get("max_notice_date") or "")[:10] > snapshot_known_date
        for row in coverage
    ):
        failures.append("portfolio data freshness or point-in-time alignment failed")
    if any(str(source.get("known_at") or "")[:10] > snapshot_known_date for source in (profile_sources or [])):
        failures.append("research source is newer than the snapshot knowledge boundary")
    required_runs = {"tencent_quote": positions, "tencent_qfq_daily": positions * 250, "eastmoney_f10_main": positions}
    for source_key, minimum in required_runs.items():
        run = runs.get(source_key) or {}
        if run.get("status") != "success" or int(run.get("accepted_count") or 0) < minimum or not run.get("finished_at"):
            failures.append(f"source run failed coverage: {source_key}")
    return not failures, failures


def _market_view(stock: dict[str, Any]) -> dict[str, Any]:
    quote = stock.get("market_quote") or {}
    features = stock.get("features") or {}
    return {
        "price": quote.get("price"),
        "change_pct": quote.get("change_pct"),
        "pe_ttm": quote.get("pe_ttm"),
        "pb": quote.get("pb"),
        "market_cap_yi": quote.get("market_cap_yi"),
        "return_20d": _round_or_none(features.get("return_20d"), 1),
        "return_60d": _round_or_none(features.get("return_60d"), 1),
        "return_250d": _round_or_none(features.get("return_250d"), 1),
        "volatility_60d": _round_or_none(features.get("volatility_60d"), 1),
        "max_drawdown_250d": _round_or_none(features.get("max_drawdown_250d"), 1),
        "ma20": _round_or_none(features.get("ma20"), 2),
        "ma60": _round_or_none(features.get("ma60"), 2),
        "ma200": _round_or_none(features.get("ma200"), 2),
        "composite_score": _round_or_none(features.get("composite_score"), 1),
    }


def _baseline_position_plan(stock: dict[str, Any]) -> list[dict[str, Any]]:
    target = float(stock["target_weight"])
    return [
        {"stage": "组合模型输出", "weight": target, "condition": "仅作为观察权重，不是已经批准的可执行仓位。"},
        {"stage": "公司级深度研究", "weight": 0.0, "condition": "补齐经营、行业、治理与正式估值证据后重新评审。"},
        {"stage": "投委会批准", "weight": 0.0, "condition": "只有 Park 明确批准的版本才可转成执行合同。"},
    ]


def _baseline_serenity(stock: dict[str, Any]) -> dict[str, Any]:
    features = stock.get("features") or {}
    definitions = (
        ("quality", "财务质量", "quality_score", "财务增速、ROE 与资产负债率的量化合成，只是筛选线索。", "financial_snapshot"),
        ("value", "估值约束", "value_score", "当前 PE/PB 的横截面量化得分，不代表公司已被低估。", "market_snapshot"),
        ("trend", "趋势确认", "trend_score", "20/60/250 日收益和均线位置的合成结果。", "market_snapshot"),
        ("resilience", "风险韧性", "resilience_score", "波动、回撤和负债率共同形成的风险承受线索。", ["market_snapshot", "financial_snapshot"]),
    )
    factors = []
    raw = 0.0
    for key, label, field, reason, source_ids in definitions:
        score100 = float(features.get(field) or 0)
        score5 = round(score100 / 20, 2)
        contribution = round(score5 / 5 * 25, 2)
        raw += contribution
        factors.append({
            "key": key, "label": label, "score": score5, "weight": 25,
            "contribution": contribution, "reason": reason,
            "source_ids": source_ids if isinstance(source_ids, list) else [source_ids],
        })
    return {
        "method": "A-share quantitative baseline v1",
        "raw_score": round(raw, 1),
        "penalty": 0.0,
        "final_score": round(raw, 1),
        "label": "量化基线，等待公司级深度验证",
        "meaning": "四项分数用于排序和发现问题，不是护城河、预期收益或买入信号；公司、行业与治理证据将在深度稿补齐。",
        "factors": factors,
        "penalties": [],
    }


def _baseline_valuation(stock: dict[str, Any]) -> dict[str, Any]:
    quote = stock.get("market_quote") or {}
    current = float(quote.get("price") or stock.get("reference_price") or 0)
    return {
        "status": "pending_company_research",
        "method": "待补：公司级盈利预测、同行比较与历史估值分位",
        "current_price": _round_or_none(current, 2),
        "pe_ttm": _round_or_none(quote.get("pe_ttm"), 2),
        "pb": _round_or_none(quote.get("pb"), 2),
        "reason": "当前证据只支持展示市场估值快照，不支持输出基本面目标价。",
    }


def _baseline_stress_test(stock: dict[str, Any]) -> dict[str, Any]:
    quote = stock.get("market_quote") or {}
    current = float(quote.get("price") or stock.get("reference_price") or 0)
    cases = (
        ("bear", "悲观", 0.80, "把当前价格压低 20%，用于检查回撤承受力，不是基本面目标价。"),
        ("base", "基准", 1.00, "以当前价格为基线，等待盈利预测和历史估值分位补齐。"),
        ("bull", "乐观", 1.20, "把当前价格上移 20%，用于检查赔率敏感度，不是正式上行空间。"),
    )
    scenarios = [
        {
            "case": case, "label": label, "price_basis": round(current, 2), "stress_multiple": multiple,
            "stress_price": round(current * multiple, 1), "change_pct": round((multiple - 1) * 100, 1),
            "assumption": assumption,
        }
        for case, label, multiple, assumption in cases
    ]
    return {
        "method": "当前价 × 情景倍数",
        "price_basis": round(current, 2),
        "formula": "stress_price = price_basis × stress_multiple",
        "scenarios": scenarios,
        "warning": "压力价不是目标价。没有公司级盈利预测与估值证据前，不得把 ±20% 情景当成预期收益。",
    }


def _baseline_report(stock: dict[str, Any], db_path: Path) -> dict[str, Any]:
    quote = stock.get("market_quote") or {}
    features = stock.get("features") or {}
    financials = _financial_view(stock)
    latest = (stock.get("financials") or [{}])[0]
    market_source = {
        "id": "market_snapshot", "document_id": f"market_{stock.get('snapshot_id')}_{stock['ticker']}",
        "title": "当前不可变行情、日线与因子快照", "kind": "market_snapshot", "strength": "强",
        "known_at": quote.get("quote_time"), "url": quote.get("source_url"),
        "snapshot_id": stock.get("snapshot_id"), "provider": quote.get("source_key"), "quote_time": quote.get("quote_time"),
        "note": f"{quote.get('source_key')} 行情 · 250+ 前复权日线 · {features.get('feature_version')} 因子",
    }
    financial_source = {
        "id": "financial_snapshot", "document_id": f"financial_{stock.get('snapshot_id')}_{stock['ticker']}",
        "title": "东方财富 F10 主要财务指标快照", "kind": "primary", "strength": "中",
        "known_at": latest.get("notice_date"), "url": None,
        "snapshot_id": stock.get("snapshot_id"), "provider": latest.get("source_key") or "financial_metrics_snapshot",
        "note": f"{len(stock.get('financials') or [])} 个报告期 · 原始行哈希已进入不可变快照",
    }
    sources = [market_source, financial_source]
    price = float(quote.get("price") or 0)
    ma200 = float(features.get("ma200") or 0)
    trend_text = "站上" if ma200 and price >= ma200 else "低于"
    position_plan = _baseline_position_plan(stock)
    source_contract = {
        "execution": ["market_snapshot", "financial_snapshot"],
        "financials": ["financial_snapshot"],
        "valuation": ["market_snapshot", "financial_snapshot"],
        "stress_test": ["market_snapshot"],
        "falsification": ["market_snapshot", "financial_snapshot"],
        "watchlist": ["market_snapshot", "financial_snapshot"],
    }
    action_stance = "模型观察 · 等待公司级深度研究"
    latest_revenue_yoy = _round_or_none(latest.get("revenue_yoy"), 1)
    latest_profit_yoy = _round_or_none(latest.get("net_profit_yoy"), 1)
    payload = {
        "report_version": "quant-research-baseline-v1.0",
        "research_profile_hash": research_profile_hash(stock["ticker"]),
        "research_logic_hash": research_logic_hash(),
        "generated_from": {
            "snapshot_id": stock.get("snapshot_id"), "publication_id": stock.get("publication_id"),
            "model_version": stock.get("model_version"),
        },
        "ticker": stock["ticker"], "name": stock["name"], "exchange": stock["exchange"], "industry": stock["industry"],
        "data_mode": stock["data_mode"], "as_of": stock.get("snapshot_as_of") or stock.get("data_as_of"),
        "known_at": quote.get("quote_time"), "data_status": "verified",
        "research_status": "baseline", "research_depth": "quantitative_baseline",
        "depth_disclosure": "已验证行情、日线、财务与组合结论；公司经营链路、行业份额、治理和正式估值仍待深度研究。",
        "portfolio_context": {"market_regime": stock.get("market_regime"), "cash_weight": stock.get("cash_weight"), "weights": stock.get("portfolio_weights") or {}},
        "title": f"{stock['name']}：量化基本面基线与模型观察",
        "executive": {
            "stance": action_stance, "score": _round_or_none(float(features.get('composite_score') or 0) / 10, 1),
            "target_weight": None, "model_observation_weight": stock["target_weight"],
            "current_executable_weight": None, "max_target_weight": None,
            "weight_semantics": "model_observation_only", "current_price": quote.get("price"), "action": "research_only",
            "execution_range": "不提供执行区间；待公司级深度研究。", "summary": "当前只形成可回放的量化观察，不形成交易动作。",
            "key_contradiction": f"量化综合分 {_round_or_none(features.get('composite_score'), 1)}/100，但公司级经营与行业证据尚未完成；该权重只能用于研究排序，不能执行。",
            "position_plan": position_plan,
        },
        "market": _market_view(stock),
        "thesis": [
            {"title": "财务快照", "body": f"最新披露营收同比 {latest_revenue_yoy}%，归母净利润同比 {latest_profit_yoy}%。", "claim_type": "fact", "source_ids": ["financial_snapshot"]},
            {"title": "趋势与风险", "body": f"当前价 {trend_text} 200 日均线，60 日收益 {_round_or_none(features.get('return_60d'), 1)}%，60 日年化波动率 {_round_or_none(features.get('volatility_60d'), 1)}%。", "claim_type": "fact", "source_ids": ["market_snapshot"]},
            {"title": "观察用途", "body": f"模型观察权重为 {stock['target_weight']}%，只用于研究排序；在公司级经营、行业、治理与估值证据完成前，不形成交易动作。", "claim_type": "inference", "source_ids": ["market_snapshot", "financial_snapshot"]},
        ],
        "business_model": {
            "description": "本版不使用未经验证的公司叙事。公司业务分部、价值链与收入驱动将在深度研究层补齐；当前只展示可以回放的市场和财务基线。",
            "segments": [],
            "value_chain": [
                {"layer": "公司", "items": "收入结构、客户与资本配置待补", "question": "利润增长来自销量、价格、成本还是会计口径"},
                {"layer": "行业", "items": "份额、供需与竞争格局待补", "question": "公司相对同行的领先是否扩大且可持续"},
                {"layer": "估值", "items": "盈利预测和历史分位待补", "question": "当前价格隐含的增长能否由现金流兑现"},
            ],
            "source_ids": ["financial_snapshot"],
        },
        "industry_position": {
            "headline": "当前可验证的是市场定价与财务表现；行业份额和竞争排序尚未进入证据包。",
            "metrics": [
                {"label": "总市值", "value": f"{_round_or_none(quote.get('market_cap_yi'), 0)}亿", "note": "行情快照"},
                {"label": "PE(TTM)", "value": f"{_round_or_none(quote.get('pe_ttm'), 1)}x", "note": "行情快照"},
                {"label": "PB", "value": f"{_round_or_none(quote.get('pb'), 2)}x", "note": "行情快照"},
                {"label": "综合分", "value": f"{_round_or_none(features.get('composite_score'), 1)}", "note": "量化基线 /100"},
            ],
            "source_ids": ["market_snapshot", "financial_snapshot"],
        },
        "moat": [],
        "quant_signals": [
            {"name": "财务质量线索", "score": _round_or_none(float(features.get('quality_score') or 0) / 10, 1), "proof": "由 ROE、增长和资产负债率计算；尚不能替代护城河研究。", "source_ids": ["financial_snapshot"]},
            {"name": "估值约束线索", "score": _round_or_none(float(features.get('value_score') or 0) / 10, 1), "proof": "由当前 PE 与 PB 计算；尚未做同行和历史分位校准。", "source_ids": ["market_snapshot"]},
            {"name": "趋势确认线索", "score": _round_or_none(float(features.get('trend_score') or 0) / 10, 1), "proof": "由多周期收益和均线位置计算。", "source_ids": ["market_snapshot"]},
            {"name": "风险韧性线索", "score": _round_or_none(float(features.get('resilience_score') or 0) / 10, 1), "proof": "由波动、回撤和负债率计算。", "source_ids": ["market_snapshot", "financial_snapshot"]},
        ],
        "management": {
            "score": 0, "strengths": ["本版未把管理层定性判断写成已验证结论。"],
            "watchouts": ["需补充治理结构、激励机制、资本配置记录和关联交易审查。"],
            "source_ids": ["financial_snapshot"],
        },
        "financials": financials,
        "serenity": _baseline_serenity(stock),
        "valuation": _baseline_valuation(stock),
        "stress_test": _baseline_stress_test(stock),
        "catalysts": [
            {"date": "下一份正式财报", "title": "盈利质量验证", "body": "核验收入、利润、ROE、毛利率和负债率是否沿同一方向改善。", "source_ids": ["financial_snapshot"]},
            {"date": "每周", "title": "趋势确认", "body": "观察 60 日收益、波动率和 200 日均线是否支持完成条件仓位。", "source_ids": ["market_snapshot"]},
        ],
        "risks": [
            {"rank": 1, "title": "公司级证据尚未补齐", "impact": "高", "probability": "高", "trigger": "深度研究发现商业模式、治理或行业格局与量化线索相反。", "evidence": "当前证据包只含行情、日线、财务与因子。", "source_ids": ["market_snapshot", "financial_snapshot"]},
            {"rank": 2, "title": "盈利或估值恶化", "impact": "高", "probability": "中", "trigger": "利润同比转负，或估值扩张而盈利预测下修。", "evidence": stock["primary_risk"], "source_ids": ["financial_snapshot", "market_snapshot"]},
            {"rank": 3, "title": "趋势失效", "impact": "中", "probability": "中", "trigger": "价格持续低于 200 日均线，60 日收益进一步恶化。", "evidence": f"当前价{trend_text} 200 日均线。", "source_ids": ["market_snapshot"]},
        ],
        "falsification": [
            "最新正式披露出现收入与利润同步转负，且不是一次性基数因素。",
            "ROE 明显下行同时资产负债率上升，财务质量分持续恶化。",
            "价格持续低于 200 日均线，60 日收益与风险韧性分同步走弱。",
            "公司级深度研究发现当前量化分数由不可持续因素驱动。",
        ],
        "watchlist": [
            {"metric": "营收同比", "current": f"{latest_revenue_yoy}%", "threshold": "转负则重审", "frequency": "季度"},
            {"metric": "利润同比", "current": f"{latest_profit_yoy}%", "threshold": "转负则重审", "frequency": "季度"},
            {"metric": "年度 ROE", "current": f"{financials['annual_quality']['roe']}%", "threshold": "连续下行则重审", "frequency": "年度"},
            {"metric": "60 日收益", "current": f"{_round_or_none(features.get('return_60d'), 1)}%", "threshold": "低于 -15% 加强风险审查", "frequency": "周"},
            {"metric": "200 日均线", "current": f"{_round_or_none(features.get('ma200'), 2)}", "threshold": "站稳后再完成趋势仓", "frequency": "周"},
        ],
        "sources": sources,
        "source_contract": source_contract,
        "evidence_summary": {
            "claim_locator_count": 2, "document_count": 2, "independent_document_count": 0,
            "primary_count": 2, "company_release_count": 0,
            "boundary": "本版只把不可变行情/日线/因子和 F10 财务快照作为已验证证据；公司经营、行业、治理和正式估值结论一律标记为待深度研究。",
        },
    }
    return _finalize_report(payload, stock, db_path)


def _finalize_report(payload: dict[str, Any], stock: dict[str, Any], db_path: Path) -> dict[str, Any]:
    payload = attach_report_contract(payload)
    ai_artifact = _active_ai_artifact(db_path, stock["ticker"], stock["snapshot_id"], payload)
    executive = payload.get("executive") or {}
    from data_store import publication_approval_state

    approval_state = publication_approval_state(stock["publication_id"], db_path)
    payload["publication_approval"] = approval_state
    if payload.get("research_depth") == "deep":
        proposed_weight = executive.get("proposed_initial_weight")
        approval_invalidated = approval_state["effective_status"] == "invalidated"
        executive["decision_review_weight"] = proposed_weight if ai_artifact and not approval_invalidated else None
        executive["current_executable_weight"] = (
            proposed_weight
            if ai_artifact and approval_state["is_current"]
            else None
        )
        executive["publication_approval_current"] = approval_state["is_current"]
        if approval_invalidated:
            payload["decision_blockers"] = ["批准后的内容已变化；旧批准失效，建议与执行仓位均已隐藏。"]
    if ai_artifact:
        payload["narrative_provider"] = {
            "provider": ai_artifact["provider"], "model": ai_artifact["model"],
            "generated_at": ai_artifact["generated_at"], "prompt_version": ai_artifact["prompt_version"],
            "artifact_version": ai_artifact["artifact_version"], "validation": ai_artifact["validation"],
            "editorial_review": ai_artifact.get("editorial_review") or {"reviewer": None, "applied_rules": []},
            "editorial_approval": ai_artifact["editorial_approval"],
            "artifact_hash": artifact_hash(db_path, stock["ticker"], stock["snapshot_id"]),
        }
        payload["ai_narrative"] = public_ai_narrative(ai_artifact["narrative"])
    payload["report_hash"] = _report_hash(payload)
    from report_versions import latest_report_diff

    payload["update_diff"] = latest_report_diff(stock["ticker"], stock["snapshot_id"], payload, db_path)
    final_errors = validate_report_contract(payload["report_contract"], payload)
    if final_errors:
        raise ReportContractError("final report payload rejected: " + "; ".join(final_errors))
    return payload


def _claim_source_ids(value: Any) -> set[str]:
    """Collect every explicit claim-level source reference from a report tree."""
    collected: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "source_ids" and isinstance(child, list):
                collected.update(str(item) for item in child)
            else:
                collected.update(_claim_source_ids(child))
    elif isinstance(value, list):
        for child in value:
            collected.update(_claim_source_ids(child))
    return collected


def _source_coverage_failures(
    payload: dict[str, Any], evidence_set: dict[str, Any]
) -> list[str]:
    source_rows = payload.get("sources") or []
    source_ids = {str(row.get("id")) for row in source_rows if row.get("id")}
    evidence_document_ids = {str(row.get("source_key")) for row in evidence_set.get("documents") or []}
    missing_claim_sources = sorted(_claim_source_ids(payload) - source_ids)
    contract_ids = {
        str(source_id)
        for values in (payload.get("source_contract") or {}).values()
        for source_id in (values or [])
    }
    missing_contract_sources = sorted(contract_ids - source_ids)
    unfrozen_sources = sorted({
        str(row.get("document_id"))
        for row in source_rows
        if row.get("kind") != "market_snapshot"
        and str(row.get("document_id")) not in evidence_document_ids
    })
    failures = []
    if missing_claim_sources:
        failures.append(f"claim source IDs are absent from report sources: {', '.join(missing_claim_sources)}")
    if missing_contract_sources:
        failures.append(f"source contract IDs are absent from report sources: {', '.join(missing_contract_sources)}")
    if unfrozen_sources:
        failures.append(f"report sources are absent from the frozen evidence set: {', '.join(unfrozen_sources)}")
    return failures


def report_payload(ticker: str, db_path: Path = DB_PATH, *, snapshot_id: str | None = None) -> dict[str, Any] | None:
    stock = stock_payload(ticker, db_path, snapshot_id=snapshot_id)
    if stock is None:
        return None
    profile_sources = CATL_PROFILE["sources"] if stock["ticker"] == "300750.SZ" else []
    quality_ready, gate_failures = _research_gate(stock, profile_sources)
    if not quality_ready:
        return {
            "ticker": stock["ticker"],
            "name": stock["name"],
            "research_status": "unverified",
            "research_depth": "demo_structure",
            "message": "深度研报结构已就绪，但当前快照不是通过质量门的 REAL 数据，因此不展示仓位或目标价结论。",
            "available": {
                "stock": _safe_stock_status(stock),
                "missing_modules": ["REAL 快照", "通过质量门", "完整行情/因子/财务覆盖"],
                "gate_failures": gate_failures,
            },
        }
    if stock["ticker"] != "300750.SZ":
        return _baseline_report(stock, db_path)

    evidence_set = load_evidence_set(stock["ticker"], stock["snapshot_id"], db_path)
    if not evidence_set:
        return {
            "ticker": stock["ticker"], "name": stock["name"],
            "research_status": "unverified", "research_depth": "company_evidence_pending",
            "message": "真实行情与财务数据已通过，但公司原始资料尚未形成与当前快照一致的冻结证据集，因此不展示深度结论、目标价或执行仓位。",
            "available": {
                "stock": _safe_stock_status(stock),
                "missing_modules": ["当前快照的公司原始资料", "独立交叉来源", "原文内容哈希"],
                "gate_failures": ["no current integrity-passed company evidence set"],
            },
        }

    profile = deepcopy(CATL_PROFILE)
    frozen_document_ids = {str(item.get("source_key")) for item in evidence_set.get("documents") or []}
    profile["sources"] = [
        source for source in profile["sources"]
        if str(source.get("document_id")) in frozen_document_ids
    ]
    quote = stock.get("market_quote") or {}
    features = stock.get("features") or {}
    market_source = {
        "id": "market_snapshot",
        "document_id": f"snapshot_{stock.get('snapshot_id')}",
        "title": "当前不可变行情与因子快照",
        "kind": "market_snapshot",
        "strength": "强",
        "known_at": quote.get("quote_time"),
        "url": None,
        "snapshot_id": stock.get("snapshot_id"),
        "provider": quote.get("source_key"),
        "quote_time": quote.get("quote_time"),
        "note": f"snapshot {stock.get('snapshot_id')} · {quote.get('source_key')} · {features.get('feature_version')}",
    }
    sources = [market_source, *[
        {**source, "evidence_manifest_hash": evidence_set["manifest_hash"]}
        for source in profile["sources"]
    ]]
    payload = {
        "report_version": "deep-research-v1.2",
        "research_profile_hash": research_profile_hash(stock["ticker"]),
        "research_logic_hash": research_logic_hash(),
        "generated_from": {
            "snapshot_id": stock.get("snapshot_id"), "publication_id": stock.get("publication_id"),
            "model_version": stock.get("model_version"), "evidence_set_id": evidence_set["evidence_set_id"],
            "evidence_manifest_hash": evidence_set["manifest_hash"], "evidence_gate_hash": evidence_set["gate_hash"],
        },
        "ticker": stock["ticker"],
        "name": stock["name"],
        "exchange": stock["exchange"],
        "industry": stock["industry"],
        "data_mode": stock["data_mode"],
        "as_of": stock.get("snapshot_as_of") or stock.get("data_as_of"),
        "known_at": _latest_timestamp(quote.get("quote_time"), evidence_set["knowledge_cutoff"]),
        "market_known_at": quote.get("quote_time"),
        "research_known_at": evidence_set["knowledge_cutoff"],
        "research_status": profile["research_status"],
        "research_depth": profile["research_depth"],
        "portfolio_context": {
            "market_regime": stock.get("market_regime"),
            "cash_weight": stock.get("cash_weight"),
            "weights": stock.get("portfolio_weights") or {},
        },
        "title": profile["report_title"],
        "executive": {
            "stance": "谨慎看多 · 分批建仓",
            "score": 7.6,
            "target_weight": stock["target_weight"],
            "proposed_initial_weight": _position_plan(profile, stock["target_weight"])[0]["weight"],
            "decision_review_weight": None,
            "current_executable_weight": None,
            "max_target_weight": stock["target_weight"],
            "current_price": quote.get("price"),
            "action": stock["action"],
            "execution_range": stock["execution_range"],
            "summary": profile["summary"],
            "key_contradiction": profile["key_contradiction"],
            "position_plan": _position_plan(profile, stock["target_weight"]),
        },
        "market": _market_view(stock),
        "thesis": profile["thesis"],
        "business_model": profile["business_model"],
        "industry_position": profile["industry_position"],
        "moat": profile["moat"],
        "management": profile["management"],
        "financials": _financial_view(stock),
        "serenity": _serenity_score(profile),
        "valuation": _valuation_view(stock, profile),
        "catalysts": profile["catalysts"],
        "risks": profile["risks"],
        "falsification": profile["falsification"],
        "watchlist": profile["watchlist"],
        "sources": sources,
        "source_contract": {
            "execution": ["market_snapshot", "q1_financials", "annual_capacity"],
            "financials": ["annual_financials", "q1_financials"],
            "valuation": ["market_snapshot", "annual_financials", "q1_financials"],
            "falsification": ["annual_capacity", "q1_financials", "annual_risks", "market_snapshot"],
            "watchlist": ["annual_market_share", "annual_capacity", "q1_financials", "market_snapshot"],
        },
        "evidence_summary": {
            "claim_locator_count": len(sources),
            "document_count": len({source["document_id"] for source in sources}),
            "independent_document_count": len({source["document_id"] for source in sources if source["kind"] == "independent"}),
            "primary_count": sum(source["kind"] in {"primary", "market_snapshot"} for source in sources),
            "company_release_count": sum(source["kind"] == "company_release" for source in sources),
            "frozen_evidence_set_id": evidence_set["evidence_set_id"],
            "frozen_manifest_hash": evidence_set["manifest_hash"],
            "frozen_document_count": evidence_set["gate"]["document_count"],
            "boundary": "证据计数按独立文档与文档内定位点分开。公司新闻只证明公司披露或签署了什么；核心财务回到年报/季报，行业地位只使用已冻结的独立行业来源交叉验证。",
        },
    }
    source_failures = _source_coverage_failures(payload, evidence_set)
    if source_failures:
        return {
            "ticker": stock["ticker"], "name": stock["name"],
            "research_status": "unverified", "research_depth": "source_coverage_blocked",
            "message": "冻结证据集与报告引用没有完全闭合，因此不展示深度结论、目标价或执行仓位。",
            "available": {
                "stock": _safe_stock_status(stock),
                "missing_modules": ["报告引用与冻结证据集的完整映射"],
                "gate_failures": source_failures,
            },
        }
    return _finalize_report(payload, stock, db_path)
