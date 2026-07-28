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
    "depreciation_fixed_assets": ("固定资产折旧、油气资产折耗、生产性生物资产折旧", "固定资产折旧"),
    "amortization_intangible": ("无形资产摊销",),
    "inventory_cashflow_change": ("存货的减少（增加以“－”号填列）",),
    "receivables_cashflow_change": ("经营性应收项目的减少（增加以“－”号填列）",),
    "payables_cashflow_change": ("经营性应付项目的增加（减少以“－”号填列）",),
    "short_term_borrowings": ("短期借款",),
    "long_term_borrowings": ("长期借款",),
    "share_capital_amount": ("股本",),
    "capital_expenditure": ("购建固定资产、无形资产和其他长期资产支付的现金",),
    "cash": ("货币资金",),
    "current_assets": ("流动资产合计",),
    "current_liabilities": ("流动负债合计",),
    "shares_outstanding": ("股本",),
}

_SHARE_COUNT_LABEL = "公司现有总股本"


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
    compact = "".join(text.split())
    if "现金流量表补充资料" in compact:
        return "consolidated_cashflow_supplement"
    if any(value in compact for value in ("合并资产负债表", "合并利润表", "合并现金流量表")):
        return "consolidated"
    if any(value in compact for value in ("母公司资产负债表", "母公司利润表", "母公司现金流量表")):
        return "parent"
    return None


def _number_after(label: str, line: str) -> float | None:
    suffix = line[line.index(label) + len(label):]
    match = re.search(r"(?<![\d.])-?[\d][\d,]*(?:\.\d+)?", suffix)
    return float(match.group(0).replace(",", "")) if match else None


def _statement_rows(text: str) -> tuple[str, ...]:
    """Preserve normal rows and deterministically reassemble a wrapped row.

    The only accepted wrapped shape is label-prefix -> numeric row ->
    label-suffix on contiguous lines.  Anything else remains separate and
    therefore cannot be admitted accidentally.
    """
    lines = [" ".join(line.split()) for line in text.splitlines() if line.strip()]
    rows = list(lines)
    for index in range(len(lines) - 2):
        left, numbers, right = lines[index:index + 3]
        if not re.search(r"[\u4e00-\u9fff]", left) or not re.fullmatch(r"[-\d,\.\s]+", numbers):
            continue
        if not re.search(r"[\u4e00-\u9fff]", right):
            continue
        rows.append(left + right + " " + numbers)
    for index in range(len(lines) - 1):
        left, right = lines[index:index + 2]
        match = re.match(r"^(.*[\u4e00-\u9fff][^0-9]*?)\s+([\d,.\s-]+)$", left)
        if not match or not re.search(r"[\u4e00-\u9fff]", right):
            continue
        # CNINFO's common wrapped-table form is label-prefix + numbers,
        # followed by the remaining label characters on the next line.
        rows.append(match.group(1) + right + " " + match.group(2))
    return tuple(rows)


def _page_lines(text: str) -> tuple[str, ...]:
    return tuple(" ".join(line.split()) for line in text.splitlines() if line.strip())


def _rows_with_context(
    page_text: str,
    *,
    active_scope: str | None,
    active_unit: tuple[str, str] | None,
) -> tuple[tuple[str, str | None, tuple[str, str] | None], ...]:
    """Return page rows with the statement context active at that exact row.

    Annual-report tables can end on the next page after their title, and a
    page can contain the tail of a consolidated statement followed by the
    title and first rows of a parent-company statement.  Context must therefore
    move linearly, not be inferred from the page as a whole.
    """
    rows: list[tuple[str, str | None, tuple[str, str] | None]] = []
    lines = _page_lines(page_text)
    for index, line in enumerate(lines):
        active_scope = _statement_scope(line) or active_scope
        active_unit = _unit(line) or active_unit
        rows.append((line, active_scope, active_unit))
        if index + 2 < len(lines):
            left, numbers, right = lines[index:index + 3]
            if (re.search(r"[\u4e00-\u9fff]", left)
                    and re.fullmatch(r"[-\d,\.\s]+", numbers)
                    and re.search(r"[\u4e00-\u9fff]", right)):
                rows.append((left + right + " " + numbers, active_scope, active_unit))
        if index + 1 < len(lines):
            left, right = lines[index:index + 2]
            match = re.match(r"^(.*[\u4e00-\u9fff][^0-9]*?)\s+([\d,.\s-]+)$", left)
            if match and re.search(r"[\u4e00-\u9fff]", right):
                rows.append((match.group(1) + right + " " + match.group(2), active_scope, active_unit))
    return tuple(rows)


