#!/usr/bin/env python3
"""Compile a runtime-only page-fact receipt from already captured official PDFs."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "product")]

from product.data_core.e4_page_level_filing_facts import FilingFactSource, compile_page_level_filing_fact_batch


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("captures", type=Path, help="runtime-only official capture manifest")
    parser.add_argument("--runtime-root", required=True, type=Path)
    args = parser.parse_args()
    rows = json.loads(args.captures.read_text(encoding="utf-8"))
    sources = []
    for row in rows:
        if row.get("status") != "captured":
            continue
        sources.append((FilingFactSource(
            str(row["ticker"]), str(row["document_id"]), str(row["raw_hash"]), str(row["source_url"]),
            str(row.get("report_period") or "unknown"),
        ), Path(str(row["path"])).read_bytes()))
    receipt = compile_page_level_filing_fact_batch(sources)
    args.runtime_root.mkdir(parents=True, exist_ok=True)
    path = args.runtime_root / f"page-level-filing-facts-{receipt['receipt_hash'][:16]}.json"
    path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"path": str(path), "counts": receipt["counts"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
