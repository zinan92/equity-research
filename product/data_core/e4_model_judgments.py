"""Receipt-bound model reasoning over official page-level issuer evidence.

The model writes every judgment sentence.  Deterministic code freezes the
input, computes explicitly allowed derived metrics, validates every sentence
and number, and maps evidence identities back to page citations.  Validation
failure can only become a typed missing item; it never invokes prose fallback.
"""
from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Iterable, Mapping

from deepseek_writer import DEFAULT_MODEL, call_structured_deepseek


JUDGMENT_STATUS = "ai_generated_judgment_unreviewed"
GENERATOR_VERSION = "e4-model-judgments-v1"
PROMPT_VERSION = "e4-model-judgments-prompt-v1"
VALIDATOR_VERSION = "e4-model-judgments-validator-v1"

_REQUIRED_CITATION = (
    "document_id",
    "raw_hash",
    "page_number",
    "quoted_anchor",
    "source_url",
    "report_period",
    "unit",
)
_NUMBER = re.compile(
    r"(?<![A-Za-z0-9])[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?(?![A-Za-z0-9])"
)
_SCIENCE = re.compile(r"[-+]?\d+(?:\.\d+)?[eE][-+]?\d+")
_SENTENCE_BREAK = re.compile(r"(?<=[。！？；])\s*|\n+")
_GENERIC_ANCHORS = (
    "公司披露",
    "主营业务",
    "主要业务",
    "核心竞争力",
    "风险因素",
    "经营情况",
    "相关情况",
    "年度报告",
    "本报告期",
    "管理层讨论",
    "未来发展",
    "研究判断",
    "需要验证",
)
_INFERENCE_MARKERS = (
    "若",
    "可能",
    "意味着",
    "表明",
    "因此",
    "取决于",
    "需要",
    "尚不能",
    "不能",
    "可作为",
    "应",
)
_UNSUPPORTED_COMPARATIVES = (
    "全球第一",
    "行业第一",
    "打败所有",
    "领先同行",
    "超过同行",
    "垄断",
    "唯一",
    "最强",
)
_TEMPORAL_COMPARATIVES = (
    "增长",
    "下降",
    "改善",
    "恶化",
    "趋势",
    "上升",
    "下滑",
)
_FUTURE_WINDOW_MARKERS = ("下一", "下次", "后续", "未来")

_TASKS: dict[str, dict[str, Any]] = {
    "investment_thesis": {
        "objective": "形成有条件的核心投资论点，说明业务事实、财务兑现和仍未验证的关键环节。",
        "requires": ("narrative", "financial"),
    },
    "moat_assessment": {
        "objective": "评估公司披露所支持的竞争优势来源，并明确自述证据不能证明的比较结论。",
        "requires": ("moat_narrative",),
    },
    "risk_register": {
        "objective": "把公司特定风险按机制、暴露和可观察后果写成风险登记。",
        "requires": ("risk_narrative",),
    },
    "falsification_tests": {
        "objective": "给出可执行的证伪测试；阈值和最新实际基线只能引用允许的财务或派生证据。",
        "requires": ("financial",),
    },
    "monitoring_kpis": {
        "objective": "选择能够验证论点的公司特定经营或财务监控指标。",
        "requires": ("narrative", "financial"),
    },
    "action_triggers": {
        "objective": "定义只触发研究重审、不产生买卖或仓位动作的观察条件。",
        "requires": ("financial",),
    },
    "accounting_checks": {
        "objective": "根据同口径页级财务事实提出可复核的会计质量检查。",
        "requires": ("financial_pair",),
    },
    "operating_kpis": {
        "objective": "从产品、技术、客户、产能、渠道或经营进展披露中提炼具体经营指标。",
        "requires": ("narrative",),
    },
    "margin_bridge": {
        "objective": "使用已提供的确定性派生值解释盈利起点，并如实保留缺少的成本层。",
        "requires": ("derived_margin",),
    },
}
_ALWAYS_MISSING: dict[str, str] = {
    "variant_view": "no page-bound market-expectations or consensus evidence in supplied receipts",
    "peer_comparison": "no page-bound peer-company facts in supplied receipts",
    "management_record": "no page-bound management track-record series in supplied receipts",
    "governance_events": "no official governance-event extraction receipt in supplied inputs",
    "macro_exposures": "no official issuer-specific macro-sensitivity evidence in supplied inputs",
    "segment_financials": "no accepted official segment-financial table in supplied inputs",
    "market_size": "no accepted official market-size evidence in supplied inputs",
}
_SYSTEM_PROMPT = """你是机构股票研究的判断生成器。只返回一个合法 JSON 对象。

硬规则：
1. 只能使用 request.evidence_registry；不得使用外部知识、行业常识或训练记忆补事实。
2. 每个可用判断的 text 由若干完整中文句子组成；claims 必须与 text 逐句、逐字、顺序一致。
3. 每个判断 claim 的 claim_type 必须是 inference，不得用 fact。supporting_quotes 必须逐字摘自对应页级证据，句子必须显式使用条件或推断措辞，不得把比较、领先、排名或因果判断伪装成事实。
4. 每个句子必须包含引用证据中的具体产品、技术、客户、渠道、业务机制、金额、比率或时间。公司名和“主营业务”“核心竞争力”等栏目词本身不算具体内容。
5. 任何阿拉伯数字必须逐字复制自该字段引用证据的 allowed_numeric_displays。即使 quoted_anchor 中还有其他数字，只要不在 allowed_numeric_displays 就禁止使用。不得改写精度、添加“.0”、去掉千分位、换算单位、估算或使用科学计数法；输出前逐个核对数字 token。
6. D 类证据是调用前由确定性代码计算的派生值，可以使用；不得自行计算任何新数字。
7. 证据不足时 status 写 missing；missing_reason 必须含 gap_code、detail、searched_evidence_ids，明确缺哪类证据和已经检查哪些输入；不得用免责声明或空泛文字填充。
8. 不得输出目标价、估值结论、买卖、仓位、止损或执行建议。
9. falsification_tests 必须返回 tests；每项除 direction、threshold、unit、time_window、latest_actual_baseline、reason 外，还必须含 evidence_ids 与 supporting_quotes。direction 只能是 below 或 above；threshold 与 baseline 必须直接引用证据；time_window 必须写“下一份正式披露”“后续正式披露”等未来窗口，禁止把 baseline 已发生期间当作未来窗口。
10. supporting_quotes 每条必须是对应 evidence.value 中逐字连续出现的实质性片段，至少含 8 个非空白字符；不得只摘数字、单位或栏目名，也不得拼接不连续片段。
11. items 字段一律禁止。
12. “增长、下降、改善、恶化、趋势、上升、下滑”等时间比较，只能在同一指标有两个可比期间，或引用原文逐字包含该趋势词时使用；单期绝对值不得推出趋势。
13. 不要输出 Markdown，不要增加 schema 外字段。"""


