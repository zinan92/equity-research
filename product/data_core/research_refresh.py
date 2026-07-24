from __future__ import annotations

import base64
import fcntl
import hashlib
import json
import math
import multiprocessing
import os
import socket
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import uuid
from copy import deepcopy
from contextlib import closing, contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, time, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Protocol
from zoneinfo import ZoneInfo

from .contracts import SourceManifest, digest
from .store import (
    DataFoundation, SnapshotReader, build_normalization_receipt, validate_provider_raw_objects,
)


REFRESH_SCHEMA_VERSION = "canonical-research-refresh-v1"
SHANGHAI = ZoneInfo("Asia/Shanghai")


class RefreshInProgressError(RuntimeError):
    pass


class InjectedInterruption(RuntimeError):
    """Test-only process interruption after a durable checkpoint."""


class CanonicalPublicationError(RuntimeError):
    """An active canonical pointer exists but fails integrity validation."""


@dataclass(frozen=True)
class CanonicalComponent:
    manifest: SourceManifest
    payload: dict[str, Any]

    def as_json(self) -> dict[str, Any]:
        return {"manifest": asdict(self.manifest), "payload": self.payload}

    @classmethod
    def from_json(cls, value: dict[str, Any]) -> "CanonicalComponent":
        manifest = dict(value["manifest"])
        manifest["quality_flags"] = tuple(manifest.get("quality_flags") or ())
        return cls(manifest=SourceManifest(**manifest), payload=value["payload"])


@dataclass(frozen=True)
class CollectedBundle:
    adapter: str
    role: str
    payload: dict[str, Any]
    manifest: SourceManifest
    data_kind: str
    components: tuple[CanonicalComponent, ...] = ()

    def as_json(self) -> dict[str, Any]:
        return {
            "adapter": self.adapter,
            "role": self.role,
            "payload": self.payload,
            "manifest": asdict(self.manifest),
            "data_kind": self.data_kind,
            "components": [component.as_json() for component in self.components],
        }

    @classmethod
    def from_json(cls, value: dict[str, Any]) -> "CollectedBundle":
        manifest = dict(value["manifest"])
        manifest["quality_flags"] = tuple(manifest.get("quality_flags") or ())
        return cls(
            adapter=value["adapter"], role=value["role"], payload=value["payload"],
            manifest=SourceManifest(**manifest), data_kind=value["data_kind"],
            components=tuple(
                CanonicalComponent.from_json(component) for component in value.get("components") or ()
            ),
        )


class SourceAdapter(Protocol):
    name: str
    role: str

    def collect(self, now: datetime) -> CollectedBundle: ...


ResearchBuilder = Callable[[SnapshotReader, str], dict[str, Any]]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("refresh clock must be timezone-aware")
    return moment.astimezone(timezone.utc).isoformat()


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True, default=str)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def latest_completed_trade_date(payload: dict[str, Any], now: datetime) -> str:
    """Select the latest open date completed for every represented exchange."""
    local = now.astimezone(SHANGHAI)
    exchanges = {row["exchange"] for row in payload.get("instruments") or []}
    open_by_date: dict[str, set[str]] = {}
    for row in payload.get("calendar") or []:
        if int(row.get("is_open", 0)) == 1:
            open_by_date.setdefault(str(row["trade_date"]), set()).add(str(row["exchange"]))
    completed = []
    for trade_date, open_exchanges in open_by_date.items():
        if open_exchanges != exchanges:
            continue
        date_value = datetime.fromisoformat(trade_date).date()
        if date_value < local.date() or (date_value == local.date() and local.time() >= time(15, 30)):
            completed.append(trade_date)
    if not completed:
        raise ValueError("collector bundle has no completed trading date with full exchange coverage")
    target = max(completed)
    target_rows = [row for row in payload.get("calendar") or [] if row["trade_date"] == target]
    invalid_previous = [
        row for row in target_rows
        if row.get("previous_open_date") and str(row["previous_open_date"]) >= target
    ]
    if invalid_previous:
        raise ValueError("trading calendar previous_open_date must be earlier than target")
    if payload.get("as_of") != target:
        raise ValueError(f"collector as_of={payload.get('as_of')} does not match completed trade date {target}")
    return target


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _pct(values: list[float], periods: int) -> float | None:
    if len(values) <= periods or values[-periods - 1] == 0:
        return None
    return (values[-1] / values[-periods - 1] - 1) * 100


@contextmanager
def _python_network_blocked():
    """Block common network and shell escape surfaces inside an isolated child."""
    originals = {
        "create_connection": socket.create_connection,
        "connect": socket.socket.connect,
        "connect_ex": socket.socket.connect_ex,
        "send": socket.socket.send,
        "sendall": socket.socket.sendall,
        "sendto": socket.socket.sendto,
        "popen": subprocess.Popen,
        "run": subprocess.run,
        "call": subprocess.call,
        "check_call": subprocess.check_call,
        "check_output": subprocess.check_output,
        "os_system": os.system,
        "os_popen": os.popen,
    }
    blocked_os_calls = tuple(
        name for name in (
            "execl", "execle", "execlp", "execlpe", "execv", "execve", "execvp", "execvpe",
            "spawnl", "spawnle", "spawnlp", "spawnlpe", "spawnv", "spawnve", "spawnvp", "spawnvpe",
            "posix_spawn", "posix_spawnp",
        )
        if hasattr(os, name)
    )
    for name in blocked_os_calls:
        originals[f"os_{name}"] = getattr(os, name)

    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("network access is forbidden during snapshot-bound research")

    socket.create_connection = forbidden
    socket.socket.connect = forbidden
    socket.socket.connect_ex = forbidden
    socket.socket.send = forbidden
    socket.socket.sendall = forbidden
    socket.socket.sendto = forbidden
    subprocess.Popen = forbidden
    subprocess.run = forbidden
    subprocess.call = forbidden
    subprocess.check_call = forbidden
    subprocess.check_output = forbidden
    os.system = forbidden
    os.popen = forbidden
    for name in blocked_os_calls:
        setattr(os, name, forbidden)
    try:
        yield
    finally:
        socket.create_connection = originals["create_connection"]
        socket.socket.connect = originals["connect"]
        socket.socket.connect_ex = originals["connect_ex"]
        socket.socket.send = originals["send"]
        socket.socket.sendall = originals["sendall"]
        socket.socket.sendto = originals["sendto"]
        subprocess.Popen = originals["popen"]
        subprocess.run = originals["run"]
        subprocess.call = originals["call"]
        subprocess.check_call = originals["check_call"]
        subprocess.check_output = originals["check_output"]
        os.system = originals["os_system"]
        os.popen = originals["os_popen"]
        for name in blocked_os_calls:
            setattr(os, name, originals[f"os_{name}"])


def _research_child(
    connection: Any,
    builder: ResearchBuilder,
    db_path: str,
    snapshot_id: str,
    ticker: str,
) -> None:
    try:
        blocked_events = {
            "socket.__new__", "socket.connect", "socket.getaddrinfo", "socket.gethostbyname",
            "subprocess.Popen", "os.system", "os.posix_spawn", "os.posix_spawnp",
        }

        def audit(event: str, _args: tuple[Any, ...]) -> None:
            if event in blocked_events:
                raise RuntimeError("network or external command access is forbidden during snapshot-bound research")

        sys.addaudithook(audit)
        with _python_network_blocked():
            artifact = builder(SnapshotReader(DataFoundation(db_path), snapshot_id), ticker)
        connection.send(("success", artifact))
    except BaseException as exc:
        connection.send(("failed", f"{type(exc).__name__}: {exc}"[:2000]))
    finally:
        connection.close()


