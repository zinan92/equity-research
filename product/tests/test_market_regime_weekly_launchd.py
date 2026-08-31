from __future__ import annotations

from pathlib import Path
import sys
import unittest

PRODUCT = Path(__file__).resolve().parents[1]
SCRIPTS = PRODUCT / "scripts"
sys.path.insert(0, str(PRODUCT))
sys.path.insert(0, str(SCRIPTS))

from scripts.manage_market_regime_weekly_launchd import LABEL, build_plist  # noqa: E402


class WeeklyLaunchdTests(unittest.TestCase):
    def test_plist_is_weekly_monday_and_points_to_delivery(self) -> None:
        payload = build_plist(
            runtime_root=Path("/tmp/runtime"),
            output_root=Path("/tmp/output"),
            archive_root=Path("/tmp/archive"),
            key_file=Path("/tmp/key"),
            feishu_env_file=Path("/tmp/env"),
            python_executable="/usr/bin/python3",
        )
        self.assertEqual(payload["Label"], LABEL)
        self.assertEqual(payload["StartCalendarInterval"], {"Weekday": 1, "Hour": 8, "Minute": 20})
        self.assertIn("run_market_regime_weekly_delivery.py", payload["ProgramArguments"][1])
        self.assertIn("--archive-root", payload["ProgramArguments"])
        self.assertEqual(payload["EnvironmentVariables"]["PATH"], "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin")

