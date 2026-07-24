from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


PRODUCT = Path(__file__).resolve().parents[1]
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from data_core.source_observability import (  # noqa: E402
    SourceObservabilityLedger,
    alert_candidates,
    build_run_trace,
)


NOW = datetime(2026, 7, 24, 12, tzinfo=timezone.utc)
TICKERS = ("300750.SZ", "600519.SH")


def receipt(*, selected: str, attempts: list[dict], status: str = "success") -> dict:
    return {
        "run_id": "refresh_test_001",
        "status": status,
        "canonical_status": status,
        "selected_adapter": selected,
        "attempts": attempts,
        "snapshot": {"snapshot_id": "core_real_001", "manifest_hash": "manifest-001"},
    }


class SourceObservabilityTest(unittest.TestCase):
    def test_fallback_failure_is_visible_but_does_not_trigger_coverage_alert(self) -> None:
        trace = build_run_trace(
            receipt(
                selected="fallback",
                attempts=[
                    {"adapter": "primary", "role": "primary", "status": "failed", "data_kind": "real"},
                    {"adapter": "fallback", "role": "fallback", "status": "success", "data_kind": "real", "target_trade_date": "2026-07-24", "finished_at": NOW.isoformat()},
                ],
            ), required_tickers=TICKERS, now=NOW,
        )
        self.assertEqual(trace["production_health"], "healthy")
        primary = next(item for item in trace["source_health"] if item["adapter"] == "primary")
        self.assertEqual(primary["coverage_impact"], 0)
        self.assertEqual(alert_candidates(trace), [])

    def test_fixture_source_never_returns_a_healthy_production_trace(self) -> None:
        trace = build_run_trace(
            receipt(selected="fixture", attempts=[
                {"adapter": "fixture", "role": "primary", "status": "success", "data_kind": "fixture", "target_trade_date": "2026-07-24", "finished_at": NOW.isoformat()},
            ]), required_tickers=TICKERS, now=NOW,
        )
        self.assertEqual(trace["production_health"], "attention")
        alert = alert_candidates(trace)[0]
        self.assertEqual((alert["severity"], alert["coverage_impact"]), ("critical", 2))
        self.assertNotIn("raw", str(trace).lower())

    def test_alert_lifecycle_deduplicates_and_recovers_after_real_source_returns(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            ledger = SourceObservabilityLedger(Path(temp))
            fixture = receipt(selected="fixture", attempts=[
                {"adapter": "fixture", "role": "primary", "status": "success", "data_kind": "fixture", "target_trade_date": "2026-07-24", "finished_at": NOW.isoformat()},
            ])
            first = ledger.record(fixture, required_tickers=TICKERS, now=NOW)
            second = ledger.record(fixture, required_tickers=TICKERS, now=NOW)
            self.assertEqual(len(first["alerts"]), 1)
            self.assertEqual(first["alerts"][0]["opened_at"], second["alerts"][0]["opened_at"])
            real = receipt(selected="real", attempts=[
                {"adapter": "real", "role": "primary", "status": "success", "data_kind": "real", "target_trade_date": "2026-07-24", "finished_at": NOW.isoformat()},
            ])
            recovered = ledger.record(real, required_tickers=TICKERS, now=NOW)
            self.assertEqual(recovered["alerts"][0]["status"], "recovered")


if __name__ == "__main__":
    unittest.main()
