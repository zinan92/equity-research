#!/usr/bin/env python3
"""Generate or publish evidence-frozen cross-company research reports.

Draft generation and publication are intentionally separate. Publication
requires an external approval manifest that binds the exact narrative and
evidence hashes reviewed by an editor.
"""

from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
from html import escape as html_escape
import json
from pathlib import Path
import re
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
PRODUCT = ROOT / "product"
sys.path.insert(0, str(PRODUCT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from company_research import (  # noqa: E402
    COMPANY_ADAPTERS,
    CROSS_COMPANY_PROMPT_VERSION,
    build_cross_company_report,
    default_company_claims,
    freeze_evidence,
    load_verified_evidence_packet,
    render_standalone_html,
)
from data_store import connect, initialize, stock_payload, verify_snapshot_content_attestation  # noqa: E402
from deepseek_writer import (  # noqa: E402
    _cross_company_artifact_provenance_hash,
    apply_cross_company_narrative,
    approve_cross_company_narrative,
    build_cross_company_frozen_request,
    generate_cross_company_narrative,
    revise_cross_company_narrative,
    validate_cross_company_narrative,
)
from report_contract import MODULE_SPECS, validate_report_contract  # noqa: E402
from research_evidence import (  # noqa: E402
    _capture_domains,
    _capture_remote,
    _extract_capture_text,
    load_evidence_set,
)
from research_reports import _baseline_report  # noqa: E402
from verify_cross_company_research import (  # noqa: E402
    chrome_path,
    digest,
    pdf_module_order,
    pdf_page_count,
    png_dimensions,
    render,
)


DEFAULT_OUTPUT = ROOT / "evidence" / "m4-cross-company-research" / "live"


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _tickers(values: list[str] | None) -> list[str]:
    resolved = [value.upper() for value in values] if values else list(COMPANY_ADAPTERS)
    unknown = sorted(set(resolved) - set(COMPANY_ADAPTERS))
    if unknown:
        raise RuntimeError(f"unsupported company adapters: {unknown}")
    return resolved


def _inputs(ticker: str, db_path: Path):
    initialize(db_path)
    with closing(connect(db_path)) as connection:
        # One read transaction binds the normalized rows consumed by the report
        # to the attestation checked below. Keep report finalization outside this
        # transaction because approval/artifact helpers initialize their own
        # connections; the report consumes the already-materialized stock dict.
        connection.execute("BEGIN")
        stock = stock_payload(ticker, db_path, connection=connection)
        if not stock:
            raise RuntimeError(f"verified stock snapshot is unavailable: {ticker}")
        snapshot_id = str(stock.get("snapshot_id") or "")
        snapshot = connection.execute(
            "SELECT manifest_hash FROM dataset_snapshots WHERE id=? AND data_mode='REAL' AND quality_status='passed'",
            (snapshot_id,),
        ).fetchone()
        verify_snapshot_content_attestation(connection, snapshot_id)
    if not snapshot or not snapshot["manifest_hash"]:
        raise RuntimeError(f"verified snapshot manifest is unavailable: {ticker}")
    baseline = _baseline_report(stock, db_path)
    if baseline.get("data_mode") != "REAL" or baseline.get("data_status") != "verified":
        raise RuntimeError(f"live publication requires a verified REAL snapshot: {ticker}")
    if baseline.get("generated_from", {}).get("snapshot_id") != snapshot_id:
        raise RuntimeError(f"baseline snapshot no longer matches the attested stock input: {ticker}")
    expected_snapshot_id = f"snap_real_{str(snapshot['manifest_hash'])[:12]}"
    if snapshot_id != expected_snapshot_id:
        raise RuntimeError(f"snapshot id no longer matches its verified manifest: {ticker}")
    evidence_set = load_evidence_set(ticker, snapshot_id, db_path, passed_only=True)
    if not evidence_set:
        raise RuntimeError(f"passed evidence set is unavailable: {ticker}")
    source_ids = [str(item.get("source_key") or "") for item in evidence_set["documents"]]
    claims = default_company_claims(ticker, available_source_ids=source_ids)
    packet = load_verified_evidence_packet(ticker, snapshot_id, claims, db_path)
    return baseline, packet, str(snapshot["manifest_hash"])


def _snapshot_binding(report: dict) -> dict[str, str]:
    generated = report["generated_from"]
    return {
        "snapshot_id": generated["snapshot_id"],
        "snapshot_manifest_hash": generated["snapshot_manifest_hash"],
        "baseline_payload_hash": generated["baseline_payload_hash"],
    }


def _redacted_evidence_receipt(report: dict, frozen_request: dict, transport: dict) -> dict:
    frozen = frozen_request["frozen_evidence"]
    documents = []
    for item in frozen["documents"]:
        documents.append({
            key: item.get(key) for key in (
                "id", "document_id", "title", "kind", "known_at", "url",
                "raw_sha256", "content_hash", "capture_receipt_hash",
                "capture_provenance", "identity_matched_by", "identity_excerpt_hash",
                "identity_extractor_version",
            )
        })
    return {
        "schema_version": "cross-company-redacted-evidence-receipt-v1",
        "status": "passed", "ticker": report["ticker"],
        "snapshot_binding": _snapshot_binding(report),
        "production_input_identity": report["generated_from"]["production_input_identity"],
        "evidence_set_id": frozen["evidence_set_id"],
        "evidence_manifest_hash": frozen["manifest_hash"],
        "evidence_gate_hash": frozen.get("gate_hash"),
        "knowledge_cutoff": frozen["knowledge_cutoff"],
        "document_count": len(documents), "documents": documents,
        "current_transport_verification_hash": digest_text(json.dumps(
            transport, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        )),
        "raw_bytes_committed": False,
    }


def _claim_source_audit_receipt(report: dict, artifact: dict) -> dict:
    rows = []

    def add(path: str, text: object, source_ids: object) -> None:
        if not isinstance(text, str) or not text.strip():
            return
        rows.append({
            "path": path, "text_sha256": digest_text(text),
            "source_ids": list(source_ids) if isinstance(source_ids, list) else [],
        })

    narrative = artifact["narrative"]
    blocks = [("executive_summary", narrative["executive_summary"])]
    blocks.extend((f"sections.{key}", value) for key, value in narrative["sections"].items())
    for path, block in blocks:
        source_ids = block["source_ids"]
        add(f"{path}.title", block.get("title"), source_ids)
        add(f"{path}.conclusion", block.get("conclusion"), source_ids)
        for index, paragraph in enumerate(block.get("paragraphs") or []):
            add(f"{path}.paragraphs[{index}]", paragraph, source_ids)
    committee = narrative["investment_committee"]
    for key in ("bull_case", "base_case", "bear_case"):
        add(f"investment_committee.{key}", committee.get(key), committee.get("source_ids"))
    source_ids = {item["id"] for item in report["sources"]}
    unknown = sorted({source for row in rows for source in row["source_ids"]} - source_ids)
    if unknown or any(not row["source_ids"] for row in rows):
        raise RuntimeError(f"claim/source audit is incomplete: {unknown}")
    return {
        "schema_version": "cross-company-claim-source-audit-v1",
        "status": "passed", "ticker": report["ticker"],
        "narrative_hash": artifact["narrative_hash"],
        "evidence_manifest_hash": artifact["evidence_manifest_hash"],
        "claim_count": len(rows), "claims": rows,
    }


def digest_text(value: str) -> str:
    from hashlib import sha256

    return sha256(value.encode("utf-8")).hexdigest()


def _pdf_text(path: Path) -> str:
    from pypdf import PdfReader

    return "\n".join((page.extract_text() or "") for page in PdfReader(str(path)).pages)


def verify_captures(args: argparse.Namespace) -> None:
    companies = []
    for ticker in _tickers(args.ticker):
        baseline, packet, snapshot_manifest_hash = _inputs(ticker, args.db)
        snapshot_id = baseline["generated_from"]["snapshot_id"]
        evidence_set = load_evidence_set(ticker, snapshot_id, args.db, passed_only=True)
        if not evidence_set:
            raise RuntimeError(f"passed evidence set is unavailable: {ticker}")
        documents = []
        for source in evidence_set["documents"]:
            requested_kind = source["document_kind"]
            url = source["canonical_url"]
            last_error: Exception | None = None
            for attempt in range(3):
                try:
                    raw, mime, status, final_url, redirect_chain = _capture_remote(
                        url, _capture_domains(ticker, requested_kind, url), timeout=90,
                    )
                    break
                except Exception as exc:
                    last_error = exc
                    if attempt < 2:
                        time.sleep(1 + attempt)
            else:
                raise RuntimeError(
                    f"secure recapture failed: {ticker}: {source['source_key']}: {last_error}"
                ) from last_error
            current_hash = sha256(raw).hexdigest()
            frozen_raw = Path(source["raw_path"]).read_bytes()
            exact_match = current_hash == source["raw_sha256"]
            semantic_overlap = 1.0 if exact_match else _semantic_overlap(
                _extract_capture_text(frozen_raw, mime), _extract_capture_text(raw, mime),
            )
            content_matches = exact_match or ("html" in mime and semantic_overlap >= 0.7)
            if status != 200 or not content_matches:
                raise RuntimeError(
                    f"current secure recapture does not match frozen content: {ticker}: "
                    f"{source['source_key']}: overlap={semantic_overlap:.3f}"
                )
            documents.append({
                "source_id": source["source_key"], "document_id": source["id"],
                "frozen_raw_sha256": source["raw_sha256"], "current_raw_sha256": current_hash,
                "hash_matches_frozen": exact_match,
                "semantic_overlap": round(semantic_overlap, 4),
                "content_matches_frozen": content_matches,
                "mime_type": mime, "http_status": status,
                "initial_url": url, "final_url": final_url, "redirect_chain": redirect_chain,
                "verified_at": datetime.now(timezone.utc).isoformat(),
                "capture_policy_version": "validated-redirect-v1",
            })
        companies.append({
            "ticker": ticker, "snapshot_id": snapshot_id,
            "snapshot_manifest_hash": snapshot_manifest_hash,
            "evidence_store_manifest_hash": evidence_set["manifest_hash"],
            "evidence_manifest_hash": freeze_evidence(packet)["manifest_hash"],
            "status": "passed", "documents": documents,
        })
    receipt = {
        "schema_version": "cross-company-transport-verification-v1", "status": "passed",
        "generated_at": datetime.now(timezone.utc).isoformat(), "companies": companies,
    }
    _write_json(args.output, receipt)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


def _semantic_overlap(left: str, right: str) -> float:
    def shingles(value: str) -> set[str]:
        normalized = re.sub(r"\s+", "", value)
        return {normalized[index:index + 20] for index in range(max(0, len(normalized) - 19))}

    first, second = shingles(left), shingles(right)
    if not first or not second:
        return 0.0
    return len(first & second) / min(len(first), len(second))


def generate_drafts(args: argparse.Namespace) -> None:
    if not args.key_file or not args.key_file.is_file():
        raise RuntimeError("draft generation requires a readable --key-file")
    for ticker in _tickers(args.ticker):
        baseline, packet, snapshot_manifest_hash = _inputs(ticker, args.db)
        report = build_cross_company_report(
            baseline, packet, model=args.model, prompt_version=args.prompt_version,
            snapshot_manifest_hash=snapshot_manifest_hash,
        )
        artifact = generate_cross_company_narrative(
            packet, args.key_file, model=args.model, prompt_version=args.prompt_version,
            snapshot_binding=_snapshot_binding(report),
        )
        if artifact["input_identity"] != report["generated_from"]["production_input_identity"]:
            raise RuntimeError(f"draft/report input identity mismatch: {ticker}")
        company_dir = args.output / ticker
        _write_json(company_dir / "deterministic-report.json", report)
        _write_json(company_dir / "base-narrative-draft.json", artifact)
        _write_json(company_dir / "narrative-draft.json", artifact)
        _write_json(company_dir / "draft-receipt.json", {
            "schema_version": "cross-company-draft-company-receipt-v1",
            "ticker": ticker,
            "snapshot_id": report["generated_from"]["snapshot_id"],
            "production_input_identity": artifact["input_identity"],
            "narrative_hash": artifact["narrative_hash"],
            "artifact_provenance_hash": _cross_company_artifact_provenance_hash(artifact),
            "evidence_manifest_hash": artifact["evidence_manifest_hash"],
            "validation_status": artifact["validation"]["status"],
        })
    companies = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(args.output.glob("*/draft-receipt.json"))
    ]
    receipt = {
        "schema_version": "cross-company-draft-receipt-v1",
        "status": "pending_editorial_approval",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "companies": companies,
    }
    _write_json(args.output / "draft-receipt.json", receipt)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


def revise_drafts(args: argparse.Namespace) -> None:
    for ticker in _tickers(args.ticker):
        baseline, packet, snapshot_manifest_hash = _inputs(ticker, args.db)
        report = build_cross_company_report(
            baseline, packet, model=args.model, prompt_version=args.prompt_version,
            snapshot_manifest_hash=snapshot_manifest_hash,
        )
        request = build_cross_company_frozen_request(
            packet, model=args.model, prompt_version=args.prompt_version,
            snapshot_binding=_snapshot_binding(report),
        )
        target = args.draft_dir / ticker / "narrative-draft.json"
        base_target = args.draft_dir / ticker / "base-narrative-draft.json"
        source = args.narrative_source_dir / ticker / "narrative-draft.json"
        artifact = json.loads(target.read_text(encoding="utf-8"))
        if artifact.get("editorial_revision"):
            raise RuntimeError(f"draft is already revised; start from the preserved base artifact: {ticker}")
        if base_target.exists():
            preserved = json.loads(base_target.read_text(encoding="utf-8"))
            if _cross_company_artifact_provenance_hash(
                preserved,
            ) != _cross_company_artifact_provenance_hash(artifact):
                raise RuntimeError(f"preserved base artifact disagrees with the draft being revised: {ticker}")
        else:
            _write_json(base_target, artifact)
        approved_source = json.loads(source.read_text(encoding="utf-8"))
        revised = revise_cross_company_narrative(
            artifact, approved_source["narrative"], request,
            editor=args.editor,
            findings=[
                "Reapplied the previously approved evidence-entailment edits only after "
                "the new frozen request, source IDs and narrative schema were revalidated."
            ],
        )
        _write_json(target, revised)
        _write_json(args.draft_dir / ticker / "revision-receipt.json", {
            "schema_version": "cross-company-revision-company-receipt-v1",
            "ticker": ticker, "input_identity": revised["input_identity"],
            "base_narrative_hash": revised["editorial_revision"]["base_narrative_hash"],
            "base_artifact_provenance_hash": revised["editorial_revision"]["base_artifact_provenance_hash"],
            "revised_narrative_hash": revised["narrative_hash"],
            "evidence_manifest_hash": revised["evidence_manifest_hash"],
            "status": "pending_independent_reapproval",
        })
    companies = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(args.draft_dir.glob("*/revision-receipt.json"))
    ]
    receipt = {
        "schema_version": "cross-company-revision-receipt-v1",
        "status": "pending_independent_reapproval", "companies": companies,
    }
    _write_json(args.draft_dir / "revision-receipt.json", receipt)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


