#!/usr/bin/env python3
"""Reassess retained real E4 evidence under the Round 7 section contract.

The legacy receipt stores admitted page facts but only hashes for several old
section inputs. This migration carries forward only values that can be rebuilt
from committed, receipt-valid sources. Hash-only old inputs become typed gaps.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product"))

from data_core.e4_judgment_wiring import wire_unreviewed_judgment_receipt  # noqa: E402
from data_core.e4_l1_m4_governance_events import validate_receipt as validate_governance_receipt  # noqa: E402
from data_core.e4_page_level_filing_facts import FilingNumericFact  # noqa: E402
from data_core.e4_vertical_degradation import compile_vertical_degradation  # noqa: E402


LEGACY_WIRING_FILE_SHA256 = (
    "db27e157a0a2e3d50c43846940dfd81beea589c7869cbac16084f40e2c2bbca9"
)
OFFICIAL_FILING_HOSTS = frozenset(
    {
        "static.cninfo.com.cn",
        "www.sse.com.cn",
        "static.sse.com.cn",
        "www.szse.cn",
        "disc.static.szse.cn",
        "www.bse.cn",
    }
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode()
    ).hexdigest()


def _legacy_receipt_hash(value: dict[str, Any]) -> str:
    payload = {key: item for key, item in value.items() if key != "receipt_hash"}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()
    ).hexdigest()


def _fact(value: dict[str, Any]) -> FilingNumericFact:
    source_url = str(value["source_url"])
    if (
        not str(value.get("document_id", "")).startswith("official-filing:")
        or urlparse(source_url).scheme != "https"
        or urlparse(source_url).hostname not in OFFICIAL_FILING_HOSTS
    ):
        raise ValueError("migration page fact is not official filing evidence")
    return FilingNumericFact(
        ticker=str(value["ticker"]),
        metric=str(value["metric"]),
        value=float(value["value"]),
        document_id=str(value["document_id"]),
        raw_hash=str(value["raw_hash"]),
        page_number=int(value["page_number"]),
        quoted_label=str(value["quoted_label"]),
        quoted_anchor=str(value["quoted_anchor"]),
        report_period=str(value["report_period"]),
        statement_scope=str(value["statement_scope"]),
        unit=str(value["unit"]),
        currency=str(value["currency"]),
        source_url=source_url,
    )


def migrate(
    legacy: dict[str, Any],
    *,
    legacy_file_sha256: str,
    judgments: dict[str, dict[str, Any]],
    governance: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if legacy.get("schema_version") != "e4-m2-research-wiring-v1":
        raise ValueError("legacy wiring schema mismatch")
    if legacy_file_sha256 != LEGACY_WIRING_FILE_SHA256:
        raise ValueError("legacy wiring file identity mismatch")
    if legacy.get("receipt_hash") != _legacy_receipt_hash(legacy):
        raise ValueError("legacy wiring receipt hash mismatch")
    rows = []
    for row in legacy.get("rows", []):
        if row.get("status") != "available":
            continue
        ticker = str(row["ticker"]).upper()
        facts = tuple(_fact(item) for item in row["result"]["page_facts"])
        additional: dict[str, dict[str, object]] = {}
        carried = {
            "financial_page_facts": {
                "count": len(facts),
                "legacy_input_receipt": row.get("input_receipts", {}).get(
                    "financial_sequences_sha256"
                ),
            }
        }
        judgment = judgments.get(ticker)
        if judgment is not None:
            for section_id, values in wire_unreviewed_judgment_receipt(
                judgment,
                ticker=ticker,
            ).items():
                additional.setdefault(section_id, {}).update(values)
            carried["legacy_judgment_materials"] = {
                "receipt_id": f"{judgment['schema_version']}:{judgment['receipt_hash']}"
            }
        governance_receipt = governance.get(ticker)
        if governance_receipt is not None:
            validate_governance_receipt(governance_receipt, ticker=ticker)
            inputs = governance_receipt["inputs"]
            founder: dict[str, object] = {}
            management = inputs.get("management_record") or {}
            events = inputs.get("governance_events") or {}
            if management.get("status") == "available":
                founder["management_evidence"] = [
                    {
                        "records": management["records"],
                        "source_receipt": governance_receipt["receipt_id"],
                    }
                ]
            if events.get("status") == "available":
                founder["governance_evidence"] = events["records"]
            if founder:
                additional["founder_and_team"] = founder
                carried["governance"] = {
                    "receipt_id": governance_receipt["receipt_id"]
                }
        result = compile_vertical_degradation(
            ticker,
            facts,
            known_at="2026-07-30T00:00:00Z",
            additional_section_inputs=additional,
        )
        rows.append(
            {
                "ticker": ticker,
                "status": "available",
                "result": result,
                "migration_lineage": {
                    "carried_forward": carried,
                    "not_carried_forward": [
                        {
                            "input_family": "market_and_decision",
                            "reason": "legacy receipt retained assessment hashes, not the source object",
                        },
                        {
                            "input_family": "r2_industry",
                            "reason": "legacy receipt retained assessment hashes, not the accepted R2 source object",
                        },
                        {
                            "input_family": "legacy_section_status",
                            "reason": "18-section status is invalid under the replacement contract",
                        },
                    ],
                },
            }
        )
    output: dict[str, Any] = {
        "schema_version": "round7-m2-wiring-migration-v1",
        "data_kind": "real",
        "supersedes_schema_version": legacy["schema_version"],
        "legacy_file_sha256": legacy_file_sha256,
        "legacy_receipt_hash": legacy.get("receipt_hash"),
        "rows": rows,
        "truth_boundary": {
            "old_section_statuses_carried_forward": False,
            "hash_only_inputs_treated_as_missing": True,
            "unreviewed_field_judgments_complete_chapters": False,
        },
    }
    output["receipt_hash"] = _canonical_hash(output)
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("legacy_wiring", type=Path)
    parser.add_argument("--judgment", action="append", default=[], type=Path)
    parser.add_argument("--governance", action="append", default=[], type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    legacy = json.loads(args.legacy_wiring.read_text(encoding="utf-8"))
    judgment_values = [
        json.loads(path.read_text(encoding="utf-8")) for path in args.judgment
    ]
    governance_values = [
        json.loads(path.read_text(encoding="utf-8")) for path in args.governance
    ]
    judgments = {
        str(value.get("ticker", "")).upper(): value for value in judgment_values
    }
    governance = {
        str(value.get("ticker", "")).upper(): value for value in governance_values
    }
    if len(judgments) != len(judgment_values) or len(governance) != len(
        governance_values
    ):
        raise ValueError("duplicate or missing migration receipt ticker")
    output = migrate(
        legacy,
        legacy_file_sha256=_sha(args.legacy_wiring),
        judgments=judgments,
        governance=governance,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