def _run_research_builder_isolated(
    builder: ResearchBuilder,
    reader: SnapshotReader,
    ticker: str,
    *,
    timeout: float = 120.0,
) -> dict[str, Any]:
    """Run snapshot-only research in a separate fail-closed process."""
    context = multiprocessing.get_context("fork")
    parent, child = context.Pipe(duplex=False)
    process = context.Process(
        target=_research_child,
        args=(child, builder, str(reader.foundation.db_path), reader.snapshot_id, ticker),
        daemon=True,
    )
    process.start()
    child.close()
    try:
        if not parent.poll(timeout):
            process.terminate()
            process.join(5)
            raise RuntimeError("research builder timed out in network-isolated process")
        status, value = parent.recv()
        process.join(5)
        if status != "success":
            raise RuntimeError(value)
        if process.exitcode not in {0, None}:
            raise RuntimeError(f"research builder child exited {process.exitcode}")
        return value
    finally:
        parent.close()
        if process.is_alive():
            process.terminate()
            process.join(5)


def _default_research_builder(
    reader: SnapshotReader, ticker: str, *, minimum_bars: int = 250
) -> dict[str, Any]:
    """Build one complete M1 baseline report from only a frozen snapshot."""
    from report_contract import attach_report_contract, validate_report_contract

    context = reader.research_context(ticker)
    instrument = context["instrument"]
    bars = sorted(
        context["daily_bars"],
        key=lambda row: (row["trade_date"], row["known_at"], row["adjustment_version"]),
    )
    latest_by_date = {row["trade_date"]: row for row in bars}
    bars = [latest_by_date[key] for key in sorted(latest_by_date)]
    facts = context["financial_facts"]
    observations = sorted(context["intelligence_items"], key=lambda row: row["known_at"])
    if len(bars) < minimum_bars or not facts or not observations:
        raise RuntimeError(
            f"standard report coverage failed bars={len(bars)}/{minimum_bars} financial_facts={len(facts)} "
            f"market_observations={len(observations)}"
        )
    latest = bars[-1]
    closes = [float(row["close"]) for row in bars]
    returns = [closes[index] / closes[index - 1] - 1 for index in range(1, len(closes)) if closes[index - 1]]
    peak = closes[-min(250, len(closes))]
    drawdown = 0.0
    for close in closes[-250:]:
        peak = max(peak, close)
        drawdown = min(drawdown, close / peak - 1)
    quote_evidence = json.loads(observations[-1]["evidence_json"])
    known_at = latest["known_at"]
    metrics_by_period: dict[str, dict[str, Any]] = {}
    for fact in facts:
        period = metrics_by_period.setdefault(fact["report_date"], {})
        period[fact["metric_key"]] = fact["metric_value"]
    series = []
    for report_date in sorted(metrics_by_period, reverse=True)[:4]:
        values = metrics_by_period[report_date]
        series.append({
            "report_date": report_date, "report_type": "canonical_snapshot",
            "revenue_yi": (_number(values.get("revenue")) or 0) / 100_000_000 if values.get("revenue") is not None else None,
            "net_profit_yi": (_number(values.get("net_profit")) or 0) / 100_000_000 if values.get("net_profit") is not None else None,
            "revenue_yoy": _number(values.get("revenue_yoy")),
            "net_profit_yoy": _number(values.get("net_profit_yoy")),
            "gross_margin": _number(values.get("gross_margin")),
            "net_margin": _number(values.get("net_margin")), "roe": _number(values.get("roe")),
        })
    latest_financial = metrics_by_period[series[0]["report_date"]]
    score = 50.0
    source_id = "market_snapshot"
    market = {
        "price": closes[-1], "change_pct": _number(quote_evidence.get("change_pct")),
        "pe_ttm": _number(quote_evidence.get("pe_ttm")), "pb": _number(quote_evidence.get("pb")),
        "market_cap_yi": _number(quote_evidence.get("market_cap_yi")),
        "return_20d": _pct(closes, 20), "return_60d": _pct(closes, 60),
        "return_250d": _pct(closes, 250),
        "volatility_60d": statistics.pstdev(returns[-60:]) * math.sqrt(252) * 100 if returns else None,
        "max_drawdown_250d": drawdown * 100,
        "ma20": statistics.mean(closes[-20:]) if len(closes) >= 20 else None,
        "ma60": statistics.mean(closes[-60:]) if len(closes) >= 60 else None,
        "ma200": statistics.mean(closes[-200:]) if len(closes) >= 200 else None,
        "composite_score": score,
    }
    payload = {
        "ticker": ticker, "name": instrument["name"], "exchange": instrument["exchange"],
        "title": f"{instrument['name']}标准研究基线", "industry": instrument["industry"],
        "as_of": latest["trade_date"], "known_at": known_at,
        "market_known_at": known_at, "research_known_at": known_at,
        "data_mode": (
            "REAL" if reader.snapshot_id.startswith("core_real_")
            else "CACHED" if reader.snapshot_id.startswith("core_cached_") else "FIXTURE"
        ),
        "data_status": "verified",
        "research_status": "baseline", "research_depth": "quantitative_baseline",
        "report_version": "canonical-baseline-v1",
        "generated_from": {
            "snapshot_id": reader.snapshot_id, "publication_id": None,
            "model_version": REFRESH_SCHEMA_VERSION,
        },
        "market": market,
        "executive": {
            "stance": "观察", "summary": "市场与财务基线已更新，公司级证据尚未完成。",
            "action": "等待公司证据门，不形成执行建议", "score": score,
            "current_price": closes[-1], "key_contradiction": "量化输入完整不等于公司研究完成",
            "execution_range": "不可执行", "position_plan": [
                {"stage": "研究升级", "weight": 0, "condition": "完成公司原始资料与独立来源交叉验证"}
            ],
            "model_observation_weight": None, "current_executable_weight": None,
            "weight_semantics": "research_baseline_only", "publication_approval_current": False,
        },
        "thesis": [{
            "title": "量化基线已冻结", "body": f"已冻结 {len(bars)} 个交易日与最新财务事实，供后续公司研究使用。",
            "claim_type": "fact", "source_ids": [source_id],
        }],
        "business_model": {
            "description": "Missing evidence：当前 canonical market snapshot 不包含公司经营分部原始资料。",
            "source_ids": [source_id], "segments": [], "value_chain": [
                {"layer": "待研究", "items": "公司原始披露", "question": "收入、利润与现金流由哪些业务驱动？"}
            ],
        },
        "industry_position": {
            "headline": "Missing evidence：行业地位需公司与独立行业资料交叉验证。",
            "source_ids": [source_id], "metrics": [],
        },
        "management": {
            "score": None, "strengths": [], "watchouts": ["治理与资本配置证据尚未冻结"],
            "source_ids": [source_id],
        },
        "financials": {
            "headline": "当前仅展示 canonical 财务事实，不推断长期质量。",
            "latest_period": series[0]["report_date"], "latest_type": "canonical_snapshot",
            "annual_quality": {
                "roe": _number(latest_financial.get("roe")),
                "gross_margin": _number(latest_financial.get("gross_margin")),
                "net_margin": _number(latest_financial.get("net_margin")),
                "debt_ratio": _number(latest_financial.get("debt_ratio")),
                "operating_cash_per_share": _number(latest_financial.get("operating_cash_per_share")),
            },
            "series": series, "quality_notes": ["财务更正必须以显式 revision 进入新版本。"],
        },
        "serenity": {
            "raw_score": score, "penalty": 0, "final_score": score, "label": "待公司研究",
            "meaning": "只表示量化输入可用，不代表护城河或买入信号。",
            "method": "canonical market baseline v1", "factors": [
                {"key": "market_data", "label": "市场数据完整性", "score": score,
                 "weight": 1, "contribution": score, "reason": "通过 snapshot quality gate", "source_ids": [source_id]}
            ], "penalties": [],
        },
        "valuation": {
            "currency": "CNY", "current_price": closes[-1], "method": "not_performed",
            "pe_ttm": market["pe_ttm"], "pb": market["pb"],
            "status": "missing_evidence", "reason": "公司盈利桥与可比估值证据尚未完成。",
        },
        "quant_signals": [
            {"name": "二百日趋势", "score": score, "proof": "只用于后续排序，不替代公司研究。", "source_ids": [source_id]}
        ],
        "stress_test": {
            "method": "price sensitivity only", "price_basis": closes[-1], "formula": "price_basis × stress_multiple",
            "scenarios": [
                {"case": case, "label": label, "price_basis": closes[-1], "stress_multiple": multiple,
                 "stress_price": closes[-1] * multiple, "change_pct": (multiple - 1) * 100,
                 "assumption": "价格敏感度占位，不是目标价"}
                for case, label, multiple in (("bear", "压力", 0.8), ("base", "基准", 1.0), ("bull", "上行", 1.2))
            ], "warning": "本压力测试不构成估值结论或交易区间。",
        },
        "catalysts": [{
            "date": "待更新", "title": "下一次定期报告", "body": "用于升级财务与公司证据。",
            "source_ids": [source_id],
        }],
        "risks": [{
            "rank": 1, "title": "公司证据不足", "impact": "高", "probability": "当前存在",
            "trigger": "在完成公司级证据前尝试输出目标价或执行仓位", "evidence": "当前仅有市场快照",
            "source_ids": [source_id],
        }],
        "falsification": ["若 snapshot identity、时点或来源校验失败，本报告立即失效。"],
        "watchlist": [{
            "metric": "公司证据门", "current": "未完成", "threshold": "两份公司原始资料与一份独立来源",
            "frequency": "每次研究升级",
        }],
        "sources": [{
            "id": source_id, "document_id": f"snapshot_{reader.snapshot_id}",
            "title": "canonical 市场与财务快照", "kind": "market_snapshot", "strength": "strong",
            "known_at": known_at, "url": None, "note": "通过 data-foundation-v1 质量门",
            "snapshot_id": reader.snapshot_id, "provider": latest["source_key"], "quote_time": known_at,
        }],
        "evidence_summary": {
            "boundary": "只有市场与财务基线；公司经营、行业与治理结论仍为 Missing evidence。",
            "document_count": 1, "independent_document_count": 0, "claim_locator_count": 1,
        },
        "source_contract": {spec: [source_id] for spec in (
            "executive", "thesis", "business_model", "industry_position", "management",
            "financials", "serenity", "valuation", "catalysts", "risks", "falsification", "watchlist",
        )},
        "disclaimer": "本报告仅为 snapshot-bound 研究基线，不构成投资建议、目标价或执行仓位。",
        "depth_disclosure": "量化基线已完成；公司级深度研究和独立证据尚未完成。",
    }
    report = attach_report_contract(payload)
    report["report_hash"] = digest(report)
    errors = validate_report_contract(report["report_contract"], report)
    if errors:
        raise RuntimeError("standard report contract failed: " + "; ".join(errors))
    return {
        "schema_version": "canonical-standard-report-artifact-v1", "status": "success",
        "ticker": ticker, "name": instrument["name"], "snapshot_id": reader.snapshot_id,
        "report_hash": report["report_hash"], "report": report,
    }


