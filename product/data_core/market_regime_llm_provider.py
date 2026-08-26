"""Audited provider boundary for DeepSeek primary and Codex CLI fallback."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any, Callable, Mapping


class ProviderFallbackError(RuntimeError):
    """Both explanation providers failed after validation boundaries."""

    code = "both_providers_failed"

    def __init__(self, primary_failure: str, fallback_failure: str) -> None:
        self.primary_failure = primary_failure
        self.fallback_failure = fallback_failure
        super().__init__(f"{self.code}:{primary_failure}:{fallback_failure}")


class CodexCliError(RuntimeError):
    """Codex CLI could not return a structured result."""


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _safe_failure(exc: BaseException) -> str:
    if isinstance(exc, ProviderFallbackError):
        return exc.code
    if isinstance(exc, TimeoutError) or isinstance(exc, subprocess.TimeoutExpired):
        return "timeout"
    text = str(exc).lower()
    if "402" in text or "insufficient balance" in text:
        return "http_402"
    if "schema" in text or "evidence" in text or "citation" in text or isinstance(exc, (ValueError, TypeError)):
        return "validation_error"
    if "http" in text or "transport" in text or "connection" in text:
        return "transport_error"
    return f"provider_error:{type(exc).__name__}"


def _unpack(result: Any) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    if isinstance(result, tuple) and len(result) == 2:
        output, receipt = result
    else:
        output, receipt = result, {}
    if not isinstance(output, Mapping):
        raise CodexCliError("structured_output_not_object")
    return output, receipt if isinstance(receipt, Mapping) else {}


def _decode_json_text(text: str) -> Mapping[str, Any]:
    value = text.strip()
    if not value:
        raise CodexCliError("empty_output")
    fence = chr(96) * 3
    if value.startswith(fence) and value.endswith(fence):
        value = re.sub(r"^" + re.escape(fence) + r"(?:json)?\s*", "", value)
        value = re.sub(r"\s*" + re.escape(fence) + r"$", "", value)
    try:
        parsed = json.loads(value)
        if isinstance(parsed, Mapping):
            return parsed
    except json.JSONDecodeError:
        pass
    for line in reversed(value.splitlines()):
        candidate = line.strip()
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, Mapping):
            for key in ("result", "text", "output", "structured_output"):
                nested = parsed.get(key)
                if isinstance(nested, Mapping):
                    return nested
                if isinstance(nested, str):
                    try:
                        decoded = json.loads(nested)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(decoded, Mapping):
                        return decoded
            return parsed
    raise CodexCliError("codex_output_not_json")


class CodexCliProvider:
    """Run Codex CLI in an isolated read-only directory and return JSON."""

    provider_name = "Codex CLI"

    def __init__(
        self,
        *,
        system_prompt: str,
        model: str | None = None,
        executable: str = "codex",
        timeout: float = 900.0,
        runner: Callable[..., Any] | None = None,
        cli_version: str | None = None,
        timeout_provider: Callable[[], float] | None = None,
    ) -> None:
        self.system_prompt = system_prompt
        self.model = model
        self.executable = executable
        self.timeout = timeout
        self.runner = runner or self._run
        self.cli_version = cli_version or "unknown"
        self.timeout_provider = timeout_provider

    @staticmethod
    def _run(command: list[str], *, cwd: Path, timeout: float) -> Any:
        return subprocess.run(command, cwd=str(cwd), capture_output=True, text=True, timeout=timeout, check=False)

    def __call__(self, request: Mapping[str, Any]) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
        request_hash = _digest(request)
        prompt = (
            self.system_prompt
            + "\n你是备用解释器。只能使用下方冻结 JSON，不得调用工具、读取文件、重新获取行情、读取旧日报或外部新闻。"
            + "\n只返回符合原请求 schema 的 JSON，不要 Markdown、解释或额外字段。"
            + "\nFROZEN_REQUEST_JSON:\n"
            + _canonical(request)
        )
        with tempfile.TemporaryDirectory(prefix="park-kline-codex-") as directory:
            root = Path(directory)
            output_path = root / "codex-output.json"
            command = [
                self.executable,
                "exec",
                "--ephemeral",
                "--sandbox",
                "read-only",
                "--skip-git-repo-check",
                "--disable",
                "shell_tool",
                "--disable",
                "browser_use",
                "--disable",
                "browser_use_external",
                "--disable",
                "computer_use",
                "--disable",
                "apps",
                "--disable",
                "unified_exec",
                "--json",
                "--output-last-message",
                str(output_path),
                "-C",
                str(root),
            ]
            if self.model:
                command.extend(["--model", self.model])
            command.append(prompt)
            timeout = self.timeout
            if self.timeout_provider is not None:
                remaining = float(self.timeout_provider())
                if remaining <= 0:
                    raise CodexCliError("runtime_timeout")
                timeout = min(timeout, remaining)
            try:
                completed = self.runner(command, cwd=root, timeout=timeout)
            except Exception as exc:
                raise CodexCliError(f"codex_runner:{type(exc).__name__}") from exc
            if int(getattr(completed, "returncode", 1) or 0) != 0:
                raise CodexCliError(f"codex_exit:{getattr(completed, 'returncode', 1)}")
            text = output_path.read_text(encoding="utf-8") if output_path.is_file() else str(getattr(completed, "stdout", "") or "")
            output = _decode_json_text(text)
        return output, {
            "provider": self.provider_name,
            "model": self.model or "codex-default",
            "cli_version": self.cli_version,
            "request_hash": request_hash,
            "output_hash": _digest(output),
            "attempt_count": 1,
            "tool_policy": "none",
            "network_policy": "no_external_tools",
            "executable": self.executable,
        }


class ValidatedFallbackProvider:
    """Validate the primary result, then use one audited fallback if needed."""

    def __init__(
        self,
        *,
        primary: Callable[[Mapping[str, Any]], Any] | None,
        fallback: Callable[[Mapping[str, Any]], Any],
        validator: Callable[[Mapping[str, Any], Mapping[str, Any]], Any],
        primary_provider: str = "DeepSeek",
        fallback_attempts: int = 3,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.validator = validator
        self.primary_provider = primary_provider
        self.fallback_attempts = max(1, int(fallback_attempts))

    def __call__(self, request: Mapping[str, Any]) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
        primary_failure = "key_missing"
        if self.primary is not None:
            try:
                output, receipt = _unpack(self.primary(request))
                self.validator(output, request)
                enriched = dict(receipt)
                enriched.update(
                    {
                        "provider": enriched.get("provider") or self.primary_provider,
                        "fallback_used": False,
                        "fallback_reason": None,
                        "primary_provider": self.primary_provider,
                        "request_hash": _digest(request),
                        "output_hash": _digest(output),
                        "validation_result": "passed",
                    }
                )
                return output, enriched
            except Exception as exc:
                primary_failure = _safe_failure(exc)
        fallback_failure = "fallback_not_attempted"
        for attempt in range(1, self.fallback_attempts + 1):
            try:
                output, receipt = _unpack(self.fallback(request))
                self.validator(output, request)
                enriched = dict(receipt)
                enriched.update(
                    {
                        "provider": enriched.get("provider") or "Codex CLI",
                        "fallback_used": True,
                        "fallback_reason": primary_failure,
                        "primary_provider": self.primary_provider,
                        "primary_failure": primary_failure,
                        "attempt_count": attempt,
                        "request_hash": _digest(request),
                        "output_hash": _digest(output),
                        "validation_result": "passed",
                    }
                )
                return output, enriched
            except Exception as exc:
                fallback_failure = _safe_failure(exc)
        raise ProviderFallbackError(primary_failure, fallback_failure)


__all__ = ["CodexCliError", "CodexCliProvider", "ProviderFallbackError", "ValidatedFallbackProvider"]
