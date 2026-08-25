from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
import unittest

PRODUCT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(PRODUCT))

from data_core.market_regime_llm_provider import (  # noqa: E402
    CodexCliProvider,
    ProviderFallbackError,
    ValidatedFallbackProvider,
)


class LlmProviderTests(unittest.TestCase):
    def test_codex_cli_is_read_only_and_returns_structured_json(self) -> None:
        calls: list[dict[str, object]] = []

        def runner(command, *, cwd, timeout):
            calls.append({"command": command, "cwd": cwd, "timeout": timeout})
            output_path = Path(command[command.index("--output-last-message") + 1])
            output_path.write_text(json.dumps({"ok": True}, ensure_ascii=False), encoding="utf-8")
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        provider = CodexCliProvider(
            system_prompt="只返回 JSON。",
            executable="codex",
            runner=runner,
            cli_version="codex-cli-test",
        )
        output, receipt = provider({"asset_key": "dxy", "evidence_ids": ["e:dxy"]})

        command = calls[0]["command"]
        self.assertEqual(output, {"ok": True})
        self.assertEqual(receipt["provider"], "Codex CLI")
        self.assertEqual(receipt["cli_version"], "codex-cli-test")
        self.assertIn("--ephemeral", command)
        self.assertIn("--sandbox", command)
        self.assertIn("read-only", command)
        self.assertIn("--skip-git-repo-check", command)
        self.assertIn("--json", command)
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", command)

    def test_fallback_keeps_primary_success_and_does_not_call_codex(self) -> None:
        fallback_calls: list[object] = []

        def validate(output, _request):
            if output.get("status") != "valid":
                raise ValueError("schema_invalid")

        provider = ValidatedFallbackProvider(
            primary=lambda _request: ({"status": "valid"}, {"provider": "DeepSeek", "attempt_count": 1}),
            fallback=lambda _request: fallback_calls.append(True),
            validator=validate,
        )
        output, receipt = provider({"evidence_ids": ["e:1"]})
        self.assertEqual(output["status"], "valid")
        self.assertFalse(fallback_calls)
        self.assertEqual(receipt["provider"], "DeepSeek")
        self.assertFalse(receipt["fallback_used"])

    def test_fallback_switches_after_any_primary_failure_and_records_reason(self) -> None:
        def validate(output, _request):
            if output.get("status") != "valid":
                raise ValueError("schema_invalid")

        provider = ValidatedFallbackProvider(
            primary=lambda _request: (_ for _ in ()).throw(RuntimeError("402 Insufficient Balance")),
            fallback=lambda _request: ({"status": "valid"}, {"provider": "Codex CLI", "cli_version": "test"}),
            validator=validate,
        )
        output, receipt = provider({"evidence_ids": ["e:1"]})
        self.assertEqual(output["status"], "valid")
        self.assertEqual(receipt["provider"], "Codex CLI")
        self.assertTrue(receipt["fallback_used"])
        self.assertEqual(receipt["fallback_reason"], "http_402")
        self.assertEqual(receipt["primary_provider"], "DeepSeek")

    def test_both_fail_raises_typed_failure_without_old_output(self) -> None:
        fallback_calls = []

        def validate(_output, _request):
            raise ValueError("evidence_invalid")

        provider = ValidatedFallbackProvider(
            primary=lambda _request: (_ for _ in ()).throw(RuntimeError("primary_down")),
            fallback=lambda _request: (fallback_calls.append(True) or (_ for _ in ()).throw(TimeoutError("fallback_down"))),
            validator=validate,
        )
        with self.assertRaises(ProviderFallbackError) as context:
            provider({"evidence_ids": ["e:1"]})
        self.assertEqual(context.exception.code, "both_providers_failed")
        self.assertIn("RuntimeError", context.exception.primary_failure)
        self.assertEqual(context.exception.fallback_failure, "timeout")
        self.assertEqual(len(fallback_calls), 3)


if __name__ == "__main__":
    unittest.main()
