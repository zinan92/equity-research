from __future__ import annotations

import sys
import unittest
from pathlib import Path


PRODUCT = Path(__file__).resolve().parents[1]
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from industry_intelligence import IndustryIntelligenceError, dossier_payload, load_snapshot, overview_payload  # noqa: E402


class IndustryIntelligenceTest(unittest.TestCase):
    def test_legacy_snapshot_is_never_served_as_product_research(self) -> None:
        for action in (load_snapshot, overview_payload, lambda: dossier_payload("300223")):
            with self.assertRaisesRegex(IndustryIntelligenceError, "canonical evidence-backed"):
                action()

    def test_legacy_product_snapshot_is_absent(self) -> None:
        self.assertFalse((PRODUCT / "data" / "industry-intelligence-v1.json").exists())


if __name__ == "__main__":
    unittest.main()
