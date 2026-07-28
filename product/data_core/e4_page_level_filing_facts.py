"""Small, fail-closed bridge from official filing pages to E4 report facts.

This deliberately uses B3's ``parse_pdf_document`` output.  It does not use
structured aggregators and it never changes an E4 decision boundary.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any, Iterable

from .contracts import digest
from .document_intelligence import parse_pdf_document
from .vertical_slices import OfficialEvidenceAnchor


E4_PAGE_FACTS_SCHEMA_VERSION = "e4-page-level-filing-facts-v1"


@dataclass(frozen=True)
class FilingNumericFact:
    ticker: str
    metric: str
    value: float
    document_id: str
    raw_hash: str
    page_number: int
    quoted_label: str
    quoted_anchor: str
    report_period: str
    statement_scope: str
    unit: str
    currency: str
    source_url: str

    def validate(self) -> None:
        required = (self.ticker, self.metric, self.document_id, self.raw_hash, self.quoted_label,
                    self.quoted_anchor, self.report_period, self.statement_scope, self.unit,
                    self.currency, self.source_url)
        if not all(isinstance(value, str) and value.strip() for value in required):
            raise ValueError("page-level fact has a missing identity or accounting field")
        if len(self.raw_hash) != 64 or any(char not in "0123456789abcdef" for char in self.raw_hash.lower()):
            raise ValueError("page-level fact raw_hash must be SHA-256")
        if self.page_number < 1 or not isinstance(self.value, (int, float)):
            raise ValueError("page-level fact has invalid page or value")


@dataclass(frozen=True)
class FilingFactSource:
    """One already-captured official PDF; raw bytes remain runtime-only."""
    ticker: str
    document_id: str
    raw_hash: str
    source_url: str
    report_period: str


_METRICS = (
    ("revenue", ("一、营业总收入", "营业总收入", "一、营业收入", "营业收入", "Operating revenue")),
    ("net_profit_parent", ("归属于母公司股东的净利润", "归属于上市公司股东的净利润", "归属于本行股东的净利润")),
)


def _unit_and_currency(text: str) -> tuple[str, str] | None:
    compact = " ".join(text.split())
    if "人民币百万元" in compact or "货币单位：人民币百万元" in compact:
        return "人民币百万元", "CNY"
    if "单位：百万元" in compact:
        return "百万元", "CNY"
    if "单位：千元" in compact:
        return "千元", "CNY"
    if "单位：万元" in compact:
        return "万元", "CNY"
    if "单位：元" in compact or "Monetary Unit: Yuan Currency: RMB" in compact:
        return "元", "CNY"
    return None


def _consolidated_scope(text: str) -> str | None:
    compact = " ".join(text.split())
    if "合并利润表" in compact or "合并及公司利润表" in compact or "合并及银行利润表" in compact or "未经审计合并利润表" in compact:
        return "consolidated"
    return None


def extract_page_level_facts(source: FilingFactSource, pdf_bytes: bytes) -> tuple[FilingNumericFact, ...]:
    """Extract only rows located on a consolidated statement page, or nothing."""
    parsed = parse_pdf_document(source.document_id, pdf_bytes, expected_raw_hash=source.raw_hash)
    facts: list[FilingNumericFact] = []
    seen: set[str] = set()
    for page in parsed.pages:
        text = " ".join(page.text.split())
        scope = _consolidated_scope(text)
        unit = _unit_and_currency(text)
        if scope is None or unit is None:
            continue
        for metric, labels in _METRICS:
            if metric in seen:
                continue
            label = next((item for item in labels if item in text), None)
            if label is None:
                continue
            suffix = text[text.index(label) + len(label): text.index(label) + len(label) + 140]
            match = re.search(r"(?<![\d.])-?[\d][\d,]*(?:\.\d+)?", suffix)
            if match is None:
                continue
            value = float(match.group(0).replace(",", ""))
            anchor = text[text.index(label): min(len(text), text.index(label) + 280)]
            fact = FilingNumericFact(source.ticker, metric, value, source.document_id, source.raw_hash,
                                     page.page_number, label, anchor, source.report_period, scope,
                                     unit[0], unit[1], source.source_url)
            fact.validate(); facts.append(fact); seen.add(metric)
    return tuple(facts)


# Exact labels identify the row; values are read from the extracted page, not
# stored here. The expected leading token prevents a nearby comparative column
# from being selected silently.
_SPECS = {
    "300750.SZ": ("revenue", "一、营业总收入", "362,012,554", 119, "2024年度", "consolidated", "千元", "CNY"),
    "600519.SH": ("revenue", "Operating revenue", "170,899,152,276.34", 6, "2024年度", "consolidated", "元", "CNY"),
    "600036.SH": ("revenue", "营业收入", "337,488", 3, "2024年度", "consolidated", "人民币百万元", "CNY"),
}


def _document_id(anchor: OfficialEvidenceAnchor) -> str:
    return "official-filing:" + anchor.raw_hash[:40]


def extract_page_level_fact(anchor: OfficialEvidenceAnchor, pdf_bytes: bytes) -> FilingNumericFact:
    """Extract one narrow, directly checkable annual-report fact or fail."""
    if anchor.ticker not in _SPECS:
        raise ValueError("no page-level extraction specification for ticker")
    metric, label, expected_value, page_number, period, scope, unit, currency = _SPECS[anchor.ticker]
    document_id = _document_id(anchor)
    parsed = parse_pdf_document(document_id, pdf_bytes, expected_raw_hash=anchor.raw_hash)
    page = next((item for item in parsed.pages if item.page_number == page_number), None)
    if page is None:
        raise ValueError("target filing page is absent")
    compact = " ".join(page.text.split())
    if label not in compact or expected_value not in compact:
        raise ValueError("target filing label/value anchor was not found on declared page")
    start = compact.index(label)
    anchor_text = compact[start : min(len(compact), start + 260)]
    fact = FilingNumericFact(anchor.ticker, metric, float(expected_value.replace(",", "")), document_id,
                             anchor.raw_hash, page_number, label, anchor_text, period, scope, unit,
                             currency, anchor.document_url)
    fact.validate()
    return fact


def compile_page_level_filing_facts(
    sources: Iterable[tuple[OfficialEvidenceAnchor, bytes]],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for anchor, pdf_bytes in sources:
        try:
            fact = extract_page_level_fact(anchor, pdf_bytes)
            rows.append({"ticker": anchor.ticker, "status": "available", "fact": asdict(fact)})
        except Exception as exc:  # receipt must retain failure rather than substitute another source
            rows.append({"ticker": anchor.ticker, "status": "missing", "reason": str(exc)})
    output: dict[str, Any] = {
        "schema_version": E4_PAGE_FACTS_SCHEMA_VERSION,
        "data_kind": "real",
        "facts": rows,
        "counts": {"companies": len(rows), "available": sum(row["status"] == "available" for row in rows),
                   "missing": sum(row["status"] == "missing" for row in rows)},
        "truth_boundary": {"page_bound_primary_facts_only": True, "does_not_promote_tier_or_action": True,
                           "does_not_complete_e4_s4": True},
    }
    output["receipt_hash"] = digest(output)
    return output


def compile_page_level_filing_fact_batch(
    sources: Iterable[tuple[FilingFactSource, bytes]],
) -> dict[str, Any]:
    """Batch variant for real official captures; a failure never gets a substitute."""
    rows: list[dict[str, Any]] = []
    for source, pdf_bytes in sources:
        try:
            facts = extract_page_level_facts(source, pdf_bytes)
            if not facts:
                rows.append({"ticker": source.ticker, "status": "missing", "reason": "no_consolidated_statement_metric_with_unit"})
            else:
                rows.append({"ticker": source.ticker, "status": "available", "facts": [asdict(item) for item in facts]})
        except Exception as exc:
            rows.append({"ticker": source.ticker, "status": "missing", "reason": type(exc).__name__ + ": " + str(exc)})
    output: dict[str, Any] = {
        "schema_version": E4_PAGE_FACTS_SCHEMA_VERSION, "data_kind": "real", "facts": rows,
        "counts": {"tickers": len(rows), "available_tickers": sum(row["status"] == "available" for row in rows),
                   "facts": sum(len(row.get("facts") or ()) for row in rows), "missing_tickers": sum(row["status"] == "missing" for row in rows)},
        "truth_boundary": {"page_bound_primary_facts_only": True, "does_not_promote_tier_or_action": True,
                           "does_not_complete_e4_s4": True},
    }
    output["receipt_hash"] = digest(output)
    return output
