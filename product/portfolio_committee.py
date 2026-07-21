from __future__ import annotations

from pathlib import Path
from typing import Any

from data_store import DB_PATH, dashboard_payload
from deepseek_writer import editorial_status
from research_reports import report_payload


def _round(value: float) -> float:
    return round(float(value), 1)


def _readiness_item(
    position: dict[str, Any],
    snapshot_id: str,
    publication_status: str,
    db_path: Path,
) -> dict[str, Any]:
    report = report_payload(position["ticker"], db_path, snapshot_id=snapshot_id)
    if not report or report.get("research_status") == "unverified":
        return {
            "ticker": position["ticker"], "name": position["name"], "industry": position["industry"],
            "research_status": "blocked", "research_depth": "unverified",
            "model_score": position.get("composite_score"), "model_observation_weight": position.get("target_weight"),
            "decision_review_weight": None, "current_executable_weight": None, "conditional_max_weight": None,
            "decision_state": "blocked", "next_gate": "修复数据或公司证据门后重新生成研报。",
            "blockers": (report or {}).get("available", {}).get("gate_failures") or ["report unavailable"],
        }

    executive = report.get("executive") or {}
    depth = report.get("research_depth")
    is_deep = report.get("research_status") == "verified" and depth == "deep"
    editorial = editorial_status(position["ticker"], db_path, snapshot_id=snapshot_id) if is_deep else {"status": "not_generated"}
    approval_current = bool((report.get("publication_approval") or {}).get("is_current"))
    stale_publication_approval = publication_status in {"approved", "published"} and not approval_current
    if stale_publication_approval:
        decision_state = "blocked"
        next_gate = "批准后的内容已变化；旧批准失效，必须重新完成整期研究门与 Park 批准。"
    elif is_deep and editorial["status"] == "approved":
        decision_state = "ready_for_park_decision"
        next_gate = "Park 复核确定性仓位条件；只有明确批准后才进入发布账本。"
    elif is_deep:
        decision_state = "narrative_review_pending"
        next_gate = "完成 DeepSeek 正文独立编辑双哈希批准；确定性研究结论已可复核。"
    else:
        decision_state = "deep_research_required"
        next_gate = "补齐公司原始资料、独立交叉来源、经营/行业/治理与正式估值研究。"
    proposed_weight = executive.get("decision_review_weight") if decision_state == "ready_for_park_decision" else None
    executable_weight = executive.get("current_executable_weight")
    return {
        "ticker": position["ticker"], "name": position["name"], "industry": position["industry"],
        "research_status": report.get("research_status"), "research_depth": depth,
        "model_score": position.get("composite_score"),
        "model_observation_weight": executive.get("model_observation_weight", position.get("target_weight")),
        "decision_review_weight": proposed_weight,
        "current_executable_weight": executable_weight,
        "conditional_max_weight": executive.get("max_target_weight"),
        "decision_state": decision_state, "next_gate": next_gate, "blockers": [],
        "editorial_status": editorial["status"],
        "editorial_integrity_errors": editorial.get("integrity_errors") or [],
        "publication_approval_current": approval_current,
        "report_hash": report.get("report_hash"),
        "evidence_set_id": (report.get("generated_from") or {}).get("evidence_set_id"),
        "stance": executive.get("stance"),
        "key_contradiction": executive.get("key_contradiction"),
    }


