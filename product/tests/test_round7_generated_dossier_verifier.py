import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.verify_round7_generated_dossier import _is_persistent_artifact  # noqa: E402


class Round7GeneratedDossierVerifierTests(unittest.TestCase):
    def test_persistent_artifact_identity_is_checkout_prefix_independent(self):
        actual = ROOT / "artifacts" / "round7-dossiers" / "300750.SZ.md"
        self.assertTrue(
            _is_persistent_artifact(
                "/Users/park/original-checkout/artifacts/round7-dossiers/300750.SZ.md",
                actual,
            )
        )
        self.assertTrue(
            _is_persistent_artifact("artifacts/round7-dossiers/300750.SZ.md", actual)
        )
        self.assertFalse(
            _is_persistent_artifact(
                "/private/tmp/generated/artifacts/round7-dossiers/300750.SZ.md",
                actual,
            )
        )
        self.assertFalse(
            _is_persistent_artifact(
                "/Users/park/original-checkout/artifacts/other/300750.SZ.md",
                actual,
            )
        )
        self.assertFalse(
            _is_persistent_artifact(
                "/Users/park/original-checkout/artifacts/round7-dossiers/600519.SH.md",
                actual,
            )
        )
        with tempfile.TemporaryDirectory() as directory:
            self.assertFalse(
                _is_persistent_artifact(
                    "/Users/park/original-checkout/artifacts/round7-dossiers/300750.SZ.md",
                    Path(directory) / "300750.SZ.md",
                )
            )

    def test_canonical_catl_artifact_passes_replay_verifier(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "verification.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/verify_round7_generated_dossier.py",
                    "300750.SZ",
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertTrue(payload["passed"], payload)
            self.assertEqual(payload["tier"], "B")
            self.assertEqual(len(payload["accepted_model_request_ids"]), 8)


if __name__ == "__main__":
    unittest.main()
