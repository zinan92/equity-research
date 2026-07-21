#!/usr/bin/env python3
"""Verify the private-beta repository baseline without touching user runtime."""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_TRACKED_PARTS = (
    "/runtime/",
    "/.cache/",
    "/node_modules/",
    "/.venv/",
    "/.playwright-mcp/",
    "/.scatter/",
    "/.auth/",
)
FORBIDDEN_TRACKED_NAMES = {
    ".env",
    "cookies.json",
    "credentials.json",
    "service-account.json",
    "session.json",
    ".npmrc",
    ".pypirc",
    ".envrc",
}
FORBIDDEN_TRACKED_SUFFIXES = (".db", ".sqlite", ".sqlite3", ".pem", ".p12", ".key")


def run(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    timeout: float = 120,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def tracked_file_audit() -> dict[str, object]:
    tracked_result = run(["git", "ls-files", "-z", "--cached"])
    pending_result = run(["git", "ls-files", "-z", "--others", "--exclude-standard"])
    tracked = [item for item in tracked_result.stdout.split("\0") if item]
    pending = [item for item in pending_result.stdout.split("\0") if item]
    forbidden = []
    for relative in tracked + pending:
        normalized = f"/{relative}"
        name = Path(relative).name.lower()
        is_environment_file = name.startswith(".env.") and name != ".env.example"
        is_browser_state = name.endswith(".json") and ("cookie" in name or "session" in name)
        if (
            name in FORBIDDEN_TRACKED_NAMES
            or name.endswith(FORBIDDEN_TRACKED_SUFFIXES)
            or is_environment_file
            or is_browser_state
            or any(part in normalized for part in FORBIDDEN_TRACKED_PARTS)
        ):
            forbidden.append(relative)
    if forbidden:
        raise RuntimeError(f"forbidden runtime or secret-like files are tracked or pending: {forbidden}")
    return {
        "tracked_files": len(tracked),
        "pending_untracked_files": len(pending),
        "forbidden_tracked_or_pending": forbidden,
    }


def unit_tests() -> dict[str, object]:
    result = run([sys.executable, "-m", "unittest", "discover", "-s", "product/tests", "-q"])
    output = (result.stdout + result.stderr).strip()
    lines = [line for line in output.splitlines() if line.startswith("Ran ") or line == "OK"]
    match = re.search(r"Ran (\d+) tests?", output)
    count = int(match.group(1)) if match else 0
    if count < 79 or "OK" not in lines:
        raise RuntimeError(f"expected at least 79 passing product tests, got: {output}")
    return {"status": "passed", "test_count": count, "summary": lines}


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def server_smoke() -> dict[str, object]:
    port = free_port()
    with tempfile.TemporaryDirectory(prefix="equity-research-baseline-") as temporary:
        db_path = Path(temporary) / "baseline.db"
        env = dict(os.environ)
        env.update({
            "PARK_DASHBOARD_DB": str(db_path),
            "PARK_AUTH_REQUIRED": "0",
            "PARK_COOKIE_SECURE": "0",
        })
        process = subprocess.Popen(
            [sys.executable, "product/server.py", "--host", "127.0.0.1", "--port", str(port)],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            deadline = time.monotonic() + 15
            health: dict[str, object] | None = None
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    output = process.stdout.read() if process.stdout else ""
                    raise RuntimeError(f"server exited before health check: {output}")
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1) as response:
                        health = json.load(response)
                    break
                except Exception:
                    time.sleep(0.15)
            if health is None:
                raise RuntimeError("server health check timed out")
            if health.get("status") != "ok" or health.get("errors") != [] or health.get("data_mode") != "DEMO":
                raise RuntimeError(f"unexpected fresh-clone health payload: {health}")
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/dashboard", timeout=3) as response:
                dashboard = json.load(response)
            if len(dashboard.get("positions") or []) != 8 or dashboard.get("snapshot", {}).get("data_mode") != "DEMO":
                raise RuntimeError("dashboard smoke response is not the expected 8-position DEMO baseline")
            return {
                "status": "passed",
                "health": health,
                "positions": len(dashboard["positions"]),
                "temporary_database": True,
            }
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, help="Optional JSON receipt path")
    args = parser.parse_args()
    receipt = {
        "objective": "fresh-clone repository baseline",
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "python": sys.version.split()[0],
        "tracked_file_audit": tracked_file_audit(),
        "unit_tests": unit_tests(),
        "server_smoke": server_smoke(),
        "status": "passed",
    }
    if args.receipt:
        target = args.receipt if args.receipt.is_absolute() else ROOT / args.receipt
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
