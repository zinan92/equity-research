"""Runtime-only, evidence-bound N3 20-company dossier batch.

This module projects the existing E3-S3 accepted positions into the existing
E3-S7/E3-S8 pipeline.  It deliberately has no valuation or recommendation
inputs: every compiled output remains ``no_action`` until later gates pass.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Callable, Iterable, Mapping

from .company_positions import CompanyPosition, REVIEW_TARGETS
from .contracts import RecordDomain, SourceManifest
from .decision_policy import DecisionInput, decide
from .dossier_generator import compile_dossier
from .evidence_gate import (
    EvidenceCandidate,
    EvidenceGatePolicy,
    EvidenceRequirement,
    EvidenceRole,
    SourceCoverageGap,
    build_context_pack,
    build_evidence_set,
)
from .industry_catalysts import CATALYST_PROFILE_SCHEMA_VERSION, SECTION_NAMES, CatalystSection, IndustryCatalystProfile
from .offline_report_model import compile_offline_report_model
from .official_filings import CNINFO_FILING_DOCUMENT_SOURCE, OfficialFilingDocumentAdapter
from .ingestion import FetchRequest


N3_DOSSIER_BATCH_SCHEMA_VERSION = "n3-dossier-batch-v1"
N3_DOSSIER_BATCH_SIZE = 20


def _digest(value: object) -> str:
    return sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def selected_positions() -> tuple[CompanyPosition, ...]:
    """Deterministically choose 20 accepted, page-cited E3-S3 positions."""

    positions = tuple(
        sorted(
            (item for item in REVIEW_TARGETS if item.status == "accepted" and item.citation is not None),
            key=lambda item: item.ticker,
        )
    )[:N3_DOSSIER_BATCH_SIZE]
    if len(positions) != N3_DOSSIER_BATCH_SIZE:
        raise ValueError("N3 batch requires 20 accepted company positions")
    return positions


def selection_identity(positions: Iterable[CompanyPosition]) -> str:
    rows = tuple(positions)
    return _digest(
        {
            "schema_version": N3_DOSSIER_BATCH_SCHEMA_VERSION,
            "positions": [asdict(item) for item in rows],
        }
    )


def _manifest(position: CompanyPosition) -> SourceManifest:
    return SourceManifest(
        source_key=CNINFO_FILING_DOCUMENT_SOURCE,
        domain_scope=RecordDomain.DOCUMENT.value,
        authority_tier="official",
        provider_version="n3-s5-runtime",
        schema_version="official-a-share-filing-v1",
        license_status="public_disclosure_internal_use",
        source_url="https://static.cninfo.com.cn/",
    )


def _missing_profile(segment_id: str, *, as_of: str) -> IndustryCatalystProfile:
    sections = tuple(
        CatalystSection(name, "missing_evidence", "No accepted current evidence is available for this section.")
        for name in SECTION_NAMES
    )
    material = {
        "schema_version": CATALYST_PROFILE_SCHEMA_VERSION,
        "segment_id": segment_id,
        "as_of": as_of[:10],
        "sections": [asdict(item) for item in sections],
    }
    identity = _digest(material)
    profile = IndustryCatalystProfile(
        "catalyst_" + identity[:40], segment_id, as_of[:10], sections, identity
    )
    profile.validate()
    return profile


def _context(position: CompanyPosition, *, known_at: str):
    assert position.citation is not None
    url, _page, raw_hash = position.citation
    manifest = _manifest(position)
    candidate = EvidenceCandidate(
        evidence_id="official-filing:" + raw_hash[:40],
        ticker=position.ticker,
        component="filings",
        role=EvidenceRole.PRIMARY,
        source_key=CNINFO_FILING_DOCUMENT_SOURCE,
        source_family="official-regulatory",
        authority_tier="official",
        independent_of_subject=False,
        status="accepted",
        known_at=known_at,
        effective_at=known_at,
        manifest_hash=manifest.manifest_hash,
        raw_hash=raw_hash,
        record_hash=_digest({"ticker": position.ticker, "url": url, "raw_hash": raw_hash}),
    )
    evidence_set = build_evidence_set(
        ticker=position.ticker,
        candidates=(candidate,),
        policy=EvidenceGatePolicy(
            as_of=known_at,
            requirements=(EvidenceRequirement("filings", min_primary=1),),
        ),
        source_gaps=(
            SourceCoverageGap("market-authority", "market", "not captured in N3 filing batch", required=False),
            SourceCoverageGap("valuation-authority", "valuation", "not captured in N3 filing batch", required=False),
            SourceCoverageGap("sell-side-authority", "sell_side", "not captured in N3 filing batch", required=False),
        ),
    )
    return build_context_pack(evidence_set)


PdfFetcher = Callable[[CompanyPosition], bytes]


def _prior_compiled_rows(
    prior_receipt: Mapping[str, object] | None,
    *,
    identity: str,
) -> dict[str, Mapping[str, object]]:
    if prior_receipt is None:
        return {}
    if prior_receipt.get("schema_version") != N3_DOSSIER_BATCH_SCHEMA_VERSION:
        raise ValueError("resume receipt schema mismatch")
    if prior_receipt.get("selection_identity") != identity:
        raise ValueError("resume receipt selection identity mismatch")
    material = dict(prior_receipt)
    receipt_hash = material.pop("receipt_hash", None)
    if not isinstance(receipt_hash, str) or receipt_hash != _digest(material):
        raise ValueError("resume receipt hash is invalid")
    rows: dict[str, Mapping[str, object]] = {}
    for row in prior_receipt.get("rows", []):
        if isinstance(row, Mapping) and row.get("status") == "compiled" and isinstance(row.get("ticker"), str):
            rows[str(row["ticker"]).upper()] = row
    return rows


def _batch_receipt(
    active: tuple[CompanyPosition, ...],
    known_at: str,
    rows: list[dict[str, object]],
    *,
    status: str,
) -> dict[str, object]:
    result = {
        "schema_version": N3_DOSSIER_BATCH_SCHEMA_VERSION,
        "status": status,
        "selection_identity": selection_identity(active),
        "known_at": known_at,
        "data_kind": "real",
        "rows": rows,
        "counts": {
            "requested": len(active),
            "resolved": len(rows),
            "compiled": sum(row["status"] == "compiled" for row in rows),
            "failed": sum(row["status"] == "failed" for row in rows),
            "no_action": sum(row.get("decision_action") == "no_action" for row in rows),
        },
        "truth_boundary": {
            "partial_evidence_bound": True,
            "counts_as_tier_a_or_b": False,
            "counts_as_full_report": False,
            "counts_as_target_or_position": False,
        },
    }
    result["receipt_hash"] = _digest(result)
    return result


def fetch_cited_pdf(position: CompanyPosition) -> bytes:
    """Fetch exactly the existing CNINFO citation; no cross-source fallback."""

    if position.citation is None:
        raise ValueError("batch position requires citation")
    url, _page, _raw_hash = position.citation
    request = FetchRequest.create(
        request_id="n3-dossier-" + position.ticker.replace(".", "-").lower(),
        domain=RecordDomain.DOCUMENT,
        entity_key=position.ticker,
        parameters={
            "document_id": "n3-s5:" + position.ticker,
            "document_url": url,
            "title": position.name + " official filing",
            "published_at": "2025-01-01T00:00:00Z",
        },
    )
    adapter = OfficialFilingDocumentAdapter(
        CNINFO_FILING_DOCUMENT_SOURCE, source_url="https://static.cninfo.com.cn/"
    )
    return asyncio.run(adapter.fetch(request)).body


def compile_position(position: CompanyPosition, *, known_at: str, fetcher: PdfFetcher = fetch_cited_pdf) -> dict[str, object]:
    """Compile one partial company dossier only after exact raw identity verification."""

    if position.citation is None:
        raise ValueError("batch position requires citation")
    url, page, expected_raw_hash = position.citation
    body = fetcher(position)
    actual_raw_hash = sha256(body).hexdigest()
    if actual_raw_hash != expected_raw_hash:
        raise ValueError("official_filing_raw_hash_mismatch")
    context = _context(position, known_at=known_at)
    dossier = compile_dossier(context, position, _missing_profile(position.segment_id, as_of=known_at))
    decision = decide(
        DecisionInput(
            ticker=position.ticker,
            context_manifest_hash=context.manifest_hash,
            dossier_id=dossier.dossier_id,
            current_price=None,
            target_price=None,
            quality_score=None,
            risk_score=None,
            liquidity_score=None,
            coverage_passed=False,
            sector_exposure=0.0,
            current_position=0.0,
            cash_weight=1.0,
        )
    )
    report = compile_offline_report_model(dossier, decision, name=position.name, exchange=position.ticker.rsplit(".", 1)[-1])
    return {
        "ticker": position.ticker,
        "status": "compiled",
        "citation": {"url": url, "page": page, "raw_hash": actual_raw_hash},
        "context_manifest_hash": context.manifest_hash,
        "dossier_id": dossier.dossier_id,
        "report_export_hash": report.export_hash,
        "decision_action": decision.action,
        "decision_receipt_hash": decision.receipt_hash,
        "gaps": ["market_price", "valuation", "quality_risk_liquidity", "sell_side", "catalyst_profile"],
    }


def compile_batch(
    *,
    known_at: str | None = None,
    fetcher: PdfFetcher = fetch_cited_pdf,
    positions: Iterable[CompanyPosition] | None = None,
    prior_receipt: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Compile a sequential batch and retain typed, non-promoted failures."""

    active = tuple(positions) if positions is not None else selected_positions()
    if len(active) != N3_DOSSIER_BATCH_SIZE:
        raise ValueError("N3 batch requires exactly 20 positions")
    if known_at is None:
        known_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    identity = selection_identity(active)
    prior_rows = _prior_compiled_rows(prior_receipt, identity=identity)
    rows = []
    for position in active:
        previous = prior_rows.get(position.ticker.upper())
        if previous is not None:
            citation = previous.get("citation")
            if isinstance(citation, Mapping) and position.citation is not None and citation.get("raw_hash") == position.citation[2]:
                rows.append(dict(previous))
                continue
        try:
            rows.append(compile_position(position, known_at=known_at, fetcher=fetcher))
        except Exception as exc:
            rows.append({"ticker": position.ticker, "status": "failed", "error": type(exc).__name__, "reason": str(exc)})
    return _batch_receipt(active, known_at, rows, status="completed")


