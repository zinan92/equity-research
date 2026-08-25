"""Daily cross-asset thesis compiler and Markdown/HTML delivery."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import html
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Callable, Mapping
from zoneinfo import ZoneInfo

from .market_regime_daily_analysis import (
    DAILY_TIMEFRAMES,
    SCHEMA_VERSION as ANALYSIS_SCHEMA,
)
from .market_regime_llm_provider import ProviderFallbackError
from .market_regime_reader_projection import project_daily_asset, render_reader_asset_html, render_reader_asset_markdown
from .market_regime_daily_source import WEEKLY_KEYS


SCHEMA_VERSION = "market-regime-daily-thesis-v2"
THESIS_ID_PREFIX = "market-regime-daily-thesis:"
DELIVERY_ID_PREFIX = "market-regime-daily-delivery:"
POSTURES = {"attack", "wait", "defense", "no_view"}
POSTURE_LABELS = {"attack": "进攻", "wait": "等待", "defense": "防守", "no_view": "无方向观点"}
ALLOWED_LATIN_WORDS = frozenset(
    {
        "Nasdaq", "Bitcoin", "Ethereum", "Nikkei", "KOSPI", "SCHD", "SPY", "QQQ", "UUP",
        "BTC", "ETH", "HYPE", "GC", "CL", "SI", "USDT", "USDC", "OHLC", "MACD", "EMA", "DXY", "VIX", "WTI", "ETF",
    }
)


class DailyThesisError(ValueError):
    """A Daily thesis or delivery contract failed closed."""


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _local_report_date(value: Any) -> str:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()


def _atomic_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _immutable_bytes(path: Path, payload: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(payload).hexdigest()
    if path.exists():
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise DailyThesisError("delivery_immutable_conflict")
        return digest
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return digest


def _has_forbidden_english(text: str) -> bool:
    words = re.findall(r"[A-Za-z]{4,}", text)
    return any(word not in ALLOWED_LATIN_WORDS for word in words)


def _numeric_tokens(text: str) -> list[float]:
    numeric_free = text.replace("4小时", "").replace("30分钟", "").replace("2s10s", "").replace("2Y", "").replace("10Y", "")
    numeric_free = numeric_free.replace("标普500", "标普").replace("标普 500", "标普").replace("科创50", "科创").replace("科创 50", "科创").replace("日经225", "日经").replace("日经 225", "日经")
    numeric_free = re.sub(r"\d+\s*(?:日|天|小时|分钟|周期|年期|个资产|个市场|个周期)", "", numeric_free)
    values: list[float] = []
    for match in re.finditer(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?", numeric_free):
        try:
            values.append(float(match.group(0)))
        except ValueError:
            continue
    return values


def _has_numeric_observation(text: str) -> bool:
    return bool(_numeric_tokens(text))


def _summary_numeric_values(analysis_bundle: Mapping[str, Any]) -> list[float]:
    values: list[float] = []
    def walk(value: Any) -> None:
        if isinstance(value, bool):
            return
        if isinstance(value, (int, float)) and value == value and abs(float(value)) != float("inf"):
            values.append(float(value))
        elif isinstance(value, Mapping):
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    for asset in analysis_bundle.get("assets") or []:
        request = asset.get("request") if isinstance(asset, Mapping) else None
        if not isinstance(request, Mapping):
            continue
        for frame in (request.get("timeframes") or {}).values():
            if not isinstance(frame, Mapping) or frame.get("status") != "ready":
                continue
            features = frame.get("features") or {}
            walk(features.get("current"))
            walk(features.get("high"))
            walk(features.get("low"))
            points = features.get("points") or []
            walk(points[-3:])
        walk((asset.get("analysis") or {}).get("output", {}).get("deterministic") if isinstance(asset.get("analysis"), Mapping) else None)
    return values


def _safe_receipt(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {"provider": "injected", "receipt_hash": _digest(str(value))}
    allowed = (
        "provider",
        "model",
        "cli_version",
        "request_hash",
        "prompt_hash",
        "prompt_version",
        "generation_status",
        "attempt_count",
        "output_hash",
        "fallback_used",
        "fallback_reason",
        "primary_provider",
        "primary_failure",
        "validation_result",
    )
    safe = {key: value[key] for key in allowed if key in value and isinstance(value[key], (str, int, float, bool, type(None)))}
    safe["receipt_hash"] = _digest(safe)
    return safe


def validate_daily_analysis_bundle(bundle: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(bundle, Mapping) or bundle.get("schema_version") != ANALYSIS_SCHEMA:
        raise DailyThesisError("analysis_bundle_schema_invalid")
    bundle_id = str(bundle.get("bundle_id") or "")
    digest = bundle_id.removeprefix("market-regime-daily-analysis:")
    if not bundle_id.startswith("market-regime-daily-analysis:") or len(digest) != 64:
        raise DailyThesisError("analysis_bundle_identity_invalid")
    if _digest(bundle.get("identity_core")) != digest:
        raise DailyThesisError("analysis_bundle_identity_mismatch")
    assets = bundle.get("assets")
    if not isinstance(assets, list) or [item.get("asset_key") for item in assets if isinstance(item, Mapping)] != list(WEEKLY_KEYS):
        raise DailyThesisError("analysis_bundle_universe_invalid")
    if (bundle.get("identity_core") or {}).get("assets_sha256") != _digest(assets):
        raise DailyThesisError("analysis_bundle_assets_hash_invalid")
    return dict(bundle)


def _evidence_ids(analysis_bundle: Mapping[str, Any]) -> set[str]:
    ids: set[str] = set()
    for asset in analysis_bundle.get("assets") or []:
        request = asset.get("request") if isinstance(asset, Mapping) else None
        if isinstance(request, Mapping):
            for frame in (request.get("timeframes") or {}).values():
                if isinstance(frame, Mapping):
                    ids.update(str(item) for item in frame.get("evidence_ids") or [])
            mechanism = request.get("mechanism")
            if isinstance(mechanism, Mapping):
                ids.update(str(item) for item in mechanism.get("mechanism_ids") or [])
        analysis = asset.get("analysis") if isinstance(asset, Mapping) else None
        output = analysis.get("output") if isinstance(analysis, Mapping) else None
        if isinstance(output, Mapping):
            def walk(value: Any) -> None:
                if isinstance(value, Mapping):
                    if isinstance(value.get("evidence_ids"), list):
                        ids.update(str(item) for item in value["evidence_ids"])
                    for child in value.values():
                        walk(child)
                elif isinstance(value, list):
                    for child in value:
                        walk(child)
            walk(output)
    return ids


def build_daily_thesis_request(analysis_bundle: Mapping[str, Any]) -> dict[str, Any]:
    bundle = validate_daily_analysis_bundle(analysis_bundle)
    assets: list[dict[str, Any]] = []
    fact_evidence_ids: set[str] = set()
    unavailable_evidence_ids: set[str] = set()
    mechanism_ids: set[str] = set()
    for asset in bundle["assets"]:
        analysis = asset.get("analysis") or {}
        output = analysis.get("output") or {}
        request = asset.get("request") or {}
        for timeframe, frame in (request.get("timeframes") or {}).items():
            if not isinstance(frame, Mapping):
                continue
            ids = {str(item) for item in frame.get("evidence_ids") or []}
            if frame.get("status") == "ready":
                fact_evidence_ids.update(ids)
            else:
                unavailable_evidence_ids.update(ids)
        mechanism = request.get("mechanism")
        if isinstance(mechanism, Mapping):
            mechanism_ids.update(str(item) for item in mechanism.get("mechanism_ids") or [])
        assets.append(
            {
                "asset_key": asset["asset_key"],
                "display_name": asset.get("display_name", asset["asset_key"]),
                "analysis_id": analysis.get("analysis_id"),
                "generation_status": analysis.get("generation_status"),
                "failure_code": analysis.get("failure_code"),
                "position": (output.get("deterministic") or {}).get("position"),
                "structure": (output.get("deterministic") or {}).get("structure"),
                "timeframes": {
                    timeframe: output.get(timeframe)
                    for timeframe in (item for item in DAILY_TIMEFRAMES if item in (request.get("timeframes") or {}))
                    if output.get(timeframe) is not None
                },
                "synthesis": output.get("synthesis"),
                "market_meaning": output.get("market_meaning"),
                "opportunity_state": output.get("opportunity_state"),
                "coverage": {
                    timeframe: (request.get("timeframes") or {}).get(timeframe, {}).get("status")
                    for timeframe in (item for item in DAILY_TIMEFRAMES if item in (request.get("timeframes") or {}))
                },
            }
        )
        if any(status == "ready" for status in (assets[-1].get("coverage") or {}).values()) and analysis.get("analysis_id"):
            fact_evidence_ids.add(str(analysis["analysis_id"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "analysis_bundle_id": bundle["bundle_id"],
        "cutoff_at": bundle.get("cutoff_at"),
        "assets": assets,
        "fact_evidence_ids": sorted(fact_evidence_ids),
        "unavailable_evidence_ids": sorted(unavailable_evidence_ids),
        "mechanism_ids": sorted(mechanism_ids),
        "numeric_values": _summary_numeric_values(bundle),
        "truth_boundary": {
            "finance_newsletter_input": False,
            "observations_are_evidence_bound": True,
            "inferred_world_model_is_not_literal_flow_measurement": True,
            "automatic_execution_eligible": False,
            "broker_access": False,
        },
    }


def _statement(value: Any, *, known_ids: set[str], field: str, numeric_values: list[float]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not isinstance(value.get("text"), str) or not value["text"].strip():
        raise DailyThesisError(f"thesis_statement_invalid:{field}")
    ids = value.get("evidence_ids")
    if not isinstance(ids, list) or not ids or any(str(item) not in known_ids for item in ids):
        raise DailyThesisError(f"thesis_evidence_invalid:{field}")
    text = value["text"].strip()
    if _has_forbidden_english(text):
        raise DailyThesisError(f"thesis_language_or_numeric_invalid:{field}")
    tokens = _numeric_tokens(text)
    def matches(token: float) -> bool:
        for candidate in numeric_values:
            tolerance = max(0.051, abs(candidate) * 0.0005)
            if abs(token - candidate) <= tolerance or (abs(candidate) <= 1 and abs(token - candidate * 100) <= 2.0):
                return True
        return False
    if any(not matches(token) for token in tokens):
        raise DailyThesisError(f"thesis_numeric_observation_unbound:{field}")
    if re.search(r"直接资金流|资金净流入|真实资金流|资金已流入|资金已流出|个人持仓|仓位比例|满仓|半仓|自动执行|经纪订单|下单", text):
        raise DailyThesisError(f"thesis_boundary_invalid:{field}")
    return {"text": text, "evidence_ids": [str(item) for item in ids]}


def _migration_statement(value: Any, *, known_ids: set[str], numeric_values: list[float]) -> dict[str, Any]:
    result = _statement(value, known_ids=known_ids, field="capital_migration", numeric_values=numeric_values)
    text = result["text"]
    if not any(token in text for token in ("可能", "推断", "更像", "通常", "若", "未必", "反映", "暗示")):
        raise DailyThesisError("thesis_capital_migration_qualifier_missing")
    if re.search(r"直接资金流|资金(?:正在|已经|已|明确|明显)(?:流入|流出|转入|转出)|资金净(?:流入|流出)", text):
        raise DailyThesisError("thesis_capital_migration_overclaim")
    return result


def _mechanism_statement(value: Any, *, mechanism_ids: set[str], field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not isinstance(value.get("text"), str) or not value["text"].strip():
        raise DailyThesisError(f"thesis_mechanism_invalid:{field}")
    ids = value.get("evidence_ids")
    if not isinstance(ids, list) or not ids or any(str(item) not in mechanism_ids for item in ids):
        raise DailyThesisError(f"thesis_mechanism_evidence_invalid:{field}")
    text = value["text"].strip()
    if _has_forbidden_english(text) or _has_numeric_observation(text) or not any(token in text for token in ("通常", "可能", "若", "取决于", "未必", "不一定")):
        raise DailyThesisError(f"thesis_mechanism_language_invalid:{field}")
    return {"text": text, "evidence_ids": [str(item) for item in ids]}


def validate_daily_thesis(output: Mapping[str, Any], request: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(output, Mapping) or output.get("generation_status") != "model_generated_unreviewed":
        raise DailyThesisError("thesis_generation_status_invalid")
    posture = str(output.get("posture") or "")
    if posture not in POSTURES:
        raise DailyThesisError("thesis_posture_invalid")
    known_ids = {str(item) for item in request.get("fact_evidence_ids") or []}
    if not known_ids:
        known_ids.update(str(item) for item in request.get("evidence_ids") or [])
    mechanism_ids = {str(item) for item in request.get("mechanism_ids") or []}
    numeric_values = [float(item) for item in request.get("numeric_values") or []]
    result = {
        "generation_status": "model_generated_unreviewed",
        "posture": posture,
        "headline": _statement(output.get("headline"), known_ids=known_ids, field="headline", numeric_values=numeric_values),
        "what_happened": _statement(output.get("what_happened"), known_ids=known_ids, field="what_happened", numeric_values=numeric_values),
        "world_model": _statement(output.get("world_model"), known_ids=known_ids, field="world_model", numeric_values=numeric_values),
        "leadership": _statement(output.get("leadership"), known_ids=known_ids, field="leadership", numeric_values=numeric_values),
        "laggards": _statement(output.get("laggards"), known_ids=known_ids, field="laggards", numeric_values=numeric_values),
        "capital_migration": _migration_statement(output.get("capital_migration"), known_ids=known_ids, numeric_values=numeric_values),
        "theoretical_mechanism": _mechanism_statement(output.get("theoretical_mechanism"), mechanism_ids=mechanism_ids, field="theoretical_mechanism"),
    }
    for field, minimum, maximum in (("watchpoints", 2, 8), ("actions", 1, 8), ("falsifiers", 1, 5)):
        rows = output.get(field)
        if not isinstance(rows, list) or not minimum <= len(rows) <= maximum:
            raise DailyThesisError(f"thesis_{field}_shape_invalid")
        result[field] = [_statement(row, known_ids=known_ids, field=f"{field}_{index}", numeric_values=numeric_values) for index, row in enumerate(rows)]
    return result


DAILY_THESIS_SYSTEM_PROMPT = """你是 Global Market K-line Daily 的跨资产主理人。只读取请求中的 19 个资产单资产分析和证据 ID，不读取 Finance Daily Newsletter，不调用新闻或外部知识，不补造数字。

