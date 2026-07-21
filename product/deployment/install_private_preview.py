#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import stat
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[2]
RUNNER_SOURCE = ROOT / "product" / "deployment" / "run_private_preview.py"
DEFAULT_RUNTIME = Path.home() / "Library" / "Application Support" / "Park Equity Research Preview"
APP_LABEL = "com.park.equity-research-preview"
TUNNEL_LABEL = "com.park.equity-research-tunnel"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_private(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}-{os.getpid()}")
    temporary.write_bytes(value)
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def app_plist(runtime: Path, python: Path, port: int) -> dict:
    runner = runtime / "bin" / "run_private_preview.py"
    return {
        "Label": APP_LABEL,
        "ProgramArguments": [
            str(python), str(runner),
            "--env-file", str(runtime / "preview.env"), "--port", str(port),
        ],
        "WorkingDirectory": str(runtime),
        "EnvironmentVariables": {"PYTHONUNBUFFERED": "1", "PYTHONDONTWRITEBYTECODE": "1"},
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 10,
        "StandardOutPath": str(runtime / "logs" / "server.out.log"),
        "StandardErrorPath": str(runtime / "logs" / "server.err.log"),
    }


def tunnel_plist(runtime: Path, cloudflared: Path, tunnel_id: str) -> dict:
    return {
        "Label": TUNNEL_LABEL,
        "ProgramArguments": [
            str(cloudflared), "tunnel", "--config", str(runtime / "cloudflared.yml"), "run", tunnel_id,
        ],
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 10,
        "StandardOutPath": str(runtime / "logs" / "cloudflared.out.log"),
        "StandardErrorPath": str(runtime / "logs" / "cloudflared.err.log"),
    }


def tunnel_config(tunnel_id: str, credential_file: Path, hostname: str, port: int) -> bytes:
    if not credential_file.is_file() or credential_file.is_symlink():
        raise RuntimeError("dedicated tunnel credential file is unavailable or unsafe")
    if stat.S_IMODE(credential_file.stat().st_mode) & 0o077:
        raise RuntimeError("dedicated tunnel credential file must be owner-only")
    if not hostname or "/" in hostname or hostname.startswith("http"):
        raise RuntimeError("invalid preview hostname")
    return (
        f"tunnel: {tunnel_id}\n"
        f"credentials-file: {credential_file.resolve()}\n"
        "metrics: 127.0.0.1:20389\n"
        "no-autoupdate: true\n\n"
        "ingress:\n"
        f"  - hostname: {hostname}\n"
        f"    service: http://127.0.0.1:{port}\n"
        "    originRequest:\n"
        "      connectTimeout: 10s\n"
        "  - service: http_status:404\n"
    ).encode()


def launchctl(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["launchctl", *args], check=check, text=True, capture_output=True)


def bootstrap_with_retry(domain: str, path: Path) -> None:
    label = path.stem
    for attempt in range(3):
        result = launchctl("bootstrap", domain, str(path), check=False)
        if result.returncode == 0:
            return
        loaded = launchctl("print", f"{domain}/{label}", check=False)
        if loaded.returncode == 0:
            return
        if attempt < 2:
            time.sleep(0.25 * (attempt + 1))
    raise RuntimeError(f"launchd bootstrap failed for {label}")


def ensure_running(domain: str, label: str, path: Path) -> None:
    target = f"{domain}/{label}"
    for attempt in range(12):
        status = launchctl("print", target, check=False)
        if status.returncode == 0 and "state = running" in status.stdout:
            return
        if status.returncode != 0:
            bootstrap_with_retry(domain, path)
        if attempt in {0, 4, 8}:
            launchctl("kickstart", "-k", target, check=False)
        time.sleep(0.5)
    raise RuntimeError(f"launchd service did not reach running state: {label}")


