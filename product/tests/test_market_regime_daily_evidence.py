from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from zoneinfo import ZoneInfo


PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT))

from data_core.market_regime_data import (  # noqa: E402
    INSTRUMENTS,
    SCHEMA_VERSION as DATA_SCHEMA_VERSION,
    HttpCapture,
    MarketRegimeDataStore,
)
from data_core.market_regime_daily_evidence import (  # noqa: E402
    PACK_ID_PREFIX,
    SCHEMA_VERSION,
    SLOT_KEYS,
    MarketRegimeDailyEvidenceError,
    MarketRegimeDailyEvidenceStore,
    _contradictions,
    _validate_slot_contract,
    compile_daily_evidence_pack,
    resolve_evidence,
)
from data_core.market_regime_macro_data import (  # noqa: E402
    DXY_CHART_URL,
    MarketRegimeMacroDataStore,
)
from data_core.market_regime_model import (  # noqa: E402
    ANALYSIS_SCHEMA_VERSION,
    MarketRegimeAnalysisStore,
    compile_market_regime,
)


NOW = datetime(2026, 8, 6, 23, 0, tzinfo=timezone.utc)
END = date(2026, 8, 5)


def canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def write_json(path: Path, value: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = canonical(value)
    path.write_bytes(encoded)
    return sha256(encoded).hexdigest()


def fixture_daily(root: Path) -> tuple[dict, dict]:
    dates = [END - timedelta(days=99 - index) for index in range(100)]
    items = []
    for spec_index, spec in enumerate(INSTRUMENTS):
        bars = []
        for index, item_date in enumerate(dates):
            value = 100 + spec_index * 5 + index * (0.2 + spec_index / 100)
            bars.append(
                {
                    "date": item_date.isoformat(),
                    "open": round(value - 0.1, 6),
                    "high": round(value + 0.4, 6),
                    "low": round(value - 0.4, 6),
                    "close": round(value, 6),
                    "volume": 1000 + index,
                }
            )
        hour, minute = (int(value) for value in spec.session_close.split(":"))
        close_at = datetime.combine(
            END, time(hour, minute), tzinfo=ZoneInfo(spec.exchange_timezone)
        ).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        artifact = {
            "schema_version": DATA_SCHEMA_VERSION,
            "instrument": asdict(spec),
            "bars": bars,
            "bar_count": len(bars),
            "last_completed_session": END.isoformat(),
            "last_completed_close_at": close_at,
            "quality": "fresh",
            "source": {
                "raw_sha256": sha256(f"raw:{spec.key}".encode()).hexdigest(),
                "status_code": 200,
            },
            "run_id": "daily-fixture-run",
            "generated_at": "2026-08-06T23:00:00Z",
            "data_kind": "real",
            "publication_eligible": False,
        }
        relative = f"normalized/daily-fixture-run/{spec.key}.json"
        artifact_sha = write_json(root / relative, artifact)
        items.append(
            {
                **artifact,
                "normalized_artifact": {
                    "path": relative,
                    "sha256": artifact_sha,
                    "schema_version": DATA_SCHEMA_VERSION,
                },
            }
        )
    snapshot = {
        "schema_version": DATA_SCHEMA_VERSION,
        "run_id": "daily-fixture-run",
        "generated_at": "2026-08-06T23:00:00Z",
        "quality": "fresh",
        "instrument_count": len(items),
        "instruments": items,
        "refresh_receipt": "runs/daily-fixture-run.json",
    }
    write_json(root / "latest.json", snapshot)
    analysis = compile_market_regime(snapshot)
    digest = analysis["analysis_id"].split(":", 1)[1]
    relative = f"analysis/artifacts/{digest}.json"
    artifact_sha = write_json(root / relative, analysis)
    write_json(
        root / "analysis" / "latest.json",
        {
            "schema_version": ANALYSIS_SCHEMA_VERSION,
            "analysis_id": analysis["analysis_id"],
            "input_fingerprint": analysis["input_fingerprint"],
            "artifact": {"path": relative, "sha256": artifact_sha},
        },
    )
    return snapshot, analysis


def capture(
    body: bytes,
    *,
    url: str,
    content_type: str,
) -> HttpCapture:
    return HttpCapture(
        "GET",
        url,
        url,
        200,
        (("content-type", content_type),),
        (),
        (url,),
        body,
        "2026-08-06T23:00:00Z",
    )


def dxy_body() -> bytes:
    dates = [END - timedelta(days=209 - index) for index in range(210)]
    zone = ZoneInfo("America/New_York")
    timestamps = [
        int(datetime.combine(item, time(9, 30), tzinfo=zone).timestamp()) for item in dates
    ]
    values = [100 + index / 10 for index in range(210)]
    return json.dumps(
        {
            "chart": {
                "result": [
                    {
                        "meta": {
                            "symbol": "DX-Y.NYB",
                            "currency": "USD",
                            "exchangeTimezoneName": "America/New_York",
                            "regularMarketTime": int(
                                datetime.combine(END, time(17), tzinfo=zone).timestamp()
                            ),
                            "currentTradingPeriod": {
                                "regular": {
                                    "end": int(
                                        datetime.combine(END, time(17), tzinfo=zone).timestamp()
                                    )
                                }
                            },
                        },
                        "timestamp": timestamps,
                        "indicators": {
                            "quote": [
                                {
                                    "open": values,
                                    "high": [value + 0.2 for value in values],
                                    "low": [value - 0.2 for value in values],
                                    "close": [value + 0.1 for value in values],
                                    "volume": [0 for _ in values],
                                }
                            ]
                        },
                    }
                ],
                "error": None,
            }
        }
    ).encode()


def treasury_body() -> bytes:
    dates = [END - timedelta(days=149 - index) for index in range(150)]
    rows = [
        f"{item.strftime('%m/%d/%Y')},{4 + index / 100:.2f},{4.5 + index / 100:.2f}"
        for index, item in enumerate(dates)
    ]
    rows.reverse()
    return ("Date,2 Yr,10 Yr\n" + "\n".join(rows) + "\n").encode()


class MacroTransport:
    def __call__(self, url: str) -> HttpCapture:
        if "finance.yahoo.com" in url:
            return capture(dxy_body(), url=DXY_CHART_URL, content_type="application/json")
        return capture(treasury_body(), url=url, content_type="text/csv")


def fixture_inputs(root: Path, macro_root: Path) -> tuple[dict, dict, dict]:
    daily, analysis = fixture_daily(root)
    macro = MarketRegimeMacroDataStore(macro_root, http_get=MacroTransport()).refresh(now=NOW)
    return daily, analysis, macro


class MarketRegimeDailyEvidenceTest(unittest.TestCase):
    def test_pack_freezes_sixteen_slots_units_times_and_resolvable_citations(self) -> None:
        with tempfile.TemporaryDirectory() as daily_temp, tempfile.TemporaryDirectory() as macro_temp:
            daily, analysis, macro = fixture_inputs(Path(daily_temp), Path(macro_temp))
            pack = compile_daily_evidence_pack(daily, analysis, macro)
        self.assertEqual(pack["schema_version"], SCHEMA_VERSION)
        self.assertEqual(len(SLOT_KEYS), 16)
        self.assertEqual(len(pack["slots"]), 16)
        self.assertEqual(pack["coverage"]["accepted"], 16)
        self.assertIn("confidence_inputs", pack)
        slots = {item["key"]: item for item in pack["slots"]}
        self.assertEqual(slots["sp500"]["change_5d_unit"], "percent_return")
        self.assertEqual(slots["dxy"]["change_5d_unit"], "percent_return")
        self.assertEqual(slots["us2y"]["level_unit"], "percent")
        self.assertEqual(slots["us2y"]["change_5d_unit"], "basis_points")
        self.assertEqual(slots["us2s10s"]["level_unit"], "basis_points")
        self.assertNotEqual(pack["time"]["joint_judgment_time"], pack["time"]["latest_evidence_time"])
        self.assertGreater(pack["time"]["cross_market_close_skew_hours"], 0)
        for evidence_id, key in pack["evidence_index"].items():
            self.assertEqual(resolve_evidence(pack, evidence_id)["key"], key)
        self.assertFalse(pack["truth_boundary"]["publication_eligible"])
        self.assertFalse(pack["truth_boundary"]["action_eligible"])

    def test_pack_id_is_deterministic_and_changes_with_canonical_macro_input(self) -> None:
        with tempfile.TemporaryDirectory() as daily_temp, tempfile.TemporaryDirectory() as macro_temp:
            daily, analysis, macro = fixture_inputs(Path(daily_temp), Path(macro_temp))
            first = compile_daily_evidence_pack(daily, analysis, macro)
            replay = compile_daily_evidence_pack(daily, analysis, macro)
            changed = json.loads(json.dumps(macro))
            dxy = next(item for item in changed["factors"] if item["factor"]["key"] == "dxy")
            dxy["value"] += 1
            second = compile_daily_evidence_pack(daily, analysis, changed)
        self.assertEqual(first["pack_id"], replay["pack_id"])
        self.assertNotEqual(first["pack_id"], second["pack_id"])

    def test_caller_cannot_poison_future_truth_boundary_contract(self) -> None:
        with tempfile.TemporaryDirectory() as daily_temp, tempfile.TemporaryDirectory() as macro_temp:
            daily, analysis, macro = fixture_inputs(Path(daily_temp), Path(macro_temp))
            first = compile_daily_evidence_pack(daily, analysis, macro)
            first["truth_boundary"]["publication_eligible"] = True
            first["identity_core"]["truth_boundary"]["action_eligible"] = True
            second = compile_daily_evidence_pack(daily, analysis, macro)
        self.assertFalse(second["truth_boundary"]["publication_eligible"])
        self.assertFalse(second["identity_core"]["truth_boundary"]["action_eligible"])

    def test_style_pair_contradiction_binds_all_four_evidence_ids(self) -> None:
        analysis = {
            "dimensions": {
                "risk": {"contradictions": []},
                "posture": {"contradictions": []},
                "style": {"contradictions": [
                {
                    "pair": "US_vs_A_tech",
                    "reason": "US and A-share tech relative trends disagree",
                }
                ]},
            }
        }
        slots = {
            key: {"evidence_id": f"evidence:{key}"}
            for key in ("nasdaq", "sp500", "star50", "shanghai")
        }
        candidate = _contradictions(analysis, slots)[0]
        self.assertEqual(
            candidate["keys"], ["nasdaq", "sp500", "star50", "shanghai"]
        )
        self.assertEqual(len(candidate["evidence_ids"]), 4)

    def test_missing_critical_slot_and_stale_or_fallback_inputs_degrade_honestly(self) -> None:
        with tempfile.TemporaryDirectory() as daily_temp, tempfile.TemporaryDirectory() as macro_temp:
            daily, analysis, macro = fixture_inputs(Path(daily_temp), Path(macro_temp))
            missing = json.loads(json.dumps(macro))
            missing["factors"] = [
                item for item in missing["factors"] if item["factor"]["key"] != "dxy"
            ]
            pack = compile_daily_evidence_pack(daily, analysis, missing)
            self.assertEqual(pack["quality"], "partial")
            self.assertIn("dxy", pack["coverage"]["critical_missing_keys"])
            self.assertEqual(pack["confidence_inputs"]["score"], 0)
            self.assertEqual(pack["coverage"]["accepted"], 15)
            self.assertEqual(
                next(item for item in pack["slots"] if item["key"] == "dxy")["status"],
                "unavailable",
            )
            unavailable_dxy = next(
                item for item in pack["slots"] if item["key"] == "dxy"
            )
            unavailable_dxy["evidence_id"] = (
                "market-regime-daily-evidence-v1:dxy:" + "0" * 64
            )
            with self.assertRaisesRegex(
                MarketRegimeDailyEvidenceError, "cannot carry a citation"
            ):
                _validate_slot_contract(pack["slots"])

            degraded = json.loads(json.dumps(macro))
            us10y = next(item for item in degraded["factors"] if item["factor"]["key"] == "us10y")
            us10y["quality"] = "stale"
            us10y["refresh_status"] = "rejected"
            us10y["refresh_failure"] = {
                "reason": "HTTP 503",
                "bounded_raw_excerpt": "upstream unavailable",
                "sources": [
                    {
                        "method": "GET",
                        "requested_url": "https://home.treasury.gov/test.csv",
                        "final_url": "https://home.treasury.gov/test.csv",
                        "status_code": 503,
                        "content_type": "text/html",
                        "raw_sha256": sha256(b"unavailable").hexdigest(),
                        "raw_bytes": 11,
                        "raw_path": "/runtime/run-a/raw.csv",
                        "fetched_at": "2026-08-06T23:00:00Z",
                    }
                ],
            }
            pack = compile_daily_evidence_pack(daily, analysis, degraded)
            self.assertIn("us10y", pack["coverage"]["stale_keys"])
            self.assertIn("us10y", pack["coverage"]["fallback_keys"])
            self.assertEqual(pack["quality"], "partial")
            self.assertLess(
                pack["confidence_inputs"]["score"],
                pack["confidence_inputs"]["base_analysis_confidence"],
            )
            replay = json.loads(json.dumps(degraded))
            replay_us10y = next(
                item for item in replay["factors"] if item["factor"]["key"] == "us10y"
            )
            replay_us10y["refresh_failure"]["sources"][0]["raw_path"] = "/other/run-b/raw.csv"
            replay_us10y["refresh_failure"]["sources"][0]["fetched_at"] = "2026-08-07T01:00:00Z"
            self.assertEqual(
                compile_daily_evidence_pack(daily, analysis, replay)["pack_id"],
                pack["pack_id"],
            )

    def test_analysis_binding_unit_mismatch_and_unknown_citation_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as daily_temp, tempfile.TemporaryDirectory() as macro_temp:
            daily, analysis, macro = fixture_inputs(Path(daily_temp), Path(macro_temp))
            wrong_analysis = json.loads(json.dumps(analysis))
            wrong_analysis["source_run_id"] = "different-run"
            with self.assertRaisesRegex(MarketRegimeDailyEvidenceError, "bind current daily"):
                compile_daily_evidence_pack(daily, wrong_analysis, macro)

            forged_analysis = json.loads(json.dumps(analysis))
            forged_analysis["asset_features"][0]["close"] += 10
            with self.assertRaisesRegex(MarketRegimeDailyEvidenceError, "identity does not match"):
                compile_daily_evidence_pack(daily, forged_analysis, macro)

            wrong_unit = json.loads(json.dumps(macro))
            us2y = next(item for item in wrong_unit["factors"] if item["factor"]["key"] == "us2y")
            us2y["factor"]["change_unit"] = "percent_return"
            with self.assertRaisesRegex(MarketRegimeDailyEvidenceError, "factor registry"):
                compile_daily_evidence_pack(daily, analysis, wrong_unit)

            wrong_provider = json.loads(json.dumps(macro))
            wrong_provider["factors"][0]["factor"]["provider"] = "other_provider"
            with self.assertRaisesRegex(MarketRegimeDailyEvidenceError, "factor registry"):
                compile_daily_evidence_pack(daily, analysis, wrong_provider)

            wrong_daily_unit = json.loads(json.dumps(daily))
            wrong_daily_unit["instruments"][0]["instrument"]["unit"] = "basis_points"
            forged_for_wrong_daily = compile_market_regime(wrong_daily_unit)
            with self.assertRaisesRegex(MarketRegimeDailyEvidenceError, "instrument registry"):
                compile_daily_evidence_pack(wrong_daily_unit, forged_for_wrong_daily, macro)

            pack = compile_daily_evidence_pack(daily, analysis, macro)
            with self.assertRaisesRegex(MarketRegimeDailyEvidenceError, "unknown evidence ID"):
                resolve_evidence(pack, "evidence:unknown")

    def test_store_replays_identity_and_detects_artifact_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as daily_temp, tempfile.TemporaryDirectory() as macro_temp, tempfile.TemporaryDirectory() as output_temp:
            daily_root, macro_root, output_root = Path(daily_temp), Path(macro_temp), Path(output_temp)
            fixture_inputs(daily_root, macro_root)
            store = MarketRegimeDailyEvidenceStore(daily_root, macro_root, output_root)
            first = store.compile_latest()
            second = store.compile_latest()
            self.assertEqual(first["pack_id"], second["pack_id"])
            self.assertEqual(store.latest()["pack_id"], first["pack_id"])
            pointer = json.loads((output_root / "latest.json").read_text())
            escaped = json.loads(json.dumps(pointer))
            escaped["artifact"]["path"] = "artifacts/../../outside.json"
            write_json(output_root / "latest.json", escaped)
            with self.assertRaisesRegex(MarketRegimeDailyEvidenceError, "reference is invalid"):
                store.latest()
            write_json(output_root / "latest.json", pointer)
            artifact = output_root / pointer["artifact"]["path"]
            artifact.write_bytes(artifact.read_bytes() + b" ")
            with self.assertRaisesRegex(MarketRegimeDailyEvidenceError, "artifact hash mismatch"):
                store.latest()

    def test_store_rejects_rebound_rights_tamper_and_noncanonical_paths(self) -> None:
        with tempfile.TemporaryDirectory() as daily_temp, tempfile.TemporaryDirectory() as macro_temp, tempfile.TemporaryDirectory() as output_temp:
            daily_root, macro_root, output_root = Path(daily_temp), Path(macro_temp), Path(output_temp)
            fixture_inputs(daily_root, macro_root)
            store = MarketRegimeDailyEvidenceStore(daily_root, macro_root, output_root)
            store.compile_latest()
            pointer = json.loads((output_root / "latest.json").read_text())
            artifact = json.loads((output_root / pointer["artifact"]["path"]).read_text())
            receipt = json.loads((output_root / pointer["receipt"]["path"]).read_text())
            artifact["truth_boundary"]["publication_eligible"] = True
            artifact["identity_core"]["truth_boundary"]["publication_eligible"] = True
            alias_artifact = "artifacts/alias.json"
            alias_receipt = "receipts/alias.json"
            artifact_hash = write_json(output_root / alias_artifact, artifact)
            receipt["publication_eligible"] = True
            receipt["artifact"] = {"path": alias_artifact, "sha256": artifact_hash}
            receipt_hash = write_json(output_root / alias_receipt, receipt)
            pointer["artifact"] = receipt["artifact"]
            pointer["receipt"] = {"path": alias_receipt, "sha256": receipt_hash}
            write_json(output_root / "latest.json", pointer)
            with self.assertRaisesRegex(MarketRegimeDailyEvidenceError, "reference is invalid"):
                store.latest()

    def test_store_rejects_rebound_value_with_stale_evidence_id(self) -> None:
        with tempfile.TemporaryDirectory() as daily_temp, tempfile.TemporaryDirectory() as macro_temp, tempfile.TemporaryDirectory() as output_temp:
            daily_root, macro_root, output_root = Path(daily_temp), Path(macro_temp), Path(output_temp)
            fixture_inputs(daily_root, macro_root)
            store = MarketRegimeDailyEvidenceStore(daily_root, macro_root, output_root)
            store.compile_latest()
            pointer = json.loads((output_root / "latest.json").read_text())
            pack = json.loads((output_root / pointer["artifact"]["path"]).read_text())
            pack["identity_core"]["slots"][0]["value"] += 10
            pack["slots"][0]["value"] += 10
            digest = sha256(
                json.dumps(
                    pack["identity_core"],
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()
            pack_id = f"{PACK_ID_PREFIX}{digest}"
            pack["pack_id"] = pack_id
            artifact_path = f"artifacts/{digest}.json"
            artifact_hash = write_json(output_root / artifact_path, pack)
            receipt = {
                "schema_version": SCHEMA_VERSION,
                "event": "completed",
                "pack_id": pack_id,
                "inputs": pack["inputs"],
                "artifact": {"path": artifact_path, "sha256": artifact_hash},
                "publication_eligible": False,
                "action_eligible": False,
            }
            receipt_path = f"receipts/{digest}.json"
            receipt_hash = write_json(output_root / receipt_path, receipt)
            write_json(
                output_root / "latest.json",
                {
                    "schema_version": SCHEMA_VERSION,
                    "pack_id": pack_id,
                    "artifact": receipt["artifact"],
                    "receipt": {"path": receipt_path, "sha256": receipt_hash},
                },
            )
            with self.assertRaisesRegex(MarketRegimeDailyEvidenceError, "slot identity mismatch"):
                store.latest()

    def test_store_rejects_analysis_that_no_longer_matches_daily_latest(self) -> None:
        with tempfile.TemporaryDirectory() as daily_temp, tempfile.TemporaryDirectory() as macro_temp, tempfile.TemporaryDirectory() as output_temp:
            daily_root, macro_root = Path(daily_temp), Path(macro_temp)
            fixture_inputs(daily_root, macro_root)
            snapshot = MarketRegimeDataStore(daily_root).latest()
            snapshot["run_id"] = "advanced-without-analysis"
            write_json(daily_root / "latest.json", snapshot)
            store = MarketRegimeDailyEvidenceStore(daily_root, macro_root, output_temp)
            with self.assertRaisesRegex(MarketRegimeDailyEvidenceError, "bind current daily"):
                store.compile_latest()

    def test_cli_status_is_informational_only_for_unused_output(self) -> None:
        script = PRODUCT.parent / "scripts" / "compile_market_regime_daily_evidence.py"
        with tempfile.TemporaryDirectory() as empty_temp:
            result = subprocess.run(
                [sys.executable, str(script), "--output-root", empty_temp, "--status"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0)
            self.assertEqual(json.loads(result.stdout)["quality"], "unavailable")


if __name__ == "__main__":
    unittest.main()
