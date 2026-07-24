from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

PRODUCT = Path(__file__).resolve().parents[1]
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from data_core.e4_official_evidence_batch import load_real_identity_tickers, run_official_evidence_batch  # noqa: E402


def hung_then_failure_worker(ticker: str, _raw_root: str, _pages: int, result_queue) -> None:
    if ticker == "000000.SZ":
        time.sleep(2)
        return
    result_queue.put({"status": "ok", "row": {"ticker": ticker, "status": "failed", "data_kind": "real", "blockers": ["simulated_next_ticker"]}})


def identity_receipt() -> dict:
    return {
        "schema_version": "ashare-security-master-v1", "data_kind": "real",
        "truth_boundary": {"identity_only": True},
        "records": [{"ticker": f"{index:06d}.SZ"} for index in range(100)],
    }


def successful_batch(ticker: str):
    body = b"%PDF-1.7\nreal filing\n%%EOF"
    raw_hash = hashlib.sha256(body).hexdigest()
    raw = SimpleNamespace(raw_hash=raw_hash, source_url="https://static.cninfo.com.cn/finalpage/real.PDF", storage_uri=f"canonical-raw/raw/sha256/{raw_hash[:2]}/{raw_hash}", fetched_at="2026-07-24T00:00:00Z", known_at="2026-07-24T00:00:00Z")
    fetched = SimpleNamespace(body=body)
    attempt = SimpleNamespace(raw=raw, fetched=fetched)
    record = SimpleNamespace(payload={
        "document_id": "official-filing:cninfo:1", "document_type": "annual_report",
        "published_at": "2026-03-31T00:00:00Z",
    })
    outcome = SimpleNamespace(publishable=True, selected_source="cninfo_official_filing_document_v1", attempts=(attempt,), records=(record,))
    return SimpleNamespace(ticker=ticker, discovery=SimpleNamespace(publishable=True), documents={"1": outcome})


class OfficialEvidenceBatchTest(unittest.TestCase):
    def write_identity(self, root: Path, payload: dict | None = None) -> Path:
        path = root / "identity.json"
        path.write_text(json.dumps(payload or identity_receipt()), encoding="utf-8")
        return path

    def test_rejects_non_real_identity_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = identity_receipt()
            payload["data_kind"] = "fixture"
            with self.assertRaisesRegex(ValueError, "real bounded"):
                load_real_identity_tickers(self.write_identity(root, payload))

    def test_captures_once_then_resumes_without_duplicate_fetch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calls: list[str] = []
            def sync(ticker: str, **_kwargs):
                calls.append(ticker)
                return successful_batch(ticker)
            first = run_official_evidence_batch(self.write_identity(root), root / "runtime", max_tickers=1, inter_ticker_delay_seconds=0, sync=sync)
            row = first["receipt"]["tickers"][0]
            self.assertEqual((row["status"], row["report_model_hash"], row["tier"]), ("captured", None, None))
            self.assertEqual(row["fetched_at"], "2026-07-24T00:00:00Z")
            self.assertFalse(first["receipt"]["truth_boundary"]["counts_as_report_model_coverage"])
            self.assertEqual(first["receipt"]["max_discovery_pages"], 3)
            second = run_official_evidence_batch(self.write_identity(root), root / "runtime", max_tickers=1, inter_ticker_delay_seconds=0, sync=sync)
            self.assertEqual(second["receipt"]["tickers"][0]["status"], "skipped")
            self.assertEqual(calls, ["000000.SZ"])

    def test_failure_isolated_and_never_becomes_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def sync(ticker: str, **_kwargs):
                if ticker == "000000.SZ":
                    raise RuntimeError("network")
                return successful_batch(ticker)
            result = run_official_evidence_batch(self.write_identity(root), root / "runtime", max_tickers=2, inter_ticker_delay_seconds=0, sync=sync)
            self.assertEqual(result["receipt"]["counts"], {"requested": 2, "captured_official_primary": 1, "failed": 1, "resumed": 0})
            self.assertEqual(result["receipt"]["tickers"][0]["blockers"], ["collector_exception"])
            self.assertFalse(result["receipt"]["truth_boundary"]["counts_as_tier_a_or_b"])

    def test_hard_timeout_terminates_hung_child_and_continues(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            started = time.monotonic()
            result = run_official_evidence_batch(
                self.write_identity(root), root / "runtime", max_tickers=2,
                inter_ticker_delay_seconds=0, collector_timeout_seconds=0.5,
                isolated_worker=hung_then_failure_worker,
            )
            elapsed = time.monotonic() - started
            rows = result["receipt"]["tickers"]
            self.assertLess(elapsed, 2.5)
            self.assertEqual(rows[0]["blockers"], ["collector_timeout"])
            self.assertEqual(rows[1]["blockers"], ["simulated_next_ticker"])
            self.assertEqual(result["receipt"]["counts"]["captured_official_primary"], 0)

    def test_interrupted_batch_resumes_from_atomic_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calls: list[str] = []

            def interrupted_sync(ticker: str, **_kwargs):
                calls.append(ticker)
                if ticker == "000001.SZ":
                    raise KeyboardInterrupt()
                return successful_batch(ticker)

            with self.assertRaises(KeyboardInterrupt):
                run_official_evidence_batch(
                    self.write_identity(root), root / "runtime", max_tickers=3,
                    inter_ticker_delay_seconds=0, sync=interrupted_sync,
                )
            pointer = json.loads((root / "runtime" / "official-evidence-batch-latest.json").read_text())
            self.assertEqual(pointer["state"], "in_progress")

            resumed_calls: list[str] = []
            def resumed_sync(ticker: str, **_kwargs):
                resumed_calls.append(ticker)
                return successful_batch(ticker)

            result = run_official_evidence_batch(
                self.write_identity(root), root / "runtime", max_tickers=3,
                inter_ticker_delay_seconds=0, sync=resumed_sync,
            )
            self.assertEqual(calls, ["000000.SZ", "000001.SZ"])
            self.assertEqual(resumed_calls, ["000001.SZ", "000002.SZ"])
            self.assertEqual(result["receipt"]["counts"], {"requested": 3, "captured_official_primary": 3, "failed": 0, "resumed": 0})
            self.assertEqual(json.loads((root / "runtime" / "official-evidence-batch-latest.json").read_text())["state"], "completed")
            self.assertFalse((root / "runtime" / "official-evidence-batch-checkpoint.json").exists())

    def test_rejects_checkpoint_with_mismatched_corpus_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def interrupted_sync(ticker: str, **_kwargs):
                if ticker == "000001.SZ":
                    raise KeyboardInterrupt()
                return successful_batch(ticker)

            with self.assertRaises(KeyboardInterrupt):
                run_official_evidence_batch(
                    self.write_identity(root), root / "runtime", max_tickers=3,
                    inter_ticker_delay_seconds=0, sync=interrupted_sync,
                )
            with self.assertRaisesRegex(ValueError, "does not match"):
                run_official_evidence_batch(
                    self.write_identity(root), root / "runtime", max_tickers=2,
                    inter_ticker_delay_seconds=0, sync=lambda ticker, **_kwargs: successful_batch(ticker),
                )
