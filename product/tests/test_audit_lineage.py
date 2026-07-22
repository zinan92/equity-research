from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "docs" / "governance" / "audit-lineage-v1.json"
VERIFY = ROOT / "scripts" / "verify_audit_lineage.py"


class AuditLineageTests(unittest.TestCase):
    def run_verify(self, ledger: Path, *extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(VERIFY), "--ledger", str(ledger), "--repo", str(ROOT), *extra],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_repository_ledger_and_git_history_verify(self) -> None:
        result = self.run_verify(LEDGER)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("verified 11 reconstructed audit entries", result.stdout)

    def test_duplicate_reference_is_rejected(self) -> None:
        payload = json.loads(LEDGER.read_text(encoding="utf-8"))
        payload["entries"][1]["missing_reference"] = 79
        with tempfile.TemporaryDirectory() as temporary:
            ledger = Path(temporary) / "ledger.json"
            ledger.write_text(json.dumps(payload), encoding="utf-8")
            result = self.run_verify(ledger, "--no-git")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing_reference", result.stdout)

    def test_short_commit_is_rejected(self) -> None:
        payload = json.loads(LEDGER.read_text(encoding="utf-8"))
        payload["entries"][0]["reference_commit"] = "43a127b"
        with tempfile.TemporaryDirectory() as temporary:
            ledger = Path(temporary) / "ledger.json"
            ledger.write_text(json.dumps(payload), encoding="utf-8")
            result = self.run_verify(ledger, "--no-git")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("full lowercase SHA", result.stdout)


if __name__ == "__main__":
    unittest.main()
