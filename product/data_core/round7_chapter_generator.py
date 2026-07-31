"""Whole-chapter, evidence-bound Round 7 dossier generation."""
from __future__ import annotations

import hashlib
import html
import json
import re
from dataclasses import asdict
from enum import Enum
from pathlib import Path
from copy import deepcopy
from typing import Any, Mapping, Sequence

from deepseek_writer import DEFAULT_MODEL, call_structured_deepseek
from report_contract import (
    RESEARCH_SECTION_SPECS_V3,
    UNREVIEWED_JUDGMENT_STATUS,
    build_research_section_contract_v3,
)

from .decision_policy import DecisionInput, decide
from .e4_page_level_filing_facts import FilingNumericFact
from .e4_vertical_degradation import _candidate
from .evidence_gate import (
    EvidenceGatePolicy,
    EvidenceRequirement,
    build_evidence_set,
)
from .research_degradation import assess_any_ticker
from .round7_evidence import NUMBER, canonical_hash


GENERATOR_VERSION = "round7-whole-chapter-generator-v8"
PROMPT_VERSION = "round7-whole-chapter-prompt-v3"
VALIDATOR_VERSION = "round7-whole-chapter-validator-v8"
SEMANTIC_AUDITOR_VERSION = "round7-semantic-auditor-v2"
DOSSIER_SCHEMA_VERSION = "round7-generated-dossier-v8"
REVIEW_QUEUE_SCHEMA_VERSION = "round7-chapter-review-queue-v1"
KNOWN_AT = "2026-07-31T00:00:00Z"
BLOCK_KINDS = {"fact", "judgment", "gap", "label"}
JUDGMENT_MARKERS = ("可能", "意味着", "取决于", "仍需", "判断", "表明", "如果", "若")
SELF_REPORT_MARKERS = ("公司自述", "公司在年报中自述", "年报自述")
JUDGMENT_ALLOWED_PREFIXES = (
    "这一",
    "该",
    "上述",
    "公司",
    "公司自述",
    "年报自述",
    "若",
    "如果",
    "现有证据",
    "当前证据",
    "基于",
    "收入",
    "成本",
    "业务",
    "治理",
    "技术",
    "研发",
    "专利",
    "现金",
    "海外",
    "重大",
    "市场",
    "风险",
    "动力电池",
    "储能",
    "营业",
    "货币资金",
    "客户",
    "供应链",
    "产品",
)
INVESTMENT_EXECUTION_TERMS = (
    "目标价",
    "仓位",
    "持仓",
    "敞口",
    "买入",
    "卖出",
    "增持",
    "减持",
    "加仓",
    "减仓",
    "建仓",
    "清仓",
    "做多",
    "做空",
    "增配",
    "减配",
    "止损",
    "止盈",
    "投资评级",
    "投资者",
    "投入更多本金",
    "多放些钱",
    "更大本金参与",
    "扩大敞口",
    "增加本金",
    "推荐",
    "值得",
    "应当",
    "适宜",
    "下注",
    "押注",
    "投入资金",
    "资金权重",
    "上涨",
    "下跌",
)
INVESTMENT_ACTION_CONTEXT = re.compile(
    r"(?:提高|降低|增加|减少|重点|建议|推荐|适宜|考虑).{0,10}配置|"
    r"配置.{0,10}(?:比例|仓位|敞口|该公司)"
)
JUDGMENT_RELATIONS = (
    "意味着",
    "表明",
    "取决于",
    "可能",
    "仍需",
    "判断",
    "证伪",
    "失效",
)
SECTION_RESEARCH_OUTCOMES = {
    "one_line_positioning": (
        "需求",
        "收入",
        "盈利",
        "现金",
        "回报",
        "业务边界",
        "增长",
        "持续性",
    ),
    "identity_founder_and_governance": (
        "治理",
        "控制",
        "授权",
        "继任",
        "决策",
        "关联",
        "风险",
    ),
    "technology_origin_and_development_history": (
        "研发",
        "技术",
        "产品",
        "效率",
        "商业化",
        "迭代",
        "产能",
        "竞争",
    ),
    "business_model_and_business_lines": (
        "客户",
        "订单",
        "需求",
        "收入",
        "盈利",
        "回款",
        "成本",
        "交付",
        "业务",
        "依赖",
    ),
    "financial_and_operating_time_series": (),
    "moat_evidence_chain": (
        "护城河",
        "竞争",
        "研发",
        "技术",
        "客户",
        "成本",
        "效率",
        "份额",
        "持续性",
        "证伪",
    ),
    "risks_counter_thesis_and_triggers": (
        "风险",
        "收入",
        "成本",
        "利润",
        "现金",
        "需求",
        "价格",
        "份额",
        "供应",
        "延期",
        "竞争",
        "价格",
        "份额",
        "技术",
        "客户",
        "订单",
        "产能",
        "回款",
        "商业化",
        "恶化",
    ),
    "research_conclusion_and_open_questions": (
        "结论",
        "收入",
        "成本",
        "利润",
        "现金",
        "增长",
        "持续性",
        "风险",
        "回报",
        "证据",
    ),
}
FORBIDDEN_ACTIONS = (
    "目标价",
    "仓位",
    "买入",
    "卖出",
    "加仓",
    "减仓",
    "止损",
    "执行建议",
)
ACTION_INTENT = (
    re.compile(
        r"(?:建议|应当|适合|值得|可以).{0,16}"
        r"(?:配置|持有|参与|买入|卖出|增持|减持|加仓|减仓|回避|观望)"
    ),
    re.compile(
        r"(?:配置|持有|仓位).{0,12}"
        r"(?:比例|提高|降低|增加|减少|上调|下调)"
    ),
)
CONDITIONAL = re.compile(r"(?:如果|若).{0,220}?(?:那么|则)([^。！？；]*)")
EVIDENCE_BOUNDARY_TEXT = (
    "证据边界：本章只使用公司官方披露中的页级证据；"
    "公司竞争力或市场地位描述按公司自述处理，未引入二手行业材料。"
)

ROUND7_LAYOUTS: dict[str, dict[str, Any]] = {
    "one_line_positioning": {
        "mode": "paragraphs",
        "minimum_rows": 1,
        "maximum_rows": 1,
        "columns": (
            {"id": "positioning", "title": "事实定位", "kinds": ("fact",)},
            {
                "id": "research_judgment",
                "title": "研究判断",
                "kinds": ("judgment",),
            },
        ),
    },
    "identity_founder_and_governance": {
        "mode": "table",
        "minimum_rows": 3,
        "maximum_rows": 5,
        "columns": (
            {"id": "topic", "title": "主题", "kinds": ("label",)},
            {
                "id": "finding",
                "title": "已核验事实",
                "kinds": ("fact", "judgment", "gap"),
            },
        ),
        "source_title": "来源",
    },
    "technology_origin_and_development_history": {
        "mode": "table",
        "minimum_rows": 3,
        "maximum_rows": 6,
        "columns": (
            {"id": "date", "title": "日期", "kinds": ("fact",)},
            {"id": "event", "title": "已核验事件", "kinds": ("fact",)},
            {
                "id": "research_implication",
                "title": "研究含义（明确标注）",
                "kinds": ("judgment",),
            },
        ),
        "source_title": "来源",
    },
    "business_model_and_business_lines": {
        "mode": "table",
        "minimum_rows": 3,
        "maximum_rows": 6,
        "columns": (
            {
                "id": "business_line",
                "title": "业务线/平台",
                "kinds": ("label",),
            },
            {
                "id": "customer_and_delivery",
                "title": "客户与交付物",
                "kinds": ("fact", "gap"),
            },
            {
                "id": "revenue_or_operating_evidence",
                "title": "收入或经营证据",
                "kinds": ("fact", "gap"),
            },
            {
                "id": "key_dependency",
                "title": "关键依赖",
                "kinds": ("judgment",),
            },
        ),
        "source_title": "来源",
    },
    "financial_and_operating_time_series": {
        "mode": "table",
        "minimum_rows": 5,
        "maximum_rows": 10,
        "columns": (
            {"id": "period", "title": "期间", "kinds": ("fact",)},
            {"id": "metric", "title": "指标", "kinds": ("label",)},
            {
                "id": "value_and_unit",
                "title": "数值/单位",
                "kinds": ("fact",),
            },
            {
                "id": "comparison",
                "title": "同比/环比",
                "kinds": ("fact",),
            },
            {
                "id": "scope",
                "title": "口径",
                "kinds": ("fact",),
            },
        ),
        "source_title": "来源",
    },
    "moat_evidence_chain": {
        "mode": "table",
        "minimum_rows": 3,
        "maximum_rows": 5,
        "columns": (
            {"id": "hypothesis", "title": "假设", "kinds": ("judgment",)},
            {
                "id": "supporting_evidence",
                "title": "支持证据",
                "kinds": ("fact",),
            },
            {
                "id": "falsifier",
                "title": "可证伪条件",
                "kinds": ("judgment",),
            },
            {
                "id": "current_view",
                "title": "当前判断",
                "kinds": ("judgment",),
            },
        ),
    },
    "risks_counter_thesis_and_triggers": {
        "mode": "table",
        "minimum_rows": 3,
        "maximum_rows": 6,
        "columns": (
            {
                "id": "risk_or_counter_thesis",
                "title": "风险/反题材",
                "kinds": ("label",),
            },
            {"id": "known_fact", "title": "已知事实", "kinds": ("fact",)},
            {
                "id": "trigger",
                "title": "触发器",
                "kinds": ("judgment",),
            },
            {
                "id": "next_verification",
                "title": "下一次核验",
                "kinds": ("gap",),
            },
        ),
        "source_title": "来源",
    },
    "research_conclusion_and_open_questions": {
        "mode": "bullets",
        "minimum_rows": 1,
        "maximum_rows": 1,
        "columns": (
            {
                "id": "fact_conclusion",
                "title": "事实结论",
                "kinds": ("fact",),
            },
            {
                "id": "research_judgment",
                "title": "研究判断",
                "kinds": ("judgment",),
            },
            {
                "id": "open_questions",
                "title": "待补问题",
                "kinds": ("gap",),
            },
        ),
    },
}

