"""Versioned, static asset-role mechanisms for Weekly theory explanations."""

from __future__ import annotations

import re
from typing import Any, Mapping

from .market_regime_weekly_source import WEEKLY_KEYS


MECHANISM_SCHEMA_VERSION = "market-regime-weekly-mechanisms-v1"


_CATALOG: dict[str, dict[str, Any]] = {
    "dxy": {"role": "美元可交易 ETF 与美元融资条件", "drivers": ["美国相对增长与实际利率", "联储政策与全球避险需求", "美元融资压力与资金回流"], "usual_consequences": ["美元走强通常收紧非美元资产的金融条件", "风险资产、黄金、加密资产与新兴市场可能承压，但美国增长驱动的美元上涨不必然压制股票"], "counter_case": "美元与风险资产可能同时上涨，例如美国增长预期改善且流动性仍充足时。"},
    "us2y": {"role": "短端政策利率预期", "drivers": ["联储路径与政策沟通", "通胀和就业数据预期", "短期流动性与现金替代需求"], "usual_consequences": ["收益率上行通常代表更紧的短端政策定价，也意味着债券价格通常承压", "收益率下行通常减轻成长资产的贴现压力，但也可能反映增长恶化"], "counter_case": "短端收益率下行可能来自衰退避险，而不是宽松带来的风险偏好。"},
    "us10y": {"role": "长期增长、通胀和期限溢价", "drivers": ["长期通胀预期", "财政供给与期限溢价", "长期增长和避险需求"], "usual_consequences": ["收益率上行提高长期资产贴现率，也意味着债券价格通常承压", "收益率下行通常支持久期资产，但避险下行可能伴随风险资产走弱"], "counter_case": "收益率和股票可以同时上行，只要增长预期上升快过贴现率压力。"},
    "us2s10s": {"role": "收益率曲线的期限结构", "drivers": ["短端政策预期与长期增长/通胀预期的相对变化", "衰退概率与期限溢价", "政策转向预期"], "usual_consequences": ["曲线变陡常表示短端压力下降或长期风险溢价上升", "曲线变平常表示政策约束或增长预期减弱"], "counter_case": "曲线变陡的原因不同，复苏式变陡和衰退式变陡对风险资产含义相反。"},
    "sp500": {"role": "美国大盘风险资产与盈利预期", "drivers": ["盈利增长与估值", "利率和流动性", "风险偏好"], "usual_consequences": ["趋势延续通常反映风险承受能力仍在", "高位反转会放大组合去风险压力"], "counter_case": "大盘上涨可能由少数权重股推动，并不代表广泛风险偏好。"},
    "nasdaq": {"role": "成长与长久期科技风险资产", "drivers": ["实际利率和贴现率", "科技盈利与资本开支", "流动性和风险偏好"], "usual_consequences": ["实际利率下行通常支持成长估值", "利率快速上行或风险收缩时波动通常更大"], "counter_case": "科技盈利上修可能抵消部分利率上行压力。"},
    "us_dividend": {"role": "美国质量/红利风格", "drivers": ["现金流与股息预期", "利率和防御需求", "价值与成长风格切换"], "usual_consequences": ["防御需求上升时红利风格可能相对占优", "长期利率上行会提高高股息资产的替代成本"], "counter_case": "红利资产也可能在全面风险偏好上升时上涨。"},
    "vix": {"role": "美国股指隐含波动与避险需求", "drivers": ["股指期权需求", "尾部风险定价", "市场去杠杆"], "usual_consequences": ["VIX上升通常对应风险资产波动和流动性压力", "VIX下降通常对应风险偏好稳定"], "counter_case": "低VIX可能是拥挤和平静，而不是低风险。"},
    "bitcoin": {"role": "BTCUSDT 可交易永续合约", "drivers": ["全球流动性与美元融资", "风险偏好和杠杆", "比特币自身供需"], "usual_consequences": ["流动性收紧和美元走强通常压制高贝塔加密资产", "风险偏好恢复时反弹弹性通常较高"], "counter_case": "加密资产也可能受自身供需驱动而脱离传统风险资产。"},
    "ethereum": {"role": "ETHUSDT 可交易永续合约", "drivers": ["全球流动性与美元融资", "风险偏好和杠杆", "以太坊网络与生态供需"], "usual_consequences": ["风险偏好上升时 ETH 通常具有较高弹性", "美元走强或杠杆收缩时高贝塔加密资产通常承压"], "counter_case": "以太坊自身升级、链上活动或资金结构可能令其阶段性脱离 BTC。"},
    "hype": {"role": "Hyperliquid HYPE 可交易永续合约", "drivers": ["加密市场流动性与杠杆", "Hyperliquid 生态活动与代币供需", "风险偏好和交易拥挤度"], "usual_consequences": ["高贝塔永续合约在风险偏好收缩时回撤通常更快", "生态增长和流动性回流可能带来超额弹性"], "counter_case": "单一生态或代币事件可能主导 HYPE，不能简单等同于 BTC 或 ETH。"},
    "shanghai": {"role": "中国大盘与国内增长预期", "drivers": ["国内增长、政策和盈利", "人民币与外部金融条件", "国内风险偏好"], "usual_consequences": ["政策预期改善通常支持风险偏好", "外部美元收紧可能通过汇率和流动性形成约束"], "counter_case": "国内政策和估值修复可能抵消外部美元压力。"},
    "star50": {"role": "中国科技成长风格", "drivers": ["科技盈利与政策", "国内流动性", "成长估值和风险偏好"], "usual_consequences": ["流动性改善通常有利于成长风格", "实际利率和风险偏好恶化会放大估值压力"], "counter_case": "产业政策或盈利上修可能使科技成长独立走强。"},
    "china_dividend": {"role": "中国高股息与防御风格", "drivers": ["股息与现金流", "国内利率", "防御需求和风格轮动"], "usual_consequences": ["增长不确定性上升时防御风格可能相对占优", "利率上行或风险偏好全面恢复时相对优势可能减弱"], "counter_case": "红利风格也可能在风险偏好改善时与大盘同步上涨。"},
    "nikkei": {"role": "日本权益与全球周期/日元因素", "drivers": ["日本盈利和全球周期", "日元汇率", "日本政策与外资流"], "usual_consequences": ["全球风险偏好改善通常支持日本权益", "日元快速升值可能压制出口盈利"], "counter_case": "国内改革或盈利改善可抵消全球风险收缩。"},
    "kospi": {"role": "韩国周期与科技出口权益", "drivers": ["半导体周期和出口", "全球制造业需求", "美元/韩元与外资流"], "usual_consequences": ["全球周期改善通常支持KOSPI", "美元走强和出口预期恶化会增加压力"], "counter_case": "芯片供需改善可能令韩国权益强于全球风险资产。"},
    "wti": {"role": "全球增长、供给约束与通胀输入", "drivers": ["全球需求与库存", "供给扰动和地缘政治", "美元与金融条件"], "usual_consequences": ["供给冲击推高油价会增加通胀和成本压力", "需求驱动上涨可能同时反映全球增长改善"], "counter_case": "油价上涨的供给冲击和需求复苏对风险资产含义不同。"},
    "gold": {"role": "真实利率、避险与储值需求", "drivers": ["实际利率和美元", "地缘政治与避险", "央行和储值需求"], "usual_consequences": ["实际利率下降或避险需求上升通常支持黄金", "美元和实际利率同时上行通常形成压力"], "counter_case": "危机初期现金需求可能造成黄金与风险资产一同下跌。"},
    "silver": {"role": "贵金属储值与工业周期的混合资产", "drivers": ["黄金和实际利率", "工业需求与制造业周期", "美元和投机风险偏好"], "usual_consequences": ["风险偏好和工业周期改善时白银弹性通常高于黄金", "流动性收缩时白银波动通常更大"], "counter_case": "避险主导时黄金上涨而白银未必同步。"},
}


