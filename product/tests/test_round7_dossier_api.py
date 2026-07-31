import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import round7_dossier_payload


class Round7DossierApiTests(unittest.TestCase):
    def test_catl_and_moutai_are_readable_from_persistent_receipts(self):
        for ticker in ("300750.SZ", "600519.SH"):
            payload = round7_dossier_payload(ticker)
            self.assertEqual(payload["ticker"], ticker)
            self.assertEqual(payload["degradation"]["tier"], "B")
            self.assertEqual(len(payload["chapters"]), 8)
            self.assertTrue(payload["receipt_hash"])

    def test_missing_dossier_is_not_synthesized(self):
        with self.assertRaises(FileNotFoundError):
            round7_dossier_payload("000000.SZ")


if __name__ == "__main__":
    unittest.main()
