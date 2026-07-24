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
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
PRODUCT = ROOT / "product"
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from data_core import (  # noqa: E402
    FetchRequest,
    RecordDomain,
    SecCompanyFactsAdapter,
    YahooChartAdapter,
    YahooFxAdapter,
    derive_historical_valuation,
    sec_point_in_time_inputs,
    validate_fetched_payload,
)


MARKET_ALIASES = {"美股": "US", "日本": "JP", "港股": "HK", "US": "US", "JP": "JP", "HK": "HK"}
SEC_TICKER_INDEX_URL = "https://www.sec.gov/files/company_tickers.json"
VALUATION_TOLERANCES = {"mcap": 0.02, "mcap_usd": 0.02, "pe": 0.05, "pb": 0.05, "peg": 0.05}


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
        selected.append({"ticker": symbol, "market": MARKET_ALIASES[str(item.get("market"))], "expected": {field: item.get(field) for field in ("price", "chg", "mcap", "mcap_usd", "pe", "pb", "peg")}})
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
        parameters={"period1": int((start - timedelta(days=45)).timestamp()), "period2": int((end + timedelta(days=6)).timestamp())},
    )
    adapter = YahooChartAdapter()
    fetched = await adapter.fetch(request)
    validated = validate_fetched_payload(adapter, request, fetched)
    return {
        str(record.payload["trade_date"]): float(record.payload["value"])
        for record in validated.records
    }


def _compare_price(
    expected: float,
    candidates: dict[str, float],
    window_start: str,
    window_end: str,
) -> dict[str, Any]:
    in_window = {
        trade_date: value
        for trade_date, value in candidates.items()
        if window_start <= trade_date <= window_end
    }
    if not in_window:
        return {"status": "missing", "expected": expected, "observed": None}
    trade_date, observed = min(in_window.items(), key=lambda item: abs(item[1] - expected))
    error = abs(observed - expected) / max(abs(expected), 1e-12)
    if error <= 0.005:
        return {
            "status": "pass",
            "expected": expected,
            "observed": observed,
            "matched_trade_date": trade_date,
            "relative_error": error,
            "tolerance": 0.005,
        }
    residual_date, residual_value = min(
        candidates.items(), key=lambda item: abs(item[1] - expected)
    )
    residual_error = abs(residual_value - expected) / max(abs(expected), 1e-12)
    if not window_start <= residual_date <= window_end and residual_error <= 0.005:
        return {
            "status": "explained_residual",
            "reason": "benchmark_as_of_outside_declared_window",
            "expected": expected,
            "observed": residual_value,
            "matched_trade_date": residual_date,
            "relative_error": residual_error,
            "tolerance": 0.005,
            "declared_window_closest": {
                "trade_date": trade_date,
                "observed": observed,
                "relative_error": error,
            },
        }
    return {
        "status": "outlier",
        "reason": "benchmark_value_not_observed_in_source_search_window",
        "expected": expected,
        "observed": observed,
        "matched_trade_date": trade_date,
        "relative_error": error,
        "tolerance": 0.005,
    }


def _compare_change(
    expected: Any, candidates: dict[str, float], matched_trade_date: Any
) -> dict[str, Any]:
    if expected in (None, ""):
        return {"status": "not_benchmarked"}
    if not isinstance(matched_trade_date, str) or matched_trade_date not in candidates:
        return {"status": "missing", "expected": float(expected)}
    earlier = sorted(day for day in candidates if day < matched_trade_date)
    if not earlier:
        return {"status": "missing", "expected": float(expected)}
    previous_date = earlier[-1]
    previous = candidates[previous_date]
    if previous == 0:
        return {"status": "missing", "expected": float(expected)}
    observed = (candidates[matched_trade_date] / previous - 1.0) * 100.0
    error = abs(observed - float(expected))
    return {
        "status": "pass" if error <= 0.1 else "reference_mismatch",
        "reason": None
        if error <= 0.1
        else "benchmark_previous_close_basis_differs_from_source_daily_close",
        "expected": float(expected),
        "observed": observed,
        "absolute_error_pp": error,
        "tolerance_pp": 0.1,
        "previous_trade_date": previous_date,
    }


def _fetch_sec_ticker_index() -> tuple[dict[str, str], str]:
    request = Request(
        SEC_TICKER_INDEX_URL,
        headers={"User-Agent": "ParkEquityResearch/1.0 research-agent"},
    )
    with urlopen(request, timeout=30) as response:
        body = response.read()
    document = json.loads(body.decode("utf-8"))
    mapping = {
        str(item.get("ticker") or "").upper(): str(item.get("cik_str") or "")
        for item in document.values()
        if isinstance(item, dict) and item.get("ticker") and item.get("cik_str")
    }
    return mapping, hashlib.sha256(body).hexdigest()


