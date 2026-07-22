from __future__ import annotations

from copy import deepcopy
from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
from html import escape
import json
import math
import os
from pathlib import Path
import re
from typing import Any

from data_store import (
    DB_PATH,
    connect,
    initialize,
    snapshot_content_hash,
    stock_payload,
    verify_snapshot_content_attestation,
)
from report_contract import validate_report_contract
from company_research import report_payload_hash
from research_reports import _baseline_report, _report_hash


PORTFOLIO_SCHEMA_VERSION = "canonical-portfolio-v1"
ALLOCATION_CONFIG_VERSION = "long-horizon-allocation-v1"
DEFAULT_STATE_ROOT = Path(__file__).resolve().parent / "runtime" / "canonical_portfolio"
HASH_RE = re.compile(r"^[0-9a-f]{64}$")


class CanonicalPortfolioError(RuntimeError):
    pass


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def digest(value: object) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _report_binding(report: dict[str, Any], snapshot_id: str) -> dict[str, Any]:
    errors = validate_report_contract(report.get("report_contract") or {}, report)
    generated = report.get("generated_from") or {}
    report_hash = report.get("report_hash")
    if errors:
        raise CanonicalPortfolioError("report contract failed: " + "; ".join(errors))
    if generated.get("snapshot_id") != snapshot_id:
        raise CanonicalPortfolioError("report snapshot identity mismatch")
    if not isinstance(report_hash, str) or not HASH_RE.fullmatch(report_hash):
        raise CanonicalPortfolioError("report hash is missing")
    if generated.get("production_input_identity"):
        calculated_report_hash = report_payload_hash(report)
    else:
        baseline_payload = deepcopy(report)
        baseline_payload.pop("report_hash", None)
        baseline_payload.pop("update_diff", None)
        calculated_report_hash = _report_hash(baseline_payload)
    if report_hash != calculated_report_hash:
        raise CanonicalPortfolioError("report payload hash mismatch")
    truth = (report.get("report_contract") or {}).get("truth_set") or {}
    evidence_identity = generated.get("evidence_manifest_hash") or digest({
        "snapshot_id": snapshot_id,
        "sources": report.get("sources") or [],
        "source_contract": report.get("source_contract") or {},
    })
    return {
        "report_hash": report_hash,
        "snapshot_id": snapshot_id,
        "model_version": generated.get("model_version"),
        "allocation_config_version": ALLOCATION_CONFIG_VERSION,
        "evidence_identity": evidence_identity,
        "contract_version": (report.get("report_contract") or {}).get("contract_version"),
        "research_status": report.get("research_status"),
        "research_depth": report.get("research_depth"),
        "evidence_status": "verified" if report.get("data_status") == "verified" else "blocked",
        "is_live_research": bool(truth.get("is_live_research")),
    }


def resolve_report_bindings(
    snapshot_id: str,
    tickers: list[str],
    db_path: Path = DB_PATH,
    *,
    deep_report_root: Path | None = None,
) -> dict[str, dict[str, Any]]:
    """Bind every allocation row to a current validated report identity.

    A deep report is preferred only when it names the exact snapshot and passes
    the public report contract. Remaining stocks use the deterministic baseline
    generated from the same immutable snapshot; they remain explicitly labelled
    quantitative_baseline rather than being promoted to deep research.
    """

    bindings: dict[str, dict[str, Any]] = {}
    for ticker in tickers:
        report: dict[str, Any] | None = None
        if deep_report_root is not None:
            candidate = _read_json(deep_report_root / ticker / "report.json")
            if candidate and (candidate.get("generated_from") or {}).get("snapshot_id") == snapshot_id:
                report = candidate
        if report is None:
            stock = stock_payload(ticker, db_path, snapshot_id=snapshot_id)
            if not stock:
                raise CanonicalPortfolioError(f"snapshot-bound stock payload is unavailable: {ticker}")
            report = _baseline_report(stock, db_path)
        bindings[ticker] = _report_binding(report, snapshot_id)
    return bindings


def _action(previous: float | None, target: float) -> str:
    if previous is None or previous == 0:
        return "新建"
    if target > previous:
        return "加仓"
    if target < previous:
        return "减仓"
    return "持有"


