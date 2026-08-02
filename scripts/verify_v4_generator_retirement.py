#!/usr/bin/env python3
"""Machine-check the V4 entry-point/legacy boundary."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def verify(manifest_path: Path) -> dict[str, object]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    active = [ROOT / path for path in manifest.get("active_v4_path", [])]
    forbidden = tuple(manifest.get("retired_field_path", {}).get("forbidden_symbols", ()))
    violations: list[str] = []
    for path in active:
        source = path.read_text(encoding="utf-8")
        for symbol in forbidden:
            if symbol in source:
                violations.append(f"{path.relative_to(ROOT)} contains retired symbol {symbol}")
    if violations:
        raise ValueError("; ".join(violations))
    if manifest.get("retired_field_path", {}).get("no_current_v4_import") is not True:
        raise ValueError("retirement manifest does not assert no_current_v4_import")
    boundary = manifest.get("legacy_adapter_boundary") or {}
    if boundary.get("status") != "review_only_unpublished":
        raise ValueError("legacy adapter boundary is not review_only_unpublished")
    for relative in boundary.get("retired_entrypoints", []):
        path = ROOT / relative
        source = path.read_text(encoding="utf-8")
        if "adapt_official_sample" in source or "write_official_outputs" in source:
            raise ValueError(f"retired entrypoint still invokes legacy adapter: {relative}")
        if "retired" not in source.lower():
            raise ValueError(f"retired entrypoint lacks explicit retirement boundary: {relative}")
    generator = (ROOT / "product" / "v4_dossier_generator.py").read_text(encoding="utf-8")
    if "adapt_official_sample" in generator:
        raise ValueError("whole-dossier generator still imports the legacy official adapter")
    publication = (ROOT / "product" / "v4_publication.py").read_text(encoding="utf-8")
    gate = (ROOT / "product" / "v4_quality_gate.py").read_text(encoding="utf-8")
    if "publication_eligible" not in publication or "evaluate_round7_quality" not in publication:
        raise ValueError("publication path does not call the canonical quality gate")
    if "ROUND7_REQUIRED_HEADINGS" not in gate or "issuer_self_report_leak" not in gate:
        raise ValueError("quality gate lacks canonical structure/self-report blockers")
    return {"status": "passed", "active_v4_path": [str(path.relative_to(ROOT)) for path in active], "forbidden_symbols_checked": list(forbidden)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=ROOT / "docs/evidence/v4-m4-generator-retirement.json")
    args = parser.parse_args()
    print(json.dumps(verify(args.manifest), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
