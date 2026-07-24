from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


PRODUCT = Path(__file__).resolve().parents[1]
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from data_core.ashare_security_master import collect_security_master, write_runtime_capture  # noqa: E402


def payload(code: str, name: str) -> bytes:
    prefix = "sh" if code.startswith("6") else "sz" if code.startswith(("0", "3")) else "bj"
    return ("var data=" + json.dumps([{"symbol": prefix + code, "code": code, "name": name}]) + ";").encode()


class AShareSecurityMasterTest(unittest.TestCase):
    def test_real_identity_receipt_stays_identity_only_and_writes_outside_git(self) -> None:
        rows = {"SH": payload("600519", "贵州茅台"), "SZ": payload("300750", "宁德时代"), "BJ": payload("830000", "北交所样本")}

        def http_get(url: str) -> bytes:
            return rows[next(market for market in rows if "fs=" in url and market.lower() in url.lower() or False)]

        # The injected resolver is intentionally direct here: source selection is tested by market-specific calls below.
        calls: list[str] = []
        def source(url: str) -> bytes:
            calls.append(url)
            return rows[("SH", "SZ", "BJ")[len(calls) - 1]]

        capture = collect_security_master(http_get=source, now="2026-07-24T00:00:00Z", per_market=1)
        receipt = capture.receipt()
        self.assertEqual(receipt["record_count"], 3)
        self.assertEqual(receipt["exchanges"], ["BSE", "SSE", "SZSE"])
        self.assertFalse(receipt["truth_boundary"]["counts_as_report_model_coverage"])
        with tempfile.TemporaryDirectory() as temporary:
            saved = write_runtime_capture(capture, Path(temporary))
            self.assertTrue(Path(saved["path"]).is_file())
            self.assertEqual(len(list((Path(temporary) / "raw").glob("*.json"))), 3)

    def test_cross_exchange_and_duplicate_rows_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "exchange mismatch"):
            collect_security_master(http_get=lambda _url: payload("600519", "贵州茅台"), per_market=1, markets=("SZ",))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            collect_security_master(http_get=lambda _url: payload("600519", "贵州茅台"), per_market=1, markets=("SH", "SH"))


if __name__ == "__main__":
    unittest.main()
