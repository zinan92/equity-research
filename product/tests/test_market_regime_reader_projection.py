from __future__ import annotations

from pathlib import Path
import sys
import unittest

PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT))

from data_core.market_regime_reader_projection import (  # noqa: E402
    project_daily_asset,
    project_weekly_card,
    render_reader_asset_html,
    render_reader_asset_markdown,
)


class ReaderProjectionTests(unittest.TestCase):
    def test_daily_and_weekly_projection_share_period_then_summary_order(self) -> None:
        daily = project_daily_asset(
            {
                "asset_key": "dxy",
                "display_name": "美元 ETF（UUP）",
                "request": {
                    "timeframes": {
                        "daily": {"status": "ready"},
                        "four_hour": {"status": "unavailable"},
                    }
                },
                "analysis": {
                    "generation_status": "model_generated_unreviewed",
                    "daily": {"text": "日线解释。"},
                    "synthesis": {"text": "综合结论。"},
                    "market_meaning": {"text": "市场含义。"},
                    "deterministic": {
                        "position": {"text": "位置：高位。"},
                        "structure": {"text": "结构：偏空。"},
                    },
                },
                "snapshots": {
                    "daily": {
                        "snapshot_id": "snapshot:dxy:daily",
                        "asset": {"path": "snapshots/dxy-daily.png", "sha256": "a" * 64},
                    }
                },
            }
        )
        weekly = project_weekly_card(
            {
                "asset_key": "dxy",
                "display_name": "美元 ETF（UUP）",
                "instrument": {"ticker": "UUP", "instrument_type": "ETF", "venue": "Yahoo Finance"},
                "analysis_status": "validated",
                "analysis": {
                    "weekly": {"text": "周线解释。"},
                    "daily": {"text": "日线解释。"},
                    "position": {"text": "位置：高位。"},
                    "structure": {"text": "结构：偏空。"},
                    "odds": {"text": "赔率未形成。"},
                    "synthesis": {"text": "综合结论。"},
                    "theoretical_implication": {"text": "市场含义。"},
                },
                "chart_slots": [
                    {
                        "timeframe": "weekly",
                        "status": "ready",
                        "snapshot": {
                            "snapshot_id": "snapshot:dxy:weekly",
                            "asset": {"path": "snapshots/dxy-weekly.png", "sha256": "b" * 64},
                        },
                    }
                ],
            }
        )
        daily_markdown = render_reader_asset_markdown(daily)
        weekly_markdown = render_reader_asset_markdown(weekly)
        for rendered in (daily_markdown, weekly_markdown):
            self.assertLess(rendered.index("![") , rendered.index("位置"))
            self.assertLess(rendered.index("位置"), rendered.index("综合结论"))
            self.assertNotIn("数据覆盖：", rendered)
        self.assertIn("dxy-daily.png", daily_markdown)
        self.assertIn("dxy-weekly.png", weekly_markdown)

    def test_shared_html_projection_renders_image_before_period_text(self) -> None:
        projection = project_daily_asset(
            {
                "asset_key": "dxy",
                "display_name": "美元 ETF（UUP）",
                "request": {"timeframes": {"daily": {"status": "ready"}}},
                "analysis": {
                    "generation_status": "analysis_unavailable",
                    "deterministic": {
                        "position": {"text": "位置：高位。"},
                        "structure": {"text": "结构：偏空。"},
                    }
                },
                "snapshots": {
                    "daily": {
                        "snapshot_id": "snapshot:dxy:daily",
                        "asset": {"path": "snapshots/dxy-daily.png", "sha256": "a" * 64},
                    }
                },
            }
        )
        html = render_reader_asset_html(projection)
        self.assertIn('src="snapshots/dxy-daily.png"', html)
        self.assertLess(html.index("<img "), html.index("位置：高位。"))
        self.assertIn("当前分析不可用", html)


if __name__ == "__main__":
    unittest.main()
