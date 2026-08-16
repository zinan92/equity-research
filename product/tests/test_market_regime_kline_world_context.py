from __future__ import annotations

from dataclasses import asdict
from datetime import date, timedelta
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


PRODUCT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(PRODUCT))

from data_core.market_regime_data import (  # noqa: E402
    INSTRUMENTS,
    SCHEMA_VERSION as DAILY_SCHEMA_VERSION,
)
from data_core.market_regime_daily_evidence import SLOT_KEYS  # noqa: E402
from data_core.market_regime_kline_world_context import (  # noqa: E402
    CONTEXT_ID_PREFIX,
    LOOKBACK,
    MAX_LLM_PROJECTION_BYTES,
    PAIR_REGISTRY,
    SERIES_ORDER,
    KlineWorldContextError,
    KlineWorldContextStore,
    build_kline_world_context,
    build_kline_world_context_from_roots,
    load_context_source_snapshots,
    validate_kline_world_context,
)
from data_core.market_regime_macro_data import MACRO_FACTOR_BY_KEY  # noqa: E402


END = date(2026, 8, 14)


def bars(*, offset: float, count: int = 130, missing_index: int | None = None) -> list[dict]:
    rows = []
    for index in range(count):
        if index == missing_index:
            continue
        value = offset + index * 0.25
        rows.append(
            {
                "date": (END - timedelta(days=count - index - 1)).isoformat(),
                "open": round(value - 0.1, 6),
                "high": round(value + 0.4, 6),
                "low": round(value - 0.4, 6),
                "close": round(value, 6),
                "volume": 1000 + index,
            }
        )
    return rows


def observations(*, offset: float, count: int = 130, step: float = 0.01) -> list[dict]:
    return [
        {
            "date": (END - timedelta(days=count - index - 1)).isoformat(),
            "value": round(offset + index * step, 6),
        }
        for index in range(count)
    ]


