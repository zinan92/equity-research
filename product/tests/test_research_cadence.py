from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

PRODUCT = Path(__file__).resolve().parents[1]
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from data_core.research_cadence import build_cadence_plan  # noqa: E402


class ResearchCadenceTest(unittest.TestCase):
    def test_policy_labels_fresh_due_stale_and_missing_deterministically(self) -> None:
        now = datetime(2026, 7, 25, 12, tzinfo=timezone.utc)
        plan = build_cadence_plan(now=now, last_good={"slow": now - timedelta(days=31), "periodic": now - timedelta(days=4), "fast": now - timedelta(hours=4)})
        states = {row["name"]: row["state"] for row in plan["lanes"]}
        self.assertEqual(states, {"slow": "due", "periodic": "stale", "fast": "fresh"})
        self.assertTrue(plan["truth_boundary"]["failed_run_must_preserve_last_good"])

    def test_naive_clock_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            build_cadence_plan(now=datetime(2026, 7, 25), last_good={})
