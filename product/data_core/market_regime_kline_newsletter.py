"""Independent local K-line Daily Newsletter for the Track 2 comparison pilot.

The module deliberately consumes only frozen Market Regime daily evidence and
one separately frozen Bitcoin supplement.  It never reads the Finance Daily
Newsletter and it never publishes trading instructions.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from html import escape
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Any, Callable, Mapping
from urllib.parse import quote
from zoneinfo import ZoneInfo

from .market_regime_daily_evidence import (
    MarketRegimeDailyEvidenceStore,
    resolve_evidence,
)
from .market_regime_daily_narrative import (
    SYSTEM_PROMPT,
    MarketRegimeDailyNarrativeError,
    MarketRegimeDailyNarrativeStore,
    validate_model_output,
)
from .market_regime_data import (
    HttpCapture,
    InstrumentSpec,
    MarketRegimeDataStore,
    http_get_capture,
    license_decision,
    normalize_capture,
)
from .market_regime_macro_data import MarketRegimeMacroDataStore


SCHEMA_VERSION = "market-regime-kline-newsletter-v1"
RENDERER_VERSION = "market-regime-kline-newsletter-renderer-v1"
BITCOIN_SCHEMA_VERSION = "market-regime-kline-bitcoin-v1"
REPORT_ID_PREFIX = "market-regime-kline-newsletter:"
BITCOIN_ID_PREFIX = "market-regime-kline-bitcoin:"
SHANGHAI = ZoneInfo("Asia/Shanghai")

BTC_SPEC = InstrumentSpec(
    "bitcoin",
    "Bitcoin",
    "crypto",
    "pilot_supplement",
    "yahoo_chart",
    "BTC-USD",
    "BTC-USD",
    "crypto_asset",
    "USD",
    "USD/coin",
    "UTC",
    "23:59",
    "provider_unadjusted_trade_price",
)
BTC_URL = (
    "https://query2.finance.yahoo.com/v8/finance/chart/"
    f"{quote(BTC_SPEC.provider_symbol, safe='^=')}"
    "?interval=1d&range=2y&events=history&includeAdjustedClose=false"
)
BTC_QUERY1_URL = BTC_URL.replace("query2.finance.yahoo.com", "query1.finance.yahoo.com")


def bitcoin_source_urls() -> tuple[tuple[str, str], ...]:
    """Same-day Yahoo endpoints for the same BTC-USD instrument identity."""

    return (("query2", BTC_URL), ("query1", BTC_QUERY1_URL))

DISPLAY_ORDER = (
    "sp500",
    "nasdaq",
    "shanghai",
    "star50",
    "nikkei",
    "kospi",
    "wti",
    "gold",
    "silver",
    "bitcoin",
    "vix",
    "dxy",
    "us2y",
    "us10y",
    "us2s10s",
)
PRICE_CHART_KEYS = frozenset(
    {
        "sp500",
        "nasdaq",
        "shanghai",
        "star50",
        "nikkei",
        "kospi",
        "wti",
        "gold",
        "silver",
        "bitcoin",
        "vix",
        "dxy",
    }
)
POSTURE_ZH = {
    "attack": "进攻",
    "wait": "等待",
    "defense": "防守",
    "unknown": "未知",
}
POSTURE_EN = {
    "attack": "ATTACK",
    "wait": "WAIT",
    "defense": "DEFENSE",
    "unknown": "UNKNOWN",
}
PILOT_SYSTEM_PROMPT = SYSTEM_PROMPT + """

本 pilot 的额外输出纪律：
- posture_evidence_ids 与 theme_evidence_ids 各引用 2–4 个最关键 ID，不要穷举全部证据。
- 每个 transmission_chain 引用 1–4 个 ID；所有 evidence_ids 列表绝不能超过 6 个。
- contradiction 的 evidence_ids 必须逐项、按原顺序复制对应 candidate 的 exact evidence_ids。
- 除非 agreement_inputs 明确给出同方向标签且 response 两端证据充分，否则 causal_status 使用 plausible_interpretation；不要把 mixed、defensive 或 dividend_led 猜成 supported_observation。
- falsifier 只能使用以下精确组合：change_5d + sign_reversal/relationship_breaks；quality + quality_degrades；status + relationship_breaks；trend_score + sign_reversal/relationship_breaks。引用行必须实际含有该 field。
- 选择最少、最能区分主线的证据，而不是试图在每个字段列出完整市场。
"""


class KlineNewsletterError(RuntimeError):
    """A Track 2 source, identity, rendering, or publication check failed."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (_canonical_json(value) + "\n").encode("utf-8")


