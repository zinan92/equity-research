"""Runtime-only market and PIT-fundamental companion batch for E4 models."""
from __future__ import annotations

import hashlib
import json
import multiprocessing
import queue
import time
from pathlib import Path
from typing import Any, Callable, Mapping

from .ashare import AShareDataPacket, collect_ashare_packet
from .contracts import digest
from .e4_official_evidence_batch import load_real_identity_tickers


E4_MARKET_FUNDAMENTALS_BATCH_SCHEMA_VERSION = "e4-s4-market-fundamentals-batch-v1"
E4_MARKET_FUNDAMENTALS_CHECKPOINT_SCHEMA_VERSION = "e4-s4-market-fundamentals-checkpoint-v1"
Collector = Callable[[str], AShareDataPacket]

_QUOTE_FACTS = (
    "last_price", "change_pct", "high", "low", "pe_ttm",
    "circulating_market_cap", "market_cap", "pb", "observed_at",
)
_BAR_FACTS = ("trade_date", "adjustment", "open", "close", "high", "low", "volume")
_FUNDAMENTAL_FACTS = (
    "report_period", "announced_at", "report_type", "revenue",
    "net_profit_parent", "total_assets", "total_liabilities", "total_equity",
    "total_operating_income", "net_profit_parent_statement", "net_cash_operating",
)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _run_config(
    identity_receipt_path: Path, official_receipt_path: Path, *, max_tickers: int,
    inter_ticker_delay_seconds: float, collector_timeout_seconds: float, max_component_attempts: int,
) -> dict[str, Any]:
    return {
        "identity_receipt_sha256": hashlib.sha256(identity_receipt_path.read_bytes()).hexdigest(),
        "official_receipt_sha256": hashlib.sha256(official_receipt_path.read_bytes()).hexdigest(),
        "max_tickers": max_tickers,
        "inter_ticker_delay_seconds": inter_ticker_delay_seconds,
        "collector_timeout_seconds": collector_timeout_seconds,
        "max_component_attempts": max_component_attempts,
    }


def _write_checkpoint(runtime_root: Path, *, config: Mapping[str, Any], rows: list[dict[str, Any]]) -> None:
    payload = {
        "schema_version": E4_MARKET_FUNDAMENTALS_CHECKPOINT_SCHEMA_VERSION,
        "state": "in_progress", "data_kind": "real", "config": dict(config), "tickers": rows,
        "truth_boundary": {"market_fundamentals_are_inputs_not_tier": True, "counts_as_tier_a_or_b": False, "counts_as_position_or_target": False},
    }
    _write_json(runtime_root / "market-fundamentals-batch-checkpoint.json", payload)
    _write_json(runtime_root / "market-fundamentals-batch-latest.json", {"state": "in_progress", "receipt": "market-fundamentals-batch-checkpoint.json"})


