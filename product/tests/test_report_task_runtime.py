from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


PRODUCT = Path(__file__).resolve().parents[1]
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from data_core.local_cache import SQLiteReportTaskCache  # noqa: E402
from data_core.report_task_runtime import ReportTask, ReportTaskResult, run_report_task_batch  # noqa: E402


class ReportTaskRuntimeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.cache = SQLiteReportTaskCache(self.root / "cache.sqlite")
        self.calls: list[str] = []

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def task(ticker: str, snapshot: str = "snap_2025_05", evidence: str = "a" * 64) -> ReportTask:
        return ReportTask(ticker, snapshot, evidence)

    def builder(self, task: ReportTask) -> ReportTaskResult:
        self.calls.append(task.ticker)
        return ReportTaskResult(task, "completed", "export_" + task.ticker, {"ticker": task.ticker, "snapshot": task.snapshot_id})

    def test_cache_isolation_binds_snapshot_and_evidence(self) -> None:
        first = self.task("300750.SZ")
        changed_snapshot = self.task("300750.SZ", snapshot="snap_other")
        changed_evidence = self.task("300750.SZ", evidence="b" * 64)
        run_report_task_batch((first,), state_root=self.root / "runs", cache=self.cache, builder=self.builder)
        self.assertEqual(self.calls, ["300750.SZ"])
        run_report_task_batch((changed_snapshot, changed_evidence), state_root=self.root / "runs", cache=self.cache, builder=self.builder)
        self.assertEqual(self.calls, ["300750.SZ", "300750.SZ", "300750.SZ"])

    def test_interruption_resume_reuses_completed_and_retries_only_unfinished(self) -> None:
        tasks = (self.task("600036.SH"), self.task("300750.SZ"))
        interrupted = {"once": False}

        def unreliable(task: ReportTask) -> ReportTaskResult:
            self.calls.append(task.ticker)
            if task.ticker == "600036.SH" and not interrupted["once"]:
                interrupted["once"] = True
                raise RuntimeError("injected interruption")
            return ReportTaskResult(task, "completed", "export_" + task.ticker, {"ticker": task.ticker})

        first = run_report_task_batch(tasks, state_root=self.root / "runs", cache=self.cache, builder=unreliable)
        self.assertEqual(first["status"], "partial")
        self.assertEqual(first["counts"]["failed"], 1)
        second = run_report_task_batch(tasks, state_root=self.root / "runs", cache=self.cache, builder=unreliable)
        self.assertTrue(second["resumed"])
        self.assertEqual(second["status"], "completed")
        self.assertEqual(second["counts"]["completed"], 2)
        self.assertEqual(self.calls.count("300750.SZ"), 1)
        self.assertEqual(self.calls.count("600036.SH"), 2)

    def test_queue_order_rate_limit_and_statuses_are_explicit(self) -> None:
        sleeps: list[float] = []
        partial = self.task("600519.SH")

        def mixed(task: ReportTask) -> ReportTaskResult:
            if task == partial:
                return ReportTaskResult(task, "partial", None, None, "missing_sell_side")
            return self.builder(task)

        receipt = run_report_task_batch(
            (partial, self.task("000001.SZ")), state_root=self.root / "runs", cache=self.cache,
            builder=mixed, max_concurrency=3, min_interval_seconds=0.25, sleep_fn=sleeps.append,
        )
        self.assertEqual(receipt["status"], "partial")
        self.assertEqual(receipt["execution"]["configured_max_concurrency"], 3)
        self.assertEqual(receipt["execution"]["effective_concurrency"], 1)
        self.assertEqual(receipt["execution"]["queue_order"], ["000001.SZ", "600519.SH"])
        self.assertEqual(sleeps, [0.25])
        self.assertEqual(receipt["counts"]["partial"], 1)

    def test_builder_cannot_cross_write_ticker_identity(self) -> None:
        task = self.task("300750.SZ")

        def wrong_task(_task: ReportTask) -> ReportTaskResult:
            other = self.task("600519.SH")
            return ReportTaskResult(other, "completed", "wrong", {"ticker": "600519.SH"})

        receipt = run_report_task_batch((task,), state_root=self.root / "runs", cache=self.cache, builder=wrong_task)
        self.assertEqual(receipt["status"], "partial")
        self.assertIn("another task identity", receipt["results"][0]["reason"])


if __name__ == "__main__":
    unittest.main()