def validate_portfolio_version(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    def number(value: Any, label: str) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            errors.append(f"{label} must be numeric")
            return 0.0
        if not math.isfinite(parsed):
            errors.append(f"{label} must be finite")
            return 0.0
        return parsed

    raw_positions = payload.get("positions")
    if not isinstance(raw_positions, list) or any(not isinstance(item, dict) for item in raw_positions):
        errors.append("portfolio positions must be a list of objects")
        positions = [item for item in raw_positions if isinstance(item, dict)] if isinstance(raw_positions, list) else []
    else:
        positions = raw_positions
    allocation = payload.get("allocation") if isinstance(payload.get("allocation"), dict) else {}
    snapshot = payload.get("snapshot") if isinstance(payload.get("snapshot"), dict) else {}
    if payload.get("schema_version") != PORTFOLIO_SCHEMA_VERSION:
        errors.append("portfolio schema version mismatch")
    if snapshot.get("data_mode") != "REAL" or snapshot.get("quality_status") != "passed":
        errors.append("portfolio requires one passed REAL snapshot")
    role = payload.get("portfolio_role")
    attestation_status = snapshot.get("attestation_status")
    if role == "canonical_current" and attestation_status != "immutable_attestation_verified":
        errors.append("canonical current portfolio requires an immutable snapshot attestation")
    elif role == "retrospective_reference_only" and attestation_status != "retrospective_hash_only":
        errors.append("retrospective portfolio role/attestation mismatch")
    elif role not in {"canonical_current", "retrospective_reference_only"}:
        errors.append("portfolio role is invalid")
    if not 6 <= len(positions) <= 12:
        errors.append("portfolio must contain 6-12 stocks")
    tickers = [item.get("ticker") for item in positions]
    if len(set(tickers)) != len(tickers):
        errors.append("portfolio tickers must be unique")
    equity = round(sum(number(item.get("target_weight"), f"target weight {item.get('ticker')}") for item in positions), 6)
    cash = number(allocation.get("cash_weight"), "cash weight")
    if round(equity + cash, 6) != 100:
        errors.append("stock and cash weights must total 100")
    if not 10 <= cash <= 40:
        errors.append("cash weight must be 10-40 percent")
    if number(allocation.get("equity_weight"), "declared equity weight") != equity:
        errors.append("declared equity weight does not reconcile")
    industries: dict[str, float] = {}
    for item in positions:
        weight = number(item.get("target_weight"), f"target weight {item.get('ticker')}")
        if not 5 <= weight <= 15:
            errors.append(f"single-stock weight out of range: {item.get('ticker')}")
        industry = str(item.get("industry") or "")
        industries[industry] = industries.get(industry, 0) + weight
        binding = item.get("report_binding") or {}
        if binding.get("snapshot_id") != snapshot.get("snapshot_id"):
            errors.append(f"report snapshot mismatch: {item.get('ticker')}")
        if not isinstance(binding.get("report_hash"), str) or not HASH_RE.fullmatch(binding["report_hash"]):
            errors.append(f"report identity missing: {item.get('ticker')}")
        if binding.get("model_version") != payload.get("model_version"):
            errors.append(f"report model mismatch: {item.get('ticker')}")
        if binding.get("allocation_config_version") != payload.get("allocation_config_version"):
            errors.append(f"allocation config mismatch: {item.get('ticker')}")
        if not isinstance(binding.get("evidence_identity"), str) or not HASH_RE.fullmatch(binding["evidence_identity"]):
            errors.append(f"report evidence identity missing: {item.get('ticker')}")
        if binding.get("evidence_status") != "verified":
            errors.append(f"report evidence is not verified: {item.get('ticker')}")
        depth_status = (binding.get("research_depth"), binding.get("research_status"))
        if depth_status not in {("deep", "verified"), ("quantitative_baseline", "baseline")}:
            errors.append(f"report research depth/status is invalid: {item.get('ticker')}")
        if binding.get("is_live_research") is not True:
            errors.append(f"report is not live research: {item.get('ticker')}")
        if binding.get("contract_version") != "1.0.0":
            errors.append(f"report contract version mismatch: {item.get('ticker')}")
        previous_target = item.get("previous_target_weight")
        drifted_weight = item.get("drifted_weight")
        if payload.get("previous_portfolio_id") is None:
            if previous_target is not None or drifted_weight is not None:
                errors.append(f"initial position cannot claim historical drift: {item.get('ticker')}")
            action_input = None
        else:
            if (
                isinstance(previous_target, bool) or isinstance(drifted_weight, bool)
                or not isinstance(previous_target, (int, float))
                or not isinstance(drifted_weight, (int, float))
                or not math.isfinite(float(previous_target)) or not math.isfinite(float(drifted_weight))
            ):
                errors.append(f"position drift fields are missing: {item.get('ticker')}")
                action_input = None
            else:
                if previous_target < 0 or drifted_weight < 0:
                    errors.append(f"position drift fields are negative: {item.get('ticker')}")
                action_input = float(drifted_weight)
        if item.get("action") != _action(action_input, weight):
            errors.append(f"portfolio action does not match drift-to-target change: {item.get('ticker')}")
        if item.get("action") not in {"新建", "加仓", "持有", "减仓", "退出"}:
            errors.append(f"invalid portfolio action: {item.get('ticker')}")
    if any(weight > 30 for weight in industries.values()):
        errors.append("industry weight exceeds 30 percent")
    expected_exposure = [
        {"industry": key, "weight": round(value, 4)}
        for key, value in sorted(industries.items(), key=lambda row: (-row[1], row[0]))
    ]
    if payload.get("industry_exposure") != expected_exposure:
        errors.append("industry exposure does not reconcile")
    identity_payload = deepcopy(payload)
    declared_id = identity_payload.pop("portfolio_id", None)
    declared_hash = identity_payload.pop("payload_hash", None)
    calculated_hash = digest(identity_payload)
    if declared_hash != calculated_hash:
        errors.append("portfolio payload hash mismatch")
    if declared_id != f"canonical_portfolio_{calculated_hash[:16]}":
        errors.append("portfolio identity mismatch")
    return errors


def build_portfolio_version(
    snapshot_id: str,
    db_path: Path = DB_PATH,
    *,
    previous: dict[str, Any] | None = None,
    deep_report_root: Path | None = None,
) -> dict[str, Any]:
    initialize(db_path)
    with closing(connect(db_path)) as connection:
        connection.execute("BEGIN")
        snapshot = connection.execute(
            "SELECT * FROM dataset_snapshots WHERE id=?", (snapshot_id,),
        ).fetchone()
        publication = connection.execute(
            """SELECT * FROM publications WHERE snapshot_id=?
               AND status IN ('quality_passed','approved','published') ORDER BY id LIMIT 1""",
            (snapshot_id,),
        ).fetchone()
        if not snapshot or not publication:
            raise CanonicalPortfolioError("snapshot or qualified source publication is unavailable")
        if snapshot["data_mode"] != "REAL" or snapshot["quality_status"] != "passed":
            raise CanonicalPortfolioError("portfolio requires one passed REAL snapshot")
        positions = [dict(row) for row in connection.execute(
            "SELECT * FROM portfolio_items WHERE publication_id=? ORDER BY ticker",
            (publication["id"],),
        ).fetchall()]
        risks = [dict(row) for row in connection.execute(
            "SELECT rank,title,detail,severity FROM portfolio_risks WHERE publication_id=? ORDER BY rank",
            (publication["id"],),
        ).fetchall()]
        attestation = connection.execute(
            "SELECT content_hash FROM snapshot_content_attestations WHERE snapshot_id=?", (snapshot_id,),
        ).fetchone()
        if attestation:
            normalized_hash = verify_snapshot_content_attestation(connection, snapshot_id)
            attestation_status = "immutable_attestation_verified"
        else:
            normalized_hash = snapshot_content_hash(connection, snapshot_id)
            attestation_status = "retrospective_hash_only"

    if not positions:
        raise CanonicalPortfolioError("portfolio contains no positions")
    tickers = [str(item["ticker"]) for item in positions]
    bindings = resolve_report_bindings(
        snapshot_id, tickers, db_path, deep_report_root=deep_report_root,
    )
    with closing(connect(db_path)) as connection:
        connection.execute("BEGIN")
        current_hash = (
            verify_snapshot_content_attestation(connection, snapshot_id)
            if attestation else snapshot_content_hash(connection, snapshot_id)
        )
        if current_hash != normalized_hash:
            raise CanonicalPortfolioError("snapshot contents changed while portfolio reports were resolved")
    previous_positions = {
        str(item["ticker"]): item for item in ((previous or {}).get("positions") or [])
    }
    current_rows = {str(item["ticker"]): item for item in positions}
    drift_values: dict[str, float] = {}
    drift_total = float(((previous or {}).get("allocation") or {}).get("cash_weight") or 0)
    for ticker, prior_item in previous_positions.items():
        prior_weight = float(prior_item["target_weight"])
        prior_price = float(prior_item.get("reference_price") or 0)
        current_price = float((current_rows.get(ticker) or {}).get("reference_price") or prior_price)
        marked_value = prior_weight * current_price / prior_price if prior_price > 0 else prior_weight
        drift_values[ticker] = marked_value
        drift_total += marked_value
    output_positions = []
    for item in positions:
        ticker = str(item["ticker"])
        target = float(item["target_weight"])
        prior_item = previous_positions.get(ticker)
        prior = float(prior_item["target_weight"]) if prior_item else None
        drifted = (
            round(drift_values.get(ticker, 0) * 100 / drift_total, 6)
            if previous is not None and drift_total > 0 else None
        )
        output_positions.append({
            "ticker": ticker,
            "name": item["name"],
            "exchange": item["exchange"],
            "industry": item["industry"],
            "reference_price": item["reference_price"],
            "target_weight": target,
            "previous_target_weight": prior,
            "drifted_weight": drifted,
            "action": _action(drifted, target),
            "execution_observation_range": item["execution_range"],
            "confidence": int(item["confidence"]),
            "thesis": item["thesis"],
            "primary_risk": item["primary_risk"],
            "weight_semantics": "model_suggested_non_executable",
            "report_binding": bindings[ticker],
        })
    output_positions.sort(key=lambda item: (-item["target_weight"], item["ticker"]))
    equity = round(sum(item["target_weight"] for item in output_positions), 4)
    industries: dict[str, float] = {}
    for item in output_positions:
        industries[item["industry"]] = industries.get(item["industry"], 0) + item["target_weight"]
    payload: dict[str, Any] = {
        "schema_version": PORTFOLIO_SCHEMA_VERSION,
        "portfolio_role": (
            "canonical_current" if attestation_status == "immutable_attestation_verified"
            else "retrospective_reference_only"
        ),
        "snapshot": {
            "snapshot_id": snapshot_id,
            "manifest_hash": snapshot["manifest_hash"],
            "normalized_content_hash": normalized_hash,
            "attestation_status": attestation_status,
            "data_mode": snapshot["data_mode"],
            "quality_status": snapshot["quality_status"],
            "as_of": snapshot["as_of"],
            "known_at": snapshot["known_at"],
        },
        "source_publication_id": publication["id"],
        "previous_portfolio_id": (previous or {}).get("portfolio_id"),
        "model_version": publication["model_version"],
        "allocation_config_version": ALLOCATION_CONFIG_VERSION,
        "generated_at": snapshot["created_at"],
        "market_regime": publication["market_regime"],
        "regime_note": publication["regime_note"],
        "allocation": {"equity_weight": equity, "cash_weight": float(publication["cash_weight"]), "total": round(equity + float(publication["cash_weight"]), 4)},
        "positions": output_positions,
        "industry_exposure": [
            {"industry": key, "weight": round(value, 4)}
            for key, value in sorted(industries.items(), key=lambda row: (-row[1], row[0]))
        ],
        "risks": risks[:3],
        "publication_state": (
            "model_suggestion_ready_for_park_review"
            if attestation_status == "immutable_attestation_verified"
            else "retrospective_replay_not_publishable"
        ),
        "execution_boundary": "No broker connection. Suggested weights are not executed holdings until a separately approved publication and model-ledger event exist.",
    }
    payload_hash = digest(payload)
    payload["payload_hash"] = payload_hash
    payload["portfolio_id"] = f"canonical_portfolio_{payload_hash[:16]}"
    errors = validate_portfolio_version(payload)
    if errors:
        raise CanonicalPortfolioError("portfolio validation failed: " + "; ".join(errors))
    return payload


def portfolio_diff(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    before = {item["ticker"]: item for item in previous["positions"]}
    after = {item["ticker"]: item for item in current["positions"]}
    rows = []
    for ticker in sorted(set(before) | set(after)):
        old = float((before.get(ticker) or {}).get("target_weight") or 0)
        new = float((after.get(ticker) or {}).get("target_weight") or 0)
        if old == new:
            continue
        item = after.get(ticker) or before[ticker]
        rows.append({
            "ticker": ticker,
            "name": item["name"],
            "before_weight": old,
            "after_weight": new,
            "change": round(new - old, 4),
            "action": _action(old, new) if new else "退出",
            "reason": "确定性评分与约束引擎在新快照上重新计算；详细依据见绑定研报与风险字段。",
        })
    payload = {
        "schema_version": "canonical-portfolio-diff-v1",
        "from_portfolio_id": previous["portfolio_id"],
        "to_portfolio_id": current["portfolio_id"],
        "from_snapshot_id": previous["snapshot"]["snapshot_id"],
        "to_snapshot_id": current["snapshot"]["snapshot_id"],
        "cash_change": round(current["allocation"]["cash_weight"] - previous["allocation"]["cash_weight"], 4),
        "changes": rows,
    }
    payload["diff_hash"] = digest(payload)
    return payload


def portfolio_state_root() -> Path:
    return Path(os.environ.get("PARK_CANONICAL_PORTFOLIO_ROOT", DEFAULT_STATE_ROOT))


def load_portfolio_state(state_root: Path | str | None = None) -> dict[str, Any]:
    root = Path(state_root) if state_root is not None else portfolio_state_root()
    pointer = _read_json(root / "current.json")
    if not pointer:
        raise CanonicalPortfolioError("canonical portfolio current pointer is unavailable")
    portfolio_id = pointer.get("portfolio_id")
    version = _read_json(root / "versions" / f"{portfolio_id}.json") if portfolio_id else None
    if not version or pointer.get("payload_hash") != version.get("payload_hash"):
        raise CanonicalPortfolioError("canonical portfolio pointer/version mismatch")
    errors = validate_portfolio_version(version)
    if errors:
        raise CanonicalPortfolioError("canonical portfolio state is invalid: " + "; ".join(errors))
    if digest({key: pointer.get(key) for key in ("portfolio_id", "payload_hash", "snapshot_id")}) != pointer.get("pointer_hash"):
        raise CanonicalPortfolioError("canonical portfolio pointer hash mismatch")
    history = load_portfolio_history(root)
    if not history or history[-1]["portfolio_id"] != portfolio_id:
        raise CanonicalPortfolioError("canonical portfolio pointer is not the latest valid version")
    if version.get("portfolio_role") != "canonical_current":
        raise CanonicalPortfolioError("canonical portfolio current pointer targets a retrospective reference")
    return deepcopy(version)


def load_portfolio_history(state_root: Path | str | None = None) -> list[dict[str, Any]]:
    root = Path(state_root) if state_root is not None else portfolio_state_root()
    items = []
    for path in sorted((root / "versions").glob("canonical_portfolio_*.json")):
        value = _read_json(path)
        if not value:
            raise CanonicalPortfolioError(f"canonical portfolio history is unreadable: {path.name}")
        errors = validate_portfolio_version(value)
        if errors:
            raise CanonicalPortfolioError(
                f"canonical portfolio history is invalid: {path.name}: " + "; ".join(errors)
            )
        if path.stem != value["portfolio_id"]:
            raise CanonicalPortfolioError(f"canonical portfolio history filename mismatch: {path.name}")
        items.append(value)
    ordered = sorted(items, key=lambda item: (item["snapshot"]["known_at"], item["portfolio_id"]))
    previous_id = None
    for item in ordered:
        if item.get("previous_portfolio_id") != previous_id:
            raise CanonicalPortfolioError("canonical portfolio history chain is broken")
        previous_id = item["portfolio_id"]
    return ordered


def render_portfolio_html(
    current: dict[str, Any], history: list[dict[str, Any]], diff: dict[str, Any], ledger: dict[str, Any]
) -> str:
    rows = "".join(
        f"<tr><td data-label='公司'><strong>{escape(item['name'])}</strong><small>{escape(item['ticker'])}</small>"
        f"<small class='primary-risk'>首要风险：{escape(item['primary_risk'])}</small></td>"
        f"<td data-label='行业'>{escape(item['industry'])}</td><td data-label='参考价'>¥{float(item['reference_price']):,.2f}</td>"
        f"<td data-label='建议仓位' class='weight'>{item['target_weight']:.0f}%</td>"
        f"<td data-label='动作'><span class='action'>{escape(item['action'])}</span></td>"
        f"<td data-label='执行观察区间'>{escape(item['execution_observation_range'])}</td>"
        f"<td data-label='置信度'>{item['confidence']}</td>"
        f"<td data-label='研究深度'><span class='depth'>{escape(item['report_binding']['research_depth'])}</span></td></tr>"
        for item in current["positions"]
    )
    changes = "".join(
        f"<li><strong>{escape(item['name'])}</strong><span>{item['before_weight']:.0f}% → {item['after_weight']:.0f}%</span>"
        f"<em>{escape(item['action'])}</em><p>{escape(item['reason'])}</p></li>"
        for item in diff["changes"]
    ) or "<li><strong>无目标仓位变化</strong><p>新快照未触发超过约束阈值的调整。</p></li>"
    risks = "".join(
        f"<li><span>0{index}</span><div><strong>{escape(item['title'])}</strong><p>{escape(item['detail'])}</p></div></li>"
        for index, item in enumerate(current["risks"], 1)
    )
    history_rows = "".join(
        f"<article><span>{escape(item['snapshot']['as_of'])}</span>"
        f"<em>{'历史补算 · 非当日发布' if item['snapshot']['attestation_status'] == 'retrospective_hash_only' else '当前验证版本'}</em>"
        f"<strong>{escape(item['portfolio_id'])}</strong>"
        f"<p>股票 {item['allocation']['equity_weight']:.0f}% · 现金 {item['allocation']['cash_weight']:.0f}% · {len(item['positions'])} 只</p></article>"
        for item in reversed(history)
    )
    ledger_rows = "".join(
        f"<tr><td data-label='公司'>{escape(item['name'])}</td>"
        f"<td data-label='目标路径'>{item['previous_target_weight']:.2f}% → {item['drifted_weight']:.2f}% → {item['target_weight']:.2f}%</td>"
        f"<td data-label='状态'>{escape(item.get('status') or 'planned')}</td>"
        f"<td data-label='生效日'>{escape(item.get('effective_trade_date') or '待下一交易日')}</td></tr>"
        for item in ledger.get("orders", [])
    )
    return f"""<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Park 投委会 · A 股长期模型组合</title><style>
:root{{--ink:#10233f;--blue:#174f8a;--line:#dbe3ec;--muted:#66758a;--paper:#fff;--wash:#f4f7fa}}*{{box-sizing:border-box}}body{{margin:0;background:var(--wash);color:var(--ink);font-family:Arial,'PingFang SC','Microsoft YaHei',sans-serif;line-height:1.55}}main{{max-width:1200px;margin:auto;background:var(--paper);box-shadow:0 0 40px #18355418}}header{{padding:50px 64px 38px;border-top:8px solid var(--blue);border-bottom:1px solid var(--line)}}.eyebrow{{margin:0 0 10px;color:var(--blue);font-size:12px;font-weight:700;letter-spacing:.16em}}h1{{font-family:Georgia,'Songti SC',serif;font-size:42px;line-height:1.16;margin:0;max-width:820px}}.sub{{color:var(--muted);max-width:780px}}.hero{{display:grid;grid-template-columns:1.5fr repeat(2,1fr);gap:0;border-bottom:1px solid var(--line)}}.hero>div{{padding:28px 32px;border-right:1px solid var(--line)}}.hero strong{{display:block;font-size:30px}}section{{padding:38px 64px;border-bottom:1px solid var(--line)}}h2{{font-family:Georgia,'Songti SC',serif;font-size:28px;margin:0 0 20px}}table{{width:100%;border-collapse:collapse;font-size:13px}}th{{text-align:left;color:var(--muted);font-weight:600;border-bottom:2px solid var(--ink);padding:10px 8px}}td{{padding:14px 8px;border-bottom:1px solid var(--line);vertical-align:top}}td small{{display:block;color:var(--muted)}}.primary-risk{{max-width:210px;margin-top:5px;font-size:10px;line-height:1.35}}.weight{{font-size:19px;font-weight:700}}.action,.depth{{display:inline-block;padding:3px 8px;background:#e9f0f8;color:var(--blue);font-weight:700}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:46px}}ol{{list-style:none;padding:0;margin:0}}.changes li{{display:grid;grid-template-columns:1fr auto auto;gap:8px;padding:13px 0;border-bottom:1px solid var(--line)}}.changes p{{grid-column:1/-1;color:var(--muted);margin:0}}.changes em{{font-style:normal;color:var(--blue);font-weight:700}}.risks li{{display:flex;gap:16px;padding:14px 0;border-bottom:1px solid var(--line)}}.risks span{{font:700 28px Georgia;color:#9db0c4}}.risks p{{margin:3px 0;color:var(--muted)}}.history{{display:grid;grid-template-columns:repeat(2,1fr);gap:14px}}.history article{{padding:18px;border:1px solid var(--line)}}.history span,.history strong{{display:block}}.history span{{color:var(--muted);font-size:12px}}.history em{{display:inline-block;margin:5px 0;color:var(--blue);font-size:11px;font-style:normal;font-weight:700}}footer{{padding:28px 64px;background:var(--ink);color:white;font-size:12px}}code{{font-size:11px;word-break:break-all}}@media(max-width:700px){{main{{box-shadow:none}}header,section{{padding:28px 20px}}h1{{font-size:31px}}.hero{{grid-template-columns:1fr}}.hero>div{{border-right:0;border-bottom:1px solid var(--line)}}.grid{{grid-template-columns:1fr}}.portfolio-table thead,.ledger-table thead{{display:none}}.portfolio-table,.portfolio-table tbody,.portfolio-table tr,.portfolio-table td,.ledger-table,.ledger-table tbody,.ledger-table tr,.ledger-table td{{display:block;width:100%}}.portfolio-table tr,.ledger-table tr{{padding:12px 0;border-bottom:2px solid var(--ink)}}.portfolio-table td,.ledger-table td{{display:grid;grid-template-columns:96px 1fr;gap:8px;padding:7px 0;border:0}}.portfolio-table td:before,.ledger-table td:before{{content:attr(data-label);color:var(--muted);font-size:11px;font-weight:700}}.portfolio-table td strong,.portfolio-table td small{{grid-column:2}}.primary-risk{{max-width:none}}.history{{grid-template-columns:1fr}}footer{{padding:24px 20px}}}}
</style></head><body><main><header><p class='eyebrow'>PARK INVESTMENT COMMITTEE / WEEKLY MANDATE</p><h1>{escape(current['market_regime'])}：明确持有什么，也明确什么还没有被执行</h1><p class='sub'>{escape(current['regime_note'])} 本页全部仓位由确定性约束引擎生成；DeepSeek 不参与权重。</p></header>
<div class='hero'><div><p class='eyebrow'>本期模型建议</p><strong>{len(current['positions'])} 只 A 股</strong><span>{escape(current['snapshot']['as_of'])} · 1000 万元基准</span></div><div><p class='eyebrow'>股票仓位</p><strong>{current['allocation']['equity_weight']:.0f}%</strong></div><div><p class='eyebrow'>现金仓位</p><strong>{current['allocation']['cash_weight']:.0f}%</strong></div></div>
<section><p class='eyebrow'>MODEL PORTFOLIO</p><h2>股票名称、建议仓位与当前动作</h2><table class='portfolio-table'><thead><tr><th>公司</th><th>行业</th><th>参考价</th><th>建议仓位</th><th>动作</th><th>执行观察区间</th><th>置信度</th><th>研究深度</th></tr></thead><tbody>{rows}</tbody></table></section>
<section class='grid'><div><p class='eyebrow'>PERIOD-OVER-PERIOD</p><h2>相对上期发生了什么</h2><ol class='changes'>{changes}</ol></div><div><p class='eyebrow'>RISK DESK</p><h2>组合级风险</h2><ol class='risks'>{risks}</ol></div></section>
<section><p class='eyebrow'>MODEL LEDGER</p><h2>模拟调仓账本</h2><table class='ledger-table'><thead><tr><th>公司</th><th>上期目标 → 漂移权重 → 本期目标</th><th>状态</th><th>生效日</th></tr></thead><tbody>{ledger_rows}</tbody></table></section>
<section><p class='eyebrow'>VERSION HISTORY</p><h2>不可回写的组合版本</h2><div class='history'>{history_rows}</div></section>
<footer><strong>研究边界</strong><p>{escape(current['execution_boundary'])} 标记为“历史补算”的版本仅为事后重放，不代表当日已发布。</p><code>{escape(current['portfolio_id'])} · {escape(current['payload_hash'])}</code></footer></main></body></html>"""
