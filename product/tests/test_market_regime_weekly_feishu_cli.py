from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT))

from data_core.market_regime_weekly_feishu_cli import _run_cli, send_weekly_rich_posts


class WeeklyFeishuCliTests(unittest.TestCase):
    def test_cli_exit_is_retried_without_leaking_stderr(self) -> None:
        with patch(
            "data_core.market_regime_weekly_feishu_cli.subprocess.run",
            side_effect=[
                SimpleNamespace(returncode=4, stdout="", stderr="auth token=<secret>"),
                SimpleNamespace(returncode=0, stdout='{"ok":true,"data":{}}', stderr=""),
            ],
        ) as run:
            with patch("data_core.market_regime_weekly_feishu_cli.time.sleep"):
                result = _run_cli(["lark-cli"], cwd=Path("/tmp"), retries=1)
        self.assertTrue(result["ok"])
        self.assertEqual(run.call_count, 2)

    def test_rich_posts_upload_images_and_never_emit_local_markdown_image_syntax(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_root = Path(directory)
            image = output_root / "snapshots" / "dxy.png"
            image.parent.mkdir(parents=True)
            image.write_bytes(b"png")
            report = {
                "report_id": "market-regime-weekly-report:test",
                "week_end": "2026-08-28",
                "chart_coverage": {"expected": 1, "ready": 1, "missing": 0},
                "cards": [
                    {
                        "asset_key": "dxy",
                        "display_name": "美元 ETF（UUP）",
                        "instrument": {"ticker": "UUP"},
                        "analysis": {
                            "weekly": {"text": "周线分析", "evidence_ids": ["e:w"]},
                            "daily": {"text": "日线分析", "evidence_ids": ["e:d"]},
                            "position": {"text": "位置：中位。"},
                            "structure": {"text": "结构：震荡。"},
                            "synthesis": {"text": "综合结论"},
                            "theoretical_implication": {"text": "市场含义"},
                        },
                        "chart_slots": [
                            {
                                "slot_id": "dxy:weekly",
                                "timeframe": "weekly",
                                "status": "complete",
                                "snapshot": {"asset": {"path": "snapshots/dxy.png"}},
                            }
                        ],
                    }
                ],
            }
            sent: list[dict] = []
            with patch(
                "data_core.market_regime_weekly_feishu_cli._run_cli",
                return_value={"ok": True, "data": {"image_key": "img_test"}},
            ), patch(
                "data_core.market_regime_weekly_feishu_cli._send_webhook",
                side_effect=lambda payload, env_file: sent.append(payload),
            ):
                result = send_weekly_rich_posts(
                    report,
                    output_root=output_root,
                    env_file=output_root / "feishu.env",
                )
            self.assertEqual(result["status"], "sent")
            self.assertEqual(result["image_count"], 1)
            self.assertEqual(result["post_count"], 2)
            self.assertTrue(any(item["msg_type"] == "post" for item in sent))
            encoded = str(sent)
            self.assertIn("img_test", encoded)
            self.assertNotIn("![", encoded)
            self.assertNotIn("snapshots/dxy.png", encoded)

    def test_missing_slot_is_described_without_uploading_an_old_image(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_root = Path(directory)
            report = {
                "report_id": "market-regime-weekly-report:test",
                "week_end": "2026-08-28",
                "chart_coverage": {"expected": 1, "ready": 0, "missing": 1},
                "cards": [
                    {
                        "asset_key": "dxy",
                        "display_name": "美元 ETF（UUP）",
                        "instrument": {"ticker": "UUP"},
                        "analysis": {"failure_code": "source_unavailable"},
                        "chart_slots": [
                            {
                                "slot_id": "dxy:weekly",
                                "timeframe": "weekly",
                                "status": "unavailable",
                                "feature": {"failure_code": "source_unavailable"},
                            }
                        ],
                    }
                ],
            }
            with patch("data_core.market_regime_weekly_feishu_cli._run_cli") as cli, patch(
                "data_core.market_regime_weekly_feishu_cli._send_webhook"
            ) as send:
                result = send_weekly_rich_posts(
                    report,
                    output_root=output_root,
                    env_file=output_root / "feishu.env",
                )
            self.assertEqual(result["image_count"], 0)
            cli.assert_not_called()
            self.assertIn("source_unavailable", str(send.call_args_list))


if __name__ == "__main__":
    unittest.main()