def _approval_map(path: Path) -> dict[str, dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "cross-company-approval-manifest-v1":
        raise RuntimeError("unsupported approval manifest")
    items = payload.get("approvals")
    if not isinstance(items, list):
        raise RuntimeError("approval manifest must contain approvals")
    mapped = {str(item.get("ticker") or "").upper(): item for item in items if isinstance(item, dict)}
    if len(mapped) != len(items):
        raise RuntimeError("approval manifest contains invalid or duplicate tickers")
    return mapped


def publish(args: argparse.Namespace) -> None:
    approvals = _approval_map(args.approval_manifest)
    selected = _tickers(args.ticker)
    if set(selected) - set(approvals):
        raise RuntimeError("approval manifest does not cover every selected ticker")
    expected_modules = [item.id for item in MODULE_SPECS]
    transport_payload = json.loads(args.transport_receipt.read_text(encoding="utf-8"))
    if transport_payload.get("status") != "passed":
        raise RuntimeError("secure transport verification did not pass")
    transport_map = {item["ticker"]: item for item in transport_payload.get("companies") or []}
    editorial_audit = json.loads(args.editorial_audit_receipt.read_text(encoding="utf-8"))
    blocking = editorial_audit.get("blocking_findings") or {}
    if (
        editorial_audit.get("status") != "passed"
        or blocking.get("p0") != 0 or blocking.get("p1") != 0
    ):
        raise RuntimeError("independent editorial audit did not clear all blocking findings")
    editorial_map = {
        str(item.get("ticker") or "").upper(): item
        for item in editorial_audit.get("companies") or [] if isinstance(item, dict)
    }
    chrome = chrome_path()
    companies = []
    for ticker in selected:
        baseline, packet, snapshot_manifest_hash = _inputs(ticker, args.db)
        report = build_cross_company_report(
            baseline, packet, model=args.model, prompt_version=args.prompt_version,
            snapshot_manifest_hash=snapshot_manifest_hash,
        )
        draft_path = args.draft_dir / ticker / "narrative-draft.json"
        artifact = json.loads(draft_path.read_text(encoding="utf-8"))
        request = build_cross_company_frozen_request(
            packet, model=args.model, prompt_version=args.prompt_version,
            snapshot_binding=_snapshot_binding(report),
        )
        transport = transport_map.get(ticker)
        if (
            not transport or transport.get("status") != "passed"
            or transport.get("snapshot_id") != report["generated_from"]["snapshot_id"]
            or transport.get("snapshot_manifest_hash") != report["generated_from"]["snapshot_manifest_hash"]
            or transport.get("evidence_manifest_hash") != report["generated_from"]["evidence_manifest_hash"]
        ):
            raise RuntimeError(f"secure transport verification identity mismatch: {ticker}")
        validation = validate_cross_company_narrative(artifact.get("narrative"), request)
        approval = approvals[ticker]
        editorial = editorial_map.get(ticker)
        if (
            not editorial or editorial.get("result") != "approved"
            or editorial.get("input_identity") != artifact.get("input_identity")
            or editorial.get("narrative_hash") != artifact.get("narrative_hash")
            or editorial.get("evidence_manifest_hash") != artifact.get("evidence_manifest_hash")
        ):
            raise RuntimeError(f"independent editorial audit identity mismatch: {ticker}")
        if artifact.get("input_identity") != request["input_identity"]:
            raise RuntimeError(f"stale narrative input identity: {ticker}")
        if validation.get("status") != "passed":
            raise RuntimeError(f"narrative no longer validates: {ticker}: {validation['errors']}")
        for key in (
            "reviewer", "narrative_hash", "evidence_manifest_hash",
            "artifact_provenance_hash", "input_identity", "provider", "model",
            "prompt_version", "prompt_hash",
        ):
            if not isinstance(approval.get(key), str) or not approval[key].strip():
                raise RuntimeError(f"approval field is missing for {ticker}: {key}")
        if approval["narrative_hash"] != artifact.get("narrative_hash"):
            raise RuntimeError(f"reviewed narrative hash changed: {ticker}")
        if approval["evidence_manifest_hash"] != artifact.get("evidence_manifest_hash"):
            raise RuntimeError(f"reviewed evidence manifest changed: {ticker}")
        expected_approval_provenance = {
            "artifact_provenance_hash": _cross_company_artifact_provenance_hash(artifact),
            "input_identity": artifact.get("input_identity"),
            "provider": artifact.get("provider"), "model": artifact.get("model"),
            "prompt_version": artifact.get("prompt_version"),
            "prompt_hash": artifact.get("prompt_hash"),
        }
        if any(approval.get(key) != value for key, value in expected_approval_provenance.items()):
            raise RuntimeError(f"reviewed artifact provenance changed: {ticker}")
        if any(editorial.get(key) != value for key, value in expected_approval_provenance.items()):
            raise RuntimeError(f"independent editorial audit provenance mismatch: {ticker}")
        approved = approve_cross_company_narrative(
            artifact,
            reviewer=approval["reviewer"],
            expected_narrative_hash=approval["narrative_hash"],
            expected_evidence_manifest_hash=approval["evidence_manifest_hash"],
            expected_artifact_provenance_hash=approval["artifact_provenance_hash"],
        )
        report = apply_cross_company_narrative(report, approved)
        errors = validate_report_contract(report["report_contract"], report)
        if errors:
            raise RuntimeError(f"report contract rejected publication: {ticker}: {errors}")
        company_dir = args.output / ticker
        company_dir.mkdir(parents=True, exist_ok=True)
        json_path = company_dir / "report.json"
        html_path = company_dir / "report.html"
        long_path = company_dir / "report-long.png"
        mobile_path = company_dir / "report-mobile.png"
        pdf_path = company_dir / "report.pdf"
        artifact_path = company_dir / "narrative-artifact.json"
        evidence_receipt_path = company_dir / "evidence-manifest-receipt.json"
        claim_audit_path = company_dir / "claim-source-audit-receipt.json"
        transport_path = company_dir / "transport-verification-receipt.json"
        _write_json(json_path, report)
        _write_json(artifact_path, approved)
        _write_json(evidence_receipt_path, _redacted_evidence_receipt(report, request, transport))
        _write_json(claim_audit_path, _claim_source_audit_receipt(report, approved))
        _write_json(transport_path, transport)
        html = render_standalone_html(report)
        html_path.write_text(html, encoding="utf-8")
        if re.findall(r'data-report-module="([^"]+)"', html) != expected_modules:
            raise RuntimeError(f"rendered module order changed: {ticker}")
        for source in report["sources"]:
            source_id = source["id"]
            if f'id="evidence-{source_id}"' not in html or f'data-evidence-id="{source_id}"' not in html:
                raise RuntimeError(f"rendered evidence trace is incomplete: {ticker}: {source_id}")
            if source.get("url") and html_escape(str(source["url"]), quote=True) not in html:
                raise RuntimeError(f"rendered evidence URL is missing: {ticker}: {source_id}")
        geometry = render(chrome, html_path, long_path, mobile_path, pdf_path)
        dimensions = png_dimensions(long_path)
        mobile_dimensions = png_dimensions(mobile_path)
        pages = pdf_page_count(pdf_path)
        if dimensions != (1440, geometry["desktop_scroll_height"]):
            raise RuntimeError(f"desktop visual proof is incomplete: {ticker}")
        if mobile_dimensions != (390, geometry["mobile_scroll_height"]):
            raise RuntimeError(f"mobile visual proof is incomplete: {ticker}")
        if pdf_module_order(pdf_path) != expected_modules or pages < 2:
            raise RuntimeError(f"PDF proof is incomplete: {ticker}")
        pdf_text = _pdf_text(pdf_path)
        if any(source["id"] not in pdf_text for source in report["sources"]):
            raise RuntimeError(f"PDF evidence trace is incomplete: {ticker}")
        companies.append({
            "ticker": ticker,
            "snapshot_id": report["generated_from"]["snapshot_id"],
            "production_input_identity": report["generated_from"]["production_input_identity"],
            "report_hash": report["report_hash"],
            "narrative_hash": approved["narrative_hash"],
            "evidence_manifest_hash": approved["evidence_manifest_hash"],
            "editorial_approval": approved["editorial_approval"],
            "artifacts": {
                "report_json_sha256": digest(json_path),
                "report_html_sha256": digest(html_path),
                "long_png_sha256": digest(long_path), "long_png_dimensions": list(dimensions),
                "long_png_full_page": dimensions[1] == geometry["desktop_scroll_height"],
                "mobile_png_sha256": digest(mobile_path), "mobile_png_dimensions": list(mobile_dimensions),
                "mobile_png_full_page": mobile_dimensions[1] == geometry["mobile_scroll_height"],
                "pdf_sha256": digest(pdf_path), "pdf_pages": pages,
                "narrative_artifact_sha256": digest(artifact_path),
                "evidence_manifest_receipt_sha256": digest(evidence_receipt_path),
                "claim_source_audit_receipt_sha256": digest(claim_audit_path),
                "transport_verification_receipt_sha256": digest(transport_path),
            },
        })
    receipt = {
        "schema_version": "cross-company-live-publication-receipt-v1",
        "status": "passed",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "company_count": len(companies),
        "same_eight_module_contract": True,
        "data_boundary": "REAL snapshot plus integrity-passed frozen evidence; no raw evidence committed",
        "editorial_audit_receipt_sha256": digest(args.editorial_audit_receipt),
        "companies": companies,
    }
    _write_json(args.output / "publication-receipt.json", receipt)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("draft", "publish"):
        command = subparsers.add_parser(name)
        command.add_argument("--db", type=Path, required=True)
        command.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
        command.add_argument("--ticker", action="append")
        command.add_argument("--model", default="deepseek-v4-pro")
        command.add_argument("--prompt-version", default=CROSS_COMPANY_PROMPT_VERSION)
    draft = subparsers.choices["draft"]
    draft.add_argument("--key-file", type=Path, required=True)
    publish_parser = subparsers.choices["publish"]
    publish_parser.add_argument("--draft-dir", type=Path, required=True)
    publish_parser.add_argument("--approval-manifest", type=Path, required=True)
    publish_parser.add_argument("--transport-receipt", type=Path, required=True)
    publish_parser.add_argument("--editorial-audit-receipt", type=Path, required=True)
    capture_parser = subparsers.add_parser("verify-captures")
    capture_parser.add_argument("--db", type=Path, required=True)
    capture_parser.add_argument("--output", type=Path, required=True)
    capture_parser.add_argument("--ticker", action="append")
    revise_parser = subparsers.add_parser("revise")
    revise_parser.add_argument("--db", type=Path, required=True)
    revise_parser.add_argument("--draft-dir", type=Path, required=True)
    revise_parser.add_argument("--narrative-source-dir", type=Path, required=True)
    revise_parser.add_argument("--ticker", action="append")
    revise_parser.add_argument("--model", default="deepseek-v4-pro")
    revise_parser.add_argument("--prompt-version", default=CROSS_COMPANY_PROMPT_VERSION)
    revise_parser.add_argument("--editor", required=True)
    args = parser.parse_args()
    if hasattr(args, "output"):
        args.output = args.output if args.output.is_absolute() else ROOT / args.output
    for attribute in (
        "draft_dir", "narrative_source_dir", "approval_manifest", "transport_receipt",
        "editorial_audit_receipt",
    ):
        value = getattr(args, attribute, None)
        if isinstance(value, Path) and not value.is_absolute():
            setattr(args, attribute, ROOT / value)
    if args.command == "draft":
        generate_drafts(args)
    elif args.command == "publish":
        publish(args)
    elif args.command == "revise":
        revise_drafts(args)
    else:
        verify_captures(args)


if __name__ == "__main__":
    main()
