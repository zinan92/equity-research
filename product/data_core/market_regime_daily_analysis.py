"""Per-asset Daily K-line analysis over an immutable source bundle."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import os
import tempfile
from typing import Any, Callable, Mapping

from .market_regime_daily_source import (
    DAILY_TIMEFRAMES,
    DAILY_TIMEFRAMES_BY_ASSET,
    SCHEMA_VERSION as SOURCE_SCHEMA,
    validate_daily_source_bundle,
)
from .market_regime_weekly_features import WeeklyFeatureError, build_timeframe_features
from .market_regime_weekly_mechanisms import mechanism_for_asset, validate_theoretical_statement
from .market_regime_weekly_position_structure import WeeklyPositionStructureError, build_position_structure
from .market_regime_weekly_source import DISPLAY_NAMES, WEEKLY_KEYS


SCHEMA_VERSION = "market-regime-daily-asset-analysis-v2"
ANALYSIS_ID_PREFIX = "market-regime-daily-asset-analysis:"
BUNDLE_ID_PREFIX = "market-regime-daily-analysis:"
ALLOWED_LATIN_WORDS = frozenset(
    {
        "Nasdaq", "Bitcoin", "Ethereum", "Nikkei", "KOSPI", "SCHD", "SPY", "QQQ", "UUP",
        "BTC", "ETH", "HYPE", "GC", "CL", "SI", "USDT", "USDC", "OHLC", "MACD", "EMA", "DXY", "VIX", "WTI", "ETF",
    }
)
_TIMEFRAME_LABELS = {"daily": "日线", "four_hour": "4小时", "thirty_minute": "30分钟"}


class DailyAnalysisError(ValueError):
    """A Daily per-asset request or output violated its contract."""


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _immutable_bytes(path: Path, payload: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(payload).hexdigest()
    if path.exists():
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise DailyAnalysisError("analysis_artifact_immutable_conflict")
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


def _has_forbidden_english(text: str) -> bool:
    words = re.findall(r"[A-Za-z]{4,}", text)
    return any(word not in ALLOWED_LATIN_WORDS for word in words)


def _numeric_tokens(text: str) -> list[float]:
    numeric_free = text.replace("4小时", "").replace("30分钟", "").replace("2s10s", "").replace("2Y", "").replace("10Y", "")
    numeric_free = re.sub(r"\d+\s*(?:日|天|小时|分钟|周期)", "", numeric_free)
    values: list[float] = []
    for match in re.finditer(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?", numeric_free):
        try:
            values.append(float(match.group(0)))
        except ValueError:
            continue
    return values


def _numbers_for_evidence(text: str, evidence_ids: list[str], request: Mapping[str, Any]) -> None:
    tokens = _numeric_tokens(text)
    if not tokens:
        return
    candidates: list[float] = []
    for frame in (request.get("timeframes") or {}).values():
        if not isinstance(frame, Mapping) or not set(evidence_ids).intersection(str(item) for item in frame.get("evidence_ids") or []):
            continue
        def walk(value: Any) -> None:
            if isinstance(value, bool):
                return
            if isinstance(value, (int, float)):
                if value == value and abs(float(value)) != float("inf"):
                    candidates.append(float(value))
            elif isinstance(value, Mapping):
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)
        walk(frame.get("points") or [])
        walk(frame.get("features") or {})
    if any(not any(abs(token - candidate) <= max(0.051, abs(candidate) * 0.0005) for candidate in candidates) for token in tokens):
        raise DailyAnalysisError("analysis_numeric_observation_unbound")


def _source_evidence_id(asset_key: str, timeframe: str, slot: Mapping[str, Any]) -> str:
    digest = str((slot.get("source_identity") or {}).get("response_sha256") or "")
    if not digest:
        digest = _digest({"asset_key": asset_key, "timeframe": timeframe, "status": slot.get("status"), "reason": slot.get("reason_code")})
    return f"daily-source:{asset_key}:{timeframe}:{digest}"


def build_daily_asset_request(asset: Mapping[str, Any], *, cutoff_at: str | None = None) -> dict[str, Any]:
    """Project one source-bundle asset into bounded per-asset model input."""

    key = str(asset.get("asset_key") or "")
    if key not in WEEKLY_KEYS:
        raise DailyAnalysisError(f"asset_key_unknown:{key}")
    instrument = asset.get("instrument")
    if not isinstance(instrument, Mapping):
        raise DailyAnalysisError(f"instrument_missing:{key}")
    raw_slots = asset.get("slots")
    allowed_timeframes = DAILY_TIMEFRAMES_BY_ASSET.get(key, ())
    if not isinstance(raw_slots, Mapping) or set(raw_slots) != set(allowed_timeframes):
        raise DailyAnalysisError(f"timeframe_slots_invalid:{key}")
    timeframes: dict[str, dict[str, Any]] = {}
    for timeframe in allowed_timeframes:
        slot = raw_slots[timeframe]
        if not isinstance(slot, Mapping):
            raise DailyAnalysisError(f"slot_invalid:{key}:{timeframe}")
        evidence_id = _source_evidence_id(key, timeframe, slot)
        source_identity = slot.get("source_identity")
        if not isinstance(source_identity, Mapping) or not str(source_identity.get("response_sha256") or ""):
            raise DailyAnalysisError(f"source_identity_missing:{key}:{timeframe}")
        series = {
            "key": key,
            "series_kind": instrument.get("series_kind"),
            "unit": instrument.get("unit"),
            "source_identity": source_identity,
            "points": slot.get("bars") or [],
        }
        try:
            features = build_timeframe_features(series, timeframe=timeframe, cutoff_at=cutoff_at)
        except WeeklyFeatureError as exc:
            features = {
                "schema_version": "market-regime-weekly-features-v1",
                "key": key,
                "timeframe": timeframe,
                "status": "unavailable",
                "source_point_count": 0,
                "points": [],
                "x_labels": [],
                "y_labels": [],
                "current": None,
                "feature_identity": _digest({"key": key, "timeframe": timeframe, "error": str(exc)}),
                "failure_code": f"feature_compile:{type(exc).__name__}",
                "source_identity": series["source_identity"],
            }
        feature_id = f"feature:{features['feature_identity']}"
        evidence_ids = [evidence_id, feature_id]
        timeframes[timeframe] = {
            "label": _TIMEFRAME_LABELS[timeframe],
            "status": slot.get("status", "unavailable"),
            "reason_code": slot.get("reason_code"),
            "completion_state": slot.get("completion_state", "unavailable"),
            "is_provisional": bool(slot.get("is_provisional", False)),
            "latest_timestamp": slot.get("latest_timestamp"),
            "unit": instrument.get("unit"),
            "points": list(slot.get("bars") or [])[-160:],
            "features": features,
            "evidence_ids": evidence_ids,
            "source_identity": dict(slot.get("source_identity") or {}),
        }
    mechanism = mechanism_for_asset(key)
    return {
        "schema_version": SCHEMA_VERSION,
        "source_schema_version": SOURCE_SCHEMA,
        "asset_key": key,
        "display_name": str(asset.get("display_name") or DISPLAY_NAMES.get(key, key)),
        "canonical_symbol": instrument.get("canonical_symbol"),
        "series_kind": instrument.get("series_kind"),
        "unit": instrument.get("unit"),
        "price_basis": instrument.get("price_basis"),
        "cutoff_at": cutoff_at,
        "timeframes": timeframes,
        "mechanism": mechanism,
        "truth_boundary": {
            "model_generated_unreviewed": True,
            "observations_are_evidence_bound": True,
            "theory_is_not_current_measurement": True,
            "automatic_execution_eligible": False,
            "broker_access": False,
        },
    }


def _validate_statement(value: Any, *, known_ids: set[str], field: str, request: Mapping[str, Any], allow_numeric_unbound: bool = False) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not isinstance(value.get("text"), str) or not value["text"].strip():
        raise DailyAnalysisError(f"statement_invalid:{field}")
    evidence_ids = value.get("evidence_ids")
    if not isinstance(evidence_ids, list) or not evidence_ids or any(item not in known_ids for item in evidence_ids):
        raise DailyAnalysisError(f"evidence_ids_invalid:{field}")
    if _has_forbidden_english(value["text"]):
        raise DailyAnalysisError(f"analysis_language_not_chinese:{field}")
    if not allow_numeric_unbound:
        _numbers_for_evidence(value["text"], [str(item) for item in evidence_ids], request)
    return {"text": value["text"].strip(), "evidence_ids": list(evidence_ids)}


def validate_daily_asset_analysis(output: Mapping[str, Any], request: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(output, Mapping) or output.get("asset_key") != request.get("asset_key"):
        raise DailyAnalysisError("analysis_asset_identity_mismatch")
    generation_status = str(output.get("generation_status") or "")
    if generation_status == "analysis_unavailable":
        if not str(output.get("failure_code") or ""):
            raise DailyAnalysisError("analysis_failure_code_missing")
        return {"asset_key": request["asset_key"], "generation_status": generation_status, "failure_code": str(output["failure_code"])}
    if generation_status != "model_generated_unreviewed":
        raise DailyAnalysisError("analysis_generation_status_invalid")
    frames = request.get("timeframes")
    expected_timeframes = set(DAILY_TIMEFRAMES_BY_ASSET.get(str(request.get("asset_key") or ""), ()))
    if not isinstance(frames, Mapping) or set(frames) != expected_timeframes:
        raise DailyAnalysisError("analysis_request_timeframes_invalid")
    fact_ids = {
        str(evidence_id)
        for frame in frames.values()
        if isinstance(frame, Mapping)
        for evidence_id in frame.get("evidence_ids") or []
    }
    mechanism = request.get("mechanism")
    if not isinstance(mechanism, Mapping) or mechanism.get("asset_key") != request.get("asset_key"):
        raise DailyAnalysisError("analysis_mechanism_invalid")
    mechanism_ids = {str(item) for item in mechanism.get("mechanism_ids") or []}
    if not mechanism_ids:
        raise DailyAnalysisError("analysis_mechanism_ids_missing")
    known_ids = set(fact_ids)
    result: dict[str, Any] = {"asset_key": request["asset_key"], "generation_status": generation_status}
    for timeframe in (item for item in DAILY_TIMEFRAMES if item in frames):
        frame = frames[timeframe]
        statement = _validate_statement(output.get(timeframe), known_ids=known_ids, field=timeframe, request=request, allow_numeric_unbound=frame.get("status") != "ready")
        if frame.get("status") != "ready":
            source_id = (frame.get("evidence_ids") or [None])[0]
            if source_id not in statement["evidence_ids"]:
                raise DailyAnalysisError(f"unavailable_evidence_missing:{timeframe}")
            if not any(token in statement["text"] for token in ("不可用", "无可用", "证据不足", "未提供", "未获取")):
                raise DailyAnalysisError(f"unavailable_disclosure_missing:{timeframe}")
        result[timeframe] = statement
    result["synthesis"] = _validate_statement(output.get("synthesis"), known_ids=known_ids, field="synthesis", request=request)
    try:
        result["market_meaning"] = validate_theoretical_statement(output.get("market_meaning"), mechanism_ids)
    except ValueError as exc:
        raise DailyAnalysisError(str(exc)) from exc
    result["confirmation"] = _validate_statement(output.get("confirmation"), known_ids=known_ids, field="confirmation", request=request)
    result["invalidation"] = _validate_statement(output.get("invalidation"), known_ids=known_ids, field="invalidation", request=request)
    result["rationale"] = _validate_statement(output.get("rationale"), known_ids=known_ids, field="rationale", request=request)
    opportunity = str(output.get("opportunity_state") or "")
    if opportunity not in {"participate", "wait", "avoid"}:
        raise DailyAnalysisError("opportunity_state_invalid")
    result["opportunity_state"] = opportunity
    return result


def _terminal_failure(request: Mapping[str, Any], failure_code: str, deterministic: Mapping[str, Any]) -> dict[str, Any]:
    output = {
        "schema_version": SCHEMA_VERSION,
        "asset_key": request["asset_key"],
        "request_hash": _digest(request),
        "generation_status": "analysis_unavailable",
        "failure_code": failure_code,
        "deterministic": dict(deterministic),
    }
    core = {"schema_version": SCHEMA_VERSION, "asset_key": request["asset_key"], "request_hash": output["request_hash"], "output": output}
    return {
        "analysis_id": f"{ANALYSIS_ID_PREFIX}{_digest(core)}",
        "identity_core": core,
        "output_hash": _digest(output),
        "output": output,
        **output,
    }


def _safe_provider_receipt(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {"provider": "injected", "receipt_hash": _digest(str(value))}
    allowed = ("provider", "model", "request_hash", "prompt_hash", "prompt_version", "generation_status", "attempt_count", "output_hash")
    safe = {key: value[key] for key in allowed if key in value and isinstance(value[key], (str, int, float, bool, type(None)))}
    safe["receipt_hash"] = _digest(safe)
    return safe


def compile_daily_asset_analysis(
    request: Mapping[str, Any],
    provider: Callable[[Mapping[str, Any]], Any] | None,
) -> dict[str, Any]:
    """Compile deterministic dimensions and one bounded model explanation."""

    request_hash = _digest(request)
    try:
        deterministic = build_position_structure(request)
    except WeeklyPositionStructureError:
        deterministic = {"position": {"state": "unknown"}, "structure": {"state": "unknown"}}
    if provider is None:
        return _terminal_failure(request, "provider_unavailable", deterministic)
    provider_receipt: dict[str, Any] = {"provider": "injected"}
    try:
        raw_result = provider(request)
        if isinstance(raw_result, tuple) and len(raw_result) == 2:
            raw, receipt = raw_result
            provider_receipt = _safe_provider_receipt(receipt)
        else:
            raw = raw_result
        output = validate_daily_asset_analysis(raw, request)
    except DailyAnalysisError as exc:
        return _terminal_failure(request, str(exc), deterministic)
    except Exception as exc:
        return _terminal_failure(request, f"provider_error:{type(exc).__name__}", deterministic)
    output = {
        "schema_version": SCHEMA_VERSION,
        "asset_key": request["asset_key"],
        "request_hash": request_hash,
        **output,
        "deterministic": deterministic,
        "provider_receipt": provider_receipt,
    }
    core = {"schema_version": SCHEMA_VERSION, "asset_key": request["asset_key"], "request_hash": request_hash, "output": output}
    return {
        "analysis_id": f"{ANALYSIS_ID_PREFIX}{_digest(core)}",
        "identity_core": core,
        "output_hash": _digest(output),
        **output,
    }


DAILY_ASSET_SYSTEM_PROMPT = """你是 Global Market K-line Daily 的单资产分析师。只读取请求中的冻结 K 线和代码特征，不读取新闻或外部知识，不补造数字。

