"""Local, receipt-backed performance and cost budgets for research tasks.

The measurements are intentionally local contract evidence, not a claim about
networked production latency or provider billing.
"""
from __future__ import annotations

import json
from pathlib import Path
from statistics import quantiles
from time import perf_counter
from typing import Any, Callable, Iterable

from .contracts import digest
from .local_cache import SQLiteReportTaskCache
from .report_task_runtime import ReportTask, ReportTaskBuilder, ReportTaskResult, run_report_task_batch


PERFORMANCE_SCHEMA_VERSION = "research-performance-budget-v1"
CACHE_READ_P95_SECONDS = 2.0
OFFLINE_REPORT_MODEL_P95_SECONDS = 3.0


def _p95(samples: list[float]) -> float:
    if not samples:
        return 0.0
    if len(samples) == 1:
        return samples[0]
    return quantiles(samples, n=100, method="inclusive")[94]


def measure_cache_reads(tasks: Iterable[ReportTask], cache: SQLiteReportTaskCache) -> dict[str, Any]:
    """Measure identity-bound cache reads without treating a miss as a hit."""
    samples: list[float] = []
    hits = 0
    for task in tasks:
        started = perf_counter()
        item = cache.get(
            cache_key=task.cache_key, ticker=task.ticker, snapshot_id=task.snapshot_id,
            evidence_manifest_hash=task.evidence_manifest_hash,
        )
        samples.append(perf_counter() - started)
        hits += int(item is not None)
    receipt = {
        "schema_version": PERFORMANCE_SCHEMA_VERSION,
        "scope": "local_contract_harness",
        "operation": "identity_bound_cache_read",
        "sample_count": len(samples), "hits": hits, "misses": len(samples) - hits,
        "p95_seconds": _p95(samples), "budget_p95_seconds": CACHE_READ_P95_SECONDS,
    }
    receipt["status"] = "passed" if receipt["p95_seconds"] <= CACHE_READ_P95_SECONDS else "budget_exceeded"
    receipt["receipt_hash"] = digest(receipt)
    return receipt


def run_report_task_workload(
    tasks: Iterable[ReportTask], *, state_root: Path, cache: SQLiteReportTaskCache, builder: ReportTaskBuilder,
) -> dict[str, Any]:
    """Measure an async-by-contract queue; no source collection occurs here."""
    durations: list[float] = []

    def measured(task: ReportTask) -> ReportTaskResult:
        started = perf_counter()
        try:
            return builder(task)
        finally:
            durations.append(perf_counter() - started)

    batch = run_report_task_batch(tasks, state_root=state_root, cache=cache, builder=measured)
    receipt = {
        "schema_version": PERFORMANCE_SCHEMA_VERSION,
        "scope": "local_contract_harness",
        "operation": "offline_report_task_queue",
        "fresh_report_mode": "queued_async_contract",
        "batch_key": batch["batch_key"], "task_count": len(batch["results"]),
        "queue_order": batch["execution"]["queue_order"], "effective_concurrency": batch["execution"]["effective_concurrency"],
        "builder_sample_count": len(durations), "builder_p95_seconds": _p95(durations),
        "budget_p95_seconds": OFFLINE_REPORT_MODEL_P95_SECONDS, "batch_status": batch["status"],
    }
    receipt["status"] = (
        "passed" if batch["status"] == "completed" and receipt["builder_p95_seconds"] <= OFFLINE_REPORT_MODEL_P95_SECONDS
        else "budget_exceeded" if receipt["builder_p95_seconds"] > OFFLINE_REPORT_MODEL_P95_SECONDS else "partial"
    )
    receipt["receipt_hash"] = digest(receipt)
    return {"workload": receipt, "batch": batch}


def _load_ledger(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        value = {"schema_version": PERFORMANCE_SCHEMA_VERSION, "entries": []}
    if not isinstance(value, dict) or not isinstance(value.get("entries"), list):
        raise ValueError("cost ledger is invalid")
    return value


def record_cost(
    root: Path, *, category: str, quantity: int, unit: str, observed_cost_minor: int | None, receipt_id: str,
) -> dict[str, Any]:
    """Persist only observed local/provider cost receipts; unknown is never zero."""
    if not category or not unit or not receipt_id or quantity < 0 or (observed_cost_minor is not None and observed_cost_minor < 0):
        raise ValueError("invalid cost receipt")
    path = root / "cost-ledger.json"
    ledger = _load_ledger(path)
    entry = {
        "entry_id": digest({"category": category, "quantity": quantity, "unit": unit, "cost": observed_cost_minor, "receipt_id": receipt_id}),
        "category": category, "quantity": quantity, "unit": unit, "observed_cost_minor": observed_cost_minor, "receipt_id": receipt_id,
    }
    entries = [item for item in ledger["entries"] if item.get("entry_id") != entry["entry_id"]]
    entries.append(entry)
    ledger = {"schema_version": PERFORMANCE_SCHEMA_VERSION, "entries": sorted(entries, key=lambda item: item["entry_id"])}
    ledger["ledger_hash"] = digest(ledger)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(ledger, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")
    temporary.replace(path)
    return entry


def evaluate_cost_budget(root: Path, budgets_minor: dict[str, int]) -> dict[str, Any]:
    """Report known totals and unknown categories separately; no cost inference."""
    if any(not isinstance(value, int) or value < 0 for value in budgets_minor.values()):
        raise ValueError("cost budgets must be nonnegative integer minor units")
    ledger = _load_ledger(root / "cost-ledger.json")
    totals: dict[str, int] = {}
    unknown: set[str] = set()
    for entry in ledger["entries"]:
        category = entry["category"]
        if entry.get("observed_cost_minor") is None:
            unknown.add(category)
        else:
            totals[category] = totals.get(category, 0) + int(entry["observed_cost_minor"])
    alerts = [
        {"category": category, "known_cost_minor": total, "budget_minor": budgets_minor[category], "status": "budget_exceeded"}
        for category, total in sorted(totals.items()) if category in budgets_minor and total > budgets_minor[category]
    ]
    receipt = {"schema_version": PERFORMANCE_SCHEMA_VERSION, "known_totals_minor": totals, "unknown_cost_categories": sorted(unknown), "alerts": alerts}
    receipt["receipt_hash"] = digest(receipt)
    return receipt
