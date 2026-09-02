from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import fcntl
import json
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


PRODUCT = Path(__file__).resolve().parents[1]
ROOT = PRODUCT.parent
sys.path.insert(0, str(PRODUCT))
sys.path.insert(0, str(ROOT / "scripts"))

from data_core.market_regime_kline_world_runtime import (  # noqa: E402
    SCHEMA_VERSION,
    KlineWorldRuntime,
    KlineWorldRuntimeError,
)
from data_core.market_regime_model import (  # noqa: E402
    ANALYSIS_SCHEMA_VERSION,
    compile_market_regime,
)
from manage_market_regime_kline_newsletter_launchd import LABEL, build_plist  # noqa: E402
from product.tests.test_market_regime_daily_evidence import MacroTransport  # noqa: E402
from product.tests.test_market_regime_kline_newsletter import BitcoinTransport  # noqa: E402
from product.tests.test_market_regime_kline_world_context import inputs  # noqa: E402
from product.tests.test_market_regime_kline_macro_analysis import valid_output  # noqa: E402


NOW = datetime(2026, 8, 16, 0, 20, tzinfo=timezone.utc)


def canonical(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def write_json(path: Path, value: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = canonical(value)
    path.write_bytes(encoded)
    return sha256(encoded).hexdigest()


def write_daily_authority(root: Path) -> dict:
    daily, _, _, _ = inputs(data_kind="real")
    run_id = "market-regime-20260816T002000Z-111111111111"
    frozen_items = []
    for item in daily["instruments"]:
        key = item["instrument"]["key"]
        artifact = deepcopy(item)
        artifact.pop("normalized_artifact", None)
        artifact["run_id"] = run_id
        artifact["generated_at"] = "2026-08-16T00:20:00Z"
        relative = f"normalized/{run_id}/{key}.json"
        digest = write_json(root / relative, artifact)
        frozen_items.append(
            {
                **artifact,
                "normalized_artifact": {
                    "path": relative,
                    "sha256": digest,
                    "schema_version": artifact["schema_version"],
                },
            }
        )
    snapshot = {
        "schema_version": daily["schema_version"],
        "run_id": run_id,
        "generated_at": "2026-08-16T00:20:00Z",
        "verdict_as_of": None,
        "analysis_status": "not_computed",
        "quality": "fresh",
        "instrument_count": len(frozen_items),
        "instruments": frozen_items,
        "refresh_receipt": f"runs/{run_id}.json",
    }
    write_json(root / "latest.json", snapshot)
    analysis = compile_market_regime(snapshot)
    analysis_digest = str(analysis["analysis_id"]).split(":", 1)[1]
    relative = f"analysis/artifacts/{analysis_digest}.json"
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
    return snapshot


class DynamicProvider:
    provider_name = "DeepSeek"
    model = "fixture-model"

    def __init__(self) -> None:
        self.requests: list[dict] = []

    def generate(self, request: dict) -> tuple[dict, dict]:
        self.requests.append(deepcopy(request))
        return valid_output(request), {
            "request_id": "request-safe",
            "model": self.model,
            "finish_reason": "stop",
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 20,
                "total_tokens": 30,
            },
        }


def runtime_fixture(base: Path, *, provider: object = None) -> KlineWorldRuntime:
    daily_root = base / "daily"
    write_daily_authority(daily_root)
    return KlineWorldRuntime(
        daily_root=daily_root,
        runtime_root=base / "runtime",
        output_root=base / "output",
        key_file=None,
        bitcoin_http_get=BitcoinTransport(),
        macro_http_get=MacroTransport(),
        world_model_provider=provider,
        allow_fixture=True,
    )


class KlineWorldRuntimeTests(unittest.TestCase):
    def test_full_serial_order_promotes_exact_verified_world_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            phases: list[str] = []
            provider = DynamicProvider()
            runtime = runtime_fixture(base, provider=provider)
            runtime.phase_observer = phases.append
            result = runtime.run_once(now=NOW)
            self.assertEqual(
                phases,
                [
                    "daily_validate",
                    "bitcoin_refresh",
                    "macro_refresh",
                    "evidence_compile",
                    "context_compile",
                    "model_compile",
                    "report_compile",
                    "report_verify",
                    "desktop_promote",
                    "status_publish",
                ],
            )
            report = result["report"]
            self.assertEqual(report["generation_status"], "model_generated_unreviewed")
            self.assertEqual(len(report["charts"]), 17)
            self.assertEqual(len(report["relationships"]), 12)
            self.assertEqual(len(report["parameter_basis"]), 7)
            self.assertEqual(report["insights"], [])
            self.assertGreaterEqual(len(report["observations"]), 1)
            self.assertGreaterEqual(len(report["data_ledger"]), 1)
            self.assertFalse(report["truth_boundary"]["finance_newsletter_input"])
            self.assertTrue(report["truth_boundary"]["macro_parameters_present"])
            self.assertFalse(report["truth_boundary"]["individual_security_advice"])
            self.assertFalse(report["truth_boundary"]["automatic_execution_eligible"])
            encoded_request = json.dumps(provider.requests, ensure_ascii=False)
            self.assertNotIn("Finance Daily Newsletter", encoded_request)
            report_state = result["report_state"]
            source_html = (base / "output" / report_state["html"]["path"]).read_bytes()
            source_markdown = (
                base / "output" / report_state["markdown"]["path"]
            ).read_bytes()
            self.assertEqual((base / "output" / "latest.html").read_bytes(), source_html)
            self.assertEqual((base / "output" / "latest.md").read_bytes(), source_markdown)
            self.assertEqual(result["status"], runtime.status())
            self.assertEqual(result["status"]["last_success"]["chart_count"], 17)
            self.assertEqual(result["status"]["last_success"]["relationship_count"], 12)
            self.assertEqual(result["status"]["last_success"]["parameter_surface_count"], 8)
            aliases = result["delivery"]["aliases"]
            self.assertTrue(aliases["dated_html"]["path"].startswith("history/2026-08-16/082000-"))
            self.assertTrue((base / "output" / aliases["dated_html"]["path"]).is_file())

    def test_no_key_delivers_current_context_without_flow_or_advice(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            runtime = runtime_fixture(Path(temporary), provider=None)
            result = runtime.run_once(now=NOW)
            report = result["report"]
            self.assertEqual(report["generation_status"], "interpretation_unavailable")
            self.assertEqual(report["macro_parameters"], {})
            self.assertEqual(report["parameter_basis"], [])
            self.assertEqual(report["insights"], [])
            self.assertEqual(report["observations"], [])
            self.assertEqual(len(report["charts"]), 17)
            self.assertEqual(len(report["parameter_surface"]), 1)
            self.assertEqual(report["parameter_surface"][0]["parameter"], "AS_OF")
            self.assertFalse(report["truth_boundary"]["macro_parameters_present"])
            self.assertEqual(
                result["status"]["last_success"]["generation_status"],
                "interpretation_unavailable",
            )

    def test_failed_final_delivery_readback_restores_exact_aliases_and_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            runtime = runtime_fixture(base, provider=DynamicProvider())
            runtime.run_once(now=NOW)
            watched = [
                base / "output" / "latest.html",
                base / "output" / "latest.md",
                runtime.delivery_store.state_path,
            ]
            before = {path: path.read_bytes() for path in watched}
            with patch.object(
                runtime.delivery_store,
                "latest",
                side_effect=KlineWorldRuntimeError("forced_final_readback"),
            ):
                with self.assertRaisesRegex(
                    KlineWorldRuntimeError, "forced_final_readback"
                ):
                    runtime.delivery_store.promote()
            self.assertEqual({path: path.read_bytes() for path in watched}, before)

    def test_status_is_read_only_strict_and_rejects_tamper(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            runtime = runtime_fixture(base, provider=DynamicProvider())
            runtime.run_once(now=NOW)
            before_tree = sorted(
                str(path.relative_to(base)) for path in base.rglob("*") if path.is_file()
            )
            runtime.status()
            after_tree = sorted(
                str(path.relative_to(base)) for path in base.rglob("*") if path.is_file()
            )
            self.assertEqual(before_tree, after_tree)
            status_path = base / "runtime" / "world-status.json"
            status = json.loads(status_path.read_text(encoding="utf-8"))
            status["last_success"]["chart_count"] = 16
            status_path.write_text(json.dumps(status), encoding="utf-8")
            with self.assertRaisesRegex(KlineWorldRuntimeError, "status_mismatch"):
                runtime.status()

    def test_phase_failure_publishes_unavailable_surface_and_persists_no_exception_detail(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            runtime = runtime_fixture(base, provider=DynamicProvider())
            first = runtime.run_once(now=NOW)
            watched = [
                base / "output" / first["delivery"]["aliases"]["dated_html"]["path"],
                base / "output" / first["delivery"]["aliases"]["dated_markdown"]["path"],
                runtime.delivery_store.state_path,
            ]
            before = {path: path.read_bytes() for path in watched}

            def fail_at_context(phase: str) -> None:
                if phase == "context_compile":
                    raise RuntimeError("credential detail /Users/example/.env")

            runtime.phase_observer = fail_at_context
            with self.assertRaisesRegex(KlineWorldRuntimeError, "run_failed"):
                runtime.run_once(now=NOW + timedelta(days=1))
            self.assertEqual({path: path.read_bytes() for path in watched}, before)
            latest_html = (base / "output" / "latest.html").read_text(encoding="utf-8")
            latest_markdown = (base / "output" / "latest.md").read_text(encoding="utf-8")
            self.assertIn("今日数据不可用", latest_html)
            self.assertIn("今日数据不可用", latest_markdown)
            self.assertNotIn(first["status"]["last_success"]["report_id"], latest_html)
            self.assertNotIn(first["status"]["last_success"]["report_id"], latest_markdown)
            surface = json.loads(
                runtime.delivery_store.surface_state_path.read_text(encoding="utf-8")
            )
            self.assertEqual(surface["state"], "unavailable")
            status = runtime.status()
            self.assertEqual(status["state"], "failed")
            self.assertEqual(
                status["last_success"]["delivery_id"],
                first["status"]["last_success"]["delivery_id"],
            )
            self.assertEqual(status["last_failure"]["code"], "run_failed")
            self.assertEqual(status["last_failure"]["phase"], "context_compile")
            encoded = json.dumps(status, ensure_ascii=False)
            self.assertNotIn("credential", encoded)
            self.assertNotIn("/Users", encoded)

    def test_same_day_runs_keep_distinct_immutable_history_editions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            runtime = runtime_fixture(base, provider=DynamicProvider())
            first = runtime.run_once(now=NOW)
            first_html = first["delivery"]["aliases"]["dated_html"]
            first_markdown = first["delivery"]["aliases"]["dated_markdown"]
            first_html_bytes = (base / "output" / first_html["path"]).read_bytes()
            first_markdown_bytes = (base / "output" / first_markdown["path"]).read_bytes()

            second = runtime.run_once(now=NOW + timedelta(hours=1))
            second_html = second["delivery"]["aliases"]["dated_html"]
            second_markdown = second["delivery"]["aliases"]["dated_markdown"]
            self.assertNotEqual(first_html["path"], second_html["path"])
            self.assertNotEqual(first_markdown["path"], second_markdown["path"])
            self.assertTrue(second_html["path"].startswith("history/2026-08-16/092000-"))
            self.assertEqual((base / "output" / first_html["path"]).read_bytes(), first_html_bytes)
            self.assertEqual(
                (base / "output" / first_markdown["path"]).read_bytes(),
                first_markdown_bytes,
            )
            self.assertEqual(
                (base / "output" / "latest.html").read_bytes(),
                (base / "output" / second_html["path"]).read_bytes(),
            )

    def test_runner_lock_contention_exits_without_touching_daily_or_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            runtime_root = base / "runtime"
            runtime_root.mkdir()
            lock_path = runtime_root / "run.lock"
            before_output = list((base / "output").glob("*")) if (base / "output").exists() else []
            with lock_path.open("a+b") as handle:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                result = subprocess.run(
                    [
                        sys.executable,
                        str(ROOT / "scripts" / "run_market_regime_kline_newsletter.py"),
                        "--daily-root",
                        str(base / "daily"),
                        "--runtime-root",
                        str(runtime_root),
                        "--output-root",
                        str(base / "output"),
                        "--no-llm",
                    ],
                    text=True,
                    capture_output=True,
                    check=False,
                )
            self.assertEqual(result.returncode, 75, result.stderr)
            self.assertEqual(json.loads(result.stdout)["code"], "run_lock_busy")
            self.assertEqual(
                list((base / "output").glob("*")) if (base / "output").exists() else [],
                before_output,
            )

    def test_existing_launchd_contract_remains_one_track2_job_at_0820(self) -> None:
        payload = build_plist(
            app_root=Path("/Applications/ParkKlineNewsletter/app"),
            runtime_root=Path("/Library/Application Support/ParkKlineDaily/runtime"),
            output_root=Path("/Desktop/K线日报"),
            archive_root=Path("/park-hands/007_kline daily newsletter"),
            key_file=Path("/secrets/deepseek-key"),
            feishu_env_file=Path("/secrets/daily-feishu.env"),
            python=Path("/usr/bin/python3"),
        )
        encoded = plistlib.dumps(payload)
        decoded = plistlib.loads(encoded)
        self.assertEqual(decoded["Label"], LABEL)
        self.assertEqual(decoded["StartCalendarInterval"], {"Hour": 8, "Minute": 20})
        self.assertEqual(
            sum("run_market_regime_daily_delivery.py" in value for value in decoded["ProgramArguments"]),
            1,
        )
        self.assertIn("--feishu-env-file", decoded["ProgramArguments"])
        self.assertNotIn("finance", encoded.decode().lower())


if __name__ == "__main__":
    unittest.main()