请只解释 request.timeframes 中实际提供的周期；不要为未出现在 request.timeframes 中的周期补写字段或内容。某个已请求周期不可用时明确说证据不可用，不能把它当作横盘。然后输出一个综合结论与一个静态机制解释。机制解释必须使用请求中的 mechanism 目录，说明常见驱动、通常后果和反例；它不是当前事实，也不是实时因果归因。

所有当前判断都必须引用请求中的 evidence_ids；机制解释引用 mechanism:*。如需数字，必须能在所引用的 feature:* 证据中找到；否则删掉数字，不要猜测。

只返回合法 JSON，且严格遵守以下格式：
- `generation_status` 必须逐字为 `model_generated_unreviewed`，不能写 `complete`、`success` 或其它状态。
- `daily`、`four_hour`、`thirty_minute`（仅输出 request.timeframes 中实际存在的字段）必须是对象 `{\"text\":\"简体中文\",\"evidence_ids\":[\"请求中的证据 ID\"]}`，绝不能是纯字符串。
- `synthesis`、`confirmation`、`invalidation`、`rationale` 也必须是同样的 `{text,evidence_ids}` 对象，不能是纯字符串。
- `market_meaning` 必须是 `{\"text\":\"简体中文\",\"evidence_ids\":[\"mechanism:...\"],\"claim_type\":\"theoretical_mechanism\"}` 对象。
- `opportunity_state` 必须逐字使用英文枚举 `participate`、`wait` 或 `avoid` 之一，不能写中文或其它词。
- 顶层必须包含 `asset_key`、`generation_status`、`synthesis`、`market_meaning`、`confirmation`、`invalidation`、`rationale`、`opportunity_state`；不要输出其它周期字段。
禁止输出个人仓位、订单、保证收益或自动执行。"""


class DeepSeekDailyAssetProvider:
    """Bounded DeepSeek adapter for one isolated Daily asset."""

    provider_name = "DeepSeek"

    def __init__(self, key_file: Path | str, *, model: str = "deepseek-v4-flash") -> None:
        self.key_file = Path(key_file).expanduser().resolve()
        self.model = model

    def __call__(self, request: Mapping[str, Any]) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
        from deepseek_writer import call_structured_deepseek
        prompt = DAILY_ASSET_SYSTEM_PROMPT
        last: tuple[Mapping[str, Any], Mapping[str, Any]] | None = None
        for attempt in range(3):
            output, receipt = call_structured_deepseek(
                system_prompt=prompt,
                request_object=request,
                key_file=self.key_file,
                model=self.model,
                max_tokens=3500,
                reasoning_effort="low",
                temperature=0.1,
                thinking_type="disabled",
            )
            last = (output, receipt)
            try:
                validate_daily_asset_analysis(output, request)
                return output, {**receipt, "attempt_count": attempt + 1}
            except DailyAnalysisError as exc:
                prompt += (
                    f"\n上一版输出未通过本地验证：{str(exc)[:240]}。"
                    "请只修复该协议错误；generation_status 必须为 model_generated_unreviewed；"
                    "所有叙事字段必须是带 text 和 evidence_ids 的 JSON 对象，不能是字符串；"
                    "数字只能来自引用的 feature:* 证据；opportunity_state 只能是 participate、wait、avoid 三个英文枚举。"
                )
        assert last is not None
        output, receipt = last
        return output, {**receipt, "attempt_count": 3}


def build_daily_analysis_bundle(
    source_bundle: Mapping[str, Any],
    *,
    provider_factory: Callable[[Mapping[str, Any]], Callable[[Mapping[str, Any]], Any] | None] | None = None,
    cutoff_at: str | None = None,
    snapshot_port: Any | None = None,
) -> dict[str, Any]:
    """Compile 19 isolated asset analyses from one source bundle."""

    source_bundle = validate_daily_source_bundle(source_bundle)
    if source_bundle.get("schema_version") != SOURCE_SCHEMA or source_bundle.get("source_status") == "unavailable":
        raise DailyAnalysisError("source_bundle_unavailable")
    generated_at = cutoff_at or str(source_bundle.get("cutoff_at") or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    analyses: list[dict[str, Any]] = []
    for asset in source_bundle.get("assets") or []:
        request = build_daily_asset_request(asset, cutoff_at=generated_at)
        provider = provider_factory(request) if provider_factory is not None else None
        artifact = compile_daily_asset_analysis(request, provider)
        analyses.append(
            {
                "asset_key": request["asset_key"],
                "display_name": request["display_name"],
                "request": request,
                "analysis": artifact,
            }
        )
    if [item.get("asset_key") for item in analyses] != list(WEEKLY_KEYS):
        raise DailyAnalysisError("analysis_asset_universe_invalid")
    snapshots = snapshot_port.render(source_bundle) if snapshot_port is not None else {}
    for item in analyses:
        item["snapshots"] = {
            timeframe: snapshots.get(f"{item['asset_key']}:{timeframe}")
            for timeframe in (item["request"].get("timeframes") or {})
            if f"{item['asset_key']}:{timeframe}" in snapshots
        }
    identity_core = {
        "schema_version": SCHEMA_VERSION,
        "source_bundle_id": source_bundle.get("bundle_id"),
        "cutoff_at": generated_at,
        "analysis_hashes": [item["analysis"].get("output_hash") for item in analyses],
        "assets_sha256": _digest(analyses),
    }
    bundle_id = f"{BUNDLE_ID_PREFIX}{_digest(identity_core)}"
    return {
        "bundle_id": bundle_id,
        "schema_version": SCHEMA_VERSION,
        "source_bundle_id": source_bundle.get("bundle_id"),
        "cutoff_at": generated_at,
        "analysis_status": "ready" if all(item["analysis"].get("generation_status") == "model_generated_unreviewed" for item in analyses) else "partial",
        "identity_core": identity_core,
        "assets": analyses,
    }


class DailyAnalysisStore:
    """Content-addressed per-asset analysis bundles and latest pointer."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).expanduser().resolve()
        self.artifacts = self.root / "artifacts"
        self.latest_path = self.root / "latest.json"

    def publish(self, bundle: Mapping[str, Any]) -> dict[str, Any]:
        value = dict(bundle)
        bundle_id = str(value.get("bundle_id") or "")
        digest = bundle_id.removeprefix(BUNDLE_ID_PREFIX)
        if not bundle_id.startswith(BUNDLE_ID_PREFIX) or digest != _digest(value.get("identity_core")):
            raise DailyAnalysisError("analysis_bundle_identity_invalid")
        if value["identity_core"].get("assets_sha256") != _digest(value.get("assets")):
            raise DailyAnalysisError("analysis_bundle_assets_hash_invalid")
        payload = (_canonical(value) + "\n").encode("utf-8")
        self.artifacts.mkdir(parents=True, exist_ok=True)
        artifact = self.artifacts / f"{digest}.json"
        artifact_hash = _immutable_bytes(artifact, payload)
        pointer = {
            "schema_version": SCHEMA_VERSION,
            "bundle_id": bundle_id,
            "artifact": {"path": f"artifacts/{digest}.json", "sha256": artifact_hash},
            "published_at": value.get("cutoff_at"),
        }
        _atomic_bytes(self.latest_path, (_canonical(pointer) + "\n").encode("utf-8"))
        return pointer

    def latest(self) -> dict[str, Any]:
        try:
            pointer = json.loads(self.latest_path.read_text(encoding="utf-8"))
            bundle_id = str(pointer.get("bundle_id") or "")
            digest = bundle_id.removeprefix(BUNDLE_ID_PREFIX)
            if pointer.get("schema_version") != SCHEMA_VERSION or not bundle_id.startswith(BUNDLE_ID_PREFIX):
                raise DailyAnalysisError("analysis_pointer_invalid")
            artifact_path = (self.root / str((pointer.get("artifact") or {}).get("path") or "")).resolve()
            if self.root.resolve() not in artifact_path.parents:
                raise DailyAnalysisError("analysis_pointer_path_escape")
            payload = artifact_path.read_bytes()
            if (pointer.get("artifact") or {}).get("sha256") != hashlib.sha256(payload).hexdigest():
                raise DailyAnalysisError("analysis_pointer_hash_invalid")
            bundle = json.loads(payload.decode("utf-8"))
            if bundle.get("bundle_id") != bundle_id or _digest(bundle.get("identity_core")) != digest:
                raise DailyAnalysisError("analysis_artifact_identity_invalid")
            if bundle["identity_core"].get("assets_sha256") != _digest(bundle.get("assets")):
                raise DailyAnalysisError("analysis_artifact_assets_hash_invalid")
            return bundle
        except FileNotFoundError as exc:
            raise DailyAnalysisError("analysis_latest_unavailable") from exc
        except json.JSONDecodeError as exc:
            raise DailyAnalysisError("analysis_latest_json_invalid") from exc


__all__ = [
    "DAILY_ASSET_SYSTEM_PROMPT",
    "DAILY_TIMEFRAMES",
    "DAILY_TIMEFRAMES_BY_ASSET",
    "DailyAnalysisError",
    "DailyAnalysisStore",
    "DeepSeekDailyAssetProvider",
    "build_daily_analysis_bundle",
    "build_daily_asset_request",
    "compile_daily_asset_analysis",
    "validate_daily_asset_analysis",
]
