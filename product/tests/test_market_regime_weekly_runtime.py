from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
import sys
from pathlib import Path
import tempfile
import unittest


PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT))

from data_core.market_regime_weekly_asset_analysis import (  # noqa: E402
    build_asset_analysis_request,
)
from data_core.market_regime_weekly_contract import build_weekly_candle_responses  # noqa: E402
from data_core.market_regime_weekly_ranking import build_ranking_request  # noqa: E402
from data_core.market_regime_weekly_report import build_weekly_report  # noqa: E402
from data_core.market_regime_weekly_runtime import (  # noqa: E402
    WeeklyRuntimeError,
    WeeklyMacroRuntime,
    WeeklyReportStore,
)
from data_core.market_regime_weekly_snapshots import SNAPSHOT_SCHEMA_VERSION  # noqa: E402
from data_core.market_regime_weekly_source import (  # noqa: E402
    CANONICAL_REGISTRY,
    CONTEXT_4H_KEYS,
    WEEKLY_KEYS,
)


def source_fixture(*, data_kind: str = "fixture") -> dict:
    series = {}
    for index, key in enumerate(WEEKLY_KEYS):
        registry = CANONICAL_REGISTRY[key]
        is_rate = registry["series_kind"] in {"rate_level", "spread"}
        weekly = (
            [{"date": "2026-08-14", "value": 4.2 + index / 100}]
            if is_rate
            else [{"date": "2026-08-14", "open": 100 + index, "high": 101 + index, "low": 99 + index, "close": 100.5 + index}]
        )
        daily = (
            [{"date": "2026-08-14", "value": 4.2 + index / 100}]
            if is_rate
            else [{"date": "2026-08-14", "open": 100 + index, "high": 101 + index, "low": 99 + index, "close": 100.5 + index}]
        )
        item = {
            "key": key,
            **registry,
            "status": "complete",
            "weekly_bin_count": 1,
            "points": weekly,
            "daily_points": daily,
            "quality": "fresh",
            "data_kind": data_kind,
            "source_identity": {"provider": "fixture", "key": key},
            "context_4h": {"status": "complete", "points": [{"start_at": "2026-08-14T00:00:00Z", "open": 100 + index, "high": 101 + index, "low": 99 + index, "close": 100.5 + index, "duration_hours": 4}]}
            if key in CONTEXT_4H_KEYS
            else None,
        }
        series[key] = item
    return {
        "schema_version": "market-regime-weekly-source-history-v1",
        "registry_version": "market-regime-weekly-registry-v1",
        "week_end": "2026-08-14",
        "cutoff_at": "2026-08-14T23:59:59Z",
        "status": "complete",
        "missing_series": [],
        "data_kind": data_kind,
        "quality": "fresh",
        "series": series,
    }


def asset_output(request: dict) -> dict:
    key = request["asset_key"]
    frames = request["timeframes"]
    first = {tf: values["evidence_ids"][0] for tf, values in frames.items()}
    mechanism_id = request["mechanism"]["mechanism_ids"][0]
    result = {
        "asset_key": key,
        "generation_status": "model_generated_unreviewed",
        "weekly": {"text": "周线真实分析", "evidence_ids": [first["weekly"]]},
        "daily": {"text": "日线真实分析", "evidence_ids": [first["daily"]]},
        "synthesis": {"text": "多周期结论", "evidence_ids": [first["weekly"]]},
        "agreement": "mixed",
        "confirmation": {"text": "确认条件", "evidence_ids": [first["weekly"]]},
        "invalidation": {"text": "失效条件", "evidence_ids": [first["daily"]]},
        "opportunity_state": "wait",
        "rationale": {"text": "依据", "evidence_ids": [first["weekly"]]},
        "theoretical_implication": {"text": "通常由宏观驱动与风险偏好共同影响；但该传导并非始终稳定。", "evidence_ids": [mechanism_id], "claim_type": "theoretical_mechanism"},
    }
    if "four_hour" in frames:
        result["four_hour"] = {"text": "4小时分析", "evidence_ids": [first["four_hour"]]}
    return result


