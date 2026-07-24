"""Runtime-only, page-bound company falsifier evidence for the N3 dossier set."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Callable, Iterable, Mapping
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from .company_positions import CompanyPosition
from .document_intelligence import DocumentPage, ParserConfig, parse_pdf_document
from .n3_dossier_batch import N3_DOSSIER_BATCH_SIZE, selected_positions, selection_identity
from .official_filings import CNINFO_FILING_DOCUMENT_SOURCE, OfficialFilingDocumentAdapter, validate_official_source_role


N3_FALSIFIER_EVIDENCE_SCHEMA_VERSION = "n3-company-falsifier-evidence-v1"
N3_FALSIFIER_EVIDENCE_MAX_FETCH_ATTEMPTS = 3
_RISK_MARKERS = ("风险因素", "风险提示", "主要风险", "风险")
_WEAKENING_MARKERS = (
    "不利", "下降", "波动", "未达", "未能", "不能", "失败", "减值", "依赖",
    "竞争", "替代", "亏损", "下滑", "恶化", "不确定",
)
PdfFetcher = Callable[[CompanyPosition], bytes]


def _digest(value: object) -> str:
    return sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def fetch_cited_pdf_with_extended_timeout(position: CompanyPosition) -> bytes:
    """Fetch the same CNINFO document in bounded, resumable HTTP ranges.

    CNINFO can terminate a single long annual-report download. Each range is
    still requested from the same allowlisted official URL, and no bytes are
    accepted until the assembled PDF matches the pre-existing citation hash.
    """
    if position.citation is None:
        raise ValueError("selected company position requires an official citation")
    url, _page, _raw_hash = position.citation
    adapter = OfficialFilingDocumentAdapter(
        CNINFO_FILING_DOCUMENT_SOURCE,
        source_url="https://static.cninfo.com.cn/",
    )
    validate_official_source_role(adapter.manifest, url)
    chunk_size = 1024 * 1024
    chunks: list[bytes] = []
    start = 0
    total: int | None = None
    while total is None or start < total:
        end = start + chunk_size - 1
        request = Request(
            url,
            headers={
                "User-Agent": "ParkEquityResearch/1.0",
                "Accept": "application/pdf",
                "Range": f"bytes={start}-{end}",
            },
        )
        with urlopen(request, timeout=35.0) as response:
            final_url = response.geturl()
            validate_official_source_role(adapter.manifest, final_url)
            content_range = str(response.headers.get("Content-Range") or "")
            matched = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", content_range)
            if response.status != 206 or not matched:
                raise ValueError("official_filing_range_response_invalid")
            left, right, reported_total = (int(item) for item in matched.groups())
            if left != start or right < left or right > end:
                raise ValueError("official_filing_range_boundary_invalid")
            if total is None:
                total = reported_total
            elif total != reported_total:
                raise ValueError("official_filing_range_total_changed")
            body = response.read()
            if len(body) != right - left + 1:
                raise ValueError("official_filing_range_body_length_invalid")
            chunks.append(body)
            start = right + 1
    return b"".join(chunks)


def _snippet(text: str, start: int, *, limit: int = 320) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    left = max(0, start - 80)
    right = min(len(compact), start + limit)
    candidate = compact[left:right]
    if left:
        candidate = "…" + candidate
    if right < len(compact):
        candidate += "…"
    return candidate


@dataclass(frozen=True)
class CompanyFalsifierEvidence:
    ticker: str
    evidence_id: str
    source_url: str
    raw_hash: str
    page_number: int
    known_at: str
    observed_condition: str

    def validate(self) -> None:
        if not re.fullmatch(r"\d{6}\.(SH|SZ|BJ)", self.ticker):
            raise ValueError("falsifier evidence ticker is invalid")
        parsed = urlsplit(self.source_url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("falsifier evidence requires an HTTPS source URL")
        if not re.fullmatch(r"[0-9a-f]{64}", self.raw_hash):
            raise ValueError("falsifier evidence raw hash is invalid")
        if self.page_number < 1 or not self.observed_condition.strip():
            raise ValueError("falsifier evidence requires a page and observed condition")
        expected = "falsifier:" + _digest(
            {
                "ticker": self.ticker,
                "raw_hash": self.raw_hash,
                "page_number": self.page_number,
                "observed_condition": self.observed_condition,
            }
        )[:40]
        if self.evidence_id != expected:
            raise ValueError("falsifier evidence ID does not match its source-bound content")


def _falsifier_from_pages(position: CompanyPosition, pages: Iterable[DocumentPage], *, known_at: str) -> CompanyFalsifierEvidence | None:
    if position.citation is None:
        raise ValueError("selected company position requires an official citation")
    source_url, _position_page, expected_raw_hash = position.citation
    for page in pages:
        text = page.text
        risk_index = next((text.find(marker) for marker in _RISK_MARKERS if text.find(marker) >= 0), -1)
        if risk_index < 0 or not any(marker in text for marker in _WEAKENING_MARKERS):
            continue
        condition = _snippet(text, risk_index)
        material = {
            "ticker": position.ticker,
            "raw_hash": expected_raw_hash,
            "page_number": page.page_number,
            "observed_condition": condition,
        }
        evidence = CompanyFalsifierEvidence(
            ticker=position.ticker,
            evidence_id="falsifier:" + _digest(material)[:40],
            source_url=source_url,
            raw_hash=expected_raw_hash,
            page_number=page.page_number,
            known_at=known_at,
            observed_condition=condition,
        )
        evidence.validate()
        return evidence
    return None


def collect_position_falsifier(
    position: CompanyPosition,
    *,
    known_at: str,
    fetcher: PdfFetcher = fetch_cited_pdf_with_extended_timeout,
) -> dict[str, object]:
    """Fetch the cited official PDF and extract one source-bound risk condition."""

    if position.citation is None:
        raise ValueError("selected company position requires an official citation")
    source_url, _position_page, expected_raw_hash = position.citation
    last_error: Exception | None = None
    for attempt in range(1, N3_FALSIFIER_EVIDENCE_MAX_FETCH_ATTEMPTS + 1):
        try:
            body = fetcher(position)
            actual_raw_hash = sha256(body).hexdigest()
            if actual_raw_hash != expected_raw_hash:
                raise ValueError("official_filing_raw_hash_mismatch")
            parsed = parse_pdf_document(
                "n3-s8:" + position.ticker,
                body,
                expected_raw_hash=expected_raw_hash,
                # A falsifier needs one readable, page-bound issuer statement.
                # Do not OCR every weak/blank annual-report page during a
                # runtime batch; unreadable pages remain unavailable evidence.
                config=ParserConfig(
                    parser_version="park-document-parser-v1-native-falsifier",
                    native_text_min_chars=0,
                ),
                ocr_backend=None,
            )
            evidence = _falsifier_from_pages(position, parsed.pages, known_at=known_at)
            if evidence is None:
                return {
                    "ticker": position.ticker,
                    "status": "gap",
                    "reason": "official_filing_has_no_explicit_observable_risk_condition",
                    "raw_hash": actual_raw_hash,
                    "fetch_attempts": attempt,
                }
            return {
                "ticker": position.ticker,
                "status": "accepted",
                "evidence": asdict(evidence),
                "fetch_attempts": attempt,
            }
        except (OSError, TimeoutError) as exc:
            last_error = exc
    if last_error is not None:
        raise RuntimeError(
            f"official_filing_fetch_failed_after_{N3_FALSIFIER_EVIDENCE_MAX_FETCH_ATTEMPTS}_attempts: {last_error}"
        )
    raise RuntimeError("official_filing_falsifier_collection_failed")


def _receipt(rows: list[dict[str, object]], *, positions: tuple[CompanyPosition, ...], known_at: str) -> dict[str, object]:
    receipt = {
        "schema_version": N3_FALSIFIER_EVIDENCE_SCHEMA_VERSION,
        "data_kind": "real",
        "selection_identity": selection_identity(positions),
        "known_at": known_at,
        "rows": rows,
        "counts": {
            "requested": len(positions),
            "resolved": len(rows),
            "accepted": sum(row.get("status") == "accepted" for row in rows),
            "gaps": sum(row.get("status") != "accepted" for row in rows),
        },
        "truth_boundary": {
            "issuer_disclosed_risk_not_investment_recommendation": True,
            "counts_as_moat": False,
            "counts_as_market_future": False,
            "counts_as_target_or_position": False,
        },
    }
    receipt["receipt_hash"] = _digest(receipt)
    return receipt


def collect_falsifier_batch(
    runtime_root: Path,
    *,
    known_at: str | None = None,
    fetcher: PdfFetcher = fetch_cited_pdf_with_extended_timeout,
    positions: Iterable[CompanyPosition] | None = None,
) -> dict[str, object]:
    """Collect the exact 20-company N3 selection; failures remain typed gaps."""

    active = tuple(positions) if positions is not None else selected_positions()
    if len(active) != N3_DOSSIER_BATCH_SIZE:
        raise ValueError("N3 falsifier batch requires exactly 20 positions")
    known_at = known_at or _now()
    rows: list[dict[str, object]] = []
    runtime_root.mkdir(parents=True, exist_ok=True)
    for position in active:
        try:
            rows.append(collect_position_falsifier(position, known_at=known_at, fetcher=fetcher))
        except Exception as exc:
            rows.append({"ticker": position.ticker, "status": "gap", "reason": f"{type(exc).__name__}: {exc}"})
        checkpoint = _receipt(rows, positions=active, known_at=known_at)
        (runtime_root / "n3-falsifier-evidence-checkpoint.json").write_text(
            json.dumps(checkpoint, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    receipt = _receipt(rows, positions=active, known_at=known_at)
    path = runtime_root / f"n3-falsifier-evidence-{str(receipt['receipt_hash'])[:16]}.json"
    path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (runtime_root / "n3-falsifier-evidence-latest.json").write_text(
        json.dumps({"state": "completed", "receipt": path.name, "receipt_hash": receipt["receipt_hash"]}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {"path": str(path), "receipt": receipt}