def _report_artifact_errors(
    artifact: dict[str, Any], *, ticker: str, snapshot_id: str, require_artifact_hash: bool
) -> list[str]:
    from report_contract import validate_report_contract

    errors: list[str] = []
    payload = deepcopy(artifact)
    stored_artifact_hash = payload.pop("artifact_hash", None)
    report = payload.get("report") or {}
    report_without_hash = deepcopy(report)
    declared_report_hash = report_without_hash.pop("report_hash", None)
    calculated_report_hash = digest(report_without_hash)
    if require_artifact_hash and stored_artifact_hash != digest(payload):
        errors.append("artifact hash mismatch")
    if payload.get("ticker") != ticker or payload.get("snapshot_id") != snapshot_id:
        errors.append("artifact identity mismatch")
    if payload.get("status") not in {"success", "reused"}:
        errors.append("artifact status is not passed")
    if declared_report_hash != calculated_report_hash:
        errors.append("report content hash mismatch")
    if payload.get("report_hash") != declared_report_hash:
        errors.append("artifact/report hash mismatch")
    if report.get("generated_from", {}).get("snapshot_id") != snapshot_id:
        errors.append("report snapshot identity mismatch")
    errors.extend(validate_report_contract(report.get("report_contract") or {}, report))
    return errors


def _publication_base(manifest: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "schema_version", "snapshot_id", "snapshot_kind", "target_trade_date",
        "payload_hash", "report_schema_version", "report_contract_version", "report_hashes",
    )
    return {key: manifest.get(key) for key in keys}


def canonical_runtime_state_root() -> Path:
    return Path(
        os.environ.get(
            "PARK_CANONICAL_STATE_ROOT",
            Path(__file__).resolve().parents[1] / "runtime" / "canonical_refresh",
        )
    )


def canonical_active_report(
    ticker: str, state_root: Path | str | None = None
) -> dict[str, Any] | None:
    """Load one integrity-checked report from the product's canonical active pointer."""
    root = Path(state_root) if state_root is not None else canonical_runtime_state_root()
    active = _read_json(root / "active.json")
    if not active:
        return None
    if not active.get("publication_id") or not active.get("snapshot_id"):
        raise CanonicalPublicationError("canonical active pointer is incomplete")
    publication = _read_json(root / "publications" / f"{active['publication_id']}.json")
    if not publication:
        raise CanonicalPublicationError("canonical publication manifest is missing")
    expected_publication_id = f"canonical_pub_{digest(_publication_base(publication))[:16]}"
    symbol = ticker.upper()
    if (
        publication.get("publication_id") != expected_publication_id
        or active.get("publication_id") != expected_publication_id
        or active.get("snapshot_id") != publication.get("snapshot_id")
        or active.get("payload_hash") != publication.get("payload_hash")
        or active.get("report_hashes") != publication.get("report_hashes")
        or active.get("target_trade_date") != publication.get("target_trade_date")
        or active.get("snapshot_kind") != publication.get("snapshot_kind")
    ):
        raise CanonicalPublicationError("canonical active/publication identity mismatch")
    relative = (publication.get("report_artifacts") or {}).get(symbol)
    if not relative:
        raise CanonicalPublicationError(f"canonical report path is missing: {symbol}")
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError:
        raise CanonicalPublicationError(f"canonical report path escapes state root: {symbol}")
    artifact = _read_json(path)
    if not artifact or _report_artifact_errors(
        artifact, ticker=symbol, snapshot_id=active["snapshot_id"], require_artifact_hash=True
    ):
        raise CanonicalPublicationError(f"canonical report artifact is invalid: {symbol}")
    if artifact.get("report_hash") != (publication.get("report_hashes") or {}).get(symbol):
        raise CanonicalPublicationError(f"canonical report hash is invalid: {symbol}")
    return deepcopy(artifact["report"])


