#!/usr/bin/env python3
"""Package one canonical Round 7 dossier after the publication quality gate."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
import hashlib
import re

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product"))

from v4_dossier_generator import generate_v4_dossier  # noqa: E402
from v4_publication import _index, public_row_is_current, _quarantine_stale_company_dir  # noqa: E402
from v4_quality_gate import evaluate_round7_quality, portable_path, write_quality_gate_receipt  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("ticker")
    parser.add_argument("--round7-dossier", type=Path, required=True)
    parser.add_argument("--round7-markdown", type=Path, required=True)
    parser.add_argument(
        "--profile",
        type=Path,
        help="optional issuer profile; when omitted, the canonical receipt remains the source of truth",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "artifacts" / "v4-reports",
    )
    args = parser.parse_args()
    ticker = args.ticker.upper()
    if not re.fullmatch(r"[0-9]{6}\.[A-Z]{2}", ticker):
        raise SystemExit(f"unsafe ticker: {ticker}")
    canonical_root = (ROOT / "artifacts" / "round7-dossiers").resolve()
    for candidate in (args.round7_dossier, args.round7_markdown):
        try:
            candidate.resolve().relative_to(canonical_root)
        except ValueError as exc:
            raise SystemExit(f"canonical Round 7 input is outside source root: {candidate}") from exc
    canonical_html = args.round7_markdown.with_suffix(".html")
    gate = evaluate_round7_quality(
        dossier_path=args.round7_dossier,
        markdown_path=args.round7_markdown,
        html_path=canonical_html,
        require_canonical_root=True,
        expected_ticker=ticker,
    )
    try:
        args.output_dir.resolve().relative_to(canonical_root)
    except ValueError:
        pass
    else:
        raise SystemExit("output directory must not be inside canonical Round 7 source root")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    gate_path = args.output_dir / f"{ticker}.quality-gate.json"
    write_quality_gate_receipt(gate, gate_path)
    publication_path = args.output_dir / "publication-receipt.json"
    publication = json.loads(publication_path.read_text(encoding="utf-8")) if publication_path.is_file() else {
        "schema_version": "park-v4-publication-receipt-v1",
        "contract_schema_version": "park-v4-dossier-v1",
        "companies": [],
        "review_queue": [],
    }
    rows = [
        item for item in publication.get("companies", [])
        if item.get("ticker") != ticker and public_row_is_current(item, output_root=args.output_dir)
    ]
    queue = [item for item in publication.get("review_queue", []) if item.get("ticker") != ticker]
    receipt: dict[str, object] | None = None
    if gate.get("publication_eligible") is True:
        output_dir = args.output_dir / ticker
        receipt = generate_v4_dossier(
            ticker=ticker,
            output_dir=output_dir,
            round7_dossier_path=args.round7_dossier,
            round7_markdown_path=args.round7_markdown,
            round7_profile_path=args.profile,
        )
        markdown_path = Path(str(receipt["output_path"]))
        output_html = output_dir / "report.html"
        output_html.write_bytes(canonical_html.read_bytes())
        package_receipt_path = output_dir / "receipt.json"
        package_receipt = json.loads(package_receipt_path.read_text(encoding="utf-8"))
        package_receipt.setdefault("output", {})["html_path"] = str(output_html)
        package_receipt["output"]["html_sha256"] = hashlib.sha256(output_html.read_bytes()).hexdigest()
        package_receipt.setdefault("artifacts", {})["html_path"] = str(output_html)
        package_receipt["artifacts"]["html_sha256"] = hashlib.sha256(output_html.read_bytes()).hexdigest()
        package_receipt.pop("receipt_hash", None)
        package_receipt["receipt_hash"] = hashlib.sha256(
            json.dumps(package_receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        package_receipt_path.write_text(json.dumps(package_receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        receipt = package_receipt
        row = {
            "ticker": ticker,
            "markdown_path": str(markdown_path),
            "html_path": str(output_html),
            "relative_html": f"{ticker}/report.html",
            "markdown_sha256": hashlib.sha256(markdown_path.read_bytes()).hexdigest(),
            "html_sha256": hashlib.sha256(output_html.read_bytes()).hexdigest(),
            "reader_characters": int((receipt.get("output") or {}).get("reader_characters") or receipt.get("reader_characters") or 0),
            "source_count": len(receipt.get("source_urls") or []),
            "status": "passed",
            "tier_credit": "none",
            "publication_eligible": True,
            "quality_gate_path": portable_path(gate_path),
            "quality_gate_sha256": hashlib.sha256(gate_path.read_bytes()).hexdigest(),
        }
        rows.append(row)
    else:
        stale_path = _quarantine_stale_company_dir(output_root=args.output_dir, ticker=ticker)
        queue.append({
            "ticker": ticker,
            "status": gate.get("status"),
            "quality_gate_path": portable_path(gate_path),
            "quality_gate_sha256": hashlib.sha256(gate_path.read_bytes()).hexdigest(),
            "source_receipt_path": portable_path(args.round7_dossier),
            "source_receipt_sha256": hashlib.sha256(args.round7_dossier.read_bytes()).hexdigest(),
            "run_id": (json.loads(args.round7_dossier.read_text(encoding="utf-8")).get("production_record") or {}).get("run_id"),
            "blocker_count": len(gate.get("blockers") or []),
            "blockers": gate.get("blockers") or [],
            "stale_publication_quarantined": stale_path,
        })
    rows.sort(key=lambda item: str(item.get("ticker")))
    queue.sort(key=lambda item: str(item.get("ticker")))
    index_path = args.output_dir / "index.html"
    index_path.write_text(_index(rows, output_root=args.output_dir), encoding="utf-8")
    review_payload = {"schema_version": "park-v4-publication-review-queue-v1", "items": queue}
    review_payload["receipt_hash"] = hashlib.sha256(json.dumps(review_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    (args.output_dir / "review-queue.json").write_text(json.dumps(review_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    publication.update({
        "status": "passed" if rows and not queue else ("blocked" if any(item.get("status") == "blocked" for item in queue) else "review_queue"),
        "canonical_source_root": portable_path(args.round7_dossier.parent),
        "companies": rows,
        "review_queue": queue,
        "index_path": portable_path(index_path),
        "index_sha256": hashlib.sha256(index_path.read_bytes()).hexdigest(),
        "fresh_model_calls": 0,
        "new_official_documents": 0,
        "is_live_research": False,
        "tier_credit": "none",
        "boundary": "Blocked/pending canonical dossiers are review-only and never receive a public index/mobile link.",
    })
    # A single-ticker refresh must not carry historical package receipt paths
    # forward as if they were active public artifacts.
    publication.pop("additional_whole_dossier_receipts", None)
    publication.setdefault("source_receipts", [])
    source_entry = {
        "ticker": ticker,
        "path": portable_path(args.round7_dossier),
        "sha256": hashlib.sha256(args.round7_dossier.read_bytes()).hexdigest(),
        "run_id": (json.loads(args.round7_dossier.read_text(encoding="utf-8")).get("production_record") or {}).get("run_id"),
        "quality_gate": portable_path(gate_path),
        "quality_gate_sha256": hashlib.sha256(gate_path.read_bytes()).hexdigest(),
    }
    publication["source_receipts"] = [item for item in publication["source_receipts"] if item.get("ticker") != ticker] + [source_entry]
    publication["source_receipts"].sort(key=lambda item: str(item.get("ticker")))
    publication.pop("receipt_hash", None)
    publication["receipt_hash"] = hashlib.sha256(json.dumps(publication, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    publication_path.write_text(json.dumps(publication, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ticker": ticker, "quality_gate": gate, "receipt": receipt}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
