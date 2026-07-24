#!/usr/bin/env python3
"""Lightweight contract check for a dossier template and a produced sample."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


REQUIRED_HEADINGS = (
    "## 1. 一句话定位", "## 2. 身份、创始人与治理", "## 3. 技术来源与发展史",
    "## 4. 商业模式与业务线", "## 5. 财务与经营时间序列", "## 6. 护城河的证据链",
    "## 7. 风险、反题材与观察触发器", "## 8. 研究结论与待补问题",
    "## 9. 生产记录", "## Sources",
)
NUMERIC_FACT = re.compile(r"\d")
SOURCE_CITATION = re.compile(r"\[S-\d+\]")
SOURCE_ROW = re.compile(r"^\| (S-\d+) \|")
TABLE_DIVIDER = re.compile(r"^\|(?:\s*:?-+:?\s*\|)+$")


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
    if path.name != "template-v1.md":
        source_rows = [line for line in text.splitlines() if SOURCE_ROW.match(line)]
        if len(source_rows) < 2:
            problems.append("sample must contain at least two source rows")
        for line in source_rows:
            if "https://" not in line:
                problems.append(f"source row has no https URL: {line[:80]}")
            if not re.search(r"\b20\d{2}[- 年]", line):
                problems.append(f"source row has no publication/access date: {line[:80]}")
        if "| token 记录 |" not in text:
            problems.append("production record has no token telemetry field")
        if "| 采集/写作耗时 |" not in text:
            problems.append("production record has no elapsed-time field")

        in_factual_sections = False
        for line_number, line in enumerate(text.splitlines(), start=1):
            if line.startswith("## 1. "):
                in_factual_sections = True
            elif line.startswith("## 9. "):
                in_factual_sections = False
            if (
                in_factual_sections
                and NUMERIC_FACT.search(line)
                and not line.startswith("#")
                and not TABLE_DIVIDER.match(line)
                and not SOURCE_CITATION.search(line)
            ):
                problems.append(f"numeric fact without source citation at line {line_number}")
    return problems


def structure_signature(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    structural_lines = [
        line.strip()
        for line in text.splitlines()
        if line.startswith("## ") or TABLE_DIVIDER.match(line)
    ]
    return hashlib.sha256("\n".join(structural_lines).encode()).hexdigest()


def verify_manifest(path: Path) -> list[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    problems: list[str] = []
    blind_set = payload.get("blind_evaluation_set")
    if not isinstance(blind_set, list) or len(blind_set) != 5:
        problems.append("blind evaluation set must contain exactly five tickers")
        blind_set = []
    if blind_set and not any(not str(ticker).endswith((".SZ", ".SH")) for ticker in blind_set):
        problems.append("blind evaluation set must contain at least one overseas company")
    runs = payload.get("runs")
    if not isinstance(runs, list):
        return problems + ["manifest runs must be a list"]
    by_ticker = {str(run.get("ticker")): run for run in runs if isinstance(run, dict)}
    missing_runs = sorted(set(map(str, blind_set)) - set(by_ticker))
    if missing_runs:
        problems.append(f"blind evaluation tickers have no production run: {missing_runs}")
    signatures = set()
    for ticker, run in by_ticker.items():
        relative_path = run.get("path")
        document_path = path.parent / str(relative_path or "")
        if not relative_path or not document_path.is_file():
            problems.append(f"{ticker}: dossier path is missing")
            continue
        signatures.add(structure_signature(document_path))
        start = run.get("goal_token_start")
        end = run.get("goal_token_end")
        delta = run.get("goal_token_delta")
        if not all(isinstance(value, int) for value in (start, end, delta)):
            problems.append(f"{ticker}: token interval is incomplete")
        elif end - start != delta or delta < 0:
            problems.append(f"{ticker}: token delta does not match interval")
        if not isinstance(run.get("elapsed_minutes"), int) or run["elapsed_minutes"] <= 0:
            problems.append(f"{ticker}: elapsed minutes must be positive")
        if not isinstance(run.get("manual_intervention_points"), list) or not run["manual_intervention_points"]:
            problems.append(f"{ticker}: manual intervention points are missing")
        hashes = run.get("source_capture_sha256")
        if not isinstance(hashes, list) or not hashes:
            problems.append(f"{ticker}: source capture hashes are missing")
        elif any(not re.fullmatch(r"[0-9a-f]{64}", str(value)) for value in hashes):
            problems.append(f"{ticker}: source capture hash is malformed")
    if len(signatures) != 1:
        problems.append("dossier runs do not share one structural signature")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    problems = {str(path): verify(path) for path in args.paths}
    if args.manifest:
        problems[str(args.manifest)] = verify_manifest(args.manifest)
    failed = {path: items for path, items in problems.items() if items}
    if failed:
        for path, items in failed.items():
            print(path)
            for item in items:
                print(f"  - {item}")
        return 1
    if args.json_out:
        payload = {
            "schema_version": "dossier-validation-v2",
            "documents": [
                {
                    "path": str(path),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "structure_signature": structure_signature(path),
                }
                for path in args.paths
            ],
        }
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(f"PASS: {len(args.paths)} dossier documents")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