请把各资产综合成一份当天的市场判断：headline、what_happened、world_model、leadership、laggards、capital_migration、theoretical_mechanism、watchpoints、actions、falsifiers。每个文字字段尽量只写一句；watchpoints 输出 2 条，actions 输出 1 条，falsifiers 输出 1 条。current observations 必须引用可用资产的 fact_evidence_ids；不可用周期不能支撑当前判断。theoretical_mechanism 只能引用 mechanism_ids。capital_migration 必须使用“可能、推断、更像、通常、反映、暗示”等合格推断语言，且严禁出现“直接资金流、资金净流入、真实资金流、资金正在流入、资金正在流出、资金已经流入、资金已经流出、资金明确流入、资金明确流出”等表述；它只能描述相对价格关系的推断。actions 只能写条件化的观察与参与框架，例如“若条件成立，再考虑参与”，严禁出现“个人、仓位、满仓、半仓、下单、订单、买入、卖出、自动执行、经纪”等词。可以提出有条件的交易建议，但不得给个人仓位、订单或自动执行。资本迁移是对价格相对关系的推断，不是直接资金流测量。所有文字使用简体中文，除官方资产符号外不要写英文句子或数字。

只返回合法 JSON：{"generation_status":"model_generated_unreviewed","posture":"attack|wait|defense|no_view","headline":{"text":"...","evidence_ids":["..."]},"what_happened":{"text":"...","evidence_ids":["..."]},"world_model":{"text":"...","evidence_ids":["..."]},"leadership":{"text":"...","evidence_ids":["..."]},"laggards":{"text":"...","evidence_ids":["..."]},"capital_migration":{"text":"...","evidence_ids":["..."]},"theoretical_mechanism":{"text":"...","evidence_ids":["mechanism:..."],"claim_type":"theoretical_mechanism"},"watchpoints":[{"text":"...","evidence_ids":["..."]}],"actions":[{"text":"...","evidence_ids":["..."]}],"falsifiers":[{"text":"...","evidence_ids":["..."]}]}"""


class DeepSeekDailyThesisProvider:
    provider_name = "DeepSeek"

    def __init__(self, key_file: Path | str, *, model: str = "deepseek-v4-flash") -> None:
        self.key_file = Path(key_file).expanduser().resolve()
        self.model = model

    def __call__(self, request: Mapping[str, Any]) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
        from deepseek_writer import call_structured_deepseek
        prompt = DAILY_THESIS_SYSTEM_PROMPT
        last: tuple[Mapping[str, Any], Mapping[str, Any]] | None = None
        for _attempt in range(3):
            output, receipt = call_structured_deepseek(
                system_prompt=prompt,
                request_object=request,
                key_file=self.key_file,
                model=self.model,
                max_tokens=9000,
                reasoning_effort="low",
                temperature=0.1,
                thinking_type="disabled",
            )
            last = (output, receipt)
            try:
                validate_daily_thesis(output, request)
                return output, receipt
            except DailyThesisError as exc:
                prompt += f"\n上一版未通过本地验证（{str(exc)[:160]}）。只修正这个字段：current facts 引用 fact_evidence_ids，理论只引用 mechanism_ids，数字必须来自 numeric_values，所有文字保持简体中文。"
        assert last is not None
        return last


def compile_daily_thesis(
    analysis_bundle: Mapping[str, Any],
    provider: Callable[[Mapping[str, Any]], Any] | None,
) -> dict[str, Any]:
    request = build_daily_thesis_request(analysis_bundle)
    request["evidence_ids"] = sorted(_evidence_ids(analysis_bundle))
    request_hash = _digest(request)
    if provider is None:
        output = {"generation_status": "thesis_unavailable", "failure_code": "provider_unavailable"}
        core = {"schema_version": SCHEMA_VERSION, "analysis_bundle_id": analysis_bundle["bundle_id"], "request_hash": request_hash, "output": output}
        return {"thesis_id": f"{THESIS_ID_PREFIX}{_digest(core)}", "identity_core": core, "output": output, **output}
    try:
        raw_result = provider(request)
        if isinstance(raw_result, tuple) and len(raw_result) == 2:
            raw, receipt = raw_result
        else:
            raw, receipt = raw_result, {"provider": "injected"}
        output = validate_daily_thesis(raw, request)
        output["provider_receipt"] = _safe_receipt(receipt)
    except ProviderFallbackError as exc:
        output = {
            "generation_status": "thesis_unavailable",
            "failure_code": exc.code,
            "provider_status": {
                "primary_provider": "DeepSeek",
                "primary_failure": exc.primary_failure,
                "fallback_provider": "Codex CLI",
                "fallback_failure": exc.fallback_failure,
                "both_failed": True,
            },
        }
    except DailyThesisError as exc:
        output = {"generation_status": "thesis_unavailable", "failure_code": str(exc)}
    except Exception as exc:
        output = {"generation_status": "thesis_unavailable", "failure_code": f"provider_error:{type(exc).__name__}"}
    core = {"schema_version": SCHEMA_VERSION, "analysis_bundle_id": analysis_bundle["bundle_id"], "request_hash": request_hash, "output": output}
    return {"thesis_id": f"{THESIS_ID_PREFIX}{_digest(core)}", "identity_core": core, "request": request, "output": output, **output}


def _coverage(asset: Mapping[str, Any]) -> str:
    statuses = asset.get("coverage") or {
        timeframe: (frame.get("status") if isinstance(frame, Mapping) else None)
        for timeframe, frame in (asset.get("timeframes") or {}).items()
    }
    labels = (("daily", "日线"), ("four_hour", "4小时"), ("thirty_minute", "30分钟"))
    return " · ".join(
        f"{label}：{'可用' if statuses.get(tf) == 'ready' else '不可用'}"
        for tf, label in labels
        if tf in statuses
    ) or "无已声明周期"


_SNAPSHOT_PATH_RE = re.compile(r"^snapshots/[A-Za-z0-9._-]+\.png$")
_IMAGE_MARKDOWN_RE = re.compile(r"^!\[([^\]]*)\]\((snapshots/[A-Za-z0-9._-]+\.png)\)$")


def _snapshot_path(snapshot: Any) -> str | None:
    if not isinstance(snapshot, Mapping) or not isinstance(snapshot.get("asset"), Mapping):
        return None
    path = str(snapshot["asset"].get("path") or "")
    return path if _SNAPSHOT_PATH_RE.fullmatch(path) else None


def _snapshot_markdown(asset: Mapping[str, Any], timeframe: str, label: str) -> str | None:
    snapshots = asset.get("snapshots") if isinstance(asset.get("snapshots"), Mapping) else {}
    path = _snapshot_path(snapshots.get(timeframe))
    if not path:
        return None
    display_name = str(asset.get("display_name") or asset.get("asset_key") or "资产")
    return f"![{display_name}｜{label} K 线图]({path})"


def _analysis_output(analysis: Mapping[str, Any]) -> Mapping[str, Any]:
    nested = analysis.get("output")
    return nested if isinstance(nested, Mapping) else analysis


def _daily_status_footer(delivery: Mapping[str, Any], analysis_bundle: Mapping[str, Any], cutoff: str) -> list[str]:
    total_slots = 0
    ready_slots = 0
    unavailable_slots = 0
    model_assets = 0
    deterministic_assets = 0
    both_failed_assets: list[str] = []
    for asset in analysis_bundle.get("assets") or []:
        request = asset.get("request") if isinstance(asset, Mapping) else {}
        frames = request.get("timeframes") if isinstance(request, Mapping) else {}
        for frame in frames.values() if isinstance(frames, Mapping) else []:
            total_slots += 1
            if isinstance(frame, Mapping) and frame.get("status") == "ready":
                ready_slots += 1
            else:
                unavailable_slots += 1
        analysis = asset.get("analysis") if isinstance(asset, Mapping) else {}
        if isinstance(analysis, Mapping) and analysis.get("generation_status") == "model_generated_unreviewed":
            model_assets += 1
        else:
            deterministic_assets += 1
            output = analysis.get("output") if isinstance(analysis, Mapping) else None
            provider_status = output.get("provider_status") if isinstance(output, Mapping) else None
            if isinstance(provider_status, Mapping) and provider_status.get("both_failed"):
                both_failed_assets.append(str(asset.get("display_name") or asset.get("asset_key") or "未知资产"))
    thesis_status = "已生成" if delivery.get("generation_status") == "model_generated_unreviewed" else "未生成"
    provider_receipt = delivery.get("provider_receipt") if isinstance(delivery.get("provider_receipt"), Mapping) else {}
    provider = str(provider_receipt.get("provider") or provider_receipt.get("model") or "未记录")
    provider_status = delivery.get("provider_status") if isinstance(delivery.get("provider_status"), Mapping) else {}
    lines = [
        "## 来源与状态",
        "",
        f"- 数据源状态：本期 {ready_slots}/{total_slots} 个已声明周期就绪；暂缺 {unavailable_slots} 个。",
        f"- 单资产解释：{model_assets} 个模型解释，{deterministic_assets} 个代码读数。",
        f"- 综合解释：{thesis_status} · provider：{provider}。",
        f"- 数据截至：{cutoff}",
        "- 本日报不读取 Finance Daily Newsletter。",
        "- 详细 source identity、evidence hash 和失败分类保留在运行回执中。",
        "- 内容仅供研究参考；不连接经纪账户，不自动执行交易。",
        "",
    ]
    if provider_status.get("both_failed"):
        lines.insert(
            4,
            f"- 模型失败披露：DeepSeek 与 Codex CLI 均未生成解释；主模型：{provider_status.get('primary_failure', '未知')}；备用模型：{provider_status.get('fallback_failure', '未知')}。",
        )
    if both_failed_assets:
        lines.insert(5, f"- 单资产模型失败披露：{', '.join(both_failed_assets)} 的 DeepSeek 与 Codex CLI 均未生成解释。")
    return lines


def render_daily_markdown(delivery: Mapping[str, Any], analysis_bundle: Mapping[str, Any]) -> str:
    thesis = delivery.get("output") or {}
    cutoff = str(delivery.get("cutoff_at") or analysis_bundle.get("cutoff_at") or "")
    report_date = _local_report_date(cutoff)
    lines = ["---", "title: 宏观 K 线日报", f"date: {report_date}", "report_type: kline-daily-newsletter", "---", "", f"# 宏观 K 线日报｜{report_date}", "", "> 只基于跨资产 K 线：日线看方向；资产有明确盘中源时，再用 4 小时或 30 分钟看上下文。未列出的周期不是失败，而是不在该资产的源能力合同内。", ""]
    lines.extend(["## 今日结论", ""])
    if thesis.get("generation_status") != "model_generated_unreviewed":
        lines.extend(["本期综合解释尚未生成。", "", "本日报保留本次真实图表和代码读数，没有把旧结论或模板判断当作今天的新结论。", ""])
    else:
        lines.extend([f"**{POSTURE_LABELS.get(thesis['posture'], thesis['posture'])}** · {thesis['headline']['text']}", "", thesis["what_happened"]["text"], "", "## 世界模型", "", thesis["world_model"]["text"], "", "## 盘面领导与落后", "", thesis["leadership"]["text"], "", thesis["laggards"]["text"], "", "## 资金迁移（价格关系推断）", "", thesis["capital_migration"]["text"], "", "## 理论机制", "", thesis["theoretical_mechanism"]["text"], "", "## 接下来观察", ""])
        lines.extend([f"{index}. {row['text']}" for index, row in enumerate(thesis["watchpoints"], 1)])
        lines.extend(["", "## 操作框架", ""])
        lines.extend([f"- {row['text']}" for row in thesis["actions"]])
        lines.extend(["", "## 失效条件", ""])
        lines.extend([f"- {row['text']}" for row in thesis["falsifiers"]])
        lines.append("")
    lines.extend(["## 每个资产的综合结论与市场含义", ""])
    for asset in analysis_bundle.get("assets") or []:
        lines.append(render_reader_asset_markdown(project_daily_asset(asset)))
        lines.append("")
    lines.extend(["## 数据边界", "", "- 已请求但抓取失败的周期保留为不可用，不代表横盘或没有变化；未列出的周期表示该资产当前没有纳入该周期请求。", ""])
    lines.extend(_daily_status_footer(delivery, analysis_bundle, cutoff))
    return "\n".join(lines)


def _render_daily_text_html(markdown: str) -> str:
    rendered_lines: list[str] = []
    for line in markdown.splitlines():
        match = _IMAGE_MARKDOWN_RE.fullmatch(line.strip())
        if match:
            alt, path = match.groups()
            rendered_lines.append(
                f"<figure class='daily-period-chart'><img src=\"{html.escape(path, quote=True)}\" alt=\"{html.escape(alt, quote=True)}\"><figcaption>{html.escape(alt)}</figcaption></figure>"
            )
        else:
            rendered_lines.append(html.escape(line))
    return "<br>".join(rendered_lines)


def render_daily_html(
    markdown: str,
    *,
    title: str = "宏观 K 线日报",
    reader_assets: list[Mapping[str, Any]] | None = None,
) -> str:
    if reader_assets:
        marker = "## 每个资产的综合结论与市场含义"
        footer_marker = "## 数据边界"
        start = markdown.find(marker)
        end = markdown.find(footer_marker, start + len(marker)) if start >= 0 else -1
        if start >= 0 and end >= 0:
            body = _render_daily_text_html(markdown[:start])
            body += "".join(render_reader_asset_html(asset) for asset in reader_assets)
            body += _render_daily_text_html(markdown[end:])
        else:
            body = _render_daily_text_html(markdown)
    else:
        body = _render_daily_text_html(markdown)
    css = "body{margin:0;background:#f4f6f2;color:#17201b;font-family:-apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei',sans-serif}main{max-width:1100px;margin:0 auto;background:#fffefa;min-height:100vh;padding:36px 28px;box-sizing:border-box}.content{font-size:16px;line-height:1.8;white-space:normal}.daily-period-chart{margin:18px 0 8px;padding:0;border:1px solid #e2e5df;background:#fffefa}.daily-period-chart img{display:block;width:100%;height:auto}.daily-period-chart figcaption{padding:6px 10px;color:#7b857e;font-size:11px;line-height:1.4}.reader-asset{margin:18px 0;border:1px solid #dedfd8;background:#fff}.reader-asset>header{display:flex;justify-content:space-between;padding:17px;border-bottom:1px solid #dedfd8}.reader-asset h2{font-size:27px;margin:0}.reader-asset .timeframe{display:flex;flex-direction:column;gap:12px;padding:16px;border-bottom:1px solid #dedfd8;margin:0}.reader-asset .timeframe b{display:block;color:#187b51;font-size:10px;letter-spacing:.1em;margin-bottom:7px}.reader-asset .snapshot-frame{width:100%;background:#fffefa;border:1px solid #eceee8;overflow:hidden}.reader-asset .snapshot-frame img{display:block;width:100%;height:auto}.reader-asset .chart-unavailable{min-height:150px;display:grid;place-items:center;padding:16px;text-align:center;color:#8a6425;background:#fff8ed}.reader-asset .timeframe p{font-size:17px;line-height:1.75;margin:0}.reader-asset .summary-dimensions{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;padding:14px 16px;background:#f7f9f5;border-bottom:1px solid #dedfd8}.reader-asset .summary-dimensions>div{border-left:3px solid #187b51;padding-left:10px}.reader-asset .summary-dimensions b{font-size:10px;color:#187b51;letter-spacing:.1em}.reader-asset .summary-dimensions p{font-size:15px;line-height:1.55;margin:4px 0}.reader-asset .synthesis{padding:17px;background:#edf3ef}.reader-asset .synthesis b{font-size:10px;color:#187b51;letter-spacing:.1em}.reader-asset .synthesis p{font-size:18px;line-height:1.65;margin:6px 0}@media(max-width:600px){main{padding:22px 16px}.content{font-size:15px}.daily-period-chart{margin-inline:-4px}.reader-asset .summary-dimensions{grid-template-columns:1fr}.reader-asset .timeframe p{font-size:16px}}";
    return f"<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title><style>{css}</style></head><body><main><div class='content'>{body}</div></main></body></html>"


class DailyThesisDeliveryStore:
    """Publish an immutable Daily thesis and copy Markdown to Obsidian."""

    def __init__(self, *, runtime_root: Path | str, output_root: Path | str, archive_root: Path | str) -> None:
        self.runtime_root = Path(runtime_root).expanduser().resolve()
        self.output_root = Path(output_root).expanduser().resolve()
        self.archive_root = Path(archive_root).expanduser().resolve()

    def _copy_snapshot_assets(self, analysis_bundle: Mapping[str, Any]) -> list[dict[str, str]]:
        copied: list[dict[str, str]] = []
        seen: set[str] = set()
        for asset in analysis_bundle.get("assets") or []:
            snapshots = asset.get("snapshots") if isinstance(asset, Mapping) and isinstance(asset.get("snapshots"), Mapping) else {}
            for snapshot in snapshots.values():
                path = _snapshot_path(snapshot)
                if not path or path in seen:
                    continue
                seen.add(path)
                source = self.output_root / path
                target = self.archive_root / path
                if not source.is_file():
                    raise DailyThesisError(f"snapshot_source_missing:{path}")
                payload = source.read_bytes()
                expected = str((snapshot.get("asset") or {}).get("sha256") or "") if isinstance(snapshot, Mapping) else ""
                actual = hashlib.sha256(payload).hexdigest()
                if expected and expected != actual:
                    raise DailyThesisError(f"snapshot_hash_mismatch:{path}")
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists() and target.read_bytes() != payload:
                    raise DailyThesisError(f"snapshot_archive_conflict:{path}")
                if not target.exists():
                    shutil.copyfile(source, target)
                copied.append({"path": path, "sha256": actual})
        return copied

    def publish(self, thesis: Mapping[str, Any], analysis_bundle: Mapping[str, Any]) -> dict[str, Any]:
        analysis_bundle = validate_daily_analysis_bundle(analysis_bundle)
        if not str(thesis.get("thesis_id") or "").startswith(THESIS_ID_PREFIX):
            raise DailyThesisError("thesis_identity_invalid")
        thesis_id = str(thesis["thesis_id"])
        digest = thesis_id.removeprefix(THESIS_ID_PREFIX)
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise DailyThesisError("thesis_identity_invalid")
        identity_core = thesis.get("identity_core")
        if not isinstance(identity_core, Mapping) or _digest(identity_core) != digest:
            raise DailyThesisError("thesis_identity_mismatch")
        if identity_core.get("analysis_bundle_id") != analysis_bundle.get("bundle_id"):
            raise DailyThesisError("thesis_analysis_binding_invalid")
        if thesis.get("generation_status") == "model_generated_unreviewed":
            request = thesis.get("request")
            output = thesis.get("output")
            if not isinstance(request, Mapping) or not isinstance(output, Mapping):
                raise DailyThesisError("thesis_output_binding_invalid")
            if request.get("analysis_bundle_id") != analysis_bundle.get("bundle_id"):
                raise DailyThesisError("thesis_request_analysis_binding_invalid")
            validate_daily_thesis(output, request)
        elif thesis.get("generation_status") != "thesis_unavailable" or not thesis.get("failure_code"):
            raise DailyThesisError("thesis_generation_status_invalid")
        snapshot_assets = self._copy_snapshot_assets(analysis_bundle)
        markdown = render_daily_markdown({**thesis, "cutoff_at": analysis_bundle.get("cutoff_at")}, analysis_bundle)
        reader_assets = [project_daily_asset(asset) for asset in analysis_bundle.get("assets") or []]
        html_text = render_daily_html(markdown, reader_assets=reader_assets)
        core = {"schema_version": SCHEMA_VERSION, "thesis_id": thesis_id, "analysis_bundle_id": analysis_bundle.get("bundle_id"), "markdown_sha256": hashlib.sha256(markdown.encode()).hexdigest(), "html_sha256": hashlib.sha256(html_text.encode()).hexdigest(), "snapshot_assets": snapshot_assets, "cutoff_at": analysis_bundle.get("cutoff_at")}
        delivery_id = f"{DELIVERY_ID_PREFIX}{_digest(core)}"
        artifact_dir = self.runtime_root / "delivery" / "artifacts"
        md_ref = {"path": f"artifacts/{digest}.md", "sha256": _immutable_bytes(artifact_dir / f"{digest}.md", markdown.encode("utf-8"))}
        html_ref = {"path": f"artifacts/{digest}.html", "sha256": _immutable_bytes(artifact_dir / f"{digest}.html", html_text.encode("utf-8"))}
        archive_date = _local_report_date(analysis_bundle.get("cutoff_at"))
        archive_path = self.archive_root / f"{archive_date}-kline-daily-newsletter.md"
        if archive_path.exists() and archive_path.read_bytes() != markdown.encode("utf-8"):
            archive_path = self.archive_root / f"{archive_date}-kline-daily-newsletter-{digest[:12]}.md"
        _atomic_bytes(archive_path, markdown.encode("utf-8"))
        _atomic_bytes(self.output_root / "latest.md", markdown.encode("utf-8"))
        _atomic_bytes(self.output_root / "latest.html", html_text.encode("utf-8"))
        archive_hash = hashlib.sha256(archive_path.read_bytes()).hexdigest()
        aliases = {
            "markdown": {"path": "latest.md", "sha256": hashlib.sha256((self.output_root / "latest.md").read_bytes()).hexdigest()},
            "html": {"path": "latest.html", "sha256": hashlib.sha256((self.output_root / "latest.html").read_bytes()).hexdigest()},
        }
        receipt = {"schema_version": SCHEMA_VERSION, "delivery_id": delivery_id, "identity_core": core, "thesis_id": thesis_id, "analysis_bundle_id": analysis_bundle.get("bundle_id"), "cutoff_at": archive_date, "markdown": md_ref, "html": html_ref, "snapshot_assets": snapshot_assets, "archive": {"path": str(archive_path), "sha256": archive_hash}, "aliases": aliases, "generation_status": thesis.get("generation_status")}
        receipt_bytes = (_canonical(receipt) + "\n").encode("utf-8")
        receipt_ref = {"path": f"receipts/{delivery_id.removeprefix(DELIVERY_ID_PREFIX)}.json", "sha256": _immutable_bytes(self.runtime_root / "delivery" / f"receipts/{delivery_id.removeprefix(DELIVERY_ID_PREFIX)}.json", receipt_bytes)}
        state = {"schema_version": SCHEMA_VERSION, "delivery_id": delivery_id, "receipt": receipt_ref}
        _atomic_bytes(self.runtime_root / "delivery" / "latest.json", (_canonical(state) + "\n").encode("utf-8"))
        readback = self.latest()
        if readback.get("delivery_id") != delivery_id:
            raise DailyThesisError("delivery_readback_identity_mismatch")
        return {**receipt, "delivery_id": delivery_id, "receipt": receipt_ref}

    def latest(self) -> dict[str, Any]:
        try:
            state = json.loads((self.runtime_root / "delivery" / "latest.json").read_text(encoding="utf-8"))
            if state.get("state") == "unavailable":
                if not str(state.get("failure_code") or "") or not str(state.get("delivery_id") or "").startswith(DELIVERY_ID_PREFIX):
                    raise DailyThesisError("delivery_unavailable_state_invalid")
                return state
            delivery_id = str(state.get("delivery_id") or "")
            if state.get("schema_version") != SCHEMA_VERSION or not delivery_id.startswith(DELIVERY_ID_PREFIX):
                raise DailyThesisError("delivery_state_invalid")
            receipt_ref = state.get("receipt") or {}
            receipt_path = (self.runtime_root / "delivery" / str(receipt_ref.get("path") or "")).resolve()
            if self.runtime_root.resolve() not in receipt_path.parents:
                raise DailyThesisError("delivery_receipt_path_escape")
            receipt_bytes = receipt_path.read_bytes()
            if receipt_ref.get("sha256") != hashlib.sha256(receipt_bytes).hexdigest():
                raise DailyThesisError("delivery_receipt_hash_invalid")
            receipt = json.loads(receipt_bytes.decode("utf-8"))
            if receipt.get("delivery_id") != delivery_id:
                raise DailyThesisError("delivery_receipt_identity_invalid")
            receipt_core = receipt.get("identity_core")
            if not isinstance(receipt_core, Mapping) or _digest(receipt_core) != delivery_id.removeprefix(DELIVERY_ID_PREFIX):
                raise DailyThesisError("delivery_receipt_core_invalid")
            if receipt.get("thesis_id") != receipt_core.get("thesis_id") or receipt.get("analysis_bundle_id") != receipt_core.get("analysis_bundle_id"):
                raise DailyThesisError("delivery_receipt_binding_invalid")
            for field in ("markdown", "html"):
                reference = receipt.get(field) or {}
                artifact_path = (self.runtime_root / "delivery" / str(reference.get("path") or "")).resolve()
                if self.runtime_root.resolve() not in artifact_path.parents:
                    raise DailyThesisError("delivery_artifact_path_escape")
                artifact_bytes = artifact_path.read_bytes()
                if reference.get("sha256") != hashlib.sha256(artifact_bytes).hexdigest():
                    raise DailyThesisError(f"delivery_{field}_hash_invalid")
            archive = receipt.get("archive") or {}
            archive_path = Path(str(archive.get("path") or "")).expanduser().resolve()
            if self.archive_root.resolve() not in archive_path.parents or archive.get("sha256") != hashlib.sha256(archive_path.read_bytes()).hexdigest():
                raise DailyThesisError("delivery_archive_invalid")
            for alias in (receipt.get("aliases") or {}).values():
                alias_path = (self.output_root / str(alias.get("path") or "")).resolve()
                if self.output_root.resolve() not in alias_path.parents or alias.get("sha256") != hashlib.sha256(alias_path.read_bytes()).hexdigest():
                    raise DailyThesisError("delivery_alias_invalid")
            return receipt
        except FileNotFoundError as exc:
            raise DailyThesisError("delivery_latest_unavailable") from exc
        except json.JSONDecodeError as exc:
            raise DailyThesisError("delivery_latest_json_invalid") from exc


__all__ = [
    "DAILY_THESIS_SYSTEM_PROMPT",
    "DailyThesisDeliveryStore",
    "DailyThesisError",
    "DeepSeekDailyThesisProvider",
    "build_daily_thesis_request",
    "compile_daily_thesis",
    "render_daily_html",
    "render_daily_markdown",
    "validate_daily_analysis_bundle",
    "validate_daily_thesis",
    "_local_report_date",
]
