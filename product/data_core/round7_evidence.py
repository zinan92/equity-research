"""Build compact, page-bound evidence inputs for whole-chapter generation."""
from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import urlparse

from .e4_page_level_filing_facts import FilingNumericFact


NARRATIVE_SCHEMA = "e4-official-narrative-evidence-v1"
FINANCIAL_SCHEMA = "round7-financial-page-evidence-v1"
OFFICIAL_HOSTS = {
    "static.cninfo.com.cn",
    "www.cninfo.com.cn",
    "www.sse.com.cn",
    "static.sse.com.cn",
    "www.szse.cn",
    "disc.static.szse.cn",
    "www.bse.cn",
}
NUMBER = re.compile(
    r"(?<![A-Za-z0-9])[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?(?![A-Za-z0-9])"
)
SENTENCE_SPLIT = re.compile(r"(?<=[。！？；])")
YEAR = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")


SECTION_EVIDENCE_RULES: dict[str, dict[str, Any]] = {
    "one_line_positioning": {
        "paths": ("主要业务", "核心竞争力", "公司简介"),
        "keywords": ("动力电池", "储能电池", "电池回收", "研发", "客户"),
        "metrics": ("revenue",),
        "narratives": 7,
        "financials": 0,
    },
    "identity_founder_and_governance": {
        "paths": ("公司简介", "公司治理", "董事、监事和高级管理人员"),
        "keywords": ("曾毓群", "董事长", "总经理", "控股股东", "股东大会", "独立董事"),
        "metrics": ("shares_outstanding", "share_capital_amount"),
        "narratives": 16,
        "financials": 2,
    },
    "technology_origin_and_development_history": {
        "paths": ("核心竞争力", "主营业务分析", "主要产品及其用途", "未来发展的展望"),
        "keywords": ("研发", "技术", "产品", "专利", "投产", "创新", "麒麟", "神行", "凝聚态"),
        "metrics": ("capital_expenditure",),
        "narratives": 18,
        "financials": 2,
    },
    "business_model_and_business_lines": {
        "paths": ("主要业务", "主营业务分析", "收入与成本", "业绩驱动因素"),
        "keywords": ("动力电池", "储能", "电池材料", "回收", "销售", "客户", "盈利"),
        "metrics": ("revenue", "operating_cost"),
        "narratives": 18,
        "financials": 0,
    },
    "financial_and_operating_time_series": {
        "paths": ("主营业务分析", "收入与成本", "投资状况分析"),
        "keywords": ("收入", "现金流", "产能", "研发", "销量", "成本"),
        "metrics": (
            "revenue",
            "operating_cost",
            "net_profit_parent",
            "operating_cash_flow",
            "cash",
            "total_assets",
            "total_liabilities",
            "capital_expenditure",
        ),
        "narratives": 10,
        "financials": 18,
    },
    "moat_evidence_chain": {
        "paths": ("核心竞争力", "主要产品及其用途", "主营业务分析"),
        "keywords": ("研发", "专利", "客户", "制造", "供应链", "产品矩阵", "合作"),
        "metrics": ("revenue", "operating_cost", "cash"),
        "narratives": 18,
        "financials": 5,
    },
    "risks_counter_thesis_and_triggers": {
        "paths": ("可能面对的风险", "与金融工具相关的风险", "风险管理", "未来发展的展望"),
        "keywords": ("风险", "竞争", "原材料", "汇率", "流动性", "技术", "需求", "安全"),
        "metrics": (
            "cash",
            "short_term_borrowings",
            "long_term_borrowings",
            "total_liabilities",
            "capital_expenditure",
            "revenue",
        ),
        "narratives": 18,
        "financials": 8,
    },
    "research_conclusion_and_open_questions": {
        "paths": ("主要业务", "核心竞争力", "可能面对的风险", "主营业务分析"),
        "keywords": ("动力电池", "储能", "研发", "客户", "风险", "现金流", "竞争"),
        "metrics": ("revenue", "operating_cost", "cash", "total_liabilities"),
        "narratives": 14,
        "financials": 8,
    },
}


