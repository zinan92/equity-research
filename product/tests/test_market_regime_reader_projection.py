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
    render_reader_article,
    render_reader_asset_markdown,
)


class ReaderProjectionTests(unittest.TestCase):
    def test_daily_and_weekly_projection_share_period_then_summary_order(self) -> None:
        daily = project_daily_asset(
            {
                "asset_key": "dxy",
                "display_name": "美元 ETF（UUP）",
                "instrument": {"ticker": "UUP", "canonical_symbol": "UUP", "instrument_type": "ETF", "venue": "Yahoo Finance"},
                "request": {
                    "timeframes": {
                        "daily": {"status": "ready", "latest_timestamp": "2026-08-25T20:00:00Z"},
                        "four_hour": {"status": "unavailable", "latest_timestamp": None},
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
        self.assertIn("标的：UUP · ETF · Yahoo Finance", daily_markdown)
        self.assertIn("观察时点：2026-08-25T20:00:00Z", daily_markdown)

    def test_article_projection_preserves_image_then_text_then_summary_order(self) -> None:
        projection = project_daily_asset(
            {
                "asset_key": "dxy",
                "display_name": "美元 ETF（UUP）",
                "instrument": {"ticker": "UUP", "canonical_symbol": "UUP", "instrument_type": "ETF"},
                "request": {"timeframes": {"daily": {"status": "ready", "latest_timestamp": "2026-08-25"}}},
                "analysis": {"generation_status": "analysis_unavailable", "deterministic": {"position": {"text": "位置：高位。"}, "structure": {"text": "结构：偏空。"}}},
                "snapshots": {"daily": {"snapshot_id": "snapshot:dxy:daily", "asset": {"path": "snapshots/dxy-daily.png", "sha256": "a" * 64}}},
            }
        )
        article = render_reader_article([projection], title="宏观 K 线日报", cutoff_at="2026-08-25")
        self.assertEqual(article["schema_version"], "market-regime-reader-article-v1")
        self.assertEqual([block["type"] for block in article["blocks"]], ["asset_heading", "image", "period_text", "asset_summary"])
        self.assertEqual(article["media"][0]["path"], "snapshots/dxy-daily.png")
        self.assertEqual(article["media"][0]["sha256"], "a" * 64)

    def test_markdown_unavailable_period_is_not_repeated(self) -> None:
        projection = project_daily_asset(
            {
                "asset_key": "dxy",
                "display_name": "美元 ETF（UUP）",
                "request": {"timeframes": {"four_hour": {"status": "unavailable"}}},
                "analysis": {"generation_status": "analysis_unavailable"},
            }
        )
        markdown = render_reader_asset_markdown(projection)
        self.assertEqual(markdown.count("本周期数据暂缺"), 1)
        self.assertIn("状态：模型解释不可用", markdown)

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
