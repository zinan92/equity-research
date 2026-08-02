#!/usr/bin/env python3
"""Publish one generated Round 7 dossier through the sole V4 entry point."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product"))

from v4_dossier_generator import generate_v4_dossier  # noqa: E402
from data_core.round7_chapter_generator import render_html  # noqa: E402
from v4_publication import _index  # noqa: E402
import hashlib


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("ticker")
    parser.add_argument("--round7-dossier", type=Path, required=True)
    parser.add_argument("--round7-markdown", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "artifacts" / "v4-reports",
    )
    args = parser.parse_args()
    output_dir = args.output_dir / args.ticker.upper()
    receipt = generate_v4_dossier(
        ticker=args.ticker,
        output_dir=output_dir,
        round7_dossier_path=args.round7_dossier,
        round7_markdown_path=args.round7_markdown,
        round7_profile_path=args.profile,
    )
    markdown_path = Path(str(receipt["output_path"]))
    html_path = output_dir / "report.html"
    html = render_html(
        markdown_path.read_text(encoding="utf-8"),
        title=f"{args.ticker.upper()} Round 7 / V4 公司档案",
    )
    html_path.write_text(html, encoding="utf-8")
    html_sha256 = hashlib.sha256(html.encode("utf-8")).hexdigest()
    receipt["html_path"] = str(html_path)
    receipt["html_sha256"] = html_sha256
    output = receipt.get("output")
    if isinstance(output, dict):
        output["html_path"] = str(html_path)
        output["html_sha256"] = html_sha256
    (output_dir / "receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    publication_path = args.output_dir / "publication-receipt.json"
    if publication_path.is_file():
        publication = json.loads(publication_path.read_text(encoding="utf-8"))
        row = {
            "ticker": args.ticker.upper(),
            "markdown_path": str(markdown_path),
            "html_path": str(html_path),
            "relative_html": f"{args.ticker.upper()}/report.html",
            "markdown_sha256": hashlib.sha256(markdown_path.read_bytes()).hexdigest(),
            "html_sha256": html_sha256,
            "reader_characters": int((receipt.get("output") or {}).get("reader_characters") or 0),
            "source_count": len(receipt.get("source_urls") or []),
            "status": receipt.get("status"),
            "tier_credit": receipt.get("tier_credit"),
        }
        rows = [
            item for item in publication.get("companies", [])
            if item.get("ticker") != args.ticker.upper()
        ] + [row]
        rows.sort(key=lambda item: str(item.get("ticker")))
        index_path = args.output_dir / "index.html"
        index_path.write_text(_index(rows), encoding="utf-8")
        publication["companies"] = rows
        publication.setdefault("additional_whole_dossier_receipts", []).append(str(output_dir / "receipt.json"))
        publication["additional_whole_dossier_receipts"] = list(dict.fromkeys(publication["additional_whole_dossier_receipts"]))
        publication["index_sha256"] = hashlib.sha256(index_path.read_bytes()).hexdigest()
        publication_path.write_text(json.dumps(publication, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