def install(args: argparse.Namespace) -> dict:
    runtime = args.runtime.expanduser().resolve()
    if not (runtime / "current" / "manifest.json").is_file() or not (runtime / "preview.env").is_file():
        raise RuntimeError("prepare_private_preview.py must complete before launchd installation")
    runtime.mkdir(parents=True, exist_ok=True)
    (runtime / "logs").mkdir(exist_ok=True)
    cloudflared = Path(args.cloudflared or shutil.which("cloudflared") or "")
    python = Path(args.python or sys.executable)
    if not cloudflared.is_file() or not python.is_file():
        raise RuntimeError("python or cloudflared binary is unavailable")
    write_private(runtime / "cloudflared.yml", tunnel_config(args.tunnel_id, args.credential_file, args.hostname, args.port))
    runner = runtime / "bin" / "run_private_preview.py"
    write_private(runner, RUNNER_SOURCE.read_bytes())
    os.chmod(runner, 0o700)
    validate = subprocess.run(
        [str(cloudflared), "tunnel", "--config", str(runtime / "cloudflared.yml"), "ingress", "validate"],
        check=False, text=True, capture_output=True,
    )
    if validate.returncode != 0:
        raise RuntimeError("cloudflared ingress validation failed")
    launch_agents = Path.home() / "Library" / "LaunchAgents"
    launch_agents.mkdir(parents=True, exist_ok=True)
    local_app = runtime / "launchd" / f"{APP_LABEL}.plist"
    local_tunnel = runtime / "launchd" / f"{TUNNEL_LABEL}.plist"
    write_private(local_app, plistlib.dumps(app_plist(runtime, python, args.port), sort_keys=False))
    write_private(local_tunnel, plistlib.dumps(tunnel_plist(runtime, cloudflared, args.tunnel_id), sort_keys=False))
    installed: list[Path] = []
    for source in (local_app, local_tunnel):
        target = launch_agents / source.name
        write_private(target, source.read_bytes())
        installed.append(target)
    domain = f"gui/{os.getuid()}"
    for label in (APP_LABEL, TUNNEL_LABEL):
        launchctl("bootout", f"{domain}/{label}", check=False)
    for path in installed:
        bootstrap_with_retry(domain, path)
    for label, path in zip((APP_LABEL, TUNNEL_LABEL), installed):
        ensure_running(domain, label, path)
    receipt = {
        "schema_version": "private-preview-launchd-install-v1",
        "status": "installed",
        "hostname": args.hostname,
        "tunnel_id": args.tunnel_id,
        "labels": [APP_LABEL, TUNNEL_LABEL],
        "app_plist_sha256": sha256(installed[0]),
        "tunnel_plist_sha256": sha256(installed[1]),
        "config_sha256": sha256(runtime / "cloudflared.yml"),
        "runtime_runner_sha256": sha256(runner),
        "runtime": str(runtime),
    }
    write_private(runtime / "launchd-install-receipt.json", json.dumps(receipt, ensure_ascii=False, indent=2).encode())
    return receipt


def uninstall() -> dict:
    domain = f"gui/{os.getuid()}"
    for label in (TUNNEL_LABEL, APP_LABEL):
        launchctl("bootout", f"{domain}/{label}", check=False)
        (Path.home() / "Library" / "LaunchAgents" / f"{label}.plist").unlink(missing_ok=True)
    return {"status": "uninstalled", "labels": [APP_LABEL, TUNNEL_LABEL]}


def main() -> None:
    parser = argparse.ArgumentParser(description="Install dedicated launch agents for the private preview")
    subcommands = parser.add_subparsers(dest="command", required=True)
    setup = subcommands.add_parser("install")
    setup.add_argument("--runtime", type=Path, default=DEFAULT_RUNTIME)
    setup.add_argument("--hostname", default="research.park-ai-intel.com")
    setup.add_argument("--tunnel-id", required=True)
    setup.add_argument("--credential-file", type=Path, required=True)
    setup.add_argument("--port", type=int, default=8878)
    setup.add_argument("--python", type=Path)
    setup.add_argument("--cloudflared", type=Path)
    subcommands.add_parser("uninstall")
    args = parser.parse_args()
    try:
        result = install(args) if args.command == "install" else uninstall()
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        raise SystemExit(f"private preview launchd install failed: {exc}") from exc
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
