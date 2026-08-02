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
    return {"status": "passed", "active_v4_path": [str(path.relative_to(ROOT)) for path in active], "forbidden_symbols_checked": list(forbidden)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=ROOT / "docs/evidence/v4-m4-generator-retirement.json")
    args = parser.parse_args()
    print(json.dumps(verify(args.manifest), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
