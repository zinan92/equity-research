"""Fail-closed official evidence bridge for the first V4 expansion cohort.

The V4 reader consumes whole dossiers, but the first expansion milestone is
deliberately limited to the evidence boundary.  This module reuses the
existing CNINFO filing adapter and financial parser, then materializes only
page-bound, issuer-scoped receipts that Round 7 can consume.  It never writes
model prose or changes a Tier/decision policy.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import urlparse

from .contracts import digest
from .e4_catl_financial_history import OfficialReport, extract_report_facts
from .e4_page_level_filing_facts import FilingNumericFact
from .official_filings import (
    OfficialFilingBatch,
    OfficialHttpTransport,
    sync_exchange_filings,
)


FINANCIAL_SCHEMA = "e4-financial-sequence-batch-v1"
MATERIALIZED_SCHEMA = "v4-n1-official-evidence-packet-v1"
ROUND7_FINANCIAL_SCHEMA = "round7-financial-page-evidence-v1"
OFFICIAL_CNINFO_HOST = "static.cninfo.com.cn"
TICKER_RE = re.compile(r"^[0-9]{6}\.(?:SZ|SH|BJ)$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
PERIODS = tuple(f"{year}FY" for year in range(2021, 2026)) + ("2026Q1",)


class OfficialEvidenceError(ValueError):
    """A source or receipt failed the official evidence contract."""


def _official_url(value: object) -> bool:
    parsed = urlparse(str(value or ""))
    return parsed.scheme == "https" and parsed.hostname == OFFICIAL_CNINFO_HOST


def _json_hash(value: Mapping[str, Any], *, omit_receipt_id: bool = False) -> str:
    excluded = {"receipt_hash"}
    if omit_receipt_id:
        excluded.add("receipt_id")
    return digest({key: item for key, item in value.items() if key not in excluded})


def _narrative_hash(value: Mapping[str, Any]) -> str:
    """Match the existing e4 narrative receipt's historical hash encoding."""
    payload = {key: item for key, item in value.items() if key not in {"receipt_hash", "receipt_id"}}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _require_sha(value: object, field: str) -> str:
    text = str(value or "")
    if not SHA256_RE.fullmatch(text):
        raise OfficialEvidenceError(f"{field} must be a lowercase SHA-256")
    return text


def _require_ticker(value: object) -> str:
    ticker = str(value or "").upper()
    if not TICKER_RE.fullmatch(ticker):
        raise OfficialEvidenceError(f"invalid A-share ticker: {ticker}")
    return ticker


def _require_document(document: Mapping[str, Any], *, ticker: str) -> dict[str, str]:
    document_id = str(document.get("document_id") or "")
    if not document_id.startswith("official-filing:"):
        raise OfficialEvidenceError(f"{ticker} document is not an official filing identity")
    source_url = str(document.get("source_url") or "")
    if not _official_url(source_url):
        raise OfficialEvidenceError(f"{ticker} document URL is not CNINFO official")
    raw_hash = _require_sha(document.get("raw_hash"), "document.raw_hash")
    title = str(document.get("title") or "").strip()
    published_at = str(document.get("published_at") or "").strip()
    if not title or not published_at:
        raise OfficialEvidenceError(f"{ticker} document metadata is incomplete")
    return {
        "document_id": document_id,
        "source_url": source_url,
        "raw_hash": raw_hash,
        "title": title,
        "published_at": published_at,
    }


def _round7_fact(raw: Mapping[str, Any], *, ticker: str, document: Mapping[str, str]) -> dict[str, Any]:
    """Drop only extractor-specific metadata while retaining the R7 fact shape."""
    required = {
        "ticker": ticker,
        "metric": str(raw.get("metric") or ""),
        "value": raw.get("value"),
        "document_id": document["document_id"],
        "raw_hash": document["raw_hash"],
        "page_number": raw.get("page_number"),
        "quoted_label": str(raw.get("quoted_label") or ""),
        "quoted_anchor": str(raw.get("quoted_anchor") or ""),
        "report_period": str(raw.get("report_period") or ""),
        "statement_scope": str(raw.get("statement_scope") or ""),
        "unit": str(raw.get("unit") or ""),
        "currency": str(raw.get("currency") or ""),
        "source_url": document["source_url"],
    }
    try:
        fact = FilingNumericFact(**required)
        fact.validate()
    except Exception as exc:  # keep the source row addressable without guessing
        raise OfficialEvidenceError(f"{ticker} page fact is invalid: {exc}") from exc
    return required


