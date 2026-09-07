from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest

PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT))

from market_regime_retention import MarketRegimeRetention, runtime_bytes  # noqa: E402


NOW = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)


def write_json(root: Path, relative: str, payload: dict) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


class MarketRegimeRetentionTest(unittest.TestCase):
    def test_resolved_root_reference_graph_and_temp_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "ssd-runtime"
            link = Path(directory) / "runtime-link"
            target.mkdir()
            link.symlink_to(target, target_is_directory=True)
            old = "old-run"
            recent = "recent-run"
            write_json(
                target,
                "latest.json",
                {
                    "instruments": [
                        {"normalized_artifact": {"path": f"intraday/normalized/{old}/keep.json"}},
                    ]
                },
            )
            write_json(target, f"intraday/runs/{recent}.json", {"run_id": recent, "completed_at": "2026-09-06T12:00:00Z", "raw_path": f"intraday/raw/{recent}/keep.bin"})
            write_json(target, f"run-events/{old}/001-completed.json", {"run_id": old, "completed_at": "2026-08-01T12:00:00Z", "raw_path": f"intraday/raw/{old}/event.bin"})
            write_json(target, "intraday/latest.json", {"snapshot": {"path": "intraday/snapshots/live.json"}})
            write_json(target, "api/latest.json", {"artifact": {"path": "api/artifacts/live.json"}})
            for relative in (
                f"intraday/raw/{old}/delete.bin",
                f"intraday/raw/{old}/event.bin",
                f"intraday/raw/{recent}/keep.bin",
                f"intraday/normalized/{old}/keep.json",
                "intraday/snapshots/live.json",
                "api/artifacts/live.json",
            ):
                path = target / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(relative.encode())
            (target / "intraday" / "raw" / old).mkdir(parents=True, exist_ok=True)
            (target / "intraday" / "raw" / old / "delete.bin").write_bytes(b"delete")
            (target / "intraday" / "raw" / recent).mkdir(parents=True, exist_ok=True)
            (target / "intraday" / "raw" / recent / "keep.bin").write_bytes(b"keep")
            (target / "api" / "artifacts" / ".live.json.in-progress").write_bytes(b"temp")

            result = MarketRegimeRetention(link, clock=lambda: NOW).prune(dry_run=False)

            self.assertEqual(result["root"], str(target.resolve()))
            self.assertFalse((target / "intraday" / "raw" / old / "delete.bin").exists())
            self.assertFalse((target / "intraday" / "raw" / old / "event.bin").exists())
            self.assertTrue((target / "intraday" / "normalized" / old / "keep.json").exists())
            self.assertTrue((target / "intraday" / "raw" / recent / "keep.bin").exists())
            self.assertFalse((target / "intraday" / "raw" / old / "delete.bin").exists())
            self.assertTrue((target / "intraday" / "raw" / recent / "keep.bin").exists())
            self.assertTrue((target / "api" / "artifacts" / ".live.json.in-progress").exists())

    def test_dry_run_does_not_write_or_delete(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "api" / "artifacts" / "old.json"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"old")
            result = MarketRegimeRetention(root, clock=lambda: NOW).prune()
            self.assertTrue(result["dry_run"])
            self.assertEqual(result["planned_delete_count"], 1)
            self.assertEqual(result["planned_delete_bytes"], 3)
            self.assertTrue(path.exists())
            self.assertFalse((root / "prune-receipt.json").exists())

    def test_runtime_bytes_uses_resolved_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "target"
            link = Path(directory) / "link"
            target.mkdir()
            (target / "one").write_bytes(b"123")
            link.symlink_to(target, target_is_directory=True)
            self.assertEqual(runtime_bytes(link), 3)


if __name__ == "__main__":
    unittest.main()
