from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

PRODUCT = Path(__file__).resolve().parents[1]
ROOT = PRODUCT.parent
sys.path.insert(0, str(PRODUCT))

from data_core.market_regime_daily_runtime import DailyKlineRuntime  # noqa: E402


def _runtime(primary: str, key_file: Path) -> DailyKlineRuntime:
    with tempfile.TemporaryDirectory() as tmp:
        return DailyKlineRuntime(
            runtime_root=Path(tmp) / "runtime",
            output_root=Path(tmp) / "out",
            archive_root=Path(tmp) / "archive",
            key_file=key_file,
            primary_provider=primary,
        )


class PrimaryProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.key = Path(self.tmp.name) / "deepseek-key"
        self.key.write_text("sk-test", encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_codex_primary_skips_the_deepseek_attempt(self) -> None:
        runtime = _runtime("codex", self.key)
        self.assertEqual(runtime.primary_provider, "codex")
        self.assertIsNone(runtime._deepseek_primary(object))

    def test_deepseek_primary_is_used_when_the_key_exists(self) -> None:
        runtime = _runtime("deepseek", self.key)
        created = runtime._deepseek_primary(lambda key_file: ("built", key_file))
        self.assertEqual(created[0], "built")

    def test_missing_key_still_falls_back(self) -> None:
        runtime = _runtime("deepseek", Path(self.tmp.name) / "absent")
        self.assertIsNone(runtime._deepseek_primary(object))

    def test_cli_exposes_the_flag(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "run_market_regime_daily_delivery.py"), "--help"],
            capture_output=True, text=True, timeout=60, cwd=ROOT,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--primary-provider", result.stdout)


if __name__ == "__main__":
    unittest.main()