def _validate_official_receipt(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    boundary = payload.get("truth_boundary") or {}
    if payload.get("schema_version") != "e4-s4-official-evidence-batch-v1" or payload.get("data_kind") != "real":
        raise ValueError("market batch requires a real E4 official-evidence receipt")
    if boundary.get("counts_as_report_model_coverage") is not False:
        raise ValueError("official-evidence receipt truth boundary is invalid")
    return payload


def _selected_facts(value: object, fields: tuple[str, ...]) -> dict[str, Any]:
    """Copy only the documented display fields from a packet component.

    Values are intentionally copied from the already validated packet summary,
    rather than recalculated here.  The row's component receipts remain the
    identity anchor for every fact in this small runtime-only projection.
    """
    if not isinstance(value, Mapping):
        return {}
    return {field: value[field] for field in fields if value.get(field) is not None}


def _display_facts(
    summary: Mapping[str, Any], *, market_available: bool, fundamentals_available: bool,
) -> tuple[dict[str, Any], list[str]]:
    """Make a bounded, non-interpretive projection suitable for display.

    A fact is emitted only when its whole source component has already passed
    the packet's real/publishable checks.  This prevents a partial response
    from looking complete merely because one field happened to parse.
    """
    facts: dict[str, Any] = {}
    blockers: list[str] = []
    if market_available:
        quote = _selected_facts(summary.get("quote"), _QUOTE_FACTS)
        bars = summary.get("daily_bars")
        latest_bar = _selected_facts(bars[-1], _BAR_FACTS) if isinstance(bars, list) and bars else {}
        if quote and latest_bar:
            facts["market"] = {
                "quote": quote,
                "latest_daily_bar": latest_bar,
                "source_components": ["quote", "daily_bars"],
            }
        else:
            blockers.append("market_display_facts_missing_validated_values")
    else:
        blockers.append("market_display_facts_unavailable")
    if fundamentals_available:
        periods = summary.get("fundamentals")
        latest = _selected_facts(periods[0], _FUNDAMENTAL_FACTS) if isinstance(periods, list) and periods else {}
        if latest.get("report_period") and latest.get("announced_at"):
            facts["fundamentals"] = {
                "latest_period": latest,
                "source_components": ["fundamentals", "balance_sheet", "income_statement", "cash_flow"],
            }
        else:
            blockers.append("fundamentals_display_facts_missing_validated_values")
    else:
        blockers.append("fundamentals_display_facts_unavailable")
    return facts, blockers


def _packet_row(ticker: str, summary: Mapping[str, Any]) -> dict[str, Any]:
    if str((summary.get("instrument") or {}).get("ticker") or "").upper() != ticker.upper():
        raise ValueError("market packet identity does not match requested ticker")
    sources = summary.get("sources") or {}
    required = ("quote", "daily_bars", "fundamentals", "balance_sheet", "income_statement", "cash_flow")
    gaps = {str(gap.get("domain") or ""): str(gap.get("reason") or "source_not_publishable") for gap in summary.get("data_gaps") or [] if isinstance(gap, Mapping)}
    component_blockers: dict[str, list[str]] = {}
    for key in required:
        source = sources.get(key) or {}
        reasons: list[str] = []
        if source.get("data_kind") != "real":
            reasons.append("non_real_source_data")
        if not source.get("publishable"):
            reasons.append(gaps.get(key, "source_not_publishable"))
        if reasons:
            component_blockers[key] = sorted(set(reasons))
    blockers = [f"{key}: {reason}" for key, reasons in component_blockers.items() for reason in reasons]
    market_available = not any(key in component_blockers for key in ("quote", "daily_bars"))
    fundamentals_available = not any(key in component_blockers for key in required[2:])
    latest_fundamental = next(iter(summary.get("fundamentals") or ()), {})
    display_facts, display_fact_blockers = _display_facts(
        summary, market_available=market_available, fundamentals_available=fundamentals_available,
    )
    return {
        "ticker": ticker.upper(), "status": "captured" if market_available and fundamentals_available else "partial" if market_available or fundamentals_available else "failed",
        "data_kind": "real", "market_available": market_available,
        "fundamentals_available": fundamentals_available,
        "display_facts": display_facts,
        "display_fact_blockers": display_fact_blockers,
        "component_blockers": component_blockers,
        "blockers": blockers,
        "latest_financial_period": latest_fundamental.get("report_period") if isinstance(latest_fundamental, Mapping) else None,
        "latest_financial_announced_at": latest_fundamental.get("announced_at") if isinstance(latest_fundamental, Mapping) else None,
        "source_receipts": {key: {
            "source_key": (sources.get(key) or {}).get("selected_source"),
            "raw_hash": (sources.get(key) or {}).get("raw_hash"),
            "manifest_hash": (sources.get(key) or {}).get("manifest_hash"),
            "known_at": (sources.get(key) or {}).get("known_at"),
            "publishable": (sources.get(key) or {}).get("publishable"),
        } for key in required},
    }


def _collector_worker(ticker: str, result_queue: Any) -> None:
    try:
        result_queue.put({"status": "ok", "summary": collect_ashare_packet(ticker, bar_limit=30, fundamental_periods=4).to_summary()})
    except Exception as exc:
        result_queue.put({"status": "error", "error": type(exc).__name__, "message": str(exc)[:240]})


def _collect_isolated(
    ticker: str,
    timeout_seconds: float,
    worker: Callable[[str, Any], None],
    *,
    summary_row: Callable[[str, Mapping[str, Any]], dict[str, Any]] = _packet_row,
) -> dict[str, Any]:
    context = multiprocessing.get_context("spawn")
    result_queue = context.Queue(maxsize=1)
    process = context.Process(target=worker, args=(ticker, result_queue))
    process.start(); process.join(timeout_seconds)
    if process.is_alive():
        process.terminate(); process.join(5)
        return {"ticker": ticker.upper(), "status": "failed", "data_kind": "real", "market_available": False, "fundamentals_available": False, "blockers": ["collector_timeout"]}
    try:
        result = result_queue.get_nowait()
    except queue.Empty:
        return {"ticker": ticker.upper(), "status": "failed", "data_kind": "real", "market_available": False, "fundamentals_available": False, "blockers": ["collector_worker_no_receipt"]}
    if result.get("status") != "ok":
        return {"ticker": ticker.upper(), "status": "failed", "data_kind": "real", "market_available": False, "fundamentals_available": False, "blockers": ["collector_exception"], "error": result.get("error"), "message": result.get("message")}
    try:
        return summary_row(ticker, result["summary"])
    except ValueError as exc:
        return {"ticker": ticker.upper(), "status": "failed", "data_kind": "real", "market_available": False, "fundamentals_available": False, "blockers": ["packet_validation_failed"], "error": type(exc).__name__, "message": str(exc)[:240]}


def _collect_with_component_retries(
    ticker: str, timeout_seconds: float, worker: Callable[[str, Any], None], *, max_attempts: int,
    collect_once: Callable[[str, float, Callable[[str, Any], None]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Retry only the unchanged worker/source plan and retain every attempt's gap."""
    if not 1 <= max_attempts <= 3:
        raise ValueError("max component attempts must be 1-3")
    collect_once = collect_once or (lambda symbol, timeout, runner: _collect_isolated(symbol, timeout, runner))
    history: list[dict[str, Any]] = []
    last: dict[str, Any] | None = None
    for attempt in range(1, max_attempts + 1):
        current = collect_once(ticker, timeout_seconds, worker)
        history.append({
            "attempt": attempt, "status": current.get("status"),
            "component_blockers": current.get("component_blockers") or {},
            "blockers": list(current.get("blockers") or ()),
        })
        last = current
        if current.get("status") == "captured":
            break
    if last is None:
        raise RuntimeError("component retry collector produced no result")
    return {**last, "collection_attempts": len(history), "attempt_history": history}


def run_market_fundamentals_batch(
    identity_receipt_path: Path, official_receipt_path: Path, runtime_root: Path, *,
    max_tickers: int = 100, inter_ticker_delay_seconds: float = 1.0,
    collector_timeout_seconds: float = 30.0, max_component_attempts: int = 2,
    worker: Callable[[str, Any], None] = _collector_worker,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    if not isinstance(max_tickers, int) or not 1 <= max_tickers <= 100:
        raise ValueError("max_tickers must be 1-100")
    if collector_timeout_seconds <= 0 or inter_ticker_delay_seconds < 0 or not 1 <= max_component_attempts <= 3:
        raise ValueError("batch timeout and delay must be valid")
    _validate_official_receipt(official_receipt_path)
    tickers = load_real_identity_tickers(identity_receipt_path)[:max_tickers]
    runtime_root.mkdir(parents=True, exist_ok=True)
    config = _run_config(identity_receipt_path, official_receipt_path, max_tickers=max_tickers, inter_ticker_delay_seconds=inter_ticker_delay_seconds, collector_timeout_seconds=collector_timeout_seconds, max_component_attempts=max_component_attempts)
    latest_path = runtime_root / "market-fundamentals-batch-latest.json"
    previous: dict[str, Mapping[str, Any]] = {}
    resuming_checkpoint = False
    if latest_path.exists():
        pointer = json.loads(latest_path.read_text(encoding="utf-8"))
        previous_path = runtime_root / str(pointer.get("receipt") or "")
        if previous_path.is_file():
            payload = json.loads(previous_path.read_text(encoding="utf-8"))
            if pointer.get("state") == "in_progress":
                if payload.get("schema_version") != E4_MARKET_FUNDAMENTALS_CHECKPOINT_SCHEMA_VERSION or payload.get("config") != config:
                    raise ValueError("market fundamentals checkpoint does not match this corpus configuration")
                previous = {str(row.get("ticker") or "").upper(): row for row in payload.get("tickers") or [] if row.get("status") in {"captured", "partial", "failed"}}
                resuming_checkpoint = True
            elif pointer.get("state") == "completed":
                if payload.get("config") != config:
                    raise ValueError("market fundamentals completed receipt does not match this corpus configuration")
                previous = {str(row.get("ticker") or "").upper(): row for row in payload.get("tickers") or []}
            else:
                raise ValueError("market fundamentals latest pointer has unknown state")
    rows: list[dict[str, Any]] = []
    for index, ticker in enumerate(tickers):
        prior = previous.get(ticker)
        if prior and resuming_checkpoint:
            rows.append(dict(prior))
            continue
        if prior:
            rows.append({"ticker": ticker, "status": "skipped", "data_kind": "real", "market_available": bool(prior.get("market_available")), "fundamentals_available": bool(prior.get("fundamentals_available")), "blockers": ["already_completed"]})
            continue
        rows.append(_collect_with_component_retries(ticker, collector_timeout_seconds, worker, max_attempts=max_component_attempts))
        _write_checkpoint(runtime_root, config=config, rows=rows)
        if index < len(tickers) - 1 and inter_ticker_delay_seconds:
            sleep(inter_ticker_delay_seconds)
    receipt = {
        "schema_version": E4_MARKET_FUNDAMENTALS_BATCH_SCHEMA_VERSION,
        "data_kind": "real", "identity_receipt_sha256": config["identity_receipt_sha256"],
        "official_receipt_sha256": config["official_receipt_sha256"], "config": config,
        "configured_max_concurrency": 1, "inter_ticker_delay_seconds": inter_ticker_delay_seconds,
        "collector_timeout_seconds": collector_timeout_seconds, "tickers": rows,
        "counts": {"requested": len(rows), "market_available": sum(bool(row["market_available"]) for row in rows), "fundamentals_available": sum(bool(row["fundamentals_available"]) for row in rows), "failed": sum(row["status"] == "failed" for row in rows)},
        "truth_boundary": {"market_fundamentals_are_inputs_not_tier": True, "counts_as_tier_a_or_b": False, "counts_as_position_or_target": False},
    }
    receipt["receipt_hash"] = digest(receipt)
    path = runtime_root / f"market-fundamentals-batch-{receipt['receipt_hash'][:16]}.json"
    _write_json(path, receipt)
    _write_json(latest_path, {"state": "completed", "receipt": path.name, "receipt_hash": receipt["receipt_hash"]})
    checkpoint_path = runtime_root / "market-fundamentals-batch-checkpoint.json"
    if checkpoint_path.exists():
        checkpoint_path.unlink()
    return {"path": str(path), "receipt": receipt}
