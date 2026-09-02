#!/usr/bin/env python3
"""Install, inspect, or remove the 08:20 Daily K-line Newsletter LaunchAgent."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
from typing import Any


LABEL = "com.park.market-regime.kline-newsletter"


def build_plist(
    *,
    app_root: Path,
    runtime_root: Path,
    output_root: Path,
    archive_root: Path,
    key_file: Path,
    feishu_env_file: Path,
    python: Path,
) -> dict[str, Any]:
    logs = runtime_root / "logs"
    return {
        "Label": LABEL,
        "ProgramArguments": [
            str(python),
            str(app_root / "scripts" / "run_market_regime_daily_delivery.py"),
            "--runtime-root",
            str(runtime_root),
            "--output-root",
            str(output_root),
            "--archive-root",
            str(archive_root),
            "--key-file",
            str(key_file),
            "--feishu-env-file",
            str(feishu_env_file),
        ],
        "WorkingDirectory": str(app_root),
        "StartCalendarInterval": {"Hour": 8, "Minute": 20},
        "RunAtLoad": False,
        "ProcessType": "Background",
        "StandardOutPath": str(logs / "stdout.log"),
        "StandardErrorPath": str(logs / "stderr.log"),
        "EnvironmentVariables": {
            "PYTHONUNBUFFERED": "1",
            "HOME": str(Path.home()),
            "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
            "CODEX_HOME": str(Path.home() / ".codex"),
        },
    }


def _run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=check, text=True, capture_output=True)


def main() -> int:
    home = Path.home()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("install", "status", "uninstall", "render"))
    parser.add_argument("--app-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--runtime-root",
        type=Path,
        default=home / "Library" / "Application Support" / "ParkKlineDaily" / "runtime",
    )
    parser.add_argument("--output-root", type=Path, default=home / "Desktop" / "K线日报")
    parser.add_argument(
        "--archive-root",
        type=Path,
        default=home / "park-hands" / "007_kline daily newsletter",
    )
    parser.add_argument(
        "--key-file", type=Path, default=home / "park-hands" / "_secrets" / "deepseek-key"
    )
    parser.add_argument(
        "--feishu-env-file",
        type=Path,
        default=home / "Library" / "Application Support" / "ParkKlineDaily" / "daily-feishu.env",
    )
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    args = parser.parse_args()
    uid = os.getuid()
    domain = f"gui/{uid}"
    service = f"{domain}/{LABEL}"
    plist_path = home / "Library" / "LaunchAgents" / f"{LABEL}.plist"
    values = {
        name: value.expanduser().resolve()
        for name, value in {
            "app_root": args.app_root,
            "runtime_root": args.runtime_root,
            "output_root": args.output_root,
            "archive_root": args.archive_root,
            "key_file": args.key_file,
            "feishu_env_file": args.feishu_env_file,
            "python": args.python,
        }.items()
    }
    payload = build_plist(**values)
    if args.command == "status":
        result = _run("launchctl", "print", service, check=False)
        sys.stdout.write(result.stdout if result.returncode == 0 else result.stderr)
        return result.returncode
    if args.command == "uninstall":
        _run("launchctl", "bootout", service, check=False)
        if plist_path.exists():
            plist_path.unlink()
        return 0
    encoded = plistlib.dumps(payload, fmt=plistlib.FMT_XML, sort_keys=True)
    if args.command == "render":
        sys.stdout.buffer.write(encoded)
        return 0
    script = values["app_root"] / "scripts" / "run_market_regime_daily_delivery.py"
    if not script.is_file() or not values["runtime_root"].is_dir():
        raise SystemExit("app script or Daily runtime is unavailable")
    if not values["feishu_env_file"].is_file():
        raise SystemExit("Daily Feishu env file is unavailable")
    values["runtime_root"].mkdir(parents=True, exist_ok=True)
    (values["runtime_root"] / "logs").mkdir(parents=True, exist_ok=True)
    values["output_root"].mkdir(parents=True, exist_ok=True)
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{plist_path.name}.", dir=plist_path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, plist_path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    _run("launchctl", "bootout", service, check=False)
    _run("launchctl", "bootstrap", domain, str(plist_path))
    _run("launchctl", "enable", service)
    result = _run("launchctl", "print", service)
    sys.stdout.write(result.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
