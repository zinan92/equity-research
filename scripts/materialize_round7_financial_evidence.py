#!/usr/bin/env python3
"""Extract page facts from the last receipt that predates the Round 7 cutover.

The source receipt mixed page facts with a retired report contract.  This
script validates the immutable Git blob and copies only the independent,
official page-fact records into a new evidence artifact.  No old section
status, Tier result, or prose is carried forward.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product"))

from data_core.e4_page_level_filing_facts import FilingNumericFact  # noqa: E402


SCHEMA_VERSION = "round7-financial-page-evidence-v1"
SOURCE_COMMIT = "2e465b227dfc3c3c7321838155733515c7add6e6"
SOURCE_PATH = "artifacts/e4-reports/e4-m4-model-wiring.json"
SOURCE_SCHEMA = "round7-m2-wiring-migration-v1"
SOURCE_RECEIPT_HASH = (
    "6a84b44ec9b4af714ca2902a19ff24c15a7ba1073fab90124e175cfcc8b60381"
)
OFFICIAL_HOSTS = {
    "static.cninfo.com.cn",
    "www.sse.com.cn",
    "static.sse.com.cn",
    "www.szse.cn",
    "disc.static.szse.cn",
    "www.bse.cn",
}


def canonical_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode()
    ).hexdigest()


def load_source_blob() -> tuple[bytes, dict]:
    blob = subprocess.check_output(
        ["git", "show", f"{SOURCE_COMMIT}:{SOURCE_PATH}"],
        cwd=ROOT,
    )
    value = json.loads(blob)
    if value.get("schema_version") != SOURCE_SCHEMA:
        raise ValueError("source wiring schema mismatch")
    payload = {key: item for key, item in value.items() if key != "receipt_hash"}
    if (
        value.get("receipt_hash") != SOURCE_RECEIPT_HASH
        or canonical_hash(payload) != SOURCE_RECEIPT_HASH
    ):
        raise ValueError("source wiring receipt identity mismatch")
    return blob, value


def build_artifact(*, ticker: str) -> dict:
    blob, source = load_source_blob()
    rows = [
        item
        for item in source.get("rows", [])
        if str(item.get("ticker") or "").upper() == ticker.upper()
    ]
    if len(rows) != 1:
        raise ValueError("source wiring must contain exactly one ticker row")
    raw_facts = rows[0].get("result", {}).get("page_facts")
    if not isinstance(raw_facts, list) or not raw_facts:
        raise ValueError("source wiring row has no page facts")
    facts = []
    for index, raw in enumerate(raw_facts):
        fact = FilingNumericFact(**raw)
        fact.validate()
        host = urlparse(fact.source_url).hostname
        if (
            fact.ticker.upper() != ticker.upper()
            or fact.statement_scope != "consolidated"
            or host not in OFFICIAL_HOSTS
        ):
            raise ValueError(f"page fact {index} is outside the official boundary")
        facts.append(raw)
    artifact = {
        "schema_version": SCHEMA_VERSION,
        "data_kind": "real",
        "ticker": ticker.upper(),
        "source": {
            "commit": SOURCE_COMMIT,
            "path": SOURCE_PATH,
            "blob_sha256": hashlib.sha256(blob).hexdigest(),
            "receipt_hash": SOURCE_RECEIPT_HASH,
            "carried_forward_fields": ["page_facts"],
            "retired_contract_fields_carried_forward": False,
        },
        "page_facts": facts,
    }
    artifact["receipt_hash"] = canonical_hash(artifact)
    return artifact


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("ticker")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    artifact = build_artifact(ticker=args.ticker)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "ticker": artifact["ticker"],
                "page_facts": len(artifact["page_facts"]),
                "receipt_hash": artifact["receipt_hash"],
                "out": str(args.out),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
