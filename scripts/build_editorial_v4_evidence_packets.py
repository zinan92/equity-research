#!/usr/bin/env python3
"""Build page-bound, official-only evidence packets for editorial V4.

The historical M4 packages are intentionally not used as prose input.  This
script consumes freshly captured official PDFs (kept outside the repository),
extracts bounded narrative paragraphs and accounting rows, and writes only
the page/quote/hash evidence needed by the editorial writer.  A missing local
PDF is a typed gap; it is never replaced by a cached or aggregator value.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from urllib.parse import urlparse
from dataclasses import asdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product"))

from data_core.document_intelligence import ParserConfig, parse_pdf_document
from data_core.e4_catl_financial_history import OfficialReport
from data_core.e4_narrative_evidence import extract_narrative_blocks

SCHEMA = "editorial-v4-evidence-packet-v1"
OFFICIAL_HOSTS = {"static.cninfo.com.cn", "www.cninfo.com.cn"}

OFFICIAL_URLS = {
    "vanke_2025_annual": "https://static.cninfo.com.cn/finalpage/2026-04-01/1225067794.PDF",
    "vanke_2026_q1": "https://static.cninfo.com.cn/finalpage/2026-04-30/1225264061.PDF",
    "longying_2025_annual": "https://static.cninfo.com.cn/finalpage/2026-04-18/1225120097.PDF",
    "longying_2026_q1": "https://static.cninfo.com.cn/finalpage/2026-04-23/1225144413.PDF",
    "midea_2025_annual": "https://static.cninfo.com.cn/finalpage/2026-03-31/1225065145.PDF",
    "midea_2026_q1": "https://static.cninfo.com.cn/finalpage/2026-04-30/1225259066.PDF",
    "cypc_2025_annual": "https://static.cninfo.com.cn/finalpage/2026-04-30/1225262036.PDF",
    "cypc_2026_q1": "https://static.cninfo.com.cn/finalpage/2026-04-30/1225262110.PDF",
    "catl_2025_annual_cninfo": "https://static.cninfo.com.cn/finalpage/2026-03-10/1225002214.PDF",
    "catl_2026_q1": "https://static.cninfo.com.cn/finalpage/2026-04-16/1225107946.PDF",
    "moutai_2025_annual": "https://static.cninfo.com.cn/finalpage/2026-04-17/1225114741.PDF",
}

# Only these manually inspected statement rows are admitted as numeric facts.
# The page index is the PDF page index emitted by DocumentPage (not a printed
# report-page label).  A mismatch is a typed gap, never a nearby-row fallback.
STRICT_ROWS: dict[tuple[str, str], tuple[tuple[str, int, tuple[str, ...], str], ...]] = {
    ("000333.SZ", "2025FY"): (
        ("revenue", 135, ("一、营业总收入",), "458,502,407"),
        ("net_profit_parent", 135, ("归属于母公司股东的", "净利润"), "43,945,411"),
    ),
    ("000333.SZ", "2026Q1"): (
        ("revenue", 8, ("一、营业总收入",), "131,580,870"),
        ("net_profit_parent", 8, ("归属于母公司股东的净利润",), "12,674,556"),
    ),
    ("600900.SH", "2025FY"): (
        ("revenue", 84, ("一、营业总收入",), "86,241,940,222.20"),
        ("net_profit_parent", 85, ("归属于母公司股东的净利润",), "34,502,809,176.39"),
    ),
    ("600900.SH", "2026Q1"): (
        ("revenue", 8, ("一、营业总收入",), "18,111,540,767.50"),
        ("net_profit_parent", 9, ("归属于母公司股东的净利润",), "6,761,006,898.48"),
    ),
    ("300750.SZ", "2025FY"): (
        ("revenue", 116, ("一、营业总收入",), "423,701,834"),
        ("net_profit_parent", 117, ("归属于母公司股东的净利润",), "72,201,282"),
    ),
    ("300750.SZ", "2026Q1"): (
        ("revenue", 8, ("一、营业总收入",), "129,131,041"),
        ("net_profit_parent", 9, ("归属于母公司所有者的净利润",), "20,737,710"),
    ),
    ("600519.SH", "2025FY"): (
        ("revenue", 61, ("一、营业总收入",), "172,054,171,890.91"),
        ("net_profit_parent", 62, ("归属于母公司股东的净利润",), "82,320,067,101.68"),
    ),
    ("300115.SZ", "2025FY"): (
        ("revenue", 84, ("一、营业总收入",), "18,818,693,525.67"),
        ("net_profit_parent", 85, ("归属于母公司股东的净利润",), "597,666,576.59"),
    ),
    ("300115.SZ", "2026Q1"): (
        ("revenue", 9, ("一、营业总收入",), "5,130,825,705.85"),
        ("net_profit_parent", 10, ("归属于母公司所有者的净利润",), "125,232,197.99"),
    ),
    ("000002.SZ", "2025FY"): (
        ("revenue", 155, ("一、营业总收入",), "233,432,768,960.43"),
        ("net_profit_parent", 155, ("归属于母公司股东的净利润",), "88,556,470,495.64"),
    ),
    ("000002.SZ", "2026Q1"): (
        ("revenue", 10, ("一、营业总收入",), "28,927,889,365.26"),
        ("net_profit_parent", 11, ("归属于母公司所有者的净利润",), "5,952,156,227.34"),
    ),
}

STRICT_SECOND: dict[tuple[str, str, str], str] = {
    ("000333.SZ", "2025FY", "revenue"): "409,084,266",
    ("000333.SZ", "2025FY", "net_profit_parent"): "38,537,237",
    ("000333.SZ", "2026Q1", "revenue"): "128,428,421",
    ("000333.SZ", "2026Q1", "net_profit_parent"): "12,422,233",
    ("600900.SH", "2025FY", "revenue"): "84,491,870,566.52",
    ("600900.SH", "2025FY", "net_profit_parent"): "32,496,172,808.65",
    ("600900.SH", "2026Q1", "revenue"): "17,015,283,778.59",
    ("600900.SH", "2026Q1", "net_profit_parent"): "5,180,785,597.87",
    ("300750.SZ", "2025FY", "revenue"): "362,012,554",
    ("300750.SZ", "2025FY", "net_profit_parent"): "50,744,682",
    ("300750.SZ", "2026Q1", "revenue"): "84,704,589",
    ("300750.SZ", "2026Q1", "net_profit_parent"): "13,962,558",
    ("600519.SH", "2025FY", "revenue"): "174,144,069,958.25",
    ("600519.SH", "2025FY", "net_profit_parent"): "86,228,146,421.62",
    ("300115.SZ", "2025FY", "revenue"): "16,934,153,115.29",
    ("300115.SZ", "2025FY", "net_profit_parent"): "771,529,452.81",
    ("300115.SZ", "2026Q1", "revenue"): "4,395,138,974.74",
    ("300115.SZ", "2026Q1", "net_profit_parent"): "174,874,009.78",
    ("000002.SZ", "2025FY", "revenue"): "343,176,440,712.96",
    ("000002.SZ", "2025FY", "net_profit_parent"): "49,478,429,211.96",
    ("000002.SZ", "2026Q1", "revenue"): "37,994,649,925.08",
    ("000002.SZ", "2026Q1", "net_profit_parent"): "6,246,208,543.03",
}
STRICT_UNITS = {
    "000002.SZ": "元", "000333.SZ": "千元", "600900.SH": "元", "300750.SZ": "千元", "600519.SH": "元", "300115.SZ": "元",
}


COMPANIES: dict[str, dict[str, Any]] = {
    "000001.SZ": {
        "name": "平安银行",
        "existing_packet": {
            "narrative": ROOT / "docs/evidence/v4-n1-official/000001.SZ-official-narrative-evidence.json",
            "financial": ROOT / "docs/evidence/v4-n1-official/000001.SZ-financial-page-evidence.json",
        },
        "docs": [],
    },
    "000333.SZ": {
        "name": "美的集团",
        "docs": [
            {"source_id": "midea_2025_annual", "period": "2025FY", "file": "midea_2025_annual.pdf", "title": "美的集团 2025 年年度报告"},
            {"source_id": "midea_2026_q1", "period": "2026Q1", "file": "midea_2026_q1.pdf", "title": "美的集团 2026 年第一季度报告"},
        ],
    },
    "600900.SH": {
        "name": "长江电力",
        "docs": [
            {"source_id": "cypc_2025_annual", "period": "2025FY", "file": "cypc_2025_annual.pdf", "title": "长江电力 2025 年年度报告"},
            {"source_id": "cypc_2026_q1", "period": "2026Q1", "file": "cypc_2026_q1.pdf", "title": "长江电力 2026 年第一季度报告"},
        ],
    },
    "300750.SZ": {
        "name": "宁德时代",
        "docs": [
            # The CNINFO copy is the official filing used for this run.  The
            # historical M4 package pointed at a CATL-hosted mirror whose raw
            # bytes are not reused here.
            {"source_id": "catl_2025_annual_cninfo", "period": "2025FY", "file": "catl_2025_annual.pdf", "title": "宁德时代 2025 年年度报告（CNINFO）", "url": "https://static.cninfo.com.cn/finalpage/2026-03-10/1225002214.PDF"},
            {"source_id": "catl_2026_q1", "period": "2026Q1", "file": "catl_2026_q1.pdf", "title": "宁德时代 2026 年第一季度报告", "url": "https://static.cninfo.com.cn/finalpage/2026-04-16/1225107946.PDF"},
        ],
    },
    "600519.SH": {
        "name": "贵州茅台",
        "docs": [
            {"source_id": "moutai_2025_annual", "period": "2025FY", "file": "moutai_2025_annual.pdf", "title": "贵州茅台 2025 年年度报告"},
        ],
    },
    "300115.SZ": {
        "name": "长盈精密",
        "docs": [
            {"source_id": "longying_2025_annual", "period": "2025FY", "file": "longying_2025_annual.pdf", "title": "长盈精密 2025 年年度报告"},
            {"source_id": "longying_2026_q1", "period": "2026Q1", "file": "longying_2026_q1.pdf", "title": "长盈精密 2026 年第一季度报告"},
        ],
    },
    "000002.SZ": {
        "name": "万科A",
        "docs": [
            {"source_id": "vanke_2025_annual", "period": "2025FY", "file": "vanke_2025_annual.pdf", "title": "万科A 2025 年年度报告"},
            {"source_id": "vanke_2026_q1", "period": "2026Q1", "file": "vanke_2026_q1.pdf", "title": "万科A 2026 年第一季度报告"},
        ],
    },
}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _source_url(ticker: str, spec: dict[str, Any], raw_hash: str) -> str:
    url = str(spec.get("url") or OFFICIAL_URLS.get(str(spec["source_id"])) or "")
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in OFFICIAL_HOSTS or not url.upper().endswith(".PDF"):
        raise ValueError(f"source URL is outside official allowlist for {ticker}/{spec['source_id']} ({raw_hash[:12]})")
    return url


def _issuer_document_id(source_id: str, raw_hash: str) -> str:
    return f"official-filing:editorial-v4:{source_id}:{raw_hash[:16]}"


def _select_blocks(blocks: list[Any], limit: int = 42) -> list[Any]:
    keywords = (
        "董事", "监事", "高级管理", "治理", "创始", "实际控制", "主营业务", "产品",
        "研发", "技术", "产能", "客户", "市场", "行业", "竞争", "海外", "战略",
        "发展", "风险", "供应链", "渠道", "核心", "业务模式", "经营",
    )

    def score(block: Any) -> tuple[int, int, int]:
        text = str(block.text)
        path = str(block.section_path or "")
        hits = sum(text.count(word) for word in keywords) + 2 * sum(path.count(word) for word in keywords)
        # Prefer concrete paragraphs while keeping a spread across pages.
        return (hits, min(len(text), 520), -int(block.page_number))

    chosen: list[Any] = []
    seen_pages: set[tuple[str, int]] = set()
    for block in sorted((item for item in blocks if item.status == "resolved"), key=score, reverse=True):
        page_key = (block.document_id, block.page_number)
        if page_key in seen_pages and len(chosen) < limit // 2:
            continue
        chosen.append(block)
        seen_pages.add(page_key)
        if len(chosen) >= limit:
            break
    return sorted(chosen, key=lambda item: (item.document_id, item.page_number, item.text))


def _fact_evidence(source_id: str, fact: Any, index: int, source_url: str, title: str) -> dict[str, Any]:
    row = asdict(fact)
    return {
        "evidence_id": f"{source_id}:fact:{fact.metric}:{fact.page_number}:{index}",
        "source_id": source_id,
        "document_id": fact.document_id,
        "source_kind": "issuer_filing",
        "evidence_class": "issuer_disclosure",
        "report_period": fact.report_period,
        "page_number": fact.page_number,
        "section_path": "consolidated_statement",
        "quoted_label": fact.quoted_label,
        "quoted_anchor": fact.quoted_anchor[:520],
        "source_url": source_url,
        "raw_sha256": fact.raw_hash,
        "unit": fact.unit,
        "currency": fact.currency,
        "metric": fact.metric,
        "value": fact.value,
        "column_identity": fact.column_identity,
        "column_header_excerpt": fact.column_header_excerpt[:280],
        "source_title": title,
        "fact_record": row,
    }


def _narrative_evidence(source_id: str, block: Any, source_url: str, title: str, index: int) -> dict[str, Any]:
    return {
        "evidence_id": f"{source_id}:narrative:{block.page_number}:{index}",
        "source_id": source_id,
        "document_id": block.document_id,
        "source_kind": "issuer_filing",
        "evidence_class": "issuer_disclosure",
        "report_period": block.report_period,
        "page_number": block.page_number,
        "section_path": block.section_path,
        "quoted_anchor": block.text[:900],
        "source_url": source_url,
        "raw_sha256": block.raw_hash,
        "source_title": title,
        "text": block.text[:900],
    }


def _numbers_after(text: str, marker: str) -> list[float]:
    tail = text[text.find(marker) + len(marker):]
    values: list[float] = []
    for token in re.findall(r"(?<![\d.])-?\d[\d,]*(?:\.\d+)?", tail):
        try:
            values.append(float(token.replace(",", "")))
        except ValueError:
            continue
    return values


def _strict_financial_facts(ticker: str, period: str, document_id: str, raw_hash: str, source_url: str, title: str, pages: tuple[Any, ...]) -> tuple[dict[str, Any], ...]:
    """Extract only rows with a declared page, label and expected first value."""
    facts: list[dict[str, Any]] = []
    for metric, page_number, label_parts, expected_first in STRICT_ROWS.get((ticker, period), ()):
        page = next((item for item in pages if item.page_number == page_number), None)
        if page is None:
            continue
        lines = page.text.splitlines()
        target_index = None
        target_marker = ""
        for index, line in enumerate(lines):
            compact = " ".join(line.split())
            if all(part in compact for part in label_parts) and any(char.isdigit() for char in compact):
                target_index = index
                target_marker = label_parts[0]
                break
        if target_index is None:
            continue
        combined = " ".join(" ".join(line.split()) for line in lines[target_index:target_index + 3])
        if expected_first not in combined:
            continue
        expected_second = STRICT_SECOND.get((ticker, period, metric), "")
        first_pos = combined.find(expected_first)
        second_pos = combined.find(expected_second, first_pos + len(expected_first)) if expected_second else -1
        if first_pos < 0 or second_pos < 0:
            continue
        # Statement headers on the declared page prove the two columns.  The
        # exact report period is fixed by the declared run, not guessed from
        # row order.
        header = " ".join(" ".join(line.split()) for line in lines[:40])
        if not ("年度" in header or "季度" in header or "本期发生额" in header or "年 1" in header or "年1" in header):
            continue
        unit = STRICT_UNITS[ticker]
        def signed_value(token: str) -> float:
            value = float(token.replace(",", ""))
            position = combined.find(token)
            if position > 0 and combined[position - 1] == "(":
                return -value
            return value

        values = (signed_value(expected_first), signed_value(expected_second))
        for offset, value in enumerate(values):
            row_period = period if offset == 0 else (f"{int(period[:4]) - 1}FY" if period.endswith("FY") else f"{int(period[:4]) - 1}Q1")
            evidence_id = f"{document_id}:fact:{metric}:{page_number}:{offset}"
            facts.append({
                "evidence_id": evidence_id,
                "source_id": document_id.split(":")[-2],
                "document_id": document_id,
                "source_kind": "issuer_filing",
                "evidence_class": "issuer_disclosure",
                "report_period": row_period,
                "page_number": page_number,
                "section_path": "consolidated_statement",
                "quoted_label": label_parts[0],
                "quoted_anchor": combined[:520],
                "source_url": source_url,
                "raw_sha256": raw_hash,
                "unit": unit,
                "currency": "CNY",
                "metric": metric,
                "value": value,
                "column_identity": "current_period" if offset == 0 else "previous_period",
                "column_header_excerpt": header[:280],
                "source_title": title,
                "validation_status": "page_row_validated_v1",
            })
    return tuple(facts)


def _derive_metrics(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for fact in facts:
        grouped.setdefault((str(fact.get("metric")), str(fact.get("document_id"))), []).append(fact)
    derived: list[dict[str, Any]] = []
    for (metric, document_id), rows in sorted(grouped.items()):
        current = next((row for row in rows if row.get("column_identity") in {"current_period", "period_end"}), None)
        previous = next((row for row in rows if row.get("column_identity") in {"previous_period", "period_begin"}), None)
        if not current or not previous or not isinstance(current.get("value"), (int, float)) or not isinstance(previous.get("value"), (int, float)):
            continue
        delta = float(current["value"]) - float(previous["value"])
        base = float(previous["value"])
        pct = None if base == 0 else delta / abs(base) * 100
        direction = "增长" if delta > 0 else "下滑" if delta < 0 else "持平"
        derived.append({
            "derived_id": f"derived:{document_id}:{metric}",
            "metric": metric,
            "document_id": document_id,
            "current_evidence_id": current["evidence_id"],
            "previous_evidence_id": previous["evidence_id"],
            "current_period": current.get("report_period"),
            "previous_period": previous.get("report_period"),
            "current_value": current["value"],
            "previous_value": previous["value"],
            "absolute_change": round(delta, 6),
            "percent_change": None if pct is None else round(pct, 6),
            "direction": direction,
            "formula": "(current_value - previous_value) / abs(previous_value) * 100",
            "computed_by": "editorial-v4-deterministic-derived-metrics-v1",
        })
    return derived


def _build_existing_packet(ticker: str, company: dict[str, Any], out_path: Path) -> dict[str, Any]:
    """Adapt an already-verified official page receipt without its old prose."""
    narrative_path = Path(company["existing_packet"]["narrative"])
    financial_path = Path(company["existing_packet"]["financial"])
    narrative = json.loads(narrative_path.read_text(encoding="utf-8"))
    financial = json.loads(financial_path.read_text(encoding="utf-8"))
    if narrative.get("data_kind") != "real" or narrative.get("ticker") != ticker:
        raise ValueError(f"existing narrative receipt identity mismatch for {ticker}")
    if financial.get("data_kind") != "real" or financial.get("ticker") != ticker:
        raise ValueError(f"existing financial receipt identity mismatch for {ticker}")
    sources: dict[str, dict[str, Any]] = {}
    evidence: list[dict[str, Any]] = []
    for block_index, block in enumerate(narrative.get("blocks", [])):
        if block.get("status") != "resolved":
            continue
        source_id = f"official:{block['document_id']}"
        source = sources.setdefault(source_id, {
            "source_id": source_id, "document_id": block["document_id"],
            "source_kind": "issuer_filing", "evidence_class": "issuer_disclosure",
            "title": "平安银行 2025 年年度报告（已验收官方页级 receipt）",
            "report_period": block.get("report_period"), "source_url": block["source_url"],
            "raw_sha256": block["raw_hash"], "page_count": 1,
        })
        source["page_count"] = max(int(source.get("page_count") or 1), int(block.get("page_number") or 1))
        evidence.append({
            "evidence_id": f"{source_id}:narrative:{block['page_number']}:{block_index}",
            "source_id": source_id, "document_id": block["document_id"],
            "source_kind": "issuer_filing", "evidence_class": "issuer_disclosure",
            "report_period": block.get("report_period"), "page_number": block["page_number"],
            "section_path": block.get("section_path"), "quoted_anchor": str(block.get("text") or "")[:900],
            "source_url": block["source_url"], "raw_sha256": block["raw_hash"],
            "source_title": source["title"], "text": str(block.get("text") or "")[:900],
        })
    # The receipt-bound bank facts have page anchors but unresolved column
    # identity.  Keep them out of numeric model input; preserve the explicit
    # gap rather than replaying an ambiguous number.
    facts: list[dict[str, Any]] = []
    packet: dict[str, Any] = {
        "schema_version": SCHEMA, "data_kind": "real", "ticker": ticker,
        "issuer_name": company["name"], "evidence_cutoff": "2026-08-03",
        "sources": sorted(sources.values(), key=lambda item: item["document_id"]),
        "evidence": evidence, "financial_facts": facts, "derived_metrics": _derive_metrics(facts),
        "gaps": [
            {"scope": ticker, "reason": "historical_receipt_has_no_2026Q1_page_packet", "raw_text_excerpt": "The selected official receipt covers the verified FY packet only."},
            {"scope": ticker, "reason": "financial_column_identity_unresolved", "raw_text_excerpt": "Existing page facts are retained by their source receipt but are not admitted as numeric model input until the statement columns are independently resolved."},
        ],
        "excluded_sources": [{"source_id": "historical-m4-ai-prose", "reason": "AI narrative/report prose is not source evidence"}],
        "truth_boundary": {"official_pdf_only": True, "issuer_disclosure_is_not_independent_proof": True, "derived_direction_is_deterministic": True, "no_valuation_or_action": True, "no_old_report_prose": True},
        "source_receipts": {"narrative_receipt_hash": narrative.get("receipt_hash"), "financial_receipt_hash": financial.get("receipt_hash")},
    }
    packet["packet_hash"] = _json_hash(packet)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return packet


def build_packet(ticker: str, source_root: Path, out_path: Path) -> dict[str, Any]:
    if ticker not in COMPANIES:
        raise ValueError(f"unsupported editorial-v4 ticker: {ticker}")
    company = COMPANIES[ticker]
    if company.get("existing_packet"):
        return _build_existing_packet(ticker, company, out_path)
    sources: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    all_facts: list[dict[str, Any]] = []
    for spec in company["docs"]:
        path = source_root / str(spec["file"])
        if not path.exists():
            gaps.append({"scope": spec["source_id"], "reason": "official_pdf_not_captured", "raw_text_excerpt": f"expected official PDF at {path}"})
            continue
        pdf_bytes = path.read_bytes()
        raw_hash = _sha256(pdf_bytes)
        document_id = _issuer_document_id(str(spec["source_id"]), raw_hash)
        try:
            url = _source_url(ticker, spec, raw_hash)
            parsed = parse_pdf_document(document_id, pdf_bytes, expected_raw_hash=raw_hash, config=ParserConfig(native_text_min_chars=0), ocr_backend=lambda _b, _p: "")
        except Exception as exc:
            gaps.append({"scope": spec["source_id"], "reason": "official_pdf_parse_failed", "raw_sha256": raw_hash, "raw_text_excerpt": f"{type(exc).__name__}: {exc}"[:520]})
            continue
        sources.append({
            "source_id": spec["source_id"], "document_id": document_id,
            "source_kind": "issuer_filing", "evidence_class": "issuer_disclosure",
            "title": spec["title"], "report_period": spec["period"],
            "source_url": url, "raw_sha256": raw_hash, "page_count": len(parsed.pages),
            "parser_version": "park-document-intelligence-v1",
        })
        report = OfficialReport(spec["period"], document_id, url, ticker=ticker)
        try:
            blocks = _select_blocks(list(extract_narrative_blocks(report, pdf_bytes, pages=parsed.pages)))
        except Exception as exc:
            blocks = []
            gaps.append({"scope": spec["source_id"], "reason": "narrative_extraction_failed", "raw_sha256": raw_hash, "raw_text_excerpt": f"{type(exc).__name__}: {exc}"[:520]})
        for index, block in enumerate(blocks):
            evidence.append(_narrative_evidence(str(spec["source_id"]), block, url, str(spec["title"]), index))
        facts = _strict_financial_facts(ticker, str(spec["period"]), document_id, raw_hash, url, str(spec["title"]), parsed.pages)
        if not facts:
            gaps.append({"scope": spec["source_id"], "reason": "no_strict_page_rows", "raw_sha256": raw_hash, "raw_text_excerpt": "The declared statement rows were not found with the expected page/label/value anchor."})
        for row in facts:
            all_facts.append(row)
            evidence.append(row)
    if not sources:
        gaps.append({"scope": ticker, "reason": "no_official_pdf_evidence", "raw_text_excerpt": "No official PDF was captured for this issuer."})
    derived = _derive_metrics(all_facts)
    packet: dict[str, Any] = {
        "schema_version": SCHEMA,
        "data_kind": "real",
        "ticker": ticker,
        "issuer_name": company["name"],
        "evidence_cutoff": "2026-08-03",
        "sources": sources,
        "evidence": evidence,
        "financial_facts": all_facts,
        "derived_metrics": derived,
        "gaps": gaps,
        "excluded_sources": [
            {"source_id": "m4-aggregator-data", "reason": "Eastmoney F10/aggregator is prohibited"},
            {"source_id": "m4-independent-media", "reason": "historical M4 independent web sources were not recaptured with page-bound evidence"},
            {"source_id": "historical-m4-ai-prose", "reason": "AI narrative/report prose is not source evidence"},
        ],
        "truth_boundary": {
            "official_pdf_only": True,
            "issuer_disclosure_is_not_independent_proof": True,
            "derived_direction_is_deterministic": True,
            "no_valuation_or_action": True,
            "no_old_report_prose": True,
        },
    }
    packet["packet_hash"] = _json_hash(packet)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return packet


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, default=ROOT / "artifacts/editorial-v4/evidence-packets")
    parser.add_argument("ticker", nargs="+", choices=tuple(COMPANIES))
    args = parser.parse_args()
    for ticker in args.ticker:
        packet = build_packet(ticker.upper(), args.source_root, args.out_dir / f"{ticker.upper()}.json")
        print(json.dumps({"ticker": ticker.upper(), "sources": len(packet["sources"]), "evidence": len(packet["evidence"]), "facts": len(packet["financial_facts"]), "gaps": len(packet["gaps"]), "packet_hash": packet["packet_hash"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