def canonical_active_summary(state_root: Path | str | None = None) -> dict[str, Any]:
    root = Path(state_root) if state_root is not None else canonical_runtime_state_root()
    active = _read_json(root / "active.json")
    if not active:
        return {"status": "unavailable", "active": None, "report_count": 0}
    report_count = 0
    for ticker in (active.get("report_hashes") or {}):
        try:
            report_count += canonical_active_report(ticker, root) is not None
        except CanonicalPublicationError:
            pass
    expected = len(active.get("report_hashes") or {})
    return {
        "status": "healthy" if expected == 8 and report_count == expected else "attention",
        "active": active,
        "report_count": report_count,
    }


class CanonicalResearchRefresh:
    """Serialized collect -> canonical snapshot -> eight-artifact activation state machine."""

    def __init__(
        self,
        foundation: DataFoundation,
        state_root: Path | str,
        adapters: Iterable[SourceAdapter],
        *,
        universe: Iterable[str],
        research_builder: ResearchBuilder = _default_research_builder,
    ) -> None:
        self.foundation = foundation
        self.state_root = Path(state_root)
        self.adapters = tuple(adapters)
        self.universe = tuple(str(ticker).upper() for ticker in universe)
        self.research_builder = research_builder
        if not self.adapters:
            raise ValueError("at least one source adapter is required")
        if (
            self.adapters[0].role != "primary"
            or any(adapter.role != "fallback" for adapter in self.adapters[1:])
        ):
            raise ValueError("adapters must start with one primary and use explicit fallback roles")
        if len(self.universe) != 8 or len(set(self.universe)) != 8:
            raise ValueError("research refresh requires the exact configured eight-stock universe")

    @property
    def _lock_path(self) -> Path:
        return self.state_root / "refresh.lock"

    def _receipt_path(self, run_id: str) -> Path:
        return self.state_root / "runs" / run_id / "receipt.json"

    def _bundle_path(self, run_id: str) -> Path:
        return self.state_root / "runs" / run_id / "bundle.json"

    def _publication_integrity(self, active: dict[str, Any] | None) -> list[str]:
        if not active or not active.get("publication_id"):
            return ["active publication is missing"]
        publication = _read_json(
            self.state_root / "publications" / f"{active['publication_id']}.json"
        )
        if not publication or publication.get("snapshot_id") != active.get("snapshot_id"):
            return ["active publication manifest is missing or mismatched"]
        errors = []
        expected_publication_id = f"canonical_pub_{digest(_publication_base(publication))[:16]}"
        if publication.get("publication_id") != expected_publication_id:
            errors.append("publication identity hash mismatch")
        if active.get("publication_id") != publication.get("publication_id"):
            errors.append("active/publication identity mismatch")
        if active.get("report_hashes") != publication.get("report_hashes"):
            errors.append("active/publication report hash map mismatch")
        if active.get("payload_hash") != publication.get("payload_hash"):
            errors.append("active/publication payload hash mismatch")
        if active.get("target_trade_date") != publication.get("target_trade_date"):
            errors.append("active/publication target date mismatch")
        if active.get("snapshot_kind") != publication.get("snapshot_kind"):
            errors.append("active/publication snapshot kind mismatch")
        for ticker in self.universe:
            relative = (publication.get("report_artifacts") or {}).get(ticker)
            expected_hash = (publication.get("report_hashes") or {}).get(ticker)
            if not relative:
                errors.append(f"{ticker}: report artifact path missing")
                continue
            path = (self.state_root / relative).resolve()
            try:
                path.relative_to(self.state_root.resolve())
            except ValueError:
                errors.append(f"{ticker}: report artifact escapes state root")
                continue
            artifact = _read_json(path)
            if not artifact:
                errors.append(f"{ticker}: report artifact missing")
                continue
            artifact_errors = _report_artifact_errors(
                artifact, ticker=ticker, snapshot_id=active["snapshot_id"], require_artifact_hash=True
            )
            errors.extend(f"{ticker}: {error}" for error in artifact_errors)
            if artifact.get("report_hash") != expected_hash:
                errors.append(f"{ticker}: publication report hash mismatch")
        return errors

    def _save_receipt(self, receipt: dict[str, Any]) -> None:
        _atomic_json(self._receipt_path(receipt["run_id"]), receipt)
        _atomic_json(self.state_root / "latest.json", receipt)

    def _snapshot_has_explicit_raw_lineage(self, snapshot_id: str | None) -> bool:
        """A5 must not reuse a pre-A5 snapshot with only implicit raw lineage."""
        if not snapshot_id:
            return False
        with self.foundation.connect() as connection:
            row = connection.execute(
                "SELECT manifest_json FROM core_snapshot_manifests "
                "WHERE snapshot_id=? AND quality_status='passed'",
                (snapshot_id,),
            ).fetchone()
        if not row:
            return False
        try:
            manifest = json.loads(row["manifest_json"])
        except (TypeError, json.JSONDecodeError):
            return False
        raw_hashes = manifest.get("raw_hashes")
        return bool(
            isinstance(raw_hashes, list)
            and raw_hashes
            and manifest.get("raw_hash_digest") == digest(raw_hashes)
        )

    def _checkpoint(self, receipt: dict[str, Any], stage: str, *, interrupt_after: str | None) -> None:
        receipt["stage"] = stage
        receipt["updated_at"] = _iso(_now())
        self._save_receipt(receipt)
        if interrupt_after == stage:
            raise InjectedInterruption(f"injected interruption after {stage}")

    def _load_resumable(self) -> tuple[dict[str, Any], CollectedBundle | None] | None:
        pointer = _read_json(self.state_root / "in_progress.json")
        if not pointer or not pointer.get("run_id"):
            return None
        receipt = _read_json(self._receipt_path(pointer["run_id"]))
        if not receipt or receipt.get("status") != "running":
            return None
        bundle_json = _read_json(self._bundle_path(pointer["run_id"]))
        return receipt, CollectedBundle.from_json(bundle_json) if bundle_json else None

    def _new_receipt(self, now: datetime) -> dict[str, Any]:
        run_id = f"refresh_{now.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
        receipt = {
            "schema_version": REFRESH_SCHEMA_VERSION,
            "run_id": run_id,
            "status": "running",
            "stage": "planned",
            "started_at": _iso(now),
            "updated_at": _iso(now),
            "attempts": [],
            "universe": list(self.universe),
            "previous_active": _read_json(self.state_root / "active.json"),
        }
        _atomic_json(self.state_root / "in_progress.json", {"run_id": run_id})
        self._save_receipt(receipt)
        return receipt

    @staticmethod
    def _components(bundle: CollectedBundle) -> tuple[CanonicalComponent, ...]:
        return bundle.components or (
            CanonicalComponent(manifest=bundle.manifest, payload=bundle.payload),
        )

    @classmethod
    def _ingest_bundle(cls, foundation: DataFoundation, bundle: CollectedBundle) -> list[dict[str, Any]]:
        return [
            {
                **foundation.ingest_payload(
                    component.payload, component.manifest, data_kind=bundle.data_kind
                ),
                "source_key": component.manifest.source_key,
                "manifest_hash": component.manifest.manifest_hash,
            }
            for component in cls._components(bundle)
        ]

    def _gap_bundle(self, bundle: CollectedBundle, *, target: str) -> CollectedBundle:
        """Keep raw evidence while submitting only absent canonical identities.

        Adjustment versions are part of the identity, so a vendor qfq revision
        appends the complete revised series instead of silently mixing versions.
        """
        self.foundation.initialize()
        with self.foundation.connect() as connection:
            existing = {
                "instruments": {row[0] for row in connection.execute("SELECT instrument_id FROM core_instruments")},
                "calendar": {tuple(row) for row in connection.execute("SELECT exchange, trade_date FROM core_trading_calendar")},
                "statuses": {tuple(row) for row in connection.execute("SELECT instrument_id, trade_date FROM core_instrument_status")},
                "actions": {row[0] for row in connection.execute("SELECT action_id FROM core_corporate_actions")},
                "factors": {tuple(row) for row in connection.execute("SELECT instrument_id, trade_date, version FROM core_adjustment_factors")},
                "bars": {tuple(row) for row in connection.execute("SELECT instrument_id, trade_date, adjustment_version FROM core_daily_bars")},
                "financials": {row[0] for row in connection.execute("SELECT fact_id FROM core_financial_facts")},
                "intelligence": {row[0] for row in connection.execute("SELECT item_id FROM core_intelligence_items")},
            }
        if not bundle.components:
            return bundle

        def absent(key: str, row: dict[str, Any]) -> bool:
            identity: Any
            if key == "instruments":
                identity = row["instrument_id"]
            elif key == "calendar":
                identity = (row["exchange"], row["trade_date"])
            elif key == "statuses":
                identity = (row["instrument_id"], row["trade_date"])
            elif key == "actions":
                identity = row["action_id"]
            elif key == "factors":
                identity = (row["instrument_id"], row["trade_date"], row["version"])
            elif key == "bars":
                identity = (row["instrument_id"], row["trade_date"], row["adjustment_version"])
            elif key == "financials":
                identity = row["fact_id"]
            else:
                identity = row["item_id"]
            return identity not in existing[key]

        components = []
        for component in bundle.components:
            payload = deepcopy(component.payload)
            for key in (
                "instruments", "calendar", "statuses", "actions", "factors",
                "bars", "financials", "intelligence",
            ):
                payload[key] = [row for row in payload.get(key) or [] if absent(key, row)]
            components.append(CanonicalComponent(component.manifest, payload))
        return CollectedBundle(
            adapter=bundle.adapter, role=bundle.role, payload=bundle.payload,
            manifest=bundle.manifest, data_kind=bundle.data_kind, components=tuple(components),
        )

    def _stage_quality(self, bundle: CollectedBundle, *, target: str, run_id: str) -> dict[str, Any]:
        """Prove a candidate source can pass canonical quality before selection."""
        stage_path = self.state_root / "runs" / run_id / f"stage-{digest(bundle.adapter)[:12]}.db"
        stage_path.parent.mkdir(parents=True, exist_ok=True)
        stage_path.unlink(missing_ok=True)
        self.foundation.initialize()
        with self.foundation.connect() as source, closing(sqlite3.connect(stage_path)) as destination:
            source.backup(destination)
        staged = DataFoundation(stage_path)
        try:
            try:
                ingestions = self._ingest_bundle(staged, bundle)
                evaluation = staged.quality_evaluation(
                    ingestions[-1]["run_id"], as_of=target, known_at=bundle.payload["known_at"]
                )
                audit = {
                    "status": "passed" if not evaluation["blockers"] else "failed",
                    "evaluation_id": evaluation["evaluation_id"],
                    "gate_hash": evaluation["quality_digest"],
                    "checks": evaluation["results"],
                    "blockers": evaluation["blockers"],
                    "source_run_count": len(ingestions),
                }
                if evaluation["blockers"]:
                    return audit
                snapshot = staged.create_snapshot(
                    ingestions[-1]["run_id"], as_of=target, known_at=bundle.payload["known_at"],
                    model_version=REFRESH_SCHEMA_VERSION,
                )
                return {
                    **audit, "snapshot_kind": snapshot["snapshot_kind"],
                    "staged_manifest_hash": snapshot["manifest_hash"],
                }
            except Exception as exc:
                return {
                    "status": "failed", "evaluation_id": None, "gate_hash": None,
                    "checks": {},
                    "blockers": [f"{type(exc).__name__}: {exc}"[:1000]],
                    "source_run_count": 0,
                }
        finally:
            stage_path.unlink(missing_ok=True)

    def _collect(self, receipt: dict[str, Any], now: datetime) -> CollectedBundle:
        errors = []
        for adapter in self.adapters:
            started_at = _iso(_now())
            attempt_bundle_path: str | None = None
            attempt_bundle_hash: str | None = None
            try:
                bundle = adapter.collect(now)
                if bundle.adapter != adapter.name or bundle.role != adapter.role:
                    raise ValueError("adapter identity differs from returned bundle")
                if bundle.data_kind not in {"fixture", "cached", "real"}:
                    raise ValueError(f"unsupported adapter data_kind: {bundle.data_kind}")
                target = latest_completed_trade_date(bundle.payload, now)
                available = {row["ticker"].upper() for row in bundle.payload.get("instruments") or []}
                missing = sorted(set(self.universe) - available)
                if missing:
                    raise ValueError("collector bundle misses configured universe: " + ",".join(missing))
                bundle = self._gap_bundle(bundle, target=target)
                attempt_number = len(receipt["attempts"]) + 1
                attempt_bundle_path = (
                    f"runs/{receipt['run_id']}/attempts/{attempt_number:02d}-{digest(adapter.name)[:12]}/bundle.json"
                )
                bundle_json = bundle.as_json()
                attempt_bundle_hash = digest(bundle_json)
                _atomic_json(self.state_root / attempt_bundle_path, bundle_json)
                current_active = _read_json(self.state_root / "active.json")
                reuse_active = bool(
                    current_active
                    and current_active.get("target_trade_date") == target
                    and current_active.get("payload_hash") == digest(bundle.payload)
                    and not self._publication_integrity(current_active)
                    and self._snapshot_has_explicit_raw_lineage(
                        current_active.get("snapshot_id")
                    )
                )
                staged_quality = (
                    {"status": "reused_active", "snapshot_id": current_active["snapshot_id"]}
                    if reuse_active
                    else self._stage_quality(bundle, target=target, run_id=receipt["run_id"])
                )
                if staged_quality["status"] not in {"passed", "reused_active"}:
                    error = "canonical quality failed: " + "; ".join(staged_quality.get("blockers") or [])
                    errors.append(error)
                    receipt["attempts"].append({
                        "adapter": adapter.name, "role": adapter.role, "status": "failed",
                        "data_kind": bundle.data_kind,
                        "started_at": started_at, "finished_at": _iso(_now()),
                        "manifest_hash": bundle.manifest.manifest_hash,
                        "payload_hash": digest(bundle.payload), "target_trade_date": target,
                        "bundle_path": attempt_bundle_path, "bundle_hash": attempt_bundle_hash,
                        "canonical_quality": staged_quality, "error": error[:1000],
                    })
                    self._save_receipt(receipt)
                    continue
                receipt["attempts"].append({
                    "adapter": adapter.name, "role": adapter.role, "status": "success",
                    "data_kind": bundle.data_kind,
                    "started_at": started_at, "finished_at": _iso(_now()),
                    "manifest_hash": bundle.manifest.manifest_hash,
                    "payload_hash": digest(bundle.payload), "target_trade_date": target,
                    "bundle_path": attempt_bundle_path, "bundle_hash": attempt_bundle_hash,
                    "canonical_quality": staged_quality,
                })
                receipt["selected_adapter"] = adapter.name
                receipt["selected_role"] = adapter.role
                receipt["target_trade_date"] = target
                receipt["payload_hash"] = digest(bundle.payload)
                receipt["reuse_active"] = reuse_active
                _atomic_json(self._bundle_path(receipt["run_id"]), bundle.as_json())
                return bundle
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                errors.append(error)
                receipt["attempts"].append({
                    "adapter": adapter.name, "role": adapter.role, "status": "failed",
                    "started_at": started_at, "finished_at": _iso(_now()), "error": error[:1000],
                    "bundle_path": attempt_bundle_path, "bundle_hash": attempt_bundle_hash,
                })
                self._save_receipt(receipt)
        raise RuntimeError("all configured sources failed: " + " | ".join(errors))

    def _build_reports(self, receipt: dict[str, Any], reader: SnapshotReader) -> list[dict[str, Any]]:
        reports = []
        report_root = self.state_root / "runs" / receipt["run_id"] / "reports"
        for ticker in self.universe:
            path = report_root / f"{ticker}.json"
            existing = _read_json(path)
            existing_valid = not _report_artifact_errors(
                existing or {}, ticker=ticker, snapshot_id=reader.snapshot_id, require_artifact_hash=True
            ) if existing else False
            if (
                existing_valid
            ):
                reports.append({
                    **existing, "status": "reused",
                    "artifact_path": f"runs/{receipt['run_id']}/reports/{ticker}.json",
                })
                continue
            try:
                artifact = _run_research_builder_isolated(self.research_builder, reader, ticker)
                artifact_errors = _report_artifact_errors(
                    artifact, ticker=ticker, snapshot_id=reader.snapshot_id, require_artifact_hash=False
                )
                if artifact_errors:
                    raise RuntimeError("research-report-v1 rejected: " + "; ".join(artifact_errors))
                artifact = {**artifact, "artifact_hash": digest(artifact)}
                _atomic_json(path, artifact)
                reports.append({
                    **artifact, "artifact_path": f"runs/{receipt['run_id']}/reports/{ticker}.json",
                })
            except Exception as exc:
                reports.append({
                    "ticker": ticker, "snapshot_id": reader.snapshot_id, "status": "failed",
                    "error": f"{type(exc).__name__}: {exc}"[:1000],
                })
        return reports

    def run(
        self,
        *,
        now: datetime | None = None,
        dry_run: bool = False,
        interrupt_after: str | None = None,
    ) -> dict[str, Any]:
        moment = now or _now()
        if dry_run:
            return {
                "schema_version": REFRESH_SCHEMA_VERSION, "status": "dry_run",
                "active": _read_json(self.state_root / "active.json"),
                "in_progress": _read_json(self.state_root / "in_progress.json"),
                "adapters": [{"name": item.name, "role": item.role} for item in self.adapters],
                "universe": list(self.universe), "network_called": False,
            }
        self.state_root.mkdir(parents=True, exist_ok=True)
        handle = self._lock_path.open("a+")
        try:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RefreshInProgressError("another canonical refresh is already running") from exc
            resumed = self._load_resumable()
            receipt, bundle = resumed if resumed else (self._new_receipt(moment), None)
            receipt["resumed"] = bool(resumed)
            try:
                if bundle is None:
                    bundle = self._collect(receipt, moment)
                    self._checkpoint(receipt, "collected", interrupt_after=interrupt_after)
                if receipt.get("reuse_active"):
                    active = _read_json(self.state_root / "active.json")
                    if not active:
                        raise RuntimeError("reused active version disappeared after source selection")
                    receipt.update({
                        "status": "success", "stage": "reused_active", "active": active,
                        "snapshot_id": active["snapshot_id"], "publication_id": active["publication_id"],
                        "snapshot_kind": active["snapshot_kind"], "ingestion_reused": True,
                        "report_gate": {"required": 8, "passed": 8, "status": "passed"},
                        "no_network_replay": {
                            "status": "passed",
                            "replay_digest": self.foundation.replay_digest(active["snapshot_id"]),
                            "network_boundary": "SnapshotReader exposes no fetch method",
                        },
                        "finished_at": _iso(_now()),
                    })
                    self._save_receipt(receipt)
                    (self.state_root / "in_progress.json").unlink(missing_ok=True)
                    return receipt
                if not receipt.get("ingestion_run_id"):
                    ingestions = self._ingest_bundle(self.foundation, bundle)
                    receipt["ingestion_runs"] = ingestions
                    receipt["ingestion_run_id"] = ingestions[-1]["run_id"]
                    receipt["ingestion_reused"] = all(bool(item["reused"]) for item in ingestions)
                    receipt["raw_hash"] = digest([item["raw_hash"] for item in ingestions])
                    self._checkpoint(receipt, "ingested", interrupt_after=interrupt_after)
                if not receipt.get("snapshot_id"):
                    quality_result = self.foundation.quality_evaluation(
                        receipt["ingestion_run_id"], as_of=receipt["target_trade_date"],
                        known_at=bundle.payload["known_at"],
                    )
                    receipt["quality_result"] = quality_result
                    self._save_receipt(receipt)
                    snapshot = self.foundation.create_snapshot(
                        receipt["ingestion_run_id"], as_of=receipt["target_trade_date"],
                        known_at=bundle.payload["known_at"], model_version=REFRESH_SCHEMA_VERSION,
                    )
                    receipt.update({
                        "snapshot_id": snapshot["snapshot_id"],
                        "snapshot_kind": snapshot["snapshot_kind"],
                        "snapshot_manifest_hash": snapshot["manifest_hash"],
                        "snapshot_raw_hashes": snapshot["raw_hashes"],
                        "snapshot_raw_hash_digest": snapshot["raw_hash_digest"],
                    })
                    self._checkpoint(receipt, "snapshotted", interrupt_after=interrupt_after)
                reader = SnapshotReader(self.foundation, receipt["snapshot_id"])
                receipt["reports"] = self._build_reports(receipt, reader)
                success_count = sum(item["status"] in {"success", "reused"} for item in receipt["reports"])
                receipt["report_gate"] = {
                    "required": len(self.universe), "passed": success_count,
                    "status": "passed" if success_count == len(self.universe) else "failed",
                }
                self._checkpoint(receipt, "reports_built", interrupt_after=interrupt_after)
                replay_digest = self.foundation.replay_digest(receipt["snapshot_id"])
                receipt["no_network_replay"] = {
                    "status": "passed", "replay_digest": replay_digest,
                    "network_boundary": "SnapshotReader exposes no fetch method",
                }
                if receipt["report_gate"]["status"] != "passed":
                    receipt["status"] = "partial"
                    receipt["stage"] = "blocked_before_activation"
                else:
                    current_active = _read_json(self.state_root / "active.json")
                    if (
                        current_active and current_active.get("target_trade_date")
                        and str(receipt["target_trade_date"]) < str(current_active["target_trade_date"])
                    ):
                        raise RuntimeError(
                            "candidate target trade date is older than the current active version"
                        )
                    report_hashes = {
                        item["ticker"]: item["report_hash"] for item in receipt["reports"]
                    }
                    publication_manifest = {
                        "schema_version": "canonical-research-publication-v1",
                        "snapshot_id": receipt["snapshot_id"],
                        "snapshot_kind": receipt["snapshot_kind"],
                        "target_trade_date": receipt["target_trade_date"],
                        "payload_hash": receipt["payload_hash"],
                        "report_schema_version": "research-report-v1",
                        "report_contract_version": "1.0.0",
                        "report_hashes": report_hashes,
                    }
                    publication_id = f"canonical_pub_{digest(_publication_base(publication_manifest))[:16]}"
                    publication_manifest["publication_id"] = publication_id
                    publication_manifest["report_artifacts"] = {
                        ticker: f"publications/{publication_id}/reports/{ticker}.json"
                        for ticker in report_hashes
                    }
                    for item in receipt["reports"]:
                        source_artifact = _read_json(self.state_root / item["artifact_path"])
                        if not source_artifact:
                            raise RuntimeError(f"{item['ticker']}: report artifact disappeared before publication")
                        artifact_errors = _report_artifact_errors(
                            source_artifact, ticker=item["ticker"], snapshot_id=receipt["snapshot_id"],
                            require_artifact_hash=True,
                        )
                        if artifact_errors:
                            raise RuntimeError(
                                f"{item['ticker']}: invalid report before publication: " + "; ".join(artifact_errors)
                            )
                        _atomic_json(
                            self.state_root / publication_manifest["report_artifacts"][item["ticker"]],
                            source_artifact,
                        )
                    publication_path = self.state_root / "publications" / f"{publication_id}.json"
                    existing_publication = _read_json(publication_path)
                    if existing_publication and existing_publication != publication_manifest:
                        raise RuntimeError("canonical publication identity collision")
                    if not existing_publication:
                        _atomic_json(publication_path, publication_manifest)
                    active = {
                        "schema_version": REFRESH_SCHEMA_VERSION,
                        "run_id": receipt["run_id"], "snapshot_id": receipt["snapshot_id"],
                        "publication_id": publication_id,
                        "snapshot_kind": receipt["snapshot_kind"],
                        "target_trade_date": receipt["target_trade_date"],
                        "payload_hash": receipt["payload_hash"],
                        "activated_at": _iso(_now()),
                        "report_hashes": report_hashes,
                    }
                    integrity_errors = self._publication_integrity(active)
                    if integrity_errors:
                        raise RuntimeError(
                            "publication failed integrity before activation: " + "; ".join(integrity_errors)
                        )
                    _atomic_json(self.state_root / "active.json", active)
                    receipt["status"] = "success"
                    receipt["stage"] = "activated"
                    receipt["publication_id"] = publication_id
                    receipt["publication_manifest"] = f"publications/{publication_id}.json"
                    receipt["active"] = active
                receipt["finished_at"] = _iso(_now())
                self._save_receipt(receipt)
                (self.state_root / "in_progress.json").unlink(missing_ok=True)
                return receipt
            except InjectedInterruption:
                raise
            except Exception as exc:
                receipt["status"] = "failed"
                receipt["stage"] = "failed"
                receipt["error"] = f"{type(exc).__name__}: {exc}"[:2000]
                receipt["finished_at"] = _iso(_now())
                receipt["active_preserved"] = _read_json(self.state_root / "active.json")
                self._save_receipt(receipt)
                (self.state_root / "in_progress.json").unlink(missing_ok=True)
                return receipt
        finally:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            finally:
                handle.close()

    def status(self) -> dict[str, Any]:
        latest = _read_json(self.state_root / "latest.json")
        active = _read_json(self.state_root / "active.json")
        in_progress = _read_json(self.state_root / "in_progress.json")
        integrity_errors = self._publication_integrity(active)
        healthy = (
            bool(active) and not in_progress and bool(latest) and latest.get("status") == "success"
            and not integrity_errors
        )
        return {
            "schema_version": REFRESH_SCHEMA_VERSION,
            "status": "healthy" if healthy else "attention",
            "active": active, "latest": latest, "in_progress": in_progress,
            "integrity_errors": integrity_errors,
        }


