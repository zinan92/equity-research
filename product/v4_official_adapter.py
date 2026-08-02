"""Canonical Round 7 pass-through boundary for the V4 reader.

The former seven-section mapper was deleted.  Legacy samples remain on disk
as historical failure evidence, but no adapter function can rewrite them into
a publishable report.  Publication uses the canonical receipt/Markdown/HTML
triple plus :mod:`v4_quality_gate`.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Mapping

from data_core.round7_evidence import OFFICIAL_HOSTS, canonical_hash
from data_core.round7_profiles import load_profile
from v4_dossier_contract import validate_v4_dossier


ADAPTER_VERSION = "v4-official-adapter-retired-v3"
ROUND7_ADAPTER_VERSION = "v4-round7-canonical-pass-through-v3"


@dataclass(frozen=True)
class OfficialV4Output:
    """Historical type retained so old receipt readers fail/diagnose cleanly."""

    ticker: str
    output_path: str
    input_sample_path: str
    input_sample_sha256: str
    narrative_receipt_id: str
    narrative_receipt_hash: str
    financial_receipt_hash: str
    source_urls: tuple[str, ...]
    output_sha256: str
    characters: int
    reader_characters: int
    validation: str
    validation_errors: tuple[str, ...]
    status: str = "pending_human_review"
    generation_mode: str = "legacy_review_only"
    fresh_model_calls: int = 0
    new_official_documents: int = 0
    tier_credit: str = "none"


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _reader_characters(markdown: str) -> int:
    headings = (
        "一句话定位", "身份、创始人与治理", "技术来源与发展史",
        "商业模式与业务线", "财务与经营时间序列", "护城河的证据链",
        "风险、反题材与观察触发器", "研究结论与待补问题",
    )
    starts = [markdown.find(f"## {heading}") for heading in headings]
    starts = [value for value in starts if value >= 0]
    end = markdown.find("## 9. 生产记录")
    return max(0, (end if end >= 0 else len(markdown)) - min(starts, default=0))


def _validate_generated_round7(
    *,
    ticker: str,
    dossier: Mapping[str, object],
    profile: Mapping[str, object] | None,
) -> tuple[str, ...]:
    if dossier.get("data_kind") != "real":
        raise ValueError("Round 7 adapter requires real dossier data")
    if str(dossier.get("ticker") or "").upper() != ticker.upper():
        raise ValueError("Round 7 dossier ticker mismatch")
    review_status = str(dossier.get("review_status") or "")
    if review_status not in {"pending_human_review", "human_reviewed"}:
        raise ValueError("Round 7 dossier review state is invalid")
    expected_content = canonical_hash({
        key: value for key, value in dossier.items()
        if key not in {"content_hash", "artifacts", "receipt_hash"}
    })
    if dossier.get("content_hash") != expected_content:
        raise ValueError("Round 7 dossier content hash mismatch")
    dossier_profile = dossier.get("issuer_profile")
    if profile is not None:
        if not isinstance(dossier_profile, Mapping):
            raise ValueError("Round 7 dossier is missing issuer profile")
        if dossier_profile.get("profile_hash") != profile.get("profile_hash"):
            raise ValueError("Round 7 dossier profile hash mismatch")
    source_receipts = dossier.get("source_receipts")
    if not isinstance(source_receipts, Mapping):
        raise ValueError("Round 7 dossier is missing source receipt bindings")
    for key in (
        "official_narrative_receipt_id",
        "official_narrative_receipt_hash",
        "financial_page_evidence_receipt_hash",
    ):
        if not str(source_receipts.get(key) or ""):
            raise ValueError(f"Round 7 source receipt field missing: {key}")
    production = dossier.get("production_record")
    if not isinstance(production, Mapping):
        raise ValueError("Round 7 dossier production record is invalid")
    if profile is not None:
        if source_receipts.get("as_of") != production.get("known_at"):
            raise ValueError("Round 7 source receipt cutoff does not match known_at")
        expected_sources = profile.get("source_receipts") or {}
        actual_sources = {
            "narrative_receipt_hash": source_receipts.get("official_narrative_receipt_hash"),
            "financial_receipt_hash": source_receipts.get("financial_page_evidence_receipt_hash"),
        }
        for key, expected in expected_sources.items():
            if key in actual_sources and actual_sources[key] != expected:
                raise ValueError(f"Round 7 profile receipt binding mismatch: {key}")
    source_urls: list[str] = []
    source_manifest = dossier.get("source_manifest")
    if not isinstance(source_manifest, list):
        raise ValueError("Round 7 source manifest is invalid")
    for item in source_manifest:
        if not isinstance(item, Mapping):
            raise ValueError("Round 7 source manifest row is invalid")
        url = str(item.get("source_url") or "")
        parsed = url.split("/", 3)
        if len(parsed) < 3 or not url.startswith("https://") or parsed[2] not in OFFICIAL_HOSTS:
            raise ValueError("Round 7 source manifest contains a non-official URL")
        pages = item.get("pages_used")
        if not isinstance(pages, list) or not pages or any(type(page) is not int or page < 1 for page in pages):
            raise ValueError("Round 7 source manifest page binding is invalid")
        if len(str(item.get("raw_hash") or "")) != 64:
            raise ValueError("Round 7 source manifest raw hash is invalid")
        source_urls.append(url)
    if not source_urls:
        raise ValueError("Round 7 source manifest is empty")
    chapters = dossier.get("chapters")
    if not isinstance(chapters, list) or len(chapters) != 8:
        raise ValueError("Round 7 adapter requires eight research chapters")
    if any(not isinstance(item, Mapping) or item.get("review_status") != review_status for item in chapters):
        raise ValueError("Round 7 adapter requires eight chapters with a uniform review state")
    accepted_ids = list(production.get("accepted_model_request_ids") or [])
    if accepted_ids and (len(accepted_ids) != len(chapters) or len(set(accepted_ids)) != len(chapters)):
        raise ValueError("Round 7 adapter requires one accepted request ID per chapter")
    accepted_audits = production.get("accepted_semantic_audits")
    if accepted_audits is not None and int(accepted_audits or 0) != len(chapters):
        raise ValueError("Round 7 adapter requires a passing semantic audit per chapter")
    typed_gaps = production.get("typed_gaps")
    if typed_gaps is not None and not isinstance(typed_gaps, list):
        raise ValueError("Round 7 adapter requires structured typed gaps")
    tier = dossier.get("degradation", {}).get("tier") if isinstance(dossier.get("degradation"), Mapping) else None
    if tier not in {"A", "B"} or (review_status == "pending_human_review" and tier != "B"):
        raise ValueError("Round 7 dossier must carry an explicit A/B Tier")
    return tuple(dict.fromkeys(source_urls))


def adapt_round7_dossier(
    *,
    ticker: str,
    dossier_path: Path,
    markdown_path: Path,
    profile_path: Path | None = None,
) -> tuple[str, dict[str, object]]:
    """Pass through one complete canonical Round 7 document unchanged."""
    dossier = json.loads(dossier_path.read_text(encoding="utf-8"))
    profile = load_profile(profile_path, ticker=ticker) if profile_path else None
    if profile is not None and str(profile.get("ticker") or "").upper() not in {"", ticker.upper()}:
        raise ValueError("Round 7 profile ticker mismatch")
    source_urls = _validate_generated_round7(ticker=ticker, dossier=dossier, profile=profile)
    review_status = str(dossier.get("review_status") or "")
    sample = markdown_path.read_text(encoding="utf-8")
    canonical_errors = tuple(validate_v4_dossier(sample))
    if canonical_errors:
        raise ValueError(
            "legacy V4 section headings are review-only and cannot enter the production adapter: "
            + "; ".join(canonical_errors)
        )
    production = dossier["production_record"]
    source_receipts = dossier["source_receipts"]
    profile_hash = (dossier.get("issuer_profile") or {}).get("profile_hash")
    return sample, {
        "ticker": ticker.upper(),
        "input_dossier_path": str(dossier_path),
        "input_dossier_sha256": _sha_bytes(dossier_path.read_bytes()),
        "input_markdown_path": str(markdown_path),
        "input_markdown_sha256": _sha_bytes(sample.encode("utf-8")),
        "round7_run_id": production.get("run_id"),
        "round7_dossier_content_hash": dossier.get("content_hash"),
        "profile_hash": profile_hash,
        "source_receipts": dict(source_receipts),
        "accepted_model_request_ids": list(production.get("accepted_model_request_ids") or []),
        "accepted_semantic_audit_request_ids": list(production.get("accepted_semantic_audit_request_ids") or []),
        "accepted_semantic_audit_count": int(production.get("accepted_semantic_audits") or 0),
        "all_semantic_audit_count": int(production.get("all_semantic_audits") or 0),
        "section_contract_statuses": list(production.get("section_contract_statuses") or []),
        "typed_gaps": list(production.get("typed_gaps") or []),
        "source_urls": list(source_urls),
        "output_sha256": _sha_bytes(sample.encode("utf-8")),
        "characters": len(sample),
        "reader_characters": _reader_characters(sample),
        "validation": "passed",
        "validation_errors": [],
        "status": review_status,
        "generation_mode": "round7_canonical_pass_through",
        "fresh_model_calls": int(production.get("accepted_model_calls") or 0),
        "new_official_documents": 0,
        "tier_credit": "none",
    }


def adapt_official_sample(*, ticker: str, sample_path: Path, narrative_receipt_path: Path, financial_receipt_path: Path) -> tuple[str, OfficialV4Output]:
    """Retired legacy entry point; it cannot rewrite a sample into V4."""
    raise ValueError(
        "legacy official sample adapter is retired; use canonical Round 7 receipt/markdown/profile"
    )


def write_official_outputs(rows: Mapping[str, tuple[str, OfficialV4Output]], output_dir: Path) -> dict[str, object]:
    """Retired legacy writer; no output is written."""
    raise ValueError(
        "legacy official output writer is retired; use publish_v4_round7_dossier.py"
    )