def inputs(*, data_kind: str = "fixture", short_key: str | None = None) -> tuple[dict, dict, dict, dict]:
    daily_items = []
    for index, spec in enumerate(INSTRUMENTS):
        item_bars = bars(offset=100 + index * 10, count=119 if short_key == spec.key else 130)
        daily_items.append(
            {
                "schema_version": DAILY_SCHEMA_VERSION,
                "instrument": asdict(spec),
                "bars": item_bars,
                "bar_count": len(item_bars),
                "last_completed_session": item_bars[-1]["date"],
                "last_completed_close_at": "2026-08-14T20:00:00Z",
                "quality": "fresh",
                "run_id": "daily-run",
                "data_kind": data_kind,
                "normalized_artifact": {"path": f"normalized/daily-run/{spec.key}.json", "sha256": f"{index + 1:064x}"},
                "publication_eligible": False,
            }
        )
    daily = {
        "schema_version": DAILY_SCHEMA_VERSION,
        "run_id": "daily-run",
        "quality": "fresh",
        "instruments": daily_items,
    }

    macro_items = []
    dxy_bars = bars(offset=95)
    for index, key in enumerate(MACRO_FACTOR_BY_KEY):
        spec = MACRO_FACTOR_BY_KEY[key]
        item = {
            "schema_version": "market-regime-macro-data-v1",
            "factor": asdict(spec),
            "last_completed_session": END.isoformat(),
            "last_completed_close_at": "2026-08-14T21:00:00Z",
            "quality": "fresh",
            "run_id": "macro-run",
            "factor_id": f"market-regime-macro-factor:{key}:{index + 1:064x}",
            "data_kind": data_kind,
            "artifact": {"path": f"normalized/macro-run/{key}.json", "sha256": f"{index + 20:064x}"},
            "publication_eligible": False,
            "action_eligible": False,
        }
        if key == "dxy":
            item["bars"] = dxy_bars
        elif key == "us2s10s":
            item["observations"] = observations(offset=40, step=1)
        else:
            item["observations"] = observations(offset=3.0 + index / 10, step=0.01)
        macro_items.append(item)
    macro = {
        "schema_version": "market-regime-macro-data-v1",
        "run_id": "macro-run",
        "quality": "fresh",
        "factors": macro_items,
        "publication_eligible": False,
        "action_eligible": False,
    }

    slots = []
    for index, key in enumerate(SLOT_KEYS):
        slots.append(
            {
                "key": key,
                "evidence_id": f"market-regime-daily-evidence-v1:{key}:{index + 50:064x}",
            }
        )
    pack = {
        "schema_version": "market-regime-daily-evidence-v1",
        "pack_id": "market-regime-daily-evidence:" + "a" * 64,
        "inputs": {"daily_run_id": "daily-run", "macro_run_id": "macro-run"},
        "slots": slots,
        "time": {
            "joint_judgment_time": "2026-08-14T06:30:00Z",
            "latest_evidence_time": "2026-08-14T21:00:00Z",
            "cross_market_close_skew_hours": 14.5,
        },
        "agreement_inputs": {
            "analysis_status": "full",
            "risk": {"label": "risk_on"},
            "posture": {"label": "leaning_defense"},
            "style": {"label": "dividend"},
            "leadership": {"leader": "precious_metals"},
        },
        "confidence_inputs": {"score": 0.84, "level": "high"},
        "contradiction_candidates": [],
    }

    bitcoin_bars = bars(offset=50000)
    bitcoin = {
        "schema_version": "market-regime-kline-bitcoin-v1",
        "instrument": {"key": "bitcoin", "display_name": "Bitcoin", "unit": "USD/coin"},
        "bars": bitcoin_bars,
        "bar_count": len(bitcoin_bars),
        "last_completed_session": bitcoin_bars[-1]["date"],
        "last_completed_close_at": "2026-08-14T23:59:00Z",
        "quality": "fresh",
        "data_kind": data_kind,
        "level_unit": "USD/coin",
        "publication_eligible": False,
        "action_eligible": False,
    }
    bitcoin_core = json.loads(json.dumps(bitcoin))
    bitcoin_digest = sha256(
        json.dumps(
            bitcoin_core, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    bitcoin = {
        "bitcoin_id": "market-regime-kline-bitcoin:" + bitcoin_digest,
        "identity_core": bitcoin_core,
        **bitcoin_core,
    }
    return daily, macro, pack, bitcoin


def context_fixture() -> dict:
    daily, macro, pack, bitcoin = inputs()
    return build_kline_world_context(
        daily=daily,
        macro=macro,
        pack=pack,
        bitcoin=bitcoin,
        allow_fixture=True,
    )


def canonical_bytes(value: dict) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode()


def write_bound_sources(base: Path) -> tuple[Path, Path, dict, dict]:
    daily, macro, pack, bitcoin = inputs(data_kind="real")
    daily_run = "market-regime-20260816T073524Z-95b305f4475d"
    macro_run = "market-regime-macro-20260816T073555Z-a066d77af206"
    daily["run_id"], macro["run_id"] = daily_run, macro_run
    pack["inputs"] = {"daily_run_id": daily_run, "macro_run_id": macro_run}
    slots = {item["key"]: item for item in pack["slots"]}
    daily_root, macro_root = base / "daily", base / "macro"
    for item in daily["instruments"]:
        key = item["instrument"]["key"]
        artifact = {name: value for name, value in item.items() if name != "normalized_artifact"}
        artifact["run_id"] = daily_run
        encoded = canonical_bytes(artifact)
        relative = Path("normalized") / daily_run / f"{key}.json"
        target = daily_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(encoded)
        slots[key]["source_identity"] = {
            "normalized_artifact_sha256": sha256(encoded).hexdigest()
        }
    for item in macro["factors"]:
        key = item["factor"]["key"]
        artifact = {name: value for name, value in item.items() if name != "artifact"}
        artifact["run_id"] = macro_run
        encoded = canonical_bytes(artifact)
        relative = Path("normalized") / macro_run / f"{key}.json"
        target = macro_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(encoded)
        slots[key]["source_identity"] = {
            "artifact_sha256": sha256(encoded).hexdigest(),
            "factor_id": artifact["factor_id"],
        }
    return daily_root, macro_root, pack, bitcoin


class KlineWorldContextTest(unittest.TestCase):
    def test_pack_bound_loader_ignores_moving_latest_and_rejects_tamper(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            daily_root, macro_root, pack, bitcoin = write_bound_sources(Path(temporary))
            (daily_root / "latest.json").write_text(
                json.dumps({"run_id": "market-regime-20260816T113550Z-4886477abcb3"}),
                encoding="utf-8",
            )
            daily, macro = load_context_source_snapshots(
                daily_root=daily_root, macro_root=macro_root, pack=pack
            )
            self.assertEqual(daily["run_id"], pack["inputs"]["daily_run_id"])
            self.assertEqual(macro["run_id"], pack["inputs"]["macro_run_id"])
            context = build_kline_world_context_from_roots(
                daily_root=daily_root,
                macro_root=macro_root,
                pack=pack,
                bitcoin=bitcoin,
            )
            self.assertEqual(context["data_kind"], "real")
            sp500 = daily_root / "normalized" / daily["run_id"] / "sp500.json"
            sp500.write_bytes(sp500.read_bytes() + b" ")
            with self.assertRaisesRegex(KlineWorldContextError, "source_artifact_hash_mismatch"):
                load_context_source_snapshots(
                    daily_root=daily_root, macro_root=macro_root, pack=pack
                )

    def test_context_freezes_exact_visible_universe_and_bounded_history(self) -> None:
        context = context_fixture()
        self.assertTrue(context["context_id"].startswith(CONTEXT_ID_PREFIX))
        self.assertEqual([item["key"] for item in context["series"]], list(SERIES_ORDER))
        self.assertEqual(len(context["series"]), 17)
        self.assertEqual(len(context["relationships"]), len(PAIR_REGISTRY))
        for item in context["series"]:
            self.assertEqual(len(item["points"]), LOOKBACK)
        roles = {item["key"]: item["role"] for item in context["series"]}
        self.assertEqual(roles["bitcoin"], "supplemental")
        self.assertTrue(all(roles[key] == "canonical" for key in SERIES_ORDER if key != "bitcoin"))
        self.assertEqual(validate_kline_world_context(context)["context_id"], context["context_id"])

    def test_rate_units_and_multi_horizon_features_are_not_price_returns(self) -> None:
        context = context_fixture()
        series = {item["key"]: item for item in context["series"]}
        self.assertEqual(series["us2y"]["level_unit"], "percent")
        self.assertEqual(series["us2y"]["change_unit"], "basis_points")
        self.assertAlmostEqual(series["us2y"]["features"]["change_5d_bp"], 5.0)
        self.assertEqual(series["us2s10s"]["level_unit"], "basis_points")
        self.assertAlmostEqual(series["us2s10s"]["features"]["change_5d_bp"], 5.0)
        self.assertIn("return_20d_pct", series["sp500"]["features"])
        self.assertNotIn("return_20d_pct", series["us10y"]["features"])

    def test_relationships_align_common_dates_and_bind_both_series(self) -> None:
        daily, macro, pack, bitcoin = inputs()
        nasdaq = next(item for item in daily["instruments"] if item["instrument"]["key"] == "nasdaq")
        nasdaq["bars"] = bars(offset=110, missing_index=25)
        nasdaq["bar_count"] = len(nasdaq["bars"])
        context = build_kline_world_context(
            daily=daily, macro=macro, pack=pack, bitcoin=bitcoin, allow_fixture=True
        )
        relation = next(item for item in context["relationships"] if item["key"] == "us_growth_vs_broad")
        self.assertGreaterEqual(len(relation["points"]), 61)
        self.assertLessEqual(len(relation["points"]), LOOKBACK)
        self.assertEqual(len({item["date"] for item in relation["points"]}), len(relation["points"]))
        series_ids = {item["key"]: item["series_id"] for item in context["series"]}
        self.assertEqual(relation["lhs_series_id"], series_ids["nasdaq"])
        self.assertEqual(relation["rhs_series_id"], series_ids["sp500"])
        self.assertEqual(relation["semantics"], "normalized_relative_performance_not_literal_fund_flow")

    def test_fixture_short_history_and_unavailable_inputs_fail_closed(self) -> None:
        daily, macro, pack, bitcoin = inputs()
        with self.assertRaisesRegex(KlineWorldContextError, "fixture_or_unknown"):
            build_kline_world_context(daily=daily, macro=macro, pack=pack, bitcoin=bitcoin)
        fixture_context = build_kline_world_context(
            daily=daily, macro=macro, pack=pack, bitcoin=bitcoin, allow_fixture=True
        )
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(KlineWorldContextError, "fixture_context_publication"):
                KlineWorldContextStore(Path(temporary)).publish(fixture_context)
        short_daily, macro, pack, bitcoin = inputs(short_key="sp500")
        with self.assertRaisesRegex(KlineWorldContextError, "history_too_short:sp500"):
            build_kline_world_context(
                daily=short_daily, macro=macro, pack=pack, bitcoin=bitcoin, allow_fixture=True
            )
        daily, macro, pack, bitcoin = inputs()
        factor = next(item for item in macro["factors"] if item["factor"]["key"] == "dxy")
        factor["quality"] = "unavailable"
        with self.assertRaisesRegex(KlineWorldContextError, "series_unavailable:dxy"):
            build_kline_world_context(
                daily=daily, macro=macro, pack=pack, bitcoin=bitcoin, allow_fixture=True
            )

    def test_exact_ohlc_change_changes_series_relationship_and_context_identity(self) -> None:
        first = context_fixture()
        daily, macro, pack, bitcoin = inputs()
        sp500 = next(item for item in daily["instruments"] if item["instrument"]["key"] == "sp500")
        sp500["bars"][-1]["close"] += 0.1
        sp500["bars"][-1]["high"] += 0.1
        second = build_kline_world_context(
            daily=daily, macro=macro, pack=pack, bitcoin=bitcoin, allow_fixture=True
        )
        self.assertNotEqual(first["context_id"], second["context_id"])
        first_series = {item["key"]: item for item in first["series"]}
        second_series = {item["key"]: item for item in second["series"]}
        self.assertNotEqual(first_series["sp500"]["series_id"], second_series["sp500"]["series_id"])
        first_rel = {item["key"]: item for item in first["relationships"]}
        second_rel = {item["key"]: item for item in second["relationships"]}
        self.assertNotEqual(first_rel["us_growth_vs_broad"]["relationship_id"], second_rel["us_growth_vs_broad"]["relationship_id"])

    def test_llm_projection_is_bounded_and_omits_storage_paths_and_receipts(self) -> None:
        context = context_fixture()
        projection = context["llm_projection"]
        encoded = json.dumps(projection, ensure_ascii=False)
        self.assertEqual(projection["context_id"], context["context_id"])
        self.assertEqual(len(projection["series"]), 17)
        self.assertNotIn("source_identity", encoded)
        self.assertNotIn("normalized/", encoded)
        self.assertNotIn("Finance Daily Newsletter", encoded)
        self.assertFalse(projection["truth_boundary"]["finance_newsletter_input"])
        self.assertTrue(projection["truth_boundary"]["market_advice_allowed"])
        self.assertFalse(projection["truth_boundary"]["automatic_execution_eligible"])
        self.assertLessEqual(
            len(json.dumps(projection, ensure_ascii=False, separators=(",", ":")).encode()),
            MAX_LLM_PROJECTION_BYTES,
        )

    def test_stale_accepted_series_degrades_context_without_hiding_points(self) -> None:
        daily, macro, pack, bitcoin = inputs()
        gold = next(item for item in daily["instruments"] if item["instrument"]["key"] == "gold")
        gold["quality"] = "stale"
        context = build_kline_world_context(
            daily=daily, macro=macro, pack=pack, bitcoin=bitcoin, allow_fixture=True
        )
        self.assertEqual(context["quality"], "partial")
        series = {item["key"]: item for item in context["series"]}
        self.assertEqual(series["gold"]["quality"], "stale")
        self.assertEqual(len(series["gold"]["points"]), LOOKBACK)

    def test_store_replays_and_rejects_artifact_tamper_without_advancing_bad_context(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = KlineWorldContextStore(root, allow_fixture=True)
            context = context_fixture()
            pointer = store.publish(context)
            before = (root / "latest.json").read_bytes()
            self.assertEqual(store.latest()["context_id"], context["context_id"])
            broken = json.loads(json.dumps(context))
            broken["series"][0]["points"][-1]["close"] += 1
            with self.assertRaisesRegex(KlineWorldContextError, "context_projection_mismatch"):
                store.publish(broken)
            self.assertEqual((root / "latest.json").read_bytes(), before)
            daily, macro, pack, bitcoin = inputs()
            sp500 = next(item for item in daily["instruments"] if item["instrument"]["key"] == "sp500")
            sp500["bars"][-1]["close"] += 0.2
            sp500["bars"][-1]["high"] += 0.2
            next_context = build_kline_world_context(
                daily=daily, macro=macro, pack=pack, bitcoin=bitcoin, allow_fixture=True
            )
            with patch.object(
                store, "latest", side_effect=KlineWorldContextError("forced_final_readback")
            ):
                with self.assertRaisesRegex(KlineWorldContextError, "forced_final_readback"):
                    store.publish(next_context)
            self.assertEqual((root / "latest.json").read_bytes(), before)
            self.assertEqual(store.latest()["context_id"], context["context_id"])
            artifact_path = root / pointer["artifact"]["path"]
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
            artifact["quality"] = "partial"
            artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
            with self.assertRaisesRegex(KlineWorldContextError, "artifact_hash_mismatch"):
                store.latest()


if __name__ == "__main__":
    unittest.main()
