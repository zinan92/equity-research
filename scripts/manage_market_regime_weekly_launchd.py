#!/usr/bin/env python3
"""Install, inspect, or remove the independent Weekly K-line LaunchAgent."""

from __future__ import annotations

import argparse
from pathlib import Path
import plistlib
import os
import subprocess
import sys
import tempfile


LABEL = "com.park.market-regime.kline-weekly"
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNTIME_ROOT = Path.home() / "Library" / "Application Support" / "ParkWeeklyMacroKline" / "runtime"
DEFAULT_OUTPUT_ROOT = Path.home() / "Desktop" / "宏观K线周报"
DEFAULT_ARCHIVE_ROOT = Path.home() / "park-hands" / "008_finance weekly newsletter"
DEFAULT_ENV_FILE = Path(
    "/Users/wendy/Library/Application Support/ParkWeeklyMacroKline/kline-feishu.env"
)
DEFAULT_KEY_FILE = Path.home() / "park-hands" / "_secrets" / "deepseek-key"


def _domain() -> str:
    return f"gui/{os.getuid()}"


def _plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def build_plist(*, runtime_root: Path, output_root: Path, archive_root: Path, key_file: Path, feishu_env_file: Path, python_executable: str = sys.executable) -> dict:
    logs = runtime_root / "logs"
    return {
        "Label": LABEL,
        "ProgramArguments": [
            python_executable,
            str(ROOT / "scripts" / "run_market_regime_weekly_delivery.py"),
            "--runtime-root", str(runtime_root),
            "--output-root", str(output_root),
            "--archive-root", str(archive_root),
            "--key-file", str(key_file),
            "--feishu-env-file", str(feishu_env_file),
        ],
        "WorkingDirectory": str(ROOT),
        "EnvironmentVariables": {
            "PYTHONUNBUFFERED": "1",
            "HOME": str(Path.home()),
            "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
            "CODEX_HOME": str(Path.home() / ".codex"),
        },
        "ProcessType": "Background",
        "RunAtLoad": False,
        "StartCalendarInterval": {"Weekday": 1, "Hour": 8, "Minute": 20},
        "StandardOutPath": str(logs / "weekly-kline.stdout.log"),
        "StandardErrorPath": str(logs / "weekly-kline.stderr.log"),
    }


def _write_plist(path: Path, payload: dict) -> None:
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


def _launchctl(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["launchctl", *args], capture_output=True, text=True, check=check)


def install(*, runtime_root: Path, output_root: Path, archive_root: Path, key_file: Path, feishu_env_file: Path, load: bool = True) -> Path:
    path = _plist_path()
    _write_plist(path, build_plist(runtime_root=runtime_root, output_root=output_root, archive_root=archive_root, key_file=key_file, feishu_env_file=feishu_env_file, python_executable=sys.executable))
    if load:
        _launchctl("bootout", f"{_domain()}/{LABEL}", check=False)
        _launchctl("bootstrap", _domain(), str(path))
        _launchctl("enable", f"{_domain()}/{LABEL}")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "status", "uninstall"))
    parser.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--archive-root", type=Path, default=DEFAULT_ARCHIVE_ROOT)
    parser.add_argument("--key-file", type=Path, default=DEFAULT_KEY_FILE)
    parser.add_argument("--feishu-env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--kickstart", action="store_true")
    args = parser.parse_args()
    target = f"{_domain()}/{LABEL}"
    if args.action == "install":
        path = install(
            runtime_root=args.runtime_root.expanduser().resolve(),
            output_root=args.output_root.expanduser().resolve(),
            archive_root=args.archive_root.expanduser().resolve(),
            key_file=args.key_file.expanduser().resolve(),
            feishu_env_file=args.feishu_env_file.expanduser().resolve(),
        )
        if args.kickstart:
            _launchctl("kickstart", "-k", target)
        print(path)
        return 0
    if args.action == "status":
        result = _launchctl("print", target, check=False)
        print(result.stdout if result.returncode == 0 else result.stderr)
        return result.returncode
    _launchctl("bootout", target, check=False)
    path = _plist_path()
    if path.exists():
        path.unlink()
    print(f"uninstalled {LABEL}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