def materialize_financial_receipt(receipt: Mapping[str, Any], *, ticker: str) -> dict[str, Any]:
    """Validate one real E4 financial receipt and derive the R7 page-fact receipt."""
    normalized = _require_ticker(ticker)
    if receipt.get("schema_version") != FINANCIAL_SCHEMA or receipt.get("data_kind") != "real":
        raise OfficialEvidenceError("financial input must be a real e4 financial sequence receipt")
    observed_hash = _json_hash(receipt)
    if str(receipt.get("receipt_hash") or "") != observed_hash:
        raise OfficialEvidenceError("financial input receipt hash mismatch")
    if not (receipt.get("truth_boundary") or {}).get("official_cninfo_pdf_only"):
        raise OfficialEvidenceError("financial input is missing the official CNINFO boundary")
    rows = [row for row in receipt.get("tickers") or () if str(row.get("ticker") or "").upper() == normalized]
    if len(rows) != 1:
        raise OfficialEvidenceError(f"financial input must contain exactly one row for {normalized}")
    row = rows[0]
    source_facts: list[dict[str, Any]] = []
    source_documents: list[dict[str, str]] = []
    page_facts: list[dict[str, Any]] = []
    available_reports = 0
    missing_reports: list[dict[str, Any]] = []
    request_diagnostics: list[dict[str, Any]] = []
    for report in row.get("reports") or ():
        period = str(report.get("period") or "")
        status = str(report.get("status") or "")
        request_diagnostics.extend(report.get("request_diagnostics") or ())
        if period not in PERIODS:
            raise OfficialEvidenceError(f"{normalized} contains an unsupported period: {period}")
        if status == "missing":
            reason = str(report.get("reason") or "typed_missing")
            excerpt = str(report.get("raw_text_excerpt") or "").strip()
            if not excerpt:
                raise OfficialEvidenceError(f"{normalized} missing {period} has no bounded source excerpt")
            missing_reports.append({"period": period, "reason": reason, "raw_text_excerpt": excerpt[:520]})
            continue
        if status != "available":
            raise OfficialEvidenceError(f"{normalized} {period} has unknown report status: {status}")
        document = _require_document(report.get("document") or {}, ticker=normalized)
        available_reports += 1
        source_documents.append(document)
        facts = report.get("facts") or ()
        if not facts:
            missing_reports.append({
                "period": period,
                "reason": "page_facts_empty",
                "raw_text_excerpt": "official PDF identity captured but no qualifying consolidated page fact was extracted",
                "document": document,
            })
            continue
        for raw in facts:
            if str(raw.get("ticker") or "").upper() != normalized:
                raise OfficialEvidenceError(f"{normalized} fact ticker mismatch")
            if str(raw.get("document_id") or "") != document["document_id"]:
                raise OfficialEvidenceError(f"{normalized} fact document mismatch")
            if str(raw.get("raw_hash") or "") != document["raw_hash"]:
                raise OfficialEvidenceError(f"{normalized} fact raw hash mismatch")
            if str(raw.get("source_url") or "") != document["source_url"]:
                raise OfficialEvidenceError(f"{normalized} fact source URL mismatch")
            if type(raw.get("page_number")) is not int or raw["page_number"] < 1:
                raise OfficialEvidenceError(f"{normalized} fact has invalid page number")
            source_fact = dict(raw)
            source_fact["document_title"] = document["title"]
            source_fact["published_at"] = document["published_at"]
            source_facts.append(source_fact)
            page_facts.append(_round7_fact(raw, ticker=normalized, document=document))
    if not available_reports and not missing_reports:
        raise OfficialEvidenceError(f"{normalized} has no reports")
    source = {
        "schema_version": FINANCIAL_SCHEMA,
        "receipt_hash": str(receipt["receipt_hash"]),
        "input_path": None,
    }
    r7 = {
        "schema_version": ROUND7_FINANCIAL_SCHEMA,
        "data_kind": "real",
        "ticker": normalized,
        "source": source,
        "page_facts": page_facts,
    }
    r7["receipt_hash"] = digest(r7)
    return {
        "ticker": normalized,
        "financial_status": "available" if available_reports else "missing",
        "financial_receipt_hash": str(receipt["receipt_hash"]),
        "available_reports": available_reports,
        "missing_reports": missing_reports,
        "request_diagnostics": request_diagnostics,
        "source_facts": source_facts,
        "source_documents": source_documents,
        "round7_financial": r7,
        "document_ids": sorted({str(item["document_id"]) for item in source_documents}),
        "source_urls": sorted({str(item["source_url"]) for item in source_documents}),
        "raw_hashes": sorted({str(item["raw_hash"]) for item in source_documents}),
    }


