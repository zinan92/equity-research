"""Runtime-only issuer-disclosed market-future evidence for N3 dossiers."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Iterable, Mapping
from urllib.parse import urlsplit

from .company_positions import CompanyPosition
from .document_intelligence import DocumentPage, ParserConfig, parse_pdf_document
from .n3_dossier_batch import N3_DOSSIER_BATCH_SIZE, selected_positions, selection_identity
from .n3_falsifier_evidence import _digest, _snippet, fetch_cited_pdf_with_extended_timeout


N3_MARKET_FUTURE_EVIDENCE_SCHEMA_VERSION = "n3-company-market-future-evidence-v1"
_FUTURE_MARKERS = ("未来", "预计", "将", "持续", "趋势", "前景", "规划", "需求增长", "市场空间", "发展机遇")
_MARKET_MARKERS = ("市场", "行业", "需求", "客户", "下游", "应用", "产业")


@dataclass(frozen=True)
class CompanyMarketFutureEvidence:
    ticker: str
    evidence_id: str
    source_url: str
    raw_hash: str
    page_number: int
    known_at: str
    observed_market_driver: str
    observation_type: str = "issuer_disclosed_market_outlook"

    def validate(self) -> None:
        if not re.fullmatch(r"\d{6}\.(SH|SZ|BJ)", self.ticker):
            raise ValueError("market-future evidence ticker is invalid")
        parsed = urlsplit(self.source_url)
        if parsed.scheme != "https" or not parsed.hostname or not re.fullmatch(r"[0-9a-f]{64}", self.raw_hash):
            raise ValueError("market-future evidence source identity is invalid")
        if self.page_number < 1 or not self.observed_market_driver.strip():
            raise ValueError("market-future evidence requires a page and observed driver")
        expected = "market-future:" + _digest({"ticker": self.ticker, "raw_hash": self.raw_hash, "page_number": self.page_number, "observed_market_driver": self.observed_market_driver, "observation_type": self.observation_type})[:40]
        if self.evidence_id != expected:
            raise ValueError("market-future evidence ID does not match source-bound content")


def _from_pages(position: CompanyPosition, pages: Iterable[DocumentPage], *, known_at: str) -> CompanyMarketFutureEvidence | None:
    if position.citation is None:
        raise ValueError("selected company position requires an official citation")
    source_url, _position_page, raw_hash = position.citation
    for page in pages:
        text = page.text
        marker_index = next((text.find(marker) for marker in _FUTURE_MARKERS if text.find(marker) >= 0), -1)
        if marker_index < 0 or not any(marker in text for marker in _MARKET_MARKERS):
            continue
        driver = _snippet(text, marker_index)
        material = {"ticker": position.ticker, "raw_hash": raw_hash, "page_number": page.page_number, "observed_market_driver": driver, "observation_type": "issuer_disclosed_market_outlook"}
        result = CompanyMarketFutureEvidence(position.ticker, "market-future:" + _digest(material)[:40], source_url, raw_hash, page.page_number, known_at, driver)
        result.validate()
        return result
    return None


def _collect_one(position: CompanyPosition, *, known_at: str) -> dict[str, object]:
    if position.citation is None:
        raise ValueError("selected company position requires an official citation")
    _source_url, _page, expected_raw_hash = position.citation
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            body = fetch_cited_pdf_with_extended_timeout(position)
            if sha256(body).hexdigest() != expected_raw_hash:
                raise ValueError("official_filing_raw_hash_mismatch")
            parsed = parse_pdf_document("n3-s10:" + position.ticker, body, expected_raw_hash=expected_raw_hash, config=ParserConfig(parser_version="park-document-parser-v1-native-market-future", native_text_min_chars=0), ocr_backend=None)
            evidence = _from_pages(position, parsed.pages, known_at=known_at)
            if evidence is None:
                return {"ticker": position.ticker, "status": "gap", "reason": "official_filing_has_no_explicit_market_future_driver", "raw_hash": expected_raw_hash, "fetch_attempts": attempt}
            return {"ticker": position.ticker, "status": "accepted", "evidence": asdict(evidence), "fetch_attempts": attempt}
        except (OSError, TimeoutError) as exc:
            last_error = exc
    raise RuntimeError(f"official_filing_fetch_failed_after_3_attempts: {last_error}")


def _receipt(rows: list[dict[str, object]], positions: tuple[CompanyPosition, ...], known_at: str) -> dict[str, object]:
    receipt: dict[str, object] = {"schema_version": N3_MARKET_FUTURE_EVIDENCE_SCHEMA_VERSION, "data_kind": "real", "selection_identity": selection_identity(positions), "known_at": known_at, "rows": rows, "counts": {"requested": len(positions), "resolved": len(rows), "accepted": sum(row.get("status") == "accepted" for row in rows), "gaps": sum(row.get("status") != "accepted" for row in rows)}, "truth_boundary": {"issuer_disclosed_outlook_not_market_consensus": True, "counts_as_market_future": True, "counts_as_target_or_position": False}}
    receipt["receipt_hash"] = _digest(receipt)
    return receipt


def collect_market_future_batch(runtime_root: Path, *, known_at: str | None = None, positions: Iterable[CompanyPosition] | None = None) -> dict[str, object]:
    active = tuple(positions) if positions is not None else selected_positions()
    if len(active) != N3_DOSSIER_BATCH_SIZE:
        raise ValueError("N3 market-future batch requires exactly 20 positions")
    known_at = known_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    runtime_root.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    for position in active:
        try:
            rows.append(_collect_one(position, known_at=known_at))
        except Exception as exc:
            rows.append({"ticker": position.ticker, "status": "gap", "reason": f"{type(exc).__name__}: {exc}"})
        (runtime_root / "n3-market-future-evidence-checkpoint.json").write_text(json.dumps(_receipt(rows, active, known_at), ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    receipt = _receipt(rows, active, known_at)
    path = runtime_root / f"n3-market-future-evidence-{str(receipt['receipt_hash'])[:16]}.json"
    path.write_text(json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    (runtime_root / "n3-market-future-evidence-latest.json").write_text(json.dumps({"state": "completed", "receipt": path.name, "receipt_hash": receipt["receipt_hash"]}, sort_keys=True) + "\n", encoding="utf-8")
    return {"path": str(path), "receipt": receipt}