def mechanism_for_asset(key: str) -> dict[str, Any]:
    if key not in WEEKLY_KEYS or key not in _CATALOG:
        raise ValueError(f"mechanism_asset_unknown:{key}")
    return {
        "schema_version": MECHANISM_SCHEMA_VERSION,
        "asset_key": key,
        "mechanism_ids": [f"mechanism:{key}:drivers", f"mechanism:{key}:transmission", f"mechanism:{key}:counter_case"],
        **_CATALOG[key],
    }


_APPROVED_SYMBOLS = frozenset({"DXY", "VIX", "WTI", "Nasdaq", "Bitcoin", "Nikkei", "KOSPI", "MACD", "EMA", "ETF", "OHLC", "S", "P"})
_QUALIFIER_TOKENS = ("通常", "一般", "往往", "可能", "常见", "若", "当", "取决于", "未必", "不一定")
_COUNTER_CASE_TOKENS = ("但", "不过", "然而", "反例", "未必", "不一定", "取决于", "区别在于", "若", "并非绝对", "不是绝对")
_FORBIDDEN_THEORY_RE = re.compile(
    r"实时|当前(?:价格|收盘|走势|市场|黄金|美元|白银|油价|指数|资产)|"
    r"当前.{0,8}(?:上涨|下跌|走强|走弱|位于|收于|高于|低于|是|为)|本周|今天|眼下|正在|已经|"
    r"本报告|本期|现价|收盘|最新|最近|(?<![不非是未])一定|"
    r"(?<![不非是未])必然|(?<![不非是未])必定|(?<![不非是未])肯定|"
    r"(?<![不非是未])必将|毫无例外|预测准确率|保证收益"
)

