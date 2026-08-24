from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
import sys

PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT))

from data_core.market_regime_daily_runtime import DailyKlineRuntime, DailyRuntimeError  # noqa: E402
from product.tests.test_market_regime_daily_analysis import _source_bundle  # noqa: E402
from product.tests.test_market_regime_daily_thesis import _analysis_bundle, _thesis_provider  # noqa: E402
from data_core.market_regime_daily_thesis import compile_daily_thesis  # noqa: E402


class DailyRuntimeTests(unittest.TestCase):
    def test_run_once_completes_with_injected_source_analysis_and_thesis(self) -> None:
        source = _source_bundle()
        analysis = _analysis_bundle()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = DailyKlineRuntime(
                runtime_root=root / "runtime",
                output_root=root / "output",
                archive_root=root / "archive",
                key_file=None,
                no_llm=True,
                no_snapshots=True,
                source_builder=lambda _client: source,
                analysis_builder=lambda _source: analysis,
                thesis_builder=lambda current_analysis: compile_daily_thesis(current_analysis, _thesis_provider),
            )
            result = runtime.run_once(now=datetime(2026, 8, 25, tzinfo=timezone.utc))
            self.assertEqual(result["state"], "completed")
            self.assertEqual(runtime.status()["state"], "completed")

    def test_status_is_idle_before_first_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            status = DailyKlineRuntime(runtime_root=Path(directory) / "runtime", output_root=Path(directory) / "output", archive_root=Path(directory) / "archive", key_file=None).status()
            self.assertEqual(status["state"], "idle")


if __name__ == "__main__":
    unittest.main()
