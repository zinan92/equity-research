#!/usr/bin/env python3
"""Lightweight contract check for a dossier template and a produced sample."""
from __future__ import annotations

import argparse
import re
from pathlib import Path


REQUIRED_HEADINGS = (
    "## 1. 一句话定位", "## 2. 身份、创始人与治理", "## 3. 技术来源与发展史",
    "## 4. 商业模式与业务线", "## 5. 财务与经营时间序列", "## 6. 护城河的证据链",
    "## 7. 风险、反题材与观察触发器", "## 8. 研究结论与待补问题",
    "## 9. 生产记录", "## Sources",
)


def verify(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    problems = [f"missing heading: {heading}" for heading in REQUIRED_HEADINGS if heading not in text]
    if "schema_version: dossier-template-v1" not in text:
        problems.append("missing dossier schema version")
    source_ids = set(re.findall(r"\| (S-\d+) \|", text))
    cited = set(re.findall(r"\[(S-\d+)\]", text))
    if cited - source_ids:
        problems.append(f"cited source IDs absent from source table: {sorted(cited - source_ids)}")
    if path.name != "template-v1.md" and source_ids and not re.search(r"https://", text):
        problems.append("source table has no https URL")
    if path.name != "template-v1.md" and not re.search(r"\[F-\d+\]", text):
        problems.append("sample has no fact IDs")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()
    problems = {str(path): verify(path) for path in args.paths}
    failed = {path: items for path, items in problems.items() if items}
    if failed:
        for path, items in failed.items():
            print(path)
            for item in items:
                print(f"  - {item}")
        return 1
    print(f"PASS: {len(args.paths)} dossier documents")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
