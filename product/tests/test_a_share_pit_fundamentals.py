from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


PRODUCT = Path(__file__).resolve().parents[1]
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from data_core import collect_validated_ashare_packet  # noqa: E402


def _tencent_quote(symbol: str) -> bytes:
    fields = [""] * 50
    fields[1] = "宁德时代"
    fields[3] = "258.20"
    fields[30] = "20260721150000"
    fields[32] = "1.25"
    fields[33] = "262.00"
    fields[34] = "253.00"
    fields[39] = "21.50"
    fields[44] = "10800.00"
    fields[45] = "11400.00"
    fields[46] = "5.10"
    return (f'v_{symbol}="' + "~".join(fields) + '";').encode("gbk")


def _tencent_bars(symbol: str) -> bytes:
    return json.dumps(
        {
            "data": {
                symbol: {
                    "qfqday": [
                        ["2026-07-20", "250", "255", "256", "249", "100000"],
                        ["2026-07-21", "256", "258.2", "262", "253", "120000"],
                    ]
                }
            }
        }
    ).encode()


def _main_finance(revision_date: str) -> bytes:
    return json.dumps(
        {
            "result": {
                "data": [
                    {
                        "SECUCODE": "300750.SZ",
                        "SECURITY_CODE": "300750",
                        "REPORT_DATE": "2026-03-31 00:00:00",
                        "NOTICE_DATE": "2026-04-20 00:00:00",
                        "UPDATE_DATE": revision_date,
                        "REPORT_TYPE": "一季报",
                        "TOTALOPERATEREVE": 84705000000,
                        "PARENTNETPROFIT": 13963000000,
                        "TOTALOPERATEREVETZ": 52.4,
                        "PARENTNETPROFITTZ": 48.5,
                        "ROEJQ": 5.72,
                        "XSMLL": 24.82,
                        "XSJLL": 16.48,
                        "ZCFZL": 67.3,
                        "MGJYXJJE": 5.24,
                    }
                ]
            }
        }
    ).encode()


def _statement(report_name: str, revision_date: str) -> bytes:
    common = {
        "SECUCODE": "300750.SZ",
        "SECURITY_CODE": "300750",
        "REPORT_DATE": "2026-03-31 00:00:00",
        "NOTICE_DATE": "2026-04-20 00:00:00",
        "UPDATE_DATE": revision_date,
        "DATE_TYPE_CODE": "001",
    }
    values = {
        "RPT_DMSK_FN_BALANCE": {
            "TOTAL_ASSETS": 1046329036000,
            "TOTAL_LIABILITIES": 652096744000,
            "TOTAL_EQUITY": 394232291000,
            "MONETARYFUNDS": 351997422000,
            "ACCOUNTS_RECE": 77710096000,
            "INVENTORY": 108940929000,
            "FIXED_ASSET": 150043366000,
        },
        "RPT_DMSK_FN_INCOME": {
            "TOTAL_OPERATE_INCOME": 129131041000,
            "TOTAL_OPERATE_COST": 107104438000,
            "OPERATE_PROFIT": 26651291000,
            "TOTAL_PROFIT": 26681603000,
            "PARENT_NETPROFIT": 20737710000,
            "DEDUCT_PARENT_NETPROFIT": 18092638000,
        },
        "RPT_DMSK_FN_CASHFLOW": {
            "NETCASH_OPERATE": 33680852000,
            "NETCASH_INVEST": -14623616000,
            "NETCASH_FINANCE": 8762324000,
            "CONSTRUCT_LONG_ASSET": 12416302000,
        },
    }
    return json.dumps({"result": {"data": [{**common, **values[report_name]}]}}).encode()


def _eastmoney_quote(*, pe: int = 2150, code: str = "300750") -> bytes:
    return json.dumps(
        {
            "data": {
                "f43": 25820,
                "f44": 26200,
                "f45": 25300,
                "f46": 25600,
                "f57": code,
                "f58": "宁德时代",
                "f116": 1140000000000,
                "f117": 1080000000000,
                "f162": pe,
                "f167": 510,
            }
        },
        ensure_ascii=False,
    ).encode()


def _sina_bars(*, calendar_mismatch: bool = False, close_mismatch: bool = False) -> bytes:
    second_date = "2026-07-22" if calendar_mismatch else "2026-07-21"
    second_close = "280.00" if close_mismatch else "258.20"
    rows = [
        {"day": "2026-07-20", "open": "250", "close": "255", "high": "256", "low": "249", "volume": "100000"},
        {"day": second_date, "open": "256", "close": second_close, "high": "262", "low": "253", "volume": "120000"},
    ]
    return ("var park=(" + json.dumps(rows, ensure_ascii=False) + ");").encode()


def _cninfo_actions(code: str = "300750") -> bytes:
    return json.dumps(
        {
            "announcements": [
                {
                    "secCode": code,
                    "secName": "宁德时代",
                    "announcementId": "1223099780",
                    "announcementTitle": "<em>宁德时代</em>：2024年年度权益分派实施公告",
                    "announcementTime": 1744712173000,
                    "adjunctUrl": "finalpage/2025-04-15/1223099780.PDF",
                }
            ]
        },
        ensure_ascii=False,
    ).encode()