async def _sec_inputs(
    symbol: str, cik: str, as_of: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    request = FetchRequest.create(
        request_id=f"n1-3-sec-{symbol}-{as_of}",
        domain=RecordDomain.FUNDAMENTAL,
        entity_key=symbol,
        parameters={"cik": cik, "as_of": as_of},
    )
    adapter = SecCompanyFactsAdapter()
    fetched = await adapter.fetch(request)
    validated = validate_fetched_payload(adapter, request, fetched)
    inputs = sec_point_in_time_inputs(
        json.loads(fetched.body.decode("utf-8")), as_of
    )
    return inputs, {
        "source_url": fetched.source_url,
        "raw_hash": validated.raw.raw_hash,
        "known_at": validated.raw.known_at,
    }


async def _frozen_fx(currency: str, trade_date: str) -> dict[str, Any]:
    if currency == "USD":
        return {
            "status": "identity",
            "trade_date": trade_date,
            "currency": currency,
            "usd_per_local_currency": 1.0,
        }
    target = datetime.fromisoformat(trade_date).replace(tzinfo=timezone.utc)
    request = FetchRequest.create(
        request_id=f"n1-3-fx-{currency}-{trade_date}",
        domain=RecordDomain.MARKET,
        entity_key=currency,
        parameters={
            "period1": int((target - timedelta(days=3)).timestamp()),
            "period2": int((target + timedelta(days=4)).timestamp()),
        },
    )
    adapter = YahooFxAdapter()
    fetched = await adapter.fetch(request)
    validated = validate_fetched_payload(adapter, request, fetched)
    by_date = {
        str(record.payload["trade_date"]): float(record.payload["value"])
        for record in validated.records
    }
    if trade_date not in by_date:
        return {
            "status": "missing_same_date",
            "trade_date": trade_date,
            "currency": currency,
            "source_url": fetched.source_url,
            "raw_hash": validated.raw.raw_hash,
        }
    return {
        "status": "frozen",
        "trade_date": trade_date,
        "currency": currency,
        "usd_per_local_currency": by_date[trade_date],
        "source_url": fetched.source_url,
        "raw_hash": validated.raw.raw_hash,
        "known_at": validated.raw.known_at,
    }


def _compare_valuations(
    expected: dict[str, Any], derived: dict[str, Any]
) -> dict[str, Any]:
    values = derived.get("values") or {}
    definitions = derived.get("definitions") or {}
    rows: dict[str, Any] = {}
    for field, tolerance in VALUATION_TOLERANCES.items():
        target = expected.get(field)
        if target in (None, ""):
            continue
        actual = values.get(field)
        if actual in (None, ""):
            rows[field] = {
                "status": "missing_historical_source",
                "tolerance": tolerance,
            }
            continue
        error = abs(float(actual) - float(target)) / max(abs(float(target)), 1e-12)
        if field == "peg":
            rows[field] = {
                "status": "definition_mismatch",
                "reason": "benchmark_growth_basis_is_undisclosed; SEC_TTM_growth_is_not_substituted",
                "expected": float(target),
                "observed": float(actual),
                "relative_error": error,
                "definition": definitions.get(field),
            }
            continue
        rows[field] = {
            "status": "pass" if error <= tolerance else "outlier",
            "reason": None
            if error <= tolerance
            else "source_definition_or_share_scope_mismatch",
            "expected": float(target),
            "observed": float(actual),
            "relative_error": error,
            "tolerance": tolerance,
            "definition": definitions.get(field),
        }
    return rows


async def validate(
    benchmark: Path,
    window_start: str,
    window_end: str,
    limit: int,
    offset: int = 0,
    *,
    with_sec: bool = False,
) -> dict[str, Any]:
    rows = _load_records(benchmark, limit, offset)
    sec_tickers: dict[str, str] = {}
    sec_ticker_index_hash: str | None = None
    if with_sec:
        sec_tickers, sec_ticker_index_hash = await asyncio.to_thread(
            _fetch_sec_ticker_index
        )
    fx_cache: dict[tuple[str, str], dict[str, Any]] = {}
    results = []
    for row in rows:
        observed: dict[str, float] = {}
        error = None
        try:
            observed = await _historical_closes(row["ticker"], window_start, window_end)
        except Exception as exc:  # keep a full diff report even if a source rejects a symbol
            error = str(exc)
        price = _compare_price(
            float(row["expected"]["price"]), observed, window_start, window_end
        )
        matched_date = price.get("matched_trade_date")
        change = _compare_change(row["expected"].get("chg"), observed, matched_date)
        valuation_details: dict[str, Any] = {
            "method": "missing_historical_source",
            "gaps": ["same-date PIT fundamentals"],
        }
        derived: dict[str, Any] = {"values": {}, "gaps": ["same-date PIT fundamentals"]}
        sec_receipt = None
        fx_receipt = None
        if isinstance(matched_date, str) and row["market"] == "US" and with_sec:
            ticker = row["ticker"]
            cik = (
                sec_tickers.get(ticker)
                or sec_tickers.get(ticker.replace(".", "-"))
                or sec_tickers.get(ticker.replace("-", "."))
            )
            if cik:
                try:
                    inputs, sec_receipt = await _sec_inputs(
                        row["ticker"], cik, matched_date
                    )
                    units = {
                        str(item.get("unit"))
                        for item in (
                            inputs.get("ttm_net_income"),
                            inputs.get("stockholders_equity"),
                        )
                        if isinstance(item, dict)
                    }
                    financial_currency = next(iter(units)) if len(units) == 1 else "USD"
                    fx_rate = 1.0
                    if financial_currency != "USD":
                        cache_key = (financial_currency, matched_date)
                        if cache_key not in fx_cache:
                            fx_cache[cache_key] = await _frozen_fx(
                                financial_currency, matched_date
                            )
                        fx_receipt = fx_cache[cache_key]
                        if fx_receipt.get("status") == "frozen":
                            fx_rate = float(fx_receipt["usd_per_local_currency"])
                        else:
                            inputs.setdefault("gaps", []).append(
                                "missing_same_date_financial_currency_fx"
                            )
                    derived = derive_historical_valuation(
                        float(observed[matched_date]),
                        inputs,
                        usd_per_financial_currency=fx_rate,
                    )
                    valuation_details = {
                        **derived,
                        "inputs": inputs,
                        "sec": sec_receipt,
                        "fx": fx_receipt,
                    }
                except Exception as exc:
                    valuation_details = {
                        "method": "sec_companyfacts_reconstruction_failed",
                        "gaps": [str(exc)],
                    }
            else:
                valuation_details = {
                    "method": "sec_ticker_unmapped",
                    "gaps": ["SEC CIK mapping"],
                }
        elif isinstance(matched_date, str) and row["market"] in {"HK", "JP"}:
            currency = "HKD" if row["market"] == "HK" else "JPY"
            cache_key = (currency, matched_date)
            try:
                if cache_key not in fx_cache:
                    fx_cache[cache_key] = await _frozen_fx(currency, matched_date)
                fx_receipt = fx_cache[cache_key]
            except Exception as exc:
                fx_receipt = {
                    "status": "source_error",
                    "currency": currency,
                    "trade_date": matched_date,
                    "error": str(exc),
                }
            valuation_details["fx"] = fx_receipt
        valuations = _compare_valuations(row["expected"], derived)
        results.append(
            {
                "ticker": row["ticker"],
                "market": row["market"],
                "price": price,
                "change": change,
                "valuation": valuations,
                "valuation_details": valuation_details,
                "source_error": error,
            }
        )
        await asyncio.sleep(0.25)
    price_rows = [item["price"] for item in results]
    change_rows = [
        item["change"]
        for item in results
        if item.get("change", {}).get("status") != "not_benchmarked"
    ]
    valuation_rows = [
        value for item in results for value in item.get("valuation", {}).values()
    ]
    return {
        "schema_version": "market-snapshot-validation-v2",
        "window_start": window_start,
        "window_end": window_end,
        "companies_checked": len(results),
        "selection_offset": offset,
        "price_tolerance": 0.005,
        "price_pass_count": sum(item["status"] == "pass" for item in price_rows),
        "price_explained_residual_count": sum(
            item["status"] == "explained_residual" for item in price_rows
        ),
        "price_outlier_count": sum(item["status"] == "outlier" for item in price_rows),
        "price_missing_count": sum(item["status"] == "missing" for item in price_rows),
        "change_pass_count": sum(item["status"] == "pass" for item in change_rows),
        "change_outlier_count": sum(item["status"] == "outlier" for item in change_rows),
        "change_reference_mismatch_count": sum(
            item["status"] == "reference_mismatch" for item in change_rows
        ),
        "change_missing_count": sum(item["status"] == "missing" for item in change_rows),
        "valuation_expected_count": len(valuation_rows),
        "valuation_pass_count": sum(item["status"] == "pass" for item in valuation_rows),
        "valuation_outlier_count": sum(
            item["status"] == "outlier" for item in valuation_rows
        ),
        "valuation_definition_mismatch_count": sum(
            item["status"] == "definition_mismatch" for item in valuation_rows
        ),
        "valuation_missing_count": sum(
            item["status"] == "missing_historical_source" for item in valuation_rows
        ),
        "sec_enabled": with_sec,
        "sec_ticker_index_url": SEC_TICKER_INDEX_URL if with_sec else None,
        "sec_ticker_index_raw_hash": sec_ticker_index_hash,
        "frozen_fx_count": sum(
            receipt.get("status") in {"frozen", "identity"}
            for receipt in fx_cache.values()
        ),
        "historical_valuation_policy": "not inferred from daily bars; missing source is an explicit gap",
        "companies": results,
    }


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# N1-3 市场快照差异报告",
        "",
        f"- trading-day window: {report['window_start']} to {report['window_end']}",
        f"- companies: {report['companies_checked']}",
        (
            "- price pass/explained residual/outlier/missing: "
            f"{report['price_pass_count']}/"
            f"{report.get('price_explained_residual_count', 0)}/"
            f"{report['price_outlier_count']}/{report['price_missing_count']}"
        ),
        (
            "- valuation pass/outlier/missing: "
            f"{report.get('valuation_pass_count', 0)}/"
            f"{report.get('valuation_outlier_count', 0)}/"
            f"{report.get('valuation_missing_count', 0)}; "
            f"definition mismatch: {report.get('valuation_definition_mismatch_count', 0)}"
        ),
        (
            "- change pass/outlier/missing: "
            f"{report.get('change_pass_count', 0)}/"
            f"{report.get('change_outlier_count', 0)}/"
            f"{report.get('change_missing_count', 0)}; "
            f"reference mismatch: {report.get('change_reference_mismatch_count', 0)}"
        ),
        "- historical valuation: SEC filed-before-as-of inputs may reconstruct US values; all other unavailable fields remain explicit gaps. Daily bars are never a substitute.",
        "",
        "| ticker | market | matched date | price status | change status | residual reason | relative error | valuation status |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for company in report["companies"]:
        price = company["price"]
        valuations = sorted({value["status"] for value in company["valuation"].values()}) or ["not benchmarked"]
        error = "" if "relative_error" not in price else f"{price['relative_error']:.2%}"
        lines.append(
            f"| {company['ticker']} | {company['market']} | "
            f"{price.get('matched_trade_date', '')} | {price['status']} | "
            f"{company.get('change', {}).get('status', '')} | "
            f"{price.get('reason', '')} | {error} | {', '.join(valuations)} |"
        )
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
    change_rows = [
        item["change"]
        for item in companies
        if item.get("change", {}).get("status") != "not_benchmarked"
    ]
    valuation_rows = [
        value for company in companies for value in company.get("valuation", {}).values()
    ]
    index_hashes = {
        item.get("sec_ticker_index_raw_hash")
        for item in batches
        if item.get("sec_ticker_index_raw_hash")
    }
    if len(index_hashes) > 1:
        raise ValueError("batch reports used different SEC ticker-index captures")
    return {
        "schema_version": "market-snapshot-validation-v2",
        "window_start": window[0],
        "window_end": window[1],
        "companies_checked": len(companies),
        "batch_count": len(batches),
        "price_tolerance": first.get("price_tolerance", 0.005),
        "price_pass_count": sum(item["status"] == "pass" for item in price_rows),
        "price_explained_residual_count": sum(
            item["status"] == "explained_residual" for item in price_rows
        ),
        "price_outlier_count": sum(item["status"] == "outlier" for item in price_rows),
        "price_missing_count": sum(item["status"] == "missing" for item in price_rows),
        "change_pass_count": sum(item["status"] == "pass" for item in change_rows),
        "change_outlier_count": sum(item["status"] == "outlier" for item in change_rows),
        "change_reference_mismatch_count": sum(
            item["status"] == "reference_mismatch" for item in change_rows
        ),
        "change_missing_count": sum(item["status"] == "missing" for item in change_rows),
        "valuation_expected_count": len(valuation_rows),
        "valuation_pass_count": sum(item["status"] == "pass" for item in valuation_rows),
        "valuation_outlier_count": sum(
            item["status"] == "outlier" for item in valuation_rows
        ),
        "valuation_definition_mismatch_count": sum(
            item["status"] == "definition_mismatch" for item in valuation_rows
        ),
        "valuation_missing_count": sum(
            item["status"] == "missing_historical_source" for item in valuation_rows
        ),
        "sec_enabled": any(bool(item.get("sec_enabled")) for item in batches),
        "sec_ticker_index_url": SEC_TICKER_INDEX_URL
        if any(bool(item.get("sec_enabled")) for item in batches)
        else None,
        "sec_ticker_index_raw_hash": next(iter(index_hashes), None),
        "frozen_fx_count": sum(int(item.get("frozen_fx_count") or 0) for item in batches),
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
    parser.add_argument(
        "--with-sec",
        action="store_true",
        help="reconstruct US historical valuations from filed-before-as-of SEC companyfacts",
    )
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
        report = asyncio.run(
            validate(
                args.benchmark,
                args.window_start,
                args.window_end,
                args.limit,
                args.offset,
                with_sec=args.with_sec,
            )
        )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.out.with_suffix(".md").write_text(_markdown(report), encoding="utf-8")
    print(args.out)
    return 0 if report["price_outlier_count"] == 0 and report["price_missing_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
