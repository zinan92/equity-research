#!/usr/bin/env python3
"""Create an external, bounded local performance/cost receipt for the report-task contract."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PRODUCT = ROOT / "product"
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from data_core.contracts import digest  # noqa: E402
from data_core.local_cache import SQLiteReportTaskCache  # noqa: E402
from data_core.performance_budget import (  # noqa: E402
    evaluate_cost_budget, measure_cache_reads, measure_cached_report_payloads, record_cost, run_report_task_workload,
)
from data_core.report_task_runtime import ReportTask, ReportTaskResult  # noqa: E402


def _write_receipt(path: Path, receipt: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def run_harness(root: Path, *, task_count: int, run_id: str | None = None) -> dict[str, Any]:
    if task_count < 1:
        raise ValueError("task_count must be positive")
    root = root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    tasks = tuple(
        ReportTask(f"PERF-{index:04d}", f"synthetic_performance_harness:{run_id}", hashlib.sha256(str(index).encode()).hexdigest())
        for index in range(1, task_count + 1)
    )
    cache = SQLiteReportTaskCache(root / "report-task-cache.sqlite")

    def builder(task: ReportTask) -> ReportTaskResult:
        return ReportTaskResult(task, "completed", digest({"task": task.cache_key}), {"performance_harness": True, "ticker": task.ticker})

    workload = run_report_task_workload(tasks, state_root=root / "runs", cache=cache, builder=builder)
    cache_reads = measure_cache_reads(tasks, cache)
    report_payloads = measure_cached_report_payloads(tasks, cache)
    for category, unit in (("parse", "documents"), ("model_tokens", "tokens"), ("storage", "bytes")):
        record_cost(root, category=category, quantity=0, unit=unit, observed_cost_minor=None, receipt_id="harness-no-provider-bill")
    costs = evaluate_cost_budget(root, {"parse": 0, "model_tokens": 0, "storage": 0})
    receipt = {
        "schema_version": "research-performance-harness-v1",
        "run_id": run_id,
        "task_count": task_count,
        "ten_x_baseline": 10,
        "workload": workload["workload"],
        "cache_summary": cache_reads,
        "cache_report_payload": report_payloads,
        "costs": costs,
        "status": "passed" if all(item["status"] == "passed" for item in (workload["workload"], cache_reads, report_payloads)) else "failed",
        "truth_boundary": {
            "local_contract_harness": True,
            "synthetic_task_identities": True,
            "network_latency_not_measured": True,
            "provider_billing_not_observed": True,
            "unknown_cost_is_not_zero": True,
            "fresh_report_contract": "queued_async_contract",
        },
    }
    receipt["receipt_hash"] = digest(receipt)
    _write_receipt(root / "performance-budget-receipt.json", receipt)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify local report-task performance and cost boundaries")
    parser.add_argument("--runtime", type=Path, required=True, help="external runtime directory for the receipt")
    parser.add_argument("--task-count", type=int, default=100)
    args = parser.parse_args()
    print(json.dumps(run_harness(args.runtime, task_count=args.task_count), ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