def _period_window(period: str) -> tuple[str, str, str]:
    if period.endswith("FY"):
        year = int(period[:4])
        return f"{year + 1}-01-01", f"{year + 1}-12-31", "category_ndbg_szsh"
    year = int(period[:4])
    return f"{year}-01-01", str(date.today()), "category_yjdbg_szsh"


def _attempt_diagnostic(attempt: Any, *, method: str) -> dict[str, Any]:
    fetched = attempt.fetched
    raw = attempt.raw
    body_hash = hashlib.sha256(fetched.body).hexdigest() if fetched else None
    return {
        "request_id": attempt.request.request_id,
        "source_key": attempt.manifest.source_key,
        "method": method,
        "request_parameters": attempt.request.parameters,
        "source_url": (raw.source_url if raw else attempt.manifest.source_url),
        "status": attempt.status,
        "error": attempt.error,
        "http_status": fetched.status_code if fetched else None,
        "response_body_sha256": body_hash,
        "response_body_size": len(fetched.body) if fetched else None,
        "raw_hash": raw.raw_hash if raw else None,
        "started_at": attempt.started_at,
        "finished_at": attempt.finished_at,
    }


def filing_batch_diagnostics(batch: OfficialFilingBatch) -> list[dict[str, Any]]:
    """Serialize actual official attempts, including failed request evidence."""
    rows: list[dict[str, Any]] = []
    for attempt in batch.discovery.attempts:
        method = "GET" if attempt.manifest.source_key.startswith("sse_") else "POST"
        rows.append(_attempt_diagnostic(attempt, method=method))
    for outcome in batch.documents.values():
        for attempt in outcome.attempts:
            rows.append(_attempt_diagnostic(attempt, method="GET"))
    return rows


def capture_financial_period(
    ticker: str,
    period: str,
    *,
    transport: OfficialHttpTransport | None = None,
    sync: Callable[..., OfficialFilingBatch] = sync_exchange_filings,
) -> dict[str, Any]:
    """Capture and parse one issuer period through the existing official adapter."""
    normalized = _require_ticker(ticker)
    if period not in PERIODS:
        raise ValueError(f"unsupported period: {period}")
    start, end, category = _period_window(period)
    active_transport = transport or OfficialHttpTransport(timeout_seconds=5.0)
    try:
        batch = sync(
            normalized,
            authority_sink=__import__("data_core.ashare", fromlist=["MemoryAuthoritySink"]).MemoryAuthoritySink(),
            transport=active_transport,
            start_date=start,
            end_date=end,
            limit=30,
            financial_reports_only=True,
            max_documents=1,
            max_discovery_pages=1,
            category=category,
        )
    except Exception as exc:
        return {
            "period": period,
            "status": "missing",
            "reason": "official_collection_exception",
            "raw_text_excerpt": f"{type(exc).__name__}: {exc}"[:520],
            "request_diagnostics": [],
        }
    wanted = "annual_report" if period.endswith("FY") else "quarterly_report"
    selected: tuple[dict[str, Any], bytes] | None = None
    for document_id, outcome in batch.documents.items():
        for attempt in reversed(outcome.attempts):
            if not attempt.raw or not attempt.fetched or not attempt.fetched.body.startswith(b"%PDF"):
                continue
            record = next((item for item in outcome.records if str(item.payload.get("document_type")) == wanted), None)
            if record is None:
                continue
            payload = record.payload
            selected = ({
                "document_id": str(payload.get("document_id") or document_id),
                "source_url": attempt.fetched.source_url,
                "raw_hash": attempt.raw.raw_hash,
                "published_at": str(payload.get("published_at") or ""),
                "title": str(payload.get("title") or ""),
            }, attempt.fetched.body)
            break
        if selected:
            break
    diagnostics = filing_batch_diagnostics(batch)
    if selected is None:
        return {
            "period": period,
            "status": "missing",
            "reason": f"official_{wanted}_not_captured",
            "raw_text_excerpt": "official index/document attempts retained in request_diagnostics",
            "discovery_summary": batch.to_summary(),
            "request_diagnostics": diagnostics,
        }
    document, body = selected
    report = OfficialReport(period, document["document_id"], document["source_url"], ticker=normalized)
    try:
        facts = extract_report_facts(report, body)
    except Exception as exc:
        return {
            "period": period,
            "status": "missing",
            "reason": "page_parse_exception",
            "raw_text_excerpt": f"{type(exc).__name__}: {exc}"[:520],
            "document": document,
            "request_diagnostics": diagnostics,
        }
    return {
        "period": period,
        "status": "available",
        "document": document,
        "facts": [asdict(item) for item in facts],
        "request_diagnostics": diagnostics,
    }


