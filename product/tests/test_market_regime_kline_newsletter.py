from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import plistlib
import sys
import tempfile
import unittest


PRODUCT = Path(__file__).resolve().parents[1]
ROOT = PRODUCT.parent
sys.path.insert(0, str(PRODUCT))
sys.path.insert(0, str(ROOT / "scripts"))

from data_core.market_regime_daily_evidence import MarketRegimeDailyEvidenceStore  # noqa: E402
from data_core.market_regime_daily_narrative import MarketRegimeDailyNarrativeStore  # noqa: E402
from data_core.market_regime_kline_newsletter import (  # noqa: E402
    BITCOIN_SCHEMA_VERSION,
    DISPLAY_ORDER,
    BitcoinDailyStore,
    KlineNewsletterError,
    KlineNewsletterStore,
    build_report_payload,
    render_html,
    render_markdown,
)
from data_core.market_regime_data import HttpCapture, MarketRegimeDataStore  # noqa: E402
from data_core.market_regime_macro_data import MarketRegimeMacroDataStore  # noqa: E402
from product.tests.test_market_regime_daily_evidence import (  # noqa: E402
    NOW,
    fixture_inputs,
)
from product.tests.test_market_regime_daily_narrative import (  # noqa: E402
    FakeProvider,
    valid_output,
)
from product.tests.test_market_regime_data import yahoo_body  # noqa: E402
from manage_market_regime_kline_newsletter_launchd import LABEL, build_plist  # noqa: E402


class BitcoinTransport:
    def __init__(self, *, bad_symbol: bool = False) -> None:
        self.bad_symbol = bad_symbol

    def __call__(self, url: str) -> HttpCapture:
        symbol = "ETH-USD" if self.bad_symbol else "BTC-USD"
        body = yahoo_body(symbol, count=210, timezone_name="UTC")
        return HttpCapture(
            "GET",
            url,
            url,
            200,
            (("content-type", "application/json"),),
            (),
            (url,),
            body,
            "2026-08-07T01:00:00Z",
        )


def compiled_inputs(base: Path, *, provider: FakeProvider | None = None) -> tuple:
    daily_root = base / "daily"
    macro_root = base / "macro"
    evidence_root = base / "evidence"
    narrative_root = base / "narrative"
    daily, _, macro = fixture_inputs(daily_root, macro_root)
    evidence_store = MarketRegimeDailyEvidenceStore(daily_root, macro_root, evidence_root)
    pack = evidence_store.compile_latest()
    narrative_store = MarketRegimeDailyNarrativeStore(evidence_store, narrative_root)
    narrative = narrative_store.compile_latest(
        provider if provider is not None else FakeProvider(valid_output(pack))
    )
    bitcoin_store = BitcoinDailyStore(base / "bitcoin", http_get=BitcoinTransport())
    bitcoin = bitcoin_store.refresh(now=datetime(2026, 8, 7, 1, 0, tzinfo=timezone.utc))
    # Unit fixtures are never served by the runtime.  Promote only the isolated
    # in-memory copy so the product builder can be exercised in a temp folder.
    bitcoin = json.loads(json.dumps(bitcoin))
    bitcoin["data_kind"] = "real"
    bitcoin["identity_core"]["data_kind"] = "real"
    return daily, macro, pack, narrative, bitcoin


