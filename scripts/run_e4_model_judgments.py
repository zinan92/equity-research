#!/usr/bin/env python3
"""Run the generic receipt-bound model judgment generator for one issuer."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product"))

from company_research import company_adapter  # noqa: E402
from data_core.e4_model_judgments import generate_model_judgments  # noqa: E402
from deepseek_writer import DEFAULT_KEY_FILE, DEFAULT_MODEL  # noqa: E402


def _verify_receipt(receipt: Mapping[str, Any], *, kind: str) -> str:
    schema = str(receipt.get("schema_version") or "")
    allowed = {
        "financial": {
            "e4-m2-research-wiring-v1": "default",
            "e4-financial-sequence-batch-v1": "compact",
        },
        "narrative": {
            "e4-official-narrative-evidence-v1": "unicode",
            "e4-l2-narrative-batch-v1": "compact",
        },
    }[kind]
    if schema not in allowed or receipt.get("data_kind") != "real":
        raise ValueError(kind + " receipt is not an accepted real schema")
    payload = {
        key: value
        for key, value in receipt.items()
        if key not in {"receipt_hash", "receipt_id"}
    }
    mode = allowed[schema]
    if mode == "default":
        serialized = json.dumps(payload, sort_keys=True, default=str)
    elif mode == "unicode":
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    else:
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
    observed = hashlib.sha256(serialized.encode()).hexdigest()
    if observed != receipt.get("receipt_hash"):
        raise ValueError(kind + " receipt hash mismatch")
    expected_id = schema + ":" + observed
    if receipt.get("receipt_id") not in (None, expected_id):
        raise ValueError(kind + " receipt id mismatch")
    boundary = receipt.get("truth_boundary") or {}
    if schema in {
        "e4-financial-sequence-batch-v1",
        "e4-official-narrative-evidence-v1",
        "e4-l2-narrative-batch-v1",
    } and boundary.get("official_cninfo_pdf_only") is not True:
        raise ValueError(kind + " receipt lacks official-PDF truth boundary")
    return expected_id


def _financial_facts(receipt: Mapping[str, Any], ticker: str) -> list[dict[str, Any]]:
    for row in receipt.get("rows") or ():
        if str(row.get("ticker") or "").upper() == ticker:
            result = row.get("result") or {}
            facts = list(result.get("page_facts") or ())
            break
    else:
        facts = []
        for row in receipt.get("tickers") or ():
            if str(row.get("ticker") or "").upper() != ticker:
                continue
            facts = [
                fact
                for report in row.get("reports") or ()
                if report.get("status") == "available"
                for fact in report.get("facts") or ()
            ]
            break
    if not facts:
        raise ValueError("financial receipt has no facts for requested ticker")
    for fact in facts:
        if (
            str(fact.get("ticker") or ticker).upper() != ticker
            or not str(fact.get("source_url") or "").startswith(
                "https://static.cninfo.com.cn/"
            )
            or not fact.get("document_id")
            or not fact.get("raw_hash")
            or not fact.get("page_number")
        ):
            raise ValueError("financial fact violates official page identity")
    return facts


def _narrative_blocks(receipt: Mapping[str, Any], ticker: str) -> list[dict[str, Any]]:
    if receipt.get("data_kind") != "real":
        raise ValueError("narrative receipt must be a real run")
    if receipt.get("ticker") is not None:
        if str(receipt.get("ticker") or "").upper() != ticker:
            raise ValueError("narrative receipt ticker mismatch")
        blocks = receipt.get("blocks") or ()
    else:
        cohort = {str(item).upper() for item in receipt.get("cohort") or ()}
        if ticker not in cohort:
            raise ValueError("narrative batch does not contain requested ticker")
        blocks = [
            block
            for block in receipt.get("blocks") or ()
            if str(block.get("ticker") or "").upper() == ticker
        ]
    return list(blocks)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("financial_receipt", type=Path)
    parser.add_argument("--narrative-receipt", required=True, type=Path)
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--key-file", type=Path, default=DEFAULT_KEY_FILE)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()

    ticker = args.ticker.upper()
    financial_bytes = args.financial_receipt.read_bytes()
    financial = json.loads(financial_bytes)
    narrative = json.loads(args.narrative_receipt.read_bytes())
    _verify_receipt(financial, kind="financial")
    verified_narrative_id = _verify_receipt(narrative, kind="narrative")
    adapter = company_adapter(ticker)
    identity = {
        "ticker": adapter.ticker,
        "name": adapter.name,
        "exchange": adapter.exchange,
        "industry": adapter.industry,
    }
    sources = {
        "financial_receipt_sha256": hashlib.sha256(financial_bytes).hexdigest(),
        "narrative_receipt_id": verified_narrative_id,
    }
    dossier_id = "e4-model-judgments:" + hashlib.sha256(
        json.dumps(
            {"ticker": ticker, "sources": sources},
            ensure_ascii=False,
            sort_keys=True,
        ).encode()
    ).hexdigest()
    generated = generate_model_judgments(
        ticker=ticker,
        issuer_identity=identity,
        page_facts=_financial_facts(financial, ticker),
        narrative_blocks=_narrative_blocks(narrative, ticker),
        source_receipts=sources,
        dossier_id=dossier_id,
        key_file=args.key_file,
        model=args.model,
    )
    output = {
        "schema_version": "e4-model-judgments-v1",
        "data_kind": "real",
        "ticker": ticker,
        "issuer_identity": identity,
        "source_financial_receipt_sha256": sources["financial_receipt_sha256"],
        "source_narrative_receipt": sources["narrative_receipt_id"],
        "source_dossier_receipt": dossier_id,
        **generated,
    }
    output["receipt_hash"] = hashlib.sha256(
        json.dumps(output, sort_keys=True).encode()
    ).hexdigest()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "out": str(args.out),
                "receipt_id": output["schema_version"] + ":" + output["receipt_hash"],
                "model": (
                    output["model_receipts"][-1]["model"]
                    if output["model_receipts"]
                    else None
                ),
                "validation": output["validation"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
