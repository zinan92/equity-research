#!/usr/bin/env python3
"""Verify N1-1 field coverage against the read-only Ainiu archive."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FIELDS = {
    "field", "surface", "meaning", "archive_layer", "nature", "cadence",
    "candidate_sources", "evidence", "confidence", "auto_update", "fallback",
    "production_method", "source_status",
}
VALID_NATURES = {"原始事实", "派生", "研究判断", "AI推断"}
VALID_CONFIDENCE = {"高", "中", "低", "判断类"}


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--docs-root", type=Path, default=ROOT / "docs" / "reverse")
    args = parser.parse_args()
    manifest = json.loads((args.archive_root / "data" / "exported" / "classification-manifest.json").read_text(encoding="utf-8"))
    provenance = json.loads((args.archive_root / "data" / "exported" / "provenance" / "provenance-records.json").read_text(encoding="utf-8"))
    payload = json.loads((args.docs_root / "field-attribution.json").read_text(encoding="utf-8"))
    if payload.get("schema_version") != "ainiu-field-attribution-v1":
        fail("unexpected schema version")
    main_expected = set(manifest["stock_field_classification"])
    levels_expected = set(manifest["levels_field_classification"])
    main_actual = {record["field"] for record in payload["fields"] if record["surface"] == "main_stock"}
    levels_actual = {record["field"] for record in payload["fields"] if record["surface"] == "levels_stock"}
    if main_actual != main_expected:
        fail(f"main coverage mismatch: missing={sorted(main_expected - main_actual)} extra={sorted(main_actual - main_expected)}")
    if levels_actual != levels_expected:
        fail(f"levels coverage mismatch: missing={sorted(levels_expected - levels_actual)} extra={sorted(levels_actual - levels_expected)}")
    if len(payload["fields"]) != 83:
        fail("expected exactly 83 field records")
    for record in payload["fields"]:
        if set(record) != REQUIRED_FIELDS:
            fail(f"invalid record keys for {record.get('surface')}.{record.get('field')}")
        if record["nature"] not in VALID_NATURES or record["confidence"] not in VALID_CONFIDENCE:
            fail(f"invalid attribution classification for {record['surface']}.{record['field']}")
        if not isinstance(record["auto_update"], bool) or not isinstance(record["candidate_sources"], list):
            fail(f"invalid automation/source shape for {record['surface']}.{record['field']}")
    direct_counts = {
        "eastmoney_f10_src_labels": sum(
            1 for item in provenance["records"]
            if item.get("key") == "src" and item.get("value") == "东财F10 主营构成"
        ),
        "eastmoney_earnings_src_labels": sum(
            1 for item in provenance["records"]
            if item.get("key") == "src" and item.get("value") == "东财预约披露"
        ),
    }
    if payload["summary"].get("direct_provenance") != direct_counts:
        fail(f"direct provenance mismatch: expected={direct_counts} got={payload['summary'].get('direct_provenance')}")
    for surface, field, expected_kind in (("main_stock", "stfin", "direct-provenance"), ("main_stock", "ern", "direct-provenance")):
        record = next(item for item in payload["fields"] if item["surface"] == surface and item["field"] == field)
        if record["evidence"].get("kind") != expected_kind or record["confidence"] != "高":
            fail(f"{field} must retain direct-provenance evidence")
    if not (args.docs_root / "field-attribution.md").is_file():
        fail("missing human-readable field-attribution.md")
    print("PASS: 83/83 fields; direct source labels F10=578 earnings=583")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
