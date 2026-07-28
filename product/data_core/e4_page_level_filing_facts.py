"""Small, fail-closed bridge from official filing pages to E4 report facts.

This deliberately uses B3's ``parse_pdf_document`` output.  It does not use
structured aggregators and it never changes an E4 decision boundary.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from typing import Any, Iterable

from .contracts import digest
from .document_intelligence import DocumentPage, parse_pdf_document
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
        # This is a deliberately narrow Report Model projection: it carries
        # only the filing fact and preserves a no-action boundary.  It must
        # not be mistaken for a complete E4 model or a recommendation.
        "report_models": [
            {"ticker": row["ticker"], "data_kind": "real", "decision_boundary": {"tier": "C", "action": "no_action", "target_price": None, "position_range": None},
             "page_level_numeric_facts": [row["fact"]]}
            for row in rows if row["status"] == "available"
        ],
        "counts": {"companies": len(rows), "available": sum(row["status"] == "available" for row in rows),
                   "missing": sum(row["status"] == "missing" for row in rows)},
        "truth_boundary": {"page_bound_primary_facts_only": True, "does_not_promote_tier_or_action": True,
                           "does_not_complete_e4_s4": True},
    }
    output["receipt_hash"] = digest(output)
    return output
