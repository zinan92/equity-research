from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

PRODUCT = Path(__file__).resolve().parents[1]
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from data_core.e4_sell_side_evidence_batch import RuntimeRawAuthoritySink, run_sell_side_evidence_batch  # noqa: E402
from data_core.sell_side_archive import SellSideArchiveBatch, SellSideArchiveItem  # noqa: E402


def identity() -> dict:
    return {"schema_version": "ashare-security-master-v1", "data_kind": "real", "truth_boundary": {"identity_only": True}, "records": [{"ticker": f"{index:06d}.SZ"} for index in range(100)]}


class SellSideEvidenceBatchTest(unittest.TestCase):
    def _identity(self, root: Path, payload: dict | None = None) -> Path:
        path = root / "identity.json"
        path.write_text(json.dumps(payload or identity()), encoding="utf-8")
        return path

    def test_archives_real_pdf_and_preserves_input_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calls: list[tuple[str, int | None]] = []
            def sync(ticker: str, **kwargs):
                calls.append((ticker, kwargs.get("max_reports")))
                item = SellSideArchiveItem("r1", ticker, "报告", "券商", None, "2026-07-01T00:00:00Z", "买入", 20, "https://pdf.dfcfw.com/pdf/H3_r1_1.pdf", "archived_pdf", "a" * 64, "canonical://raw/r1")
                return SellSideArchiveBatch(ticker, (item,), (SimpleNamespace(publishable=True, attempts=()),), {})
            result = run_sell_side_evidence_batch(self._identity(root), root / "runtime", max_tickers=1, inter_ticker_delay_seconds=0, max_reports_per_ticker=1, sync=sync)
            row = result["receipt"]["tickers"][0]
            self.assertEqual(calls, [("000000.SZ", 1)])
            self.assertEqual(row["counts"], {"catalog_reports": 1, "archived_pdf": 1, "metadata_only": 0})
            self.assertFalse(result["receipt"]["truth_boundary"]["counts_as_tier_a_or_b"])

    def test_metadata_only_and_exception_are_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def sync(ticker: str, **_kwargs):
                if ticker == "000000.SZ":
                    raise TimeoutError("timeout")
                item = SellSideArchiveItem("r2", ticker, "报告", None, None, "2026-07-01T00:00:00Z", None, None, "https://pdf.dfcfw.com/pdf/H3_r2_1.pdf", "metadata_only", error="HTTPError")
                return SellSideArchiveBatch(ticker, (item,), (SimpleNamespace(publishable=True, attempts=()),), {})
            result = run_sell_side_evidence_batch(self._identity(root), root / "runtime", max_tickers=2, inter_ticker_delay_seconds=0, sync=sync)
            self.assertEqual(result["receipt"]["tickers"][0]["blockers"], ["sell_side_collector_exception"])
            self.assertEqual(result["receipt"]["tickers"][1]["blockers"], ["sell_side_pdf_unavailable_metadata_only"])
            self.assertEqual(result["receipt"]["counts"]["failed"], 1)

    def test_completed_receipt_is_reused_and_config_mismatch_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); calls: list[str] = []
            def sync(ticker: str, **_kwargs):
                calls.append(ticker)
                return SellSideArchiveBatch(ticker, (), (), {})
            source = self._identity(root)
            first = run_sell_side_evidence_batch(source, root / "runtime", max_tickers=1, inter_ticker_delay_seconds=0, sync=sync)
            second = run_sell_side_evidence_batch(source, root / "runtime", max_tickers=1, inter_ticker_delay_seconds=0, sync=sync)
            self.assertEqual(first["receipt"]["receipt_hash"], second["receipt"]["receipt_hash"])
            self.assertEqual(calls, ["000000.SZ"])
            with self.assertRaisesRegex(ValueError, "does not match"):
                run_sell_side_evidence_batch(source, root / "runtime", max_tickers=2, inter_ticker_delay_seconds=0, sync=sync)

    def test_rejects_non_real_identity_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); payload = identity(); payload["data_kind"] = "fixture"
            with self.assertRaisesRegex(ValueError, "real bounded"):
                run_sell_side_evidence_batch(self._identity(root, payload), root / "runtime", max_tickers=1, inter_ticker_delay_seconds=0)

    def test_runtime_sink_persists_hash_bound_bytes_and_rejects_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); body = b"%PDF-1.7\\nproof\\n%%EOF"; raw_hash = __import__("hashlib").sha256(body).hexdigest()
            sink = RuntimeRawAuthoritySink(root / "raw")
            sink.persist_attempt(SimpleNamespace(raw=SimpleNamespace(raw_hash=raw_hash), fetched=SimpleNamespace(body=body)))
            path = sink.path_for(raw_hash)
            self.assertEqual(Path(path).read_bytes(), body)
            with self.assertRaisesRegex(ValueError, "do not match"):
                sink.persist_attempt(SimpleNamespace(raw=SimpleNamespace(raw_hash="0" * 64), fetched=SimpleNamespace(body=body)))

    def test_metadata_only_row_never_exposes_runtime_raw_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def sync(ticker: str, **_kwargs):
                item = SellSideArchiveItem("r3", ticker, "报告", None, None, "2026-07-01T00:00:00Z", None, None, "https://pdf.dfcfw.com/pdf/H3_r3_1.pdf", "metadata_only", error="HTTPError")
                return SellSideArchiveBatch(ticker, (item,), (SimpleNamespace(publishable=True, attempts=()),), {})
            row = run_sell_side_evidence_batch(self._identity(root), root / "runtime", max_tickers=1, inter_ticker_delay_seconds=0, sync=sync)["receipt"]["tickers"][0]
            self.assertIsNone(row["reports"][0]["runtime_raw_path"])
