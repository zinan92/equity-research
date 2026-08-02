"""Single entry point for producing a V4 reader dossier.

V4 is a document contract, not a bag of fields.  This module deliberately
accepts a canonical Round 7 receipt/Markdown/profile and validates it once
before writing a package artifact.  No field-level
judgment writer or legacy heading mapper is reachable from this entry point.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from v4_dossier_contract import V4_SCHEMA_VERSION, validate_v4_dossier
from v4_quality_gate import CANONICAL_SOURCE_DIR, evaluate_round7_quality
from v4_official_adapter import (
    adapt_round7_dossier,
)


GENERATOR_VERSION = "park-v4-whole-dossier-generator-v1"
RECEIPT_SCHEMA_VERSION = "park-v4-whole-dossier-receipt-v1"


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha_path(path: Path) -> str:
    return _sha_bytes(path.read_bytes())


def _reader_characters(markdown: str) -> int:
    starts = [markdown.find(f"## {heading}") for heading in (
        "一句话定位", "身份、创始人与治理", "技术来源与发展史",
        "商业模式与业务线", "财务与经营时间序列", "护城河的证据链",
        "风险、反题材与观察触发器", "研究结论与待补问题",
    )]
    starts = [value for value in starts if value >= 0]
    end = markdown.find("## 9. 生产记录")
    return max(0, (end if end >= 0 else len(markdown)) - min(starts, default=0))


def publish_completed_dossier(
    *,
    ticker: str,
    markdown_path: Path,
    evidence_manifest_path: Path,
    output_dir: Path,
    status: str = "pending_human_review",
) -> dict[str, Any]:
    """Retired escape hatch kept only to return a typed migration error."""
    raise ValueError(
        "completed_markdown_path is retired; production requires the canonical "
        "Round 7 receipt/markdown/html and v4_quality_gate"
    )
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
        upstream_quality_gate = evaluate_round7_quality(
            dossier_path=round7_dossier_path,
            markdown_path=round7_markdown_path,
            html_path=round7_markdown_path.with_suffix(".html"),
            require_canonical_root=True,
            expected_ticker=ticker,
        )
        if upstream_quality_gate.get("publication_eligible") is not True:
            raise ValueError(
                "canonical Round 7 quality gate blocked packaging: "
                + "; ".join(str(item.get("code")) for item in upstream_quality_gate.get("blockers", [])[:8])
            )
        output_dir = output_dir.resolve()
        try:
            output_dir.relative_to(CANONICAL_SOURCE_DIR.resolve())
        except ValueError:
            pass
        else:
            raise ValueError("generated V4 package must not be written inside canonical Round 7 source root")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{ticker.upper()}.md"
        output_path.write_text(text, encoding="utf-8")
        record["output_path"] = str(output_path)
        record["quality_gate_status"] = upstream_quality_gate["status"]
        record["quality_gate_receipt_hash"] = upstream_quality_gate["receipt_hash"]
        output_sha256 = _sha_path(output_path)
        record["output_sha256"] = output_sha256
        source_html_path = round7_markdown_path.with_suffix(".html")
        receipt = {
            "schema_version": RECEIPT_SCHEMA_VERSION,
            "contract_schema_version": V4_SCHEMA_VERSION,
            "generator_version": GENERATOR_VERSION,
            "generation_mode": "round7_canonical_pass_through",
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
            "output_sha256": output_sha256,
            "output_content_hash": _sha_bytes(text.encode("utf-8")),
            "artifacts": {
                "markdown_path": str(output_path),
                "markdown_sha256": output_sha256,
                "source_html_path": str(source_html_path),
                "source_html_sha256": _sha_path(source_html_path),
            },
            "tier_credit": "none",
            "quality_gate": upstream_quality_gate,
            "boundary": "Round 7 is the sole whole-chapter generator; V4 passes the exact nine-chapter artifact through unchanged and preserves official evidence/request provenance.",
        }
        receipt["receipt_hash"] = hashlib.sha256(
            json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        (output_dir / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return receipt
    if any(value is not None for value in (official_sample_path, narrative_receipt_path, financial_receipt_path)):
        raise ValueError(
            "legacy official adapter inputs are retired; provide canonical Round 7 "
            "receipt/markdown/profile instead"
        )
    raise ValueError(
        "provide canonical Round 7 receipt/markdown/profile; field-level and legacy "
        "adapter generation is retired"
    )