def capture_financial_periods(
    ticker: str,
    periods: Iterable[str],
    *,
    transport: OfficialHttpTransport | None = None,
    sync: Callable[..., OfficialFilingBatch] = sync_exchange_filings,
) -> dict[str, Any]:
    normalized = _require_ticker(ticker)
    period_list = list(periods)
    reports = [capture_financial_period(normalized, period, transport=transport, sync=sync) for period in period_list]
    output: dict[str, Any] = {
        "schema_version": FINANCIAL_SCHEMA,
        "data_kind": "real",
        "cohort": [normalized],
        "periods_attempted": period_list,
        "sequential": True,
        "configured_max_concurrency": 1,
        "inter_ticker_delay_seconds": 0.0,
        "tickers": [{"ticker": normalized, "reports": reports}],
        "counts": {
            "tickers": 1,
            "facts": sum(len(item.get("facts") or ()) for item in reports),
            "available_reports": sum(item.get("status") == "available" for item in reports),
            "missing_reports": sum(item.get("status") == "missing" for item in reports),
        },
        "truth_boundary": {
            "official_cninfo_pdf_only": True,
            "page_bound_only": True,
            "does_not_promote_tier_or_action": True,
        },
    }
    output["receipt_hash"] = digest(output)
    return output


def merge_financial_receipts(receipts: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Merge bounded per-period runs without losing their source identities."""
    values = tuple(receipts)
    if not values:
        raise OfficialEvidenceError("at least one financial receipt is required")
    tickers: set[str] = set()
    reports: list[dict[str, Any]] = []
    seen_periods: set[str] = set()
    input_hashes: list[str] = []
    ticker: str | None = None
    for receipt in values:
        if receipt.get("schema_version") != FINANCIAL_SCHEMA or receipt.get("data_kind") != "real":
            raise OfficialEvidenceError("only real financial sequence receipts can be merged")
        expected = _json_hash(receipt)
        if str(receipt.get("receipt_hash") or "") != expected:
            raise OfficialEvidenceError("financial receipt hash mismatch during merge")
        rows = receipt.get("tickers") or ()
        if len(rows) != 1:
            raise OfficialEvidenceError("each merge input must contain one issuer")
        current = _require_ticker(rows[0].get("ticker"))
        tickers.add(current)
        if ticker is None:
            ticker = current
        if current != ticker:
            raise OfficialEvidenceError("financial merge inputs must share one ticker")
        for report in rows[0].get("reports") or ():
            period = str(report.get("period") or "")
            if period in seen_periods:
                raise OfficialEvidenceError(f"duplicate financial period during merge: {period}")
            seen_periods.add(period)
            reports.append(dict(report))
        input_hashes.append(str(receipt["receipt_hash"]))
    assert ticker is not None
    ordered = sorted(reports, key=lambda item: (PERIODS.index(item["period"]) if item["period"] in PERIODS else 999, item["period"]))
    output: dict[str, Any] = {
        "schema_version": FINANCIAL_SCHEMA,
        "data_kind": "real",
        "cohort": [ticker],
        "periods_attempted": [str(item["period"]) for item in ordered],
        "sequential": True,
        "configured_max_concurrency": 1,
        "inter_ticker_delay_seconds": 0.0,
        "tickers": [{"ticker": ticker, "reports": ordered}],
        "counts": {
            "tickers": 1,
            "facts": sum(len(item.get("facts") or ()) for item in ordered),
            "available_reports": sum(item.get("status") == "available" for item in ordered),
            "missing_reports": sum(item.get("status") == "missing" for item in ordered),
        },
        "truth_boundary": {
            "official_cninfo_pdf_only": True,
            "page_bound_only": True,
            "does_not_promote_tier_or_action": True,
        },
        "merged_input_receipt_hashes": sorted(input_hashes),
    }
    output["receipt_hash"] = digest(output)
    return output


def build_packet(
    financial_inputs: Mapping[str, Mapping[str, Any]],
    *,
    input_paths: Mapping[str, str] | None = None,
    narrative_inputs: Mapping[str, Mapping[str, Any]] | None = None,
    narrative_paths: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Build a deterministic, multi-issuer packet from already captured receipts."""
    narrative_inputs = narrative_inputs or {}
    input_paths = input_paths or {}
    narrative_paths = narrative_paths or {}
    companies: list[dict[str, Any]] = []
    for ticker in sorted(financial_inputs):
        normalized = _require_ticker(ticker)
        materialized = materialize_financial_receipt(financial_inputs[ticker], ticker=normalized)
        materialized["round7_financial"]["source"]["input_path"] = input_paths.get(normalized)
        materialized["round7_financial"]["receipt_hash"] = digest(
            {key: value for key, value in materialized["round7_financial"].items() if key != "receipt_hash"}
        )
        narrative = narrative_inputs.get(normalized)
        narrative_summary: dict[str, Any]
        if narrative is None:
            narrative_summary = {
                "status": "missing",
                "reason": "narrative_receipt_not_supplied",
                "path": narrative_paths.get(normalized),
            }
        else:
            narrative_hash = _narrative_hash(narrative)
            if narrative.get("schema_version") != "e4-official-narrative-evidence-v1" or narrative.get("data_kind") != "real":
                raise OfficialEvidenceError(f"{normalized} narrative receipt is not real official evidence")
            if str(narrative.get("ticker") or "").upper() != normalized:
                raise OfficialEvidenceError(f"{normalized} narrative receipt ticker mismatch")
            if str(narrative.get("receipt_hash") or "") != narrative_hash:
                raise OfficialEvidenceError(f"{normalized} narrative receipt hash mismatch")
            if str(narrative.get("source_financial_receipt_sha256") or "") != materialized["financial_receipt_hash"]:
                raise OfficialEvidenceError(f"{normalized} narrative is bound to a different financial receipt")
            if not narrative.get("reports") or not narrative.get("blocks"):
                raise OfficialEvidenceError(f"{normalized} narrative receipt is empty")
            reports_by_id = {str(item.get("document_id")): item for item in narrative["reports"]}
            for block in narrative["blocks"]:
                report = reports_by_id.get(str(block.get("document_id")))
                if report is None or str(block.get("raw_hash")) != str(report.get("raw_hash")) or str(block.get("source_url")) != str(report.get("source_url")) or not _official_url(block.get("source_url")) or type(block.get("page_number")) is not int or block["page_number"] < 1:
                    raise OfficialEvidenceError(f"{normalized} narrative block identity mismatch")
            narrative_summary = {
                "status": "available",
                "receipt_id": narrative.get("receipt_id"),
                "receipt_hash": narrative.get("receipt_hash"),
                "source_financial_receipt_sha256": narrative.get("source_financial_receipt_sha256"),
                "source_rebound_from_receipt_id": narrative.get("source_rebound_from_receipt_id"),
                "path": narrative_paths.get(normalized),
                "reports": len(narrative.get("reports") or ()),
                "blocks": len(narrative.get("blocks") or ()),
            }
        companies.append({
            **{key: value for key, value in materialized.items() if key != "round7_financial"},
            "round7_financial_path": input_paths.get(normalized),
            "round7_financial_receipt_hash": materialized["round7_financial"]["receipt_hash"],
            "round7_page_facts": materialized["round7_financial"]["page_facts"],
            "narrative": narrative_summary,
        })
    packet: dict[str, Any] = {
        "schema_version": MATERIALIZED_SCHEMA,
        "data_kind": "real",
        "companies": companies,
        "truth_boundary": {
            "official_cninfo_pdf_only": True,
            "page_bound_only": True,
            "ai_judgment": False,
            "does_not_promote_tier_or_action": True,
            "timeouts_and_missing_are_retained": True,
        },
    }
    packet["receipt_hash"] = digest(packet)
    return packet


def rebind_narrative_receipt(
    receipt: Mapping[str, Any],
    *,
    financial_receipt_hash: str,
) -> dict[str, Any]:
    """Rebind an already fetched narrative to a merged financial receipt.

    This is allowed only as a deterministic provenance transform: the
    narrative's declared CNINFO document IDs, raw hashes, URLs and pages are
    unchanged.  The returned receipt records the prior receipt identity so a
    reviewer can distinguish a rebinding from a fresh PDF fetch.
    """
    if receipt.get("schema_version") != "e4-official-narrative-evidence-v1" or receipt.get("data_kind") != "real":
        raise OfficialEvidenceError("only a real narrative receipt can be rebound")
    old_hash = _narrative_hash(receipt)
    old_id = f"e4-official-narrative-evidence-v1:{old_hash}"
    if receipt.get("receipt_hash") != old_hash or receipt.get("receipt_id") != old_id:
        raise OfficialEvidenceError("narrative receipt hash mismatch during rebinding")
    _require_sha(financial_receipt_hash, "financial_receipt_hash")
    payload = {key: value for key, value in receipt.items() if key not in {"receipt_hash", "receipt_id"}}
    payload["source_rebound_from_receipt_id"] = old_id
    payload["source_financial_receipt_sha256"] = financial_receipt_hash
    rebound_hash = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    payload["receipt_hash"] = rebound_hash
    payload["receipt_id"] = f"e4-official-narrative-evidence-v1:{rebound_hash}"
    return payload
