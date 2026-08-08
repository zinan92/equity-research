from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


PRODUCT = Path(__file__).resolve().parents[1]
ROOT = PRODUCT.parent
sys.path.insert(0, str(PRODUCT))

from data_core.market_regime_data import (  # noqa: E402
    INSTRUMENTS as DAILY_INSTRUMENTS,
    SCHEMA_VERSION as DAILY_SCHEMA_VERSION,
)
from data_core.market_regime_intraday_data import (  # noqa: E402
    INSTRUMENT_BY_KEY as INTRADAY_INSTRUMENT_BY_KEY,
    SCHEMA_VERSION as INTRADAY_SCHEMA_VERSION,
)
from data_core.market_regime_intraday_model import (  # noqa: E402
    ENTER_SCORE,
    EXIT_SCORE,
    HISTORY_SCHEMA_VERSION,
    MarketRegimeIntradayModelError,
    MarketRegimeIntradayOverlayStore,
    build_asset_impulse,
    classify_relation_candidate,
    compile_intraday_overlay,
    validate_overlay,
)
from data_core.market_regime_model import (  # noqa: E402
    ANALYSIS_SCHEMA_VERSION,
    compile_market_regime,
)


def canonical_bytes(value: dict) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def daily_bars(rate: float, *, count: int = 140) -> list[dict]:
    start = date(2026, 3, 19)
    previous = 100.0
    rows = []
    for index in range(count):
        close = previous * (1.0 + rate)
        rows.append(
            {
                "date": (start + timedelta(days=index)).isoformat(),
                "open": previous,
                "high": max(previous, close) * 1.002,
                "low": min(previous, close) * 0.998,
                "close": close,
                "volume": 1_000_000 + index,
            }
        )
        previous = close
    return rows


def structural_analysis(*, a_rate: float = 0.002, name: str = "structural") -> dict:
    items = []
    for spec in DAILY_INSTRUMENTS:
        rate = a_rate if spec.key in {"shanghai", "star50", "china_dividend"} else 0.0
        rows = daily_bars(rate)
        artifact_hash = sha256(f"{name}:{spec.key}".encode()).hexdigest()
        items.append(
            {
                "schema_version": DAILY_SCHEMA_VERSION,
                "instrument": asdict(spec),
                "bars": rows,
                "bar_count": len(rows),
                "last_completed_session": rows[-1]["date"],
                "last_completed_close_at": "2026-08-05T20:00:00Z",
                "quality": "fresh",
                "run_id": f"run-{name}",
                "generated_at": "2026-08-06T00:00:00Z",
                "source": {"raw_sha256": sha256(f"raw:{name}:{spec.key}".encode()).hexdigest()},
                "license": {
                    "license_status": "local_evaluation_only",
                    "verified_for_publication": False,
                },
                "data_kind": "fixture",
                "publication_eligible": False,
                "normalized_artifact": {
                    "path": f"normalized/run-{name}/{spec.key}.json",
                    "sha256": artifact_hash,
                    "schema_version": DAILY_SCHEMA_VERSION,
                },
            }
        )
    snapshot = {
        "schema_version": DAILY_SCHEMA_VERSION,
        "run_id": f"run-{name}",
        "generated_at": "2026-08-06T00:00:00Z",
        "quality": "fresh",
        "instrument_count": len(items),
        "instruments": items,
        "analysis_status": "not_computed",
    }
    return compile_market_regime(snapshot)


