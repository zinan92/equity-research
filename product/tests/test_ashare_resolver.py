from __future__ import annotations

import sys
import unittest
from pathlib import Path

PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT))

from data_core.ashare_resolver import AShareResolver, SecurityAlias, SecurityStatus  # noqa: E402


class AShareResolverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.resolver = AShareResolver(
            (
                SecurityAlias("600519.SH", "贵州茅台", "2001-08-27"),
                SecurityAlias("300750.SZ", "宁德时代", "2018-06-11"),
                SecurityAlias("830799.BJ", "艾融软件", "2021-11-15"),
                SecurityAlias("600000.SH", "同名", "2010-01-01"),
                SecurityAlias("000001.SZ", "同名", "2010-01-01"),
                SecurityAlias("600036.SH", "招商银行旧名", "2010-01-01", "2020-12-31"),
            ),
            (
                SecurityStatus("600519.SH", "2026-07-17", "normal"),
                SecurityStatus("300750.SZ", "2026-07-17", "suspended"),
                SecurityStatus("830799.BJ", "2026-07-17", "delisted"),
            ),
        )

    def test_a4_ticker_normalization_is_first_priority_across_markets(self) -> None:
        self.assertEqual(self.resolver.resolve("600519", as_of="2026-07-17")["ticker"], "600519.SH")
        self.assertEqual(self.resolver.resolve("sz300750", as_of="2026-07-17")["trading_status"], "suspended")
        self.assertEqual(self.resolver.resolve("830799.BJ", as_of="2026-07-17")["trading_status"], "delisted")

    def test_historical_alias_and_collision_fail_closed(self) -> None:
        self.assertEqual(self.resolver.resolve("招商银行旧名", as_of="2020-01-01")["status"], "matched")
        self.assertEqual(self.resolver.resolve("招商银行旧名", as_of="2026-01-01")["status"], "unmapped")
        collision = self.resolver.resolve("同名", as_of="2026-01-01")
        self.assertEqual(collision["status"], "ambiguous")
        self.assertEqual(len(collision["candidates"]), 2)


if __name__ == "__main__":
    unittest.main()