class KlineNewsletterTest(unittest.TestCase):
    def test_bitcoin_freezes_completed_daily_bars_and_rejects_wrong_symbol(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = BitcoinDailyStore(root, http_get=BitcoinTransport())
            artifact = store.refresh(
                now=datetime(2026, 8, 7, 1, 0, tzinfo=timezone.utc)
            )
            self.assertEqual(artifact["schema_version"], BITCOIN_SCHEMA_VERSION)
            self.assertEqual(artifact["instrument"]["key"], "bitcoin")
            self.assertGreaterEqual(artifact["bar_count"], 200)
            self.assertEqual(artifact["change_5d_unit"], "percent_return")
            self.assertEqual(store.latest()["bitcoin_id"], artifact["bitcoin_id"])
            self.assertEqual(artifact["data_kind"], "fixture")
        with tempfile.TemporaryDirectory() as temporary:
            store = BitcoinDailyStore(
                Path(temporary), http_get=BitcoinTransport(bad_symbol=True)
            )
            with self.assertRaisesRegex(KlineNewsletterError, "normalization_rejected"):
                store.refresh(now=datetime(2026, 8, 7, 1, 0, tzinfo=timezone.utc))

    def test_report_has_exactly_fifteen_observations_charts_and_rate_units(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            daily, macro, pack, narrative, bitcoin = compiled_inputs(base)
            report = build_report_payload(
                pack=pack,
                narrative=narrative,
                daily=daily,
                macro=macro,
                bitcoin=bitcoin,
                generated_at=NOW,
            )
            self.assertEqual([row["key"] for row in report["cross_section"]], list(DISPLAY_ORDER))
            self.assertEqual([row["key"] for row in report["charts"]], list(DISPLAY_ORDER))
            self.assertEqual(len(report["charts"]), 15)
            rows = {row["key"]: row for row in report["cross_section"]}
            self.assertEqual(rows["sp500"]["change_5d_unit"], "percent_return")
            self.assertEqual(rows["us2y"]["change_5d_unit"], "basis_points")
            self.assertEqual(rows["us2s10s"]["level_unit"], "basis_points")
            charts = {row["key"]: row for row in report["charts"]}
            self.assertEqual(charts["us2y"]["chart_type"], "line")
            self.assertEqual(charts["bitcoin"]["chart_type"], "candlestick")
            self.assertFalse(report["truth_boundary"]["finance_newsletter_input"])
            self.assertFalse(report["truth_boundary"]["publication_eligible"])

    def test_north_star_render_is_vertical_responsive_and_visually_distinct(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            daily, macro, pack, narrative, bitcoin = compiled_inputs(Path(temporary))
            report = build_report_payload(
                pack=pack,
                narrative=narrative,
                daily=daily,
                macro=macro,
                bitcoin=bitcoin,
                generated_at=NOW,
            )
            html = render_html(report)
            markdown = render_markdown(report)
            self.assertIn('data-posture="wait"', html)
            self.assertIn('html[data-posture="attack"]', html)
            self.assertIn('html[data-posture="defense"]', html)
            self.assertIn('@media(max-width:700px)', html)
            self.assertEqual(html.count("<canvas data-chart="), 15)
            self.assertIn("15 个观测的五日横截面", html)
            self.assertIn("两个 Track 只在事后由 Park 人工比较", html)
            self.assertIn("| 美国国债 2Y |", markdown)
            self.assertIn("bp", markdown)

    def test_fallback_is_honest_and_fixture_cannot_publish(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            daily_root, macro_root = base / "daily", base / "macro"
            daily, _, macro = fixture_inputs(daily_root, macro_root)
            evidence_store = MarketRegimeDailyEvidenceStore(
                daily_root, macro_root, base / "evidence"
            )
            pack = evidence_store.compile_latest()
            narrative = MarketRegimeDailyNarrativeStore(
                evidence_store, base / "narrative"
            ).compile_latest(None)
            bitcoin = BitcoinDailyStore(
                base / "bitcoin", http_get=BitcoinTransport()
            ).refresh(now=datetime(2026, 8, 7, 1, 0, tzinfo=timezone.utc))
            with self.assertRaisesRegex(KlineNewsletterError, "fixture_bitcoin"):
                build_report_payload(
                    pack=pack,
                    narrative=narrative,
                    daily=daily,
                    macro=macro,
                    bitcoin=bitcoin,
                    generated_at=NOW,
                )
            promoted = json.loads(json.dumps(bitcoin))
            promoted["data_kind"] = "real"
            report = build_report_payload(
                pack=pack,
                narrative=narrative,
                daily=daily,
                macro=macro,
                bitcoin=promoted,
                generated_at=NOW,
            )
            self.assertEqual(report["posture"], "unknown")
            self.assertEqual(report["generation_status"], "deterministic_fallback")
            self.assertIn("解释不可用", report["synthesis"])
            self.assertEqual(len(report["falsifiers"]), 2)

    def test_publish_replay_and_tamper_fail_closed_without_losing_last_good(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            daily, macro, pack, narrative, bitcoin = compiled_inputs(base)
            report = build_report_payload(
                pack=pack,
                narrative=narrative,
                daily=daily,
                macro=macro,
                bitcoin=bitcoin,
                generated_at=NOW,
            )
            store = KlineNewsletterStore(base / "runtime", base / "output")
            first = store.publish(report)
            replay = store.publish(report)
            self.assertEqual(first["report_id"], replay["report_id"])
            pointer, loaded = store.latest()
            self.assertEqual(loaded["report_id"], report["report_id"])
            artifact = base / "runtime" / pointer["payload"]["path"]
            artifact.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(KlineNewsletterError, "hash_mismatch"):
                store.latest()

    def test_launchd_contract_is_one_0820_job_and_not_finance(self) -> None:
        root = Path("/Applications/ParkKlineNewsletter/app")
        payload = build_plist(
            app_root=root,
            daily_root=Path("/Library/Application Support/ParkMarketRegime/runtime"),
            runtime_root=Path("/Library/Application Support/ParkKlineNewsletter/runtime"),
            output_root=Path("/Desktop/K线日报"),
            key_file=Path("/secrets/deepseek-key"),
            python=Path("/usr/bin/python3"),
        )
        encoded = plistlib.dumps(payload)
        decoded = plistlib.loads(encoded)
        self.assertEqual(decoded["Label"], LABEL)
        self.assertEqual(decoded["StartCalendarInterval"], {"Hour": 8, "Minute": 20})
        self.assertFalse(decoded["RunAtLoad"])
        self.assertNotIn("finance", encoded.decode().lower())
        self.assertNotIn("KeepAlive", decoded)


if __name__ == "__main__":
    unittest.main()
