from __future__ import annotations

import subprocess
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class NoFeishuFlagTests(unittest.TestCase):
    def test_help_lists_no_feishu_flag(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "run_market_regime_daily_delivery.py"), "--help"],
            capture_output=True, text=True, timeout=60, cwd=ROOT,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--no-feishu", result.stdout)


if __name__ == "__main__":
    unittest.main()