def validate_committee_payload(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    items = payload.get("items") or []
    metrics = payload.get("metrics") or {}
    if len(items) != 8 or len({item.get("ticker") for item in items}) != 8:
        errors.append("committee must contain exactly eight unique stocks")
    if any(item.get("current_executable_weight") is not None and item.get("research_depth") != "deep" for item in items):
        errors.append("only company-level deep research may expose executable weight")
    if any(item.get("decision_review_weight") is not None and item.get("decision_state") != "ready_for_park_decision" for item in items):
        errors.append("only decision-ready research may expose a review weight")
    if any(item.get("current_executable_weight") is not None and item.get("decision_state") != "ready_for_park_decision" for item in items):
        errors.append("only decision-ready research may expose executable weight")
    if any(
        item.get("current_executable_weight") is not None
        and item.get("conditional_max_weight") is not None
        and float(item["current_executable_weight"]) > float(item["conditional_max_weight"])
        for item in items
    ):
        errors.append("current executable weight exceeds conditional maximum")
    if _round(sum(float(item.get("model_observation_weight") or 0) for item in items)) != _round(metrics.get("model_observation_equity") or 0):
        errors.append("model observation weights do not reconcile")
    if _round(sum(float(item.get("current_executable_weight") or 0) for item in items)) != _round(metrics.get("current_executable_equity") or 0):
        errors.append("current executable weights do not reconcile")
    if _round(sum(float(item.get("decision_review_weight") or 0) for item in items)) != _round(metrics.get("decision_review_equity") or 0):
        errors.append("decision review weights do not reconcile")
    if int(metrics.get("deep_research_count") or 0) + int(metrics.get("baseline_count") or 0) + int(metrics.get("blocked_count") or 0) != len(items):
        errors.append("research readiness counts do not reconcile")
    return errors


def committee_payload(db_path: Path = DB_PATH) -> dict[str, Any]:
    dashboard = dashboard_payload(db_path)
    snapshot = dashboard["snapshot"]
    publication_status = dashboard["publication"]["status"]
    items = [_readiness_item(position, snapshot["id"], publication_status, db_path) for position in dashboard["positions"]]
    deep_count = sum(item["research_depth"] == "deep" and item["research_status"] == "verified" for item in items)
    baseline_count = sum(item["research_status"] == "baseline" for item in items)
    blocked_count = sum(item["decision_state"] == "blocked" for item in items)
    executable = _round(sum(float(item.get("current_executable_weight") or 0) for item in items))
    reviewable = _round(sum(float(item.get("decision_review_weight") or 0) for item in items))
    observation = _round(sum(float(item.get("model_observation_weight") or 0) for item in items))
    queue = []
    for item in sorted(items, key=lambda row: (row["decision_state"] != "narrative_review_pending", -(float(row.get("model_score") or 0)))):
        priority = "P0" if item["decision_state"] == "blocked" else "P1" if item["decision_state"] == "narrative_review_pending" else "P2"
        queue.append({
            "priority": priority, "ticker": item["ticker"], "name": item["name"],
            "state": item["decision_state"], "task": item["next_gate"],
        })
    top_positions = sorted(items, key=lambda row: float(row.get("model_observation_weight") or 0), reverse=True)[:3]
    payload = {
        "snapshot": {
            "id": snapshot["id"], "as_of": snapshot["as_of"], "known_at": snapshot["known_at"],
            "data_mode": snapshot["data_mode"], "quality_status": snapshot["quality_status"],
        },
        "publication": dashboard["publication"],
        "decision_status": "blocked" if blocked_count else "ready_for_park_decision" if all(item["decision_state"] == "ready_for_park_decision" for item in items) else "research_incomplete",
        "headline": (
            f"8 只股票的数据底座已就绪，但只有 {deep_count} 只完成公司级深度研究；"
            f"当前可进入 Park 决策复核的建议仓位为 {reviewable:.0f}%，已批准执行为 {executable:.0f}%；其余仍是模型观察权重。"
        ),
        "metrics": {
            "stock_count": len(items), "deep_research_count": deep_count,
            "baseline_count": baseline_count, "blocked_count": blocked_count,
            "model_observation_equity": observation,
            "decision_review_equity": reviewable,
            "current_executable_equity": executable,
            "research_pending_equity": _round(max(observation - reviewable, 0)),
            "cash_weight": _round(dashboard["allocation"]["cash"]),
        },
        "items": items,
        "research_queue": queue,
        "risk_lens": [
            {
                "title": "研究覆盖缺口",
                "detail": f"{baseline_count} 只仍是量化基线；真实数据完整不等于公司研究完成。",
                "severity": "high" if baseline_count else "low",
            },
            {
                "title": "前三大观察权重",
                "detail": "、".join(f"{item['name']} {float(item.get('model_observation_weight') or 0):.0f}%" for item in top_positions),
                "severity": "medium",
            },
            *[
                {"title": risk["title"], "detail": risk["detail"], "severity": "medium"}
                for risk in (dashboard.get("risks") or [])[:2]
            ],
        ],
        "scope": {
            "user_input": "not_in_scope_v1", "broker_connection": False,
            "position_semantics": "model observation weights remain non-executable until company research and Park approval",
        },
    }
    payload["validation_errors"] = validate_committee_payload(payload)
    if payload["validation_errors"]:
        payload["decision_status"] = "blocked"
    return payload


def portfolio_release_errors(publication_id: str, db_path: Path = DB_PATH) -> list[str]:
    """Fail closed unless the whole eight-stock research package is decision-ready."""
    payload = committee_payload(db_path)
    errors = list(payload.get("validation_errors") or [])
    if (payload.get("publication") or {}).get("id") != publication_id:
        errors.append("publication is not the current committee package")
    if payload.get("decision_status") != "ready_for_park_decision":
        errors.append("all eight stocks must complete current, approved company-level research")
    if any(item.get("decision_state") != "ready_for_park_decision" for item in payload.get("items") or []):
        errors.append("one or more stocks are not ready for Park decision")
    return sorted(set(errors))


if __name__ == "__main__":
    import json

    print(json.dumps(committee_payload(), ensure_ascii=False, indent=2, default=str))
