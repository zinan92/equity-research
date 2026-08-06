from __future__ import annotations

from dataclasses import asdict
from datetime import date, timedelta
from hashlib import sha256
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest


PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT))

from data_core.market_regime_data import INSTRUMENTS, SCHEMA_VERSION as DATA_SCHEMA_VERSION  # noqa: E402
from data_core.market_regime_model import (  # noqa: E402
    ANALYSIS_SCHEMA_VERSION,
    DimensionResult,
    MODEL_VERSION,
    MarketRegimeAnalysisStore,
    MarketRegimeModelError,
    build_asset_feature,
    compile_market_regime,
    compile_scenario,
)


BASE_RATES = {item.key: 0.0 for item in INSTRUMENTS}
RISK_ON_RATES = {
    **BASE_RATES,
    "sp500": 0.006,
    "nasdaq": 0.010,
    "shanghai": 0.003,
    "star50": 0.006,
    "kospi": 0.004,
    "nikkei": 0.003,
    "wti": 0.002,
    "gold": -0.002,
    "silver": -0.001,
    "vix": -0.008,
    "china_dividend": 0.001,
    "us_dividend": 0.0015,
}
RISK_OFF_RATES = {
    **BASE_RATES,
    "sp500": -0.006,
    "nasdaq": -0.010,
    "shanghai": -0.004,
    "star50": -0.008,
    "kospi": -0.006,
    "nikkei": -0.005,
    "wti": -0.003,
    "gold": 0.007,
    "silver": 0.008,
    "vix": 0.010,
    "china_dividend": -0.001,
    "us_dividend": -0.0015,
}


def bars(rate: float, *, count: int = 140) -> list[dict]:
    start = date(2026, 3, 19)
    values = []
    previous = 100.0
    for index in range(count):
        close = previous * (1 + rate)
        open_price = previous
        values.append(
            {
                "date": (start + timedelta(days=index)).isoformat(),
                "open": open_price,
                "high": max(open_price, close) * 1.002,
                "low": min(open_price, close) * 0.998,
                "close": close,
                "volume": 1_000_000 + index,
            }
        )
        previous = close
    return values


def snapshot_for(
    rates: dict[str, float],
    *,
    missing: set[str] | None = None,
    close_overrides: dict[str, str] | None = None,
    name: str = "fixture",
) -> dict:
    missing = missing or set()
    close_overrides = close_overrides or {}
    items = []
    for spec in INSTRUMENTS:
        if spec.key in missing:
            continue
        rows = bars(rates[spec.key])
        artifact_hash = sha256(f"{name}:{spec.key}".encode()).hexdigest()
        items.append(
            {
                "schema_version": DATA_SCHEMA_VERSION,
                "instrument": asdict(spec),
                "bars": rows,
                "bar_count": len(rows),
                "last_completed_session": rows[-1]["date"],
                "last_completed_close_at": close_overrides.get(spec.key, "2026-08-05T20:00:00Z"),
                "quality": "fresh",
                "run_id": f"run-{name}",
                "generated_at": "2026-08-06T06:00:00Z",
                "source": {"raw_sha256": sha256(f"raw:{name}:{spec.key}".encode()).hexdigest()},
                "license": {"license_status": "local_evaluation_only", "verified_for_publication": False},
                "data_kind": "fixture",
                "publication_eligible": False,
                "normalized_artifact": {
                    "path": f"normalized/run-{name}/{spec.key}.json",
                    "sha256": artifact_hash,
                    "schema_version": DATA_SCHEMA_VERSION,
                },
            }
        )
    return {
        "schema_version": DATA_SCHEMA_VERSION,
        "run_id": f"run-{name}",
        "generated_at": "2026-08-06T06:00:00Z",
        "quality": "fresh" if not missing else "partial",
        "instrument_count": len(items),
        "instruments": items,
        "analysis_status": "not_computed",
    }


