from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "product"))

from data_core.market_regime_data import HttpCapture  # noqa: E402
from probe_market_regime_intraday_sources import PROBES, collect_probe  # noqa: E402


NOW = datetime(2026, 8, 8, 7, 0, tzinfo=timezone.utc)


class FixedTransport:
    def __init__(self) -> None:
        self.urls: list[str] = []

    def __call__(self, url: str) -> HttpCapture:
        self.urls.append(url)
        key = next(key for key, expected in PROBES if expected == url)
        status = 429 if key == "yahoo_query2_es_m5" else 200
        body = (f'{{"probe":"{key}","marker":"complete-raw-{key}"}}').encode()
        content_type = "text/html" if status == 429 or key.startswith("tencent") else "application/json"
        return HttpCapture(
            method="GET",
            requested_url=url,
            final_url=url,
            status_code=status,
            response_headers=(("content-type", content_type), ("date", "Sat, 08 Aug 2026 07:00:00 GMT")),
            dropped_header_names=("set-cookie",),
            redirect_chain=(url,),
            body=body,
            fetched_at="2026-08-08T07:00:00Z",
            error="HTTPError: Too Many Requests" if status == 429 else None,
        )


class MarketRegimeIntradayProbeTest(unittest.TestCase):
    def test_committed_safe_projection_is_bounded_and_non_gating(self) -> None:
        path = ROOT / "evidence/market-regime-live-s0/source-probe-2026-08-08.json"
        receipt = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(receipt["probe_count"] if "probe_count" in receipt else len(receipt["probes"]), 4)
        self.assertFalse(receipt["publication_eligible"])
        self.assertFalse(receipt["action_eligible"])
        self.assertFalse(receipt["reliability_proven"])
        self.assertFalse(receipt["exchange_realtime_proven"])
        self.assertFalse(receipt["redistribution_rights_proven"])
        self.assertEqual([item["status_code"] for item in receipt["probes"]], [200, 200, 200, 429])
        for item in receipt["probes"]:
            self.assertTrue(str(item["raw_capture_locator"]).startswith("local-runtime:"))
            self.assertEqual(len(item["raw_sha256"]), 64)
            self.assertLessEqual(len(item["bounded_raw_excerpt"]), 160)
        self.assertNotIn("set-cookie", path.read_text(encoding="utf-8").lower())

    def test_probe_freezes_urls_preserves_full_raw_and_emits_only_safe_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            transport = FixedTransport()
            receipt = collect_probe(
                Path(directory),
                transport=transport,
                plain_transport=transport,
                clock=lambda: NOW,
                run_id="fixture-probe",
            )
            self.assertEqual(transport.urls, [url for _, url in PROBES])
            self.assertEqual(receipt["probe_count"], 4)
            self.assertFalse(receipt["publication_eligible"])
            self.assertFalse(receipt["action_eligible"])
            self.assertEqual(
                [item["status_code"] for item in receipt["probes"]],
                [200, 200, 200, 429],
            )
            for item in receipt["probes"]:
                relative = str(item["raw_capture_locator"]).removeprefix("local-runtime:")
                raw = Path(directory, relative).read_bytes()
                self.assertEqual(sha256(raw).hexdigest(), item["raw_sha256"])
                self.assertIn("complete-raw", raw.decode())
                self.assertNotIn("complete-raw", json.dumps({key: value for key, value in item.items() if key != "bounded_raw_excerpt"}))
                self.assertFalse(item["reliability_proven"])
                self.assertFalse(item["exchange_realtime_proven"])
                self.assertFalse(item["redistribution_rights_proven"])
            saved = json.loads(
                Path(directory, "intraday-probes/receipts/fixture-probe.json").read_text()
            )
            self.assertEqual(saved, receipt)
            claimed = saved.pop("receipt_sha256")
            encoded = (
                json.dumps(saved, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
            ).encode()
            self.assertEqual(claimed, sha256(encoded).hexdigest())

    def test_same_frozen_inputs_replay_to_same_receipt_identity(self) -> None:
        receipts = []
        for _ in range(2):
            with tempfile.TemporaryDirectory() as directory:
                receipts.append(
                    collect_probe(
                        Path(directory),
                        transport=FixedTransport(),
                        plain_transport=FixedTransport(),
                        clock=lambda: NOW,
                        run_id="fixture-probe",
                    )
                )
        self.assertEqual(receipts[0], receipts[1])


if __name__ == "__main__":
    unittest.main()