def _digest(value: Any) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise KlineNewsletterError("time_requires_timezone")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _atomic_bytes(path: Path, encoded: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    _atomic_bytes(path, _json_bytes(value))


def _immutable_bytes(path: Path, encoded: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    digest = sha256(encoded).hexdigest()
    if path.exists():
        if path.read_bytes() != encoded:
            raise KlineNewsletterError("immutable_identity_collision")
        return digest
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return digest


def _finite(value: Any, *, field: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise KlineNewsletterError(f"invalid_number:{field}") from exc
    if not math.isfinite(result):
        raise KlineNewsletterError(f"invalid_number:{field}")
    return round(result, 6)


def _change_5d(bars: list[Mapping[str, Any]]) -> float:
    if len(bars) < 6:
        raise KlineNewsletterError("bitcoin_history_too_short")
    latest = _finite(bars[-1].get("close"), field="bitcoin.close")
    prior = _finite(bars[-6].get("close"), field="bitcoin.close_5d")
    if prior == 0:
        raise KlineNewsletterError("bitcoin_zero_reference")
    return round((latest / prior - 1) * 100, 6)


@dataclass(frozen=True)
class PilotDeepSeekNarrativeProvider:
    """S4-compatible provider tuned for a clean bounded pilot response."""

    key_file: Path
    model: str = "deepseek-v4-flash"
    provider_name: str = "DeepSeek"

    def generate(
        self, request: Mapping[str, Any]
    ) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
        from deepseek_writer import call_structured_deepseek

        slots = request.get("evidence_slots") or []
        validation_pack = {
            "pack_id": request.get("pack_id"),
            "slots": slots,
            "evidence_index": {
                str(slot.get("evidence_id")): str(slot.get("key"))
                for slot in slots
                if isinstance(slot, Mapping) and slot.get("evidence_id") and slot.get("key")
            },
            "agreement_inputs": request.get("agreement_inputs"),
            "contradiction_candidates": request.get("contradiction_candidates"),
        }
        final_output: Mapping[str, Any] | None = None
        final_receipt: Mapping[str, Any] | None = None
        for attempt in range(3):
            output, receipt = call_structured_deepseek(
                system_prompt=PILOT_SYSTEM_PROMPT,
                request_object=request,
                key_file=self.key_file,
                model=self.model,
                max_tokens=5000,
                reasoning_effort="high",
                temperature=0.1,
                thinking_type="disabled",
            )
            final_output, final_receipt = output, receipt
            try:
                validate_model_output(output, validation_pack)
                return output, receipt
            except MarketRegimeDailyNarrativeError:
                if attempt == 2:
                    break
        if final_output is None or final_receipt is None:  # pragma: no cover
            raise KlineNewsletterError("narrative_provider_no_attempt")
        # Return the final invalid value unchanged.  The canonical S4 compiler
        # owns the fallback and reason receipt; this provider never repairs or
        # relaxes model semantics.
        return final_output, final_receipt


class BitcoinDailyStore:
    """Freeze one completed-daily Bitcoin supplement with same-day retries."""

    def __init__(
        self,
        root: Path | str,
        *,
        http_get: Callable[[str], HttpCapture] = http_get_capture,
    ) -> None:
        self.root = Path(root).expanduser().resolve()
        self.http_get = http_get
        self._live_transport = http_get is http_get_capture

    def refresh(self, *, now: datetime | None = None) -> dict[str, Any]:
        if now is not None and self._live_transport:
            raise KlineNewsletterError("bitcoin_live_clock_override_forbidden")
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        rights = license_decision(
            deployment_mode="local_prototype",
            license_status="local_evaluation_only",
        )
        selected: tuple[HttpCapture, str, dict[str, Any], str, list[dict[str, Any]]] | None = None
        attempts: list[dict[str, Any]] = []
        for endpoint, url in bitcoin_source_urls():
            capture: HttpCapture | None = None
            wrote_raw = False
            raw_relative = f"raw/{endpoint}-attempt.bin"
            try:
                capture = self.http_get(url)
                if not isinstance(capture, HttpCapture):
                    raise KlineNewsletterError("bitcoin_transport_invalid")
                raw_hash = capture.raw_sha256 or sha256(b"").hexdigest()
                raw_suffix = ".json" if capture.content_type == "application/json" else ".bin"
                raw_relative = f"raw/{raw_hash}{raw_suffix}"
                _immutable_bytes(self.root / raw_relative, capture.body)
                wrote_raw = True
                normalized = normalize_capture(BTC_SPEC, capture, now=current)
                attempts.append(
                    {
                        "endpoint": endpoint,
                        "accepted": True,
                        "reason": None,
                        **capture.receipt(raw_path=raw_relative),
                    }
                )
                selected = (capture, raw_relative, normalized, endpoint, attempts)
                break
            except Exception as exc:
                if isinstance(exc, Exception) and getattr(exc, "capture", None) is not None:
                    capture = getattr(exc, "capture")
                if capture is not None:
                    if not wrote_raw:
                        raw_hash = capture.raw_sha256 or sha256(b"").hexdigest()
                        raw_suffix = ".json" if capture.content_type == "application/json" else ".bin"
                        raw_relative = f"raw/{raw_hash}-{endpoint}{raw_suffix}"
                        _immutable_bytes(self.root / raw_relative, capture.body)
                    attempt_receipt = capture.receipt(raw_path=raw_relative)
                    if not capture.body:
                        attempt_receipt["raw_sha256"] = sha256(b"").hexdigest()
                else:
                    attempt_receipt = {
                        "method": "GET",
                        "requested_url": url,
                        "final_url": url,
                        "status_code": None,
                        "content_type": None,
                        "raw_sha256": None,
                        "raw_bytes": 0,
                        "raw_path": None,
                        "fetched_at": _iso(current),
                        "error": None,
                    }
                attempts.append(
                    {
                        "endpoint": endpoint,
                        "accepted": False,
                        "reason": " ".join(str(exc).split())[:240] or type(exc).__name__,
                        "bounded_raw_excerpt": (
                            " ".join(capture.body.decode("utf-8", errors="replace").split())[:400]
                            if capture and capture.body
                            else None
                        ),
                        **attempt_receipt,
                    }
                )
        if selected is None:
            raise KlineNewsletterError("bitcoin_all_same_day_sources_rejected")
        capture, raw_relative, normalized, endpoint, attempts = selected
        raw_hash = capture.raw_sha256
        if not raw_hash:
            raise KlineNewsletterError("bitcoin_source_identity_missing")
        core = {
            "schema_version": BITCOIN_SCHEMA_VERSION,
            "instrument": asdict(BTC_SPEC),
            "bars": normalized["bars"],
            "bar_count": normalized["bar_count"],
            "last_completed_session": normalized["last_completed_session"],
            "last_completed_close_at": normalized["last_completed_close_at"],
            "quality": normalized["quality"],
            "value": _finite(normalized["bars"][-1]["close"], field="bitcoin.value"),
            "change_5d": _change_5d(normalized["bars"]),
            "level_unit": BTC_SPEC.unit,
            "change_5d_unit": "percent_return",
            "source_identity": {
                "raw_sha256": raw_hash,
                "raw_bytes": len(capture.body),
                "raw_path": raw_relative,
                "selected_endpoint": endpoint,
                "source_attempts": attempts,
            },
            "data_kind": "real" if self._live_transport else "fixture",
            "rights": rights.as_json(),
            "publication_eligible": False,
            "action_eligible": False,
        }
        bitcoin_id = f"{BITCOIN_ID_PREFIX}{_digest(core)}"
        artifact = {"bitcoin_id": bitcoin_id, "identity_core": core, **core}
        artifact_bytes = _json_bytes(artifact)
        artifact_relative = f"artifacts/{bitcoin_id.removeprefix(BITCOIN_ID_PREFIX)}.json"
        artifact_hash = _immutable_bytes(self.root / artifact_relative, artifact_bytes)
        pointer = {
            "schema_version": BITCOIN_SCHEMA_VERSION,
            "bitcoin_id": bitcoin_id,
            "artifact": {"path": artifact_relative, "sha256": artifact_hash},
        }
        _atomic_json(self.root / "latest.json", pointer)
        return artifact

    def latest(self) -> dict[str, Any]:
        try:
            pointer = json.loads((self.root / "latest.json").read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            raise KlineNewsletterError("bitcoin_latest_unavailable") from exc
        if not isinstance(pointer, dict) or pointer.get("schema_version") != BITCOIN_SCHEMA_VERSION:
            raise KlineNewsletterError("bitcoin_pointer_invalid")
        bitcoin_id = str(pointer.get("bitcoin_id") or "")
        if not bitcoin_id.startswith(BITCOIN_ID_PREFIX):
            raise KlineNewsletterError("bitcoin_identity_invalid")
        digest = bitcoin_id.removeprefix(BITCOIN_ID_PREFIX)
        reference = pointer.get("artifact") or {}
        relative = str(reference.get("path") or "")
        expected = str(reference.get("sha256") or "")
        canonical = f"artifacts/{digest}.json"
        target = (self.root / relative).resolve()
        if relative != canonical or len(expected) != 64 or self.root not in target.parents:
            raise KlineNewsletterError("bitcoin_reference_invalid")
        try:
            encoded = target.read_bytes()
            artifact = json.loads(encoded)
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            raise KlineNewsletterError("bitcoin_artifact_unavailable") from exc
        if sha256(encoded).hexdigest() != expected or not isinstance(artifact, dict):
            raise KlineNewsletterError("bitcoin_artifact_hash_mismatch")
        core = artifact.get("identity_core")
        if (
            not isinstance(core, dict)
            or artifact.get("bitcoin_id") != f"{BITCOIN_ID_PREFIX}{_digest(core)}"
            or artifact.get("bitcoin_id") != bitcoin_id
            or artifact.get("schema_version") != BITCOIN_SCHEMA_VERSION
            or artifact.get("publication_eligible") is not False
            or artifact.get("action_eligible") is not False
        ):
            raise KlineNewsletterError("bitcoin_artifact_identity_mismatch")
        for key, value in core.items():
            if artifact.get(key) != value:
                raise KlineNewsletterError("bitcoin_artifact_projection_mismatch")
        return artifact


def _citations(pack: Mapping[str, Any], evidence_ids: Any) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    if not isinstance(evidence_ids, list):
        return result
    for evidence_id in evidence_ids:
        try:
            slot = resolve_evidence(pack, str(evidence_id))
        except Exception:
            continue
        result.append(
            {
                "evidence_id": str(evidence_id),
                "key": str(slot.get("key") or ""),
                "label": str(slot.get("display_name") or slot.get("key") or "evidence"),
                "session": str(slot.get("session") or "unavailable"),
            }
        )
    return result


def _chart_from_daily(item: Mapping[str, Any]) -> dict[str, Any]:
    instrument = item.get("instrument") or {}
    key = str(instrument.get("key") or "")
    bars = item.get("bars") or []
    if not isinstance(bars, list) or not bars:
        raise KlineNewsletterError(f"chart_unavailable:{key}")
    return {
        "key": key,
        "label": str(instrument.get("display_name") or key),
        "chart_type": "candlestick",
        "unit": str(instrument.get("unit") or ""),
        "session": str(item.get("last_completed_session") or ""),
        "quality": str(item.get("quality") or "unavailable"),
        "bars": bars[-90:],
    }


def _chart_from_macro(item: Mapping[str, Any]) -> dict[str, Any]:
    factor = item.get("factor") or {}
    key = str(factor.get("key") or "")
    if key == "dxy":
        rows = item.get("bars") or []
        chart_type = "candlestick"
    else:
        rows = item.get("observations") or []
        chart_type = "line"
    if not isinstance(rows, list) or not rows:
        raise KlineNewsletterError(f"chart_unavailable:{key}")
    return {
        "key": key,
        "label": str(factor.get("display_name") or key),
        "chart_type": chart_type,
        "unit": str(item.get("level_unit") or factor.get("level_unit") or ""),
        "session": str(item.get("last_completed_session") or ""),
        "quality": str(item.get("quality") or "unavailable"),
        "bars": rows[-90:],
    }


def build_report_payload(
    *,
    pack: Mapping[str, Any],
    narrative: Mapping[str, Any],
    daily: Mapping[str, Any],
    macro: Mapping[str, Any],
    bitcoin: Mapping[str, Any],
    generated_at: datetime,
) -> dict[str, Any]:
    if bitcoin.get("data_kind") != "real":
        raise KlineNewsletterError("fixture_bitcoin_publication_forbidden")
    if narrative.get("pack_id") != pack.get("pack_id"):
        raise KlineNewsletterError("narrative_pack_mismatch")
    pack_inputs = pack.get("inputs") or {}
    if pack_inputs.get("daily_run_id") != daily.get("run_id"):
        raise KlineNewsletterError("daily_pack_mismatch")
    if pack_inputs.get("macro_run_id") != macro.get("run_id"):
        raise KlineNewsletterError("macro_pack_mismatch")
    output = narrative.get("output") or {}
    posture = str(output.get("posture") or "unknown")
    if posture not in POSTURE_ZH:
        raise KlineNewsletterError("narrative_posture_invalid")
    slots = {
        str(slot.get("key")): slot
        for slot in pack.get("slots") or []
        if isinstance(slot, dict)
    }
    bitcoin_row = {
        "key": "bitcoin",
        "display_name": "Bitcoin",
        "value": bitcoin.get("value"),
        "level_unit": bitcoin.get("level_unit"),
        "change_5d": bitcoin.get("change_5d"),
        "change_5d_unit": "percent_return",
        "session": bitcoin.get("last_completed_session"),
        "quality": bitcoin.get("quality"),
        "status": "accepted",
        "evidence_role": "human_comparison_supplement",
    }
    cross_section: list[dict[str, Any]] = []
    for key in DISPLAY_ORDER:
        source = bitcoin_row if key == "bitcoin" else slots.get(key)
        if not isinstance(source, Mapping):
            raise KlineNewsletterError(f"cross_section_missing:{key}")
        cross_section.append(
            {
                field: source.get(field)
                for field in (
                    "key",
                    "display_name",
                    "value",
                    "level_unit",
                    "change_5d",
                    "change_5d_unit",
                    "session",
                    "quality",
                    "status",
                    "evidence_id",
                    "evidence_role",
                )
                if source.get(field) is not None
            }
        )

    daily_items = {
        str((item.get("instrument") or {}).get("key")): item
        for item in daily.get("instruments") or []
        if isinstance(item, dict)
    }
    macro_items = {
        str((item.get("factor") or {}).get("key")): item
        for item in macro.get("factors") or []
        if isinstance(item, dict)
    }
    charts: list[dict[str, Any]] = []
    for key in DISPLAY_ORDER:
        if key == "bitcoin":
            chart = {
                "key": "bitcoin",
                "label": "Bitcoin",
                "chart_type": "candlestick",
                "unit": bitcoin.get("level_unit"),
                "session": bitcoin.get("last_completed_session"),
                "quality": bitcoin.get("quality"),
                "bars": (bitcoin.get("bars") or [])[-90:],
            }
        elif key in macro_items:
            chart = _chart_from_macro(macro_items[key])
        else:
            item = daily_items.get(key)
            if item is None:
                raise KlineNewsletterError(f"chart_source_missing:{key}")
            chart = _chart_from_daily(item)
        charts.append(chart)
    if len(charts) != 15:
        raise KlineNewsletterError("chart_count_mismatch")

    def cited_rows(rows: Any, text_key: str) -> list[dict[str, Any]]:
        result = []
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            result.append(
                {
                    "text": str(row.get(text_key) or ""),
                    "citations": _citations(pack, row.get("evidence_ids")),
                    "causal_status": row.get("causal_status"),
                }
            )
        return result

    generated = generated_at.astimezone(SHANGHAI)
    confidence = pack.get("confidence_inputs") or {}
    core = {
        "schema_version": SCHEMA_VERSION,
        "renderer_version": RENDERER_VERSION,
        "report_date": generated.date().isoformat(),
        "generated_at": _iso(generated_at),
        "sources": {
            "daily_run_id": daily.get("run_id"),
            "macro_run_id": macro.get("run_id"),
            "pack_id": pack.get("pack_id"),
            "narrative_id": narrative.get("narrative_id"),
            "bitcoin_id": bitcoin.get("bitcoin_id"),
        },
        "posture": posture,
        "posture_zh": POSTURE_ZH[posture],
        "posture_en": POSTURE_EN[posture],
        "synthesis": str(output.get("synthesis") or "模型解释不可用；当前只展示冻结证据。"),
        "generation_status": str(narrative.get("generation_status") or "deterministic_fallback"),
        "fallback_reason_code": output.get("fallback_reason_code"),
        "confidence": {
            "score": confidence.get("score"),
            "level": confidence.get("level"),
            "explanation": output.get("confidence_explanation"),
        },
        "time": pack.get("time"),
        "coverage": pack.get("coverage"),
        "transmission_chain": cited_rows(output.get("transmission_chain"), "claim"),
        "contradictions": cited_rows(output.get("contradictions"), "claim"),
        "falsifiers": cited_rows(output.get("falsifiers"), "condition"),
        "cross_section": cross_section,
        "charts": charts,
        "bitcoin_boundary": (
            "Bitcoin is frozen and shown as a human-comparison supplement; "
            "the canonical posture v1 does not use it as a deterministic model input."
        ),
        "truth_boundary": {
            "track": "kline_only",
            "finance_newsletter_input": False,
            "local_evaluation_only": True,
            "model_generated_unreviewed": narrative.get("generation_status")
            == "model_generated_unreviewed",
            "investment_advice": False,
            "publication_eligible": False,
            "action_eligible": False,
        },
    }
    return {
        "report_id": f"{REPORT_ID_PREFIX}{_digest(core)}",
        "identity_core": core,
        **core,
    }


def _fmt_value(value: Any, unit: str | None = None) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    if unit == "basis_points":
        return f"{number:+.1f} bp"
    if unit == "percent_return":
        return f"{number:+.1f}%"
    if unit == "percent":
        return f"{number:.2f}%"
    if abs(number) >= 1000:
        return f"{number:,.1f}"
    return f"{number:.2f}"


def _citation_html(citations: list[Mapping[str, str]]) -> str:
    return "".join(
        f'<span class="cite" title="{escape(str(item.get("evidence_id") or ""))}">'
        f'{escape(str(item.get("label") or "evidence"))} · '
        f'{escape(str(item.get("session") or ""))}</span>'
        for item in citations
    )


def render_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        f"# K 线日报｜{report['report_date']}",
        "",
        f"## {report['posture_zh']} / {report['posture_en']}",
        "",
        str(report.get("synthesis") or ""),
        "",
        f"- 置信度：{_fmt_value((report.get('confidence') or {}).get('score'))} / {(report.get('confidence') or {}).get('level')}",
        f"- 解释状态：{report.get('generation_status')}",
        f"- 跨市场完成日收盘时差：{_fmt_value((report.get('time') or {}).get('cross_market_close_skew_hours'))} 小时",
        "",
        "## 世界正在定价什么",
        "",
    ]
    for index, row in enumerate(report.get("transmission_chain") or [], 1):
        labels = "、".join(item.get("label", "") for item in row.get("citations") or [])
        lines.append(f"{index}. {row.get('text')}（{labels}）")
    lines.extend(["", "## 15 个观测的 5 日横截面", "", "| 市场 | 5日变化 | 完成日 | 质量 |", "|---|---:|---|---|"])
    for row in report.get("cross_section") or []:
        lines.append(
            f"| {row.get('display_name')} | {_fmt_value(row.get('change_5d'), row.get('change_5d_unit'))} | "
            f"{row.get('session', '—')} | {row.get('quality', '—')} |"
        )
    lines.extend(["", "## 主线内部的矛盾", ""])
    for row in report.get("contradictions") or []:
        lines.append(f"- {row.get('text')}")
    lines.extend(["", "## 两个证伪条件", ""])
    for row in report.get("falsifiers") or []:
        lines.append(f"- {row.get('text')}")
    lines.extend(
        [
            "",
            "---",
            "",
            "仅限 Park 本地评估。数据与模型解释均不可公开分发；这不是投资建议、预测、仓位或订单。",
            "Bitcoin 当前是人工比较补充项，尚未进入 canonical posture v1 的确定性输入。",
            "本日报不读取 Finance Daily Newsletter，两个 Track 仅供事后人工比较。",
            "",
        ]
    )
    return "\n".join(lines)


def render_html(report: Mapping[str, Any]) -> str:
    posture = str(report.get("posture") or "unknown")
    chain_html = "".join(
        f'<li><span class="dot"></span><div><p>{escape(str(row.get("text") or ""))}</p>'
        f'<div class="citations">{_citation_html(row.get("citations") or [])}</div></div></li>'
        for row in report.get("transmission_chain") or []
    )
    contradiction_html = "".join(
        f'<article class="tension"><span>矛盾 {index}</span><p>{escape(str(row.get("text") or ""))}</p>'
        f'<div class="citations">{_citation_html(row.get("citations") or [])}</div></article>'
        for index, row in enumerate(report.get("contradictions") or [], 1)
    )
    falsifier_html = "".join(
        f'<article class="falsifier"><b>{index:02d}</b><p>{escape(str(row.get("text") or ""))}</p>'
        f'<div class="citations">{_citation_html(row.get("citations") or [])}</div></article>'
        for index, row in enumerate(report.get("falsifiers") or [], 1)
    )
    cross_html = "".join(
        f'<div class="market-row"><span>{escape(str(row.get("display_name") or row.get("key") or ""))}</span>'
        f'<strong class="{"up" if float(row.get("change_5d") or 0) >= 0 else "down"}">'
        f'{escape(_fmt_value(row.get("change_5d"), row.get("change_5d_unit")))}</strong>'
        f'<small>{escape(str(row.get("session") or "—"))} · {escape(str(row.get("quality") or "—"))}</small></div>'
        for row in report.get("cross_section") or []
    )
    chart_html = "".join(
        f'<article class="chart-card"><header><div><span>{index:02d}</span><h3>{escape(str(chart.get("label") or ""))}</h3></div>'
        f'<small>{escape(str(chart.get("session") or ""))} · {escape(str(chart.get("quality") or ""))}</small></header>'
        f'<canvas data-chart="{escape(str(chart.get("key") or ""))}" aria-label="{escape(str(chart.get("label") or ""))} daily chart"></canvas></article>'
        for index, chart in enumerate(report.get("charts") or [], 1)
    )
    score = (report.get("confidence") or {}).get("score")
    score_text = "—" if score is None else f"{float(score) * 100:.0f}"
    generation_label = (
        "模型解释 · 未人工复核"
        if report.get("generation_status") == "model_generated_unreviewed"
        else "解释降级 · 仅展示冻结证据"
    )
    embedded = json.dumps(report, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="zh-CN" data-posture="{escape(posture)}">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>K 线日报｜{escape(str(report.get('report_date') or ''))}</title>
<style>
:root{{--ink:#111714;--muted:#69726d;--line:#e2e7e4;--paper:#fff;--wash:#f5f7f5;--accent:#5d6b64;--accent-dark:#34423b;--tint:#edf1ef;--positive:#148254;--negative:#cf453d}}
html[data-posture="attack"]{{--accent:#087a49;--accent-dark:#045d36;--tint:#e4f6ec}}
html[data-posture="wait"]{{--accent:#bd7410;--accent-dark:#875008;--tint:#fff1d8}}
html[data-posture="defense"]{{--accent:#d13d34;--accent-dark:#98271f;--tint:#fde7e4}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--wash);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Noto Sans CJK SC",sans-serif}}main{{width:min(1120px,100%);margin:0 auto;background:var(--paper);min-height:100vh;box-shadow:0 0 45px rgba(20,30,25,.08)}}
.mast{{padding:24px 48px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;gap:20px;align-items:center}}.eyebrow{{font-size:12px;letter-spacing:.15em;color:var(--muted);text-transform:uppercase}}.badges{{display:flex;gap:8px;flex-wrap:wrap}}.badge{{font-size:11px;border:1px solid var(--line);padding:6px 9px;border-radius:99px;color:var(--muted);background:white}}
.hero{{padding:58px 48px 52px;background:linear-gradient(115deg,var(--tint),#fff 62%);border-bottom:4px solid var(--accent);display:grid;grid-template-columns:1fr 240px;gap:50px;align-items:end}}.hero h1{{font-family:Georgia,"Songti SC",serif;font-size:clamp(72px,10vw,138px);font-weight:500;line-height:.85;margin:20px 0 18px;color:var(--accent-dark);letter-spacing:-.08em}}.hero .en{{font-size:12px;letter-spacing:.32em;color:var(--accent);font-weight:700}}.hero .synthesis{{font-family:Georgia,"Songti SC",serif;font-size:21px;line-height:1.75;max-width:720px;margin:28px 0 0}}.confidence{{border:1px solid color-mix(in srgb,var(--accent) 30%,white);background:rgba(255,255,255,.72);padding:22px;border-radius:4px}}.confidence span{{font-size:11px;letter-spacing:.15em;color:var(--muted)}}.confidence strong{{display:block;font-family:Georgia,serif;color:var(--accent-dark);font-size:56px;font-weight:400;margin:7px 0}}.confidence p{{font-size:12px;color:var(--muted);line-height:1.65;margin:0}}
section{{padding:48px;border-bottom:1px solid var(--line)}}.section-head{{display:flex;justify-content:space-between;gap:24px;align-items:baseline;margin-bottom:30px}}.section-head div{{display:flex;align-items:center;gap:12px}}.section-head b{{width:26px;height:26px;border-radius:50%;background:var(--accent);color:white;display:grid;place-items:center;font-size:12px}}.section-head h2{{font-size:15px;margin:0}}.section-head small{{font-size:11px;color:var(--muted)}}
.chain{{margin:0;padding:0;list-style:none;max-width:850px}}.chain li{{display:grid;grid-template-columns:18px 1fr;gap:18px;position:relative;padding:0 0 28px}}.chain li:not(:last-child)::before{{content:"";position:absolute;left:5px;top:14px;bottom:0;border-left:1px solid var(--line)}}.dot{{width:11px;height:11px;background:var(--accent);border-radius:50%;margin-top:8px;z-index:1;box-shadow:0 0 0 5px white}}.chain p{{font-family:Georgia,"Songti SC",serif;font-size:23px;line-height:1.55;margin:0}}
.citations{{display:flex;gap:6px;flex-wrap:wrap;margin-top:9px}}.cite{{font-size:10px;color:var(--muted);background:#f3f5f4;padding:4px 7px;border-radius:2px}}.cross{{display:grid;grid-template-columns:repeat(3,1fr);gap:0 28px}}.market-row{{display:grid;grid-template-columns:1fr auto;gap:3px 10px;padding:12px 0;border-bottom:1px solid var(--line)}}.market-row span{{font-size:13px}}.market-row strong{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}}.market-row small{{grid-column:1/-1;color:var(--muted);font-size:10px}}.up{{color:var(--positive)}}.down{{color:var(--negative)}}
.tensions{{display:grid;grid-template-columns:repeat(2,1fr);gap:18px}}.tension{{border-left:3px solid var(--accent);background:var(--tint);padding:20px}}.tension>span{{font-size:10px;color:var(--accent);letter-spacing:.15em}}.tension p{{font-family:Georgia,"Songti SC",serif;font-size:18px;line-height:1.6;margin:9px 0 0}}.falsifiers{{display:grid;grid-template-columns:repeat(2,1fr);gap:18px}}.falsifier{{border:1px solid var(--line);padding:24px;display:grid;grid-template-columns:42px 1fr;gap:12px}}.falsifier>b{{font-family:Georgia,serif;color:var(--accent);font-size:30px}}.falsifier p{{font-size:15px;line-height:1.65;margin:0}}.falsifier .citations{{grid-column:2}}
.charts{{display:grid;grid-template-columns:repeat(2,1fr);gap:18px}}.chart-card{{border:1px solid var(--line);padding:16px;background:white}}.chart-card header{{display:flex;justify-content:space-between;gap:10px;margin-bottom:10px}}.chart-card header div{{display:flex;align-items:baseline;gap:9px}}.chart-card header span{{font-size:10px;color:var(--accent)}}.chart-card h3{{font-size:14px;margin:0}}.chart-card small{{font-size:9px;color:var(--muted)}}canvas{{display:block;width:100%;height:190px}}.boundary{{background:#111714;color:#e9efeb;padding:34px 48px;font-size:11px;line-height:1.8}}.boundary strong{{color:white}}.boundary code{{color:#b8c5bd;overflow-wrap:anywhere;word-break:break-all}}
@media(max-width:700px){{main{{box-shadow:none}}.mast{{padding:18px 20px;align-items:flex-start}}.hero{{padding:42px 20px 34px;grid-template-columns:1fr;gap:28px}}.hero h1{{font-size:82px}}.hero .synthesis{{font-size:18px}}.confidence{{display:grid;grid-template-columns:1fr auto;align-items:center}}.confidence strong{{font-size:42px;margin:0}}.confidence p{{grid-column:1/-1}}section{{padding:34px 20px}}.section-head{{align-items:flex-start}}.chain p{{font-size:20px}}.cross{{grid-template-columns:1fr}}.tensions,.falsifiers,.charts{{grid-template-columns:1fr}}.boundary{{padding:28px 20px}}canvas{{height:170px}}}}
</style></head>
<body><main>
<header class="mast"><div><div class="eyebrow">Park · K-line Daily</div><small>Track 2 / independent comparison pilot</small></div><div class="badges"><span class="badge">{escape(str(report.get('report_date') or ''))}</span><span class="badge">{escape(generation_label)}</span><span class="badge">LOCAL ONLY</span></div></header>
<div class="hero"><div><div class="eyebrow">今日市场姿态 / Market posture</div><h1>{escape(str(report.get('posture_zh') or '未知'))}</h1><div class="en">{escape(str(report.get('posture_en') or 'UNKNOWN'))}</div><p class="synthesis">{escape(str(report.get('synthesis') or ''))}</p></div><aside class="confidence"><span>代码置信度</span><strong>{escape(score_text)}</strong><p>{escape(str((report.get('confidence') or {}).get('explanation') or ''))}</p></aside></div>
<section><div class="section-head"><div><b>1</b><h2>当前主导全球资产定价的力量是什么？</h2></div><small>3–5 步 · 全部绑定冻结证据</small></div><ol class="chain">{chain_html}</ol></section>
<section><div class="section-head"><div><b>2</b><h2>15 个观测的五日横截面</h2></div><small>收益率与曲线变化使用 bp</small></div><div class="cross">{cross_html}</div></section>
<section><div class="section-head"><div><b>3</b><h2>主线内部哪里不一致？</h2></div><small>矛盾不是噪音，是置信度边界</small></div><div class="tensions">{contradiction_html}</div></section>
<section><div class="section-head"><div><b>4</b><h2>哪两件事会推翻当前解释？</h2></div><small>恰好两个 · 可观察</small></div><div class="falsifiers">{falsifier_html}</div></section>
<section><div class="section-head"><div><b>5</b><h2>15 张完成日线证据</h2></div><small>K 线为主；美债收益率与曲线为折线</small></div><div class="charts">{chart_html}</div></section>
<footer class="boundary"><strong>边界：</strong>仅限 Park 本地评估；不可公开分发，不是投资建议、预测、仓位或订单。<br>本页不读取 Finance Daily Newsletter，两个 Track 只在事后由 Park 人工比较。<br>Bitcoin 已冻结并显示，但当前仍是人工比较补充项，尚未进入 canonical posture v1 的确定性输入。<br><code>{escape(str(report.get('report_id') or ''))}</code></footer>
</main><script id="report-data" type="application/json">{embedded}</script>
<script>
const REPORT=JSON.parse(document.getElementById('report-data').textContent);
const css=getComputedStyle(document.documentElement), up=css.getPropertyValue('--positive').trim(), down=css.getPropertyValue('--negative').trim(), muted='#9aa39e', ink='#35403a';
function fit(canvas){{const r=canvas.getBoundingClientRect(),d=Math.max(1,window.devicePixelRatio||1);canvas.width=Math.round(r.width*d);canvas.height=Math.round(r.height*d);const c=canvas.getContext('2d');c.setTransform(d,0,0,d,0,0);return [c,r.width,r.height]}}
function values(rows,type){{return rows.flatMap(r=>type==='line'?[Number(r.value)]:[Number(r.high),Number(r.low)]).filter(Number.isFinite)}}
function draw(canvas,chart){{const [c,w,h]=fit(canvas),rows=(chart.bars||[]).slice(-60),pad={{l:8,r:8,t:12,b:18}},vals=values(rows,chart.chart_type);if(!vals.length)return;let lo=Math.min(...vals),hi=Math.max(...vals);if(hi===lo){{hi+=1;lo-=1}}const y=v=>pad.t+(hi-v)/(hi-lo)*(h-pad.t-pad.b),step=(w-pad.l-pad.r)/Math.max(rows.length,1);c.clearRect(0,0,w,h);c.strokeStyle='#edf0ee';c.lineWidth=1;for(let i=0;i<4;i++){{let yy=pad.t+i*(h-pad.t-pad.b)/3;c.beginPath();c.moveTo(pad.l,yy);c.lineTo(w-pad.r,yy);c.stroke()}}if(chart.chart_type==='line'){{c.strokeStyle=ink;c.lineWidth=1.7;c.beginPath();rows.forEach((r,i)=>{{let x=pad.l+(i+.5)*step,yy=y(Number(r.value));i?c.lineTo(x,yy):c.moveTo(x,yy)}});c.stroke()}}else{{rows.forEach((r,i)=>{{let o=Number(r.open),cl=Number(r.close),hh=Number(r.high),ll=Number(r.low),x=pad.l+(i+.5)*step,col=cl>=o?up:down,bw=Math.max(1.5,Math.min(7,step*.58));c.strokeStyle=col;c.fillStyle=col;c.lineWidth=1;c.beginPath();c.moveTo(x,y(hh));c.lineTo(x,y(ll));c.stroke();let top=Math.min(y(o),y(cl)),bh=Math.max(1,Math.abs(y(o)-y(cl)));c.fillRect(x-bw/2,top,bw,bh)}})}}c.fillStyle=muted;c.font='9px -apple-system,sans-serif';c.fillText(rows[0]?.date||'',pad.l,h-4);let last=rows.at(-1);c.textAlign='right';c.fillText(last?.date||'',w-pad.r,h-4);c.textAlign='left'}}
function redraw(){{for(const canvas of document.querySelectorAll('canvas[data-chart]')){{let chart=REPORT.charts.find(x=>x.key===canvas.dataset.chart);if(chart)draw(canvas,chart)}}}}redraw();let timer;addEventListener('resize',()=>{{clearTimeout(timer);timer=setTimeout(redraw,120)}});
</script></body></html>"""


class KlineNewsletterStore:
    """Publish immutable report artifacts, then atomically advance latest."""

    def __init__(self, runtime_root: Path | str, output_root: Path | str) -> None:
        self.runtime_root = Path(runtime_root).expanduser().resolve()
        self.output_root = Path(output_root).expanduser().resolve()

    def publish(self, report: Mapping[str, Any]) -> dict[str, Any]:
        report_id = str(report.get("report_id") or "")
        if not report_id.startswith(REPORT_ID_PREFIX):
            raise KlineNewsletterError("report_identity_invalid")
        digest = report_id.removeprefix(REPORT_ID_PREFIX)
        core = report.get("identity_core")
        if not isinstance(core, dict) or report_id != f"{REPORT_ID_PREFIX}{_digest(core)}":
            raise KlineNewsletterError("report_identity_mismatch")
        if report.get("truth_boundary") != core.get("truth_boundary"):
            raise KlineNewsletterError("report_boundary_mismatch")
        if (report.get("truth_boundary") or {}).get("publication_eligible") is not False:
            raise KlineNewsletterError("report_publication_boundary_invalid")
        payload_relative = f"reports/artifacts/{digest}.json"
        payload_hash = _immutable_bytes(
            self.runtime_root / payload_relative, _json_bytes(dict(report))
        )
        markdown = render_markdown(report).encode("utf-8")
        html = render_html(report).encode("utf-8")
        date = str(report.get("report_date") or "unknown")
        html_relative = f"archive/{date}/{digest}.html"
        md_relative = f"archive/{date}/{digest}.md"
        html_hash = _immutable_bytes(self.output_root / html_relative, html)
        md_hash = _immutable_bytes(self.output_root / md_relative, markdown)
        pointer = {
            "schema_version": SCHEMA_VERSION,
            "report_id": report_id,
            "report_date": date,
            "generated_at": report.get("generated_at"),
            "payload": {"path": payload_relative, "sha256": payload_hash},
            "html": {"path": html_relative, "sha256": html_hash},
            "markdown": {"path": md_relative, "sha256": md_hash},
            "publication_eligible": False,
            "action_eligible": False,
        }
        _atomic_json(self.runtime_root / "latest.json", pointer)
        _atomic_bytes(self.output_root / "latest.html", html)
        _atomic_bytes(self.output_root / "latest.md", markdown)
        _atomic_bytes(self.output_root / f"{date}-kline-daily.html", html)
        _atomic_bytes(self.output_root / f"{date}-kline-daily.md", markdown)
        return pointer

    def latest(self) -> tuple[dict[str, Any], dict[str, Any]]:
        try:
            pointer = json.loads(
                (self.runtime_root / "latest.json").read_text(encoding="utf-8")
            )
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            raise KlineNewsletterError("report_latest_unavailable") from exc
        if not isinstance(pointer, dict) or pointer.get("schema_version") != SCHEMA_VERSION:
            raise KlineNewsletterError("report_pointer_invalid")
        report_id = str(pointer.get("report_id") or "")
        digest = report_id.removeprefix(REPORT_ID_PREFIX)
        if not report_id.startswith(REPORT_ID_PREFIX) or len(digest) != 64:
            raise KlineNewsletterError("report_pointer_identity_invalid")
        payload_ref = pointer.get("payload") or {}
        relative = str(payload_ref.get("path") or "")
        expected = str(payload_ref.get("sha256") or "")
        target = (self.runtime_root / relative).resolve()
        if (
            relative != f"reports/artifacts/{digest}.json"
            or len(expected) != 64
            or self.runtime_root not in target.parents
        ):
            raise KlineNewsletterError("report_payload_reference_invalid")
        try:
            encoded = target.read_bytes()
            report = json.loads(encoded)
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            raise KlineNewsletterError("report_payload_unavailable") from exc
        if sha256(encoded).hexdigest() != expected or not isinstance(report, dict):
            raise KlineNewsletterError("report_payload_hash_mismatch")
        core = report.get("identity_core")
        if not isinstance(core, dict) or report.get("report_id") != f"{REPORT_ID_PREFIX}{_digest(core)}":
            raise KlineNewsletterError("report_payload_identity_mismatch")
        for name in ("html", "markdown"):
            reference = pointer.get(name) or {}
            output_target = (self.output_root / str(reference.get("path") or "")).resolve()
            if self.output_root not in output_target.parents:
                raise KlineNewsletterError(f"report_{name}_reference_invalid")
            try:
                output = output_target.read_bytes()
            except FileNotFoundError as exc:
                raise KlineNewsletterError(f"report_{name}_unavailable") from exc
            if sha256(output).hexdigest() != reference.get("sha256"):
                raise KlineNewsletterError(f"report_{name}_hash_mismatch")
        return pointer, report


class KlineNewsletterRuntime:
    """One serial Track 2 run; callers/scheduler own recurrence."""

    def __init__(
        self,
        *,
        daily_root: Path | str,
        runtime_root: Path | str,
        output_root: Path | str,
        key_file: Path | str | None,
        bitcoin_http_get: Callable[[str], HttpCapture] = http_get_capture,
        macro_http_get: Callable[[str], HttpCapture] | None = None,
    ) -> None:
        self.daily_root = Path(daily_root).expanduser().resolve()
        self.runtime_root = Path(runtime_root).expanduser().resolve()
        self.output_root = Path(output_root).expanduser().resolve()
        self.key_file = Path(key_file).expanduser().resolve() if key_file else None
        self.bitcoin_store = BitcoinDailyStore(
            self.runtime_root / "bitcoin", http_get=bitcoin_http_get
        )
        self.macro_store = MarketRegimeMacroDataStore(
            self.runtime_root / "macro",
            **({"http_get": macro_http_get} if macro_http_get is not None else {}),
        )
        self.evidence_store = MarketRegimeDailyEvidenceStore(
            self.daily_root,
            self.runtime_root / "macro",
            self.runtime_root / "evidence",
        )
        self.narrative_store = MarketRegimeDailyNarrativeStore(
            self.evidence_store, self.runtime_root / "narrative"
        )
        self.report_store = KlineNewsletterStore(self.runtime_root, self.output_root)

    def run_once(self) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        try:
            MarketRegimeDataStore(self.daily_root).latest()
            bitcoin = self.bitcoin_store.refresh()
            macro = self.macro_store.refresh(
                deployment_mode="local_prototype",
                license_status="local_evaluation_only",
            )
            pack = self.evidence_store.compile_latest()
            provider = (
                PilotDeepSeekNarrativeProvider(self.key_file)
                if self.key_file is not None and self.key_file.exists()
                else None
            )
            narrative = self.narrative_store.compile_latest(provider)
            # Re-read every served artifact through its validator before the
            # report pointer advances.
            bitcoin = self.bitcoin_store.latest()
            macro = self.macro_store.latest()
            pack = self.evidence_store.latest()
            narrative = self.narrative_store.latest()
            daily = MarketRegimeDataStore(self.daily_root).latest()
            report = build_report_payload(
                pack=pack,
                narrative=narrative,
                daily=daily,
                macro=macro,
                bitcoin=bitcoin,
                generated_at=now,
            )
            pointer = self.report_store.publish(report)
            self.report_store.latest()
            status = {
                "schema_version": SCHEMA_VERSION,
                "state": "idle",
                "last_success": {
                    "at": _iso(datetime.now(timezone.utc)),
                    "report_id": pointer["report_id"],
                    "report_date": pointer["report_date"],
                    "generation_status": report["generation_status"],
                },
                "last_failure": None,
            }
            _atomic_json(self.runtime_root / "status.json", status)
            return {"pointer": pointer, "report": report, "status": status}
        except Exception as exc:
            code = str(exc) if isinstance(exc, KlineNewsletterError) else "run_failed"
            if not code or "/" in code or "\\" in code or len(code) > 80:
                code = "run_failed"
            status = {
                "schema_version": SCHEMA_VERSION,
                "state": "failed",
                "last_success": None,
                "last_failure": {
                    "at": _iso(datetime.now(timezone.utc)),
                    "code": code,
                    "phase": "track2_run",
                },
            }
            try:
                prior = json.loads(
                    (self.runtime_root / "status.json").read_text(encoding="utf-8")
                )
                if isinstance(prior, dict) and prior.get("last_success"):
                    status["last_success"] = prior["last_success"]
            except (FileNotFoundError, json.JSONDecodeError):
                pass
            _atomic_json(self.runtime_root / "status.json", status)
            raise KlineNewsletterError(code) from exc