def persist_snapshot(root: Path, snapshot: dict) -> None:
    for item in snapshot["instruments"]:
        reference = item["normalized_artifact"]
        frozen = {key: value for key, value in item.items() if key != "normalized_artifact"}
        encoded = (json.dumps(frozen, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
        reference["sha256"] = sha256(encoded).hexdigest()
        path = root / reference["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(encoded)
    (root / "latest.json").write_text(
        json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


class MarketRegimeModelTest(unittest.TestCase):
    def test_asset_feature_contract_is_bounded_and_evidence_bound(self) -> None:
        item = snapshot_for(RISK_ON_RATES)["instruments"][0]
        feature = build_asset_feature(item)
        self.assertEqual(feature["key"], "sp500")
        self.assertGreater(feature["trend_score"], 35)
        self.assertEqual(set(feature["returns"]), {"1d", "5d", "20d", "60d"})
        self.assertIn("20d_annualized_pct", feature["realized_volatility"])
        self.assertEqual(feature["normalized_artifact_sha256"], item["normalized_artifact"]["sha256"])

    def test_non_positive_continuous_future_close_is_explicitly_rejected(self) -> None:
        item = next(
            row
            for row in snapshot_for(BASE_RATES)["instruments"]
            if row["instrument"]["key"] == "wti"
        )
        item["bars"][-2]["close"] = -1.0
        with self.assertRaisesRegex(MarketRegimeModelError, "non-positive close"):
            build_asset_feature(item)

    def test_risk_on_fixture_is_offensive_technology_led_and_us_led(self) -> None:
        result = compile_market_regime(snapshot_for(RISK_ON_RATES, name="risk-on"))
        dimensions = result["dimensions"]
        self.assertEqual(result["status"], "full")
        self.assertEqual(dimensions["risk"]["label"], "risk_on")
        self.assertEqual(dimensions["posture"]["label"], "offense")
        self.assertIn(dimensions["style"]["label"], {"technology", "leaning_technology"})
        self.assertEqual(dimensions["leadership"]["leader"], "us_equities")
        self.assertEqual(result["scenario"]["code"], "growth_led_risk_on")

    def test_risk_off_fixture_is_defensive_dividend_and_precious_metals_led(self) -> None:
        result = compile_market_regime(snapshot_for(RISK_OFF_RATES, name="risk-off"))
        dimensions = result["dimensions"]
        self.assertEqual(dimensions["risk"]["label"], "risk_off")
        self.assertEqual(dimensions["posture"]["label"], "defense")
        self.assertIn(dimensions["style"]["label"], {"dividend", "leaning_dividend"})
        self.assertEqual(dimensions["leadership"]["leader"], "precious_metals")

    def test_positive_risk_with_defensive_dividend_rotation_is_not_growth_led(self) -> None:
        rates = {
            **RISK_ON_RATES,
            "nasdaq": 0.006,
            "star50": -0.005,
            "gold": 0.007,
            "china_dividend": 0.006,
            "us_dividend": 0.006,
        }
        result = compile_market_regime(snapshot_for(rates, name="risk-on-defense"))
        dimensions = result["dimensions"]
        self.assertGreater(dimensions["risk"]["score"], 15)
        self.assertLess(dimensions["posture"]["score"], 0)
        self.assertLess(dimensions["style"]["score"], -7)
        self.assertEqual(result["scenario"]["code"], "cross_asset_rotation")
        self.assertTrue(
            any(
                item["instrument"] == "nasdaq"
                for item in dimensions["posture"]["contradictions"]
            )
        )
        self.assertFalse(
            any(
                item["instrument"] == "star50"
                for item in dimensions["posture"]["contradictions"]
            )
        )

    def test_balanced_posture_is_non_defensive_for_growth_scenario(self) -> None:
        features = {
            "wti": {"trend_score": 0.0, "returns": {"20d": 0.0}},
            "gold": {"trend_score": 0.0, "returns": {"20d": 0.0}},
            "vix": {"trend_score": -20.0, "returns": {"20d": 0.0}},
            "nasdaq": {"trend_score": 40.0, "returns": {"20d": 5.0}},
        }
        def dimension(score: float, label: str) -> DimensionResult:
            return DimensionResult(score, label, "full", {}, (), (), ())
        balanced = compile_scenario(
            features,
            dimension(20, "leaning_risk_on"),
            dimension(-1, "balanced"),
            dimension(10, "leaning_technology"),
        )
        defensive = compile_scenario(
            features,
            dimension(20, "leaning_risk_on"),
            dimension(-8, "leaning_defense"),
            dimension(10, "leaning_technology"),
        )
        self.assertEqual(balanced["code"], "growth_led_risk_on")
        self.assertEqual(defensive["code"], "cross_asset_rotation")

    def test_mixed_fixture_does_not_force_a_leader(self) -> None:
        result = compile_market_regime(snapshot_for(BASE_RATES, name="mixed"))
        self.assertEqual(result["dimensions"]["risk"]["label"], "mixed")
        self.assertEqual(result["dimensions"]["posture"]["label"], "balanced")
        self.assertEqual(result["dimensions"]["style"]["label"], "style_balanced")
        self.assertEqual(result["dimensions"]["leadership"]["state"], "none")
        self.assertIsNone(result["dimensions"]["leadership"]["leader"])
        self.assertIn("当前本就处于多空混合", result["what_is_going_on"]["invalidation"])

    def test_missing_leadership_group_keeps_ranking_but_crowns_no_winner(self) -> None:
        result = compile_market_regime(
            snapshot_for(RISK_ON_RATES, missing={"silver"}, name="missing-silver")
        )
        leadership = result["dimensions"]["leadership"]
        self.assertEqual(leadership["status"], "partial")
        self.assertEqual(leadership["state"], "unknown")
        self.assertIsNone(leadership["leader"])
        self.assertEqual(leadership["missing_groups"], ["precious_metals"])
        self.assertGreaterEqual(len(leadership["ranking"]), 4)

    def test_missing_vix_only_blocks_risk_dimension_and_marks_overall_partial(self) -> None:
        result = compile_market_regime(
            snapshot_for(RISK_ON_RATES, missing={"vix"}, name="missing-vix")
        )
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["dimensions"]["risk"]["label"], "unknown")
        self.assertEqual(result["dimensions"]["risk"]["missing"], ["vix"])
        self.assertNotEqual(result["dimensions"]["posture"]["label"], "unknown")
        self.assertEqual(result["scenario"]["status"], "unknown")
        self.assertIn("risk", result["scenario"]["missing"])
        self.assertIn("vix", result["scenario"]["missing"])
        self.assertNotIn("暂未出现", result["what_is_going_on"]["divergence"])
        self.assertIn("先补齐 Risk 关键依赖", result["what_is_going_on"]["invalidation"])
        neutral = compile_market_regime(
            snapshot_for(BASE_RATES, missing={"vix"}, name="missing-vix-neutral")
        )
        self.assertIn("关键维度证据尚不完整", neutral["what_is_going_on"]["divergence"])

    def test_missing_dividend_proxy_only_blocks_style_and_degrades_posture(self) -> None:
        result = compile_market_regime(
            snapshot_for(RISK_ON_RATES, missing={"china_dividend"}, name="missing-dividend")
        )
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["dimensions"]["style"]["label"], "unknown")
        self.assertEqual(result["dimensions"]["style"]["missing"], ["china_dividend"])
        self.assertEqual(result["dimensions"]["posture"]["status"], "partial")
        self.assertNotEqual(result["dimensions"]["risk"]["label"], "unknown")
        self.assertEqual(result["scenario"]["status"], "unknown")
        self.assertIn("style", result["scenario"]["missing"])

    def test_oil_gold_up_with_risk_off_is_supply_shock_not_risk_on(self) -> None:
        rates = {**RISK_OFF_RATES, "wti": 0.012, "gold": 0.008}
        result = compile_market_regime(snapshot_for(rates, name="supply-shock"))
        self.assertEqual(result["scenario"]["code"], "supply_shock_risk_off")
        self.assertEqual(result["dimensions"]["risk"]["label"], "risk_off")
        self.assertEqual(result["dimensions"]["leadership"]["ranking"][0]["group"], "energy")
        self.assertEqual(result["dimensions"]["leadership"]["state"], "contested")

    def test_cross_market_close_skew_downgrades_otherwise_full_verdict(self) -> None:
        result = compile_market_regime(
            snapshot_for(
                RISK_ON_RATES,
                close_overrides={"nikkei": "2026-08-03T06:00:00Z"},
                name="skewed",
            )
        )
        self.assertGreater(result["cross_market_close_skew_hours"], 30)
        self.assertEqual(result["status"], "partial")

    def test_replay_is_byte_deterministic_and_truth_boundary_is_non_actionable(self) -> None:
        snapshot = snapshot_for(RISK_ON_RATES, name="replay")
        first = compile_market_regime(snapshot)
        second = compile_market_regime(snapshot)
        self.assertEqual(
            json.dumps(first, sort_keys=True, separators=(",", ":")),
            json.dumps(second, sort_keys=True, separators=(",", ":")),
        )
        self.assertEqual(first["schema_version"], ANALYSIS_SCHEMA_VERSION)
        self.assertEqual(first["model_version"], MODEL_VERSION)
        self.assertEqual(first["data_kind"], "fixture")
        self.assertEqual(first["truth_boundary"]["judgment_state"], "model_generated_unreviewed")
        self.assertFalse(first["truth_boundary"]["action_eligible"])
        self.assertFalse(first["truth_boundary"]["publication_eligible"])
        self.assertTrue(first["truth_boundary"]["not_investment_advice"])

    def test_analysis_identity_binds_snapshot_quality_and_generated_time(self) -> None:
        base = snapshot_for(RISK_ON_RATES, name="identity")
        changed_quality = json.loads(json.dumps(base))
        changed_quality["quality"] = "partial"
        changed_time = json.loads(json.dumps(base))
        changed_time["generated_at"] = "2026-08-06T07:00:00Z"
        identities = {
            compile_market_regime(snapshot)["analysis_id"]
            for snapshot in (base, changed_quality, changed_time)
        }
        self.assertEqual(len(identities), 3)

    def test_cli_propagates_fixture_and_truth_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            persist_snapshot(root, snapshot_for(RISK_ON_RATES, name="cli"))
            completed = subprocess.run(
                [sys.executable, str(PRODUCT.parent / "scripts" / "compile_market_regime.py"), "--root", str(root)],
                check=True,
                capture_output=True,
                text=True,
            )
            output = json.loads(completed.stdout)
            self.assertEqual(output["data_kind"], "fixture")
            self.assertEqual(output["truth_boundary"]["judgment_state"], "model_generated_unreviewed")
            self.assertFalse(output["truth_boundary"]["action_eligible"])

    def test_analysis_store_is_idempotent_and_does_not_mutate_normalized_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot = snapshot_for(RISK_ON_RATES, name="store")
            persist_snapshot(root, snapshot)
            before = {
                path.relative_to(root).as_posix(): sha256(path.read_bytes()).hexdigest()
                for path in root.glob("normalized/**/*.json")
            }
            store = MarketRegimeAnalysisStore(root)
            first = store.compile_latest()
            second = store.compile_latest()
            self.assertEqual(first, second)
            self.assertEqual(store.latest(), first)
            after = {
                path.relative_to(root).as_posix(): sha256(path.read_bytes()).hexdigest()
                for path in root.glob("normalized/**/*.json")
            }
            self.assertEqual(before, after)
            pointer = json.loads((root / "analysis" / "latest.json").read_text())
            artifact = root / pointer["artifact"]["path"]
            self.assertEqual(sha256(artifact.read_bytes()).hexdigest(), pointer["artifact"]["sha256"])
            artifact.write_bytes(artifact.read_bytes() + b" ")
            with self.assertRaisesRegex(MarketRegimeModelError, "hash mismatch"):
                store.latest()


if __name__ == "__main__":
    unittest.main()
