from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


PRODUCT = Path(__file__).resolve().parents[1]
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from data_core.local_cache import SQLiteReportTaskCache  # noqa: E402
from data_core.performance_budget import (  # noqa: E402
    evaluate_cost_budget, measure_cache_reads, measure_cached_report_payloads, record_cost, run_report_task_workload,
)
from data_core.report_task_runtime import ReportTask, ReportTaskResult  # noqa: E402


class PerformanceBudgetTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.cache = SQLiteReportTaskCache(self.root / "cache.sqlite")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def tasks(count: int = 10) -> tuple[ReportTask, ...]:
        return tuple(ReportTask(f"{index:06d}.SZ", "snap_real_001", f"{index:064x}") for index in range(1, count + 1))

    def test_ten_task_workload_is_ordered_and_cannot_cross_write(self) -> None:
        tasks = self.tasks()

        def builder(task: ReportTask) -> ReportTaskResult:
            return ReportTaskResult(task, "completed", f"export-{task.ticker}", {"ticker": task.ticker})

        output = run_report_task_workload(tasks, state_root=self.root / "runs", cache=self.cache, builder=builder)
        self.assertEqual((output["workload"]["status"], output["workload"]["task_count"]), ("passed", 10))
        self.assertEqual(output["workload"]["queue_order"], [task.ticker for task in tasks])
        self.assertEqual({row["task"]["ticker"] for row in output["batch"]["results"]}, {task.ticker for task in tasks})
        cached = measure_cache_reads(tasks, self.cache)
        self.assertEqual((cached["status"], cached["hits"], cached["misses"]), ("passed", 10, 0))
        payload = measure_cached_report_payloads(tasks, self.cache)
        self.assertEqual((payload["status"], payload["hits"], payload["misses"]), ("passed", 10, 0))
        self.assertGreater(payload["payload_bytes"], 0)

    def test_known_cost_alerts_and_unknown_provider_costs_are_distinct(self) -> None:
        record_cost(self.root, category="parse", quantity=4, unit="documents", observed_cost_minor=120, receipt_id="parse-001")
        record_cost(self.root, category="model_tokens", quantity=1000, unit="tokens", observed_cost_minor=None, receipt_id="model-001")
        receipt = evaluate_cost_budget(self.root, {"parse": 100, "model_tokens": 500})
        self.assertEqual(receipt["alerts"], [{"category": "parse", "known_cost_minor": 120, "budget_minor": 100, "status": "budget_exceeded"}])
        self.assertEqual(receipt["unknown_cost_categories"], ["model_tokens"])


if __name__ == "__main__":
    unittest.main()
