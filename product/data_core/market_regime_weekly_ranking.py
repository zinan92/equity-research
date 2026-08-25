"""Late Stage-B opportunity ordering for Weekly Macro asset analyses."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Callable, Mapping

from .market_regime_weekly_source import WEEKLY_KEYS
from .market_regime_llm_provider import ProviderFallbackError


SCHEMA_VERSION = "market-regime-weekly-ranking-v1"
RANKING_ID_PREFIX = "market-regime-weekly-ranking:"
RANKING_STATES = frozenset({"participate", "wait", "avoid"})


class WeeklyRankingError(ValueError):
    """Ranking request/output violated the late Stage-B contract."""


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _safe_provider_receipt(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    allowed = (
        "provider",
        "model",
        "cli_version",
        "attempt_count",
        "fallback_used",
        "fallback_reason",
        "primary_provider",
        "primary_failure",
        "request_hash",
        "output_hash",
        "validation_result",
    )
    return {key: value[key] for key in allowed if key in value and isinstance(value[key], (str, int, float, bool, type(None)))}


def build_ranking_request(terminal_vector: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Project only the validated/typed terminal vector into Stage B."""

    if len(terminal_vector) != len(WEEKLY_KEYS):
        raise WeeklyRankingError("ranking_terminal_vector_length_invalid")
    if [item.get("asset_key") for item in terminal_vector] != list(WEEKLY_KEYS):
        raise WeeklyRankingError("ranking_terminal_vector_order_invalid")
    slots: list[dict[str, Any]] = []
    for slot in terminal_vector:
        key = str(slot.get("asset_key") or "")
        status = str(slot.get("status") or "")
        if status == "analysis_unavailable":
            slots.append({"asset_key": key, "status": status, "reason_code": str(slot.get("reason_code") or "analysis_unavailable")})
            continue
        if status != "validated" or not isinstance(slot.get("output"), Mapping):
            raise WeeklyRankingError(f"ranking_terminal_slot_invalid:{key}")
        output = slot["output"]
        evidence_ids: list[str] = []
        for name in ("synthesis", "confirmation", "invalidation", "rationale"):
            row = output.get(name)
            if isinstance(row, Mapping):
                evidence_ids.extend(str(item) for item in row.get("evidence_ids") or [])
        analysis_id = str(slot.get("analysis_id") or "")
        if not analysis_id:
            raise WeeklyRankingError(f"ranking_analysis_id_missing:{key}")
        slots.append(
            {
                "asset_key": key,
                "status": "validated",
                "analysis_id": analysis_id,
                "agreement": output.get("agreement"),
                "opportunity_state": output.get("opportunity_state"),
                "synthesis": output.get("synthesis"),
                "confirmation": output.get("confirmation"),
                "invalidation": output.get("invalidation"),
                "rationale": output.get("rationale"),
                "evidence_ids": sorted(set(evidence_ids)),
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "asset_keys": list(WEEKLY_KEYS),
        "slots": slots,
        "truth_boundary": {
            "cross_asset_causal_claims": False,
            "direct_fund_flow_claims": False,
            "automatic_execution_eligible": False,
            "broker_access": False,
            "portfolio_mutation": False,
        },
    }


def _statement(row: Any, *, allowed_ids: set[str], required: bool = True) -> dict[str, Any]:
    if not isinstance(row, Mapping) or not isinstance(row.get("text"), str) or not row["text"].strip():
        if required:
            raise WeeklyRankingError("ranking_statement_invalid")
        return {"text": "", "evidence_ids": []}
    ids = row.get("evidence_ids")
    if not isinstance(ids, list) or any(item not in allowed_ids for item in ids):
        raise WeeklyRankingError("ranking_evidence_unknown")
    if required and not ids:
        raise WeeklyRankingError("ranking_evidence_missing")
    return {"text": row["text"], "evidence_ids": list(ids)}


def validate_ranking_output(output: Mapping[str, Any], request: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(output, Mapping):
        raise WeeklyRankingError("ranking_output_invalid")
    if output.get("generation_status") == "ranking_unavailable":
        if not isinstance(output.get("failure_code"), str) or not output["failure_code"]:
            raise WeeklyRankingError("ranking_failure_code_missing")
        return {"generation_status": "ranking_unavailable", "failure_code": output["failure_code"]}
    if output.get("generation_status") != "model_generated_unreviewed":
        raise WeeklyRankingError("ranking_generation_status_invalid")
    slots = request.get("slots")
    if not isinstance(slots, list) or len(slots) != len(WEEKLY_KEYS):
        raise WeeklyRankingError("ranking_request_invalid")
    allowed_ids: set[str] = set()
    for slot in slots:
        if slot.get("status") == "validated":
            allowed_ids.add(str(slot["analysis_id"]))
            allowed_ids.update(str(item) for item in slot.get("evidence_ids") or [])
    changes = output.get("important_changes") or []
    if not isinstance(changes, list) or len(changes) > 3:
        raise WeeklyRankingError("ranking_important_changes_invalid")
    validated_changes = [_statement(item, allowed_ids=allowed_ids) for item in changes]
    rows = output.get("ordered_assets")
    if not isinstance(rows, list) or len(rows) != len(WEEKLY_KEYS):
        raise WeeklyRankingError("ranking_order_length_invalid")
    by_key = {str(item.get("asset_key") or ""): item for item in rows}
    if set(by_key) != set(WEEKLY_KEYS) or len(by_key) != len(WEEKLY_KEYS):
        raise WeeklyRankingError("ranking_asset_set_invalid")
    expected_ranks: list[int] = []
    validated_rows: list[dict[str, Any]] = []
    for slot in slots:
        key = str(slot["asset_key"])
        row = by_key[key]
        if slot["status"] == "analysis_unavailable":
            if row.get("status") != "unavailable" or row.get("rank") is not None or row.get("evidence_ids"):
                raise WeeklyRankingError(f"ranking_unavailable_slot_invalid:{key}")
            validated_rows.append({"asset_key": key, "status": "unavailable", "rank": None, "text": str(row.get("text") or "数据不可用"), "evidence_ids": []})
            continue
        state = str(row.get("status") or "")
        rank = row.get("rank")
        if state not in RANKING_STATES or not isinstance(rank, int) or rank < 1:
            raise WeeklyRankingError("ranking_order_invalid")
        expected_ranks.append(rank)
        validated_rows.append({
            "asset_key": key,
            "status": state,
            "rank": rank,
            **_statement(row, allowed_ids=allowed_ids),
        })
    if sorted(expected_ranks) != list(range(1, len(expected_ranks) + 1)):
        raise WeeklyRankingError("ranking_order_invalid")
    return {"generation_status": "model_generated_unreviewed", "important_changes": validated_changes, "ordered_assets": validated_rows}


def compile_ranking(
    request: Mapping[str, Any],
    provider: Callable[[Mapping[str, Any]], Mapping[str, Any]],
) -> dict[str, Any]:
    request_hash = _digest(request)
    provider_receipt: dict[str, Any] = {}
    try:
        raw_result = provider(request)
        if isinstance(raw_result, tuple) and len(raw_result) == 2:
            raw, receipt = raw_result
            provider_receipt = _safe_provider_receipt(receipt)
        else:
            raw = raw_result
        output = validate_ranking_output(raw, request)
    except ProviderFallbackError as exc:
        return {
            "schema_version": SCHEMA_VERSION,
            "request_hash": request_hash,
            "generation_status": "ranking_unavailable",
            "failure_code": exc.code,
            "provider_status": {
                "primary_provider": "DeepSeek",
                "primary_failure": exc.primary_failure,
                "fallback_provider": "Codex CLI",
                "fallback_failure": exc.fallback_failure,
                "both_failed": True,
            },
            "ordered_assets": [],
            "important_changes": [],
        }
    except WeeklyRankingError:
        return {"schema_version": SCHEMA_VERSION, "request_hash": request_hash, "generation_status": "ranking_unavailable", "failure_code": "output_schema_invalid"}
    except Exception:
        return {"schema_version": SCHEMA_VERSION, "request_hash": request_hash, "generation_status": "ranking_unavailable", "failure_code": "provider_error"}
    core = {"schema_version": SCHEMA_VERSION, "request_hash": request_hash, "output": output}
    output_hash = _digest(output)
    ranking_id = f"{RANKING_ID_PREFIX}{_digest(core)}"
    return {
        "ranking_id": ranking_id,
        "identity_core": core,
        "request_hash": request_hash,
        "generation_status": output["generation_status"],
        "output_hash": output_hash,
        "important_changes": output["important_changes"],
        "ordered_assets": output["ordered_assets"],
        "receipt": {"schema_version": SCHEMA_VERSION, "event": "completed", "ranking_id": ranking_id, "request_hash": request_hash, "output_hash": output_hash, "provider": provider_receipt},
    }
