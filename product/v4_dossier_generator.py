"""Single entry point for producing a V4 reader dossier.

V4 is a document contract, not a bag of fields.  This module deliberately
accepts a complete Markdown dossier (or an official-source Round 7 sample
that can be deterministically adapted) and validates it once before writing
the publication artifact.  No field-level judgment writer is reachable from
this entry point.
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from v4_dossier_contract import V4_SCHEMA_VERSION, assert_valid_v4_dossier, validate_v4_dossier
from v4_official_adapter import (
    OfficialV4Output,
    adapt_official_sample,
    adapt_round7_dossier,
)


GENERATOR_VERSION = "park-v4-whole-dossier-generator-v1"
RECEIPT_SCHEMA_VERSION = "park-v4-whole-dossier-receipt-v1"


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha_path(path: Path) -> str:
    return _sha_bytes(path.read_bytes())


def _reader_characters(markdown: str) -> int:
    starts = [markdown.find(f"## {heading}") for heading in ("一句话定位", "产业坐标", "创始人与团队", "发展时间线", "技术、产品与商业模式", "财务与估值", "风险与点评")]
    starts = [value for value in starts if value >= 0]
    end = markdown.find("## 9. 生产记录")
    return max(0, (end if end >= 0 else len(markdown)) - min(starts, default=0))


def _official_urls(value: Mapping[str, Any]) -> tuple[str, ...]:
    urls: list[str] = []
    for item in value.get("source_urls") or value.get("sources") or ():
        if isinstance(item, str):
            urls.append(item)
        elif isinstance(item, Mapping) and isinstance(item.get("url"), str):
            urls.append(str(item["url"]))
    result = tuple(dict.fromkeys(urls))
    if not result or any(not url.startswith("https://") for url in result):
        raise ValueError("V4 production output requires HTTPS source URLs")
    return result


def publish_completed_dossier(
    *,
    ticker: str,
    markdown_path: Path,
    evidence_manifest_path: Path,
    output_dir: Path,
    status: str = "pending_human_review",
) -> dict[str, Any]:
    """Validate and persist a complete dossier produced by any company run.

    The caller supplies a whole document and its immutable evidence manifest;
    no prose is assembled from individual judgment fields here.
    """
    markdown = markdown_path.read_text(encoding="utf-8")
    assert_valid_v4_dossier(markdown)
    manifest = json.loads(evidence_manifest_path.read_text(encoding="utf-8"))
    manifest_ticker = str(manifest.get("ticker") or ticker).upper()
    if manifest_ticker != ticker.upper():
        raise ValueError("evidence manifest ticker mismatch")
    source_urls = _official_urls(manifest)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{ticker.upper()}.md"
    output_path.write_text(markdown, encoding="utf-8")
    receipt = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "contract_schema_version": V4_SCHEMA_VERSION,
        "generator_version": GENERATOR_VERSION,
        "generation_mode": "whole_dossier_publish",
        "ticker": ticker.upper(),
        "status": status,
        "is_live_research": False,
        "fresh_model_calls": int(manifest.get("fresh_model_calls", 0)),
        "new_official_documents": int(manifest.get("new_official_documents", 0)),
        "source_urls": list(source_urls),
        "input_markdown_path": str(markdown_path),
        "input_markdown_sha256": _sha_path(markdown_path),
        "evidence_manifest_path": str(evidence_manifest_path),
        "evidence_manifest_sha256": _sha_path(evidence_manifest_path),
        "output_path": str(output_path),
        "output_sha256": _sha_path(output_path),
        "characters": len(markdown),
        "reader_characters": _reader_characters(markdown),
        "tier_credit": "none",
        "upstream": manifest.get("upstream"),
        "boundary": "V4 accepts one complete dossier; unreviewed prose remains pending human review and grants no Tier/action credit.",
    }
    (output_dir / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return receipt

def generate_v4_dossier(
    *,
    ticker: str,
    output_dir: Path,
    completed_markdown_path: Path | None = None,
    evidence_manifest_path: Path | None = None,
    official_sample_path: Path | None = None,
    narrative_receipt_path: Path | None = None,
    financial_receipt_path: Path | None = None,
    round7_dossier_path: Path | None = None,
    round7_markdown_path: Path | None = None,
    round7_profile_path: Path | None = None,
) -> dict[str, Any]:
    """Generate/package one V4 dossier through the sole public entry point."""
    if completed_markdown_path is not None:
        if evidence_manifest_path is None:
            raise ValueError("evidence_manifest_path is required with completed_markdown_path")
        return publish_completed_dossier(
            ticker=ticker,
            markdown_path=completed_markdown_path,
            evidence_manifest_path=evidence_manifest_path,
            output_dir=output_dir,
        )
    if round7_dossier_path is not None:
        if round7_profile_path is None:
            raise ValueError("round7_profile_path is required with round7_dossier_path")
        if round7_markdown_path is None:
            raise ValueError("round7_markdown_path is required with round7_dossier_path")
        text, record = adapt_round7_dossier(
            ticker=ticker,
            dossier_path=round7_dossier_path,
            markdown_path=round7_markdown_path,
            profile_path=round7_profile_path,
        )
        errors = tuple(validate_v4_dossier(text))
        if errors:
            raise ValueError("generated Round 7 V4 output failed validation: " + "; ".join(errors))
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{ticker.upper()}.md"
        output_path.write_text(text, encoding="utf-8")
        record["output_path"] = str(output_path)
        record["output_sha256"] = _sha_path(output_path)
        receipt = {
            "schema_version": RECEIPT_SCHEMA_VERSION,
            "contract_schema_version": V4_SCHEMA_VERSION,
            "generator_version": GENERATOR_VERSION,
            "generation_mode": "round7_generated_whole_dossier_adaptation",
            "ticker": ticker.upper(),
            "status": record["status"],
            "is_live_research": False,
            "fresh_model_calls": record["fresh_model_calls"],
            "new_official_documents": 0,
            "source_urls": record["source_urls"],
            "output": record,
            "upstream": {
                "round7_run_id": record["round7_run_id"],
                "round7_dossier_content_hash": record["round7_dossier_content_hash"],
                "profile_hash": record["profile_hash"],
                "source_receipts": record["source_receipts"],
                "accepted_model_request_ids": record["accepted_model_request_ids"],
                "accepted_semantic_audit_request_ids": record[
                    "accepted_semantic_audit_request_ids"
                ],
                "accepted_semantic_audit_count": record[
                    "accepted_semantic_audit_count"
                ],
                "all_semantic_audit_count": record["all_semantic_audit_count"],
                "section_contract_statuses": record["section_contract_statuses"],
                "typed_gaps": record["typed_gaps"],
            },
            "output_path": str(output_path),
            "output_sha256": _sha_path(output_path),
            "tier_credit": "none",
            "boundary": "Round 7 is the sole whole-chapter generator; V4 only maps headings and preserves its official evidence/request provenance.",
        }
        (output_dir / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return receipt
    required = (official_sample_path, narrative_receipt_path, financial_receipt_path)
    if any(value is None for value in required):
        raise ValueError("provide either a complete dossier or all official adapter inputs")
    text, record = adapt_official_sample(
        ticker=ticker,
        sample_path=official_sample_path,
        narrative_receipt_path=narrative_receipt_path,
        financial_receipt_path=financial_receipt_path,
    )
    errors = tuple(validate_v4_dossier(text))
    if errors:
        raise ValueError("official V4 output failed validation: " + "; ".join(errors))
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{ticker.upper()}.md"
    output_path.write_text(text, encoding="utf-8")
    updated = OfficialV4Output(**{**asdict(record), "output_path": str(output_path)})
    receipt = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "contract_schema_version": V4_SCHEMA_VERSION,
        "generator_version": GENERATOR_VERSION,
        "generation_mode": "official_evidence_adaptation",
        "ticker": ticker.upper(),
        "status": updated.status,
        "is_live_research": False,
        "fresh_model_calls": 0,
        "new_official_documents": 0,
        "source_urls": list(updated.source_urls),
        "output": asdict(updated),
        "output_path": str(output_path),
        "output_sha256": _sha_path(output_path),
        "tier_credit": "none",
        "boundary": "Deterministic official-evidence adaptation through the unified whole-dossier entry point; no field writer or fresh model call.",
    }
    (output_dir / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return receipt
