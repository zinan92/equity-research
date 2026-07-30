from __future__ import annotations

import sys
import hashlib
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "product"))

from data_core.round7_north_star import (  # noqa: E402
    ROUND7_BLIND_TICKERS,
    ROUND7_BLIND_SAMPLE_SHA256,
    ROUND7_READER_UNITS,
    ROUND7_STRUCTURE_SIGNATURE,
    SAFETY_SOURCE_SHA256,
    structure_signature,
    verify_blind_set,
    verify_round7_document,
)


class Round7NorthStarTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = ROOT / "docs" / "dossier-production"
        self.paths = tuple(
            self.root / "samples" / (ticker.lower() + "-v1.md")
            if ticker == "NVDA"
            else self.root / "samples" / (ticker + "-v1.md")
            for ticker in ROUND7_BLIND_TICKERS
        )

    def test_blind_set_is_the_canonical_round7_structure(self) -> None:
        checks = verify_blind_set(self.paths)
        self.assertEqual(len(checks), 5)
        self.assertEqual(
            {check.structure_signature for check in checks},
            {ROUND7_STRUCTURE_SIGNATURE},
        )

    def test_round7_has_nine_reader_units(self) -> None:
        self.assertEqual(len(ROUND7_READER_UNITS), 9)
        self.assertEqual(len(set(ROUND7_READER_UNITS)), 9)

    def test_legacy_catl_sample_is_not_misclassified_as_round7(self) -> None:
        check = verify_round7_document(
            self.root / "samples" / "300750.SZ-v1.md"
        )
        self.assertTrue(check.problems)
        self.assertIn(
            "structure signature differs from accepted Round 7",
            check.problems,
        )

    def test_structure_signature_changes_when_reader_order_changes(self) -> None:
        text = self.paths[0].read_text(encoding="utf-8")
        swapped = text.replace(
            "## 一句话定位", "## TEMP", 1
        ).replace(
            "## 产业坐标", "## 一句话定位", 1
        ).replace("## TEMP", "## 产业坐标", 1)
        self.assertNotEqual(
            structure_signature(swapped),
            ROUND7_STRUCTURE_SIGNATURE,
        )

    def test_heading_shell_cannot_pass_as_round7_quality(self) -> None:
        source = self.paths[0].read_text(encoding="utf-8")
        shell_lines = [
            line
            for line in source.splitlines()
            if line.startswith(("## ", "### ", "| ---", "| :--"))
        ]
        shell_lines.extend(
            (
                "`[F-01]` 空壳事实。[S-01]",
                "| S-01 | issuer | report | 2026-01-01 | https://example.com/a | use |",
                "| S-02 | issuer | report | 2026-01-02 | https://example.com/b | use |",
            )
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "shell.md"
            path.write_text("\n".join(shell_lines), encoding="utf-8")
            check = verify_round7_document(path)
        self.assertIn("body shorter than Round 7 minimum", check.problems)
        self.assertIn("missing falsifier", check.problems)
        self.assertIn("missing typed evidence gap", check.problems)

    def test_safety_sources_match_the_frozen_baseline(self) -> None:
        observed = {
            relative: hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
            for relative in SAFETY_SOURCE_SHA256
        }
        self.assertEqual(observed, SAFETY_SOURCE_SHA256)

    def test_blind_sample_bodies_match_the_approved_baseline(self) -> None:
        observed = {
            ticker: hashlib.sha256(path.read_bytes()).hexdigest()
            for ticker, path in zip(ROUND7_BLIND_TICKERS, self.paths)
        }
        self.assertEqual(observed, ROUND7_BLIND_SAMPLE_SHA256)


if __name__ == "__main__":
    unittest.main()
