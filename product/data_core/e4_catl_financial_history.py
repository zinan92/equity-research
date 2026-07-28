"""Official-PDF-only financial history for the CATL vertical validation.

This is deliberately a narrow extractor: a value is admitted only when its
label, page, PDF hash, accounting unit and consolidated statement scope are
all available from one CNINFO PDF page.  It does not substitute vendor data.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from typing import Iterable

from .document_intelligence import parse_pdf_document
from .official_filings import default_http_transport

CATL_TICKER = "300750.SZ"


@dataclass(frozen=True)
class OfficialReport:
    period: str
    document_id: str
    source_url: str


# IDs and URLs are declared by CNINFO's annual/quarterly-report index.  Raw
# PDF bytes and their hashes are acquired at runtime; no PDF is committed.
CATL_REPORTS: tuple[OfficialReport, ...] = (
    OfficialReport("2021FY", "1213027750", "https://static.cninfo.com.cn/finalpage/2022-04-22/1213027750.PDF"),
    OfficialReport("2022FY", "1216084559", "https://static.cninfo.com.cn/finalpage/2023-03-10/1216084559.PDF"),
    OfficialReport("2023FY", "1219313047", "https://static.cninfo.com.cn/finalpage/2024-03-16/1219313047.PDF"),
    OfficialReport("2024FY", "1222806982", "https://static.cninfo.com.cn/finalpage/2025-03-15/1222806982.PDF"),
    OfficialReport("2025FY", "1225002214", "https://static.cninfo.com.cn/finalpage/2026-03-10/1225002214.PDF"),
    OfficialReport("2025Q3", "1224721971", "https://static.cninfo.com.cn/finalpage/2025-10-21/1224721971.PDF"),
    OfficialReport("2026Q1", "1225107946", "https://static.cninfo.com.cn/finalpage/2026-04-16/1225107946.PDF"),
    OfficialReport("2026H1", "1225441586", "https://static.cninfo.com.cn/finalpage/2026-07-25/1225441586.PDF"),
)


@dataclass(frozen=True)
class OfficialFinancialFact:
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


_METRICS = {
    "revenue": ("营业总收入",),
    "operating_cost": ("营业成本",),
    "net_profit_parent": ("归属于母公司股东的净利润", "归属于母公司所有者的净利润"),
    "operating_cash_flow": ("经营活动产生的现金流量净额",),
    "total_assets": ("资产总计",),
    "total_liabilities": ("负债合计",),
    "parent_equity": ("归属于母公司所有者权益合计",),
    "total_equity": ("所有者权益合计",),
    "operating_profit": ("营业利润",),
    "total_profit": ("利润总额",),
    "income_tax_expense": ("所得税费用",),
    "capital_expenditure": ("购建固定资产、无形资产和其他长期资产支付的现金",),
    "cash": ("货币资金",),
    "current_assets": ("流动资产合计",),
    "current_liabilities": ("流动负债合计",),
    "shares_outstanding": ("股本",),
}


def _unit(text: str) -> tuple[str, str] | None:
    compact = " ".join(text.split())
    if "单位：千元" in compact or "单位为：千元" in compact:
        return "千元", "CNY"
    if "单位：万元" in compact or "单位为：万元" in compact:
        return "万元", "CNY"
    if "单位：人民币元" in compact or "金额单位：元" in compact:
        return "元", "CNY"
    if "单位：元" in compact:
        return "元", "CNY"
    return None


def _statement_scope(text: str) -> str | None:
    compact = " ".join(text.split())
    if any(value in compact for value in ("合并资产负债表", "合并利润表", "合并现金流量表")):
        return "consolidated"
    if any(value in compact for value in ("母公司资产负债表", "母公司利润表", "母公司现金流量表")):
        return "parent"
    return None


def _number_after(label: str, line: str) -> float | None:
    suffix = line[line.index(label) + len(label):]
    match = re.search(r"(?<![\d.])-?[\d][\d,]*(?:\.\d+)?", suffix)
    return float(match.group(0).replace(",", "")) if match else None


def extract_report_facts(report: OfficialReport, pdf_bytes: bytes) -> tuple[OfficialFinancialFact, ...]:
    raw_hash = hashlib.sha256(pdf_bytes).hexdigest()
    parsed = parse_pdf_document(report.document_id, pdf_bytes, expected_raw_hash=raw_hash)
    facts: list[OfficialFinancialFact] = []
    found: set[str] = set()
    active_scope: str | None = None
    active_unit: tuple[str, str] | None = None
    for page in parsed.pages:
        active_scope = _statement_scope(page.text) or active_scope
        active_unit = _unit(page.text) or active_unit
        if active_scope != "consolidated" or active_unit is None:
            continue
        for line in page.text.splitlines():
            compact = " ".join(line.split())
            for metric, labels in _METRICS.items():
                if metric in found:
                    continue
                label = next((value for value in labels if value in compact), None)
                if label is None:
                    continue
                # Avoid accepting subtotal rows when the contract asks for the
                # consolidated total, or the parent-equity row for total equity.
                if metric == "total_liabilities" and not compact.startswith("负债合计"):
                    continue
                if metric == "total_equity" and not compact.startswith("所有者权益合计"):
                    continue
                value = _number_after(label, compact)
                if value is None:
                    continue
                facts.append(OfficialFinancialFact(
                    CATL_TICKER, metric, value, report.document_id, raw_hash,
                    page.page_number, label, compact[:420], report.period,
                    "consolidated", active_unit[0], active_unit[1], report.source_url,
                ))
                found.add(metric)
    return tuple(facts)


def capture_catl_history(reports: Iterable[OfficialReport] = CATL_REPORTS) -> dict[str, object]:
    """Fetch only declared CNINFO PDFs and retain every missing metric explicitly."""
    rows = []
    for report in reports:
        response = default_http_transport(report.source_url, {"Accept": "application/pdf"})
        if response.status_code != 200 or not response.body.startswith(b"%PDF"):
            rows.append({"period": report.period, "status": "missing", "reason": "official_pdf_unavailable"})
            continue
        facts = extract_report_facts(report, response.body)
        present = {fact.metric for fact in facts}
        rows.append({
            "period": report.period, "status": "available", "facts": [asdict(fact) for fact in facts],
            "missing_metrics": sorted(set(_METRICS).difference(present)),
        })
    return {
        "schema_version": "e4-catl-official-financial-history-v1", "data_kind": "real",
        "ticker": CATL_TICKER, "reports": rows,
        "truth_boundary": {"official_cninfo_pdf_only": True, "page_bound_only": True,
                           "does_not_complete_valuation_or_decision": True},
    }
