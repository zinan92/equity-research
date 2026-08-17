#!/usr/bin/env python3
"""Run or inspect the independent local Track 2 K-line Daily Newsletter."""
from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
PRODUCT = ROOT / "product"
sys.path.insert(0, str(PRODUCT))

from data_core.market_regime_kline_world_runtime import (  # noqa: E402
    SCHEMA_VERSION,
    KlineWorldRuntime,
    KlineWorldRuntimeError,
)


def _defaults() -> tuple[Path, Path, Path, Path]:
    home = Path.home()
    return (
        Path(
            os.getenv(
                "PARK_MARKET_REGIME_ROOT",
                home / "Library" / "Application Support" / "ParkMarketRegime" / "runtime",
            )
        ),
        Path(
            os.getenv(
                "PARK_KLINE_NEWSLETTER_RUNTIME",
                home / "Library" / "Application Support" / "ParkKlineNewsletter" / "runtime",
            )
        ),
        Path(
            os.getenv(
                "PARK_KLINE_NEWSLETTER_OUTPUT",
                home / "Desktop" / "K线日报",
            )
        ),
        Path(
            os.getenv(
                "DEEPSEEK_API_KEY_FILE",
                home / "park-hands" / "_secrets" / "deepseek-key",
            )
        ),
    )


def _safe_summary(result: dict) -> dict:
    delivery = result.get("delivery") or {}
    status = result.get("status") or {}
    success = status.get("last_success") or {}
    return {
        "schema_version": SCHEMA_VERSION,
        "state": "completed",
        "delivery_id": success.get("delivery_id"),
        "report_id": success.get("report_id"),
        "report_date": success.get("report_date"),
        "posture": success.get("posture"),
        "generation_status": success.get("generation_status"),
        "chart_count": success.get("chart_count"),
        "relationship_count": success.get("relationship_count"),
        "parameter_basis_count": success.get("parameter_basis_count"),
        "insight_count": success.get("insight_count"),
        "observation_count": success.get("observation_count"),
        "missing_data_count": success.get("missing_data_count"),
        "macro_parameters_present": (
            delivery.get("truth_boundary") or {}
        ).get("macro_parameters_present"),
        "individual_security_advice": False,
        "publication_eligible": False,
        "automatic_execution_eligible": False,
    }


def _safe_status(status: dict) -> dict:
    success = status.get("last_success") or {}
    return {
        "schema_version": SCHEMA_VERSION,
        "state": status.get("state"),
        "last_success": success or None,
        "last_failure": status.get("last_failure"),
        "publication_eligible": False,
        "automatic_execution_eligible": False,
    }


def main() -> int:
    daily_default, runtime_default, output_default, key_default = _defaults()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--daily-root", type=Path, default=daily_default)
    parser.add_argument("--runtime-root", type=Path, default=runtime_default)
    parser.add_argument("--output-root", type=Path, default=output_default)
    parser.add_argument("--key-file", type=Path, default=key_default)
    parser.add_argument("--no-llm", action="store_true")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()
    runtime_root = args.runtime_root.expanduser().resolve()
    output_root = args.output_root.expanduser().resolve()
    runtime = KlineWorldRuntime(
        daily_root=args.daily_root,
        runtime_root=runtime_root,
        output_root=output_root,
        key_file=None if args.no_llm else args.key_file,
    )
    if args.status:
        try:
            status = runtime.status()
        except KlineWorldRuntimeError as exc:
            print(
                json.dumps(
                    {
                        "schema_version": SCHEMA_VERSION,
                        "state": "unavailable",
                        "code": str(exc),
                        "publication_eligible": False,
                        "action_eligible": False,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 2 if (runtime_root / "world-status.json").exists() else 0
        print(json.dumps(_safe_status(status), ensure_ascii=False, indent=2))
        return 0

    runtime_root.mkdir(parents=True, exist_ok=True)
    lock_path = runtime_root / "run.lock"
    with lock_path.open("a+b") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(
                json.dumps(
                    {
                        "schema_version": SCHEMA_VERSION,
                        "state": "busy",
                        "code": "run_lock_busy",
                    },
                    ensure_ascii=False,
                )
            )
            return 75
        try:
            result = runtime.run_once()
        except KlineWorldRuntimeError as exc:
            print(
                json.dumps(
                    {
                        "schema_version": SCHEMA_VERSION,
                        "state": "failed",
                        "code": str(exc),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 2
    print(json.dumps(_safe_summary(result), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