def write_batch(runtime_root: Path, receipt: Mapping[str, object]) -> Path:
    """Write a runtime-only immutable receipt; callers own resume orchestration."""

    if receipt.get("schema_version") != N3_DOSSIER_BATCH_SCHEMA_VERSION:
        raise ValueError("unexpected N3 batch receipt schema")
    runtime_root.mkdir(parents=True, exist_ok=True)
    receipt_hash = str(receipt["receipt_hash"])
    path = runtime_root / f"n3-dossier-batch-{receipt_hash[:16]}.json"
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)
    return path


def run_checkpointed_batch(
    runtime_root: Path,
    *,
    known_at: str | None = None,
    fetcher: PdfFetcher = fetch_cited_pdf,
    positions: Iterable[CompanyPosition] | None = None,
    prior_receipt: Mapping[str, object] | None = None,
) -> tuple[dict[str, object], Path]:
    """Checkpoint after every terminal row and resume only exact compiled rows.

    The latest pointer is runtime-only.  A failed row is retried on resume;
    only a compiled row with the same selected citation raw hash is reused.
    """

    active = tuple(positions) if positions is not None else selected_positions()
    if len(active) != N3_DOSSIER_BATCH_SIZE:
        raise ValueError("N3 batch requires exactly 20 positions")
    if known_at is None:
        known_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    prior = prior_receipt or None
    prior_rows = _prior_compiled_rows(prior, identity=selection_identity(active))
    rows: list[dict[str, object]] = []
    for position in active:
        reusable = prior_rows.get(position.ticker.upper())
        if reusable is not None:
            rows.append(dict(reusable))
        else:
            try:
                rows.append(compile_position(position, known_at=known_at, fetcher=fetcher))
            except Exception as exc:
                rows.append({"ticker": position.ticker, "status": "failed", "error": type(exc).__name__, "reason": str(exc)})
        checkpoint = _batch_receipt(active, known_at, rows, status="in_progress")
        checkpoint_path = write_batch(runtime_root, checkpoint)
        (runtime_root / "n3-dossier-batch-latest.json").write_text(
            json.dumps({"status": "in_progress", "receipt": checkpoint_path.name, "receipt_hash": checkpoint["receipt_hash"]}, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    completed = _batch_receipt(active, known_at, rows, status="completed")
    completed_path = write_batch(runtime_root, completed)
    (runtime_root / "n3-dossier-batch-latest.json").write_text(
        json.dumps({"status": "completed", "receipt": completed_path.name, "receipt_hash": completed["receipt_hash"]}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return completed, completed_path


def load_resumable_batch(path: Path, *, positions: Iterable[CompanyPosition] | None = None) -> dict[str, object]:
    """Load only a receipt whose exact selected citation set still matches."""

    receipt = json.loads(path.read_text(encoding="utf-8"))
    active = tuple(positions) if positions is not None else selected_positions()
    if not isinstance(receipt, dict) or receipt.get("selection_identity") != selection_identity(active):
        raise ValueError("resume receipt selection identity mismatch")
    return receipt
