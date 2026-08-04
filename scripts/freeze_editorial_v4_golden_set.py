#!/usr/bin/env python3
"""Freeze the Park-approved V4/P3 dossiers as a replayable golden set.

The manifest records hashes and contract measurements only.  It never copies
report prose into a prompt or grants publication/Tier credit.  A later batch
can compare its machine/QA shape to this set without using the golden text as
evidence.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product"))

from editorial_v4_contract import AGGRESSIVE_JUDGMENT_CUES, SECTIONS, canonical_hash  # noqa: E402
from verify_editorial_v4_p3 import audit_one  # noqa: E402


DEFAULT_TICKERS = ("000333.SZ", "600519.SH", "600900.SH", "300750.SZ", "000001.SZ")


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def freeze(*, p3_root: Path, output: Path, tickers: tuple[str, ...]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for ticker in tickers:
        audit = audit_one(p3_root, ticker)
        if audit["final_status"] != "passed":
            raise ValueError(f"golden candidate {ticker} failed completion audit: {audit['failed_checks']}")
        report_path = p3_root / ticker / "report.json"
        receipt_path = p3_root / ticker / "quality-loop-receipt.json"
        packet_path = p3_root / "evidence-packets" / f"{ticker}.json"
        report = _read(report_path)
        receipt = _read(receipt_path)
        packet = _read(packet_path)
        sections = {
            str(item.get("id")): len(str(item.get("body") or ""))
            for item in report.get("sections") or []
            if isinstance(item, dict)
        }
        rows.append({
            "ticker": ticker,
            "issuer_name": report.get("issuer_name"),
            "final_iteration": receipt.get("final_iteration"),
            "report_sha256": canonical_hash(report),
            "packet_hash": packet.get("packet_hash"),
            "report_chars": sum(sections.values()),
            "sections": sections,
            "section_contract": [
                {"id": section_id, "minimum_chars": minimum}
                for section_id, _title, minimum in SECTIONS
            ],
            "judgment_count": sum(
                1 for claim in report.get("claims") or []
                if isinstance(claim, dict) and claim.get("kind") == "judgment"
            ),
            "aggressive_judgment_count": sum(
                1 for claim in report.get("claims") or []
                if isinstance(claim, dict)
                and claim.get("kind") == "judgment"
                and AGGRESSIVE_JUDGMENT_CUES.search(str(claim.get("text") or ""))
            ),
            "official_packet": True,
            "model_provider": report.get("production_record", {}).get("model_provider"),
            "review_only": True,
            "no_tier_credit": True,
            "no_publication_credit": True,
        })
    return {
        "schema_version": "editorial-v4-golden-set-v1",
        "frozen_at": date.today().isoformat(),
        "acceptance_basis": "Park explicitly approved the five-report V4/P3 batch in the controlling thread.",
        "park_review_status": "accepted",
        "golden_contract": "Round 7/Ainiu V4 seven-section whole-report contract",
        "prose_reuse_for_generation": False,
        "evidence_reuse_for_generation": False,
        "review_only": True,
        "no_tier_credit": True,
        "no_publication_credit": True,
        "tickers": list(tickers),
        "reports": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--p3-root", type=Path, default=ROOT / "artifacts/editorial-v4-p3")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/editorial-v4-p4/golden-set-manifest.json")
    parser.add_argument("tickers", nargs="*", default=list(DEFAULT_TICKERS))
    args = parser.parse_args()
    result = freeze(p3_root=args.p3_root, output=args.output, tickers=tuple(item.upper() for item in args.tickers))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "park_review_status": result["park_review_status"], "tickers": result["tickers"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
