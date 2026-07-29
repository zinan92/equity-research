"""Official-PDF-only financial history for the CATL vertical validation.

This is deliberately a narrow extractor: a value is admitted only when its
label, page, PDF hash, accounting unit and consolidated statement scope are
all available from one CNINFO PDF page.  It does not substitute vendor data.
"""
from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from .document_intelligence import DocumentPage, ParserConfig, parse_pdf_document
from .official_filings import default_http_transport

CATL_TICKER = "300750.SZ"


@dataclass(frozen=True)
class OfficialReport:
    period: str
    document_id: str
    source_url: str
    ticker: str = CATL_TICKER


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
    column_identity: str = "unknown"
    column_header_excerpt: str = ""
    unit_source_excerpt: str = ""
    validation_status: str = "unvalidated"
    as_of_date: str | None = None


_METRICS = {
    "revenue": ("营业总收入", "营业收入", "Revenue"),
    "operating_cost": ("营业成本",),
    "net_profit_parent": ("归属于母公司股东的净利润", "归属于母公司所有者的净利润", "归属于本行股东的净利润"),
    "operating_cash_flow": ("经营活动产生的现金流量净额",),
    "total_assets": ("资产总计", "资产合计", "Total assets"),
    "total_liabilities": ("负债合计", "Total liabilities"),
    "parent_equity": ("归属于母公司所有者权益合计", "归属于本行股东权益合计", "Total owners' equity attributable to the parent company"),
    "total_equity": ("所有者权益合计", "Total owners' equity"),
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
}

_SHARE_COUNT_LABEL = "公司现有总股本"


def _unit(text: str) -> tuple[str, str] | None:
    compact = " ".join(text.split())
    if "人民币百万元" in compact or "货币单位：人民币百万元" in compact:
        return "人民币百万元", "CNY"
    if "单位：百万元" in compact:
        return "百万元", "CNY"
    if "单位：千元" in compact or "单位为：千元" in compact:
        return "千元", "CNY"
    if "单位：万元" in compact or "单位为：万元" in compact:
        return "万元", "CNY"
    if "单位：人民币元" in compact or "金额单位：元" in compact:
        return "元", "CNY"
    if "单位：元" in compact:
        return "元", "CNY"
    if "Unit: RMB" in compact or "unit in the notes to financial statements is:RMB" in compact:
        return "元", "CNY"
    return None


def _column_identity(text: str) -> tuple[str, str] | None:
    """Recognize a table header; never infer first-column semantics by order."""
    compact = " ".join(text.split())
    if "本期发生额" in compact and "上期发生额" in compact:
        return "current_period", compact[:240]
    if "期末余额" in compact and "期初余额" in compact:
        return "period_end", compact[:240]
    if "本期金额" in compact and "上期金额" in compact:
        return "current_period", compact[:240]
    if len(re.findall(r"20\d{2}年度", compact)) >= 2:
        return "current_period", compact[:240]
    if len(re.findall(r"20\d{2}年", compact)) >= 2:
        return "current_period", compact[:240]
    if "Closing balance" in compact and "Opening balance" in compact:
        return "period_end", compact[:240]
    return None


def _statement_scope(text: str) -> str | None:
    compact = "".join(text.split())
    if "现金流量表补充资料" in compact:
        return "consolidated_cashflow_supplement"
    if any(value in compact for value in ("合并资产负债表", "合并利润表", "合并现金流量表", "合并及银行利润表", "合并及本行利润表")):
        return "consolidated"
    if any(value in compact for value in ("Consolidatedbalancesheet", "Consolidatedincomestatement", "Consolidatedcashflowstatement")):
        return "consolidated"
    if any(value in compact for value in ("母公司资产负债表", "母公司利润表", "母公司现金流量表")):
        return "parent"
    return None


def _number_after(label: str, line: str) -> float | None:
    suffix = line[line.index(label) + len(label):]
    match = re.search(r"(?<![\d.])-?[\d][\d,]*(?:\.\d+)?", suffix)
    return float(match.group(0).replace(",", "")) if match else None


def _numbers_after(label: str, line: str) -> tuple[float, ...]:
    suffix = line[line.index(label) + len(label):]
    return tuple(float(item.replace(",", "")) for item in re.findall(r"(?<![\d.])-?\d[\d,]*(?:\.\d+)?", suffix))


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


