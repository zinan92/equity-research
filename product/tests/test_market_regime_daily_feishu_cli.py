from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys

PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT))

from data_core.market_regime_daily_feishu_cli import send_daily_rich_posts  # noqa: E402


def _bundle() -> dict:
    return {
        "bundle_id": "market-regime-daily-analysis:" + ("a" * 64),
        "source_status": "ready",
        "cutoff_at": "2026-09-01T00:20:00Z",
        "assets": [
            {
                "asset_key": "dxy",
                "display_name": "美元 ETF（UUP）",
                "instrument": {"ticker": "UUP"},
                "request": {"timeframes": {"daily": {"status": "ready"}}},
                "analysis": {
                    "generation_status": "model_generated_unreviewed",
                    "daily": {"text": "日线短线修复，但中期方向仍待确认。"},
                    "position": {"text": "位置：高位。"},
                    "structure": {"text": "结构：偏弱。"},
                    "odds": {"text": "赔率尚未形成。"},
                    "synthesis": {"text": "综合结论：等待确认。"},
                    "theoretical_implication": {"text": "市场含义：美元变化会影响融资条件。"},
                },
                "snapshots": {
                    "daily": {
                        "asset": {"path": "snapshots/dxy.png", "sha256": "a" * 64}
                    }
                },
            }
        ],
    }


class DailyFeishuCliTests(unittest.TestCase):
    def test_rich_sender_uploads_images_and_never_sends_local_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_root = Path(directory)
            (output_root / "snapshots").mkdir()
            (output_root / "snapshots" / "dxy.png").write_bytes(b"png")
            sent: list[dict] = []

            def fake_send(payload, *, env_file):
                sent.append(payload)

            with patch("data_core.market_regime_daily_feishu_cli._resolve_lark_cli", return_value="/lark-cli"), patch(
                "data_core.market_regime_daily_feishu_cli._upload_snapshot", return_value="img_dxy"
            ), patch("data_core.market_regime_daily_feishu_cli._send_webhook", side_effect=fake_send):
                result = send_daily_rich_posts(
                    _bundle(),
                    {
                        "output": {
                            "generation_status": "model_generated_unreviewed",
                            "posture": "wait",
                            "headline": {"text": "等待确认。"},
                        }
                    },
                    output_root=output_root,
                    env_file=output_root / "daily-feishu.env",
                )

            self.assertEqual(result["status"], "sent")
            self.assertEqual(result["image_count"], 1)
            self.assertEqual(result["post_count"], 2)
            self.assertTrue(sent)
            encoded = repr(sent)
            self.assertNotIn("snapshots/dxy.png", encoded)
            self.assertNotIn(str(output_root), encoded)
            self.assertTrue(all(payload["msg_type"] == "post" for payload in sent))


if __name__ == "__main__":
    unittest.main()