_NUMERIC_ASSET_LABELS = {
    "us2y": ("2Y", "2 年期", "2年期"),
    "us10y": ("10Y", "10 年期", "10年期"),
    "us2s10s": ("2s10s", "2S10S", "2年10年", "2年期10年期"),
    "sp500": ("标普 500", "标普500", "S&P 500", "S&P500"),
    "star50": ("科创 50", "科创50"),
    "nikkei": ("日经 225", "日经225", "Nikkei 225"),
}


def _validate_theory_text(text: str, *, asset_key: str | None = None) -> None:
    words = re.findall(r"[A-Za-z]{2,}", text)
    if any(word not in _APPROVED_SYMBOLS for word in words):
        raise ValueError("theory_language_not_chinese")
    if _FORBIDDEN_THEORY_RE.search(text):
        raise ValueError("theory_current_or_certain_claim")
    numeric_free = text
    for label in sorted(_NUMERIC_ASSET_LABELS.get(asset_key or "", ()), key=len, reverse=True):
        numeric_free = numeric_free.replace(label, "")
    numeric_free = re.sub(r"2s10s|10Y|2Y", "", numeric_free, flags=re.IGNORECASE)
    if re.search(r"\d|%|％", numeric_free):
        raise ValueError("theory_numeric_observation")
    if not any(token in text for token in _QUALIFIER_TOKENS):
        raise ValueError("theory_qualifier_missing")
    if not any(token in text for token in _COUNTER_CASE_TOKENS):
        raise ValueError("theory_counter_case_missing")


def validate_theoretical_statement(output: Mapping[str, Any], allowed_mechanism_ids: set[str]) -> dict[str, Any]:
    if not isinstance(output, Mapping) or not isinstance(output.get("text"), str) or not output["text"].strip():
        raise ValueError("theory_statement_invalid")
    if output.get("claim_type") != "theoretical_mechanism":
        raise ValueError("theory_claim_type_invalid")
    mechanism_id = next(iter(allowed_mechanism_ids), "")
    asset_key = mechanism_id.split(":")[1] if mechanism_id.startswith("mechanism:") and ":" in mechanism_id else None
    _validate_theory_text(output["text"], asset_key=asset_key)
    evidence_ids = output.get("evidence_ids")
    if not isinstance(evidence_ids, list) or not evidence_ids:
        raise ValueError("mechanism_evidence_required")
    if not any(item in allowed_mechanism_ids for item in evidence_ids):
        raise ValueError("mechanism_evidence_required")
    if any(item not in allowed_mechanism_ids for item in evidence_ids):
        raise ValueError("theory_evidence_unknown")
    return {"text": output["text"], "evidence_ids": list(evidence_ids), "claim_type": output["claim_type"]}