def intraday_bars(at: datetime, rate: float, *, count: int = 40) -> list[dict]:
    latest_end = at - timedelta(minutes=5)
    first_end = latest_end - timedelta(minutes=5 * (count - 1))
    previous = 100.0
    rows = []
    for index in range(count):
        ended = first_end + timedelta(minutes=5 * index)
        close = previous * (1.0 + rate)
        rows.append(
            {
                "provider_timestamp": int(ended.timestamp()),
                "started_at": (ended - timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
                "ended_at": ended.isoformat().replace("+00:00", "Z"),
                "open": previous,
                "high": max(previous, close),
                "low": min(previous, close),
                "close": close,
                "volume": 1000 + index,
            }
        )
        previous = close
    return rows


def intraday_snapshot(
    at: datetime,
    rates: dict[str, float],
    *,
    states: dict[str, str] | None = None,
    missing: set[str] | None = None,
    name: str = "intraday",
) -> dict:
    states = states or {}
    missing = missing or set()
    items = []
    for key, rate in rates.items():
        if key in missing:
            continue
        spec = INTRADAY_INSTRUMENT_BY_KEY[key]
        state = states.get(key, "open")
        rows = intraday_bars(at, rate)
        artifact_hash = sha256(f"{name}:{at.isoformat()}:{key}".encode()).hexdigest()
        last_end = rows[-1]["ended_at"]
        items.append(
            {
                "schema_version": INTRADAY_SCHEMA_VERSION,
                "instrument": asdict(spec),
                "interval": "5m",
                "bars": rows,
                "bar_count": len(rows),
                "provider_timestamp": last_end,
                "last_completed_bar_end_at": last_end,
                "last_completed_session": at.date().isoformat(),
                "observed_at": at.isoformat().replace("+00:00", "Z"),
                "received_at": at.isoformat().replace("+00:00", "Z"),
                "age_seconds": 300,
                "current_age_seconds": 300,
                "session_state": state,
                "freshness": "live_candidate" if state == "open" else "delayed",
                "refresh_status": "accepted",
                "data_kind": "fixture",
                "publication_eligible": False,
                "action_eligible": False,
                "normalized_artifact": {
                    "path": f"intraday/normalized/{name}/{key}.json",
                    "sha256": artifact_hash,
                    "schema_version": INTRADAY_SCHEMA_VERSION,
                },
            }
        )
    core = {
        "schema_version": INTRADAY_SCHEMA_VERSION,
        "run_id": f"run-{name}-{at:%H%M}",
        "generated_at": at.isoformat().replace("+00:00", "Z"),
        "quality": "complete" if not missing else "partial",
        "instrument_count": len(rates),
        "accepted_count": len(items),
        "rejected_count": len(rates) - len(items),
        "data_kind": "fixture",
        "publication_eligible": False,
        "action_eligible": False,
        "instruments": items,
    }
    identity = sha256(canonical_bytes(core)).hexdigest()
    return {
        **core,
        "snapshot_id": f"market-regime-intraday-snapshot:{identity}",
    }


def resign_snapshot(snapshot: dict) -> dict:
    core = {key: value for key, value in snapshot.items() if key != "snapshot_id"}
    identity = sha256(canonical_bytes(core)).hexdigest()
    snapshot["snapshot_id"] = f"market-regime-intraday-snapshot:{identity}"
    return snapshot


def persist_structural(root: Path, analysis: dict) -> None:
    digest = analysis["analysis_id"].split(":", 1)[1]
    relative = f"analysis/artifacts/{digest}.json"
    encoded = canonical_bytes(analysis)
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded)
    pointer = {
        "schema_version": ANALYSIS_SCHEMA_VERSION,
        "analysis_id": analysis["analysis_id"],
        "input_fingerprint": analysis["input_fingerprint"],
        "artifact": {"path": relative, "sha256": sha256(encoded).hexdigest()},
    }
    (root / "analysis" / "latest.json").write_bytes(canonical_bytes(pointer))


def persist_intraday(root: Path, snapshot: dict) -> None:
    digest = snapshot["snapshot_id"].split(":", 1)[1]
    relative = f"intraday/snapshots/{digest}.json"
    encoded = canonical_bytes(snapshot)
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded)
    pointer = {
        "schema_version": INTRADAY_SCHEMA_VERSION,
        "run_id": snapshot["run_id"],
        "snapshot_id": snapshot["snapshot_id"],
        "snapshot": {"path": relative, "sha256": sha256(encoded).hexdigest()},
    }
    (root / "intraday" / "latest.json").write_bytes(canonical_bytes(pointer))


