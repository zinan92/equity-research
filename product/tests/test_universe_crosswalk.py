from __future__ import annotations

import sys
import json
import tempfile
import unittest
from pathlib import Path


PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT))

from data_core.universe_crosswalk import UniverseCrosswalk, apply_code_migrations, build_crosswalk  # noqa: E402
from scripts.verify_crosswalk_coverage import verify  # noqa: E402


class UniverseCrosswalkTest(unittest.TestCase):
    def test_crosswalk_uses_code_and_market_not_name_order(self) -> None:
        records = build_crosswalk(
            [{"code": "300750", "name": "宁德时代", "market": "A股"}, {"code": "NVDA", "name": "NVIDIA", "market": "美股"}],
            [{"code": "300750", "name": "宁德时代", "market": "A股"}, {"code": "NVDA", "name": "NVIDIA", "market": "美股"}],
        )
        resolver = UniverseCrosswalk(records)
        catl = resolver.resolve("300750.SZ")
        self.assertEqual(catl.status, "matched")
        self.assertEqual({row.ticker for row in catl.candidates}, {"300750.SZ"})
        self.assertEqual(catl.data_kind, "fixture")
        self.assertEqual(catl.candidates[0].source_ref, "fixture")
        self.assertEqual(resolver.resolve("NVDA").status, "matched")

    def test_conflicting_names_are_ambiguous_not_silently_merged(self) -> None:
        records = build_crosswalk(
            [{"code": "300750", "name": "宁德时代", "market": "A股"}],
            [{"code": "300750", "name": "错误名称", "market": "A股"}],
        )
        self.assertTrue(all(row.status == "ambiguous" for row in records))
        self.assertEqual(UniverseCrosswalk(records).resolve("300750.SZ").status, "ambiguous")

    def test_unknown_or_unsupported_identity_stays_unmapped(self) -> None:
        records = build_crosswalk(
            [{"code": "", "name": "无代码公司", "market": "A股"}],
            [],
        )
        resolver = UniverseCrosswalk(records)
        self.assertEqual(records[0].status, "unmapped")
        self.assertEqual(resolver.resolve("不存在").status, "unmapped")

    def test_six_digit_main_records_infer_mainland_market(self) -> None:
        records = build_crosswalk([{"code": "600519", "name": "贵州茅台"}], [])
        self.assertEqual(records[0].status, "matched")
        self.assertEqual(records[0].ticker, "600519.SH")

    def test_code_migration_promotes_current_ticker_and_resolves_old_alias(self) -> None:
        records = build_crosswalk([{"code": "835185", "name": "贝特瑞", "market": "BSE"}], [])
        migrated = apply_code_migrations(records, [{
            "old_code": "835185", "current_code": "920185", "org_id": "gfbj0835185",
            "top_search_raw_hash": "a" * 64,
        }])
        resolver = UniverseCrosswalk(migrated)
        self.assertEqual(migrated[0].ticker, "920185.BJ")
        self.assertEqual(resolver.resolve("835185").status, "matched")
        self.assertEqual(resolver.resolve("835185").candidates[0].ticker, "920185.BJ")

    def test_golden_coverage_keeps_archive_absence_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            golden = root / "golden.json"
            audit = root / "audit.json"
            golden.write_text(json.dumps({"companies": [
                {"ticker": "300750.SZ", "market": "A"},
            ] * 30}), encoding="utf-8")
            audit.write_text(json.dumps({"records": []}), encoding="utf-8")
            result = verify(golden, audit)
        self.assertTrue(result["passed"])
        self.assertEqual(result["parsed_count"], 30)
        self.assertEqual(result["archive_unmapped_count"], 30)


if __name__ == "__main__":
    unittest.main()
