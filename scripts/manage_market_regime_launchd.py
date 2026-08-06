#!/usr/bin/env python3
"""Install, inspect, or remove Park Market Regime user launch agents."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
from typing import Any
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
SCHEDULER_LABEL = "com.park.market-regime.scheduler"
WEB_LABEL = "com.park.market-regime.web"
LABELS = (SCHEDULER_LABEL, WEB_LABEL)


class LaunchdManagementError(RuntimeError):
    """The local launchd installation contract is invalid."""


def default_state_root() -> Path:
    return Path.home() / "Library" / "Application Support" / "ParkMarketRegime"


def default_launch_agents_root() -> Path:
    return Path.home() / "Library" / "LaunchAgents"


def _validate_repo_root(value: Path | str) -> Path:
    root = Path(value).expanduser().resolve()
    required = (
        root / "product" / "server.py",
        root / "scripts" / "run_market_regime_scheduler.py",
        root / "product" / "static" / "market-regime.html",
    )
    if not all(path.is_file() for path in required):
        raise LaunchdManagementError("repo root does not contain the Market Regime runtime")
    return root


def build_service_plists(
    *,
    repo_root: Path | str,
    state_root: Path | str,
    python_executable: Path | str = sys.executable,
    interval_hours: int = 4,
    port: int = 8896,
) -> dict[str, dict[str, Any]]:
    repo = _validate_repo_root(repo_root)
    state = Path(state_root).expanduser().resolve()
    python = Path(python_executable).expanduser().resolve()
    if interval_hours not in {4, 12}:
        raise LaunchdManagementError("interval must be 4 or 12 hours")
    if port < 1024 or port > 65535:
        raise LaunchdManagementError("port must be between 1024 and 65535")
    runtime = state / "runtime"
    logs = state / "logs"
    common = {
        "WorkingDirectory": str(repo),
        "RunAtLoad": True,
        "KeepAlive": True,
        "ProcessType": "Background",
        "ThrottleInterval": 10,
        "EnvironmentVariables": {
            "PYTHONUNBUFFERED": "1",
            "PARK_MARKET_REGIME_ROOT": str(runtime),
        },
    }
    scheduler = {
        **common,
        "Label": SCHEDULER_LABEL,
        "ProgramArguments": [
            str(python),
            str(repo / "scripts" / "run_market_regime_scheduler.py"),
            "--root",
            str(runtime),
            "--interval-hours",
            str(interval_hours),
        ],
        "StandardOutPath": str(logs / "scheduler.stdout.log"),
        "StandardErrorPath": str(logs / "scheduler.stderr.log"),
    }
    web_environment = {
        **common["EnvironmentVariables"],
        "PARK_DASHBOARD_DB": str(state / "dashboard.db"),
        "PARK_AUTH_REQUIRED": "0",
        "PARK_COOKIE_SECURE": "0",
        "PARK_PRIVATE_PREVIEW": "0",
        "PARK_MANUAL_PAID_PILOT": "0",
    }
    web = {
        **common,
        "Label": WEB_LABEL,
        "ProgramArguments": [
            str(python),
            str(repo / "product" / "server.py"),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        "EnvironmentVariables": web_environment,
        "StandardOutPath": str(logs / "web.stdout.log"),
        "StandardErrorPath": str(logs / "web.stderr.log"),
    }
    return {SCHEDULER_LABEL: scheduler, WEB_LABEL: web}


def _atomic_plist(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            plistlib.dump(payload, handle, fmt=plistlib.FMT_XML, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _launchctl(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["launchctl", *arguments],
        check=check,
        capture_output=True,
        text=True,
    )


def _domain() -> str:
    return f"gui/{os.getuid()}"


def install(
    *,
    repo_root: Path | str,
    state_root: Path | str,
    launch_agents_root: Path | str,
    interval_hours: int,
    port: int,
    python_executable: Path | str = sys.executable,
    load: bool = True,
) -> dict[str, Any]:
    state = Path(state_root).expanduser().resolve()
    agents = Path(launch_agents_root).expanduser().resolve()
    (state / "runtime").mkdir(parents=True, exist_ok=True)
    (state / "logs").mkdir(parents=True, exist_ok=True)
    plists = build_service_plists(
        repo_root=repo_root,
        state_root=state,
        python_executable=python_executable,
        interval_hours=interval_hours,
        port=port,
    )
    paths: dict[str, str] = {}
    for label, payload in plists.items():
        path = agents / f"{label}.plist"
        _atomic_plist(path, payload)
        paths[label] = str(path)
    if load:
        for label in LABELS:
            _launchctl("bootout", f"{_domain()}/{label}", check=False)
        for label in (SCHEDULER_LABEL, WEB_LABEL):
            _launchctl("bootstrap", _domain(), paths[label])
            _launchctl("enable", f"{_domain()}/{label}")
            _launchctl("kickstart", "-k", f"{_domain()}/{label}")
    return {
        "status": "installed" if load else "written_not_loaded",
        "repo_root": str(Path(repo_root).expanduser().resolve()),
        "state_root": str(state),
        "interval_hours": interval_hours,
        "url": f"http://127.0.0.1:{port}/market-regime",
        "plists": paths,
    }


def service_status(*, port: int, load: bool = True) -> dict[str, Any]:
    services: dict[str, Any] = {}
    for label in LABELS:
        if not load:
            services[label] = {"loaded": None}
            continue
        completed = _launchctl("print", f"{_domain()}/{label}", check=False)
        services[label] = {
            "loaded": completed.returncode == 0,
            "detail": "loaded" if completed.returncode == 0 else completed.stderr.strip(),
        }
    try:
        with urlopen(f"http://127.0.0.1:{port}/api/market-regime/health", timeout=2) as response:
            health = json.loads(response.read())
    except Exception as exc:
        health = {"status": "unavailable", "detail": f"{type(exc).__name__}: {exc}"}
    return {
        "services": services,
        "health": health,
        "url": f"http://127.0.0.1:{port}/market-regime",
    }


def uninstall(
    *,
    state_root: Path | str,
    launch_agents_root: Path | str,
    load: bool = True,
) -> dict[str, Any]:
    agents = Path(launch_agents_root).expanduser().resolve()
    removed: list[str] = []
    for label in LABELS:
        if load:
            _launchctl("bootout", f"{_domain()}/{label}", check=False)
        path = agents / f"{label}.plist"
        try:
            path.unlink()
        except FileNotFoundError:
            continue
        removed.append(str(path))
    return {
        "status": "uninstalled",
        "removed": removed,
        "runtime_preserved": str(Path(state_root).expanduser().resolve()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-root", type=Path, default=default_state_root())
    parser.add_argument("--launch-agents-root", type=Path, default=default_launch_agents_root())
    parser.add_argument("--port", type=int, default=8896)
    subparsers = parser.add_subparsers(dest="command", required=True)
    install_parser = subparsers.add_parser("install")
    install_parser.add_argument("--repo-root", type=Path, default=ROOT)
    install_parser.add_argument("--interval-hours", type=int, choices=(4, 12), default=4)
    install_parser.add_argument("--no-load", action="store_true")
    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--no-launchctl", action="store_true")
    uninstall_parser = subparsers.add_parser("uninstall")
    uninstall_parser.add_argument("--no-launchctl", action="store_true")
    args = parser.parse_args()
    if args.command == "install":
        result = install(
            repo_root=args.repo_root,
            state_root=args.state_root,
            launch_agents_root=args.launch_agents_root,
            interval_hours=args.interval_hours,
            port=args.port,
            load=not args.no_load,
        )
    elif args.command == "status":
        result = service_status(port=args.port, load=not args.no_launchctl)
    else:
        result = uninstall(
            state_root=args.state_root,
            launch_agents_root=args.launch_agents_root,
            load=not args.no_launchctl,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
