"""Runtime-only, page-bound company moat evidence for the N3 dossier set."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping
from urllib.parse import urlsplit

from .company_positions import CompanyPosition
from .document_intelligence import DocumentPage, ParserConfig, parse_pdf_document
from .n3_dossier_batch import N3_DOSSIER_BATCH_SIZE, selected_positions, selection_identity
from .n3_falsifier_evidence import _digest, _snippet, fetch_cited_pdf_with_extended_timeout


N3_MOAT_EVIDENCE_SCHEMA_VERSION = "n3-company-moat-evidence-v1"
_MOAT_MARKERS = ("核心竞争力", "竞争优势", "领先优势", "技术优势", "核心技术", "行业领先", "市场领先", "护城河")
_CONCRETE_MARKERS = ("客户", "技术", "专利", "认证", "资质", "规模", "成本", "研发", "市场份额", "产能", "供应链")


@dataclass(frozen=True)
class CompanyMoatEvidence:
    ticker: str
    evidence_id: str
    source_url: str
    raw_hash: str
    page_number: int
    known_at: str
    observed_capability: str

    def validate(self) -> None:
        if not re.fullmatch(r"\d{6}\.(SH|SZ|BJ)", self.ticker):
            raise ValueError("moat evidence ticker is invalid")
        parsed = urlsplit(self.source_url)
        if parsed.scheme != "https" or not parsed.hostname or not re.fullmatch(r"[0-9a-f]{64}", self.raw_hash):
            raise ValueError("moat evidence source identity is invalid")
        if self.page_number < 1 or not self.observed_capability.strip():
            raise ValueError("moat evidence requires a page and observed capability")
        expected = "moat:" + _digest({"ticker": self.ticker, "raw_hash": self.raw_hash, "page_number": self.page_number, "observed_capability": self.observed_capability})[:40]
        if self.evidence_id != expected:
            raise ValueError("moat evidence ID does not match source-bound content")


def _from_pages(position: CompanyPosition, pages: Iterable[DocumentPage], *, known_at: str) -> CompanyMoatEvidence | None:
    if position.citation is None:
        raise ValueError("selected company position requires an official citation")
    source_url, _position_page, raw_hash = position.citation
    for page in pages:
        text = page.text
        marker_index = next((text.find(marker) for marker in _MOAT_MARKERS if text.find(marker) >= 0), -1)
        if marker_index < 0 or not any(marker in text for marker in _CONCRETE_MARKERS):
            continue
        capability = _snippet(text, marker_index)
        material = {"ticker": position.ticker, "raw_hash": raw_hash, "page_number": page.page_number, "observed_capability": capability}
        evidence = CompanyMoatEvidence(position.ticker, "moat:" + _digest(material)[:40], source_url, raw_hash, page.page_number, known_at, capability)
        evidence.validate()
        return evidence
    return None


def collect_position_moat(position: CompanyPosition, *, known_at: str) -> dict[str, object]:
    if position.citation is None:
        raise ValueError("selected company position requires an official citation")
    source_url, _position_page, expected_raw_hash = position.citation
    body = fetch_cited_pdf_with_extended_timeout(position)
    from hashlib import sha256
    if sha256(body).hexdigest() != expected_raw_hash:
        raise ValueError("official_filing_raw_hash_mismatch")
    parsed = parse_pdf_document("n3-s9:" + position.ticker, body, expected_raw_hash=expected_raw_hash, config=ParserConfig(parser_version="park-document-parser-v1-native-moat", native_text_min_chars=0), ocr_backend=None)
    evidence = _from_pages(position, parsed.pages, known_at=known_at)
    if evidence is None:
        return {"ticker": position.ticker, "status": "gap", "reason": "official_filing_has_no_explicit_concrete_moat_capability", "raw_hash": expected_raw_hash}
    return {"ticker": position.ticker, "status": "accepted", "evidence": asdict(evidence)}


def collect_moat_batch(runtime_root: Path, *, known_at: str | None = None, positions: Iterable[CompanyPosition] | None = None) -> dict[str, object]:
    active = tuple(positions) if positions is not None else selected_positions()
    if len(active) != N3_DOSSIER_BATCH_SIZE:
        raise ValueError("N3 moat batch requires exactly 20 positions")
    known_at = known_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    runtime_root.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    for position in active:
        try:
            rows.append(collect_position_moat(position, known_at=known_at))
        except Exception as exc:
            rows.append({"ticker": position.ticker, "status": "gap", "reason": f"{type(exc).__name__}: {exc}"})
        checkpoint = _receipt(rows, active, known_at)
        (runtime_root / "n3-moat-evidence-checkpoint.json").write_text(json.dumps(checkpoint, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    receipt = _receipt(rows, active, known_at)
    path = runtime_root / f"n3-moat-evidence-{str(receipt['receipt_hash'])[:16]}.json"
    path.write_text(json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    (runtime_root / "n3-moat-evidence-latest.json").write_text(json.dumps({"state": "completed", "receipt": path.name, "receipt_hash": receipt["receipt_hash"]}, sort_keys=True) + "\n", encoding="utf-8")
    return {"path": str(path), "receipt": receipt}


def _receipt(rows: list[dict[str, object]], positions: tuple[CompanyPosition, ...], known_at: str) -> dict[str, object]:
    result = {"schema_version": N3_MOAT_EVIDENCE_SCHEMA_VERSION, "data_kind": "real", "selection_identity": selection_identity(positions), "known_at": known_at, "rows": rows, "counts": {"requested": len(positions), "resolved": len(rows), "accepted": sum(row.get("status") == "accepted" for row in rows), "gaps": sum(row.get("status") != "accepted" for row in rows)}, "truth_boundary": {"issuer_disclosed_capability_not_investment_recommendation": True, "counts_as_market_future": False, "counts_as_target_or_position": False}}
    result["receipt_hash"] = _digest(result)
    return result
