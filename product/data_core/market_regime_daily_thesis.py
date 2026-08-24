"""Daily cross-asset thesis compiler and Markdown/HTML delivery."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import html
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Callable, Mapping

from .market_regime_daily_analysis import (
    DAILY_TIMEFRAMES,
    SCHEMA_VERSION as ANALYSIS_SCHEMA,
)
from .market_regime_daily_source import WEEKLY_KEYS


SCHEMA_VERSION = "market-regime-daily-thesis-v1"
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


def _has_numeric_observation(text: str) -> bool:
    numeric_free = text.replace("4小时", "").replace("30分钟", "").replace("2s10s", "").replace("2Y", "").replace("10Y", "")
    return bool(re.search(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?\s*(?:%|％|bp|基点)?", numeric_free))


def _safe_receipt(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {"provider": "injected", "receipt_hash": _digest(str(value))}
    allowed = ("provider", "model", "request_hash", "prompt_hash", "prompt_version", "generation_status", "attempt_count", "output_hash")
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
                "generation_status": analysis.get("generation_status"),
                "failure_code": analysis.get("failure_code"),
                "position": (output.get("deterministic") or {}).get("position"),
                "structure": (output.get("deterministic") or {}).get("structure"),
                "timeframes": {
                    timeframe: output.get(timeframe)
                    for timeframe in DAILY_TIMEFRAMES
                    if output.get(timeframe) is not None
                },
                "synthesis": output.get("synthesis"),
                "market_meaning": output.get("market_meaning"),
                "opportunity_state": output.get("opportunity_state"),
                "coverage": {
                    timeframe: (request.get("timeframes") or {}).get(timeframe, {}).get("status")
                    for timeframe in DAILY_TIMEFRAMES
                },
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "analysis_bundle_id": bundle["bundle_id"],
        "cutoff_at": bundle.get("cutoff_at"),
        "assets": assets,
        "fact_evidence_ids": sorted(fact_evidence_ids),
        "unavailable_evidence_ids": sorted(unavailable_evidence_ids),
        "mechanism_ids": sorted(mechanism_ids),
        "truth_boundary": {
            "finance_newsletter_input": False,
            "observations_are_evidence_bound": True,
            "inferred_world_model_is_not_literal_flow_measurement": True,
            "automatic_execution_eligible": False,
            "broker_access": False,
        },
    }


def _statement(value: Any, *, known_ids: set[str], field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not isinstance(value.get("text"), str) or not value["text"].strip():
        raise DailyThesisError(f"thesis_statement_invalid:{field}")
    ids = value.get("evidence_ids")
    if not isinstance(ids, list) or not ids or any(str(item) not in known_ids for item in ids):
        raise DailyThesisError(f"thesis_evidence_invalid:{field}")
    text = value["text"].strip()
    if _has_forbidden_english(text) or _has_numeric_observation(text):
        raise DailyThesisError(f"thesis_language_or_numeric_invalid:{field}")
    if re.search(r"直接资金流|资金净流入|真实资金流|资金已流入|资金已流出|个人持仓|仓位比例|满仓|半仓|自动执行|经纪订单|下单", text):
        raise DailyThesisError(f"thesis_boundary_invalid:{field}")
    return {"text": text, "evidence_ids": [str(item) for item in ids]}


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
    result = {
        "generation_status": "model_generated_unreviewed",
        "posture": posture,
        "headline": _statement(output.get("headline"), known_ids=known_ids, field="headline"),
        "what_happened": _statement(output.get("what_happened"), known_ids=known_ids, field="what_happened"),
        "world_model": _statement(output.get("world_model"), known_ids=known_ids, field="world_model"),
        "leadership": _statement(output.get("leadership"), known_ids=known_ids, field="leadership"),
        "laggards": _statement(output.get("laggards"), known_ids=known_ids, field="laggards"),
        "capital_migration": _statement(output.get("capital_migration"), known_ids=known_ids, field="capital_migration"),
        "theoretical_mechanism": _mechanism_statement(output.get("theoretical_mechanism"), mechanism_ids=mechanism_ids, field="theoretical_mechanism"),
    }
    for field, minimum, maximum in (("watchpoints", 2, 8), ("actions", 1, 8), ("falsifiers", 1, 5)):
        rows = output.get(field)
        if not isinstance(rows, list) or not minimum <= len(rows) <= maximum:
            raise DailyThesisError(f"thesis_{field}_shape_invalid")
        result[field] = [_statement(row, known_ids=known_ids, field=f"{field}_{index}") for index, row in enumerate(rows)]
    return result


DAILY_THESIS_SYSTEM_PROMPT = """你是 Global Market K-line Daily 的跨资产主理人。只读取请求中的 19 个资产单资产分析和证据 ID，不读取 Finance Daily Newsletter，不调用新闻或外部知识，不补造数字。