def _native_layout_pages(document_id: str, raw_hash: str, pdf_bytes: bytes) -> tuple[DocumentPage, ...]:
    """Use Poppler's native layout text only when pypdf yields no admissible fact.

    This is not OCR and does not invent coordinates: form-feed boundaries from
    the official PDF become one-based document pages.  It handles a known
    rotated-font layout where pypdf returns no usable CJK table text while
    `pdftotext -layout` exposes the original text layer.
    """
    executable = shutil.which("pdftotext")
    if not executable:
        return ()
    with tempfile.TemporaryDirectory(prefix="park-native-layout-") as directory:
        pdf_path = Path(directory) / "source.pdf"
        text_path = Path(directory) / "source.txt"
        pdf_path.write_bytes(pdf_bytes)
        try:
            completed = subprocess.run(
                [executable, "-layout", str(pdf_path), str(text_path)],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return ()
        if completed.returncode != 0 or not text_path.exists():
            return ()
        text = text_path.read_text(encoding="utf-8", errors="replace")
    return tuple(
        DocumentPage(
            document_id=document_id,
            page_number=index,
            raw_hash=raw_hash,
            parser_version="native-layout-fallback-v1",
            text=page_text.strip(),
            text_hash=hashlib.sha256(page_text.strip().encode("utf-8")).hexdigest(),
            extraction_method="native_layout_fallback",
            table_status="possible_unlocated",
        )
        for index, page_text in enumerate(text.split("\f"), start=1)
        if page_text.strip()
    )


def _rows_with_context(
    page_text: str,
    *,
    active_scope: str | None,
    active_unit: tuple[str, str] | None,
    active_column: str = "unknown",
    active_column_excerpt: str = "",
) -> tuple[tuple[str, str | None, tuple[str, str] | None, str, str, str], ...]:
    """Return page rows with the statement context active at that exact row.

    Annual-report tables can end on the next page after their title, and a
    page can contain the tail of a consolidated statement followed by the
    title and first rows of a parent-company statement.  Context must therefore
    move linearly, not be inferred from the page as a whole.
    """
    rows: list[tuple[str, str | None, tuple[str, str] | None, str, str, str]] = []
    lines = _page_lines(page_text)
    column_excerpt = active_column_excerpt; unit_excerpt = ""
    for index, line in enumerate(lines):
        active_scope = _statement_scope(line) or active_scope
        if _unit(line): active_unit = _unit(line); unit_excerpt = line[:240]
        if _column_identity(line): active_column, column_excerpt = _column_identity(line)
        rows.append((line, active_scope, active_unit, active_column, column_excerpt, unit_excerpt))
        if index + 2 < len(lines):
            left, numbers, right = lines[index:index + 3]
            if (re.search(r"[\u4e00-\u9fff]", left)
                    and re.fullmatch(r"[-\d,\.\s]+", numbers)
                    and re.search(r"[\u4e00-\u9fff]", right)):
                rows.append((left + right + " " + numbers, active_scope, active_unit, active_column, column_excerpt, unit_excerpt))
        if index + 1 < len(lines):
            left, right = lines[index:index + 2]
            match = re.match(r"^(.*[\u4e00-\u9fff][^0-9]*?)\s+([\d,.\s-]+)$", left)
            if match and re.search(r"[\u4e00-\u9fff]", right):
                rows.append((match.group(1) + right + " " + match.group(2), active_scope, active_unit, active_column, column_excerpt, unit_excerpt))
    return tuple(rows)


def extract_report_facts(
    report: OfficialReport,
    pdf_bytes: bytes,
    *,
    _pages: tuple[DocumentPage, ...] | None = None,
) -> tuple[OfficialFinancialFact, ...]:
    raw_hash = hashlib.sha256(pdf_bytes).hexdigest()
    # This batch needs native page-bound tables.  Suppress automatic document-
    # wide OCR here: a single scanned appendix otherwise makes an otherwise
    # native annual report spend minutes OCRing every page.  Entirely scanned
    # reports remain explicit missing evidence for the separate OCR path.
    # Keep any native page text, even when it is short or rotated.  Passing an
    # empty OCR callback would erase such text; fully image-only pages remain
    # explicitly unreadable here and are reserved for the separate OCR path.
    using_layout_fallback = _pages is not None
    if _pages is None:
        parsed = parse_pdf_document(
            report.document_id,
            pdf_bytes,
            expected_raw_hash=raw_hash,
            config=ParserConfig(native_text_min_chars=0),
            ocr_backend=lambda _bytes, _page: "",
        )
        pages = parsed.pages
    else:
        pages = _pages
    facts: list[OfficialFinancialFact] = []
    found: set[str] = set()
    active_scope: str | None = None
    active_unit: tuple[str, str] | None = None
    active_column = "unknown"
    active_column_excerpt = ""
    for page in pages:
        rows = _rows_with_context(
            page.text,
            active_scope=active_scope,
            active_unit=active_unit,
            active_column=active_column,
            active_column_excerpt=active_column_excerpt,
        )
        if rows:
            _, active_scope, active_unit, active_column, active_column_excerpt, _ = rows[-1]
        for compact, row_scope, row_unit, column_identity, column_header, unit_source in rows:
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
                if metric == "total_assets" and not compact.startswith(("资产总计", "资产合计", "Total assets")):
                    continue
                if metric == "total_liabilities" and not compact.startswith("负债合计"):
                    continue
                if metric == "total_equity" and not compact.startswith("所有者权益合计"):
                    continue
                values = _numbers_after(label, compact)
                if not values:
                    continue
                suffix = compact[compact.index(label) + len(label):]
                # Chinese annual reports commonly place a note reference such
                # as ``六、22`` between the row label and the two values.
                # It is table metadata, never a financial amount.
                if re.match(r"\s*[一二三四五六七八九十]+、\d+\s+", suffix) and len(values) >= 3:
                    values = values[1:]
                # Some bank statements place the note reference immediately
                # after ``股本`` (for example ``股本 35 25,220 25,220``).  A
                # note number is not a monetary share-capital value.
                if metric == "share_capital_amount" and len(values) >= 3 and values[0] < 1_000 <= values[1]:
                    values = values[1:]
                selected_values = values[:2] if column_identity != "unknown" else values[:1]
                for index, value in enumerate(selected_values):
                    identity = column_identity if index == 0 else {
                        "current_period": "previous_period",
                        "period_end": "period_begin",
                    }.get(column_identity, "unknown")
                    period = report.period if identity not in {"previous_period", "period_begin"} else str(int(report.period[:4]) - 1) + report.period[4:]
                    facts.append(OfficialFinancialFact(
                        report.ticker, metric, value, report.document_id, raw_hash,
                        page.page_number, label, compact[:420], period,
                        row_scope, row_unit[0], row_unit[1], report.source_url,
                        identity, column_header, unit_source,
                        "column_identity_unresolved" if identity == "unknown" else "pending_magnitude_validation",
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
                        report.ticker, "shares_outstanding", value, report.document_id, raw_hash,
                        page.page_number, _SHARE_COUNT_LABEL, compact_page[max(0, compact_page.index(_SHARE_COUNT_LABEL) - 80):compact_page.index(_SHARE_COUNT_LABEL) + 260],
                        report.period, "share_count_disclosure", "股", "N/A", report.source_url,
                    ))
                    found.add("shares_outstanding")
    # A money-denominated balance-sheet row can never stand in for shares.
    # Keep this invariant at the extractor boundary, before valuation inputs.
    for fact in facts:
        if fact.metric == "shares_outstanding" and fact.unit != "股":
            raise ValueError("shares_outstanding must use the independent shares unit")
    if facts or using_layout_fallback:
        return tuple(facts)
    fallback_pages = _native_layout_pages(report.document_id, raw_hash, pdf_bytes)
    return extract_report_facts(report, pdf_bytes, _pages=fallback_pages) if fallback_pages else ()


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


_UNIT_MULTIPLIER = {"元": 1, "千元": 1_000, "万元": 10_000, "人民币百万元": 1_000_000, "百万元": 1_000_000}


def validate_balance_sheet(facts: Iterable[OfficialFinancialFact]) -> dict[str, object]:
    """Validate the free accounting identity without mutating raw fact units."""
    rows = {fact.metric: fact for fact in facts if fact.column_identity in {"current_period", "period_end"}}
    required = ("total_assets", "total_liabilities", "total_equity")
    if any(key not in rows for key in required):
        return {"status": "missing", "reason": "missing_balance_sheet_component", "raw_text_excerpt": " | ".join(item.quoted_anchor[:160] for item in rows.values())[:520]}
    try:
        values = {key: rows[key].value * _UNIT_MULTIPLIER[rows[key].unit] for key in required}
    except KeyError:
        return {"status": "missing", "reason": "unsupported_balance_sheet_unit", "raw_text_excerpt": " | ".join(rows[key].quoted_anchor[:120] for key in required)}
    difference = values["total_assets"] - values["total_liabilities"] - values["total_equity"]
    tolerance = max(1, abs(values["total_assets"]) * .000001)
    return {"status": "passed" if abs(difference) <= tolerance else "failed", "difference": difference, "tolerance": tolerance, "components": {key: {"document_id": rows[key].document_id, "page_number": rows[key].page_number, "value": rows[key].value, "unit": rows[key].unit} for key in required}}


def validate_statement_column_consistency(facts: Iterable[OfficialFinancialFact]) -> dict[str, object]:
    """Fail closed when one statement-period mixes end and opening columns."""
    relevant = [item for item in facts if item.statement_scope == "consolidated" and item.metric in {"cash", "current_assets", "current_liabilities", "total_assets", "total_liabilities", "total_equity"}]
    identities = sorted({item.column_identity for item in relevant})
    if "unknown" in identities:
        return {"status": "failed", "reason": "unresolved_statement_column", "raw_text_excerpt": " | ".join(item.quoted_anchor[:120] for item in relevant)[:520]}
    # Both identities are expected only if every field is represented twice.
    by_metric = {}
    for item in relevant: by_metric.setdefault(item.metric, set()).add(item.column_identity)
    mixed = {key: sorted(value) for key, value in by_metric.items() if value not in ({"period_end"}, {"period_begin"}, {"current_period"}, {"previous_period"}, {"period_end", "period_begin"}, {"current_period", "previous_period"})}
    # If every metric occurs once, it must be the same statement column.  A
    # mix (cash=opening, liabilities=closing) is a silent but fatal table bug.
    singleton_identities = {next(iter(value)) for value in by_metric.values() if len(value) == 1}
    if len(singleton_identities) > 1:
        mixed["statement"] = sorted(singleton_identities)
    return {"status": "failed" if mixed else "passed", "identities": identities, "mixed": mixed}


def validate_balance_sheet_by_column(facts: Iterable[OfficialFinancialFact]) -> dict[str, object]:
    """Run the accounting identity independently for closing and opening columns."""
    rows = tuple(facts)
    result = {}
    for identity in ("period_end", "period_begin", "current_period", "previous_period"):
        selected = [item for item in rows if item.column_identity == identity]
        if selected:
            result[identity] = validate_balance_sheet(selected)
    return result


def compare_cross_year(current: Iterable[OfficialFinancialFact], previous: Iterable[OfficialFinancialFact]) -> list[dict[str, object]]:
    """Compare a later filing's prior-period column to the prior filing current column."""
    now = {fact.metric: fact for fact in current if fact.column_identity == "previous_period"}
    prior = {fact.metric: fact for fact in previous if fact.column_identity in {"current_period", "period_end"}}
    results = []
    for metric in sorted(set(now) & set(prior)):
        left, right = now[metric], prior[metric]
        if left.unit not in _UNIT_MULTIPLIER or right.unit not in _UNIT_MULTIPLIER:
            status, nature = "inconsistent", "unsupported_unit"
        else:
            a, b = left.value * _UNIT_MULTIPLIER[left.unit], right.value * _UNIT_MULTIPLIER[right.unit]
            ratio = abs(a / b) if b else None
            status = "consistent" if abs(a - b) <= max(1, abs(b) * .000001) else "inconsistent"
            nature = "exact_or_rounding" if status == "consistent" else ("quantity_scale" if ratio and (ratio > 100 or ratio < .01) else "different_value")
        results.append({"metric": metric, "status": status, "nature": nature, "current_document_id": left.document_id, "current_page_number": left.page_number, "current_value": left.value, "previous_document_id": right.document_id, "previous_page_number": right.page_number, "previous_value": right.value})
    return results


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