_LISTED_AT = {
    "600519.SH": "2001-08-27", "600036.SH": "2002-04-09",
    "600900.SH": "2003-11-18", "000333.SZ": "2013-09-18",
    "600941.SH": "2022-01-05", "300750.SZ": "2018-06-11",
    "601088.SH": "2007-10-09", "688036.SH": "2019-12-30",
}


def normalize_legacy_collector_bundle(inputs: dict[str, Any]) -> dict[str, Any]:
    """Adapt existing Tencent/Eastmoney collectors to the canonical row contract."""
    from data_store import DEMO_POSITIONS

    tickers = [item["ticker"] for item in DEMO_POSITIONS]
    quotes, klines, financials = inputs["quotes"], inputs["klines"], inputs["financials"]
    provider_raw_objects = {
        "calendar": [inputs["exchange_calendar"]],
        "quotes": [inputs["quote_raw"]],
        "klines": [
            {
                "ticker": ticker, "source_url": klines[ticker]["source_url"],
                "raw_hash": klines[ticker]["raw_hash"],
                "raw_payload_b64": klines[ticker]["raw_payload_b64"],
            }
            for ticker in tickers
        ],
        "financials": [
            {
                "ticker": ticker, "source_url": financials[ticker]["source_url"],
                "raw_hash": financials[ticker]["raw_hash"],
                "raw_payload_b64": financials[ticker]["raw_payload_b64"],
            }
            for ticker in tickers
        ],
    }
    for group in provider_raw_objects.values():
        for raw_object in group:
            raw_bytes = base64.b64decode(raw_object["raw_payload_b64"], validate=True)
            if hashlib.sha256(raw_bytes).hexdigest() != raw_object["raw_hash"]:
                raise ValueError("provider raw payload hash mismatch")
    calendar_dates = sorted({str(value)[:10] for value in inputs["exchange_calendar"]["trade_dates"]})
    collected_at = datetime.fromisoformat(str(inputs["finished_at"]).replace("Z", "+00:00")).astimezone(SHANGHAI)
    completed = [
        value for value in calendar_dates
        if value < collected_at.date().isoformat()
        or (value == collected_at.date().isoformat() and collected_at.time() >= time(15, 30))
    ]
    if len(completed) < 2:
        raise ValueError("independent exchange calendar has fewer than two completed trading dates")
    completed = completed[-400:]
    previous, target = completed[-2:]
    known_at = max(str(quotes[ticker]["quote_time"]) for ticker in tickers)
    instruments, statuses, factors, bars, facts, intelligence = [], [], [], [], [], []
    for item in DEMO_POSITIONS:
        ticker = item["ticker"]
        instrument_id = f"CN:{ticker}"
        code = ticker.split(".")[0]
        board = "CHINEXT" if code.startswith("3") else "STAR" if code.startswith("688") else "MAIN"
        exchange = "SSE" if ticker.endswith(".SH") else "SZSE"
        instruments.append({
            "instrument_id": instrument_id, "ticker": ticker, "name": item["name"],
            "exchange": exchange, "board": board, "industry": item["industry"],
            "listed_at": _LISTED_AT[ticker],
        })
        statuses.append({
            "instrument_id": instrument_id, "trade_date": target,
            "trading_status": "normal",
        })
        collected_sequence = int(
            datetime.fromisoformat(known_at.replace("Z", "+00:00")).timestamp()
        ) * 1_000_000
        adjustment_version = collected_sequence + int(str(klines[ticker]["raw_hash"])[-5:], 16)
        for row in klines[ticker]["bars"]:
            if row["trade_date"] > target:
                continue
            factors.append({
                "instrument_id": instrument_id, "trade_date": row["trade_date"],
                "factor": 1.0, "version": adjustment_version,
            })
            volume = float(row["volume_lots"]) * 100.0
            bars.append({
                "instrument_id": instrument_id, "trade_date": row["trade_date"],
                "open": row["open"], "high": row["high"], "low": row["low"],
                "close": row["close"], "volume": volume,
                "amount": float(row["close"]) * volume, "adjustment_version": adjustment_version,
            })
        for statement in financials[ticker]["rows"]:
            for metric_key, unit in (
                ("revenue", "CNY"), ("net_profit", "CNY"), ("revenue_yoy", "percent"),
                ("net_profit_yoy", "percent"), ("roe", "percent"),
                ("gross_margin", "percent"), ("net_margin", "percent"),
                ("debt_ratio", "percent"), ("operating_cash_per_share", "CNY/share"),
            ):
                if statement.get(metric_key) is None:
                    continue
                facts.append({
                    "fact_id": f"fact:{ticker}:{statement['report_date']}:{metric_key}:r1",
                    "instrument_id": instrument_id, "report_date": statement["report_date"],
                    "announced_at": f"{statement['notice_date']}T23:59:59+08:00", "revision": 1,
                    "metric_key": metric_key, "metric_value": float(statement[metric_key]), "unit": unit,
                })
        quote = quotes[ticker]
        intelligence.append({
            "item_id": f"quote:{ticker}:{quote['quote_time']}", "instrument_id": instrument_id,
            "title": f"{ticker} market quote", "published_at": quote["quote_time"],
            "evidence": {
                key: quote.get(key) for key in (
                    "price", "change_pct", "high", "low", "pe_ttm", "pb",
                    "market_cap_yi", "circulating_cap_yi", "source_key", "source_url", "raw_hash",
                )
            },
            "is_llm_inferred": False,
        })
    exchanges = sorted({row["exchange"] for row in instruments})
    return {
        "fixture": False, "as_of": target, "known_at": known_at,
        "instruments": instruments,
        "calendar": [
            {
                "exchange": exchange, "trade_date": trade_date, "is_open": 1,
                "previous_open_date": completed[index - 1] if index else None,
            }
            for index, trade_date in enumerate(completed) for exchange in exchanges
        ],
        "statuses": statuses, "factors": factors, "actions": [], "bars": bars,
        "financials": facts, "intelligence": intelligence,
        "collector_sources": {
            "quotes": sorted({row["source_url"] for row in quotes.values()}),
            "klines": sorted({row["source_url"] for row in klines.values()}),
            "financials": sorted({row["source_url"] for row in financials.values()}),
        },
        "collector_raw_hashes": {
            "quotes": sorted({row["raw_hash"] for row in quotes.values()}),
            "klines": sorted({row["raw_hash"] for row in klines.values()}),
            "financials": sorted({row["raw_hash"] for row in financials.values()}),
        },
        "provider_raw_objects": provider_raw_objects,
    }


