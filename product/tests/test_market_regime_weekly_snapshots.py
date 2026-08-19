from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import sys

PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT))
sys.path.insert(0, str(PRODUCT / "tests"))

from data_core.market_regime_weekly_report import attach_chart_snapshots, build_weekly_report  # noqa: E402
from data_core.market_regime_weekly_report import render_weekly_html, render_weekly_markdown  # noqa: E402
from data_core.market_regime_weekly_runtime import WeeklyReportStore, WeeklyRuntimeError  # noqa: E402
from data_core.market_regime_weekly_snapshots import PlaywrightWeeklyChartSnapshotPort  # noqa: E402
from test_market_regime_weekly_report import (  # noqa: E402
    analyses_fixture,
    candle_response_fixture,
    ranking_fixture,
    source_fixture,
)


class WeeklyChartSnapshotTest(unittest.TestCase):
    def test_browser_snapshots_bind_renderer_input_and_report_readback(self) -> None:
        with tempfile.TemporaryDirectory(prefix="weekly-snapshot-test-") as temporary:
            root = Path(temporary)
            candle_responses = {
                "gold:weekly": candle_response_fixture("gold"),
                "us2y:weekly": candle_response_fixture("us2y", series_kind="rate_level"),
            }
            report = build_weekly_report(
                source_fixture(),
                analyses_fixture(),
                ranking_fixture(),
                candle_responses=candle_responses,
            )
            port = PlaywrightWeeklyChartSnapshotPort(runtime_root=root / "runtime", output_root=root / "output")
            snapshots = port(report=report, candle_responses=candle_responses)
            self.assertEqual(set(snapshots), {"gold:weekly", "us2y:weekly"})
            updated = attach_chart_snapshots(report, snapshots)
            self.assertNotEqual(updated["report_id"], report["report_id"])
            for slot in updated["chart_slots"]:
                if slot["slot_id"] not in snapshots:
                    continue
                snapshot = slot["snapshot"]
                self.assertTrue((root / "output" / snapshot["asset"]["path"]).is_file())
                self.assertTrue((root / "runtime" / snapshot["receipt"]["path"]).is_file())
            store = WeeklyReportStore(root / "runtime", root / "output")
            pointer = store.publish(updated)
            self.assertEqual(store.latest()["report_id"], pointer["report_id"])
            snapshot_slot = next(slot for slot in updated["chart_slots"] if isinstance(slot.get("snapshot"), dict))
            snapshot_id = snapshot_slot["snapshot"]["snapshot_id"]
            self.assertIn(snapshot_id, render_weekly_html(updated))
            self.assertIn(snapshot_id, render_weekly_markdown(updated))
            asset_path = root / "output" / snapshot_slot["snapshot"]["asset"]["path"]
            asset_path.write_bytes(b"tampered")
            with self.assertRaisesRegex(WeeklyRuntimeError, "weekly_chart_snapshot_hash_mismatch"):
                store.latest()


if __name__ == "__main__":
    unittest.main()
