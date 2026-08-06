#!/usr/bin/env python3
"""Verify a generated Round 7 dossier and its production receipts."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product"))

from data_core.round7_chapter_generator import (  # noqa: E402
    DOSSIER_SCHEMA_VERSION,
    REVIEW_QUEUE_SCHEMA_VERSION,
    build_chapter_request,
    validate_chapter,
)
from data_core.round7_evidence import OFFICIAL_HOSTS, canonical_hash  # noqa: E402
from data_core.round7_profiles import profile_hash  # noqa: E402
from data_core.round7_north_star import verify_round7_document  # noqa: E402
from report_contract import RESEARCH_SECTION_SPECS_V3  # noqa: E402


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _is_persistent_artifact(declared_value: object, actual: Path) -> bool:
    """Compare a receipt path by stable repo identity, not checkout prefix.

    Historical receipts froze the absolute path of the checkout that generated
    them.  A Git worktree or CI clone has a different prefix while preserving
    the exact repository-relative artifact.  Content hashes remain the primary
    identity; this guard additionally rejects temp declarations and wrong
    repo-relative locations.
    """

    raw = str(declared_value or "").strip()
    if not raw:
        return False
    declared = Path(raw)
    if declared.is_absolute() and str(declared).startswith(("/tmp/", "/private/tmp/")):
        return False
    try:
        relative_actual = actual.resolve().relative_to(ROOT.resolve())
    except ValueError:
        return False
    if declared.is_absolute():
        if len(declared.parts) < len(relative_actual.parts):
            return False
        return tuple(declared.parts[-len(relative_actual.parts):]) == relative_actual.parts
    return declared == relative_actual


def verify(ticker: str, directory: Path) -> dict:
    receipt_path = directory / f"{ticker}.receipt.json"
    markdown_path = directory / f"{ticker}.md"
    html_path = directory / f"{ticker}.html"
    review_path = directory / f"{ticker}.review-queue.json"
    problems: list[str] = []
    for path in (receipt_path, markdown_path, html_path, review_path):
        if not path.is_file():
            problems.append(f"missing artifact: {path}")
    if problems:
        return {"ticker": ticker, "passed": False, "problems": problems}

    dossier = json.loads(receipt_path.read_text(encoding="utf-8"))
    queue = json.loads(review_path.read_text(encoding="utf-8"))
    if dossier.get("schema_version") != DOSSIER_SCHEMA_VERSION:
        problems.append("dossier schema mismatch")
    if dossier.get("ticker") != ticker or dossier.get("data_kind") != "real":
        problems.append("dossier identity is not real and ticker-bound")
    issuer_profile = dossier.get("issuer_profile")
    if issuer_profile is not None:
        if issuer_profile.get("profile_hash") != profile_hash(issuer_profile):
            problems.append("issuer profile hash mismatch")
        if dossier.get("production_record", {}).get("issuer_profile_hash") != issuer_profile.get("profile_hash"):
            problems.append("production record profile hash mismatch")
        if dossier.get("source_receipts", {}).get("issuer_profile_hash") != issuer_profile.get("profile_hash"):
            problems.append("source receipt profile hash mismatch")
    production = dossier.get("production_record", {})
    source_receipts = dossier.get("source_receipts", {})
    if issuer_profile is not None:
        known_at = production.get("known_at")
        if not known_at:
            problems.append("profiled dossier is missing explicit known_at")
        if source_receipts.get("as_of") != known_at:
            problems.append("source receipt cutoff does not match production known_at")
        expected_sources = issuer_profile.get("source_receipts") or {}
        actual_sources = {
            "narrative_receipt_hash": source_receipts.get(
                "official_narrative_receipt_hash"
            ),
            "financial_receipt_hash": source_receipts.get(
                "financial_page_evidence_receipt_hash"
            ),
        }
        for key, expected in expected_sources.items():
            if key in actual_sources and actual_sources[key] != expected:
                problems.append(f"profile source receipt binding mismatch: {key}")
    expected_receipt_hash = canonical_hash(
        {key: value for key, value in dossier.items() if key != "receipt_hash"}
    )
    if dossier.get("receipt_hash") != expected_receipt_hash:
        problems.append("dossier receipt hash mismatch")
    expected_content_hash = canonical_hash(
        {
            key: value
            for key, value in dossier.items()
            if key not in {"content_hash", "artifacts", "receipt_hash"}
        }
    )
    if dossier.get("content_hash") != expected_content_hash:
        problems.append("dossier content hash mismatch")
    artifacts = dossier.get("artifacts") or {}
    if artifacts.get("markdown_sha256") != _sha(markdown_path):
        problems.append("markdown hash mismatch")
    if artifacts.get("html_sha256") != _sha(html_path):
        problems.append("HTML hash mismatch")
    for key, actual in (
        ("markdown_path", markdown_path),
        ("html_path", html_path),
    ):
        if not _is_persistent_artifact(artifacts.get(key), actual):
            problems.append(f"{key} is not the persistent artifact")

    north_star = verify_round7_document(markdown_path)
    warnings = []
    for item in north_star.problems:
        if item == "fewer than two source rows":
            warnings.append("north_star: one official source document; coverage remains partial")
        else:
            problems.append("north_star: " + item)

    expected_ids = [spec.section_id for spec in RESEARCH_SECTION_SPECS_V3[:-1]]
    chapters = dossier.get("chapters") or []
    if [item.get("section_id") for item in chapters] != expected_ids:
        problems.append("model chapters do not match the exact Round 7 order")
    registry = dossier.get("evidence_registry") or {}
    prior_context: list[dict] = []
    for spec, chapter in zip(RESEARCH_SECTION_SPECS_V3[:-1], chapters):
        request = build_chapter_request(
            spec=spec,
            issuer=dossier["issuer"],
            evidence=list(registry.values()),
            prior_chapter_context=(
                prior_context
                if spec.section_id == "research_conclusion_and_open_questions"
                else ()
            ),
            profile=issuer_profile,
        )
        chapter_problems = validate_chapter(
            {
                "section_id": chapter.get("section_id"),
                "rows": chapter.get("rows"),
            },
            request=request,
            registry=registry,
        )
        problems.extend(
            f"{spec.section_id}: {item}" for item in chapter_problems
        )
        observed_characters = sum(
            len(str(cell.get("text") or ""))
            for row in chapter.get("rows") or []
            for cell in row.get("cells") or []
        )
        if chapter.get("character_count") != observed_characters:
            problems.append(f"{spec.section_id}: character count mismatch")
        expected_chapter_hash = canonical_hash(
            {"section_id": chapter.get("section_id"), "rows": chapter.get("rows")}
        )
        if chapter.get("content_hash") != expected_chapter_hash:
            problems.append(f"{spec.section_id}: chapter content hash mismatch")
        if (
            chapter.get("status") != "ai_generated_judgment_unreviewed"
            or chapter.get("review_status") != "pending_human_review"
        ):
            problems.append(f"{spec.section_id}: review status is unsafe")
        prior_context.append(
            {
                "section_id": chapter.get("section_id"),
                "blocks": [
                    {
                        "kind": block.get("kind"),
                        "text": block.get("text"),
                        "evidence_ids": block.get("evidence_ids"),
                    }
                    for block in chapter.get("blocks") or []
                ],
            }
        )

    accepted = [
        item
        for item in dossier.get("provider_receipts") or []
        if item.get("accepted")
    ]
    accepted_by_id = {
        item.get("request_id"): item for item in accepted if item.get("request_id")
    }
    final_ids = [item.get("model_request_id") for item in chapters]
    if (
        len(accepted) != 8
        or len(accepted_by_id) != 8
        or set(final_ids) != set(accepted_by_id)
    ):
        problems.append("final chapters are not bound to exactly eight accepted calls")
    for request_id in final_ids:
        semantic = (accepted_by_id.get(request_id) or {}).get("semantic_audit")
        if (
            not isinstance(semantic, dict)
            or semantic.get("verdict") != "pass"
            or semantic.get("problems")
        ):
            problems.append(f"{request_id}: semantic audit did not pass")
        else:
            chapter = next(
                item for item in chapters if item.get("model_request_id") == request_id
            )
            if semantic.get("audited_chapter_hash") != chapter.get("content_hash"):
                problems.append(f"{request_id}: semantic audit is not bound to final chapter bytes")
    production = dossier.get("production_record") or {}
    if (
        production.get("accepted_model_calls") != 8
        or production.get("accepted_semantic_audits") != 8
    ):
        problems.append("production record accepted-call counts are wrong")

    sections = dossier.get("section_contract", {}).get("sections") or []
    statuses = {
        item.get("section_id"): (
            item.get("status"),
            item.get("status_reason"),
        )
        for item in sections
    }
    for section_id in expected_ids:
        if statuses.get(section_id) != ("partial", "pending_judgment_review"):
            problems.append(f"{section_id}: expected pending-review PARTIAL")
    if statuses.get("production_record") != ("full", None):
        problems.append("production_record is not FULL")
    degradation = dossier.get("degradation") or {}
    if degradation.get("tier") != "B":
        problems.append("unreviewed dossier did not remain Tier B")
    if sorted(degradation.get("blocked_fields") or []) != [
        "action",
        "position_range",
        "target_price",
    ]:
        problems.append("Tier-B blocked fields changed")
    if dossier.get("decision", {}).get("action") != "no_action":
        problems.append("decision policy did not remain no_action")

    if queue.get("schema_version") != REVIEW_QUEUE_SCHEMA_VERSION:
        problems.append("review queue schema mismatch")
    expected_queue_hash = canonical_hash(
        {key: value for key, value in queue.items() if key != "receipt_hash"}
    )
    if queue.get("receipt_hash") != expected_queue_hash:
        problems.append("review queue hash mismatch")
    if len(queue.get("items") or []) != 8:
        problems.append("review queue does not contain all eight model chapters")
    for item in queue.get("items") or []:
        if (
            not item.get("full_text")
            or not item.get("citations")
            or item.get("review_status") != "pending_human_review"
        ):
            problems.append(
                f"review queue item {item.get('section_id')} is incomplete"
            )

    for source in dossier.get("source_manifest") or []:
        parsed = urlparse(str(source.get("source_url") or ""))
        if (
            parsed.scheme != "https"
            or parsed.hostname not in OFFICIAL_HOSTS
            or not source.get("raw_hash")
            or not source.get("pages_used")
        ):
            problems.append(
                f"source manifest entry {source.get('document_id')} is invalid"
            )

    metrics = dossier.get("metrics") or {}
    observed_generated = sum(
        int(item.get("character_count") or 0) for item in chapters
    )
    if metrics.get("generated_research_text_characters") != observed_generated:
        problems.append("generated research text metric is wrong")
    result = {
        "ticker": ticker,
        "passed": not problems,
        "problems": problems,
        "warnings": warnings,
        "receipt_hash": dossier.get("receipt_hash"),
        "run_id": production.get("run_id"),
        "north_star": {
            "structure_signature": north_star.structure_signature,
            "body_characters": north_star.body_characters,
            "source_rows": north_star.source_rows,
            "fact_ids": north_star.fact_ids,
        },
        "metrics": metrics,
        "section_statuses": statuses,
        "tier": degradation.get("tier"),
        "blocked_fields": degradation.get("blocked_fields"),
        "accepted_model_request_ids": final_ids,
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("ticker")
    parser.add_argument(
        "--directory",
        type=Path,
        default=ROOT / "artifacts" / "round7-dossiers",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = verify(args.ticker.upper(), args.directory)
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