class ValidationHttp:
    def __init__(
        self,
        *,
        valuation_conflict: bool = False,
        calendar_mismatch: bool = False,
        close_mismatch: bool = False,
        cninfo_code: str = "300750",
        revision_date: str = "2026-04-20 12:00:00",
    ) -> None:
        self.valuation_conflict = valuation_conflict
        self.calendar_mismatch = calendar_mismatch
        self.close_mismatch = close_mismatch
        self.cninfo_code = cninfo_code
        self.revision_date = revision_date

    def __call__(self, url: str, encoding: str) -> bytes:
        if "qt.gtimg.cn" in url:
            return _tencent_quote(url.rsplit("=", 1)[-1])
        if "ifzq.gtimg.cn" in url:
            symbol = url.split("param=", 1)[1].split(",", 1)[0]
            return _tencent_bars(symbol)
        if "RPT_F10_FINANCE_MAINFINADATA" in url:
            return _main_finance(self.revision_date)
        for report in (
            "RPT_DMSK_FN_BALANCE",
            "RPT_DMSK_FN_INCOME",
            "RPT_DMSK_FN_CASHFLOW",
        ):
            if report in url:
                return _statement(report, self.revision_date)
        if "push2delay.eastmoney.com" in url:
            return _eastmoney_quote(pe=5000 if self.valuation_conflict else 2150)
        if "quotes.sina.cn" in url:
            return _sina_bars(
                calendar_mismatch=self.calendar_mismatch,
                close_mismatch=self.close_mismatch,
            )
        if "cninfo.com.cn" in url:
            return _cninfo_actions(self.cninfo_code)
        raise AssertionError(url)


class ASharePitFundamentalsTest(unittest.TestCase):
    def test_catl_cross_source_packet_is_publishable_and_aliases_resolve(self) -> None:
        result = collect_validated_ashare_packet(
            "300750.SZ", http_get=ValidationHttp(), bar_limit=2, fundamental_periods=1
        )
        self.assertTrue(result.publishable)
        self.assertFalse(result.conflicts)
        for alias in ("300750.SZ", "300750", "sz300750", "CN:300750.SZ", "宁德时代"):
            self.assertTrue(result.security_master.resolves(alias))
        self.assertEqual(result.secondary_daily_bars[-1]["close"], 258.2)
        self.assertEqual(result.corporate_actions[0]["event_id"], "cninfo:1223099780")
        self.assertTrue(result.corporate_actions[0]["document_url"].startswith("https://"))
        self.assertGreaterEqual(
            len(result.packet.fundamentals[0]["component_revision_ids"]), 4
        )

    def test_financial_row_revision_identity_changes_when_provider_row_changes(self) -> None:
        first = collect_validated_ashare_packet(
            "300750.SZ",
            http_get=ValidationHttp(revision_date="2026-04-20 12:00:00"),
            bar_limit=2,
            fundamental_periods=1,
        )
        second = collect_validated_ashare_packet(
            "300750.SZ",
            http_get=ValidationHttp(revision_date="2026-04-21 09:00:00"),
            bar_limit=2,
            fundamental_periods=1,
        )
        self.assertNotEqual(
            set(first.packet.fundamentals[0]["component_revision_ids"]),
            set(second.packet.fundamentals[0]["component_revision_ids"]),
        )

    def test_valuation_conflict_fails_closed(self) -> None:
        result = collect_validated_ashare_packet(
            "300750.SZ",
            http_get=ValidationHttp(valuation_conflict=True),
            bar_limit=2,
            fundamental_periods=1,
        )
        self.assertFalse(result.publishable)
        self.assertTrue(any(item.check == "valuation_pe_ttm" for item in result.conflicts))

    def test_calendar_conflict_fails_closed(self) -> None:
        result = collect_validated_ashare_packet(
            "300750.SZ",
            http_get=ValidationHttp(calendar_mismatch=True),
            bar_limit=2,
            fundamental_periods=1,
        )
        self.assertFalse(result.publishable)
        self.assertTrue(any(item.check == "trading_calendar" for item in result.conflicts))

    def test_daily_close_conflict_fails_closed(self) -> None:
        result = collect_validated_ashare_packet(
            "300750.SZ",
            http_get=ValidationHttp(close_mismatch=True),
            bar_limit=2,
            fundamental_periods=1,
        )
        self.assertFalse(result.publishable)
        self.assertTrue(any(item.check.startswith("daily_close:") for item in result.conflicts))

    def test_cninfo_wrong_ticker_fails_closed(self) -> None:
        result = collect_validated_ashare_packet(
            "300750.SZ",
            http_get=ValidationHttp(cninfo_code="000001"),
            bar_limit=2,
            fundamental_periods=1,
        )
        self.assertFalse(result.publishable)
        self.assertFalse(result.validation_outcomes["corporate_actions"].publishable)


if __name__ == "__main__":
    unittest.main()