@dataclass(frozen=True)
class FrozenJudgmentInput:
    request: dict[str, Any]
    registry: dict[str, dict[str, Any]]
    preflight_missing: dict[str, str]
    input_hash: str


def _canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode()
    ).hexdigest()


def _citation(value: Mapping[str, Any], *, narrative: bool = False) -> dict[str, Any]:
    result = {
        key: value.get(key)
        for key in (
            "document_id",
            "raw_hash",
            "page_number",
            "source_url",
            "report_period",
        )
    }
    result["quoted_anchor"] = value.get("text") if narrative else value.get("quoted_anchor")
    result["unit"] = "narrative_text" if narrative else value.get("unit")
    if narrative:
        result["section_path"] = value.get("section_path")
    elif value.get("statement_scope"):
        result["statement_scope"] = value.get("statement_scope")
    return result


def _complete_citation(value: Mapping[str, Any]) -> bool:
    return all(value.get(key) not in (None, "") for key in _REQUIRED_CITATION)


def _decimal(value: Any) -> Decimal | None:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed.is_finite() else None


def _numeric_value(token: str) -> Decimal | None:
    cleaned = token.replace(",", "").rstrip("%")
    parsed = _decimal(cleaned)
    if parsed is None:
        return None
    return parsed / Decimal("100") if token.endswith("%") else parsed


def _source_display_token(fact: Mapping[str, Any]) -> str | None:
    wanted = _decimal(fact.get("value"))
    if wanted is None:
        return None
    tokens = _NUMBER.findall(str(fact.get("quoted_anchor") or ""))
    matches = [token for token in tokens if _numeric_value(token) == wanted]
    if not matches:
        return None
    selected = max(matches, key=len)
    larger = [
        value
        for value in (_numeric_value(token) for token in tokens)
        if value is not None and abs(value) >= Decimal("1000")
    ]
    if abs(wanted) < Decimal("100") and larger:
        return None
    return selected