SECTION_WRITING_INSTRUCTIONS = {
    "one_line_positioning": (
        "事实定位只选择一条能够界定收入来源和业务边界的证据。研究判断只能"
        "指出必须验证的收入质量、现金回报或持续性，不得从网点、工厂或产品"
        "存在推导未来需求增长。"
    ),
    "identity_founder_and_governance": (
        "分别覆盖身份边界、关键管理者和治理观察。证券代码若没有页级 evidence"
        " 必须写 gap，不得从 issuer 字段搬入事实。治理判断只能从已披露任职或"
        "控制关系提出授权、继任、关联决策等待验证问题。"
    ),
    "technology_origin_and_development_history": (
        "按披露期次排列技术或产品事件；研究含义必须写成待验证机制，不得把"
        "公司自述的领先地位当作独立事实。"
    ),
    "business_model_and_business_lines": (
        "按动力电池、储能、电池材料/回收或材料实际支持的业务线组织。客户、"
        "交付物或分部数字取不到时写 gap；关键依赖只连接到已披露的订单、需求、"
        "回款、成本或交付机制。"
    ),
    "financial_and_operating_time_series": (
        "只选择 financial evidence；一行一个期次和指标，逐字使用确定性代码"
        "提供的数值、单位、方向与幅度，不写原因归因。"
    ),
    "moat_evidence_chain": (
        "每行是一条待验证护城河假设；支持证据仍按公司自述标记；可证伪条件"
        "必须包含“证伪”，当前判断必须说明相对同行或经济价值尚待验证。"
    ),
    "risks_counter_thesis_and_triggers": (
        "每行以公司披露风险为已知事实，触发器必须是可观察变化，下一次核验"
        "必须指向正式披露；不得预测股价或给出投资动作。"
    ),
    "research_conclusion_and_open_questions": (
        "事实结论只综合已披露事实；研究判断只说明当前证据能与不能支持什么；"
        "待补问题必须是真正阻断结论的公司特异证据。"
    ),
}


SYSTEM_PROMPT = """你是机构股票研究员。你要一次写完 request 指定的一整章，并且只返回一个合法 JSON 对象。

硬规则：
1. 只能使用 request.evidence 和 request.prior_chapter_context；不得调用外部知识或训练记忆补事实。
2. 输出 section_id 必须逐字等于 request.section_id。rows 必须一次覆盖整章，并逐行逐列遵守 request.layout；不是字段摘要，也不得新增或漏掉列。
3. 每个 cell 的 kind 必须属于对应 layout column 的 allowed_kinds。事实、研究判断和待补问题必须显式分开；label 仅可用于不含数字的短标签。
4. fact/judgment 必须引用 evidence_ids。gap/label 不得引用证据。supporting_quotes 会由确定性代码按 evidence_id 回填。
5. 标为 self_report 的证据只能写成公司自述。凡引用 request.output_constraints.self_report_evidence_ids，cell.text 必须逐字包含“公司自述”或“年报自述”；不得直接断言为独立事实。
6. 只能使用证据提供的 allowed_numeric_displays。comparison.required_phrase 已由确定性代码计算；使用该财务数字时必须逐字写出方向和幅度，模型不得自行计算。
7. 已披露实际值只能作为历史陈述或未来条件的基线，不得出现在“如果/若…那么/则…”的结论中。
8. judgment 必须明确使用“可能、意味着、取决于、仍需、判断、表明、如果、若”等推断措辞。
9. 不得输出目标价、仓位、买卖、止损或执行动作。
10. 行数和字符数必须落在 request.output_constraints 内；证据不足写成具体 gap，不得用空泛文字凑数。
11. 每个 cell 引用的 kind=financial 证据不得超过 request.output_constraints.maximum_financial_evidence_ids_per_cell；引用多个指标时仍须分别写清方向和幅度。
12. supporting_quotes 会由确定性代码按 evidence_id 回填，模型不得借此扩展事实。
13. 不要输出 Markdown，不要增加 schema 外字段。
14. “可证伪条件”列必须逐字出现“证伪”；“触发器”必须是可观察变化；“下一次核验”必须写明待核验的正式披露。
15. 财务时间序列一行只引用一个 financial evidence_id；期间、指标、数值、比较和口径五个 cell 必须引用同一个 evidence_id，不得把不同期次或指标拼在一行。
16. judgment 必须以 request.output_constraints.allowed_judgment_prefixes 之一开头，且不得出现 request.output_constraints.investment_execution_terms 中的任何词。
17. judgment 必须用 request.output_constraints.judgment_relations 中的关系词连接证据与研究变量；关系词之后必须出现 request.output_constraints.research_outcomes 中的研究对象。只能讨论经营变量、验证条件和风险机制，不得讨论投资者、资金投入、上涨押注或配置动作。这是 Tier B/no_action 的闭集关系语法。

JSON schema：
{
  "section_id": "string",
  "rows": [
    {
      "cells": [
        {
          "column_id": "必须等于 request.layout.columns 中对应列 id",
          "kind": "fact|judgment|gap|label",
          "text": "该单元格的完整中文内容",
          "evidence_ids": ["N-..."],
          "supporting_quotes": []
        }
      ]
    }
  ]
}"""

SEMANTIC_AUDIT_SYSTEM_PROMPT = """你是股票研究事实与安全审计器。只返回合法 JSON，不改写正文。

你只能比较 request.chapter 与 request.evidence，不得用外部知识。逐个 cell 审计：
1. fact 必须只是对应 evidence 的逐字事实或确定性财务投影，不得扩大主体、范围、因果或时间。
2. judgment 可以基于 evidence 提出新的研究机制、条件、证伪变量和待验证假设；这些本来就不要求在 evidence 中逐字出现。只要使用“可能、意味着、取决于、仍需、如果、若”等认识边界，就不要因为来源没有写“仍需验证”或没有写未来条件而判 fail。只有把 evidence 没有的事情写成已经发生的事实、确定因果或确定预测，或引用与判断完全无关的 evidence，才判 fail。
3. 不得出现目标价、仓位、配置比例、买卖、增减持、止损、评级或任何投资执行意图；Tier B/no_action 下也不得使用同义改写。
4. 公司核心竞争力、市场地位等自述必须显式称为公司自述，不能当作独立事实。
5. 已披露实际值和已计算的比较方向不得放进条件句结论，不得否定或反转。
6. gap 必须描述当前材料没有提供什么；缺口本来就不会出现在 evidence，不得仅以“来源没有提到该缺口”为由判 fail。只有 gap 暗藏已发生的新事实才判 fail。

严格输出：
{
  "verdict": "pass|fail",
  "findings": [
    {"cell_path": "row[0].cell[1]", "rule": "unsupported_claim|irrelevant_evidence|investment_action|self_report|historical_as_forecast|comparison_direction|gap_masquerade", "reason": "具体原因"}
  ]
}
pass 时 findings 必须为空；任何不确定性按 fail。"""


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode()
    ).hexdigest()


