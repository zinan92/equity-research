#!/usr/bin/env python3
"""Verify the two persistent E4 wired-report outputs without changing data."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def summary(receipt_path: Path) -> dict:
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    html = Path(receipt["html_path"])
    if not html.is_file() or "数据时点" not in html.read_text(encoding="utf-8"):
        raise ValueError(f"missing or invalid report HTML: {html}")
    if receipt.get("tier") == "A":
        raise ValueError("wired report must not reach Tier A")
    if f"含 {receipt.get('unreviewed_judgment_count')} 项未审阅 AI 判断" not in html.read_text(encoding="utf-8"):
        raise ValueError("report does not display the unreviewed judgment count")
    states = Counter(item["status"] for item in receipt["sections"])
    if sum(states.values()) != 18:
        raise ValueError("report does not contain 18 C1 sections")
    return {"ticker": receipt["ticker"], "html_path": str(html), "receipt_path": str(receipt_path), "tier": receipt["tier"], "tier_reasons": receipt["tier_reasons"], "unreviewed_judgment_count": receipt["unreviewed_judgment_count"], "section_counts": dict(states), "sections": [{key: item.get(key) for key in ("section_id", "status", "status_reason", "present_required", "missing_required")} for item in receipt["sections"]]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("receipts", nargs="+", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    reports = [summary(path) for path in args.receipts]
    result = {"schema_version": "e4-wired-report-verification-v1", "status": "passed", "reports": reports}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
