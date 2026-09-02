from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import plistlib
import sys
import tempfile
import unittest
from unittest.mock import patch


PRODUCT = Path(__file__).resolve().parents[1]
ROOT = PRODUCT.parent
sys.path.insert(0, str(PRODUCT))
sys.path.insert(0, str(ROOT / "scripts"))

from data_core.market_regime_daily_evidence import MarketRegimeDailyEvidenceStore  # noqa: E402
from data_core.market_regime_daily_narrative import (  # noqa: E402
    MarketRegimeDailyNarrativeError,
    MarketRegimeDailyNarrativeStore,
    build_narrative_request,
    validate_model_output,
)
from data_core.market_regime_kline_newsletter import (  # noqa: E402
    BTC_QUERY1_URL,
    BTC_SPEC,
    BTC_URL,
    BITCOIN_SCHEMA_VERSION,
    DISPLAY_ORDER,
    BitcoinDailyStore,
    KlineNewsletterError,
    KlineNewsletterStore,
    PilotDeepSeekNarrativeProvider,
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
    def __init__(self, *, bad_symbol: bool = False, count: int = 540) -> None:
        self.bad_symbol = bad_symbol
        self.count = count

    def __call__(self, url: str) -> HttpCapture:
        symbol = "ETH-USD" if self.bad_symbol else "BTC-USD"
        body = yahoo_body(symbol, count=self.count, timezone_name="UTC")
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
    def test_bitcoin_instrument_identity_is_frozen(self) -> None:
        identity_bytes = json.dumps(
            asdict(BTC_SPEC),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        self.assertEqual(
            sha256(identity_bytes).hexdigest(),
            "eb666b661fe57f9344a076d2f503b53cb59c70ef7cd5e05851ccf39ab580fb5d",
        )

    def test_pilot_provider_retries_only_invalid_identical_frozen_requests(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            daily_root, macro_root = base / "daily", base / "macro"
            fixture_inputs(daily_root, macro_root)
            store = MarketRegimeDailyEvidenceStore(
                daily_root, macro_root, base / "evidence"
            )
            pack = store.compile_latest()
            request = build_narrative_request(pack)
            valid = valid_output(pack)
            invalid = json.loads(json.dumps(valid))
            invalid["posture_evidence_ids"] = []
            provider = PilotDeepSeekNarrativeProvider(base / "unused-key")
            receipt = {"request_id": "safe", "finish_reason": "stop"}

            with patch(
                "deepseek_writer.call_structured_deepseek",
                side_effect=[(invalid, receipt), (valid, receipt)],
            ) as mocked:
                output, _ = provider.generate(request)
            self.assertEqual(output, valid)
            self.assertEqual(mocked.call_count, 2)
            self.assertEqual(
                mocked.call_args_list[0].kwargs["request_object"],
                mocked.call_args_list[1].kwargs["request_object"],
            )
            self.assertEqual(mocked.call_args_list[0].kwargs["request_object"], request)

            with patch(
                "deepseek_writer.call_structured_deepseek",
                return_value=(valid, receipt),
            ) as mocked:
                output, _ = provider.generate(request)
            self.assertEqual(output, valid)
            self.assertEqual(mocked.call_count, 1)

            with patch(
                "deepseek_writer.call_structured_deepseek",
                return_value=(invalid, receipt),
            ) as mocked:
                output, _ = provider.generate(request)
            self.assertEqual(mocked.call_count, 3)
            with self.assertRaises(MarketRegimeDailyNarrativeError):
                validate_model_output(output, pack)

    def test_bitcoin_freezes_completed_daily_bars_and_rejects_wrong_symbol(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = BitcoinDailyStore(root, http_get=BitcoinTransport())
            artifact = store.refresh(
                now=datetime(2026, 8, 7, 1, 0, tzinfo=timezone.utc)
            )
            self.assertEqual(artifact["schema_version"], BITCOIN_SCHEMA_VERSION)
            self.assertEqual(artifact["instrument"]["key"], "bitcoin")
            self.assertGreaterEqual(artifact["bar_count"], 520)
            self.assertEqual(
                artifact["last_completed_session"], artifact["bars"][-1]["date"]
            )
            self.assertEqual(artifact["change_5d_unit"], "percent_return")
            self.assertEqual(store.latest()["bitcoin_id"], artifact["bitcoin_id"])
            self.assertEqual(artifact["data_kind"], "fixture")
        with tempfile.TemporaryDirectory() as temporary:
            store = BitcoinDailyStore(
                Path(temporary), http_get=BitcoinTransport(bad_symbol=True)
            )
            with self.assertRaisesRegex(KlineNewsletterError, "all_same_day_sources_rejected"):
                store.refresh(now=datetime(2026, 8, 7, 1, 0, tzinfo=timezone.utc))

    def test_bitcoin_primary_rejection_uses_same_day_alternate_endpoint(self) -> None:
        primary = HttpCapture(
            "GET",
            BTC_URL,
            BTC_URL,
            429,
            (("content-type", "text/html"),),
            (),
            (BTC_URL,),
            b"<html>rate limited</html>",
            "2026-08-07T01:00:00Z",
        )
        alternate = BitcoinTransport()(BTC_QUERY1_URL)

        class FallbackTransport:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def __call__(self, url: str) -> HttpCapture:
                self.calls.append(url)
                return primary if url == BTC_URL else alternate

        transport = FallbackTransport()
        with tempfile.TemporaryDirectory() as temporary:
            artifact = BitcoinDailyStore(temporary, http_get=transport).refresh(
                now=datetime(2026, 8, 7, 1, 0, tzinfo=timezone.utc)
            )
            self.assertEqual(artifact["source_identity"]["selected_endpoint"], "query1")
            self.assertEqual(
                [item["accepted"] for item in artifact["source_identity"]["source_attempts"]],
                [False, True],
            )
            self.assertEqual(transport.calls, [BTC_URL, BTC_QUERY1_URL])

    def test_short_bitcoin_refresh_never_advances_latest_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            accepted_store = BitcoinDailyStore(root, http_get=BitcoinTransport())
            accepted = accepted_store.refresh(
                now=datetime(2026, 8, 7, 1, 0, tzinfo=timezone.utc)
            )
            pointer = root / "latest.json"
            pointer_before = pointer.read_bytes()
            short_store = BitcoinDailyStore(
                root,
                http_get=BitcoinTransport(count=519),
            )
            with self.assertRaisesRegex(
                KlineNewsletterError,
                "bitcoin_all_same_day_sources_rejected",
            ):
                short_store.refresh(
                    now=datetime(2026, 8, 7, 2, 0, tzinfo=timezone.utc)
                )
            self.assertEqual(pointer.read_bytes(), pointer_before)
            self.assertEqual(
                accepted_store.latest()["bitcoin_id"], accepted["bitcoin_id"]
            )

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
            feishu_env_file=Path("/secrets/daily-feishu.env"),
            python=Path("/usr/bin/python3"),
        )
        encoded = plistlib.dumps(payload)
        decoded = plistlib.loads(encoded)
        self.assertEqual(decoded["Label"], LABEL)
        self.assertEqual(decoded["StartCalendarInterval"], {"Hour": 8, "Minute": 20})
        self.assertFalse(decoded["RunAtLoad"])
        self.assertTrue(any("run_market_regime_daily_delivery.py" in value for value in decoded["ProgramArguments"]))
        self.assertIn("--feishu-env-file", decoded["ProgramArguments"])
        self.assertNotIn("finance", encoded.decode().lower())
        self.assertNotIn("KeepAlive", decoded)


if __name__ == "__main__":
    unittest.main()
