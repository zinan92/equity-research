from __future__ import annotations

import plistlib
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from manage_market_regime_launchd import (  # noqa: E402
    INTRADAY_SCHEDULER_LABEL,
    LABELS,
    LaunchdManagementError,
    SCHEDULER_LABEL,
    WEB_LABEL,
    build_service_plists,
    install,
    set_intraday_enabled,
    uninstall,
)


class MarketRegimeLaunchdTest(unittest.TestCase):
    def test_plists_are_loopback_keepalive_and_use_external_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state"
            plists = build_service_plists(
                repo_root=ROOT,
                state_root=state,
                python_executable=sys.executable,
                interval_hours=4,
                port=8896,
            )
            self.assertEqual(
                set(plists),
                {SCHEDULER_LABEL, INTRADAY_SCHEDULER_LABEL, WEB_LABEL},
            )
            scheduler = plists[SCHEDULER_LABEL]
            intraday = plists[INTRADAY_SCHEDULER_LABEL]
            web = plists[WEB_LABEL]
            self.assertTrue(scheduler["KeepAlive"])
            self.assertEqual(intraday["KeepAlive"], {"SuccessfulExit": False})
            self.assertTrue(web["KeepAlive"])
            self.assertTrue(scheduler["RunAtLoad"])
            self.assertEqual(scheduler["ProgramArguments"][-1], "4")
            self.assertEqual(intraday["ProgramArguments"][-1], "15")
            self.assertIn(
                "run_market_regime_intraday_scheduler.py",
                intraday["ProgramArguments"][1],
            )
            self.assertIn("127.0.0.1", web["ProgramArguments"])
            self.assertIn("8896", web["ProgramArguments"])
            runtime = Path(web["EnvironmentVariables"]["PARK_MARKET_REGIME_ROOT"])
            self.assertEqual(runtime, state.resolve() / "runtime")
            self.assertNotIn("0.0.0.0", web["ProgramArguments"])
            self.assertEqual(web["EnvironmentVariables"]["PARK_AUTH_REQUIRED"], "0")
            self.assertEqual(web["EnvironmentVariables"]["PARK_PRIVATE_PREVIEW"], "0")

    def test_install_without_launchctl_writes_parseable_plists_and_uninstalls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / "state"
            agents = root / "agents"
            receipt = install(
                repo_root=ROOT,
                state_root=state,
                launch_agents_root=agents,
                interval_hours=12,
                port=8898,
                load=False,
            )
            self.assertEqual(receipt["status"], "written_not_loaded")
            self.assertEqual(receipt["interval_hours"], 12)
            self.assertEqual(receipt["intraday_interval_minutes"], 15)
            for label in LABELS:
                path = Path(receipt["plists"][label])
                self.assertTrue(path.is_file())
                with path.open("rb") as handle:
                    self.assertEqual(plistlib.load(handle)["Label"], label)
            removed = uninstall(
                state_root=state,
                launch_agents_root=agents,
                load=False,
            )
            self.assertEqual(len(removed["removed"]), 3)
            self.assertEqual(Path(removed["runtime_preserved"]), state.resolve())
            self.assertTrue(state.is_dir())

    def test_invalid_interval_and_port_fail_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            with self.assertRaisesRegex(LaunchdManagementError, "4 or 12"):
                build_service_plists(repo_root=ROOT, state_root=state, interval_hours=6)
            with self.assertRaisesRegex(LaunchdManagementError, "15 minutes"):
                build_service_plists(
                    repo_root=ROOT,
                    state_root=state,
                    intraday_interval_minutes=5,
                )
            with self.assertRaisesRegex(LaunchdManagementError, "port"):
                build_service_plists(repo_root=ROOT, state_root=state, port=80)

    def test_intraday_stop_switch_is_reversible_without_deleting_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / "state"
            agents = root / "agents"
            stopped = set_intraday_enabled(
                enabled=False,
                state_root=state,
                launch_agents_root=agents,
                load=False,
            )
            marker = Path(stopped["stop_switch"])
            self.assertTrue(marker.is_file())
            self.assertEqual(stopped["status"], "stopped")
            runtime = state / "runtime"
            sentinel = runtime / "keep-me.json"
            sentinel.write_text("{}", encoding="utf-8")
            started = set_intraday_enabled(
                enabled=True,
                state_root=state,
                launch_agents_root=agents,
                load=False,
            )
            self.assertEqual(started["status"], "started")
            self.assertFalse(marker.exists())
            self.assertTrue(sentinel.is_file())


if __name__ == "__main__":
    unittest.main()