def extract_report_facts(report: OfficialReport, pdf_bytes: bytes) -> tuple[OfficialFinancialFact, ...]:
    raw_hash = hashlib.sha256(pdf_bytes).hexdigest()
    parsed = parse_pdf_document(report.document_id, pdf_bytes, expected_raw_hash=raw_hash)
    facts: list[OfficialFinancialFact] = []
    found: set[str] = set()
    active_scope: str | None = None
    active_unit: tuple[str, str] | None = None
    for page in parsed.pages:
        rows = _rows_with_context(page.text, active_scope=active_scope, active_unit=active_unit)
        if rows:
            _, active_scope, active_unit = rows[-1]
        for compact, row_scope, row_unit in rows:
            if row_scope not in {"consolidated", "consolidated_cashflow_supplement"} or row_unit is None:
                continue
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
                    row_scope, row_unit[0], row_unit[1], report.source_url,
                ))
                found.add(metric)
        # Share count is not a balance-sheet amount.  It is disclosed in the
        # distribution narrative and has its own unit/scope so it cannot be
        # confused with the similarly named monetary share-capital row.
        if "shares_outstanding" not in found:
            compact_page = " ".join(page.text.split())
            if _SHARE_COUNT_LABEL in compact_page:
                value = _number_after(_SHARE_COUNT_LABEL, compact_page)
                if value is not None:
                    facts.append(OfficialFinancialFact(
                        CATL_TICKER, "shares_outstanding", value, report.document_id, raw_hash,
                        page.page_number, _SHARE_COUNT_LABEL, compact_page[max(0, compact_page.index(_SHARE_COUNT_LABEL) - 80):compact_page.index(_SHARE_COUNT_LABEL) + 260],
                        report.period, "share_count_disclosure", "shares", "N/A", report.source_url,
                    ))
                    found.add("shares_outstanding")
    return tuple(facts)


def _missing_metric_records(
    report: OfficialReport, pdf_bytes: bytes, present: set[str],
) -> list[dict[str, str]]:
    """Keep a bounded raw excerpt with every negative extraction conclusion."""
    raw_hash = hashlib.sha256(pdf_bytes).hexdigest()
    parsed = parse_pdf_document(report.document_id, pdf_bytes, expected_raw_hash=raw_hash)
    corpus = "\n".join(page.text for page in parsed.pages)
    records = []
    for metric, labels in sorted(_METRICS.items()):
        if metric in present:
            continue
        label = labels[0]
        needle = label[: max(4, len(label) // 2)]
        position = corpus.find(needle)
        excerpt = corpus[max(0, position - 160): position + 360] if position >= 0 else corpus[:320]
        records.append({
            "metric": metric,
            "reason": "no_page_bound_consolidated_row",
            "raw_text_excerpt": " ".join(excerpt.split())[:520],
        })
    return records


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
            "missing_metrics": _missing_metric_records(report, response.body, present),
        })
    return {
        "schema_version": "e4-catl-official-financial-history-v1", "data_kind": "real",
        "ticker": CATL_TICKER, "reports": rows,
        "truth_boundary": {"official_cninfo_pdf_only": True, "page_bound_only": True,
                           "does_not_complete_valuation_or_decision": True},
    }
