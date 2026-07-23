#!/usr/bin/env python3
"""Validate historical closes against a local, non-committed benchmark.

The benchmark can be an extracted subset of the Ainiu archive, but is never a
runtime dependency and is never copied into this repository.  The command
creates a JSON and Markdown diff report at an explicitly supplied local path.
Historical valuation fields remain gaps unless the caller supplies an archival
source with the same as-of date and valuation definition.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PRODUCT = ROOT / "product"
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from data_core import FetchRequest, RecordDomain, YahooChartAdapter, validate_fetched_payload  # noqa: E402


MARKET_ALIASES = {"美股": "US", "日本": "JP", "港股": "HK", "US": "US", "JP": "JP", "HK": "HK"}


def _ticker(record: dict[str, Any]) -> str | None:
    code = str(record.get("code") or "").strip().upper()
    market = MARKET_ALIASES.get(str(record.get("market") or "").strip())
    if not code or market is None:
        return None
    if market == "US":
        return code
    if market == "JP":
        return code if code.endswith(".T") else f"{code}.T"
    return code if code.endswith(".HK") else f"{code.zfill(5)}.HK"


def _load_records(path: Path, limit: int, offset: int = 0) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    records = payload.get("records") if isinstance(payload, dict) else None
    if not isinstance(records, list):
        raise ValueError("benchmark needs an object with records")
    selected = []
    seen: set[str] = set()
    for item in records:
        if not isinstance(item, dict) or not isinstance(item.get("price"), (int, float)):
            continue
        symbol = _ticker(item)
        if symbol is None or symbol in seen:
            continue
        seen.add(symbol)
        selected.append({"ticker": symbol, "market": MARKET_ALIASES[str(item.get("market"))], "expected": {field: item.get(field) for field in ("price", "mcap", "mcap_usd", "pe", "pb", "peg")}})
    selected = selected[offset:offset + limit]
    if len(selected) < limit:
        raise ValueError(f"benchmark exposes only {len(selected)} supported records after offset={offset}, need {limit}")
    return selected


async def _historical_closes(symbol: str, start_date: str, end_date: str) -> dict[str, float]:
    start = datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(end_date).replace(tzinfo=timezone.utc)
    request = FetchRequest.create(
        request_id=f"n1-3-price-{symbol}-{start_date}-to-{end_date}", domain=RecordDomain.MARKET,
        entity_key=symbol,
        parameters={"period1": int((start - timedelta(days=4)).timestamp()), "period2": int((end + timedelta(days=5)).timestamp())},
    )
    adapter = YahooChartAdapter()
    fetched = await adapter.fetch(request)
    validated = validate_fetched_payload(adapter, request, fetched)
    return {
        str(record.payload["trade_date"]): float(record.payload["value"])
        for record in validated.records
        if start_date <= str(record.payload.get("trade_date")) <= end_date
    }


def _compare_price(expected: float, candidates: dict[str, float]) -> dict[str, Any]:
    if not candidates:
        return {"status": "missing", "expected": expected, "observed": None}
    trade_date, observed = min(candidates.items(), key=lambda item: abs(item[1] - expected))
    error = abs(observed - expected) / max(abs(expected), 1e-12)
    return {"status": "pass" if error <= 0.005 else "outlier", "expected": expected, "observed": observed, "matched_trade_date": trade_date, "relative_error": error, "tolerance": 0.005}


async def validate(benchmark: Path, window_start: str, window_end: str, limit: int, offset: int = 0) -> dict[str, Any]:
    rows = _load_records(benchmark, limit, offset)
    results = []
    for row in rows:
        observed: dict[str, float] = {}
        error = None
        try:
            observed = await _historical_closes(row["ticker"], window_start, window_end)
        except Exception as exc:  # keep a full diff report even if a source rejects a symbol
            error = str(exc)
        price = _compare_price(float(row["expected"]["price"]), observed)
        valuations = {field: {"status": "missing_historical_source"} for field in ("mcap", "mcap_usd", "pe", "pb", "peg") if row["expected"].get(field) is not None}
        results.append({"ticker": row["ticker"], "market": row["market"], "price": price, "valuation": valuations, "source_error": error})
        await asyncio.sleep(0.25)
    price_rows = [item["price"] for item in results]
    return {
        "schema_version": "market-snapshot-validation-v1",
        "window_start": window_start,
        "window_end": window_end,
        "companies_checked": len(results),
        "selection_offset": offset,
        "price_tolerance": 0.005,
        "price_pass_count": sum(item["status"] == "pass" for item in price_rows),
        "price_outlier_count": sum(item["status"] == "outlier" for item in price_rows),
        "price_missing_count": sum(item["status"] == "missing" for item in price_rows),
        "historical_valuation_policy": "not inferred from daily bars; missing source is an explicit gap",
        "companies": results,
    }


def _markdown(report: dict[str, Any]) -> str:
    lines = ["# N1-3 市场快照差异报告", "", f"- trading-day window: {report['window_start']} to {report['window_end']}", f"- companies: {report['companies_checked']}", f"- price pass/outlier/missing: {report['price_pass_count']}/{report['price_outlier_count']}/{report['price_missing_count']}", "- historical valuation: all missing unless a same-date archival valuation source is supplied; daily bars are not a substitute.", "", "| ticker | market | matched date | price status | relative error | valuation status |", "| --- | --- | --- | --- | --- |"]
    for company in report["companies"]:
        price = company["price"]
        valuations = sorted({value["status"] for value in company["valuation"].values()}) or ["not benchmarked"]
        error = "" if "relative_error" not in price else f"{price['relative_error']:.2%}"
        lines.append(f"| {company['ticker']} | {company['market']} | {price.get('matched_trade_date', '')} | {price['status']} | {error} | {', '.join(valuations)} |")
    return "\n".join(lines) + "\n"


def combine_reports(paths: list[Path]) -> dict[str, Any]:
    """Combine independently collected polite batches into one 30-company diff."""
    if not paths:
        raise ValueError("at least one batch report is required")
    batches = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    first = batches[0]
    window = (first.get("window_start"), first.get("window_end"))
    if not all((item.get("window_start"), item.get("window_end")) == window for item in batches):
        raise ValueError("all batches must use the same validation window")
    companies = [company for batch in batches for company in batch.get("companies", [])]
    tickers = [str(item.get("ticker")) for item in companies]
    if len(tickers) != len(set(tickers)):
        raise ValueError("batch reports contain duplicate tickers")
    price_rows = [item["price"] for item in companies]
    return {
        "schema_version": "market-snapshot-validation-v1",
        "window_start": window[0],
        "window_end": window[1],
        "companies_checked": len(companies),
        "batch_count": len(batches),
        "price_tolerance": first.get("price_tolerance", 0.005),
        "price_pass_count": sum(item["status"] == "pass" for item in price_rows),
        "price_outlier_count": sum(item["status"] == "outlier" for item in price_rows),
        "price_missing_count": sum(item["status"] == "missing" for item in price_rows),
        "historical_valuation_policy": first["historical_valuation_policy"],
        "companies": companies,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark", type=Path)
    parser.add_argument("--window-start", default="2026-06-30", help="YYYY-MM-DD")
    parser.add_argument("--window-end", default="2026-07-02", help="YYYY-MM-DD")
    parser.add_argument("--out", required=True, type=Path, help="JSON output; Markdown is written beside it")
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--offset", type=int, default=0, help="supported-record offset; permits polite validation batches")
    parser.add_argument("--combine", nargs="+", type=Path, help="existing batch JSON reports to merge without making requests")
    args = parser.parse_args()
    if args.combine:
        if args.benchmark:
            raise ValueError("--combine and --benchmark are mutually exclusive")
        report = combine_reports(args.combine)
    else:
        if not args.benchmark:
            raise ValueError("--benchmark is required unless --combine is used")
        if datetime.fromisoformat(args.window_start) > datetime.fromisoformat(args.window_end):
            raise ValueError("window-start must be no later than window-end")
        if args.offset < 0:
            raise ValueError("offset must be non-negative")
        report = asyncio.run(validate(args.benchmark, args.window_start, args.window_end, args.limit, args.offset))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.out.with_suffix(".md").write_text(_markdown(report), encoding="utf-8")
    print(args.out)
    return 0 if report["price_outlier_count"] == 0 and report["price_missing_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