def _resolved_narratives(
    blocks: Iterable[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    rows = []
    for block in blocks:
        citation = _citation(block, narrative=True)
        if (
            block.get("status") == "resolved"
            and block.get("section_path")
            and block.get("text")
            and _complete_citation(citation)
        ):
            rows.append(block)
    rows.sort(
        key=lambda row: (
            str(row.get("report_period") or ""),
            str(row.get("document_id") or ""),
            int(row.get("page_number") or 0),
            str(row.get("text") or ""),
        ),
        reverse=True,
    )
    return rows


def _resolved_financials(
    facts: Iterable[Mapping[str, Any]],
) -> list[tuple[Mapping[str, Any], str]]:
    rows: list[tuple[Mapping[str, Any], str]] = []
    for fact in facts:
        citation = _citation(fact)
        period = str(fact.get("report_period") or "")
        display = _source_display_token(fact)
        if (
            period not in {"", "unknown", "unresolved"}
            and display is not None
            and _complete_citation(citation)
            and not (
                fact.get("metric") == "shares_outstanding"
                and fact.get("unit") not in {"股", "shares"}
            )
        ):
            rows.append((fact, display))
    rows.sort(
        key=lambda pair: (
            str(pair[0].get("report_period") or ""),
            str(pair[0].get("metric") or ""),
            str(pair[0].get("document_id") or ""),
            int(pair[0].get("page_number") or 0),
        ),
        reverse=True,
    )
    return rows


def _margin_derivations(
    financial: list[tuple[Mapping[str, Any], str]],
) -> list[dict[str, Any]]:
    by_key: dict[tuple[str, str, str], dict[str, tuple[Mapping[str, Any], str]]] = {}
    for fact, display in financial:
        key = (
            str(fact.get("report_period")),
            str(fact.get("unit")),
            str(fact.get("statement_scope") or ""),
        )
        by_key.setdefault(key, {})[str(fact.get("metric"))] = (fact, display)
    results: list[dict[str, Any]] = []
    for key, metrics in sorted(by_key.items(), reverse=True):
        if "revenue" not in metrics or "operating_cost" not in metrics:
            continue
        revenue = _decimal(metrics["revenue"][0].get("value"))
        cost = _decimal(metrics["operating_cost"][0].get("value"))
        if (
            revenue is None
            or cost is None
            or revenue <= 0
            or cost <= 0
            or cost >= revenue
        ):
            continue
        gross_profit = revenue - cost
        gross_margin = (
            gross_profit / revenue * Decimal("100")
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        results.extend(
            (
                {
                    "metric": "derived_gross_profit",
                    "display_value": format(gross_profit, "f"),
                    "unit": key[1],
                    "period": key[0],
                    "scope": key[2],
                    "operation": "revenue - operating_cost",
                    "component_metrics": ("revenue", "operating_cost"),
                },
                {
                    "metric": "derived_gross_margin",
                    "display_value": format(gross_margin, "f") + "%",
                    "unit": "%",
                    "period": key[0],
                    "scope": key[2],
                    "operation": "(revenue - operating_cost) / revenue * 100",
                    "component_metrics": ("revenue", "operating_cost"),
                    "rounding": "ROUND_HALF_UP to 2 decimal places",
                },
            )
        )
        break
    return results


def _has_terms(rows: Iterable[Mapping[str, Any]], terms: tuple[str, ...]) -> bool:
    return any(
        any(term in str(row.get("section_path") or "") + str(row.get("text") or "") for term in terms)
        for row in rows
    )


def freeze_judgment_input(
    *,
    ticker: str,
    issuer_identity: Mapping[str, Any],
    page_facts: Iterable[Mapping[str, Any]],
    narrative_blocks: Iterable[Mapping[str, Any]],
    source_receipts: Mapping[str, Any],
) -> FrozenJudgmentInput:
    """Freeze a bounded, page-cited request before any model call."""
    normalized = ticker.upper()
    if str(issuer_identity.get("ticker") or "").upper() != normalized:
        raise ValueError("issuer identity ticker mismatch")
    issuer_name = str(issuer_identity.get("name") or "").strip()
    if not issuer_name:
        raise ValueError("issuer identity name is required")
    narratives = _resolved_narratives(narrative_blocks)
    financial = _resolved_financials(page_facts)
    registry: dict[str, dict[str, Any]] = {}
    for index, block in enumerate(narratives, 1):
        evidence_id = "N" + str(index).zfill(4)
        registry[evidence_id] = {
            "kind": "narrative",
            "text": block["text"],
            "section_path": block["section_path"],
            "citation": _citation(block, narrative=True),
            "allowed_numeric_displays": list(
                dict.fromkeys(_NUMBER.findall(str(block["text"])))
            ),
        }
    financial_ids: dict[tuple[str, str, str, int], str] = {}
    for index, (fact, display) in enumerate(financial, 1):
        evidence_id = "F" + str(index).zfill(4)
        financial_ids[
            (
                str(fact.get("report_period")),
                str(fact.get("metric")),
                str(fact.get("unit")),
                int(fact.get("page_number") or 0),
            )
        ] = evidence_id
        period_numbers = re.findall(r"\d+", str(fact.get("report_period") or ""))
        registry[evidence_id] = {
            "kind": "financial_fact",
            "metric": fact["metric"],
            "value": fact["value"],
            "display_value": display,
            "period": fact["report_period"],
            "unit": fact["unit"],
            "scope": fact.get("statement_scope"),
            "citation": _citation(fact),
            "allowed_numeric_displays": [display, *period_numbers],
        }
    derivations = _margin_derivations(financial)
    for index, derived in enumerate(derivations, 1):
        component_ids = []
        for metric in derived["component_metrics"]:
            candidates = [
                evidence_id
                for evidence_id, item in registry.items()
                if item.get("kind") == "financial_fact"
                and item.get("metric") == metric
                and item.get("period") == derived["period"]
                and item.get("scope") == derived["scope"]
                and item.get("unit") == (
                    derived["unit"] if derived["unit"] != "%" else next(
                        (
                            value.get("unit")
                            for value in registry.values()
                            if value.get("metric") == "revenue"
                            and value.get("period") == derived["period"]
                        ),
                        None,
                    )
                )
            ]
            if candidates:
                component_ids.append(candidates[0])
        if len(component_ids) != 2:
            continue
        evidence_id = "D" + str(index).zfill(4)
        registry[evidence_id] = {
            "kind": "deterministic_derived_metric",
            **derived,
            "component_evidence_ids": component_ids,
            "allowed_numeric_displays": [
                derived["display_value"],
                *re.findall(r"\d+", derived["period"]),
            ],
        }

    available = {
        "narrative": bool(narratives),
        "financial": bool(financial),
        "financial_pair": len({fact.get("metric") for fact, _ in financial}) >= 2,
        "moat_narrative": _has_terms(
            narratives,
            ("竞争", "技术", "研发", "品牌", "客户", "产品", "渠道"),
        ),
        "risk_narrative": _has_terms(narratives, ("风险", "不利", "波动", "挑战")),
        "derived_margin": any(key.startswith("D") for key in registry),
    }
    preflight_missing = dict(_ALWAYS_MISSING)
    runnable_tasks = []
    for judgment_id, task in _TASKS.items():
        missing_requirements = [
            requirement
            for requirement in task["requires"]
            if not available.get(requirement, False)
        ]
        if missing_requirements:
            preflight_missing[judgment_id] = (
                "missing required frozen evidence classes: "
                + ", ".join(missing_requirements)
            )
        else:
            runnable_tasks.append(
                {
                    "judgment_id": judgment_id,
                    "objective": task["objective"],
                    "required_evidence_classes": list(task["requires"]),
                }
            )
    request = {
        "generator_version": GENERATOR_VERSION,
        "prompt_version": PROMPT_VERSION,
        "ticker": normalized,
        "issuer_identity": deepcopy(dict(issuer_identity)),
        "source_receipts": deepcopy(dict(source_receipts)),
        "constraints": {
            "status_after_validation": JUDGMENT_STATUS,
            "facts_are_page_level_only": True,
            "human_review_required": True,
            "no_target_price_position_or_action": True,
        },
        "tasks": runnable_tasks,
        "evidence_registry": registry,
        "output_shape": {
            "judgments": [
                {
                    "judgment_id": "one requested task id",
                    "status": "available or missing",
                    "text": "required only when available",
                    "claims": [
                        {
                            "text": "one sentence copied exactly from text",
                            "claim_type": "inference",
                            "evidence_ids": ["one or more registry ids"],
                            "supporting_quotes": [
                                {
                                    "evidence_id": "one cited registry id",
                                    "quote": "verbatim source span",
                                }
                            ],
                        }
                    ],
                    "tests": "required only for falsification_tests",
                    "items": "forbidden",
                    "missing_reason": {
                        "gap_code": "required only when missing",
                        "detail": "specific input gap",
                        "searched_evidence_ids": ["registry ids actually checked"],
                    },
                }
            ]
        },
    }
    return FrozenJudgmentInput(
        request=request,
        registry=registry,
        preflight_missing=preflight_missing,
        input_hash=_canonical_hash(request),
    )


def _sentences(text: str) -> list[str]:
    return [item.strip() for item in _SENTENCE_BREAK.split(text.strip()) if item.strip()]


def _number_tokens(text: str) -> list[str]:
    return _NUMBER.findall(text)


def _content_anchors(evidence: Mapping[str, Any], issuer_name: str) -> set[str]:
    source = str(evidence.get("text") or evidence.get("citation", {}).get("quoted_anchor") or "")
    source = source.replace(issuer_name, "")
    anchors: set[str] = set()
    for phrase in re.findall(r"[\u4e00-\u9fff]{4,}", source):
        for size in range(4, min(9, len(phrase) + 1)):
            for index in range(0, len(phrase) - size + 1):
                value = phrase[index : index + size]
                if not any(generic in value or value in generic for generic in _GENERIC_ANCHORS):
                    anchors.add(value)
    return anchors


def _specificity(
    sentence: str,
    evidence_ids: Iterable[str],
    registry: Mapping[str, Mapping[str, Any]],
    issuer_name: str,
) -> tuple[bool, list[str]]:
    anchors: set[str] = set()
    for evidence_id in evidence_ids:
        evidence = registry[evidence_id]
        anchors.update(
            value
            for value in evidence.get("allowed_numeric_displays") or []
            if value and value in sentence
        )
        anchors.update(
            value
            for value in _content_anchors(evidence, issuer_name)
            if value in sentence
        )
    return bool(anchors), sorted(anchors, key=lambda value: (-len(value), value))[:8]


def _fact_projection(
    evidence_id: str,
    registry: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    evidence = registry[evidence_id]
    if evidence["kind"] == "narrative":
        return {
            "evidence_id": evidence_id,
            "evidence_type": "narrative_block",
            "metric": "narrative_evidence",
            "value": evidence["text"],
            "citation": deepcopy(evidence["citation"]),
        }
    if evidence["kind"] == "financial_fact":
        return {
            "evidence_id": evidence_id,
            "evidence_type": "financial_fact",
            "metric": evidence["metric"],
            "value": evidence["value"],
            "display_value": evidence["display_value"],
            "citation": deepcopy(evidence["citation"]),
        }
    component_citations = [
        deepcopy(registry[item]["citation"])
        for item in evidence["component_evidence_ids"]
    ]
    return {
        "evidence_id": evidence_id,
        "evidence_type": "deterministic_derived_metric",
        "metric": evidence["metric"],
        "value": evidence["display_value"],
        "display_value": evidence["display_value"],
        "operation": evidence["operation"],
        "component_evidence_ids": list(evidence["component_evidence_ids"]),
        "component_citations": component_citations,
        "citation": component_citations[0],
    }


def _source_text(evidence: Mapping[str, Any]) -> str:
    return str(
        evidence.get("text")
        or evidence.get("citation", {}).get("quoted_anchor")
        or ""
    )


def _validate_supporting_quotes(
    *,
    quotes: Any,
    evidence_ids: list[str],
    registry: Mapping[str, Mapping[str, Any]],
    prefix: str,
) -> tuple[list[dict[str, str]], list[str]]:
    errors: list[str] = []
    if not isinstance(quotes, list) or not quotes:
        return [], [prefix + " requires supporting_quotes"]
    accepted: list[dict[str, str]] = []
    for index, row in enumerate(quotes):
        quote_prefix = prefix + ".supporting_quotes[" + str(index) + "]"
        if not isinstance(row, Mapping):
            errors.append(quote_prefix + " must be an object")
            continue
        evidence_id = str(row.get("evidence_id") or "")
        quote = str(row.get("quote") or "").strip()
        if evidence_id not in evidence_ids:
            errors.append(quote_prefix + " evidence id is not cited by the field")
            continue
        if len(quote) < 8:
            errors.append(quote_prefix + " must contain a substantive source span")
            continue
        if quote not in _source_text(registry[evidence_id]):
            errors.append(quote_prefix + " is not verbatim source text")
            continue
        accepted.append({"evidence_id": evidence_id, "quote": quote})
    return accepted, errors


def _validate_structured_text(
    *,
    text: str,
    evidence_ids: Any,
    supporting_quotes: Any,
    registry: Mapping[str, Mapping[str, Any]],
    issuer_name: str,
    prefix: str,
    claim_type: str = "inference",
) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    if not text.strip():
        errors.append(prefix + " text is required")
    if not isinstance(evidence_ids, list) or not evidence_ids:
        return None, errors + [prefix + " requires evidence_ids"]
    normalized_ids = [str(item) for item in evidence_ids]
    unknown = [item for item in normalized_ids if item not in registry]
    if unknown:
        return None, errors + [
            prefix + " cites unknown evidence ids: " + ", ".join(unknown)
        ]
    quotes, quote_errors = _validate_supporting_quotes(
        quotes=supporting_quotes,
        evidence_ids=normalized_ids,
        registry=registry,
        prefix=prefix,
    )
    errors.extend(quote_errors)
    if claim_type not in {"fact", "inference"}:
        errors.append(prefix + " claim_type must be fact or inference")
    if claim_type == "fact" and (
        len(quotes) != 1
        or text.rstrip("。！？；").strip()
        != quotes[0]["quote"].rstrip("。！？；").strip()
    ):
        errors.append(
            prefix
            + " fact text must equal one verbatim supporting quote apart from terminal punctuation"
        )
    if claim_type == "inference" and not any(
        marker in text for marker in _INFERENCE_MARKERS
    ):
        errors.append(prefix + " inference lacks explicit conditional language")
    quoted_text = " ".join(row["quote"] for row in quotes)
    unsupported = [
        term
        for term in _UNSUPPORTED_COMPARATIVES
        if term in text and term not in quoted_text
    ]
    if unsupported:
        errors.append(
            prefix
            + " contains unsupported comparative assertion: "
            + ", ".join(unsupported)
        )
    unsupported_temporal = [
        term
        for term in _TEMPORAL_COMPARATIVES
        if term in text and term not in quoted_text
    ]
    if unsupported_temporal:
        financial_periods_by_metric: dict[str, set[str]] = {}
        for evidence_id in normalized_ids:
            evidence = registry[evidence_id]
            if evidence.get("kind") != "financial_fact":
                continue
            metric = str(evidence.get("metric") or "")
            financial_periods_by_metric.setdefault(metric, set()).add(
                str(evidence.get("period") or "")
            )
        has_comparable_periods = any(
            len(periods - {""}) >= 2
            for periods in financial_periods_by_metric.values()
        )
        if not has_comparable_periods:
            errors.append(
                prefix
                + " contains unsupported temporal comparison: "
                + ", ".join(unsupported_temporal)
            )
    allowed_numbers = {
        token
        for evidence_id in normalized_ids
        for token in registry[evidence_id].get("allowed_numeric_displays") or []
    }
    for token in _number_tokens(text):
        if token not in allowed_numbers:
            errors.append(prefix + " contains untraceable numeric token: " + token)
    if _SCIENCE.search(text):
        errors.append(prefix + " contains scientific notation")
    specific, anchors = _specificity(
        text,
        normalized_ids,
        registry,
        issuer_name,
    )
    if not specific:
        errors.append(prefix + " lacks source-specific content")
    if errors:
        return None, sorted(set(errors))
    return {
        "text": text,
        "claim_type": claim_type,
        "evidence_ids": normalized_ids,
        "supporting_quotes": quotes,
        "specific_anchors": anchors,
    }, []


def _missing(reason: str, *, errors: Iterable[str] = ()) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "missing",
        "reason": reason,
        "raw_text_excerpt": "no qualifying page-bound evidence or validated model judgment",
    }
    error_rows = list(errors)
    if error_rows:
        result["validation_errors"] = error_rows
    return result


def _validate_falsification(
    value: Mapping[str, Any],
    registry: Mapping[str, Mapping[str, Any]],
    issuer_name: str,
) -> list[str]:
    errors: list[str] = []
    tests = value.get("tests")
    if not isinstance(tests, list) or not tests:
        return ["falsification_tests requires non-empty tests"]
    for index, test in enumerate(tests):
        prefix = "tests[" + str(index) + "]"
        if not isinstance(test, Mapping):
            errors.append(prefix + " must be an object")
            continue
        allowed_fields = {
            "direction",
            "threshold_evidence_id",
            "threshold",
            "unit",
            "time_window",
            "latest_actual_baseline",
            "reason",
            "evidence_ids",
            "supporting_quotes",
        }
        unknown_fields = sorted(set(test) - allowed_fields)
        if unknown_fields:
            errors.append(prefix + " contains unknown fields: " + ", ".join(unknown_fields))
        if test.get("direction") not in {"below", "above"}:
            errors.append(prefix + " direction must be below or above")
        evidence_ids = test.get("evidence_ids")
        normalized_ids = (
            [str(item) for item in evidence_ids]
            if isinstance(evidence_ids, list)
            else []
        )
        invalid_ids = [item for item in normalized_ids if item not in registry]
        if not normalized_ids or invalid_ids:
            errors.append(prefix + " requires valid evidence_ids")
        _validated_reason, reason_errors = _validate_structured_text(
            text=str(test.get("reason") or "").strip(),
            evidence_ids=normalized_ids,
            supporting_quotes=test.get("supporting_quotes"),
            registry=registry,
            issuer_name=issuer_name,
            prefix=prefix + ".reason",
            claim_type="inference",
        )
        errors.extend(reason_errors)
        threshold_id = str(test.get("threshold_evidence_id") or "")
        if threshold_id not in registry or not threshold_id.startswith(("F", "D")):
            errors.append(prefix + " threshold evidence is invalid")
        elif threshold_id not in normalized_ids:
            errors.append(prefix + " threshold evidence must be cited by the test")
        else:
            expected = str(registry[threshold_id].get("display_value") or "")
            if str(test.get("threshold") or "") != expected:
                errors.append(prefix + " threshold is not the frozen display value")
            if str(test.get("unit") or "") != str(registry[threshold_id].get("unit") or ""):
                errors.append(prefix + " threshold unit mismatch")
        baseline = test.get("latest_actual_baseline")
        if not isinstance(baseline, Mapping):
            errors.append(prefix + " latest_actual_baseline is required")
        else:
            baseline_id = str(baseline.get("evidence_id") or "")
            if baseline_id not in registry or not baseline_id.startswith("F"):
                errors.append(prefix + " baseline must reference a financial fact")
            elif baseline_id not in normalized_ids:
                errors.append(prefix + " baseline evidence must be cited by the test")
            else:
                expected = registry[baseline_id]
                for key, expected_value in (
                    ("display_value", expected.get("display_value")),
                    ("unit", expected.get("unit")),
                    ("period", expected.get("period")),
                ):
                    if str(baseline.get(key) or "") != str(expected_value or ""):
                        errors.append(prefix + " baseline " + key + " mismatch")
        time_window = str(test.get("time_window") or "").strip()
        if not time_window:
            errors.append(prefix + " time_window is required")
        elif not any(marker in time_window for marker in _FUTURE_WINDOW_MARKERS):
            errors.append(
                prefix
                + " time_window must identify a future or next formal disclosure"
            )
        if len(str(test.get("reason") or "").strip()) < 18:
            errors.append(prefix + " reason lacks a meaningful business mechanism")
        serialized = json.dumps(test, ensure_ascii=False)
        allowed_numbers = {
            token
            for evidence_id in normalized_ids
            if evidence_id in registry
            for token in registry[evidence_id].get("allowed_numeric_displays") or []
        }
        for token in _number_tokens(serialized):
            if token not in allowed_numbers:
                errors.append(prefix + " contains untraceable numeric token: " + token)
        if _SCIENCE.search(serialized):
            errors.append(prefix + " contains scientific notation")
    return errors


def _validate_items(
    value: Mapping[str, Any],
    registry: Mapping[str, Mapping[str, Any]],
    issuer_name: str,
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    raw_items = value.get("items")
    if raw_items is None:
        return [], [], []
    if not isinstance(raw_items, list):
        return [], ["items must be an array"], []
    adapted: list[dict[str, Any]] = []
    errors: list[str] = []
    used: list[str] = []
    for index, item in enumerate(raw_items):
        prefix = "items[" + str(index) + "]"
        if not isinstance(item, Mapping):
            errors.append(prefix + " must be an object")
            continue
        unknown_fields = sorted(
            set(item) - {"text", "evidence_ids", "supporting_quotes"}
        )
        if unknown_fields:
            errors.append(prefix + " contains unknown fields: " + ", ".join(unknown_fields))
        structured, item_errors = _validate_structured_text(
            text=str(item.get("text") or "").strip(),
            evidence_ids=item.get("evidence_ids"),
            supporting_quotes=item.get("supporting_quotes"),
            registry=registry,
            issuer_name=issuer_name,
            prefix=prefix,
            claim_type="inference",
        )
        if item_errors or structured is None:
            errors.extend(item_errors)
            continue
        adapted.append(
            {
                "text": structured["text"],
                "evidence_ids": structured["evidence_ids"],
                "supporting_quotes": structured["supporting_quotes"],
            }
        )
        for evidence_id in structured["evidence_ids"]:
            if evidence_id not in used:
                used.append(evidence_id)
    return adapted, sorted(set(errors)), used


def _validate_item(
    *,
    judgment_id: str,
    value: Mapping[str, Any],
    frozen: FrozenJudgmentInput,
) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    if value.get("status") == "missing":
        missing_reason = value.get("missing_reason")
        if not isinstance(missing_reason, Mapping):
            errors.append("model missing item requires structured missing_reason")
            return None, errors
        gap_code = str(missing_reason.get("gap_code") or "").strip()
        detail = str(missing_reason.get("detail") or "").strip()
        searched = missing_reason.get("searched_evidence_ids")
        if not gap_code or len(detail) < 20:
            errors.append("model missing item requires exact gap_code and detail")
        if not isinstance(searched, list):
            errors.append("model missing item requires searched_evidence_ids")
            searched = []
        unknown = [
            str(item)
            for item in searched
            if str(item) not in frozen.registry
        ]
        if unknown:
            errors.append(
                "model missing item searched unknown evidence ids: "
                + ", ".join(unknown)
            )
        if errors:
            return None, errors
        result = _missing(gap_code + ": " + detail)
        result["searched_evidence_ids"] = [str(item) for item in searched]
        return result, []
    if value.get("status") != "available":
        return None, ["status must be available or missing"]
    text = value.get("text")
    claims = value.get("claims")
    if not isinstance(text, str) or not text.strip():
        errors.append("available item requires text")
        text = ""
    if not isinstance(claims, list) or not claims:
        errors.append("available item requires claims")
        claims = []
    sentences = _sentences(text)
    if not 1 <= len(sentences) <= 2:
        errors.append("available item requires one or two sentences")
    claim_texts = [
        str(claim.get("text") or "").strip()
        for claim in claims
        if isinstance(claim, Mapping)
    ]
    if sentences != claim_texts:
        errors.append("claims must match text sentence-for-sentence and byte-for-byte")
    issuer_name = str(frozen.request["issuer_identity"]["name"])
    adapted_claims: list[dict[str, Any]] = []
    used_ids: list[str] = []
    rename_rows: list[dict[str, Any]] = []
    for index, claim in enumerate(claims):
        prefix = "claims[" + str(index) + "]"
        if not isinstance(claim, Mapping):
            errors.append(prefix + " must be an object")
            continue
        if claim.get("claim_type") != "inference":
            errors.append(prefix + " claim_type must be inference")
            continue
        sentence = str(claim.get("text") or "").strip()
        structured, claim_errors = _validate_structured_text(
            text=sentence,
            evidence_ids=claim.get("evidence_ids"),
            supporting_quotes=claim.get("supporting_quotes"),
            registry=frozen.registry,
            issuer_name=issuer_name,
            prefix=prefix,
            claim_type=str(claim.get("claim_type") or ""),
        )
        if claim_errors or structured is None:
            errors.extend(claim_errors)
            continue
        normalized_ids = structured["evidence_ids"]
        anchors = structured["specific_anchors"]
        specific = bool(anchors)
        citations = []
        for evidence_id in normalized_ids:
            projected = _fact_projection(evidence_id, frozen.registry)
            if projected["evidence_type"] == "deterministic_derived_metric":
                citations.extend(projected["component_citations"])
            else:
                citations.append(projected["citation"])
            if evidence_id not in used_ids:
                used_ids.append(evidence_id)
        adapted_claims.append(
            {
                "text": sentence,
                "claim_type": structured["claim_type"],
                "evidence_ids": normalized_ids,
                "supporting_quotes": structured["supporting_quotes"],
                "citations": citations,
            }
        )
        replaced = sentence.replace(issuer_name, "该公司")
        rename_rows.append(
            {
                "sentence": sentence,
                "replaced_sentence": replaced,
                "status": "passed" if specific else "failed",
                "specific_anchors": anchors,
                "reason": (
                    "source-specific anchors survive issuer replacement"
                    if specific
                    else "no source-specific anchor survives issuer replacement"
                ),
            }
        )
    if judgment_id == "falsification_tests":
        errors.extend(_validate_falsification(value, frozen.registry, issuer_name))
    elif "tests" in value:
        errors.append("tests field is forbidden for this judgment")
    if "items" in value:
        errors.append("items field is forbidden for model judgments")
    adapted_items, item_errors, item_ids = _validate_items(
        value,
        frozen.registry,
        issuer_name,
    )
    errors.extend(item_errors)
    for evidence_id in item_ids:
        if evidence_id not in used_ids:
            used_ids.append(evidence_id)
    if errors:
        return None, sorted(set(errors))
    passed = sum(row["status"] == "passed" for row in rename_rows)
    result = {
        "status": JUDGMENT_STATUS,
        "text": text,
        "facts": [_fact_projection(item, frozen.registry) for item in used_ids],
        "claims": adapted_claims,
        "name_swap_test": {
            "status": "passed" if passed == len(rename_rows) else "failed",
            "passed_sentences": passed,
            "total_sentences": len(rename_rows),
            "pass_rate": passed / len(rename_rows) if rename_rows else 0.0,
            "sentences": rename_rows,
        },
        "citation_mix": {
            "narrative_blocks": sum(item.startswith("N") for item in used_ids),
            "financial_facts": sum(item.startswith("F") for item in used_ids),
            "derived_metrics": sum(item.startswith("D") for item in used_ids),
        },
    }
    if "tests" in value:
        result["tests"] = deepcopy(value["tests"])
    return result, []


def _validate_response(
    response: Mapping[str, Any],
    frozen: FrozenJudgmentInput,
) -> tuple[dict[str, Any], dict[str, list[str]]]:
    raw_rows = response.get("judgments")
    if not isinstance(raw_rows, list):
        return {}, {"__response__": ["response requires judgments array"]}
    by_id: dict[str, Mapping[str, Any]] = {}
    duplicate_ids: set[str] = set()
    for row in raw_rows:
        if not isinstance(row, Mapping):
            continue
        judgment_id = str(row.get("judgment_id") or "")
        if judgment_id in by_id:
            duplicate_ids.add(judgment_id)
        by_id[judgment_id] = row
    output: dict[str, Any] = {}
    errors: dict[str, list[str]] = {}
    requested_ids = {item["judgment_id"] for item in frozen.request["tasks"]}
    unknown = sorted(set(by_id) - requested_ids)
    if unknown:
        errors["__response__"] = ["response contains unrequested judgments: " + ", ".join(unknown)]
    for judgment_id in sorted(requested_ids):
        if judgment_id in duplicate_ids:
            errors[judgment_id] = ["duplicate judgment id"]
            continue
        value = by_id.get(judgment_id)
        if value is None:
            errors[judgment_id] = ["requested judgment is absent from response"]
            continue
        adapted, item_errors = _validate_item(
            judgment_id=judgment_id,
            value=value,
            frozen=frozen,
        )
        if item_errors:
            errors[judgment_id] = item_errors
        elif adapted is not None:
            output[judgment_id] = adapted
    return output, errors


def _task_registry(
    judgment_id: str,
    registry: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    narrative_terms = {
        "investment_thesis": ("业务", "产品", "客户", "经营", "战略"),
        "moat_assessment": ("竞争", "技术", "研发", "品牌", "客户", "产品", "渠道"),
        "risk_register": ("风险", "不利", "波动", "挑战"),
        "falsification_tests": ("业务", "产品", "客户", "经营"),
        "monitoring_kpis": ("业务", "产品", "研发", "客户", "经营", "风险"),
        "action_triggers": ("风险", "业务", "产品", "经营"),
        "accounting_checks": ("经营", "风险", "财务"),
        "operating_kpis": ("业务", "产品", "研发", "客户", "渠道", "产能"),
        "margin_bridge": ("成本", "盈利", "产品", "业务"),
    }.get(judgment_id, ())
    selected_ids: list[str] = []
    if judgment_id in {
        "investment_thesis",
        "moat_assessment",
        "risk_register",
        "monitoring_kpis",
        "operating_kpis",
    }:
        narrative_candidates = []
        for evidence_id, evidence in registry.items():
            if evidence.get("kind") != "narrative":
                continue
            path = str(evidence.get("section_path") or "")
            text = str(evidence.get("text") or "")
            combined = path + text
            term_score = sum(4 for term in narrative_terms if term in combined)
            if not term_score:
                continue
            score = term_score
            if "管理层讨论与分析" in path:
                score += 18
            if "经营情况讨论与分析" in path:
                score += 12
            if "财务报告" in path:
                score -= 10
            if "会计政策" in path or "金融工具" in path:
                score -= 8
            if judgment_id == "risk_register" and "风险" in path:
                score += 12
            narrative_candidates.append(
                (
                    score,
                    str(evidence.get("citation", {}).get("report_period") or ""),
                    evidence_id,
                )
            )
        narrative_candidates.sort(reverse=True)
        narrative_ids = [row[2] for row in narrative_candidates[:4]]
        if not narrative_ids:
            narrative_ids = [
                evidence_id
                for evidence_id, evidence in registry.items()
                if evidence.get("kind") == "narrative"
            ][:6]
        selected_ids.extend(narrative_ids)
    metric_priority = {
        "investment_thesis": (
            "revenue",
            "net_profit_parent",
            "operating_cash_flow",
            "operating_cost",
        ),
        "falsification_tests": (
            "revenue",
            "net_profit_parent",
            "operating_cash_flow",
        ),
        "monitoring_kpis": (
            "revenue",
            "net_profit_parent",
            "operating_cash_flow",
            "operating_cost",
        ),
        "action_triggers": (
            "revenue",
            "net_profit_parent",
            "operating_cash_flow",
        ),
        "accounting_checks": (
            "revenue",
            "operating_cost",
            "net_profit_parent",
            "operating_cash_flow",
            "total_assets",
            "total_liabilities",
            "cash",
        ),
        "margin_bridge": ("revenue", "operating_cost"),
    }.get(judgment_id, ())
    for metric in metric_priority:
        matches = [
            evidence_id
            for evidence_id, evidence in registry.items()
            if evidence.get("kind") == "financial_fact"
            and evidence.get("metric") == metric
        ]
        selected_ids.extend(matches[:1])
    if judgment_id in {"margin_bridge", "monitoring_kpis"}:
        derived_ids = [
            evidence_id
            for evidence_id, evidence in registry.items()
            if evidence.get("kind") == "deterministic_derived_metric"
        ]
        selected_ids.extend(derived_ids)
        for evidence_id in derived_ids:
            selected_ids.extend(registry[evidence_id]["component_evidence_ids"])
    unique = list(dict.fromkeys(selected_ids))
    return {
        evidence_id: deepcopy(dict(registry[evidence_id]))
        for evidence_id in unique
    }


def generate_model_judgments(
    *,
    ticker: str,
    issuer_identity: Mapping[str, Any],
    page_facts: Iterable[Mapping[str, Any]],
    narrative_blocks: Iterable[Mapping[str, Any]],
    source_receipts: Mapping[str, Any],
    dossier_id: str,
    key_file: Path,
    model: str = DEFAULT_MODEL,
    transport: Any = None,
    judgment_ids: Iterable[str] | None = None,
    resume_receipt: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate and validate issuer judgments with no deterministic prose path."""
    frozen = freeze_judgment_input(
        ticker=ticker,
        issuer_identity=issuer_identity,
        page_facts=page_facts,
        narrative_blocks=narrative_blocks,
        source_receipts=source_receipts,
    )
    selected_judgment_ids = (
        {str(item) for item in judgment_ids}
        if judgment_ids is not None
        else None
    )
    if selected_judgment_ids is not None:
        known_ids = {item["judgment_id"] for item in frozen.request["tasks"]}
        unknown_ids = selected_judgment_ids - known_ids
        if unknown_ids:
            raise ValueError(
                "requested judgment ids are not runnable: "
                + ", ".join(sorted(unknown_ids))
            )
        frozen.request["tasks"] = [
            item
            for item in frozen.request["tasks"]
            if item["judgment_id"] in selected_judgment_ids
        ]
        frozen = FrozenJudgmentInput(
            request=frozen.request,
            registry=frozen.registry,
            preflight_missing=frozen.preflight_missing,
            input_hash=_canonical_hash(frozen.request),
        )
    content = {
        judgment_id: _missing(reason)
        for judgment_id, reason in frozen.preflight_missing.items()
    }
    model_receipts: list[dict[str, Any]] = []
    response_hashes: list[str] = []
    validation_errors: dict[str, list[str]] = {}
    validated: dict[str, Any] = {}
    resume_lineage: list[str] = []
    if resume_receipt is not None:
        expected_resume_fields = {
            "generator_version": GENERATOR_VERSION,
            "prompt_version": PROMPT_VERSION,
            "validator_version": VALIDATOR_VERSION,
            "input_hash": frozen.input_hash,
            "prompt_hash": _canonical_hash(_SYSTEM_PROMPT),
        }
        mismatches = [
            key
            for key, expected in expected_resume_fields.items()
            if resume_receipt.get(key) != expected
        ]
        if mismatches:
            raise ValueError(
                "resume receipt is incompatible: " + ", ".join(mismatches)
            )
        prior_content = resume_receipt.get("content") or {}
        if resume_receipt.get("content_hash") != _canonical_hash(prior_content):
            raise ValueError("resume receipt content hash mismatch")
        prior_model_receipts = list(
            resume_receipt.get("model_receipts") or ()
        )
        prior_response_hashes = list(
            resume_receipt.get("response_hashes") or ()
        )
        if len(prior_model_receipts) != len(prior_response_hashes):
            raise ValueError("resume receipt model/response cardinality mismatch")
        if any(
            not row.get("request_id")
            or not row.get("model")
            or row.get("finish_reason") != "stop"
            or not row.get("purpose")
            for row in prior_model_receipts
        ):
            raise ValueError("resume receipt contains incomplete model provenance")
        resume_lineage.extend(
            str(item) for item in resume_receipt.get("resume_lineage") or ()
        )
        prior_schema = str(resume_receipt.get("schema_version") or "")
        prior_hash = str(resume_receipt.get("receipt_hash") or "")
        if not prior_schema or not prior_hash:
            raise ValueError("resume receipt identity is incomplete")
        resume_lineage.append(prior_schema + ":" + prior_hash)
        model_receipts.extend(
            deepcopy(prior_model_receipts)
        )
        response_hashes.extend(
            str(item) for item in prior_response_hashes
        )
        for task in frozen.request["tasks"]:
            judgment_id = str(task["judgment_id"])
            prior_value = prior_content.get(judgment_id)
            if not isinstance(prior_value, Mapping):
                continue
            if prior_value.get("status") != JUDGMENT_STATUS:
                continue
            resume_value = deepcopy(dict(prior_value))
            resume_value["status"] = "available"
            resumed, resume_errors = _validate_item(
                judgment_id=judgment_id,
                value=resume_value,
                frozen=frozen,
            )
            if resume_errors or resumed is None:
                continue
            validated[judgment_id] = resumed
            content[judgment_id] = resumed
    for task in frozen.request["tasks"]:
        judgment_id = str(task["judgment_id"])
        if judgment_id in validated:
            continue
        task_request = {
            key: deepcopy(value)
            for key, value in frozen.request.items()
            if key != "evidence_registry"
        }
        task_request["tasks"] = [deepcopy(task)]
        task_request["evidence_registry"] = _task_registry(
            judgment_id,
            frozen.registry,
        )
        task_request["task_execution"] = {
            "return_exactly_one_judgment_id": judgment_id,
            "sentence_count": "one or two",
            "sentence_length": "40 to 120 Chinese characters",
            "claims_must_equal_text_sentences": True,
            "text_must_equal_claim_texts_concatenated_in_order": True,
            "prefer_inference_claims_with_explicit_conditional_language": True,
            "claim_type_policy": "every claim must use inference; fact is forbidden",
            "allowed_evidence_ids": list(task_request["evidence_registry"]),
            "tests_policy": (
                "exactly one test is required"
                if judgment_id == "falsification_tests"
                else "tests field is forbidden"
            ),
            "items_policy": "items field is forbidden",
            "numeric_copy_policy": (
                "Every numeric token must appear byte-for-byte in the cited "
                "evidence allowed_numeric_displays; numbers found only in "
                "quoted_anchor are forbidden; never append .0."
            ),
            "supporting_quote_policy": (
                "Each quote must be one verbatim contiguous substring from "
                "the cited evidence value, with at least 8 non-space "
                "characters and substantive words, never a number-only span."
            ),
        }
        if judgment_id == "action_triggers":
            task_request["task_execution"]["task_specific_guidance"] = (
                "Use one current financial display as both the observable "
                "baseline and review threshold. Do not calculate percentages "
                "or copy comparison-column numbers from quoted_anchor."
            )
        if judgment_id == "margin_bridge":
            task_request["task_execution"]["task_specific_guidance"] = (
                "Cite D evidence for deterministic derived values, but quote "
                "only the component F evidence because D has no verbatim "
                "source text. Copy each D display_value exactly, including "
                "comma and decimal formatting as supplied."
            )
        task_request["output_shape"] = {
            "judgments": [
                {
                    "judgment_id": judgment_id,
                    "status": "available or missing",
                    "text": "one or two sentences when available",
                    "claims": [
                        {
                            "text": "exactly one sentence from text",
                            "claim_type": "inference",
                            "evidence_ids": ["allowed evidence ids"],
                            "supporting_quotes": [
                                {
                                    "evidence_id": "one cited evidence id",
                                    "quote": "verbatim source span",
                                }
                            ],
                        }
                    ],
                    **(
                        {
                            "tests": [
                                {
                                    "direction": "below or above",
                                    "threshold_evidence_id": "one F or D id",
                                    "threshold": "exact allowed display",
                                    "unit": "exact evidence unit",
                                    "time_window": "specific disclosure window without invented digits",
                                    "latest_actual_baseline": {
                                        "evidence_id": "one F id",
                                        "display_value": "exact allowed display",
                                        "unit": "exact evidence unit",
                                        "period": "exact evidence period",
                                    },
                                    "reason": "conditional business mechanism",
                                    "evidence_ids": ["cited F, D, or N ids"],
                                    "supporting_quotes": [
                                        {
                                            "evidence_id": "one cited evidence id",
                                            "quote": "verbatim source span",
                                        }
                                    ],
                                }
                            ]
                        }
                        if judgment_id == "falsification_tests"
                        else {}
                    ),
                    "missing_reason": {
                        "gap_code": "required only when missing",
                        "detail": "specific input gap",
                        "searched_evidence_ids": ["ids actually checked"],
                    },
                }
            ]
        }
        task_frozen = FrozenJudgmentInput(
            request=task_request,
            registry=task_request["evidence_registry"],
            preflight_missing={},
            input_hash=_canonical_hash(task_request),
        )
        try:
            response, receipt = call_structured_deepseek(
                system_prompt=_SYSTEM_PROMPT,
                request_object=task_request,
                key_file=key_file,
                model=model,
                max_tokens=6000,
                reasoning_effort="medium",
                temperature=0,
                thinking_type="disabled",
                transport=transport,
            )
        except (json.JSONDecodeError, KeyError) as exc:
            validation_errors[judgment_id] = [
                "model response parse failure: " + type(exc).__name__
            ]
            content[judgment_id] = _missing(
                "generation_validation_failure",
                errors=validation_errors[judgment_id],
            )
            continue
        except RuntimeError as exc:
            if "did not finish cleanly: length" not in str(exc):
                raise
            validation_errors[judgment_id] = [
                "model response exceeded per-judgment output budget"
            ]
            content[judgment_id] = _missing(
                "generation_validation_failure",
                errors=validation_errors[judgment_id],
            )
            continue
        receipt["purpose"] = "draft:" + judgment_id
        model_receipts.append(receipt)
        response_hashes.append(_canonical_hash(response))
        item_validated, item_errors = _validate_response(response, task_frozen)
        rejected_response = response
        for repair_attempt in range(1, 3):
            if not item_errors:
                break
            repair_request = {
                "task": "Repair this one rejected judgment so it passes every supplied rule. Return the original output_shape only.",
                "validation_errors": item_errors,
                "rejected_draft": rejected_response,
                "original_request": task_request,
            }
            try:
                repaired, repair_receipt = call_structured_deepseek(
                    system_prompt=_SYSTEM_PROMPT,
                    request_object=repair_request,
                    key_file=key_file,
                    model=model,
                    max_tokens=6000,
                    reasoning_effort="medium",
                    temperature=0,
                    thinking_type="disabled",
                    transport=transport,
                )
            except (json.JSONDecodeError, KeyError) as exc:
                item_errors = {
                    judgment_id: [
                        "model repair parse failure: " + type(exc).__name__
                    ]
                }
                break
            except RuntimeError as exc:
                if "did not finish cleanly: length" not in str(exc):
                    raise
                item_errors = {
                    judgment_id: [
                        "model repair exceeded per-judgment output budget"
                    ]
                }
                break
            else:
                repair_receipt["purpose"] = (
                    "validation_repair:"
                    + judgment_id
                    + ":"
                    + str(repair_attempt)
                )
                model_receipts.append(repair_receipt)
                response_hashes.append(_canonical_hash(repaired))
                rejected_response = repaired
                item_validated, item_errors = _validate_response(
                    repaired,
                    task_frozen,
                )
        if judgment_id in item_validated:
            validated[judgment_id] = item_validated[judgment_id]
            content[judgment_id] = item_validated[judgment_id]
        if item_errors:
            errors = [
                message
                for messages in item_errors.values()
                for message in messages
            ]
            validation_errors[judgment_id] = sorted(set(errors))
            if judgment_id not in validated:
                content[judgment_id] = _missing(
                    "generation_validation_failure",
                    errors=validation_errors[judgment_id],
                )
    for value in content.values():
        if value.get("status") == JUDGMENT_STATUS:
            value["dossier_id"] = dossier_id
    requested_ids = {item["judgment_id"] for item in frozen.request["tasks"]}
    unresolved_requested = requested_ids - set(content)
    for judgment_id in sorted(unresolved_requested):
        content[judgment_id] = _missing(
            "generation_validation_failure",
            errors=["no validated judgment was produced"],
        )
    sentence_rows = [
        sentence
        for value in content.values()
        if value.get("status") == JUDGMENT_STATUS
        for sentence in value["name_swap_test"]["sentences"]
    ]
    rename_passed = sum(item["status"] == "passed" for item in sentence_rows)
    return {
        "generator_version": GENERATOR_VERSION,
        "prompt_version": PROMPT_VERSION,
        "validator_version": VALIDATOR_VERSION,
        "input_hash": frozen.input_hash,
        "prompt_hash": _canonical_hash(_SYSTEM_PROMPT),
        "response_hashes": response_hashes,
        "model_receipts": model_receipts,
        "resume_lineage": list(dict.fromkeys(resume_lineage)),
        "content_hash": _canonical_hash(content),
        "content": content,
        "validation": {
            "status": "passed" if not validation_errors else "partial",
            "errors": validation_errors,
            "name_swap": {
                "passed_sentences": rename_passed,
                "total_sentences": len(sentence_rows),
                "pass_rate": (
                    rename_passed / len(sentence_rows)
                    if sentence_rows
                    else 0.0
                ),
            },
        },
    }
