"""Official-PDF page-bound narrative extraction for issuer research.

This module deliberately handles prose separately from the financial-table
extractor.  It keeps the same document identity boundary: a narrative block is
admitted only with the original CNINFO document id, raw hash, page, full
heading path and verbatim source text.  Nothing here is an AI conclusion.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Iterable

from .document_intelligence import DocumentPage, ParserConfig, parse_pdf_document
from .e4_catl_financial_history import CATL_REPORTS, CATL_TICKER, OfficialReport
from .official_filings import default_http_transport


NARRATIVE_SCHEMA = "e4-official-narrative-evidence-v1"
_SECTION = re.compile(r"^第[一二三四五六七八九十]+节\s*(.{2,80})$")
_CHAPTER = re.compile(r"^([一二三四五六七八九十]+)、\s*(.{2,100})$")
_SUBCHAPTER = re.compile(r"^[（(]([一二三四五六七八九十]+)[）)]\s*(.{2,100})$")
_NUMBERED = re.compile(r"^(\d+(?:\.\d+){0,3})[、.]\s*(.{2,100})$")
_PAGE_NUMBER = re.compile(r"^(?:第\s*)?\d{1,4}(?:\s*页)?(?:\s*/\s*\d{1,4})?$")
_TARGET_WORDS = (
    "业务概述", "主营业务", "产品", "地区", "行业", "发展战略", "经营情况", "竞争力",
    "未来发展", "研发", "核心技术", "风险", "董事", "监事", "高级管理", "高管", "治理",
)


@dataclass(frozen=True)
class NarrativeBlock:
    ticker: str
    report_period: str
    document_id: str
    raw_hash: str
    page_number: int
    section_path: str | None
    text: str
    source_url: str
    extraction_method: str
    status: str
    reason: str | None = None


def _compact(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _is_toc_page(text: str) -> bool:
    compact = _compact(text)
    return "目录" in compact and (compact.count("……") >= 3 or len(re.findall(r"\.{3,}|…{3,}|\s\d{1,3}(?=\s|$)", compact)) >= 5)


def _margin_lines(pages: Iterable[DocumentPage]) -> set[str]:
    pages = tuple(pages)
    counts: Counter[str] = Counter()
    for page in pages:
        lines = [_compact(line) for line in page.text.splitlines() if _compact(line)]
        for line in lines[:3] + lines[-3:]:
            if len(line) >= 4 and not _PAGE_NUMBER.match(line):
                counts[line] += 1
    threshold = max(3, len(pages) // 8)
    return {line for line, count in counts.items() if count >= threshold}


def _heading(line: str) -> tuple[int, str] | None:
    line = _compact(line)
    if len(line) > 100 or re.search(r"[。；;]", line):
        return None
    candidates = ((_SECTION.match(line), 1), (_CHAPTER.match(line), 2), (_SUBCHAPTER.match(line), 3), (_NUMBERED.match(line), 4))
    for match, level in candidates:
        if not match:
            continue
        title = match.group(match.lastindex or 0)
        # A table row or dated board-resolution sentence can start with a list
        # marker.  It is not a heading merely because it begins with ``1、``.
        # Keep recognisable titles short and free of sentence/table signals.
        if level > 1 and (len(title) > 55 or re.search(r"[，,:：]", title) or len(re.findall(r"\d", title)) > 4):
            return None
        return level, line
    return None


def _path_is_target(path: tuple[str, ...]) -> bool:
    combined = " > ".join(path)
    root = path[0] if path else ""
    if root.startswith("第三节"):
        return True
    if root.startswith("第二节"):
        # The root itself contains ``公司简介``.  It is not sufficient to
        # admit the entire financial-indicator section as business narrative.
        return any(word in combined for word in ("业务", "产品", "地区"))
    if root.startswith("第四节"):
        return any(word in combined for word in ("董事", "监事", "管理", "治理", "任职", "变动"))
    return any(word in combined for word in _TARGET_WORDS)


def _is_prose(line: str) -> bool:
    compact = _compact(line)
    if len(compact) < 24 or _PAGE_NUMBER.match(compact) or "单位：" in compact:
        return False
    digits = len(re.findall(r"\d", compact))
    chinese = len(re.findall(r"[\u4e00-\u9fff]", compact))
    return chinese >= 12 and digits <= max(6, len(compact) // 8)


def _paragraphs(lines: Iterable[str]) -> tuple[str, ...]:
    paragraphs: list[str] = []
    current: list[str] = []
    for line in lines:
        current.append(_compact(line))
        if re.search(r"[。！？；;]$", line) or len("".join(current)) >= 900:
            value = _compact("".join(current))
            if _is_prose(value):
                paragraphs.append(value)
            current = []
    if current:
        value = _compact("".join(current))
        if _is_prose(value):
            paragraphs.append(value)
    return tuple(paragraphs)


def extract_narrative_blocks(
    report: OfficialReport,
    pdf_bytes: bytes,
    *,
    pages: Iterable[DocumentPage] | None = None,
) -> tuple[NarrativeBlock, ...]:
    """Extract target prose while retaining heading state across pages."""
    raw_hash = hashlib.sha256(pdf_bytes).hexdigest()
    if pages is None:
        parsed = parse_pdf_document(
            report.document_id, pdf_bytes, expected_raw_hash=raw_hash,
            config=ParserConfig(parser_version="park-narrative-parser-v1", native_text_min_chars=0),
            ocr_backend=lambda _bytes, _page: "",
        )
        pages = parsed.pages
    pages = tuple(pages)
    margins = _margin_lines(pages)
    path: list[str] = []
    blocks: list[NarrativeBlock] = []
    for page in pages:
        if _is_toc_page(page.text):
            continue
        prose: list[str] = []
        for raw_line in page.text.splitlines():
            line = _compact(raw_line)
            if not line or line in margins or _PAGE_NUMBER.match(line):
                continue
            detected = _heading(line)
            if detected:
                level, title = detected
                path = path[:level - 1] + [title]
                continue
            if _is_prose(line):
                prose.append(line)
        current_path = tuple(path)
        for paragraph in _paragraphs(prose):
            target = _path_is_target(current_path)
            blocks.append(NarrativeBlock(
                ticker=report.ticker, report_period=report.period, document_id=report.document_id,
                raw_hash=raw_hash, page_number=page.page_number,
                section_path=" > ".join(current_path) if target and current_path else None,
                text=paragraph, source_url=report.source_url,
                extraction_method=page.extraction_method,
                status="resolved" if target and current_path else "unresolved",
                reason=None if target and current_path else "no_target_section_context",
            ))
    return tuple(blocks)


def _report_coverage(blocks: Iterable[NarrativeBlock]) -> dict[str, object]:
    resolved = [block for block in blocks if block.status == "resolved"]
    unresolved = [block for block in blocks if block.status != "resolved"]
    by_path: dict[str, list[NarrativeBlock]] = defaultdict(list)
    for block in resolved:
        by_path[str(block.section_path)].append(block)
    return {
        "resolved_blocks": len(resolved), "resolved_pages": len({block.page_number for block in resolved}),
        "unresolved_blocks": len(unresolved),
        "by_section_path": [
            {"section_path": path, "blocks": len(rows), "pages": sorted({row.page_number for row in rows})}
            for path, rows in sorted(by_path.items())
        ],
        "unresolved": [
            {"document_id": block.document_id, "page_number": block.page_number, "raw_excerpt": block.text[:320], "reason": block.reason}
            for block in unresolved
        ],
    }


def _capture_report_narrative(report: OfficialReport) -> tuple[dict[str, object], tuple[NarrativeBlock, ...]]:
    """One bounded official fetch; any failure becomes an explicit gap."""
    try:
        response = default_http_transport(report.source_url, {"Accept": "application/pdf"})
    except Exception as exc:  # transport is an external source boundary
        return ({"period": report.period, "document_id": report.document_id, "status": "missing", "reason": f"official_pdf_fetch_failed:{type(exc).__name__}", "source_url": report.source_url}, ())
    if response.status_code != 200 or not response.body.startswith(b"%PDF"):
        return ({"period": report.period, "document_id": report.document_id, "status": "missing", "reason": "official_pdf_unavailable", "source_url": report.source_url}, ())
    blocks = extract_narrative_blocks(report, response.body)
    return ({
        "period": report.period, "document_id": report.document_id, "status": "available",
        "raw_hash": hashlib.sha256(response.body).hexdigest(), "source_url": report.source_url,
        "coverage": _report_coverage(blocks),
    }, blocks)


def capture_catl_narrative(reports: Iterable[OfficialReport] = CATL_REPORTS) -> dict[str, object]:
    """Fetch only declared official CNINFO PDFs; retain source failures honestly."""
    reports = tuple(reports)
    report_rows: list[dict[str, object]] = []
    all_blocks: list[NarrativeBlock] = []
    # Eight fixed official documents are independent.  Bounded concurrency
    # keeps a recoverable source failure from delaying all remaining receipts.
    with ThreadPoolExecutor(max_workers=min(4, max(1, len(reports)))) as pool:
        captured = list(pool.map(_capture_report_narrative, reports))
    for row, blocks in captured:
        report_rows.append(row)
        all_blocks.extend(blocks)
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    payload = {
        "schema_version": NARRATIVE_SCHEMA, "data_kind": "real", "ticker": CATL_TICKER,
        "generated_at": generated_at, "reports": report_rows,
        "blocks": [asdict(block) for block in all_blocks],
        "coverage": _report_coverage(all_blocks),
        "truth_boundary": {"official_cninfo_pdf_only": True, "page_bound_only": True, "ai_judgment": False},
    }
    payload["receipt_hash"] = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    payload["receipt_id"] = f"{NARRATIVE_SCHEMA}:{payload['receipt_hash']}"
    return payload


def merge_narrative_receipts(receipts: Iterable[dict[str, object]]) -> dict[str, object]:
    """Combine bounded official runs without losing their original receipt IDs."""
    receipts = tuple(receipts)
    if not receipts:
        raise ValueError("at least one real narrative receipt is required")
    seen: set[str] = set()
    reports: list[dict[str, object]] = []
    blocks: list[NarrativeBlock] = []
    receipt_ids: list[str] = []
    for receipt in receipts:
        if receipt.get("schema_version") != NARRATIVE_SCHEMA or receipt.get("data_kind") != "real" or receipt.get("ticker") != CATL_TICKER:
            raise ValueError("only real CATL narrative receipts can be merged")
        receipt_hash = str(receipt.get("receipt_hash") or "")
        copy = {key: value for key, value in receipt.items() if key not in {"receipt_hash", "receipt_id"}}
        if not receipt_hash or hashlib.sha256(json.dumps(copy, ensure_ascii=False, sort_keys=True).encode()).hexdigest() != receipt_hash:
            raise ValueError("source narrative receipt hash mismatch")
        receipt_ids.append(str(receipt.get("receipt_id")))
        for report in receipt.get("reports", []):
            document_id = str(report.get("document_id"))
            if document_id in seen:
                raise ValueError(f"duplicate official narrative document: {document_id}")
            seen.add(document_id)
            reports.append(report)
        blocks.extend(NarrativeBlock(**block) for block in receipt.get("blocks", []))
    payload = {
        "schema_version": NARRATIVE_SCHEMA, "data_kind": "real", "ticker": CATL_TICKER,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "reports": reports, "blocks": [asdict(block) for block in blocks], "coverage": _report_coverage(blocks),
        "source_run_receipts": receipt_ids,
        "truth_boundary": {"official_cninfo_pdf_only": True, "page_bound_only": True, "ai_judgment": False},
    }
    payload["receipt_hash"] = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    payload["receipt_id"] = f"{NARRATIVE_SCHEMA}:{payload['receipt_hash']}"
    return payload