def ranking_output(request: dict) -> dict:
    rows = []
    rank = 0
    for slot in request["slots"]:
        if slot["status"] == "analysis_unavailable":
            rows.append({"asset_key": slot["asset_key"], "status": "unavailable", "rank": None, "text": "数据不可用", "evidence_ids": []})
            continue
        rank += 1
        rows.append({"asset_key": slot["asset_key"], "status": "wait", "rank": rank, "text": "等待确认", "evidence_ids": [slot["analysis_id"]]})
    return {"generation_status": "model_generated_unreviewed", "important_changes": [], "ordered_assets": rows}


def snapshot_stub(report: dict, runtime_root: Path, output_root: Path) -> dict:
    """Write tiny immutable stand-ins for runtime contract tests."""
    def digest(value: object) -> str:
        return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    result = {}
    for slot in report["chart_slots"]:
        slot_id = slot["slot_id"]
        token = digest({"slot_id": slot_id, "report": report["report_id"]})
        snapshot_id = f"market-regime-weekly-chart-snapshot:{token}"
        asset = {"path": f"snapshots/{token}.png", "sha256": hashlib.sha256(slot_id.encode()).hexdigest()}
        asset_path = output_root / asset["path"]
        asset_path.parent.mkdir(parents=True, exist_ok=True)
        asset_path.write_bytes(slot_id.encode())
        asset["sha256"] = hashlib.sha256(asset_path.read_bytes()).hexdigest()
        unsigned = {"schema_version": SNAPSHOT_SCHEMA_VERSION, "snapshot_id": snapshot_id, "asset": asset}
        receipt = {**unsigned, "receipt_hash": digest(unsigned)}
        receipt_path = runtime_root / "chart_snapshots" / "receipts" / f"{token}.json"
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_bytes = (json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
        receipt_path.write_bytes(receipt_bytes)
        result[slot_id] = {
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "snapshot_id": snapshot_id,
            "asset": asset,
            "receipt": {"path": str(receipt_path.relative_to(runtime_root)), "sha256": hashlib.sha256(receipt_bytes).hexdigest()},
        }
    return result


class WeeklyMacroRuntimeTest(unittest.TestCase):
    def test_one_shot_runs_all_stages_and_publishes_reader_artifacts(self) -> None:
        phases: list[str] = []
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime = WeeklyMacroRuntime(
                source_loader=lambda **_: source_fixture(data_kind="real"),
                asset_provider=lambda request: asset_output(request),
                ranking_provider=lambda request: ranking_output(request),
                runtime_root=root / "runtime",
                output_root=root / "output",
                allow_fixture=True,
                phase_observer=phases.append,
                chart_snapshot_port=lambda **kwargs: snapshot_stub(kwargs["report"], root / "runtime", root / "output"),
            )
            result = runtime.run_once(now=datetime(2026, 8, 17, 0, 20, tzinfo=timezone.utc))
            report = result["report"]
            self.assertEqual(report["week_end"], "2026-08-14")
            self.assertEqual(len(report["cards"]), 17)
            self.assertEqual(len(report["chart_slots"]), 39)
            responses = build_weekly_candle_responses(result["source"])
            self.assertEqual(len(responses), 39)
            self.assertEqual(responses["gold:weekly"]["status"], "ready")
            gold_analysis = result["analyses"]["gold"]
            self.assertTrue(any(str(item).startswith("feature:") for item in gold_analysis["position"]["evidence_ids"]))
            self.assertTrue(any(str(item).startswith("candle-response:") for item in gold_analysis["weekly"]["evidence_ids"]))
            self.assertEqual(len(result["candle_responses"]), 39)
            self.assertEqual(phases, ["source", "asset_analysis", "ranking", "report", "publish"])
            replayed = WeeklyReportStore(root / "runtime", root / "output").latest()
            self.assertEqual(replayed["report_id"], report["report_id"])
            self.assertTrue((root / "output" / "latest.html").is_file())
            self.assertTrue((root / "output" / "latest.md").is_file())

    def test_one_asset_failure_is_typed_and_does_not_block_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            def provider(request: dict) -> dict:
                if request["asset_key"] == "gold":
                    raise RuntimeError("provider detail must not leak")
                return asset_output(request)

            runtime = WeeklyMacroRuntime(
                source_loader=lambda **_: source_fixture(),
                asset_provider=provider,
                ranking_provider=lambda request: ranking_output(request),
                runtime_root=Path(temporary) / "runtime",
                output_root=Path(temporary) / "output",
                allow_fixture=True,
            )
            report = runtime.run_once(now=datetime(2026, 8, 17, tzinfo=timezone.utc))["report"]
            gold = next(card for card in report["cards"] if card["asset_key"] == "gold")
            self.assertEqual(gold["analysis_status"], "analysis_unavailable")
            self.assertEqual(len(report["chart_slots"]), 39)

    def test_one_stale_candle_response_is_typed_and_does_not_block_other_assets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = source_fixture(data_kind="real")
            source["series"]["gold"]["quality"] = "stale"
            runtime = WeeklyMacroRuntime(
                source_loader=lambda **_: source,
                asset_provider=lambda request: asset_output(request),
                ranking_provider=lambda request: ranking_output(request),
                runtime_root=Path(temporary) / "runtime",
                output_root=Path(temporary) / "output",
                chart_snapshot_port=lambda **kwargs: snapshot_stub(kwargs["report"], Path(temporary) / "runtime", Path(temporary) / "output"),
            )
            result = runtime.run_once(now=datetime(2026, 8, 17, tzinfo=timezone.utc))
            self.assertEqual(result["candle_responses"]["gold:weekly"]["status"], "unavailable")
            self.assertEqual(next(card for card in result["report"]["cards"] if card["asset_key"] == "gold")["analysis_status"], "analysis_unavailable")
            self.assertEqual(next(card for card in result["report"]["cards"] if card["asset_key"] == "sp500")["analysis_status"], "validated")

    def test_real_run_without_snapshot_port_fails_before_report_publish(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime = WeeklyMacroRuntime(
                source_loader=lambda **_: source_fixture(data_kind="real"),
                asset_provider=lambda request: asset_output(request),
                ranking_provider=lambda request: ranking_output(request),
                runtime_root=root / "runtime",
                output_root=root / "output",
            )
            with self.assertRaisesRegex(WeeklyRuntimeError, "chart_snapshot_port_unavailable"):
                runtime.run_once(now=datetime(2026, 8, 17, tzinfo=timezone.utc))
            self.assertFalse((root / "runtime" / "latest.json").exists())

    def test_malformed_feature_for_one_asset_is_typed_and_does_not_abort_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = source_fixture()
            source["series"]["gold"]["source_identity"] = {"run_id": None}
            runtime = WeeklyMacroRuntime(
                source_loader=lambda **_: source,
                asset_provider=lambda request: asset_output(request),
                ranking_provider=lambda request: ranking_output(request),
                runtime_root=Path(temporary) / "runtime",
                output_root=Path(temporary) / "output",
                allow_fixture=True,
            )
            result = runtime.run_once(now=datetime(2026, 8, 17, tzinfo=timezone.utc))
            self.assertEqual(result["analyses"]["gold"]["generation_status"], "analysis_unavailable")
            self.assertEqual(result["analyses"]["gold"]["failure_code"], "source_feature_invalid")
            self.assertEqual(len(result["report"]["chart_slots"]), 39)

    def test_fixture_source_is_rejected_in_real_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            runtime = WeeklyMacroRuntime(
                source_loader=lambda **_: source_fixture(data_kind="fixture"),
                asset_provider=lambda request: asset_output(request),
                ranking_provider=lambda request: ranking_output(request),
                runtime_root=Path(temporary) / "runtime",
                output_root=Path(temporary) / "output",
            )
            with self.assertRaisesRegex(WeeklyRuntimeError, "fixture_source_not_publishable"):
                runtime.run_once(now=datetime(2026, 8, 17, tzinfo=timezone.utc))


if __name__ == "__main__":
    unittest.main()