class LegacyCollectorAdapter:
    """Production adapter for the already-shipped three-source collector bundle."""

    name = "legacy_tencent_eastmoney_bundle_v1"

    def __init__(self, *, role: str = "primary", timeout: float = 12.0) -> None:
        if role not in {"primary", "fallback"}:
            raise ValueError("adapter role must be primary or fallback")
        self.role = role
        self.timeout = timeout

    def collect(self, now: datetime) -> CollectedBundle:
        from real_pipeline import collect_real_inputs

        payload = normalize_legacy_collector_bundle(collect_real_inputs(timeout=self.timeout))
        empty = {
            "fixture": False, "as_of": payload["as_of"], "known_at": payload["known_at"],
            "instruments": [], "calendar": [], "statuses": [], "factors": [],
            "actions": [], "bars": [], "financials": [], "intelligence": [],
        }
        component_specs = (
            (
                "sina_exchange_calendar_v1", "https://finance.sina.com.cn/",
                {
                    **empty, "calendar": payload["calendar"],
                    "component_source_urls": [payload["provider_raw_objects"]["calendar"][0]["source_url"]],
                    "provider_raw_hashes": [payload["provider_raw_objects"]["calendar"][0]["raw_hash"]],
                    "provider_raw_objects": payload["provider_raw_objects"]["calendar"],
                },
                ("independent_exchange_calendar", "akshare_trade_date_decoder"),
            ),
            (
                "tencent_qfq_daily_v1", "https://web.ifzq.gtimg.cn/",
                {
                    **empty, "instruments": payload["instruments"],
                    "statuses": payload["statuses"], "factors": payload["factors"],
                    "actions": payload["actions"], "bars": payload["bars"],
                    "component_source_urls": payload["collector_sources"]["klines"],
                    "provider_raw_hashes": payload["collector_raw_hashes"]["klines"],
                    "provider_raw_objects": payload["provider_raw_objects"]["klines"],
                },
                ("vendor_qfq", "instrument_reference_v1", "suspension_aware"),
            ),
            (
                "tencent_quote_v1", "https://qt.gtimg.cn/",
                {
                    **empty, "intelligence": payload["intelligence"],
                    "component_source_urls": payload["collector_sources"]["quotes"],
                    "provider_raw_hashes": payload["collector_raw_hashes"]["quotes"],
                    "provider_raw_objects": payload["provider_raw_objects"]["quotes"],
                },
                ("market_quote_observation",),
            ),
            (
                "eastmoney_f10_main_v1", "https://datacenter.eastmoney.com/",
                {
                    **empty, "financials": payload["financials"],
                    "component_source_urls": payload["collector_sources"]["financials"],
                    "provider_raw_hashes": payload["collector_raw_hashes"]["financials"],
                    "provider_raw_objects": payload["provider_raw_objects"]["financials"],
                },
                ("notice_date_point_in_time", "revision_identity_required_for_corrections"),
            ),
        )
        components_list = []
        for source_key, source_url, component_payload, quality_flags in component_specs:
            component_payload["normalization_receipt"] = build_normalization_receipt(component_payload)
            components_list.append(CanonicalComponent(
                manifest=SourceManifest(
                    source_key=source_key, domain_scope="a_share_market", authority_tier="canonical",
                    provider_version="2026-07-adapter-v1", schema_version=REFRESH_SCHEMA_VERSION,
                    license_status="configured_internal_use", source_url=source_url,
                    quality_flags=quality_flags,
                ),
                payload=component_payload,
            ))
        components = tuple(components_list)
        manifest = SourceManifest(
            source_key=self.name, domain_scope="a_share_market_bundle", authority_tier="canonical",
            provider_version="tencent-quote+qfq-eastmoney-f10-2026-07",
            schema_version=REFRESH_SCHEMA_VERSION, license_status="configured_internal_use",
            source_url="bundle://tencent_quote+tencent_qfq_daily+eastmoney_f10_main",
            quality_flags=("normalized_bundle", "vendor_qfq", "instrument_reference_v1"),
        )
        return CollectedBundle(
            adapter=self.name, role=self.role, payload=payload, manifest=manifest, data_kind="real",
            components=components,
        )


class FileBundleFallbackAdapter:
    """Explicit cached fallback backed by a previously frozen bundle receipt."""

    name = "file_bundle_fallback_v1"
    role = "fallback"

    def __init__(self, bundle_path: Path | str) -> None:
        self.bundle_path = Path(bundle_path)

    def collect(self, now: datetime) -> CollectedBundle:
        value = _read_json(self.bundle_path)
        if not value:
            raise RuntimeError("configured fallback bundle is missing or invalid JSON")
        stored = CollectedBundle.from_json(value)
        if stored.data_kind == "fixture":
            raise RuntimeError("fixture bundle cannot be configured as a product fallback")
        validate_provider_raw_objects(stored.payload, required=False)
        if not stored.payload.get("provider_raw_objects"):
            raise RuntimeError("cached fallback lacks provider raw objects")
        for component in stored.components:
            validate_provider_raw_objects(
                component.payload, required=True, source_key=component.manifest.source_key
            )
        return CollectedBundle(
            adapter=self.name, role=self.role, payload=stored.payload,
            manifest=stored.manifest, data_kind="cached", components=stored.components,
        )
