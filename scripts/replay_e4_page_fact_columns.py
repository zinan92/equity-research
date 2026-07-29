#!/usr/bin/env python3
"""Re-evaluate stored page facts against their official PDF table context.

The stored batch is immutable evidence of an earlier extraction pass.  This
tool never manufactures a replacement value: it only attaches a fresh table
column identity when the current official-PDF extractor emits the same metric
and numeric value from the same filing.  Anything not reproducible remains
explicitly unresolved, with its original page-bound text retained as the
diagnostic excerpt.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path

PRODUCT = Path(__file__).resolve().parents[1] / "product"
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from data_core.e4_catl_financial_history import OfficialReport
from data_core.e4_financial_sequence_batch import _ParseTimeout, _extract_bounded
from data_core.official_filings import default_http_transport


def _document_suffix(value: object) -> str:
    return str(value or "").rsplit(":", 1)[-1]


def _same_number(left: object, right: object) -> bool:
    try:
        return abs(float(left) - float(right)) <= max(1e-6, abs(float(right)) * 1e-9)
    except (TypeError, ValueError):
        return False


def _replay_report(ticker: str, report: dict[str, object]) -> tuple[list[dict[str, object]], dict[str, object]]:
    facts = [dict(item) for item in report.get("facts", []) if isinstance(item, dict)]
    if not facts:
        return facts, {"status": "no_stored_facts"}
    exemplar = facts[0]
    source_url = str(exemplar.get("source_url") or "")
    document_id = _document_suffix(exemplar.get("document_id"))
    response = default_http_transport(source_url, {"Accept": "application/pdf"})
    if response.status_code != 200 or not response.body.startswith(b"%PDF"):
        excerpt = f"official replay HTTP {response.status_code}; bytes={len(response.body)}"
        for fact in facts:
            fact["column_identity"] = "unknown"
            fact["report_period"] = "unresolved"
            fact["validation_status"] = "replay_source_unavailable"
            fact["replay_raw_text_excerpt"] = excerpt
        return facts, {"status": "source_unavailable", "raw_text_excerpt": excerpt}
    official_report = OfficialReport(str(report.get("period")), document_id, source_url, ticker=ticker)
    try:
        # A single pathological official PDF must not make the replay claim
        # success by silently skipping the rest of the cohort.
        fresh = _extract_bounded(official_report, response.body)
    except _ParseTimeout:
        excerpt = "official PDF parse exceeded 20s bounded replay limit"
        for fact in facts:
            fact["column_identity"] = "unknown"
            fact["report_period"] = "unresolved"
            fact["validation_status"] = "replay_parse_timeout"
            fact["replay_raw_text_excerpt"] = excerpt
        return facts, {"status": "parse_timeout", "raw_text_excerpt": excerpt}
    except Exception as exc:
        excerpt = f"official PDF replay extractor failed: {type(exc).__name__}: {exc}"[:520]
        for fact in facts:
            fact["column_identity"] = "unknown"
            fact["report_period"] = "unresolved"
            fact["validation_status"] = "replay_parse_error"
            fact["replay_raw_text_excerpt"] = excerpt
        return facts, {"status": "parse_error", "raw_text_excerpt": excerpt}
    by_metric: dict[str, list[object]] = defaultdict(list)
    for item in fresh:
        by_metric[item.metric].append(item)
    matched = 0
    for fact in facts:
        candidates = [item for item in by_metric.get(str(fact.get("metric")), ()) if _same_number(fact.get("value"), item.value)]
        # A value may repeat in a statement; page identity disambiguates it.
        page = fact.get("page_number")
        page_matches = [item for item in candidates if item.page_number == page]
        selected = page_matches[0] if len(page_matches) == 1 else (candidates[0] if len(candidates) == 1 else None)
        if selected is None:
            fact["column_identity"] = "unknown"
            fact["report_period"] = "unresolved"
            fact["validation_status"] = "replay_unresolved_no_matching_page_fact"
            fact["replay_raw_text_excerpt"] = str(fact.get("quoted_anchor") or "")[:520]
            continue
        matched += 1
        fact.update({
            "column_identity": selected.column_identity,
            "column_header_excerpt": selected.column_header_excerpt,
            "unit_source_excerpt": selected.unit_source_excerpt,
            "report_period": selected.report_period,
            "validation_status": selected.validation_status,
            "replay_raw_text_excerpt": selected.quoted_anchor[:520],
        })
    return facts, {"status": "replayed", "matched": matched, "stored": len(facts), "fresh_fact_count": len(fresh)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    payload = json.loads(args.receipt.read_text(encoding="utf-8"))
    diagnostics = []
    reasons: Counter[str] = Counter()
    periods: Counter[str] = Counter()
    total = 0
    for ticker in payload.get("tickers", []):
        for report in ticker.get("reports", []):
            replayed, diagnostic = _replay_report(str(ticker.get("ticker")), report)
            report["facts"] = replayed
            diagnostic.update({"ticker": ticker.get("ticker"), "period": report.get("period")})
            diagnostics.append(diagnostic)
            for fact in replayed:
                total += 1
                periods[str(fact.get("report_period"))] += 1
                if fact.get("column_identity") == "unknown":
                    reasons[str(fact.get("validation_status"))] += 1
    payload["column_context_replay"] = {
        "schema_version": "e4-column-context-replay-v1",
        "facts_examined": total,
        "unresolved_count": sum(reasons.values()),
        "unresolved_reason_counts": dict(reasons),
        "report_period_distribution": dict(sorted(periods.items())),
        "reports": diagnostics,
        "truth_boundary": "only current official-PDF values matching the stored page fact receive a refreshed column identity",
    }
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["column_context_replay"], ensure_ascii=False))


if __name__ == "__main__":
    main()