请把各资产综合成一份当天的市场判断：headline、what_happened、world_model、leadership、laggards、capital_migration、theoretical_mechanism、watchpoints、actions、falsifiers。current observations 必须引用可用资产的 fact_evidence_ids；不可用周期不能支撑当前判断。theoretical_mechanism 只能引用 mechanism_ids。可以提出有条件的交易建议，但不得给个人仓位、订单或自动执行。资本迁移是对价格相对关系的推断，不是直接资金流测量。所有文字使用简体中文，除官方资产符号外不要写英文句子或数字。

只返回合法 JSON：{"generation_status":"model_generated_unreviewed","posture":"attack|wait|defense|no_view","headline":{"text":"...","evidence_ids":["..."]},"what_happened":{"text":"...","evidence_ids":["..."]},"world_model":{"text":"...","evidence_ids":["..."]},"leadership":{"text":"...","evidence_ids":["..."]},"laggards":{"text":"...","evidence_ids":["..."]},"capital_migration":{"text":"...","evidence_ids":["..."]},"theoretical_mechanism":{"text":"...","evidence_ids":["mechanism:..."],"claim_type":"theoretical_mechanism"},"watchpoints":[{"text":"...","evidence_ids":["..."]}],"actions":[{"text":"...","evidence_ids":["..."]}],"falsifiers":[{"text":"...","evidence_ids":["..."]}]}"""


class DeepSeekDailyThesisProvider:
    provider_name = "DeepSeek"

    def __init__(self, key_file: Path | str, *, model: str = "deepseek-v4-flash") -> None:
        self.key_file = Path(key_file).expanduser().resolve()
        self.model = model

    def __call__(self, request: Mapping[str, Any]) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
        from deepseek_writer import call_structured_deepseek

        output, receipt = call_structured_deepseek(
            system_prompt=DAILY_THESIS_SYSTEM_PROMPT,
            request_object=request,
            key_file=self.key_file,
            model=self.model,
            max_tokens=5000,
            reasoning_effort="low",
            temperature=0.1,
            thinking_type="disabled",
        )
        return output, receipt


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
    return " · ".join(f"{label}：{'可用' if statuses.get(tf) == 'ready' else '不可用'}" for tf, label in (("daily", "日线"), ("four_hour", "4小时"), ("thirty_minute", "30分钟")))


def render_daily_markdown(delivery: Mapping[str, Any], analysis_bundle: Mapping[str, Any]) -> str:
    thesis = delivery.get("output") or {}
    cutoff = str(delivery.get("cutoff_at") or analysis_bundle.get("cutoff_at") or "")
    lines = ["---", "title: 宏观 K 线日报", f"date: {cutoff[:10]}", "report_type: kline-daily-newsletter", f"generation_status: {delivery.get('generation_status')}", "---", "", f"# 宏观 K 线日报｜{cutoff[:10]}", "", "> 只基于跨资产 K 线：日线看方向，4 小时看上下文，30 分钟看短线节奏。", ""]
    lines.extend(["## 今日结论", ""])
    if thesis.get("generation_status") != "model_generated_unreviewed":
        lines.extend(["当前综合 thesis 不可用。", "", "本日报保留各资产数据状态，但没有把旧结论或模板判断当作今天的新结论。", ""])
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
        analysis = asset.get("analysis") or {}
        output = analysis.get("output") or {}
        lines.extend([f"### {asset.get('display_name', asset.get('asset_key'))}", ""])
        lines.append(f"数据覆盖：{_coverage(asset.get('request') or {})}")
        if analysis.get("generation_status") != "model_generated_unreviewed":
            lines.extend(["", "单资产分析不可用；保留 K 线数据状态，未使用旧分析。", ""])
            continue
        for timeframe, label in (("daily", "日线"), ("four_hour", "4小时"), ("thirty_minute", "30分钟")):
            statement = output.get(timeframe)
            if isinstance(statement, Mapping):
                lines.extend([f"- **{label}**：{statement['text']}"])
        if isinstance(output.get("synthesis"), Mapping):
            lines.extend([f"- **综合结论**：{output['synthesis']['text']}"])
        if isinstance(output.get("market_meaning"), Mapping):
            lines.extend([f"- **市场含义**：{output['market_meaning']['text']}"])
        lines.append("")
    lines.extend(["## 数据边界", "", f"- 数据截至：{cutoff}", "- 本日报不读取 Finance Daily Newsletter。", "- 不可用周期保留为不可用，不代表横盘或没有变化。", "- 内容仅供研究参考；不连接经纪账户，不自动执行交易。", ""])
    return "\n".join(lines)


def render_daily_html(markdown: str, *, title: str = "宏观 K 线日报") -> str:
    escaped = html.escape(markdown)
    body = "<br>".join(escaped.splitlines())
    return f"<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title><style>body{{margin:0;background:#f4f6f2;color:#17201b;font-family:-apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei',sans-serif}}main{{max-width:900px;margin:0 auto;background:#fffefa;min-height:100vh;padding:36px 28px;box-sizing:border-box}}.content{{font-size:16px;line-height:1.8;white-space:normal}}@media(max-width:600px){{main{{padding:22px 16px}}.content{{font-size:15px}}}}</style></head><body><main><div class='content'>{body}</div></main></body></html>"


class DailyThesisDeliveryStore:
    """Publish an immutable Daily thesis and copy Markdown to Obsidian."""

    def __init__(self, *, runtime_root: Path | str, output_root: Path | str, archive_root: Path | str) -> None:
        self.runtime_root = Path(runtime_root).expanduser().resolve()
        self.output_root = Path(output_root).expanduser().resolve()
        self.archive_root = Path(archive_root).expanduser().resolve()

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
        markdown = render_daily_markdown({**thesis, "cutoff_at": analysis_bundle.get("cutoff_at")}, analysis_bundle)
        html_text = render_daily_html(markdown)
        core = {"schema_version": SCHEMA_VERSION, "thesis_id": thesis_id, "analysis_bundle_id": analysis_bundle.get("bundle_id"), "markdown_sha256": hashlib.sha256(markdown.encode()).hexdigest(), "html_sha256": hashlib.sha256(html_text.encode()).hexdigest(), "cutoff_at": analysis_bundle.get("cutoff_at")}
        delivery_id = f"{DELIVERY_ID_PREFIX}{_digest(core)}"
        artifact_dir = self.runtime_root / "delivery" / "artifacts"
        md_ref = {"path": f"artifacts/{digest}.md", "sha256": _immutable_bytes(artifact_dir / f"{digest}.md", markdown.encode("utf-8"))}
        html_ref = {"path": f"artifacts/{digest}.html", "sha256": _immutable_bytes(artifact_dir / f"{digest}.html", html_text.encode("utf-8"))}
        archive_date = str(analysis_bundle.get("cutoff_at") or "")[:10]
        archive_path = self.archive_root / f"{archive_date}-kline-daily-newsletter.md"
        if archive_path.exists() and archive_path.read_bytes() != markdown.encode("utf-8"):
            archive_path = self.archive_root / f"{archive_date}-kline-daily-newsletter-{digest[:12]}.md"
        _atomic_bytes(archive_path, markdown.encode("utf-8"))
        _atomic_bytes(self.output_root / "latest.md", markdown.encode("utf-8"))
        _atomic_bytes(self.output_root / "latest.html", html_text.encode("utf-8"))
        receipt = {"schema_version": SCHEMA_VERSION, "delivery_id": delivery_id, "thesis_id": thesis_id, "analysis_bundle_id": analysis_bundle.get("bundle_id"), "cutoff_at": archive_date, "markdown": md_ref, "html": html_ref, "archive_path": str(archive_path), "generation_status": thesis.get("generation_status")}
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
            for field in ("markdown", "html"):
                reference = receipt.get(field) or {}
                artifact_path = (self.runtime_root / "delivery" / str(reference.get("path") or "")).resolve()
                if self.runtime_root.resolve() not in artifact_path.parents:
                    raise DailyThesisError("delivery_artifact_path_escape")
                artifact_bytes = artifact_path.read_bytes()
                if reference.get("sha256") != hashlib.sha256(artifact_bytes).hexdigest():
                    raise DailyThesisError(f"delivery_{field}_hash_invalid")
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
]
