"""Fail-closed quality gate for canonical Round 7 publication artifacts.

This gate is deliberately separate from the C1/Tier/B6 safety machinery.  It
answers a narrower question: is this exact nine-chapter artifact safe to put
in the reader/public index?  Official issuer prose remains official evidence,
but strategic and marketing claims are classified as issuer self-report and
cannot satisfy the independent-analysis gate by themselves.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

from data_core.round7_evidence import (
    OFFICIAL_HOSTS,
    NARRATIVE_CLASSIFICATION_VERSION,
    classify_narrative_provenance,
)
from data_core.round7_north_star import (
    ROUND7_REQUIRED_HEADINGS,
    ROUND7_READER_UNITS,
    ROUND7_STRUCTURE_SIGNATURE,
    structure_signature,
    verify_round7_document,
)
from v4_dossier_contract import validate_v4_dossier


QUALITY_GATE_SCHEMA_VERSION = "round7-quality-gate-v1"
QUALITY_GATE_VERSION = "round7-publication-quality-v1"
REPO_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_SOURCE_DIR = Path(__file__).resolve().parents[1] / "artifacts" / "round7-dossiers"
RESEARCH_CHAPTER_UNITS = ROUND7_READER_UNITS[:-1]
ANALYTICAL_SECTIONS = RESEARCH_CHAPTER_UNITS
_SELF_REPORT_LABELS = ("公司自述", "年报自述", "发行人自述", "公司披露的战略")
_OBJECTIVE_PATH_MARKERS = (
    "风险管理", "风险披露", "信用风险", "流动性风险", "市场风险",
    "公司治理", "董事", "监事", "高级管理人员",
)
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def portable_path(path: Path) -> str:
    """Use repo-relative paths in committed receipts while resolving internally."""
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(path)


def _canonical_json_hash(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _is_official(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme == "https" and parsed.hostname in OFFICIAL_HOSTS


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _declared_path_matches(declared: Any, actual: Path, *, dossier_root: Path) -> bool:
    value = str(declared or "")
    if not value:
        return False
    candidates = []
    declared_path = Path(value)
    if declared_path.is_absolute():
        candidates.append(declared_path)
    else:
        candidates.extend((dossier_root / declared_path, CANONICAL_SOURCE_DIR.parent.parent / declared_path))
    return any(candidate.resolve() == actual.resolve() for candidate in candidates)


def _source_map(source_manifest: Any) -> dict[str, list[Mapping[str, Any]]]:
    result: dict[str, list[Mapping[str, Any]]] = {}
    if not isinstance(source_manifest, list):
        return result
    for row in source_manifest:
        if isinstance(row, Mapping):
            result.setdefault(str(row.get("document_id") or ""), []).append(row)
    return result


def _citation_errors(
    evidence_id: str,
    row: Mapping[str, Any],
    source_rows: Mapping[str, list[Mapping[str, Any]]],
) -> list[str]:
    errors: list[str] = []
    citation = row.get("citation")
    if not isinstance(citation, Mapping):
        return [f"{evidence_id}: citation missing"]
    document_id = str(citation.get("document_id") or "")
    raw_hash = str(citation.get("raw_hash") or "")
    page = citation.get("page_number")
    url = str(citation.get("source_url") or "")
    if not document_id or type(page) is not int or page < 1:
        errors.append(f"{evidence_id}: document/page locator invalid")
    if not _HEX64.fullmatch(raw_hash):
        errors.append(f"{evidence_id}: raw_hash invalid")
    if not str(citation.get("quoted_anchor") or "").strip():
        errors.append(f"{evidence_id}: quoted_anchor missing")
    if not _is_official(url):
        errors.append(f"{evidence_id}: source URL is not an approved official host")
    matches = [
        item
        for item in source_rows.get(document_id, [])
        if str(item.get("raw_hash") or "") == raw_hash
        and str(item.get("source_url") or "") == url
        and isinstance(item.get("pages_used"), list)
        and page in item.get("pages_used", [])
    ]
    if not matches:
        errors.append(f"{evidence_id}: citation is not bound to source_manifest")
    return errors


def _evidence_class(row: Mapping[str, Any], *, recomputed_self_report: bool) -> str:
    if str(row.get("kind") or "") == "financial":
        return "financial_page_fact"
    if recomputed_self_report or bool(row.get("self_report")):
        return "issuer_self_report"
    path = str(row.get("section_path") or "")
    if any(marker in path for marker in _OBJECTIVE_PATH_MARKERS):
        return "objective_official_fact"
    return "issuer_disclosed_narrative"


def _iter_cells(chapter: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    cells: list[Mapping[str, Any]] = []
    for row in chapter.get("rows") or []:
        if isinstance(row, Mapping):
            for cell in row.get("cells") or []:
                if isinstance(cell, Mapping):
                    cells.append(cell)
    return cells


def _typed_gap_applies(
    section_typed_gaps: list[Mapping[str, Any]],
    cell: Mapping[str, Any],
    *,
    section_id: str,
) -> bool:
    """Only a cell-scoped structured gap can explain missing independent evidence.

    A section-wide marker would let one weak cell excuse every other cell in
    the chapter. Producers must bind the gap to the exact ``section_id`` and
    ``evidence_ids`` that were attempted; free-form prose never satisfies this
    function.
    """
    cell_evidence_ids = {str(item) for item in cell.get("evidence_ids") or ()}
    for item in section_typed_gaps:
        if str(item.get("gap_code") or "") != "insufficient_independent_evidence":
            continue
        if str(item.get("section_id") or "") != section_id:
            continue
        gap_evidence_ids = {str(value) for value in item.get("evidence_ids") or ()}
        if gap_evidence_ids and gap_evidence_ids == cell_evidence_ids:
            return True
    return False


def evaluate_round7_quality(
    *,
    dossier_path: Path,
    markdown_path: Path | None = None,
    html_path: Path | None = None,
    require_canonical_root: bool = False,
    expected_ticker: str | None = None,
) -> dict[str, Any]:
    """Evaluate one canonical dossier without changing its content.

    The return value is always serializable and records blockers instead of
    raising for quality failures.  Missing/broken input identity is a blocker,
    not an excuse to manufacture a replacement artifact.
    """
    blockers: list[dict[str, Any]] = []
    dossier_path = Path(dossier_path)
    try:
        dossier = _load(dossier_path)
    except Exception as exc:  # malformed input is a publication blocker
        result = {
            "schema_version": QUALITY_GATE_SCHEMA_VERSION,
            "quality_gate_version": QUALITY_GATE_VERSION,
            "status": "blocked",
            "publication_eligible": False,
            "blockers": [{"code": "dossier_receipt_invalid", "detail": str(exc)}],
            "self_report_leak_count": 0,
            "independent_evidence_by_section": {},
        }
        result["receipt_hash"] = _canonical_json_hash(result)
        return result
    ticker = str(dossier.get("ticker") or "").upper()
    if expected_ticker and ticker != str(expected_ticker).upper():
        blockers.append({
            "code": "publication_ticker_mismatch",
            "expected": str(expected_ticker).upper(),
            "actual": ticker,
        })
    if not ticker:
        blockers.append({"code": "ticker_missing"})
    issuer = dossier.get("issuer")
    if isinstance(issuer, Mapping) and str(issuer.get("ticker") or "").upper() not in {"", ticker}:
        blockers.append({
            "code": "issuer_ticker_mismatch",
            "expected": ticker,
            "actual": issuer.get("ticker"),
        })
    expected_markdown = dossier_path.with_name(f"{ticker}.md") if ticker else dossier_path.with_suffix(".md")
    expected_html = dossier_path.with_name(f"{ticker}.html") if ticker else dossier_path.with_suffix(".html")
    markdown_path = Path(markdown_path or expected_markdown)
    html_path = Path(html_path or expected_html)
    if dossier_path.name != f"{ticker}.receipt.json":
        blockers.append({"code": "receipt_filename_mismatch", "detail": dossier_path.name})
    if require_canonical_root and dossier_path.parent.resolve() != CANONICAL_SOURCE_DIR.resolve():
        blockers.append({"code": "non_canonical_source_root", "detail": str(dossier_path.parent)})
    if dossier.get("data_kind") != "real":
        blockers.append({"code": "data_kind_not_real"})
    if dossier.get("schema_version") != "round7-generated-dossier-v8":
        blockers.append({"code": "canonical_receipt_schema_invalid", "actual": dossier.get("schema_version")})
    production_record = dossier.get("production_record")
    if not isinstance(production_record, Mapping):
        production_record = {}
        blockers.append({"code": "production_record_invalid"})
    if not str(production_record.get("run_id") or ""):
        blockers.append({"code": "production_run_id_missing"})
    if str(dossier.get("review_status") or "") not in {"pending_human_review", "human_reviewed"}:
        blockers.append({"code": "review_status_invalid", "detail": dossier.get("review_status")})

    for path, code in ((markdown_path, "markdown_missing"), (html_path, "html_missing")):
        if not path.is_file():
            blockers.append({"code": code, "detail": str(path)})
    markdown = markdown_path.read_text(encoding="utf-8") if markdown_path.is_file() else ""
    if markdown:
        frontmatter_match = re.match(r"\A---\n(?P<body>.*?)\n---(?:\n|\Z)", markdown, re.DOTALL)
        frontmatter_values: dict[str, str] = {}
        if frontmatter_match:
            for line in frontmatter_match.group("body").splitlines():
                if ":" in line:
                    key, value = line.split(":", 1)
                    frontmatter_values[key.strip()] = value.strip().strip('"\'')
        frontmatter_ticker = frontmatter_values.get("ticker", "")
        if not frontmatter_ticker:
            blockers.append({"code": "markdown_ticker_missing"})
        elif frontmatter_ticker.upper() != ticker:
            blockers.append({"code": "markdown_ticker_mismatch", "expected": ticker, "actual": frontmatter_ticker})
        if frontmatter_values.get("data_kind") != "real":
            blockers.append({"code": "markdown_data_kind_mismatch", "actual": frontmatter_values.get("data_kind")})
        if frontmatter_values.get("review_status") != str(dossier.get("review_status") or ""):
            blockers.append({"code": "markdown_review_status_mismatch"})
        if frontmatter_values.get("run_id") != str(production_record.get("run_id") or ""):
            blockers.append({"code": "markdown_run_id_mismatch"})
        expected_tier = (dossier.get("degradation") if isinstance(dossier.get("degradation"), Mapping) else {}).get("tier")
        if frontmatter_values.get("tier") != str(expected_tier or ""):
            blockers.append({"code": "markdown_tier_mismatch"})
        structural = verify_round7_document(markdown_path)
        for problem in structural.problems:
            blockers.append({"code": "canonical_structure_invalid", "detail": problem})
        for problem in validate_v4_dossier(markdown):
            blockers.append({"code": "v4_contract_invalid", "detail": problem})
        if structure_signature(markdown) != ROUND7_STRUCTURE_SIGNATURE:
            blockers.append({"code": "round7_structure_signature_mismatch"})

    raw_artifacts = dossier.get("artifacts")
    if not isinstance(raw_artifacts, Mapping):
        artifacts: Mapping[str, Any] = {}
        blockers.append({"code": "artifacts_invalid"})
    else:
        artifacts = raw_artifacts
    if not _declared_path_matches(artifacts.get("markdown_path"), markdown_path, dossier_root=dossier_path.parent):
        blockers.append({"code": "declared_markdown_path_mismatch", "declared": artifacts.get("markdown_path"), "actual": str(markdown_path)})
    if not _declared_path_matches(artifacts.get("html_path"), html_path, dossier_root=dossier_path.parent):
        blockers.append({"code": "declared_html_path_mismatch", "declared": artifacts.get("html_path"), "actual": str(html_path)})
    if require_canonical_root:
        for path, code in ((markdown_path, "markdown_outside_canonical_root"), (html_path, "html_outside_canonical_root")):
            if path.resolve().parent != CANONICAL_SOURCE_DIR.resolve():
                blockers.append({"code": code, "detail": str(path)})
    if markdown_path.is_file():
        actual = _sha(markdown_path)
        declared = str(artifacts.get("markdown_sha256") or "")
        if declared and declared != actual:
            blockers.append({"code": "markdown_hash_mismatch", "expected": declared, "actual": actual})
        elif not declared:
            blockers.append({"code": "markdown_hash_missing"})
    if html_path.is_file():
        actual = _sha(html_path)
        declared = str(artifacts.get("html_sha256") or "")
        if declared and declared != actual:
            blockers.append({"code": "html_hash_mismatch", "expected": declared, "actual": actual})
        elif not declared:
            blockers.append({"code": "html_hash_missing"})
        if markdown and ticker:
            try:
                from data_core.round7_chapter_generator import render_html
                issuer_name = str((dossier.get("issuer") or {}).get("short_name") or ticker)
                expected_html = render_html(markdown, title=f"{issuer_name} Round 7 公司档案")
                if hashlib.sha256(expected_html.encode("utf-8")).hexdigest() != actual:
                    blockers.append({"code": "html_renderer_binding_mismatch"})
            except Exception as exc:
                blockers.append({"code": "html_renderer_validation_error", "detail": str(exc)})

    raw_source_manifest = dossier.get("source_manifest")
    if raw_source_manifest is not None and not isinstance(raw_source_manifest, list):
        blockers.append({"code": "source_manifest_invalid"})
    elif isinstance(raw_source_manifest, list):
        for item in raw_source_manifest:
            if not isinstance(item, Mapping):
                blockers.append({"code": "source_manifest_row_invalid"})
    source_rows = _source_map(raw_source_manifest)
    if not source_rows:
        blockers.append({"code": "source_manifest_missing"})
    else:
        for document_id, rows in source_rows.items():
            identities = {
                (str(row.get("raw_hash") or ""), str(row.get("source_url") or ""), tuple(row.get("pages_used") or ()))
                for row in rows
            }
            if len(identities) > 1:
                blockers.append({"code": "source_manifest_document_id_ambiguous", "document_id": document_id})
            if not document_id:
                blockers.append({"code": "source_manifest_document_id_missing"})
            for row in rows:
                raw_hash = str(row.get("raw_hash") or "")
                url = str(row.get("source_url") or "")
                pages = row.get("pages_used")
                if not _HEX64.fullmatch(raw_hash):
                    blockers.append({"code": "source_manifest_raw_hash_invalid", "document_id": document_id})
                if not _is_official(url):
                    blockers.append({"code": "source_manifest_non_official_url", "document_id": document_id})
                if not isinstance(pages, list) or not pages or any(type(page) is not int or page < 1 for page in pages):
                    blockers.append({"code": "source_manifest_page_binding_invalid", "document_id": document_id})
    if markdown:
        source_urls_in_markdown = set(re.findall(r"https://[^\s|)]+", markdown))
        manifest_urls = {
            str(item.get("source_url") or "")
            for rows in source_rows.values()
            for item in rows
        }
        for url in source_urls_in_markdown:
            if not _is_official(url):
                blockers.append({"code": "markdown_non_official_source_url", "url": url})
            elif url not in manifest_urls:
                blockers.append({"code": "markdown_source_url_not_in_manifest", "url": url})

    raw_source_receipts = dossier.get("source_receipts")
    if not isinstance(raw_source_receipts, Mapping):
        source_receipts: Mapping[str, Any] = {}
        blockers.append({"code": "source_receipts_invalid"})
    else:
        source_receipts = raw_source_receipts
    bound_receipt_hashes = {
        key: value
        for key, value in source_receipts.items()
        if str(key).endswith("hash") and isinstance(value, str)
    }
    if not bound_receipt_hashes:
        blockers.append({"code": "source_receipt_binding_missing"})
    else:
        for key, value in bound_receipt_hashes.items():
            if not _HEX64.fullmatch(value):
                blockers.append({"code": "source_receipt_hash_invalid", "field": key})
    required_receipt_fields = (
        "official_narrative_receipt_id",
        "official_narrative_receipt_hash",
        "financial_page_evidence_receipt_hash",
    )
    for field in required_receipt_fields:
        if not str(source_receipts.get(field) or ""):
            blockers.append({"code": "source_receipt_field_missing", "field": field})
    narrative_id = str(source_receipts.get("official_narrative_receipt_id") or "")
    narrative_hash = str(source_receipts.get("official_narrative_receipt_hash") or "")
    if narrative_id:
        if not re.fullmatch(r"[^:]+:[0-9a-f]{64}", narrative_id):
            blockers.append({"code": "source_receipt_id_invalid", "field": "official_narrative_receipt_id"})
        elif narrative_id.rsplit(":", 1)[-1] != narrative_hash:
            blockers.append({"code": "source_receipt_id_hash_mismatch", "field": "official_narrative_receipt_id"})
    issuer_profile = dossier.get("issuer_profile")
    profile_hash_value = str(issuer_profile.get("profile_hash") or "") if isinstance(issuer_profile, Mapping) else ""
    profile_receipt_hash = str(source_receipts.get("issuer_profile_hash") or "")
    production_profile_hash = str(production_record.get("issuer_profile_hash") or "")
    if profile_hash_value or profile_receipt_hash or production_profile_hash:
        if not (profile_hash_value and profile_receipt_hash and production_profile_hash):
            blockers.append({"code": "issuer_profile_binding_incomplete"})
        elif any(not _HEX64.fullmatch(value) for value in (profile_hash_value, profile_receipt_hash, production_profile_hash)):
            blockers.append({"code": "issuer_profile_hash_invalid"})
        elif len({profile_hash_value, profile_receipt_hash, production_profile_hash}) != 1:
            blockers.append({"code": "issuer_profile_hash_mismatch"})
        profile_path_value = str(source_receipts.get("issuer_profile_path") or "")
        profile_candidates = []
        if profile_path_value:
            profile_path = Path(profile_path_value)
            profile_candidates = [profile_path] if profile_path.is_absolute() else [REPO_ROOT / profile_path]
        profile_file = next((path for path in profile_candidates if path.is_file()), None)
        if profile_file is None:
            blockers.append({"code": "issuer_profile_file_binding_missing"})
        else:
            try:
                from data_core.round7_profiles import profile_hash
                profile_payload = _load(profile_file)
                if str(profile_payload.get("ticker") or "").upper() not in {"", ticker}:
                    blockers.append({
                        "code": "issuer_profile_ticker_mismatch",
                        "expected": ticker,
                        "actual": profile_payload.get("ticker"),
                    })
                if profile_hash(profile_payload) != profile_hash_value:
                    blockers.append({"code": "issuer_profile_file_hash_mismatch"})
            except Exception as exc:
                blockers.append({"code": "issuer_profile_file_invalid", "detail": str(exc)})
    source_file_bindings = {
        "official_narrative_file_sha256": f"{ticker}-official-narrative-evidence.json",
        "financial_page_evidence_file_sha256": f"{ticker}-financial-page-evidence.json",
    }
    for hash_field, filename in source_file_bindings.items():
        declared_hash = str(source_receipts.get(hash_field) or "")
        if not declared_hash:
            blockers.append({"code": "source_receipt_file_hash_missing", "field": hash_field})
            continue
        candidates = (
            REPO_ROOT / "artifacts" / "evidence" / filename,
            REPO_ROOT / "docs" / "evidence" / "v4-n1-official" / filename,
        )
        source_file = next((path for path in candidates if path.is_file()), None)
        if source_file is None:
            blockers.append({"code": "source_receipt_file_binding_missing", "field": hash_field, "filename": filename})
        elif _sha(source_file) != declared_hash:
            blockers.append({"code": "source_receipt_file_hash_mismatch", "field": hash_field, "path": str(source_file)})
        else:
            try:
                source_payload = _load(source_file)
                receipt_hash_field = "official_narrative_receipt_hash" if hash_field.startswith("official_narrative") else "financial_page_evidence_receipt_hash"
                if str(source_payload.get("ticker") or "").upper() != ticker:
                    blockers.append({"code": "source_receipt_ticker_mismatch", "field": hash_field, "path": str(source_file)})
                expected_schema = "e4-official-narrative-evidence-v1" if hash_field.startswith("official_narrative") else "round7-financial-page-evidence-v1"
                if source_payload.get("schema_version") != expected_schema:
                    blockers.append({"code": "source_receipt_schema_mismatch", "field": hash_field, "path": str(source_file)})
                if str(source_payload.get("receipt_hash") or "") != str(source_receipts.get(receipt_hash_field) or ""):
                    blockers.append({"code": "source_receipt_hash_mismatch", "field": receipt_hash_field, "path": str(source_file)})
            except Exception as exc:
                blockers.append({"code": "source_receipt_file_invalid", "field": hash_field, "detail": str(exc)})

    expected_content = {
        key: value
        for key, value in dossier.items()
        if key not in {"content_hash", "artifacts", "receipt_hash"}
    }
    if dossier.get("content_hash") != _canonical_json_hash(expected_content):
        blockers.append({"code": "dossier_content_hash_mismatch"})
    declared_receipt_hash = str(dossier.get("receipt_hash") or "")
    expected_receipt_hash = _canonical_json_hash({key: value for key, value in dossier.items() if key != "receipt_hash"})
    if not _HEX64.fullmatch(declared_receipt_hash):
        blockers.append({"code": "dossier_receipt_hash_missing_or_invalid"})
    elif declared_receipt_hash != expected_receipt_hash:
        blockers.append({"code": "dossier_receipt_hash_mismatch", "expected": declared_receipt_hash, "actual": expected_receipt_hash})

    registry = dossier.get("evidence_registry") or {}
    if not isinstance(registry, Mapping):
        registry = {}
        blockers.append({"code": "evidence_registry_missing"})
    if not registry:
        blockers.append({"code": "evidence_registry_empty"})
    evidence_classes: dict[str, str] = {}
    self_report_leaks: list[dict[str, Any]] = []
    citation_error_count = 0
    for evidence_id, raw_row in registry.items():
        if not isinstance(raw_row, Mapping):
            blockers.append({"code": "evidence_row_invalid", "evidence_id": evidence_id})
            continue
        row = dict(raw_row)
        if str(row.get("evidence_id") or "") != str(evidence_id):
            blockers.append({
                "code": "evidence_id_field_mismatch",
                "evidence_id": str(evidence_id),
                "row_evidence_id": row.get("evidence_id"),
            })
        if not str(evidence_id).strip():
            blockers.append({"code": "evidence_id_missing"})
        if str(row.get("kind") or "") not in {"narrative", "financial"}:
            blockers.append({"code": "evidence_kind_invalid", "evidence_id": evidence_id, "kind": row.get("kind")})
            continue
        if str(row.get("kind") or "") == "narrative" and row.get("classification_version") != NARRATIVE_CLASSIFICATION_VERSION:
            blockers.append({"code": "narrative_classification_version_mismatch", "evidence_id": evidence_id})
        text = str(row.get("text") or "")
        path = str(row.get("section_path") or "")
        recomputed, reason = classify_narrative_provenance(text, path)
        stored = bool(row.get("self_report"))
        if str(row.get("kind") or "") == "narrative" and stored != recomputed:
            self_report_leaks.append({
                "evidence_id": str(evidence_id),
                "stored_self_report": stored,
                "recomputed_self_report": recomputed,
                "reason": reason,
            })
        evidence_classes[str(evidence_id)] = _evidence_class(row, recomputed_self_report=recomputed)
        for error in _citation_errors(str(evidence_id), row, source_rows):
            citation_error_count += 1
            blockers.append({"code": "citation_binding_invalid", "detail": error})
    for leak in self_report_leaks:
        blockers.append({"code": "issuer_self_report_leak", **leak})

    raw_chapters = dossier.get("chapters")
    if not isinstance(raw_chapters, list):
        blockers.append({"code": "chapters_invalid"})
        raw_chapters = []
    elif len(raw_chapters) != len(RESEARCH_CHAPTER_UNITS):
        blockers.append({"code": "chapter_count_invalid", "expected": len(RESEARCH_CHAPTER_UNITS), "actual": len(raw_chapters)})
    raw_chapter_ids = [str(item.get("section_id") or "") for item in raw_chapters if isinstance(item, Mapping)]
    if len(raw_chapter_ids) != len(set(raw_chapter_ids)):
        blockers.append({"code": "chapter_ids_duplicate"})
    chapters = {
        str(item.get("section_id")): item
        for item in raw_chapters
        if isinstance(item, Mapping) and item.get("section_id")
    }
    if len(chapters) != len(RESEARCH_CHAPTER_UNITS) or set(chapters) != set(RESEARCH_CHAPTER_UNITS):
        blockers.append({"code": "chapter_set_invalid", "expected": list(RESEARCH_CHAPTER_UNITS), "actual": sorted(chapters)})
    for section_id in RESEARCH_CHAPTER_UNITS:
        chapter = chapters.get(section_id)
        if not isinstance(chapter, Mapping):
            continue
        if not isinstance(chapter.get("rows"), list) or not chapter.get("rows"):
            blockers.append({"code": "chapter_rows_missing", "section_id": section_id})
        chapter_status = str(chapter.get("status") or "")
        chapter_review_status = str(chapter.get("review_status") or "")
        if chapter_status not in {"ai_generated_judgment_unreviewed", "pending_human_review", "partial", "full", "human_reviewed"}:
            blockers.append({"code": "chapter_status_invalid", "section_id": section_id, "status": chapter_status})
        if chapter_review_status not in {"pending_human_review", "human_reviewed"}:
            blockers.append({"code": "chapter_review_status_invalid", "section_id": section_id, "status": chapter_review_status})
    section_contract = dossier.get("section_contract")
    if not isinstance(section_contract, Mapping):
        section_contract = {}
        blockers.append({"code": "section_contract_invalid"})
    section_contract_rows = section_contract.get("sections") or []
    if not isinstance(section_contract_rows, list):
        blockers.append({"code": "section_contract_sections_invalid"})
        section_contract_rows = []
    contract_rows_by_id = {
        str(item.get("section_id")): item
        for item in section_contract_rows
        if isinstance(item, Mapping) and item.get("section_id")
    }
    raw_contract_ids = [
        str(item.get("section_id") or "")
        for item in section_contract_rows
        if isinstance(item, Mapping)
    ]
    if len(raw_contract_ids) != len(set(raw_contract_ids)):
        blockers.append({"code": "section_contract_ids_duplicate"})
    for section_id in RESEARCH_CHAPTER_UNITS:
        contract_row = contract_rows_by_id.get(section_id)
        if contract_row is None:
            blockers.append({"code": "section_contract_row_missing", "section_id": section_id})
        elif str(contract_row.get("status") or "") not in {"partial", "full", "missing"}:
            blockers.append({"code": "section_contract_status_invalid", "section_id": section_id, "status": contract_row.get("status")})
        elif str(contract_row.get("status") or "") == "missing":
            blockers.append({"code": "section_contract_missing", "section_id": section_id})
    raw_typed_gaps = production_record.get("typed_gaps")
    if raw_typed_gaps is None:
        raw_typed_gaps = []
    elif not isinstance(raw_typed_gaps, list):
        raw_typed_gaps = []
        blockers.append({"code": "production_typed_gaps_invalid"})
    raw_quality_gaps = dossier.get("quality_gaps")
    if not isinstance(raw_quality_gaps, list):
        raw_quality_gaps = []
        if dossier.get("quality_gaps") is not None:
            blockers.append({"code": "quality_gaps_invalid"})
    quality_gap_rows = [
        item for item in raw_typed_gaps + raw_quality_gaps
        if isinstance(item, Mapping) and str(item.get("gap_code") or "") == "insufficient_independent_evidence"
    ]
    independent_by_section: dict[str, int] = {}
    self_by_section: dict[str, int] = {}
    for section_id in ANALYTICAL_SECTIONS:
        chapter = chapters.get(section_id, {})
        contract_row = contract_rows_by_id.get(section_id) or {}
        section_typed_gaps = [
            item for item in contract_row.get("typed_gaps", [])
            if isinstance(item, Mapping)
        ]
        section_typed_gaps.extend(
            item for item in quality_gap_rows
            if not item.get("section_id") or str(item.get("section_id")) == section_id
        )
        for gap in section_typed_gaps:
            if (
                str(gap.get("gap_code") or "") == "insufficient_independent_evidence"
                and (
                    not str(gap.get("section_id") or "")
                    or not gap.get("evidence_ids")
                )
            ):
                blockers.append({
                    "code": "typed_gap_scope_invalid",
                    "section_id": section_id,
                    "detail": "independent-evidence gaps must bind exact section_id and evidence_ids",
                })
        independent_count = 0
        self_count = 0
        for cell in _iter_cells(chapter):
            kind = str(cell.get("kind") or "")
            if kind not in {"fact", "judgment"}:
                continue
            text = str(cell.get("text") or "")
            ids = [str(item) for item in cell.get("evidence_ids") or ()]
            classes = [evidence_classes.get(item, "unknown") for item in ids]
            unknown_ids = [item for item, cls in zip(ids, classes) if cls == "unknown"]
            if unknown_ids:
                blockers.append({"code": "unknown_evidence_id", "section_id": section_id, "column_id": cell.get("column_id"), "evidence_ids": unknown_ids})
            independent = [item for item in classes if item in {"financial_page_fact", "objective_official_fact"}]
            self_ids = [item for item, cls in zip(ids, classes) if cls == "issuer_self_report"]
            independent_count += len(set(independent))
            self_count += len(set(self_ids))
            if self_ids and not any(label in text for label in _SELF_REPORT_LABELS):
                blockers.append({
                    "code": "issuer_self_report_unmarked",
                    "section_id": section_id,
                    "column_id": cell.get("column_id"),
                    "evidence_ids": self_ids,
                })
            if not independent and not _typed_gap_applies(section_typed_gaps, cell, section_id=section_id):
                blockers.append({
                    "code": "insufficient_independent_evidence",
                    "section_id": section_id,
                    "column_id": cell.get("column_id"),
                    "evidence_ids": ids,
                    "detail": "critical fact/judgment cell has no financial/objective page evidence or typed gap",
                })
        independent_by_section[section_id] = independent_count
        self_by_section[section_id] = self_count

    production_review_status = str(production_record.get("human_review_status") or "")
    if production_review_status not in {"pending_human_review", "human_reviewed"}:
        blockers.append({"code": "production_review_status_invalid", "status": production_review_status})
    if not str(production_record.get("run_id") or ""):
        blockers.append({"code": "production_record_invalid"})
    section_contract_pending = any(
        isinstance(item, Mapping) and (
            str(item.get("status_reason") or "") == "pending_judgment_review"
            or str(item.get("status") or "") in {"partial", "missing", "pending_human_review"}
        )
        for item in section_contract_rows
    )
    review_pending = (
        str(dossier.get("review_status") or "") == "pending_human_review"
        or production_review_status != "human_reviewed"
        or section_contract_pending
        or any(str(item.get("status")) in {"ai_generated_judgment_unreviewed", "pending_human_review"} for item in raw_chapters if isinstance(item, Mapping))
    )
    chapter_review_statuses = {
        str(item.get("review_status") or "")
        for item in raw_chapters
        if isinstance(item, Mapping)
    }
    if str(dossier.get("review_status") or "") == "human_reviewed" and chapter_review_statuses != {"human_reviewed"}:
        blockers.append({"code": "chapter_review_status_mismatch"})
    if str(dossier.get("review_status") or "") == "pending_human_review" and "human_reviewed" in chapter_review_statuses:
        blockers.append({"code": "chapter_review_status_mismatch"})
    raw_degradation = dossier.get("degradation")
    if raw_degradation is not None and not isinstance(raw_degradation, Mapping):
        blockers.append({"code": "degradation_invalid"})
    if production_review_status == "human_reviewed":
        human_review = dossier.get("human_review")
        reviewed_artifact_hash = _canonical_json_hash({
            key: value for key, value in dossier.items()
            if key not in {"human_review", "receipt_hash"}
        })
        required_review_fields = ("reviewer_id", "reviewed_at", "decision", "artifact_content_hash")
        if (
            not isinstance(human_review, Mapping)
            or any(not str(human_review.get(field) or "").strip() for field in required_review_fields)
            or str(human_review.get("artifact_content_hash") or "") != reviewed_artifact_hash
        ):
            blockers.append({"code": "human_review_receipt_missing"})
            review_pending = True
    if blockers:
        status = "blocked"
    elif review_pending:
        status = "pending_human_review"
    else:
        status = "passed"
    result: dict[str, Any] = {
        "schema_version": QUALITY_GATE_SCHEMA_VERSION,
        "quality_gate_version": QUALITY_GATE_VERSION,
        "ticker": ticker,
        "status": status,
        "publication_eligible": status == "passed",
        "canonical_source_root": dossier_path.parent.resolve() == CANONICAL_SOURCE_DIR.resolve(),
        "dossier_path": portable_path(dossier_path),
        "markdown_path": portable_path(markdown_path),
        "html_path": portable_path(html_path),
        "dossier_sha256": _sha(dossier_path),
        "markdown_sha256": _sha(markdown_path) if markdown_path.is_file() else None,
        "html_sha256": _sha(html_path) if html_path.is_file() else None,
        "dossier_content_hash": dossier.get("content_hash"),
        "structure_signature": structure_signature(markdown) if markdown else None,
        "required_headings": list(ROUND7_REQUIRED_HEADINGS),
        "source_manifest_hash": _canonical_json_hash({"source_manifest": dossier.get("source_manifest")}),
        "source_receipt_hashes": {
            key: value
            for key, value in source_receipts.items()
            if str(key).endswith("hash") and isinstance(value, str)
        },
        "classification_version": NARRATIVE_CLASSIFICATION_VERSION,
        "self_report_leak_count": len(self_report_leaks),
        "self_report_leaks": self_report_leaks,
        "citation_error_count": citation_error_count,
        "independent_evidence_by_section": independent_by_section,
        "issuer_self_report_by_section": self_by_section,
        "blockers": blockers,
        "review_status": dossier.get("review_status"),
        "run_id": production_record.get("run_id"),
        "tier": (dossier.get("degradation") if isinstance(dossier.get("degradation"), Mapping) else {}).get("tier"),
        "boundary": "Publication quality only; this receipt does not alter C1, B6, Tier, decision policy, or human review state.",
    }
    result["receipt_hash"] = _canonical_json_hash({key: value for key, value in result.items() if key != "receipt_hash"})
    return result


def write_quality_gate_receipt(result: Mapping[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(result), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
