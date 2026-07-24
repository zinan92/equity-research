#!/usr/bin/env python3
"""Build and score a local-only blind dossier comparison.

The benchmark archive is read at runtime. Its prose and the A/B key are never
written into repository-tracked paths by this tool.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DIMENSIONS = ("detail", "evidence_density", "anti_hype_discipline")
REQUIRED_ROLES = {"park", "external_reader"}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _review_body(text: str) -> str:
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        try:
            close = lines.index("---", 1)
            lines = lines[close + 1 :]
        except ValueError:
            pass
    body = "\n".join(lines).strip()
    if "\n## 9. 生产记录" in body:
        body = body.split("\n## 9. 生产记录", 1)[0].rstrip()
    return body


def build_pack(
    *,
    archive_path: Path,
    manifest_path: Path,
    output_path: Path,
    key_path: Path,
) -> dict[str, Any]:
    archive = _read_json(archive_path)
    records = archive.get("records_by_code")
    if not isinstance(records, dict):
        raise ValueError("archive must contain records_by_code")
    manifest = _read_json(manifest_path)
    tickers = manifest.get("blind_evaluation_set")
    runs = {
        str(run.get("ticker")): run
        for run in manifest.get("runs", [])
        if isinstance(run, dict)
    }
    if not isinstance(tickers, list) or len(tickers) != 5:
        raise ValueError("manifest blind_evaluation_set must contain five tickers")

    pair_sections: list[str] = []
    key_pairs: list[dict[str, Any]] = []
    for index, raw_ticker in enumerate(tickers, start=1):
        ticker = str(raw_ticker)
        archive_code = ticker.split(".", 1)[0]
        benchmark = records.get(archive_code)
        run = runs.get(ticker)
        if not isinstance(benchmark, dict) or not isinstance(benchmark.get("md"), str):
            raise ValueError(f"benchmark dossier missing for {ticker}")
        if not isinstance(run, dict):
            raise ValueError(f"production run missing for {ticker}")
        own_path = manifest_path.parent / str(run.get("path") or "")
        if not own_path.is_file():
            raise ValueError(f"self-produced dossier missing for {ticker}")
        own_text = _review_body(own_path.read_text(encoding="utf-8"))
        benchmark_text = str(benchmark["md"]).strip()
        own_label = "A" if secrets.randbits(1) == 0 else "B"
        benchmark_label = "B" if own_label == "A" else "A"
        documents = {own_label: own_text, benchmark_label: benchmark_text}
        pair_id = f"P{index}"
        pair_sections.extend(
            [
                f"## {pair_id} · {ticker}",
                "",
                "### Document A",
                "",
                documents["A"],
                "",
                "### Document B",
                "",
                documents["B"],
                "",
            ]
        )
        key_pairs.append(
            {
                "pair_id": pair_id,
                "ticker": ticker,
                "self_label": own_label,
                "benchmark_label": benchmark_label,
                "self_sha256": _sha256_bytes(own_text.encode()),
                "benchmark_sha256": _sha256_bytes(benchmark_text.encode()),
            }
        )

    score_rows = [
        "| Pair | Document | Detail 1–5 | Evidence density 1–5 | Anti-hype discipline 1–5 | Notes |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for pair in key_pairs:
        for label in ("A", "B"):
            score_rows.append(f"| {pair['pair_id']} | {label} |  |  |  |  |")
    pack = "\n".join(
        [
            "# Dossier Blind Review Pack",
            "",
            "Read each A/B pair without trying to identify the producer. Score each document independently on detail, evidence density, and anti-hype discipline from 1 to 5.",
            "",
            *pair_sections,
            "## Score sheet",
            "",
            *score_rows,
            "",
        ]
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(pack, encoding="utf-8")
    key_payload = {
        "schema_version": "dossier-blind-key-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "pack_sha256": _sha256_bytes(pack.encode()),
        "pairs": key_pairs,
    }
    key_path.write_text(
        json.dumps(key_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "pair_count": len(key_pairs),
        "pack_sha256": key_payload["pack_sha256"],
        "pack_path": str(output_path),
        "key_path": str(key_path),
    }


def _score_document(value: Any, *, reviewer_id: str, pair_id: str, label: str) -> int:
    if not isinstance(value, dict):
        raise ValueError(f"{reviewer_id}/{pair_id}/{label}: score must be an object")
    total = 0
    for dimension in DIMENSIONS:
        score = value.get(dimension)
        if not isinstance(score, int) or isinstance(score, bool) or not 1 <= score <= 5:
            raise ValueError(
                f"{reviewer_id}/{pair_id}/{label}/{dimension}: score must be 1..5"
            )
        total += score
    return total


def score_pack(*, key_path: Path, scores_path: Path) -> dict[str, Any]:
    key = _read_json(key_path)
    scores = _read_json(scores_path)
    key_pairs = {
        str(pair["pair_id"]): pair
        for pair in key.get("pairs", [])
        if isinstance(pair, dict)
    }
    reviewers = scores.get("reviewers")
    if not isinstance(reviewers, list) and isinstance(scores.get("reviewer"), dict):
        reviewers = [scores["reviewer"]]
    if not isinstance(reviewers, list):
        raise ValueError("scores must contain reviewers")
    roles = {str(reviewer.get("role")) for reviewer in reviewers if isinstance(reviewer, dict)}
    missing_roles = REQUIRED_ROLES - roles

    observations: list[dict[str, Any]] = []
    for reviewer in reviewers:
        reviewer_id = str(reviewer.get("id") or "")
        role = str(reviewer.get("role") or "")
        by_pair = {
            str(row.get("pair_id")): row
            for row in reviewer.get("scores", [])
            if isinstance(row, dict)
        }
        if set(by_pair) != set(key_pairs):
            raise ValueError(f"{reviewer_id}: scores must cover every pair exactly once")
        for pair_id, pair in key_pairs.items():
            row = by_pair[pair_id]
            totals = {
                label: _score_document(
                    row.get(label),
                    reviewer_id=reviewer_id,
                    pair_id=pair_id,
                    label=label,
                )
                for label in ("A", "B")
            }
            self_total = totals[str(pair["self_label"])]
            benchmark_total = totals[str(pair["benchmark_label"])]
            observations.append(
                {
                    "reviewer_id": reviewer_id,
                    "role": role,
                    "pair_id": pair_id,
                    "ticker": pair["ticker"],
                    "self_total": self_total,
                    "benchmark_total": benchmark_total,
                    "ratio": self_total / benchmark_total,
                }
            )
    self_sum = sum(row["self_total"] for row in observations)
    benchmark_sum = sum(row["benchmark_total"] for row in observations)
    ratio = self_sum / benchmark_sum
    return {
        "schema_version": "dossier-blind-score-receipt-v1",
        "reviewer_count": len(reviewers),
        "present_roles": sorted(roles),
        "missing_roles": sorted(missing_roles),
        "pair_count": len(key_pairs),
        "observations": observations,
        "self_score_total": self_sum,
        "benchmark_score_total": benchmark_sum,
        "aggregate_ratio": ratio,
        "threshold": 0.8,
        "passed": not missing_roles and ratio >= 0.8,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build")
    build.add_argument("--archive", required=True, type=Path)
    build.add_argument("--manifest", required=True, type=Path)
    build.add_argument("--out", required=True, type=Path)
    build.add_argument("--key-out", required=True, type=Path)
    score = subparsers.add_parser("score")
    score.add_argument("--key", required=True, type=Path)
    score.add_argument("--scores", required=True, type=Path)
    score.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    if args.command == "build":
        receipt = build_pack(
            archive_path=args.archive,
            manifest_path=args.manifest,
            output_path=args.out,
            key_path=args.key_out,
        )
    else:
        receipt = score_pack(key_path=args.key, scores_path=args.scores)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(receipt, ensure_ascii=False))
    return 0 if receipt.get("passed", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