class MarketRegimeIntradayModelTest(unittest.TestCase):
    def setUp(self) -> None:
        self.structural = structural_analysis()
        self.base = datetime(2026, 8, 6, 2, 30, tzinfo=timezone.utc)
        self.positive = {
            "shanghai": 0.001,
            "star50": 0.0012,
            "china_dividend": 0.0006,
        }
        self.negative = {key: -rate for key, rate in self.positive.items()}
        self.neutral = {key: 0.0 for key in self.positive}

    def compile_at(
        self,
        minutes: int,
        rates: dict[str, float],
        previous: dict | None = None,
        **kwargs,
    ) -> dict:
        at = self.base + timedelta(minutes=minutes)
        snapshot = intraday_snapshot(at, rates, name=f"at-{minutes}", **kwargs)
        return compile_intraday_overlay(self.structural, snapshot, previous)

    def confirmed(self) -> dict:
        first = self.compile_at(0, self.positive)
        return self.compile_at(15, self.positive, first)

    def test_asset_impulse_is_bounded_and_evidence_bound(self) -> None:
        snapshot = intraday_snapshot(self.base, self.positive)
        item = snapshot["instruments"][0]
        signal = build_asset_impulse(item)
        self.assertGreater(signal["impulse_score"], ENTER_SCORE)
        self.assertLessEqual(signal["impulse_score"], 50)
        self.assertEqual(signal["interval_count"], 12)
        self.assertIn(item["normalized_artifact"]["sha256"][:16], signal["evidence_id"])

    def test_enter_exit_and_neutral_boundaries_are_frozen(self) -> None:
        self.assertEqual(classify_relation_candidate("positive", ENTER_SCORE), "confirms")
        self.assertEqual(classify_relation_candidate("positive", -ENTER_SCORE), "diverges")
        self.assertEqual(classify_relation_candidate("positive", ENTER_SCORE - 0.001), "insufficient")
        self.assertEqual(
            classify_relation_candidate("positive", EXIT_SCORE, previous_relation="confirms"),
            "confirms",
        )
        self.assertEqual(
            classify_relation_candidate("positive", EXIT_SCORE - 0.001, previous_relation="confirms"),
            "insufficient",
        )
        self.assertEqual(classify_relation_candidate("negative", -ENTER_SCORE), "confirms")
        self.assertEqual(classify_relation_candidate("negative", ENTER_SCORE), "diverges")
        self.assertEqual(classify_relation_candidate("neutral", EXIT_SCORE), "confirms")
        self.assertEqual(classify_relation_candidate("neutral", ENTER_SCORE), "diverges")

    def test_two_unique_overlays_are_required_to_establish_direction(self) -> None:
        first = self.compile_at(0, self.positive)
        self.assertEqual(first["relation"], "insufficient")
        self.assertEqual(first["transition"]["pending_relation"], "confirms")
        self.assertEqual(first["transition"]["pending_count"], 1)
        second = self.compile_at(15, self.positive, first)
        self.assertEqual(second["relation"], "confirms")
        self.assertTrue(second["transition"]["transitioned"])
        self.assertIsNotNone(second["transition"]["cooldown_until"])

    def test_opposite_direction_waits_for_persistence_and_cooldown(self) -> None:
        confirmed = self.confirmed()
        first_opposite = self.compile_at(30, self.negative, confirmed)
        self.assertEqual(first_opposite["relation"], "confirms")
        self.assertTrue(first_opposite["transition"]["blocked_by_cooldown"])
        second_opposite = self.compile_at(40, self.negative, first_opposite)
        self.assertEqual(second_opposite["relation"], "confirms")
        self.assertEqual(second_opposite["transition"]["pending_count"], 2)
        self.assertTrue(second_opposite["transition"]["blocked_by_cooldown"])
        after_cooldown = self.compile_at(50, self.negative, second_opposite)
        self.assertEqual(after_cooldown["relation"], "diverges")
        self.assertTrue(after_cooldown["transition"]["transitioned"])

    def test_weak_impulse_exits_only_after_two_verified_overlays(self) -> None:
        confirmed = self.confirmed()
        first_weak = self.compile_at(30, self.neutral, confirmed)
        self.assertEqual(first_weak["relation"], "confirms")
        self.assertEqual(first_weak["transition"]["pending_relation"], "insufficient")
        second_weak = self.compile_at(45, self.neutral, first_weak)
        self.assertEqual(second_weak["relation"], "insufficient")

    def test_closed_and_unknown_evidence_degrade_immediately(self) -> None:
        confirmed = self.confirmed()
        closed_states = {key: "closed" for key in self.positive}
        closed = self.compile_at(30, self.positive, confirmed, states=closed_states)
        self.assertEqual(closed["relation"], "closed")
        self.assertTrue(closed["transition"]["immediate_evidence_state"])
        self.assertIn("stable_relation_changed", closed["material_change"]["reasons"])
        unknown_states = {key: "unknown" for key in self.positive}
        unknown = self.compile_at(45, self.positive, closed, states=unknown_states)
        self.assertEqual(unknown["relation"], "insufficient")
        self.assertNotEqual(unknown["relation"], "closed")

    def test_closed_requires_current_accepted_session_evidence(self) -> None:
        states = {key: "closed" for key in self.positive}
        snapshot = intraday_snapshot(self.base, self.positive, states=states)
        snapshot["instruments"][0]["refresh_status"] = "rejected"
        resign_snapshot(snapshot)
        overlay = compile_intraday_overlay(self.structural, snapshot)
        self.assertEqual(overlay["relation"], "insufficient")
        self.assertIn("unavailable or conflicting", overlay["a_share_tape"]["reason"])

    def test_open_recovery_from_closed_still_requires_two_unique_overlays(self) -> None:
        states = {key: "closed" for key in self.positive}
        closed = self.compile_at(0, self.positive, states=states)
        first_open = self.compile_at(15, self.positive, closed)
        self.assertEqual(first_open["relation"], "insufficient")
        self.assertEqual(first_open["transition"]["pending_relation"], "confirms")
        recovered = self.compile_at(30, self.positive, first_open)
        self.assertEqual(recovered["relation"], "confirms")

    def test_partial_snapshot_degrades_only_missing_dependencies(self) -> None:
        first = self.compile_at(0, self.positive, missing={"china_dividend"})
        second = self.compile_at(
            15,
            self.positive,
            first,
            missing={"china_dividend"},
        )
        self.assertEqual(second["relation"], "confirms")
        self.assertIn("china_dividend", second["a_share_tape"]["missing_dependencies"])
        self.assertIsNone(second["a_share_tape"]["style_relative_score"])
        missing_broad = self.compile_at(
            30,
            self.positive,
            second,
            missing={"shanghai"},
        )
        self.assertEqual(missing_broad["relation"], "insufficient")

    def test_cash_and_futures_split_group_weight_without_splicing_identity(self) -> None:
        rates = {
            "sp500_cash": 0.001,
            "sp500_futures_proxy": 0.001,
            **self.positive,
        }
        overlay = self.compile_at(0, rates)
        us_rows = [
            row for row in overlay["signal_contributions"]
            if row["group"] == "us_large_cap"
        ]
        self.assertEqual({row["instrument"] for row in us_rows}, {"sp500_cash", "sp500_futures_proxy"})
        self.assertEqual({row["signed_weight"] for row in us_rows}, {0.08})
        self.assertNotEqual(us_rows[0]["evidence_id"], us_rows[1]["evidence_id"])

    def test_first_overlay_does_not_claim_change_and_has_two_watch_conditions(self) -> None:
        overlay = self.compile_at(0, self.positive)
        self.assertFalse(overlay["material_change"]["is_material"])
        self.assertEqual(overlay["material_change"]["reasons"], ["baseline_not_available"])
        self.assertEqual(len(overlay["watch_conditions"]), 2)
        self.assertTrue(overlay["truth_boundary"]["experimental"])
        self.assertFalse(overlay["truth_boundary"]["forecast"])
        self.assertFalse(overlay["truth_boundary"]["action_eligible"])

    def test_same_inputs_and_fixed_previous_replay_to_same_identity(self) -> None:
        previous = self.compile_at(0, self.positive)
        snapshot = intraday_snapshot(
            self.base + timedelta(minutes=15),
            self.positive,
            name="fixed",
        )
        first = compile_intraday_overlay(self.structural, snapshot, previous)
        second = compile_intraday_overlay(self.structural, snapshot, previous)
        self.assertEqual(first, second)
        self.assertEqual(first["overlay_id"], second["overlay_id"])
        duplicate = compile_intraday_overlay(self.structural, snapshot, first)
        self.assertEqual(duplicate, first)

    def test_structural_rebind_reuses_only_the_identical_intraday_snapshot(self) -> None:
        snapshot = intraday_snapshot(self.base, self.positive, name="rebind-input")
        previous = compile_intraday_overlay(self.structural, snapshot)
        rebound_structural = structural_analysis(a_rate=-0.002, name="rebound")

        rebound = compile_intraday_overlay(
            rebound_structural,
            snapshot,
            previous,
        )
        self.assertNotEqual(rebound["overlay_id"], previous["overlay_id"])
        self.assertEqual(rebound["generated_at"], previous["generated_at"])
        self.assertEqual(
            rebound["intraday"]["snapshot_id"],
            previous["intraday"]["snapshot_id"],
        )
        self.assertEqual(
            rebound["structural"]["analysis_id"],
            rebound_structural["analysis_id"],
        )
        self.assertEqual(rebound["baseline_overlay_id"], previous["overlay_id"])
        self.assertEqual(rebound["transition"]["pending_count"], 1)
        self.assertIn(
            "structural_analysis_changed",
            rebound["material_change"]["reasons"],
        )
        self.assertEqual(
            compile_intraday_overlay(rebound_structural, snapshot, rebound),
            rebound,
        )

        different_same_time = intraday_snapshot(
            self.base,
            self.negative,
            name="different-same-time",
        )
        with self.assertRaisesRegex(
            MarketRegimeIntradayModelError,
            "new intraday snapshot must be later",
        ):
            compile_intraday_overlay(
                rebound_structural,
                different_same_time,
                previous,
            )

    def test_tampered_structural_snapshot_or_overlay_identity_fails_closed(self) -> None:
        bad_structural = json.loads(json.dumps(self.structural))
        bad_structural["analysis_id"] = "market-regime-analysis:" + "0" * 64
        with self.assertRaisesRegex(MarketRegimeIntradayModelError, "structural analysis identity"):
            compile_intraday_overlay(
                bad_structural,
                intraday_snapshot(self.base, self.positive),
            )
        bad_snapshot = intraday_snapshot(self.base, self.positive)
        bad_snapshot["quality"] = "partial"
        with self.assertRaisesRegex(MarketRegimeIntradayModelError, "snapshot identity"):
            compile_intraday_overlay(self.structural, bad_snapshot)
        overlay = self.compile_at(0, self.positive)
        overlay["relation"] = "closed"
        with self.assertRaisesRegex(MarketRegimeIntradayModelError, "overlay .*mismatch"):
            validate_overlay(overlay)

    def test_history_is_append_only_duplicate_safe_and_hash_verified(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            persist_structural(root, self.structural)
            first_snapshot = intraday_snapshot(self.base, self.positive, name="store-1")
            persist_intraday(root, first_snapshot)
            store = MarketRegimeIntradayOverlayStore(root)
            first = store.compile_latest()
            self.assertTrue(first["history_appended"])
            self.assertEqual(first["sequence"], 1)
            duplicate = store.compile_latest()
            self.assertFalse(duplicate["history_appended"])
            self.assertEqual(duplicate["sequence"], 1)
            second_snapshot = intraday_snapshot(
                self.base + timedelta(minutes=15),
                self.positive,
                name="store-2",
            )
            persist_intraday(root, second_snapshot)
            second = store.compile_latest()
            self.assertTrue(second["history_appended"])
            self.assertEqual(second["sequence"], 2)
            history = store.verify_history()
            self.assertEqual([row["sequence"] for row in history], [1, 2])
            self.assertEqual(history[0]["schema_version"], HISTORY_SCHEMA_VERSION)
            self.assertIsNone(history[0]["previous"])
            self.assertEqual(history[1]["previous"]["history_id"], history[0]["history_id"])
            latest = store.latest()
            self.assertEqual(latest["overlay_id"], second["overlay"]["overlay_id"])

            first_overlay_path = root / history[0]["overlay"]["path"]
            original = first_overlay_path.read_bytes()
            first_overlay_path.write_bytes(b"{}\n")
            with self.assertRaisesRegex(MarketRegimeIntradayModelError, "artifact hash"):
                store.verify_history()
            first_overlay_path.write_bytes(original)

            first_history_path = root / history[1]["previous"]["path"]
            original_history = first_history_path.read_bytes()
            first_history_path.write_bytes(b"{}\n")
            with self.assertRaisesRegex(MarketRegimeIntradayModelError, "artifact hash"):
                store.verify_history()
            first_history_path.write_bytes(original_history)

    def test_fixed_replay_produces_same_overlay_and_history_identities(self) -> None:
        receipts = []
        for _ in range(2):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                persist_structural(root, self.structural)
                persist_intraday(
                    root,
                    intraday_snapshot(self.base, self.positive, name="replay-1"),
                )
                store = MarketRegimeIntradayOverlayStore(root)
                first = store.compile_latest()
                persist_intraday(
                    root,
                    intraday_snapshot(
                        self.base + timedelta(minutes=15),
                        self.positive,
                        name="replay-2",
                    ),
                )
                second = store.compile_latest()
                receipts.append(
                    (
                        first["overlay"]["overlay_id"],
                        first["history_id"],
                        second["overlay"]["overlay_id"],
                        second["history_id"],
                    )
                )
        self.assertEqual(receipts[0], receipts[1])

    def test_failed_input_does_not_advance_overlay_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            persist_structural(root, self.structural)
            persist_intraday(root, intraday_snapshot(self.base, self.positive))
            store = MarketRegimeIntradayOverlayStore(root)
            store.compile_latest()
            overlay_pointer = root / "intraday" / "overlay" / "latest.json"
            before = overlay_pointer.read_bytes()
            intraday_pointer = json.loads(
                (root / "intraday" / "latest.json").read_text(encoding="utf-8")
            )
            intraday_pointer["snapshot"]["sha256"] = "0" * 64
            (root / "intraday" / "latest.json").write_bytes(canonical_bytes(intraday_pointer))
            with self.assertRaisesRegex(MarketRegimeIntradayModelError, "artifact hash"):
                store.compile_latest()
            self.assertEqual(overlay_pointer.read_bytes(), before)

    def test_cli_returns_bounded_receipt_and_duplicate_does_not_append(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            persist_structural(root, self.structural)
            persist_intraday(root, intraday_snapshot(self.base, self.positive))
            command = [
                sys.executable,
                str(ROOT / "scripts" / "compile_market_regime_intraday.py"),
                "--root",
                str(root),
            ]
            first = json.loads(subprocess.run(command, check=True, capture_output=True, text=True).stdout)
            second = json.loads(subprocess.run(command, check=True, capture_output=True, text=True).stdout)
            self.assertTrue(first["history_appended"])
            self.assertFalse(second["history_appended"])
            self.assertEqual(first["overlay_id"], second["overlay_id"])
            self.assertEqual(len(first["watch_conditions"]), 2)


if __name__ == "__main__":
    unittest.main()
