from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import patch

PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT))

from data_core.market_regime_weekly_feishu import (  # noqa: E402
    WeeklyFeishuDeliveryError,
    send_weekly_markdown,
)


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps({"code": 0}).encode("utf-8")


class WeeklyFeishuTests(unittest.TestCase):
    def test_send_uses_external_env_and_never_returns_webhook(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env = Path(directory) / ".env"
            env.write_text("FEISHU_BOT_WEBHOOK=https://example.invalid/hook\nFEISHU_BOT_SECRET=test-secret\n", encoding="utf-8")
            with patch("data_core.market_regime_weekly_feishu.urlopen", return_value=_Response()) as opened:
                result = send_weekly_markdown(
                    "# 周报\n\n结论",
                    week_end="2026-08-28",
                    report_id="report:test",
                    output_root=Path("/tmp/macro"),
                    archive_path=Path("/tmp/archive.md"),
                    env_file=env,
                )
            self.assertEqual(result["status"], "sent")
            self.assertNotIn("webhook", result)
            request = opened.call_args.args[0]
            payload = json.loads(request.data.decode("utf-8"))
            self.assertEqual(payload["msg_type"], "text")
            self.assertIn("周报", payload["content"]["text"])

    def test_missing_webhook_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(WeeklyFeishuDeliveryError, "feishu_webhook_missing"):
                send_weekly_markdown(
                    "周报",
                    week_end="2026-08-28",
                    report_id="report:test",
                    output_root=Path(directory),
                    env_file=Path(directory) / "missing.env",
                )

    def test_long_report_is_split_without_losing_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env = Path(directory) / ".env"
            env.write_text("FEISHU_BOT_WEBHOOK=https://example.invalid/hook\n", encoding="utf-8")
            with patch("data_core.market_regime_weekly_feishu.urlopen", return_value=_Response()) as opened:
                result = send_weekly_markdown(
                    "X" * 32000,
                    week_end="2026-08-28",
                    report_id="report:test",
                    output_root=Path(directory),
                    env_file=env,
                )
            self.assertGreater(result["chunk_count"], 1)
            self.assertEqual(opened.call_count, result["chunk_count"])