def canonical_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode()
    ).hexdigest()


def _official_url(value: object) -> bool:
    parsed = urlparse(str(value or ""))
    return parsed.scheme == "https" and parsed.hostname in OFFICIAL_HOSTS


def _narrative_receipt_hash(value: Mapping[str, Any]) -> str:
    payload = {
        key: item
        for key, item in value.items()
        if key not in {"receipt_hash", "receipt_id"}
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def load_source_receipts(
    *,
    narrative_path: Path,
    financial_path: Path,
    ticker: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    narratives = json.loads(narrative_path.read_text(encoding="utf-8"))
    financials = json.loads(financial_path.read_text(encoding="utf-8"))
    if (
        narratives.get("schema_version") != NARRATIVE_SCHEMA
        or narratives.get("data_kind") != "real"
        or str(narratives.get("ticker") or "").upper() != ticker.upper()
    ):
        raise ValueError("official narrative receipt identity mismatch")
    narrative_hash = _narrative_receipt_hash(narratives)
    if (
        narratives.get("receipt_hash") != narrative_hash
        or narratives.get("receipt_id") != f"{NARRATIVE_SCHEMA}:{narrative_hash}"
    ):
        raise ValueError("official narrative receipt hash mismatch")
    reports = {
        str(item.get("document_id")): item
        for item in narratives.get("reports", [])
        if isinstance(item, Mapping)
    }
    if not reports or not narratives.get("blocks"):
        raise ValueError("official narrative receipt is empty")
    for index, block in enumerate(narratives["blocks"]):
        report = reports.get(str(block.get("document_id")))
        if (
            report is None
            or str(block.get("raw_hash")) != str(report.get("raw_hash"))
            or str(block.get("source_url")) != str(report.get("source_url"))
            or not _official_url(block.get("source_url"))
            or type(block.get("page_number")) is not int
            or block["page_number"] < 1
        ):
            raise ValueError(f"official narrative block {index} is invalid")
    if (
        financials.get("schema_version") != FINANCIAL_SCHEMA
        or financials.get("data_kind") != "real"
        or str(financials.get("ticker") or "").upper() != ticker.upper()
    ):
        raise ValueError("financial page-evidence identity mismatch")
    expected = canonical_hash(
        {key: item for key, item in financials.items() if key != "receipt_hash"}
    )
    if financials.get("receipt_hash") != expected:
        raise ValueError("financial page-evidence hash mismatch")
    for index, raw in enumerate(financials.get("page_facts", [])):
        fact = FilingNumericFact(**raw)
        fact.validate()
        if (
            fact.ticker.upper() != ticker.upper()
            or fact.statement_scope != "consolidated"
            or not _official_url(fact.source_url)
        ):
            raise ValueError(f"financial page fact {index} is invalid")
    return narratives, financials


def _evidence_id(prefix: str, value: object) -> str:
    return f"{prefix}-{canonical_hash(value)[:10]}"


def _decimal(value: object) -> Decimal | None:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() else None


def _numeric_value(token: str) -> Decimal | None:
    value = _decimal(token.replace(",", "").rstrip("%"))
    if value is None:
        return None
    return value / Decimal("100") if token.endswith("%") else value


def _display_and_comparison(fact: Mapping[str, Any]) -> tuple[str | None, dict | None]:
    value = _decimal(fact.get("value"))
    tokens = NUMBER.findall(str(fact.get("quoted_anchor") or ""))
    if value is None:
        return None, None
    matching = [
        (index, token)
        for index, token in enumerate(tokens)
        if _numeric_value(token) == value
    ]
    if not matching:
        return None, None
    index, display = max(matching, key=lambda item: len(item[1]))
    comparison = None
    if index + 1 < len(tokens):
        prior_display = tokens[index + 1]
        prior = _numeric_value(prior_display)
        if prior not in {None, Decimal("0")}:
            change = ((value - prior) / abs(prior) * Decimal("100")).quantize(
                Decimal("0.1"),
                rounding=ROUND_HALF_UP,
            )
            direction = "增长" if change > 0 else "下滑" if change < 0 else "持平"
            magnitude = f"{abs(change):.1f}%"
            prefix = (
                "较期初"
                if fact.get("metric")
                in {
                    "cash",
                    "current_assets",
                    "total_assets",
                    "short_term_borrowings",
                    "long_term_borrowings",
                    "total_liabilities",
                }
                else "同比"
            )
            comparison = {
                "prior_display": prior_display,
                "direction": direction,
                "magnitude": magnitude,
                "required_phrase": (
                    f"{prefix}{direction}{magnitude}"
                    if direction != "持平"
                    else f"{prefix}持平"
                ),
            }
    return display, comparison


def _sentence_rows(narratives: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for block in narratives.get("blocks", []):
        if (
            block.get("status") != "resolved"
            or not block.get("section_path")
            or not block.get("text")
        ):
            continue
        for raw_sentence in SENTENCE_SPLIT.split(str(block["text"])):
            sentence = " ".join(raw_sentence.split()).strip()
            table_markers = sum(
                marker in sentence
                for marker in (
                    "序号",
                    "项目名称",
                    "合计采购",
                    "公司需遵守",
                    "营业收入 营业成本",
                    "任职人员姓名",
                )
            )
            if (
                len(sentence) < 24
                or len(sentence) > 480
                or sentence in seen
                or sentence.count("|") > 2
                or len(NUMBER.findall(sentence)) > 12
                or table_markers >= 2
            ):
                continue
            seen.add(sentence)
            path = str(block["section_path"])
            self_report = (
                "核心竞争力" in path
                or any(
                    marker in sentence
                    for marker in (
                        "全球领先",
                        "行业领先",
                        "核心技术优势",
                        "竞争优势",
                        "市场地位",
                        "第一",
                    )
                )
            )
            identity = {
                "document_id": block["document_id"],
                "page_number": block["page_number"],
                "text": sentence,
            }
            rows.append(
                {
                    "evidence_id": _evidence_id("N", identity),
                    "kind": "narrative",
                    "text": sentence,
                    "section_path": path,
                    "report_period": block.get("report_period"),
                    "self_report": self_report,
                    "allowed_numeric_displays": list(
                        dict.fromkeys(
                            NUMBER.findall(sentence)
                            + YEAR.findall(str(block.get("report_period") or ""))
                        )
                    ),
                    "citation": {
                        "document_id": block["document_id"],
                        "raw_hash": block["raw_hash"],
                        "page_number": block["page_number"],
                        "quoted_anchor": sentence,
                        "source_url": block["source_url"],
                        "section_path": path,
                    },
                }
            )
    return rows


def _financial_rows(financials: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, int, str, str]] = set()
    sorted_facts = sorted(
        financials.get("page_facts", []),
        key=lambda item: (
            str(item.get("report_period") or ""),
            str(item.get("metric") or ""),
        ),
        reverse=True,
    )
    for raw in sorted_facts:
        period = str(raw.get("report_period") or "")
        if period in {"", "unknown", "unresolved"}:
            continue
        display, comparison = _display_and_comparison(raw)
        if display is None:
            continue
        identity = (
            str(raw["document_id"]),
            int(raw["page_number"]),
            str(raw["metric"]),
            str(raw["quoted_anchor"]),
        )
        if identity in seen:
            continue
        seen.add(identity)
        allowed = [display]
        period_years = YEAR.findall(period)
        allowed.extend(period_years)
        if comparison is not None:
            allowed.extend(
                (
                    comparison["prior_display"],
                    comparison["magnitude"],
                )
            )
            if period_years:
                allowed.append(str(int(period_years[0]) - 1))
        rows.append(
            {
                "evidence_id": _evidence_id("P", identity),
                "kind": "financial",
                "metric": raw["metric"],
                "period": period,
                "display": display,
                "unit": raw["unit"],
                "currency": raw["currency"],
                "comparison": comparison,
                "allowed_numeric_displays": list(dict.fromkeys(allowed)),
                "citation": {
                    "document_id": raw["document_id"],
                    "raw_hash": raw["raw_hash"],
                    "page_number": raw["page_number"],
                    "quoted_anchor": raw["quoted_anchor"],
                    "quoted_label": raw["quoted_label"],
                    "source_url": raw["source_url"],
                    "statement_scope": raw["statement_scope"],
                },
            }
        )
    return rows


def _score_narrative(
    row: Mapping[str, Any],
    *,
    paths: Iterable[str],
    keywords: Iterable[str],
) -> int:
    path = str(row.get("section_path") or "")
    text = str(row.get("text") or "")
    years = YEAR.findall(str(row.get("report_period") or ""))
    freshness = max(0, min(5, int(years[0]) - 2021)) if years else 0
    extraction_noise = (
        8 * ("公司需遵守" in text)
        + 4 * (text.count("公司") > 4)
        + 4 * ("序号" in text or "报告期内上市公司" in text)
    )
    return (
        sum(4 for term in paths if term in path)
        + sum(2 for term in keywords if term in text)
        + freshness
        + (1 if len(text) <= 220 else 0)
        - (4 if len(text) > 300 else 0)
        - min(len(NUMBER.findall(text)) // 4, 4)
        - extraction_noise
    )


def build_evidence_registry(
    narratives: Mapping[str, Any],
    financials: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    rows = _sentence_rows(narratives) + _financial_rows(financials)
    return {str(item["evidence_id"]): item for item in rows}


def select_section_evidence(
    registry: Mapping[str, Mapping[str, Any]],
    *,
    section_id: str,
) -> list[dict[str, Any]]:
    rules = SECTION_EVIDENCE_RULES[section_id]
    narratives = [
        (item, _score_narrative(item, paths=rules["paths"], keywords=rules["keywords"]))
        for item in registry.values()
        if item.get("kind") == "narrative"
        and not (
            section_id
            in {
                "one_line_positioning",
                "business_model_and_business_lines",
                "financial_and_operating_time_series",
            }
            and item.get("self_report")
        )
    ]
    selected_narratives = [
        dict(item)
        for item, score in sorted(
            narratives,
            key=lambda pair: (
                pair[1],
                str(pair[0].get("report_period") or ""),
                -int(pair[0]["citation"]["page_number"]),
                pair[0]["evidence_id"],
            ),
            reverse=True,
        )
        if score > 0
    ][: int(rules["narratives"])]
    financial_candidates = [
        dict(item)
        for item in registry.values()
        if item.get("kind") == "financial"
        and item.get("metric") in rules["metrics"]
    ]
    financial_candidates.sort(
        key=lambda item: (
            str(item.get("period") or ""),
            str(item.get("metric") or ""),
            item["evidence_id"],
        ),
        reverse=True,
    )
    selected_financials = []
    selected_metrics: set[str] = set()
    selected_metric_periods: set[tuple[str, str]] = set()
    financial_limit = int(rules["financials"])
    for item in financial_candidates if financial_limit > 0 else ():
        metric = str(item.get("metric") or "")
        period = str(item.get("period") or "")
        if section_id == "financial_and_operating_time_series":
            identity = (metric, period)
            if identity in selected_metric_periods:
                continue
            selected_metric_periods.add(identity)
        else:
            if metric in selected_metrics:
                continue
        selected_financials.append(item)
        selected_metrics.add(metric)
        if len(selected_financials) >= financial_limit:
            break
    selected = selected_narratives + selected_financials
    if not selected:
        raise ValueError(f"{section_id} has no page-bound evidence")
    # The synthesis chapter is deliberately fed a compact, high-signal slice;
    # sending every narrative paragraph makes the structured response exceed
    # the provider's completion envelope without improving traceability.
    if section_id == "research_conclusion_and_open_questions":
        selected = selected[:8]
    return selected
