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
    ROUND7_CANONICAL_DOSSIER_SHA256,
    ROUND7_READER_UNITS,
    ROUND7_STRUCTURE_SIGNATURE,
    SAFETY_SOURCE_SHA256,
    structure_signature,
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
        self.canonical = self.root / "samples" / "300750.SZ-v1.md"

    def test_catl_sample_is_the_exact_canonical_round7_structure(self) -> None:
        check = verify_round7_document(self.canonical)
        self.assertEqual(check.problems, ())
        self.assertEqual(check.structure_signature, ROUND7_STRUCTURE_SIGNATURE)
        self.assertEqual(
            hashlib.sha256(self.canonical.read_bytes()).hexdigest(),
            ROUND7_CANONICAL_DOSSIER_SHA256,
        )

    def test_round7_has_nine_reader_units(self) -> None:
        self.assertEqual(len(ROUND7_READER_UNITS), 9)
        self.assertEqual(len(set(ROUND7_READER_UNITS)), 9)

    def test_blind_pack_is_reference_evidence_not_canonical_taxonomy(self) -> None:
        checks = tuple(verify_round7_document(path) for path in self.paths)
        self.assertTrue(all(check.problems for check in checks))
        self.assertNotIn(
            ROUND7_STRUCTURE_SIGNATURE,
            {check.structure_signature for check in checks},
        )

    def test_structure_signature_changes_when_reader_order_changes(self) -> None:
        text = self.canonical.read_text(encoding="utf-8")
        swapped = text.replace(
            "## 1. 一句话定位", "## TEMP", 1
        ).replace(
            "## 2. 身份、创始人与治理", "## 1. 一句话定位", 1
        ).replace("## TEMP", "## 2. 身份、创始人与治理", 1)
        self.assertNotEqual(
            structure_signature(swapped),
            ROUND7_STRUCTURE_SIGNATURE,
        )

    def test_heading_shell_cannot_pass_as_round7_quality(self) -> None:
        source = self.canonical.read_text(encoding="utf-8")
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
