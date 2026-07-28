#!/usr/bin/env python3
"""Create a runtime-only receipt for the three official vertical-slice filings."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "product") not in sys.path:
    sys.path.insert(0, str(ROOT / "product"))

from product.data_core.e4_page_level_filing_facts import compile_page_level_filing_facts
from product.data_core.vertical_slices import official_evidence_anchors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", required=True, type=Path)
    args = parser.parse_args()
    sources = []
    for anchor in official_evidence_anchors():
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                request = Request(anchor.document_url, headers={"User-Agent": "ParkEquityResearch/1.0 (official-filing verification)"})
                with urlopen(request, timeout=45) as response:
                    sources.append((anchor, response.read()))
                break
            except Exception as exc:
                last_error = exc
                if attempt == 2:
                    raise RuntimeError(f"official filing download failed for {anchor.ticker} after 3 attempts") from exc
                time.sleep(1 + attempt)
    receipt = compile_page_level_filing_facts(sources)
    args.runtime_root.mkdir(parents=True, exist_ok=True)
    path = args.runtime_root / f"page-level-filing-facts-{receipt['receipt_hash'][:16]}.json"
    path.write_text(json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
