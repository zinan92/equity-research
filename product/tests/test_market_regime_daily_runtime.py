from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
import sys

PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT))

from data_core.market_regime_daily_runtime import DailyKlineRuntime, DailyRuntimeError  # noqa: E402
from data_core.market_regime_daily_thesis import DailyThesisDeliveryStore  # noqa: E402
from product.tests.test_market_regime_daily_analysis import _source_bundle  # noqa: E402
from product.tests.test_market_regime_daily_thesis import _analysis_bundle, _thesis_provider  # noqa: E402
from data_core.market_regime_daily_thesis import compile_daily_thesis  # noqa: E402


class DailyRuntimeTests(unittest.TestCase):
    def test_run_once_completes_with_injected_source_analysis_and_thesis(self) -> None:
        source = _source_bundle()
        analysis = _analysis_bundle()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = DailyKlineRuntime(
                runtime_root=root / "runtime",
                output_root=root / "output",
                archive_root=root / "archive",
                key_file=None,
                no_llm=True,
                no_snapshots=True,
                source_builder=lambda _client: source,
                analysis_builder=lambda _source: analysis,
                thesis_builder=lambda current_analysis: compile_daily_thesis(current_analysis, _thesis_provider),
            )
            result = runtime.run_once(now=datetime(2026, 8, 24, 16, 0, tzinfo=timezone.utc))
            self.assertEqual(result["state"], "completed")
            self.assertEqual(runtime.status()["state"], "completed")
            self.assertEqual(runtime.status()["report_date"], "2026-08-25")

    def test_status_is_idle_before_first_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            status = DailyKlineRuntime(runtime_root=Path(directory) / "runtime", output_root=Path(directory) / "output", archive_root=Path(directory) / "archive", key_file=None).status()
            self.assertEqual(status["state"], "idle")

    def test_failed_run_replaces_latest_with_unavailable_surface(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def fail(_client):
                raise RuntimeError("source_boom")
            runtime = DailyKlineRuntime(
                runtime_root=root / "runtime",
                output_root=root / "output",
                archive_root=root / "archive",
                key_file=None,
                no_llm=True,
                no_snapshots=True,
                source_builder=fail,
            )
            with self.assertRaises(DailyRuntimeError):
                runtime.run_once(now=datetime(2026, 8, 25, tzinfo=timezone.utc))
            self.assertIn("当前日报不可用", (root / "output" / "latest.md").read_text(encoding="utf-8"))
            status = runtime.status()
            self.assertEqual(status["state"], "failed")
            self.assertIsNone(status.get("source_bundle_id"))
            self.assertEqual(status["last_failure"]["phase"], "source_refresh")
            self.assertEqual(DailyThesisDeliveryStore(runtime_root=root / "runtime", output_root=root / "output", archive_root=root / "archive").latest()["state"], "unavailable")

    def test_runtime_budget_timeout_publishes_unavailable_surface(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = DailyKlineRuntime(
                runtime_root=root / "runtime",
                output_root=root / "output",
                archive_root=root / "archive",
                key_file=None,
                no_llm=True,
                no_snapshots=True,
                max_runtime_seconds=0,
            )
            with self.assertRaisesRegex(DailyRuntimeError, "runtime_timeout"):
                runtime.run_once(now=datetime(2026, 8, 25, tzinfo=timezone.utc))
            self.assertEqual(runtime.status()["last_failure"]["code"], "runtime_timeout")
            self.assertIn("当前日报不可用", (root / "output" / "latest.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()


# --- resume: skip the two expensive phases when the market data is unchanged ---

def _resume_runtime(tmp_path):
    from data_core.market_regime_daily_runtime import DailyKlineRuntime

    rt = DailyKlineRuntime.__new__(DailyKlineRuntime)
    rt.runtime_root = tmp_path
    return rt


def _write_resume_receipt(rt, **overrides):
    import json

    payload = {
        "schema_version": rt.RESUME_SCHEMA,
        "source_assets_sha256": "fp-1",
        "analysis_bundle_id": "market-regime-daily-analysis:abc",
        "thesis_id": "market-regime-daily-thesis:def",
        "thesis": {"thesis_id": "market-regime-daily-thesis:def",
                   "identity_core": {"analysis_bundle_id": "market-regime-daily-analysis:abc"}},
    }
    payload.update(overrides)
    (rt.runtime_root / "resume.json").write_text(json.dumps(payload), encoding="utf-8")


def test_resume_reuses_analysis_and_thesis_for_identical_source(tmp_path, monkeypatch):
    import data_core.market_regime_daily_runtime as mod

    rt = _resume_runtime(tmp_path)
    _write_resume_receipt(rt)
    monkeypatch.setattr(mod, "DailyAnalysisStore", lambda root: type("S", (), {
        "latest": staticmethod(lambda: {"bundle_id": "market-regime-daily-analysis:abc", "assets": []})})())

    got = rt._resume_candidate("fp-1")
    assert got is not None
    analysis, thesis = got
    assert analysis["bundle_id"] == "market-regime-daily-analysis:abc"
    assert thesis["thesis_id"] == "market-regime-daily-thesis:def"


def test_resume_fails_closed_on_every_mismatch(tmp_path, monkeypatch):
    """Anything unexpected must recompute, never publish yesterday's judgement."""
    import data_core.market_regime_daily_runtime as mod

    rt = _resume_runtime(tmp_path)
    ok_store = lambda root: type("S", (), {  # noqa: E731
        "latest": staticmethod(lambda: {"bundle_id": "market-regime-daily-analysis:abc"})})()
    monkeypatch.setattr(mod, "DailyAnalysisStore", ok_store)

    # no receipt at all
    assert rt._resume_candidate("fp-1") is None
    # empty fingerprint is never resumable
    _write_resume_receipt(rt)
    assert rt._resume_candidate("") is None
    # different trading session
    assert rt._resume_candidate("fp-2") is None
    # schema drift
    _write_resume_receipt(rt, schema_version="something-else")
    assert rt._resume_candidate("fp-1") is None
    # stored analysis moved on without the receipt
    _write_resume_receipt(rt, analysis_bundle_id="market-regime-daily-analysis:other")
    assert rt._resume_candidate("fp-1") is None
    # thesis not bound to that analysis bundle
    _write_resume_receipt(rt, thesis={"thesis_id": "t", "identity_core": {"analysis_bundle_id": "mismatch"}})
    assert rt._resume_candidate("fp-1") is None
    # unreadable analysis store
    _write_resume_receipt(rt)
    monkeypatch.setattr(mod, "DailyAnalysisStore", lambda root: type("S", (), {
        "latest": staticmethod(lambda: (_ for _ in ()).throw(RuntimeError("gone")))})())
    assert rt._resume_candidate("fp-1") is None


def test_resume_receipt_roundtrips(tmp_path, monkeypatch):
    import data_core.market_regime_daily_runtime as mod

    rt = _resume_runtime(tmp_path)
    analysis = {"bundle_id": "market-regime-daily-analysis:abc"}
    thesis = {"thesis_id": "market-regime-daily-thesis:def",
              "identity_core": {"analysis_bundle_id": "market-regime-daily-analysis:abc"}}
    rt._write_resume("fp-9", analysis, thesis, at="2026-09-21T01:00:00Z")
    monkeypatch.setattr(mod, "DailyAnalysisStore", lambda root: type("S", (), {
        "latest": staticmethod(lambda: analysis)})())
    assert rt._resume_candidate("fp-9") is not None
    # an empty fingerprint writes nothing rather than a receipt that matches everything
    rt2 = _resume_runtime(tmp_path / "other")
    rt2.runtime_root.mkdir()
    rt2._write_resume("", analysis, thesis, at="x")
    assert not (rt2.runtime_root / "resume.json").exists()


def test_source_fingerprint_is_the_data_digest_not_the_run_time():
    from data_core.market_regime_daily_runtime import DailyKlineRuntime

    fp = DailyKlineRuntime._source_fingerprint
    # generated_at differs between runs; assets_sha256 does not
    assert fp({"identity_core": {"assets_sha256": "d1", "generated_at": "t1"}}) == "d1"
    assert fp({"identity_core": {"assets_sha256": "d1", "generated_at": "t2"}}) == "d1"
    assert fp({}) == "" and fp({"identity_core": None}) == ""