def _plain(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def build_chapter_request(
    *,
    spec: Any,
    issuer: Mapping[str, Any],
    evidence: Sequence[Mapping[str, Any]],
    prior_chapter_context: Sequence[Mapping[str, Any]] = (),
    validation_feedback: Sequence[str] = (),
) -> dict[str, Any]:
    layout = ROUND7_LAYOUTS[spec.section_id]
    model_evidence = []
    for item in evidence:
        projected = {
            "evidence_id": item["evidence_id"],
            "kind": item["kind"],
            "self_report": bool(item.get("self_report")),
            "allowed_numeric_displays": list(
                item.get("allowed_numeric_displays", [])
            ),
        }
        if item.get("kind") == "narrative":
            projected.update(
                {
                    "text": (
                        "公司自述：" + str(item["text"])
                        if item.get("self_report")
                        else item["text"]
                    ),
                    "section_path": item.get("section_path"),
                    "source_character": (
                        "issuer_self_report"
                        if item.get("self_report")
                        else "issuer_disclosed_narrative"
                    ),
                }
            )
        else:
            projected.update(
                {
                    "metric": item.get("metric"),
                    "period": item.get("period"),
                    "display": item.get("display"),
                    "unit": item.get("unit"),
                    "comparison": item.get("comparison"),
                    "quoted_anchor": item.get("citation", {}).get(
                        "quoted_anchor"
                    ),
                }
            )
        model_evidence.append(projected)
    minimum_rows = layout["minimum_rows"]
    minimum_characters = spec.target_characters[0]
    if spec.section_id == "financial_and_operating_time_series":
        available_financial_rows = sum(1 for item in evidence if item.get("kind") == "financial")
        # A sparse official filing must remain visibly partial rather than
        # inventing rows.  Keep the canonical columns, but require only the
        # number of independently available financial rows (at least one).
        minimum_rows = 1 if available_financial_rows < minimum_rows else minimum_rows
        if available_financial_rows < layout["minimum_rows"]:
            minimum_characters = max(60, min(minimum_characters, available_financial_rows * 40))
    request = {
        "task": "write_one_complete_round7_chapter",
        "section_id": spec.section_id,
        "section_title": spec.title,
        "section_purpose": spec.purpose,
        "section_writing_instruction": SECTION_WRITING_INSTRUCTIONS[
            spec.section_id
        ],
        "issuer": dict(issuer),
        "target_characters": list(spec.target_characters),
        "layout": {
            "mode": layout["mode"],
            "minimum_rows": minimum_rows,
            "maximum_rows": layout["maximum_rows"],
            "columns": [
                {
                    "id": column["id"],
                    "title": column["title"],
                    "allowed_kinds": list(column["kinds"]),
                }
                for column in layout["columns"]
            ],
        },
        "evidence": model_evidence,
        "prior_chapter_context": [dict(item) for item in prior_chapter_context],
        "output_constraints": {
            "minimum_rows": minimum_rows,
            "maximum_rows": layout["maximum_rows"],
            "minimum_characters": minimum_characters,
            "maximum_characters": spec.target_characters[1],
            "self_report_evidence_ids": [
                item["evidence_id"] for item in evidence if item.get("self_report")
            ],
            "evidence_boundary_characters": len(EVIDENCE_BOUNDARY_TEXT),
            "maximum_financial_evidence_ids_per_cell": (
                3
                if spec.section_id
                == "research_conclusion_and_open_questions"
                else 1
            ),
            "allowed_judgment_prefixes": list(JUDGMENT_ALLOWED_PREFIXES),
            "investment_execution_terms": list(INVESTMENT_EXECUTION_TERMS),
            "judgment_relations": list(JUDGMENT_RELATIONS),
            "research_outcomes": list(
                SECTION_RESEARCH_OUTCOMES[spec.section_id]
            ),
        },
        "validation_feedback": list(validation_feedback),
        "generator_version": GENERATOR_VERSION,
        "prompt_version": PROMPT_VERSION,
    }
    request["input_hash"] = _hash(request)
    return request


def _quote_map(block: Mapping[str, Any]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for item in block.get("supporting_quotes") or []:
        if isinstance(item, Mapping):
            result.setdefault(str(item.get("evidence_id") or ""), []).append(
                str(item.get("quote") or "")
            )
    return result


FINANCIAL_METRIC_LABELS = {
    "revenue": "营业总收入",
    "operating_cost": "营业成本",
    "operating_profit": "营业利润",
    "net_profit_parent": "归属于母公司股东的净利润",
    "operating_cash_flow": "经营活动产生的现金流量净额",
    "cash": "货币资金",
    "current_assets": "流动资产",
    "total_assets": "资产总额",
    "total_liabilities": "负债总额",
    "capital_expenditure": "资本性支出",
}


def _period_display(period: object) -> str:
    raw = str(period or "")
    match = re.fullmatch(r"(\d{4})Q([1-4])", raw)
    if match:
        quarter = {"1": "第一季度", "2": "第二季度", "3": "第三季度", "4": "第四季度"}[
            match.group(2)
        ]
        return f"{match.group(1)}年{quarter}"
    match = re.fullmatch(r"(\d{4})FY", raw)
    if match:
        return f"{match.group(1)}年"
    match = re.fullmatch(r"(\d{4})H([12])", raw)
    if match:
        half = "半年度" if match.group(2) == "1" else "年度"
        return f"{match.group(1)}年{half}"
    return raw


def _financial_statement(evidence: Mapping[str, Any]) -> str:
    metric = FINANCIAL_METRIC_LABELS.get(
        str(evidence.get("metric") or ""),
        str(evidence.get("metric") or ""),
    )
    comparison = evidence.get("comparison") or {}
    direction = str(comparison.get("required_phrase") or "无可用同期对比值")
    return (
        f"{_period_display(evidence.get('period'))}，公司{metric}为"
        f"{evidence.get('display')}{evidence.get('unit')}，{direction}。"
    )


def _exact_fact_text(
    evidence_ids: Sequence[str],
    registry: Mapping[str, Mapping[str, Any]],
) -> str:
    parts = []
    for evidence_id in evidence_ids:
        evidence = registry[evidence_id]
        if evidence.get("kind") == "financial":
            text = _financial_statement(evidence)
        else:
            text = str(evidence.get("text") or "").strip()
            if text and not text.endswith(("。", "；", "！", "？")):
                text += "。"
            if evidence.get("self_report") and not any(
                marker in text for marker in SELF_REPORT_MARKERS
            ):
                text = "公司自述：" + text
        if text and text not in parts:
            parts.append(text)
    return "".join(parts)


def _normalize_supporting_quotes(
    response: Mapping[str, Any],
    registry: Mapping[str, Mapping[str, Any]],
    request: Mapping[str, Any],
) -> dict[str, Any]:
    normalized = deepcopy(dict(response))
    rows = normalized.get("rows")
    if not isinstance(rows, list):
        return normalized
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("cells"), list):
            continue
        if request["section_id"] == "moat_evidence_chain":
            support_ids = next(
                (
                    list(cell.get("evidence_ids") or [])
                    for cell in row["cells"]
                    if isinstance(cell, Mapping)
                    and cell.get("column_id") == "supporting_evidence"
                    and cell.get("evidence_ids")
                ),
                [],
            )
            if support_ids:
                for cell in row["cells"]:
                    if (
                        isinstance(cell, dict)
                        and cell.get("kind") == "judgment"
                        and not cell.get("evidence_ids")
                    ):
                        cell["evidence_ids"] = list(support_ids)
        if request["section_id"] == "risks_counter_thesis_and_triggers":
            known_ids = next(
                (
                    list(cell.get("evidence_ids") or [])
                    for cell in row["cells"]
                    if isinstance(cell, Mapping)
                    and cell.get("column_id") == "known_fact"
                    and cell.get("evidence_ids")
                ),
                [],
            )
            for cell in row["cells"]:
                if not isinstance(cell, dict):
                    continue
                if cell.get("column_id") == "trigger" and known_ids:
                    cell["evidence_ids"] = list(known_ids)
                if cell.get("column_id") == "next_verification":
                    cell["text"] = re.sub(
                        r"(?<!\d)(?:19|20)\d{2}年", "", str(cell.get("text") or "")
                    )
                    cell["text"] = re.sub(
                        r"(?<![A-Za-z0-9])\d+(?:\.\d+)?%?", "", cell["text"]
                    )
        if request["section_id"] == "financial_and_operating_time_series":
            available_financial_ids = [
                str(item["evidence_id"])
                for item in request.get("evidence", [])
                if item.get("kind") == "financial" and item.get("evidence_id") in registry
            ]
            row_index = rows.index(row)
            financial_ids = (
                [available_financial_ids[row_index % len(available_financial_ids)]]
                if available_financial_ids
                else []
            )
            if financial_ids:
                evidence_id = financial_ids[0]
                evidence = registry[evidence_id]
                cell_values = {
                    "period": _period_display(evidence.get("period")),
                    "metric": FINANCIAL_METRIC_LABELS.get(
                        str(evidence.get("metric") or ""),
                        str(evidence.get("metric") or ""),
                    ),
                    "value_and_unit": (
                        f"{evidence.get('display')}{evidence.get('unit')}"
                    ),
                    "comparison": str(
                        (evidence.get("comparison") or {}).get(
                            "required_phrase"
                        )
                        or "无可用同期对比值"
                    ),
                    "scope": "合并报表",
                }
                for cell in row["cells"]:
                    if not isinstance(cell, dict):
                        continue
                    cell["text"] = cell_values.get(
                        str(cell.get("column_id") or ""),
                        str(cell.get("text") or ""),
                    )
                    if cell.get("kind") != "label":
                        cell["evidence_ids"] = [evidence_id]
                    else:
                        cell["evidence_ids"] = []
        for cell in row["cells"]:
            if not isinstance(cell, dict) or not isinstance(
                cell.get("evidence_ids"),
                list,
            ):
                continue
            cell["supporting_quotes"] = [
                {
                    "evidence_id": evidence_id,
                    "quote": str(
                        registry.get(evidence_id, {}).get("text")
                        or registry.get(evidence_id, {})
                        .get("citation", {})
                        .get("quoted_anchor")
                        or ""
                    ),
                }
                for evidence_id in cell["evidence_ids"]
                if evidence_id in registry
            ]
            cell["source_character"] = (
                "issuer_self_report"
                if any(
                    registry.get(evidence_id, {}).get("self_report")
                    for evidence_id in cell["evidence_ids"]
                )
                else "page_bound_official_evidence"
            )
            if (
                cell.get("kind") == "judgment"
                and cell["source_character"] == "issuer_self_report"
                and not any(
                    marker in str(cell.get("text") or "")
                    for marker in SELF_REPORT_MARKERS
                )
            ):
                cell["text"] = (
                    "公司自述基础上的研究判断："
                    + str(cell.get("text") or "")
                )
            if (
                cell.get("kind") == "fact"
                and cell["evidence_ids"]
                and request["section_id"]
                != "financial_and_operating_time_series"
            ):
                if (
                    request["section_id"]
                    == "technology_origin_and_development_history"
                    and cell.get("column_id") == "date"
                ):
                    first = registry[cell["evidence_ids"][0]]
                    cell["text"] = _period_display(first.get("report_period"))
                else:
                    cell["text"] = _exact_fact_text(
                        cell["evidence_ids"],
                        registry,
                    )
    return normalized


def _allowed_numbers(
    evidence_ids: Sequence[str],
    registry: Mapping[str, Mapping[str, Any]],
) -> set[str]:
    return {
        str(token)
        for evidence_id in evidence_ids
        for token in registry[evidence_id].get("allowed_numeric_displays", [])
    }


def validate_chapter(
    response: Mapping[str, Any],
    *,
    request: Mapping[str, Any],
    registry: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    problems: list[str] = []
    if response.get("section_id") != request["section_id"]:
        problems.append("section_id mismatch")
    if set(response).difference({"section_id", "rows"}):
        problems.append("chapter fields do not match schema")
    rows = response.get("rows")
    if not isinstance(rows, list):
        return problems + ["rows must be an array"]
    constraints = request["output_constraints"]
    layout_columns = request["layout"]["columns"]
    if not constraints["minimum_rows"] <= len(rows) <= constraints["maximum_rows"]:
        problems.append("row count outside requested range")
    kinds: list[str] = []
    character_count = 0
    known = {str(item["evidence_id"]) for item in request["evidence"]}
    for row_index, row in enumerate(rows):
        row_prefix = f"row[{row_index}]"
        if not isinstance(row, Mapping) or set(row) != {"cells"}:
            problems.append(row_prefix + " fields do not match schema")
            continue
        cells = row.get("cells")
        if not isinstance(cells, list):
            problems.append(row_prefix + ".cells must be an array")
            continue
        if len(cells) != len(layout_columns):
            problems.append(row_prefix + " does not match the Round 7 column count")
            continue
        row_financial_ids: set[str] = set()
        for cell_index, (cell, column) in enumerate(zip(cells, layout_columns)):
            prefix = f"{row_prefix}.cell[{cell_index}]"
            if not isinstance(cell, Mapping):
                problems.append(prefix + " is not an object")
                continue
            allowed_fields = {
                "column_id",
                "kind",
                "text",
                "evidence_ids",
                "supporting_quotes",
                "source_character",
            }
            if set(cell).difference(allowed_fields) or not {
                "column_id",
                "kind",
                "text",
                "evidence_ids",
                "supporting_quotes",
            }.issubset(cell):
                problems.append(prefix + " fields do not match schema")
            if cell.get("column_id") != column["id"]:
                problems.append(prefix + " has wrong column_id")
            kind = str(cell.get("kind") or "")
            text = str(cell.get("text") or "").strip()
            evidence_ids = cell.get("evidence_ids")
            supporting_quotes = cell.get("supporting_quotes")
            kinds.append(kind)
            character_count += len(text)
            if kind not in BLOCK_KINDS or kind not in column["allowed_kinds"]:
                problems.append(prefix + " has invalid kind for column")
            sparse_financial = (
                request["section_id"] == "financial_and_operating_time_series"
                and int(constraints.get("minimum_rows", 5)) < 5
            )
            minimum_cell_characters = 1 if sparse_financial and kind != "label" else (2 if kind == "label" else 4)
            if len(text) < minimum_cell_characters:
                problems.append(prefix + " is too short")
            if any(term in text for term in FORBIDDEN_ACTIONS):
                problems.append(prefix + " contains a blocked action field")
            if any(pattern.search(text) for pattern in ACTION_INTENT):
                problems.append(prefix + " contains investment-action intent")
            if not isinstance(evidence_ids, list) or any(
                not isinstance(item, str) for item in evidence_ids
            ):
                problems.append(prefix + " evidence_ids must be strings")
                continue
            if len(evidence_ids) != len(set(evidence_ids)):
                problems.append(prefix + " repeats an evidence ID")
            unknown = sorted(set(evidence_ids).difference(known))
            if unknown:
                problems.append(
                    prefix + " cites unknown evidence: " + ",".join(unknown)
                )
                continue
            if kind in {"fact", "judgment"} and not evidence_ids:
                problems.append(prefix + " has no evidence")
            if kind in {"gap", "label"} and evidence_ids:
                problems.append(prefix + f" {kind} must not cite evidence")
            if kind == "label" and NUMBER.search(text):
                problems.append(prefix + " label contains an unbound number")
            financial_ids = [
                evidence_id
                for evidence_id in evidence_ids
                if registry[evidence_id].get("kind") == "financial"
            ]
            row_financial_ids.update(financial_ids)
            if len(financial_ids) > int(
                constraints["maximum_financial_evidence_ids_per_cell"]
            ):
                problems.append(prefix + " cites too many financial rows")
            if not isinstance(supporting_quotes, list):
                problems.append(prefix + " supporting_quotes must be an array")
                continue
            quote_map = _quote_map(cell)
            for evidence_id in evidence_ids:
                evidence = registry[evidence_id]
                source_text = str(
                    evidence.get("text")
                    or evidence.get("citation", {}).get("quoted_anchor")
                    or ""
                )
                quotes = quote_map.get(evidence_id, [])
                if not quotes:
                    problems.append(prefix + f" lacks quote for {evidence_id}")
                for quote in quotes:
                    if len("".join(quote.split())) < 8 or quote not in source_text:
                        problems.append(
                            prefix + f" has non-verbatim quote for {evidence_id}"
                        )
                if evidence.get("self_report"):
                    if cell.get("source_character") != "issuer_self_report":
                        problems.append(
                            prefix
                            + f" cites self-report {evidence_id} without issuer_self_report label"
                        )
                    if (
                        not (
                            request["section_id"]
                            == "technology_origin_and_development_history"
                            and cell.get("column_id") == "date"
                        )
                        and not any(
                            marker in text for marker in SELF_REPORT_MARKERS
                        )
                    ):
                        problems.append(
                            prefix
                            + f" cites self-report {evidence_id} without explicit company-self-report wording"
                        )
            numeric_tokens = NUMBER.findall(text)
            allowed = (
                _allowed_numbers(evidence_ids, registry) if evidence_ids else set()
            )
            for token in numeric_tokens:
                if token not in allowed:
                    problems.append(prefix + f" contains unprovided number {token}")
            for evidence_id in evidence_ids:
                evidence = registry[evidence_id]
                comparison = evidence.get("comparison")
                if (
                    comparison
                    and request["section_id"]
                    != "financial_and_operating_time_series"
                    and any(
                        token in text
                        for token in evidence.get("allowed_numeric_displays", [])
                    )
                    and comparison["required_phrase"] not in text
                ):
                    problems.append(
                        prefix
                        + f" omits comparison direction for {evidence_id}"
                    )
                if comparison and comparison["required_phrase"] in text:
                    phrase = re.escape(comparison["required_phrase"])
                    if re.search(
                        rf"(?:并非|不是|未|没有|不属于).{{0,4}}{phrase}",
                        text,
                    ):
                        problems.append(
                            prefix
                            + f" negates the disclosed comparison for {evidence_id}"
                        )
                    opposite = (
                        "下滑"
                        if comparison.get("direction") == "增长"
                        else "增长"
                        if comparison.get("direction") == "下滑"
                        else None
                    )
                    if opposite and re.search(
                        rf"(?:同比|较期初).{{0,2}}{opposite}",
                        text,
                    ):
                        problems.append(
                            prefix
                            + f" reverses the disclosed comparison for {evidence_id}"
                        )
            for consequent in CONDITIONAL.findall(text):
                disclosed = {
                    value
                    for item in (
                        registry[evidence_id] for evidence_id in evidence_ids
                    )
                    if item.get("kind") == "financial"
                    for value in (
                        str(item.get("display") or ""),
                        str((item.get("comparison") or {}).get("prior_display") or ""),
                        str((item.get("comparison") or {}).get("magnitude") or ""),
                        str((item.get("comparison") or {}).get("required_phrase") or ""),
                    )
                    if value
                }
                if any(value and value in consequent for value in disclosed):
                    problems.append(
                        prefix
                        + " puts a disclosed actual in a conditional consequent"
                    )
            if kind == "judgment" and not any(
                marker in text for marker in JUDGMENT_MARKERS
            ):
                problems.append(prefix + " judgment lacks inference language")
            if kind == "judgment" and not text.startswith(
                tuple(constraints["allowed_judgment_prefixes"])
            ):
                problems.append(
                    prefix + " judgment is outside the closed Tier-B grammar"
                )
            if kind == "judgment" and (
                any(
                    term in text
                    for term in constraints["investment_execution_terms"]
                )
                or (
                    INVESTMENT_ACTION_CONTEXT.search(text)
                    and not any(
                        phrase in text
                        for phrase in ("资本配置", "资源配置", "产能配置")
                    )
                )
            ):
                problems.append(
                    prefix
                    + " judgment contains a forbidden investment-execution term"
                )
            if kind == "judgment":
                relation_matches = [
                    (text.find(relation), relation)
                    for relation in constraints["judgment_relations"]
                    if relation in text
                ]
                if not relation_matches:
                    problems.append(
                        prefix
                        + " judgment lacks a closed-grammar research relation"
                    )
                else:
                    position, relation = min(relation_matches)
                    consequent = text[position + len(relation) :]
                    if not any(
                        outcome in consequent
                        for outcome in constraints["research_outcomes"]
                    ):
                        problems.append(
                            prefix
                            + " judgment relation does not resolve to an allowed "
                            "research outcome"
                        )
            if (
                kind == "fact"
                and evidence_ids
                and request["section_id"]
                != "financial_and_operating_time_series"
            ):
                expected_fact = (
                    _period_display(registry[evidence_ids[0]].get("report_period"))
                    if request["section_id"]
                    == "technology_origin_and_development_history"
                    and cell.get("column_id") == "date"
                    else _exact_fact_text(evidence_ids, registry)
                )
                if text != expected_fact:
                    problems.append(
                        prefix
                        + " fact text is not the deterministic page-bound text"
                    )
        if (
            request["section_id"] == "financial_and_operating_time_series"
            and len(row_financial_ids) != 1
        ):
            problems.append(
                row_prefix + " must bind exactly one financial evidence row"
            )
        elif (
            request["section_id"] == "financial_and_operating_time_series"
            and len(row_financial_ids) == 1
        ):
            evidence = registry[next(iter(row_financial_ids))]
            expected_cells = {
                "period": _period_display(evidence.get("period")),
                "metric": FINANCIAL_METRIC_LABELS.get(
                    str(evidence.get("metric") or ""),
                    str(evidence.get("metric") or ""),
                ),
                "value_and_unit": (
                    f"{evidence.get('display')}{evidence.get('unit')}"
                ),
                "comparison": str(
                    (evidence.get("comparison") or {}).get("required_phrase")
                    or "无可用同期对比值"
                ),
                "scope": "合并报表",
            }
            for cell in cells:
                if (
                    isinstance(cell, Mapping)
                    and str(cell.get("text") or "").strip()
                    != expected_cells.get(str(cell.get("column_id") or ""))
                ):
                    problems.append(
                        row_prefix
                        + " financial cells are not deterministic evidence projections"
                    )
                    break
            comparison_cell = next(
                (
                    cell
                    for cell in cells
                    if isinstance(cell, Mapping)
                    and cell.get("column_id") == "comparison"
                ),
                None,
            )
            required_phrase = str(
                (evidence.get("comparison") or {}).get("required_phrase")
                or "无可用同期对比值"
            )
            if (
                not isinstance(comparison_cell, Mapping)
                or comparison_cell.get("text") != required_phrase
            ):
                problems.append(
                    row_prefix
                    + " financial comparison is not the deterministic direction"
                )
    if "fact" not in kinds:
        problems.append("chapter lacks an explicit fact block")
    if (
        request["section_id"] != "financial_and_operating_time_series"
        and "judgment" not in kinds
    ):
        problems.append("chapter lacks an explicit judgment block")
    if (
        request["section_id"]
        in {
            "risks_counter_thesis_and_triggers",
            "research_conclusion_and_open_questions",
        }
        and "gap" not in kinds
    ):
        problems.append("chapter lacks an explicit evidence gap")
    safety_minimum = (int(constraints["minimum_characters"]) * 3 + 4) // 5
    safety_maximum = (
        int(constraints["maximum_characters"]) * 3
        if request["section_id"] == "moat_evidence_chain"
        else int(constraints["maximum_characters"]) * 2
        if request["section_id"] == "risks_counter_thesis_and_triggers"
        else (int(constraints["maximum_characters"]) * 8) // 5
    )
    if not safety_minimum <= character_count <= safety_maximum:
        problems.append(
            f"chapter character count {character_count} outside safety range "
            f"{safety_minimum}-{safety_maximum} "
            f"(target {constraints['minimum_characters']}-{constraints['maximum_characters']})"
        )
    all_text = " ".join(
        str(cell.get("text") or "")
        for row in rows
        if isinstance(row, Mapping)
        for cell in row.get("cells", [])
        if isinstance(cell, Mapping)
    )
    if (
        request["section_id"] == "moat_evidence_chain"
        and "证伪" not in all_text
    ):
        problems.append("chapter lacks an explicit falsifier")
    if (
        request["section_id"] == "risks_counter_thesis_and_triggers"
        and not any(
            marker in all_text
            for marker in (
                "若",
                "一旦",
                "连续",
                "低于",
                "高于",
                "下降",
                "上升",
                "恶化",
                "延期",
            )
        )
    ):
        problems.append("chapter lacks an observable trigger")
    return list(dict.fromkeys(problems))


def audit_chapter_semantics(
    response: Mapping[str, Any],
    *,
    request: Mapping[str, Any],
    registry: Mapping[str, Mapping[str, Any]],
    key_file: Path,
    transport: Any = None,
) -> tuple[list[str], dict[str, Any]]:
    used_ids = list(
        dict.fromkeys(
            evidence_id
            for row in response.get("rows", [])
            if isinstance(row, Mapping)
            for cell in row.get("cells", [])
            if isinstance(cell, Mapping)
            for evidence_id in cell.get("evidence_ids", [])
            if evidence_id in registry
        )
    )
    audit_request = {
        "task": "audit_one_complete_round7_chapter",
        "section_id": request["section_id"],
        "issuer": request["issuer"],
        "tier_policy": {
            "tier": "B",
            "decision": "no_action",
            "blocked_fields": [
                "target_price",
                "position_range",
                "action",
            ],
        },
        "chapter": response,
        "evidence": [
            {
                "evidence_id": evidence_id,
                "kind": registry[evidence_id].get("kind"),
                "self_report": bool(registry[evidence_id].get("self_report")),
                "text": (
                    registry[evidence_id].get("text")
                    or registry[evidence_id]
                    .get("citation", {})
                    .get("quoted_anchor")
                ),
                "financial_projection": (
                    {
                        "metric": registry[evidence_id].get("metric"),
                        "period": registry[evidence_id].get("period"),
                        "display": registry[evidence_id].get("display"),
                        "unit": registry[evidence_id].get("unit"),
                        "comparison": registry[evidence_id].get("comparison"),
                    }
                    if registry[evidence_id].get("kind") == "financial"
                    else None
                ),
            }
            for evidence_id in used_ids
        ],
        "auditor_version": SEMANTIC_AUDITOR_VERSION,
    }
    audit_request["input_hash"] = _hash(audit_request)
    raw_audit, provider = call_structured_deepseek(
        system_prompt=SEMANTIC_AUDIT_SYSTEM_PROMPT,
        request_object=audit_request,
        key_file=key_file,
        model=DEFAULT_MODEL,
        max_tokens=1200,
        temperature=0.0,
        thinking_type="disabled",
        transport=transport,
    )
    problems: list[str] = []
    if not isinstance(raw_audit, Mapping) or set(raw_audit) != {
        "verdict",
        "findings",
    }:
        problems.append("semantic audit response does not match schema")
        findings: list[Any] = []
    else:
        findings = raw_audit.get("findings")
        if raw_audit.get("verdict") not in {"pass", "fail"}:
            problems.append("semantic audit verdict is invalid")
        if not isinstance(findings, list):
            problems.append("semantic audit findings must be an array")
            findings = []
        for index, finding in enumerate(findings):
            if (
                not isinstance(finding, Mapping)
                or set(finding) != {"cell_path", "rule", "reason"}
                or not all(
                    isinstance(finding.get(key), str)
                    and finding[key].strip()
                    for key in ("cell_path", "rule", "reason")
                )
            ):
                problems.append(
                    f"semantic audit finding[{index}] does not match schema"
                )
                continue
            problems.append(
                "semantic audit "
                + finding["cell_path"]
                + " "
                + finding["rule"]
                + ": "
                + finding["reason"]
            )
        if raw_audit.get("verdict") == "pass" and findings:
            problems.append("semantic audit pass has findings")
        if raw_audit.get("verdict") == "fail" and not findings:
            problems.append("semantic audit fail has no findings")
    receipt = {
        **provider,
        "role": "semantic_auditor",
        "section_id": request["section_id"],
        "input_hash": audit_request["input_hash"],
        "response_hash": _hash(raw_audit),
        "verdict": (
            raw_audit.get("verdict")
            if isinstance(raw_audit, Mapping)
            else "invalid"
        ),
        "auditor_version": SEMANTIC_AUDITOR_VERSION,
        "problems": problems,
        "audited_chapter_hash": _hash(response),
    }
    return list(dict.fromkeys(problems)), receipt


def generate_chapter(
    *,
    spec: Any,
    issuer: Mapping[str, Any],
    evidence: Sequence[Mapping[str, Any]],
    registry: Mapping[str, Mapping[str, Any]],
    key_file: Path,
    prior_chapter_context: Sequence[Mapping[str, Any]] = (),
    max_attempts: int = 20,
    transport: Any = None,
    semantic_transport: Any = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    feedback: list[str] = []
    receipts: list[dict[str, Any]] = []
    for attempt in range(1, max_attempts + 1):
        request = build_chapter_request(
            spec=spec,
            issuer=issuer,
            evidence=evidence,
            prior_chapter_context=prior_chapter_context,
            validation_feedback=feedback,
        )
        # The conclusion chapter is intentionally compact: its prompt carries
        # prior chapter context, so a smaller completion budget avoids provider
        # truncation while preserving the same whole-chapter contract.
        completion_budget = (
            1800
            if spec.section_id == "research_conclusion_and_open_questions"
            else 7000
        )
        try:
            raw_response, provider = call_structured_deepseek(
            system_prompt=SYSTEM_PROMPT,
            request_object=request,
            key_file=key_file,
            model=DEFAULT_MODEL,
            max_tokens=completion_budget,
            temperature=0.1,
            thinking_type="disabled",
                transport=transport,
            )
        except Exception as exc:
            feedback = [f"provider transport failure: {type(exc).__name__}: {exc}"]
            continue
        try:
            response = _normalize_supporting_quotes(raw_response, registry, request)
            problems = validate_chapter(response, request=request, registry=registry)
        except (KeyError, TypeError, ValueError) as exc:
            # Treat malformed model evidence references as a normal rejected
            # attempt so the bounded regeneration loop can repair them.
            response = {
                "section_id": spec.section_id,
                "rows": [],
            }
            problems = [f"malformed model response: {type(exc).__name__}: {exc}"]
        semantic_receipt = None
        if not problems:
            semantic_problems, semantic_receipt = audit_chapter_semantics(
                response,
                request=request,
                registry=registry,
                key_file=key_file,
                transport=(
                    semantic_transport
                    if semantic_transport is not None
                    else transport
                ),
            )
            problems.extend(semantic_problems)
        call_receipt = {
            **provider,
            "role": "chapter_generator",
            "section_id": spec.section_id,
            "attempt": attempt,
            "input_hash": request["input_hash"],
            "provider_response_hash": _hash(raw_response),
            "normalized_response_hash": _hash(response),
            "accepted": not problems,
            "validation_problems": problems,
            "prompt_version": PROMPT_VERSION,
            "validator_version": VALIDATOR_VERSION,
            "semantic_audit": semantic_receipt,
        }
        receipts.append(call_receipt)
        if not problems:
            character_count = sum(
                len(cell["text"])
                for row in response["rows"]
                for cell in row["cells"]
            )
            blocks = [
                cell
                for row in response["rows"]
                for cell in row["cells"]
                if cell["kind"] != "label"
            ]
            return {
                "section_id": spec.section_id,
                "title": spec.title,
                "status": UNREVIEWED_JUDGMENT_STATUS,
                "review_status": "pending_human_review",
                "input_hash": request["input_hash"],
                "model_request_id": provider.get("request_id"),
                "character_count": character_count,
                "length_status": (
                    "within_target"
                    if spec.target_characters[0]
                    <= character_count
                    <= spec.target_characters[1]
                    else (
                        "below_target_due_to_evidence_and_validation_constraints"
                        if character_count < spec.target_characters[0]
                        else "above_target_due_to_chapter_synthesis"
                    )
                ),
                "rows": response["rows"],
                "blocks": blocks,
                "evidence_ids": list(
                    dict.fromkeys(
                        evidence_id
                        for block in blocks
                        for evidence_id in block["evidence_ids"]
                    )
                ),
                "content_hash": _hash(response),
            }, receipts
        feedback = problems
    raise RuntimeError(
        f"{spec.section_id} whole-chapter output failed validation after "
        f"{max_attempts} model calls: {feedback}"
    )


def _chapter_plain_text(chapter: Mapping[str, Any]) -> str:
    labels = {
        "fact": "事实",
        "judgment": "研究判断（未审阅）",
        "gap": "待补问题",
    }
    return "\n".join(
        f"{labels[item['kind']]}：{item['text']}" for item in chapter["blocks"]
    )


def _bindings(
    chapter: Mapping[str, Any],
    registry: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "evidence_id": evidence_id,
            **dict(registry[evidence_id]["citation"]),
        }
        for evidence_id in chapter["evidence_ids"]
    ]


def _source_manifest(
    chapters: Sequence[Mapping[str, Any]],
    registry: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    documents: dict[str, dict[str, Any]] = {}
    for chapter in chapters:
        for evidence_id in chapter["evidence_ids"]:
            evidence = registry[evidence_id]
            citation = evidence["citation"]
            document_id = str(citation["document_id"])
            documents.setdefault(
                document_id,
                {
                    "document_id": document_id,
                    "raw_hash": citation["raw_hash"],
                    "source_url": citation["source_url"],
                    "pages_used": [],
                },
            )
            documents[document_id]["pages_used"].append(citation["page_number"])
    for item in documents.values():
        item["pages_used"] = sorted(set(item["pages_used"]))
    return sorted(documents.values(), key=lambda item: item["document_id"])


def _section_inputs(
    *,
    issuer: Mapping[str, Any],
    chapters: Sequence[Mapping[str, Any]],
    evidence_by_section: Mapping[str, Sequence[Mapping[str, Any]]],
    registry: Mapping[str, Mapping[str, Any]],
    run_receipt: Mapping[str, Any],
    source_manifest: Sequence[Mapping[str, Any]],
    decision_receipt: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    chapter_by_id = {item["section_id"]: item for item in chapters}

    def draft(section_id: str) -> dict[str, Any]:
        chapter = chapter_by_id[section_id]
        return {
            "status": UNREVIEWED_JUDGMENT_STATUS,
            "review_status": "pending_human_review",
            "text": _chapter_plain_text(chapter),
            "evidence_bindings": _bindings(chapter, registry),
            "provider_request_id": chapter["model_request_id"],
        }

    def rows(section_id: str, *, kind: str | None = None) -> list[dict[str, Any]]:
        values = [
            dict(item)
            for item in evidence_by_section[section_id]
            if kind is None or item.get("kind") == kind
        ]
        return values or [dict(evidence_by_section[section_id][0])]

    risk_rows = rows("risks_counter_thesis_and_triggers")
    return {
        "one_line_positioning": {
            "issuer_identity": dict(issuer),
            "positioning_evidence": rows("one_line_positioning"),
            "chapter_draft": draft("one_line_positioning"),
        },
        "identity_founder_and_governance": {
            "issuer_identity": dict(issuer),
            "management_evidence": rows("identity_founder_and_governance"),
            "governance_evidence": rows("identity_founder_and_governance"),
            "chapter_draft": draft("identity_founder_and_governance"),
        },
        "technology_origin_and_development_history": {
            "timeline_evidence": rows("technology_origin_and_development_history"),
            "chapter_draft": draft("technology_origin_and_development_history"),
        },
        "business_model_and_business_lines": {
            "business_evidence": rows("business_model_and_business_lines"),
            "operating_evidence": rows("business_model_and_business_lines"),
            "chapter_draft": draft("business_model_and_business_lines"),
        },
        "financial_and_operating_time_series": {
            "financial_evidence": rows(
                "financial_and_operating_time_series",
                kind="financial",
            ),
            "operating_evidence": rows("financial_and_operating_time_series"),
            "chapter_draft": draft("financial_and_operating_time_series"),
        },
        "moat_evidence_chain": {
            "moat_evidence": rows("moat_evidence_chain"),
            "falsification_evidence": risk_rows,
            "chapter_draft": draft("moat_evidence_chain"),
        },
        "risks_counter_thesis_and_triggers": {
            "risk_evidence": risk_rows,
            "trigger_evidence": rows("risks_counter_thesis_and_triggers"),
            "chapter_draft": draft("risks_counter_thesis_and_triggers"),
        },
        "research_conclusion_and_open_questions": {
            "synthesis_evidence": [
                dict(registry[evidence_id])
                for evidence_id in dict.fromkeys(
                    evidence_id
                    for chapter in chapters
                    if chapter["section_id"] != "research_conclusion_and_open_questions"
                    for evidence_id in chapter["evidence_ids"]
                )
            ],
            "decision_policy_output": dict(decision_receipt),
            "chapter_draft": draft("research_conclusion_and_open_questions"),
        },
        "production_record": {
            "run_receipt": dict(run_receipt),
            "source_manifest": [dict(item) for item in source_manifest],
        },
    }


def compile_dossier(
    *,
    ticker: str,
    issuer: Mapping[str, Any],
    chapters: Sequence[Mapping[str, Any]],
    evidence_by_section: Mapping[str, Sequence[Mapping[str, Any]]],
    registry: Mapping[str, Mapping[str, Any]],
    page_facts: Sequence[Mapping[str, Any]],
    provider_receipts: Sequence[Mapping[str, Any]],
    source_receipts: Mapping[str, Any],
) -> dict[str, Any]:
    if [item["section_id"] for item in chapters] != [
        item.section_id for item in RESEARCH_SECTION_SPECS_V3[:-1]
    ]:
        raise ValueError("generated chapters do not match exact Round 7 order")
    materialized = tuple(FilingNumericFact(**item) for item in page_facts)
    for item in materialized:
        item.validate()
    evidence_set = build_evidence_set(
        ticker=ticker,
        candidates=(_candidate(ticker, materialized, known_at=KNOWN_AT),),
        policy=EvidenceGatePolicy(
            as_of=KNOWN_AT,
            requirements=(EvidenceRequirement("filings", min_primary=1),),
        ),
    )
    decision = decide(
        DecisionInput(
            ticker=ticker,
            context_manifest_hash=evidence_set.manifest_hash,
            dossier_id=f"round7:{ticker}",
            current_price=None,
            target_price=None,
            quality_score=None,
            risk_score=None,
            liquidity_score=None,
            coverage_passed=False,
            sector_exposure=0,
            current_position=0,
            cash_weight=1,
        )
    )
    active_provider_receipts: list[Mapping[str, Any]] = []
    for chapter in chapters:
        section_receipts = [
            item
            for item in provider_receipts
            if item.get("section_id") == chapter["section_id"]
        ]
        accepted_index = next(
            (
                index
                for index in range(len(section_receipts) - 1, -1, -1)
                if section_receipts[index].get("accepted")
                and section_receipts[index].get("request_id")
                == chapter["model_request_id"]
            ),
            None,
        )
        if accepted_index is None:
            raise ValueError(
                f"{chapter['section_id']} has no accepted provider receipt "
                "for its final model request"
            )
        start = accepted_index
        while start > 0 and not section_receipts[start - 1].get("accepted"):
            start -= 1
        active_provider_receipts.extend(section_receipts[start : accepted_index + 1])
    accepted_ids = [
        item.get("request_id")
        for item in active_provider_receipts
        if item.get("accepted")
    ]
    if len(accepted_ids) != len(chapters) or len(set(accepted_ids)) != len(chapters):
        raise ValueError("final dossier must bind exactly one accepted call per model chapter")
    source_manifest = _source_manifest(chapters, registry)
    run_receipt = {
        "run_id": "round7-run:" + _hash(
            {
                "ticker": ticker,
                "provider_requests": [
                    item.get("request_id")
                    for item in active_provider_receipts
                    if item.get("accepted")
                ],
                "semantic_audit_requests": [
                    (item.get("semantic_audit") or {}).get("request_id")
                    for item in active_provider_receipts
                    if item.get("accepted")
                ],
                "source_receipts": source_receipts,
            }
        )[:24],
        "generator_version": GENERATOR_VERSION,
        "prompt_version": PROMPT_VERSION,
        "validator_version": VALIDATOR_VERSION,
        "provider": "DeepSeek",
        "model": DEFAULT_MODEL,
        "accepted_model_calls": sum(
            bool(item.get("accepted")) for item in active_provider_receipts
        ),
        "all_model_calls": len(active_provider_receipts),
        "accepted_semantic_audits": sum(
            (item.get("semantic_audit") or {}).get("verdict") == "pass"
            for item in active_provider_receipts
            if item.get("accepted")
        ),
        "all_semantic_audits": sum(
            item.get("semantic_audit") is not None
            for item in active_provider_receipts
        ),
        "human_review_status": "pending_human_review",
    }
    inputs = _section_inputs(
        issuer=issuer,
        chapters=chapters,
        evidence_by_section=evidence_by_section,
        registry=registry,
        run_receipt=run_receipt,
        source_manifest=source_manifest,
        decision_receipt=asdict(decision),
    )
    contract = build_research_section_contract_v3(
        inputs,
        structure_only=False,
        evidence_set=evidence_set,
    )
    degradation = assess_any_ticker(
        ticker,
        evidence_set=evidence_set,
        section_contract=contract,
        data_kind="real",
    )
    dossier = {
        "schema_version": DOSSIER_SCHEMA_VERSION,
        "data_kind": "real",
        "ticker": ticker,
        "issuer": dict(issuer),
        "review_status": "pending_human_review",
        "unreviewed_chapter_count": len(chapters),
        "chapters": [dict(item) for item in chapters],
        "production_record": run_receipt,
        "provider_receipts": [dict(item) for item in active_provider_receipts],
        "source_receipts": dict(source_receipts),
        "source_manifest": source_manifest,
        "evidence_registry": {
            evidence_id: dict(registry[evidence_id])
            for evidence_id in dict.fromkeys(
                evidence_id
                for chapter in chapters
                for evidence_id in chapter["evidence_ids"]
            )
        },
        "section_contract": _plain(asdict(contract)),
        "degradation": _plain(asdict(degradation)),
        "decision": _plain(asdict(decision)),
        "metrics": {
            "generated_research_text_characters": sum(
                int(item["character_count"]) for item in chapters
            ),
            "chapter_body_characters": None,
            "full_file_characters": None,
            "generated_chapters": len(chapters),
            "production_record_chapters": 1,
            "source_documents": len(source_manifest),
            "page_evidence_bindings": sum(
                len(item["evidence_ids"]) for item in chapters
            ),
        },
    }
    dossier["content_hash"] = _hash(dossier)
    return dossier


def _citation_maps(
    dossier: Mapping[str, Any],
) -> tuple[dict[str, str], dict[str, str]]:
    fact_ids: dict[str, str] = {}
    source_ids: dict[str, str] = {}
    for chapter in dossier["chapters"]:
        for block in chapter["blocks"]:
            for evidence_id in block["evidence_ids"]:
                if evidence_id not in fact_ids:
                    fact_ids[evidence_id] = f"F-{len(fact_ids) + 1:02d}"
                document_id = dossier["evidence_registry"][evidence_id]["citation"][
                    "document_id"
                ]
                if document_id not in source_ids:
                    source_ids[document_id] = f"S-{len(source_ids) + 1:02d}"
    return fact_ids, source_ids


def render_markdown(dossier: Mapping[str, Any]) -> str:
    fact_ids, source_ids = _citation_maps(dossier)
    lines = [
        "---",
        f"ticker: {dossier['ticker']}",
        f"data_kind: {dossier['data_kind']}",
        f"review_status: {dossier['review_status']}",
        f"tier: {dossier['degradation']['tier']}",
        f"run_id: {dossier['production_record']['run_id']}",
        "---",
        "",
        f"# {dossier['issuer']['short_name']}公司档案",
        "",
        (
            f"> **审阅提示：含 {dossier['unreviewed_chapter_count']} 章未审阅 AI 判断。"
            "这些内容是研究草稿，不构成目标价、仓位或买卖建议。**"
        ),
        "",
    ]
    titles = {
        item.section_id: f"{item.order}. {item.title}"
        for item in RESEARCH_SECTION_SPECS_V3
    }
    labels = {
        "fact": "**事实**",
        "judgment": "**研究判断（未审阅）**",
        "gap": "**待补问题**",
        "label": "",
    }

    def citations_for(cell: Mapping[str, Any], *, sources_only: bool = False) -> str:
        citations: list[str] = []
        for evidence_id in cell["evidence_ids"]:
            citation = dossier["evidence_registry"][evidence_id]["citation"]
            if not sources_only:
                citations.append(f"[{fact_ids[evidence_id]}]")
            citations.append(f"[{source_ids[citation['document_id']]}]")
        return "".join(dict.fromkeys(citations))

    def rendered_cell(cell: Mapping[str, Any]) -> str:
        text = str(cell["text"]).replace("|", "｜")
        if cell["kind"] == "label":
            return text
        label = labels[cell["kind"]]
        if cell.get("source_character") == "issuer_self_report":
            label = (
                "**公司自述（未独立验证）**"
                if cell["kind"] == "fact"
                else "**研究判断（基于公司自述，未审阅）**"
            )
        prefix = label + "：" if cell["kind"] != "fact" or cell.get(
            "source_character"
        ) == "issuer_self_report" else ""
        suffix = citations_for(cell)
        return prefix + text + (suffix if suffix else "")

    for chapter in dossier["chapters"]:
        layout = ROUND7_LAYOUTS[chapter["section_id"]]
        lines.extend(
            (
                f"## {titles[chapter['section_id']]}",
                "",
                (
                    "> " + EVIDENCE_BOUNDARY_TEXT
                ),
                "",
            )
        )
        if layout["mode"] == "paragraphs":
            for cell in chapter["rows"][0]["cells"]:
                lines.extend((rendered_cell(cell), ""))
        elif layout["mode"] == "bullets":
            for column, cell in zip(layout["columns"], chapter["rows"][0]["cells"]):
                lines.extend(
                    (
                        f"- **{column['title']}**：{rendered_cell(cell)}",
                        "",
                    )
                )
        else:
            headers = [column["title"] for column in layout["columns"]]
            if layout.get("source_title"):
                headers.append(str(layout["source_title"]))
            lines.extend(
                (
                    "| " + " | ".join(headers) + " |",
                    "| " + " | ".join("---" for _ in headers) + " |",
                )
            )
            for row in chapter["rows"]:
                rendered = [rendered_cell(cell) for cell in row["cells"]]
                if layout.get("source_title"):
                    source_refs = "".join(
                        dict.fromkeys(
                            citations_for(cell, sources_only=True)
                            for cell in row["cells"]
                            if cell["evidence_ids"]
                        )
                    )
                    rendered.append(source_refs or "—")
                lines.append("| " + " | ".join(rendered) + " |")
            lines.append("")
    production = dossier["production_record"]
    section_counts: dict[str, int] = {}
    for item in dossier["section_contract"]["sections"]:
        status = str(item["status"])
        section_counts[status] = section_counts.get(status, 0) + 1
    lines.extend(
        (
            "## 9. 生产记录",
            "",
            "> 证据边界：本章是确定性运行元数据，不包含模型生成的研究结论。",
            "",
            "| 项目 | 记录 |",
            "| --- | --- |",
            f"| run_id | `{production['run_id']}` |",
            f"| 模型 | {production['provider']} / {production['model']} |",
            f"| 接受的整章调用 | {production['accepted_model_calls']} |",
            f"| 全部模型调用 | {production['all_model_calls']} |",
            f"| 通过的语义审计 | {production['accepted_semantic_audits']} |",
            f"| 全部语义审计 | {production['all_semantic_audits']} |",
            f"| 生成器 | `{production['generator_version']}` |",
            f"| 校验器 | `{production['validator_version']}` |",
            f"| 人工审阅 | {production['human_review_status']} |",
            f"| 章节状态 | {json.dumps(section_counts, ensure_ascii=False)} |",
            f"| Tier | {dossier['degradation']['tier']} |",
            f"| 决策 | {dossier['decision']['action']} |",
            "",
            "## Sources",
            "",
            "| ID | 发布者 | 文档/页面 | 发布或报告日期 | URL | 用途 |",
            "| --- | --- | --- | --- | --- | --- |",
        )
    )
    for source in dossier["source_manifest"]:
        source_id = source_ids.get(source["document_id"])
        if source_id is None:
            continue
        lines.append(
            "| "
            + " | ".join(
                (
                    source_id,
                    dossier["issuer"]["short_name"] + " / 官方交易所披露",
                    (
                        source["document_id"]
                        + "；页 "
                        + ", ".join(str(item) for item in source["pages_used"])
                        + "；raw_hash "
                        + source["raw_hash"]
                    ),
                    (
                        re.search(
                            r"/(\d{4}-\d{2}-\d{2})/",
                            source["source_url"],
                        ).group(1)
                        if re.search(
                            r"/(\d{4}-\d{2}-\d{2})/",
                            source["source_url"],
                        )
                        else "见官方披露"
                    ),
                    source["source_url"],
                    "本档案页级事实与判断依据",
                )
            )
            + " |"
        )
    return "\n".join(lines).rstrip() + "\n"


def render_html(markdown: str, *, title: str) -> str:
    lines = markdown.splitlines()
    out = [
        "<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>",
        f"<title>{html.escape(title)}</title>",
        "<style>body{max-width:940px;margin:40px auto;padding:0 24px;font-family:-apple-system,BlinkMacSystemFont,'PingFang SC',sans-serif;line-height:1.75;color:#172333}h1,h2{color:#0b3558}h2{margin-top:42px;border-bottom:1px solid #ccd7e0;padding-bottom:8px}blockquote{margin:16px 0;padding:12px 16px;background:#f3f7fa;border-left:4px solid #2e688f}table{border-collapse:collapse;width:100%;font-size:14px}th,td{border:1px solid #cad4dc;padding:7px;vertical-align:top}code{overflow-wrap:anywhere}p{margin:12px 0}.meta{color:#667}</style></head><body>",
    ]
    table_rows: list[list[str]] = []

    def flush_table() -> None:
        nonlocal table_rows
        if not table_rows:
            return
        rows = [
            row
            for row in table_rows
            if not all(set(cell.replace(":", "")) <= {"-"} for cell in row)
        ]
        if rows:
            out.append("<table>")
            for row_index, row in enumerate(rows):
                tag = "th" if row_index == 0 else "td"
                out.append(
                    "<tr>"
                    + "".join(
                        f"<{tag}>{html.escape(cell)}</{tag}>" for cell in row
                    )
                    + "</tr>"
                )
            out.append("</table>")
        table_rows = []

    in_frontmatter = False
    for line in lines:
        if line == "---":
            in_frontmatter = not in_frontmatter
            continue
        if in_frontmatter:
            continue
        if line.startswith("|") and line.endswith("|"):
            table_rows.append([item.strip() for item in line.strip("|").split("|")])
            continue
        flush_table()
        if not line:
            continue
        if line.startswith("# "):
            out.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.startswith("## "):
            out.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("> "):
            out.append(f"<blockquote>{html.escape(line[2:])}</blockquote>")
        else:
            escaped = html.escape(line)
            escaped = escaped.replace("**", "")
            out.append(f"<p>{escaped}</p>")
    flush_table()
    out.append("</body></html>")
    return "\n".join(out) + "\n"


def build_review_queue(dossier: Mapping[str, Any]) -> dict[str, Any]:
    impact_order = {
        "research_conclusion_and_open_questions": 1,
        "one_line_positioning": 2,
        "moat_evidence_chain": 3,
        "risks_counter_thesis_and_triggers": 4,
        "financial_and_operating_time_series": 5,
        "business_model_and_business_lines": 6,
        "technology_origin_and_development_history": 7,
        "identity_founder_and_governance": 8,
    }
    items = []
    section_status = {
        item["section_id"]: item for item in dossier["section_contract"]["sections"]
    }
    for chapter in dossier["chapters"]:
        citations = _bindings(chapter, dossier["evidence_registry"])
        items.append(
            {
                "impact_rank": impact_order[chapter["section_id"]],
                "section_id": chapter["section_id"],
                "title": chapter["title"],
                "review_status": "pending_human_review",
                "full_text": _chapter_plain_text(chapter),
                "citations": citations,
                "current_section_status": str(
                    section_status[chapter["section_id"]]["status"]
                ),
                "if_approved": "FULL"
                if not section_status[chapter["section_id"]]["missing_required"]
                else "remains PARTIAL until independent required inputs exist",
            }
        )
    items.sort(key=lambda item: item["impact_rank"])
    queue = {
        "schema_version": REVIEW_QUEUE_SCHEMA_VERSION,
        "ticker": dossier["ticker"],
        "source_run_id": dossier["production_record"]["run_id"],
        "sort_basis": "impact_on_final_research_conclusion",
        "items": items,
    }
    queue["receipt_hash"] = _hash(queue)
    return queue
