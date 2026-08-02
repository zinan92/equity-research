#!/usr/bin/env python3
"""Generate one Round 7 dossier with one whole-chapter model request at a time."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product"))

from data_core.round7_chapter_generator import (  # noqa: E402
    GENERATOR_VERSION,
    PROMPT_VERSION,
    SEMANTIC_AUDITOR_VERSION,
    VALIDATOR_VERSION,
    build_chapter_request,
    build_review_queue,
    compile_dossier,
    generate_chapter,
    render_html,
    render_markdown,
    validate_chapter,
)
from data_core.round7_evidence import (  # noqa: E402
    build_evidence_registry,
    canonical_hash,
    load_source_receipts,
    select_section_evidence,
)
from data_core.round7_profiles import load_profile, section_rule  # noqa: E402
from deepseek_writer import DEFAULT_KEY_FILE  # noqa: E402
from report_contract import RESEARCH_SECTION_SPECS_V3  # noqa: E402


ISSUERS = {
    "300750.SZ": {
        "ticker": "300750.SZ",
        "name": "宁德时代新能源科技股份有限公司",
        "short_name": "宁德时代",
    },
    "600519.SH": {
        "ticker": "600519.SH",
        "name": "贵州茅台酒股份有限公司",
        "short_name": "贵州茅台",
    },
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix="." + path.name + ".",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _load_checkpoint(
    path: Path,
    *,
    ticker: str,
    profile_hash: str | None,
    known_at: str,
) -> dict:
    if not path.exists():
        return {
            "ticker": ticker,
            "profile_hash": profile_hash,
            "known_at": known_at,
            "chapters": {},
            "provider_receipts": [],
        }
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        quarantine = path.with_suffix(path.suffix + ".corrupt")
        os.replace(path, quarantine)
        raise RuntimeError(f"unreadable checkpoint quarantined at {quarantine}") from exc
    if value.get("ticker") != ticker:
        raise ValueError("checkpoint ticker mismatch")
    if value.get("profile_hash") != profile_hash or value.get("known_at") != known_at:
        raise ValueError("checkpoint profile or as-of mismatch")
    return value


def _parse_as_of(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("--as-of must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError("--as-of must include a timezone")
    return parsed.astimezone(timezone.utc)


def _validate_cutoff(
    *,
    narratives: dict,
    financials: dict,
    as_of: str,
) -> None:
    cutoff = _parse_as_of(as_of)
    dates: list[datetime] = []
    generated_at = narratives.get("generated_at")
    if generated_at:
        dates.append(_parse_as_of(str(generated_at)))
    for report in narratives.get("reports", []):
        published_at = report.get("published_at")
        if published_at:
            dates.append(_parse_as_of(str(published_at)))
    for raw in financials.get("page_facts", []):
        published_at = raw.get("published_at")
        if published_at:
            dates.append(_parse_as_of(str(published_at)))
    if dates and cutoff < max(dates):
        raise ValueError("--as-of precedes an official source known_at")


def _prior_context(chapters: list[dict]) -> list[dict]:
    # Prior chapters are context, not a second evidence dump.  Keep the
    # synthesis prompt deterministic and bounded so the conclusion cannot cite
    # every financial row at once.
    context: list[dict] = []
    for chapter in chapters:
        blocks = []
        for block in chapter["blocks"]:
            if block["kind"] == "label":
                continue
            blocks.append(
                {
                    "kind": block["kind"],
                    "text": str(block["text"])[:360],
                    "evidence_ids": list(block["evidence_ids"][:2]),
                }
            )
            if len(blocks) >= 2:
                break
        context.append({"section_id": chapter["section_id"], "blocks": blocks})
    return context


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("ticker")
    parser.add_argument("--issuer-profile", type=Path)
    parser.add_argument("--narrative", type=Path)
    parser.add_argument("--financial", type=Path)
    parser.add_argument("--as-of")
    parser.add_argument("--key-file", type=Path, default=DEFAULT_KEY_FILE)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "artifacts" / "round7-dossiers",
    )
    parser.add_argument(
        "--runtime-dir",
        type=Path,
        default=ROOT / "product" / "runtime" / "round7-dossiers",
    )
    args = parser.parse_args()
    ticker = args.ticker.upper()
    profile = None
    if args.issuer_profile is not None:
        profile = load_profile(args.issuer_profile, ticker=ticker)
        issuer = dict(profile["issuer"])
        narrative_path = args.narrative or (
            ROOT / "docs" / "evidence" / "v4-n2" / f"{ticker}-official-narrative-evidence.json"
        )
        financial_path = args.financial or (
            ROOT / "docs" / "evidence" / "v4-n2" / f"{ticker}-financial-page-evidence.json"
        )
        if not args.as_of:
            raise ValueError("--as-of is required for a profiled issuer run")
        known_at = str(args.as_of)
    else:
        if ticker not in ISSUERS:
            raise ValueError("unknown ticker requires --issuer-profile")
        issuer = ISSUERS[ticker]
        narrative_path = args.narrative or (
            ROOT / "artifacts" / "evidence" / f"{ticker}-official-narrative-evidence.json"
        )
        financial_path = args.financial or (
            ROOT / "artifacts" / "evidence" / f"{ticker}-financial-page-evidence.json"
        )
        known_at = str(args.as_of or "2026-07-31T00:00:00Z")
    narratives, financials = load_source_receipts(
        narrative_path=narrative_path,
        financial_path=financial_path,
        ticker=ticker,
    )
    _validate_cutoff(narratives=narratives, financials=financials, as_of=known_at)
    if profile:
        expected = profile.get("source_receipts") or {}
        if expected.get("narrative_receipt_hash") != narratives.get("receipt_hash"):
            raise ValueError("issuer profile narrative receipt binding mismatch")
        if expected.get("financial_receipt_hash") != financials.get("receipt_hash"):
            raise ValueError("issuer profile financial receipt binding mismatch")
        sequence_hash = (financials.get("source") or {}).get("receipt_hash")
        if expected.get("financial_sequence_receipt_hash") != sequence_hash:
            raise ValueError("issuer profile financial sequence binding mismatch")
    registry = build_evidence_registry(narratives, financials)
    evidence_by_section: dict[str, list[dict]] = {}
    for spec in RESEARCH_SECTION_SPECS_V3[:-1]:
        evidence_by_section[spec.section_id] = select_section_evidence(
            registry,
            section_id=spec.section_id,
            profile=profile,
        )
    source_receipts = {
        "official_narrative_receipt_id": narratives["receipt_id"],
        "official_narrative_receipt_hash": narratives["receipt_hash"],
        "official_narrative_file_sha256": _sha(narrative_path),
        "financial_page_evidence_receipt_hash": financials["receipt_hash"],
        "financial_page_evidence_file_sha256": _sha(financial_path),
        "as_of": known_at,
        "issuer_profile_hash": (profile or {}).get("profile_hash"),
        "issuer_profile_path": str(args.issuer_profile) if args.issuer_profile else None,
    }

    args.runtime_dir.mkdir(parents=True, exist_ok=True)
    lock_path = args.runtime_dir / f"{ticker}.lock"
    lock = lock_path.open("a+", encoding="utf-8")
    try:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        lock.close()
        raise RuntimeError(f"another dossier run holds {lock_path}") from exc
    checkpoint_path = args.runtime_dir / f"{ticker}.checkpoint.json"
    checkpoint = _load_checkpoint(
        checkpoint_path,
        ticker=ticker,
        profile_hash=(profile or {}).get("profile_hash"),
        known_at=known_at,
    )
    checkpoint["source_receipts"] = dict(source_receipts)

    chapters: list[dict] = []
    provider_receipts: list[dict] = list(checkpoint.get("provider_receipts") or [])
    for spec in RESEARCH_SECTION_SPECS_V3[:-1]:
        evidence = list(evidence_by_section[spec.section_id])
        # The conclusion is the one deliberate synthesis step: carry bounded
        # blocks from the seven preceding chapters so it can reconcile them.
        # Other chapters remain independent evidence-bound calls.
        prior = (
            _prior_context(chapters)
            if spec.section_id == "research_conclusion_and_open_questions"
            else []
        )
        if prior:
            used = list(
                dict.fromkeys(
                    evidence_id
                    for prior_chapter in prior
                    for block in prior_chapter["blocks"]
                    for evidence_id in block["evidence_ids"]
                )
            )[:12]
            selected = {item["evidence_id"] for item in evidence}
            evidence.extend(
                dict(registry[evidence_id])
                for evidence_id in used
                if evidence_id not in selected
            )
            evidence_by_section[spec.section_id] = evidence
        checkpoint_key = canonical_hash(
            {
                "section_id": spec.section_id,
                "evidence": evidence,
                "prior": prior,
                "generator_version": GENERATOR_VERSION,
                "prompt_version": PROMPT_VERSION,
                "validator_version": VALIDATOR_VERSION,
                "semantic_auditor_version": SEMANTIC_AUDITOR_VERSION,
                "profile_hash": (profile or {}).get("profile_hash"),
                "known_at": known_at,
            }
        )
        saved = checkpoint.get("chapters", {}).get(spec.section_id)
        chapter = None
        if (
            isinstance(saved, dict)
            and saved.get("checkpoint_key") == checkpoint_key
        ):
            candidate = saved.get("chapter")
            # The generator already persisted this candidate only after the
            # full deterministic validator and semantic auditor passed.  Do
            # not re-run model-sensitive validation on resume; the final
            # verifier performs the authoritative replay against the frozen
            # evidence registry.
            expected_saved_hash = canonical_hash(
                {"section_id": candidate.get("section_id"), "rows": candidate.get("rows")}
            ) if isinstance(candidate, dict) else None
            if (
                isinstance(candidate, dict)
                and candidate.get("section_id") == spec.section_id
                and candidate.get("content_hash") == expected_saved_hash
            ):
                chapter = candidate
        if chapter is None:
            chapter, new_receipts = generate_chapter(
                spec=spec,
                issuer=issuer,
                evidence=evidence,
                registry=registry,
                key_file=args.key_file,
                prior_chapter_context=prior,
                profile=profile,
            )
            provider_receipts.extend(new_receipts)
            checkpoint.setdefault("chapters", {})[spec.section_id] = {
                "checkpoint_key": checkpoint_key,
                "chapter": chapter,
            }
            checkpoint["provider_receipts"] = provider_receipts
            _write(
                checkpoint_path,
                json.dumps(checkpoint, ensure_ascii=False, indent=2) + "\n",
            )
            print(
                f"{spec.section_id}: accepted after {len(new_receipts)} whole-chapter call(s), "
                f"{chapter['character_count']} chars"
            )
        else:
            print(
                f"{spec.section_id}: resumed accepted chapter, "
                f"{chapter['character_count']} chars"
            )
        chapter.setdefault(
            "length_status",
            (
                "within_target"
                if tuple(
                    section_rule(
                        profile,
                        spec.section_id,
                        {"target_characters": spec.target_characters},
                    ).get("target_characters")
                    or spec.target_characters
                )[0]
                <= chapter["character_count"]
                <= tuple(
                    section_rule(
                        profile,
                        spec.section_id,
                        {"target_characters": spec.target_characters},
                    ).get("target_characters")
                    or spec.target_characters
                )[1]
                else (
                    "below_target_due_to_evidence_and_validation_constraints"
                    if chapter["character_count"]
                    < tuple(
                        section_rule(
                            profile,
                            spec.section_id,
                            {"target_characters": spec.target_characters},
                        ).get("target_characters")
                        or spec.target_characters
                    )[0]
                    else "above_target_due_to_chapter_synthesis"
                )
            ),
        )
        chapters.append(chapter)

    dossier = compile_dossier(
        ticker=ticker,
        issuer=issuer,
        chapters=chapters,
        evidence_by_section=evidence_by_section,
        registry=registry,
        page_facts=financials["page_facts"],
        provider_receipts=provider_receipts,
        source_receipts=source_receipts,
        profile=profile,
        known_at=known_at,
    )
    markdown = render_markdown(dossier)
    dossier["metrics"]["chapter_body_characters"] = len(
        markdown.split("## 1. 一句话定位", 1)[1]
        .split("## 9. 生产记录", 1)[0]
        .strip()
    )
    dossier["metrics"]["full_file_characters"] = len(markdown)
    dossier["content_hash"] = canonical_hash(
        {key: item for key, item in dossier.items() if key != "content_hash"}
    )
    markdown = render_markdown(dossier)
    rendered_html = render_html(
        markdown,
        title=f"{issuer['short_name']} Round 7 公司档案",
    )
    dossier["artifacts"] = {
        "markdown_path": str(args.output_dir / f"{ticker}.md"),
        "markdown_sha256": hashlib.sha256(markdown.encode()).hexdigest(),
        "html_path": str(args.output_dir / f"{ticker}.html"),
        "html_sha256": hashlib.sha256(rendered_html.encode()).hexdigest(),
    }
    dossier["receipt_hash"] = canonical_hash(dossier)
    review_queue = build_review_queue(dossier)
    _write(args.output_dir / f"{ticker}.md", markdown)
    _write(args.output_dir / f"{ticker}.html", rendered_html)
    _write(
        args.output_dir / f"{ticker}.receipt.json",
        json.dumps(dossier, ensure_ascii=False, indent=2) + "\n",
    )
    _write(
        args.output_dir / f"{ticker}.review-queue.json",
        json.dumps(review_queue, ensure_ascii=False, indent=2) + "\n",
    )
    checkpoint_path.unlink(missing_ok=True)
    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    lock.close()
    print(json.dumps(dossier["metrics"], ensure_ascii=False))
    print(
        json.dumps(
            {
                "tier": dossier["degradation"]["tier"],
                "reasons": dossier["degradation"]["reasons"],
                "blocked_fields": dossier["degradation"]["blocked_fields"],
                "section_statuses": dossier["degradation"]["section_statuses"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
