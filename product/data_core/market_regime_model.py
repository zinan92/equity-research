"""Deterministic, evidence-bound cross-asset market-regime compiler."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import statistics
import tempfile
from typing import Any, Iterable, Mapping

from .market_regime_data import (
    INSTRUMENT_BY_KEY,
    SCHEMA_VERSION as DATA_SCHEMA_VERSION,
    MarketRegimeDataError,
    MarketRegimeDataStore,
)


MODEL_VERSION = "market-regime-model-v1"
ANALYSIS_SCHEMA_VERSION = "market-regime-analysis-v1"
MIN_MODEL_BARS = 80
MAX_FULL_CLOSE_SKEW_HOURS = 30.0

RISK_WEIGHTS: dict[str, float] = {
    "sp500": 0.20,
    "nasdaq": 0.22,
    "shanghai": 0.11,
    "star50": 0.12,
    "kospi": 0.08,
    "nikkei": 0.08,
    "us_dividend": 0.05,
    "vix": -0.14,
}
RISK_CRITICAL = frozenset({"sp500", "nasdaq", "shanghai", "star50", "vix"})
OFFENSE_KEYS = ("nasdaq", "star50", "kospi")
DEFENSE_KEYS = ("us_dividend", "china_dividend", "gold")
STYLE_KEYS = ("nasdaq", "sp500", "star50", "shanghai", "us_dividend", "china_dividend")
LEADERSHIP_GROUPS: dict[str, tuple[str, ...]] = {
    "us_equities": ("sp500", "nasdaq"),
    "a_equities": ("shanghai", "star50"),
    "asia_ex_china": ("kospi", "nikkei"),
    "energy": ("wti",),
    "precious_metals": ("gold", "silver"),
}

LABELS_ZH = {
    "risk_on": "Risk On",
    "leaning_risk_on": "偏 Risk On",
    "mixed": "多空混合",
    "leaning_risk_off": "偏 Risk Off",
    "risk_off": "Risk Off",
    "offense": "进攻",
    "leaning_offense": "偏进攻",
    "balanced": "均衡",
    "leaning_defense": "偏防守",
    "defense": "防守",
    "technology": "科技占优",
    "leaning_technology": "偏科技",
    "style_balanced": "科技/红利均衡",
    "leaning_dividend": "偏红利",
    "dividend": "红利占优",
    "unknown": "证据不足",
}


class MarketRegimeModelError(RuntimeError):
    """Frozen input or deterministic model contract is invalid."""


@dataclass(frozen=True)
class DimensionResult:
    score: float | None
    label: str
    status: str
    confidence: dict[str, Any]
    dependencies: tuple[str, ...]
    evidence: tuple[dict[str, Any], ...]
    contradictions: tuple[dict[str, Any], ...]
    missing: tuple[str, ...] = ()

    def as_json(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "label": self.label,
            "label_zh": LABELS_ZH.get(self.label, self.label),
            "status": self.status,
            "confidence": self.confidence,
            "dependencies": list(self.dependencies),
            "evidence": list(self.evidence),
            "contradictions": list(self.contradictions),
            "missing": list(self.missing),
        }


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _clamp(value: float, low: float = -100.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _round(value: float, digits: int = 6) -> float:
    rounded = round(float(value), digits)
    return 0.0 if rounded == -0.0 else rounded


def _instant(value: str, *, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise MarketRegimeModelError(f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise MarketRegimeModelError(f"{field} must include timezone")
    return parsed.astimezone(timezone.utc)


def _return(closes: list[float], periods: int) -> float:
    if len(closes) <= periods or closes[-periods - 1] == 0:
        raise MarketRegimeModelError(f"insufficient closes for {periods}d return")
    return closes[-1] / closes[-periods - 1] - 1.0


def _realized_daily_vol(closes: list[float], periods: int) -> float:
    if len(closes) <= periods:
        raise MarketRegimeModelError(f"insufficient closes for {periods}d volatility")
    values = closes[-periods - 1 :]
    logs = [math.log(values[index] / values[index - 1]) for index in range(1, len(values))]
    return max(statistics.pstdev(logs), 0.003)


def _trend_label(score: float) -> str:
    if score >= 35:
        return "strong_up"
    if score >= 10:
        return "up"
    if score <= -35:
        return "strong_down"
    if score <= -10:
        return "down"
    return "flat"


def _artifact_hash(item: Mapping[str, Any]) -> str:
    reference = item.get("normalized_artifact") or {}
    value = str(reference.get("sha256") or "")
    if len(value) != 64:
        raise MarketRegimeModelError("instrument lacks a bound normalized artifact hash")
    return value


def _instrument_key(item: Mapping[str, Any]) -> str:
    instrument = item.get("instrument") or {}
    key = str(instrument.get("key") or "")
    if key not in INSTRUMENT_BY_KEY:
        raise MarketRegimeModelError(f"unknown instrument in snapshot: {key or 'missing'}")
    return key


def build_asset_feature(item: Mapping[str, Any]) -> dict[str, Any]:
    key = _instrument_key(item)
    if item.get("quality") not in {"fresh", "partial", "stale"}:
        raise MarketRegimeModelError(f"{key} is not usable: {item.get('quality')}")
    bars = item.get("bars") or []
    if not isinstance(bars, list) or len(bars) < MIN_MODEL_BARS:
        raise MarketRegimeModelError(f"{key} needs at least {MIN_MODEL_BARS} bars")
    closes: list[float] = []
    dates: list[str] = []
    prior_date: str | None = None
    for row in bars:
        trade_date = str(row.get("date") or "")
        if not trade_date or (prior_date is not None and trade_date <= prior_date):
            raise MarketRegimeModelError(f"{key} bars are not strictly ascending")
        try:
            close = float(row["close"])
        except (KeyError, TypeError, ValueError) as exc:
            raise MarketRegimeModelError(f"{key} has an invalid close") from exc
        if not math.isfinite(close) or (key != "wti" and close <= 0):
            raise MarketRegimeModelError(f"{key} has an invalid close")
        dates.append(trade_date)
        closes.append(close)
        prior_date = trade_date
    if any(close <= 0 for close in closes):
        raise MarketRegimeModelError(
            f"{key} contains a non-positive close unsupported by the return model"
        )
    returns = {period: _return(closes, period) for period in (1, 5, 20, 60)}
    ma20 = statistics.fmean(closes[-20:])
    ma60 = statistics.fmean(closes[-60:])
    vol20_daily = _realized_daily_vol(closes, 20)
    vol60_daily = _realized_daily_vol(closes, 60)
    z5 = returns[5] / (vol20_daily * math.sqrt(5))
    z20 = returns[20] / (vol60_daily * math.sqrt(20))
    ma20_distance = (closes[-1] / ma20 - 1.0) / (vol20_daily * math.sqrt(20))
    ma_cross = (ma20 / ma60 - 1.0) / (vol60_daily * math.sqrt(20))
    score = _clamp(
        30 * math.tanh(z5)
        + 35 * math.tanh(z20)
        + 20 * math.tanh(ma20_distance)
        + 15 * math.tanh(ma_cross)
    )
    artifact_sha = _artifact_hash(item)
    session = str(item.get("last_completed_session") or dates[-1])
    close_at = str(item.get("last_completed_close_at") or "")
    _instant(close_at, field=f"{key}.last_completed_close_at")
    return {
        "key": key,
        "display_name": INSTRUMENT_BY_KEY[key].display_name,
        "session": session,
        "close_at": close_at,
        "quality": item.get("quality"),
        "close": _round(closes[-1]),
        "returns": {f"{period}d": _round(value * 100) for period, value in returns.items()},
        "ma20": _round(ma20),
        "ma60": _round(ma60),
        "realized_volatility": {
            "20d_annualized_pct": _round(vol20_daily * math.sqrt(252) * 100),
            "60d_annualized_pct": _round(vol60_daily * math.sqrt(252) * 100),
        },
        "trend_score": _round(score, 3),
        "trend_label": _trend_label(score),
        "evidence_id": f"{key}:{session}:{artifact_sha[:16]}",
        "normalized_artifact_sha256": artifact_sha,
    }


def _confidence(*, coverage: float, coherence: float, status: str) -> dict[str, Any]:
    score = _clamp(0.6 * coverage + 0.4 * coherence, 0.0, 1.0)
    if status == "unknown":
        score = 0.0
    level = "high" if score >= 0.80 else "medium" if score >= 0.60 else "low"
    return {
        "score": _round(score, 3),
        "level": level,
        "coverage": _round(coverage, 3),
        "coherence": _round(coherence, 3),
    }


def _evidence(features: Mapping[str, Mapping[str, Any]], keys: Iterable[str]) -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "instrument": key,
            "session": features[key]["session"],
            "trend_score": features[key]["trend_score"],
            "return_20d_pct": features[key]["returns"]["20d"],
            "evidence_id": features[key]["evidence_id"],
            "normalized_artifact_sha256": features[key]["normalized_artifact_sha256"],
        }
        for key in keys
        if key in features
    )


def _risk_label(score: float) -> str:
    if score >= 30:
        return "risk_on"
    if score >= 10:
        return "leaning_risk_on"
    if score <= -30:
        return "risk_off"
    if score <= -10:
        return "leaning_risk_off"
    return "mixed"


def compile_risk(features: Mapping[str, Mapping[str, Any]]) -> DimensionResult:
    missing = tuple(key for key in RISK_WEIGHTS if key not in features)
    critical_missing = tuple(key for key in RISK_CRITICAL if key not in features)
    if critical_missing:
        return DimensionResult(
            None,
            "unknown",
            "unknown",
            _confidence(coverage=(len(RISK_WEIGHTS) - len(missing)) / len(RISK_WEIGHTS), coherence=0, status="unknown"),
            tuple(RISK_WEIGHTS),
            _evidence(features, RISK_WEIGHTS),
            (),
            missing,
        )
    available = [key for key in RISK_WEIGHTS if key in features]
    denominator = sum(abs(RISK_WEIGHTS[key]) for key in available)
    contributions = {
        key: float(features[key]["trend_score"]) * RISK_WEIGHTS[key] / denominator
        for key in available
    }
    score = _clamp(sum(contributions.values()))
    agreement = sum(
        abs(value) for value in contributions.values() if value == 0 or math.copysign(1, value) == math.copysign(1, score or 1)
    )
    total = sum(abs(value) for value in contributions.values()) or 1.0
    coherence = agreement / total
    contradictions = tuple(
        {
            "instrument": key,
            "signed_contribution": _round(value, 3),
            "trend_score": features[key]["trend_score"],
            "reason": "moves against aggregate risk score",
        }
        for key, value in contributions.items()
        if abs(value) >= 2 and score != 0 and math.copysign(1, value) != math.copysign(1, score)
    )
    status = "full" if not missing else "partial"
    return DimensionResult(
        _round(score, 3),
        _risk_label(score),
        status,
        _confidence(coverage=len(available) / len(RISK_WEIGHTS), coherence=coherence, status=status),
        tuple(RISK_WEIGHTS),
        _evidence(features, RISK_WEIGHTS),
        contradictions,
        missing,
    )


def _posture_label(score: float) -> str:
    if score >= 25:
        return "offense"
    if score >= 8:
        return "leaning_offense"
    if score <= -25:
        return "defense"
    if score <= -8:
        return "leaning_defense"
    return "balanced"


def compile_posture(features: Mapping[str, Mapping[str, Any]]) -> DimensionResult:
    offense = [key for key in OFFENSE_KEYS if key in features]
    defense = [key for key in DEFENSE_KEYS if key in features]
    dependencies = (*OFFENSE_KEYS, *DEFENSE_KEYS)
    missing = tuple(key for key in dependencies if key not in features)
    if len(offense) < 2 or len(defense) < 2:
        return DimensionResult(
            None,
            "unknown",
            "unknown",
            _confidence(coverage=(len(offense) + len(defense)) / len(dependencies), coherence=0, status="unknown"),
            dependencies,
            _evidence(features, dependencies),
            (),
            missing,
        )
    offense_score = statistics.fmean(float(features[key]["trend_score"]) for key in offense)
    defense_score = statistics.fmean(float(features[key]["trend_score"]) for key in defense)
    score = _clamp((offense_score - defense_score) / 2)
    dispersion = statistics.pstdev([float(features[key]["trend_score"]) for key in (*offense, *defense)])
    coherence = 1.0 - min(1.0, dispersion / 100)
    status = "full" if not missing else "partial"
    contradictions = tuple(
        {
            "instrument": key,
            "trend_score": features[key]["trend_score"],
            "reason": (
                "defensive asset remains strong during offensive posture"
                if score > 0
                else "offensive asset remains strong during defensive posture"
            ),
        }
        for key in (defense if score > 0 else offense)
        if abs(score) >= 8 and float(features[key]["trend_score"]) >= 15
    )
    return DimensionResult(
        _round(score, 3),
        _posture_label(score),
        status,
        _confidence(coverage=(len(offense) + len(defense)) / len(dependencies), coherence=coherence, status=status),
        dependencies,
        _evidence(features, dependencies),
        contradictions,
        missing,
    )


def _style_label(score: float) -> str:
    if score >= 20:
        return "technology"
    if score >= 7:
        return "leaning_technology"
    if score <= -20:
        return "dividend"
    if score <= -7:
        return "leaning_dividend"
    return "style_balanced"


def compile_style(features: Mapping[str, Mapping[str, Any]]) -> DimensionResult:
    missing = tuple(key for key in STYLE_KEYS if key not in features)
    if missing:
        return DimensionResult(
            None,
            "unknown",
            "unknown",
            _confidence(coverage=(len(STYLE_KEYS) - len(missing)) / len(STYLE_KEYS), coherence=0, status="unknown"),
            STYLE_KEYS,
            _evidence(features, STYLE_KEYS),
            (),
            missing,
        )
    tech_edges = (
        float(features["nasdaq"]["trend_score"]) - float(features["sp500"]["trend_score"]),
        float(features["star50"]["trend_score"]) - float(features["shanghai"]["trend_score"]),
    )
    dividend_edges = (
        float(features["us_dividend"]["trend_score"]) - float(features["sp500"]["trend_score"]),
        float(features["china_dividend"]["trend_score"]) - float(features["shanghai"]["trend_score"]),
    )
    score = _clamp((statistics.fmean(tech_edges) - statistics.fmean(dividend_edges)) / 2)
    pair_values = [*tech_edges, *dividend_edges]
    coherence = 1.0 - min(1.0, statistics.pstdev(pair_values) / 100)
    contradictions = ()
    if tech_edges[0] * tech_edges[1] < 0:
        contradictions += ({"pair": "US_vs_A_tech", "reason": "US and A-share tech relative trends disagree"},)
    if dividend_edges[0] * dividend_edges[1] < 0:
        contradictions += ({"pair": "US_vs_A_dividend", "reason": "US and A-share dividend relative trends disagree"},)
    return DimensionResult(
        _round(score, 3),
        _style_label(score),
        "full",
        _confidence(coverage=1.0, coherence=coherence, status="full"),
        STYLE_KEYS,
        _evidence(features, STYLE_KEYS),
        contradictions,
    )


def compile_leadership(features: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    ranking = []
    missing_groups = []
    for group, members in LEADERSHIP_GROUPS.items():
        if any(key not in features for key in members):
            missing_groups.append(group)
            continue
        member_scores = []
        for key in members:
            trend = float(features[key]["trend_score"])
            momentum = 100 * math.tanh(float(features[key]["returns"]["20d"]) / 12)
            member_scores.append(0.55 * trend + 0.45 * momentum)
        score = statistics.fmean(member_scores)
        ranking.append(
            {
                "group": group,
                "score": _round(score, 3),
                "members": list(members),
                "evidence": list(_evidence(features, members)),
            }
        )
    ranking.sort(key=lambda item: (-item["score"], item["group"]))
    if len(ranking) < 4:
        state, leader, gap = "unknown", None, None
        status = "unknown"
    else:
        top, second = ranking[0], ranking[1]
        gap = _round(top["score"] - second["score"], 3)
        if missing_groups:
            state, leader = "unknown", None
        elif top["score"] < 10:
            state, leader = "none", None
        elif gap < 8:
            state, leader = "contested", None
        else:
            state, leader = "leader", top["group"]
        status = "full" if not missing_groups else "partial"
    coverage = len(ranking) / len(LEADERSHIP_GROUPS)
    confidence = _confidence(
        coverage=coverage,
        coherence=0 if gap is None else min(1.0, max(0.0, gap / 30)),
        status=status,
    )
    return {
        "state": state,
        "leader": leader,
        "status": status,
        "confidence": confidence,
        "gap_to_second": gap,
        "ranking": ranking,
        "missing_groups": missing_groups,
    }


def compile_scenario(
    features: Mapping[str, Mapping[str, Any]],
    risk: DimensionResult,
    posture: DimensionResult,
    style: DimensionResult,
) -> dict[str, Any]:
    def score(key: str) -> float | None:
        return float(features[key]["trend_score"]) if key in features else None

    risk_score = risk.score
    oil, gold, vix, nasdaq = score("wti"), score("gold"), score("vix"), score("nasdaq")
    oil_return_20d = (
        float(features["wti"]["returns"]["20d"]) if "wti" in features else None
    )
    inputs = {
        "risk": risk_score,
        "wti": oil,
        "wti_return_20d_pct": oil_return_20d,
        "gold": gold,
        "vix": vix,
        "nasdaq": nasdaq,
        "posture": posture.score,
        "style": style.score,
    }
    missing = [key for key, value in inputs.items() if value is None]
    if missing:
        return {"code": "unknown", "status": "unknown", "missing": missing, "inputs": inputs}
    if (
        oil >= 35
        and oil_return_20d >= 12
        and gold >= 20
        and risk_score <= -10
    ):
        code = "supply_shock_risk_off"
    elif (
        oil >= 30
        and oil_return_20d >= 8
        and risk_score >= 10
    ):
        code = "reflation_risk_on"
    elif gold >= 30 and vix >= 20 and risk_score <= -10:
        code = "flight_to_safety"
    elif (
        nasdaq >= 25
        and risk_score >= 15
        and posture.score > -8
        and style.score >= 7
    ):
        code = "growth_led_risk_on"
    elif risk_score <= -15:
        code = "broad_deleveraging"
    else:
        code = "cross_asset_rotation"
    return {
        "code": code,
        "status": "full",
        "missing": [],
        "inputs": inputs,
    }


def _input_fingerprint(snapshot: Mapping[str, Any], items: Iterable[Mapping[str, Any]]) -> str:
    identity = {
        "data_schema_version": snapshot.get("schema_version"),
        "run_id": snapshot.get("run_id"),
        "generated_at": snapshot.get("generated_at"),
        "quality": snapshot.get("quality"),
        "artifacts": sorted(
            (
                {
                    "key": _instrument_key(item),
                    "sha256": _artifact_hash(item),
                    "session": item.get("last_completed_session"),
                    "close_at": item.get("last_completed_close_at"),
                    "quality": item.get("quality"),
                    "data_kind": item.get("data_kind"),
                }
                for item in items
                if item.get("quality") in {"fresh", "partial", "stale"}
            ),
            key=lambda row: row["key"],
        ),
    }
    return sha256(_canonical_json(identity).encode("utf-8")).hexdigest()


def _explanation(
    risk: DimensionResult,
    posture: DimensionResult,
    style: DimensionResult,
    leadership: Mapping[str, Any],
    scenario: Mapping[str, Any],
) -> dict[str, Any]:
    risk_text = LABELS_ZH.get(risk.label, risk.label)
    posture_text = LABELS_ZH.get(posture.label, posture.label)
    style_text = LABELS_ZH.get(style.label, style.label)
    leader = leadership.get("leader")
    leadership_text = (
        f"{leader} 领先，领先第二名 {leadership.get('gap_to_second')} 分"
        if leader
        else "领导权不明确" if leadership.get("state") in {"contested", "none"} else "领导力证据不足"
    )
    confirmation = (
        f"风险总分 {risk.score}，当前状态为 {risk_text}。"
        if risk.score is not None
        else "Risk 维度缺少关键依赖，不能给出完整 Risk On/Off 结论。"
    )
    rotation = f"内部结构为{posture_text}、{style_text}；{leadership_text}。"
    contradictions = [*risk.contradictions, *posture.contradictions, *style.contradictions]
    incomplete = any(
        status != "full"
        for status in (risk.status, posture.status, style.status, leadership.get("status"))
    )
    reason_zh = {
        "moves against aggregate risk score": "与整体风险方向相反",
        "defensive asset remains strong during offensive posture": "进攻姿态中防守资产仍偏强",
        "offensive asset remains strong during defensive posture": "防守姿态中进攻资产仍偏强",
        "US and A-share tech relative trends disagree": "美股与 A 股科技相对趋势不一致",
        "US and A-share dividend relative trends disagree": "美股与 A 股红利相对趋势不一致",
    }
    if contradictions:
        first = contradictions[0]
        subject = first.get("instrument") or first.get("pair")
        divergence = f"主要背离：{subject} — {reason_zh.get(first['reason'], first['reason'])}。"
    elif incomplete:
        divergence = "关键维度证据尚不完整，当前不能据此确认市场不存在方向性背离。"
    else:
        divergence = "主要资产暂未出现足以推翻主结论的方向性背离。"
    if risk.status == "unknown":
        invalidation = (
            f"观察条件：先补齐 Risk 关键依赖（{', '.join(risk.missing)}），在此之前不建立可失效的主方向。"
        )
    elif risk.label == "mixed":
        invalidation = (
            "观察条件：当前本就处于多空混合；只有 Risk 分数突破 ±10 且领导组领先差距达到 8 分，才升级为方向性状态。"
        )
    elif leadership.get("state") in {"contested", "none", "unknown"}:
        invalidation = (
            "失效观察：Risk 分数回到 -10 到 +10 会推翻当前风险方向；领导权尚未确立，领先差距达到 8 分前不确认主线。"
        )
    else:
        invalidation = (
            "失效观察：Risk 分数回到 -10 到 +10，或领导组领先差距跌破 8 分时，应把当前方向降为混合/争夺。"
        )
    return {
        "headline": f"{risk_text} · {posture_text} · {style_text}",
        "confirmation": confirmation,
        "rotation": rotation,
        "divergence": divergence,
        "invalidation": invalidation,
        "scenario_code": scenario["code"],
    }


def compile_market_regime(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    if snapshot.get("schema_version") != DATA_SCHEMA_VERSION:
        raise MarketRegimeModelError("market-regime data schema mismatch")
    raw_items = snapshot.get("instruments") or []
    if not isinstance(raw_items, list):
        raise MarketRegimeModelError("snapshot instruments must be a list")
    usable_items = [
        item for item in raw_items
        if isinstance(item, dict) and item.get("quality") in {"fresh", "partial", "stale"}
    ]
    data_kinds = sorted({str(item.get("data_kind") or "unknown") for item in usable_items})
    input_data_kind = data_kinds[0] if len(data_kinds) == 1 else "mixed" if data_kinds else "unknown"
    features: dict[str, dict[str, Any]] = {}
    rejected: dict[str, str] = {}
    for item in usable_items:
        try:
            feature = build_asset_feature(item)
        except MarketRegimeModelError as exc:
            try:
                key = _instrument_key(item)
            except MarketRegimeModelError:
                key = "unknown"
            rejected[key] = str(exc)
            continue
        if feature["key"] in features:
            raise MarketRegimeModelError(f"duplicate instrument: {feature['key']}")
        features[feature["key"]] = feature
    risk = compile_risk(features)
    posture = compile_posture(features)
    style = compile_style(features)
    leadership = compile_leadership(features)
    scenario = compile_scenario(features, risk, posture, style)
    close_times = [_instant(item["close_at"], field=f"{key}.close_at") for key, item in features.items()]
    if close_times:
        earliest, latest = min(close_times), max(close_times)
        close_skew = (latest - earliest).total_seconds() / 3600
        verdict_as_of = earliest.isoformat().replace("+00:00", "Z")
        latest_evidence_at = latest.isoformat().replace("+00:00", "Z")
    else:
        close_skew, verdict_as_of, latest_evidence_at = None, None, None
    dimension_statuses = [risk.status, posture.status, style.status, leadership["status"]]
    if all(status == "unknown" for status in dimension_statuses):
        overall_status = "unknown"
    elif (
        snapshot.get("quality") == "fresh"
        and all(status == "full" for status in dimension_statuses)
        and close_skew is not None
        and close_skew <= MAX_FULL_CLOSE_SKEW_HOURS
    ):
        overall_status = "full"
    else:
        overall_status = "partial"
    confidence_values = [
        risk.confidence["score"],
        posture.confidence["score"],
        style.confidence["score"],
        leadership["confidence"]["score"],
    ]
    confidence_score = statistics.fmean(confidence_values)
    if close_skew is None or close_skew > MAX_FULL_CLOSE_SKEW_HOURS:
        confidence_score *= 0.75
    confidence_score = _round(confidence_score, 3)
    confidence_level = "high" if confidence_score >= 0.8 else "medium" if confidence_score >= 0.6 else "low"
    input_fingerprint = _input_fingerprint(snapshot, usable_items)
    analysis_identity = sha256(f"{MODEL_VERSION}:{input_fingerprint}".encode("utf-8")).hexdigest()
    result = {
        "schema_version": ANALYSIS_SCHEMA_VERSION,
        "model_version": MODEL_VERSION,
        "analysis_id": f"market-regime-analysis:{analysis_identity}",
        "input_fingerprint": input_fingerprint,
        "source_run_id": snapshot.get("run_id"),
        "data_kind": input_data_kind,
        "generated_at": snapshot.get("generated_at"),
        "verdict_as_of": verdict_as_of,
        "latest_evidence_at": latest_evidence_at,
        "cross_market_close_skew_hours": _round(close_skew, 3) if close_skew is not None else None,
        "status": overall_status,
        "confidence": {"score": confidence_score, "level": confidence_level},
        "dimensions": {
            "risk": risk.as_json(),
            "posture": posture.as_json(),
            "style": style.as_json(),
            "leadership": leadership,
        },
        "scenario": scenario,
        "what_is_going_on": _explanation(risk, posture, style, leadership, scenario),
        "asset_features": [features[key] for key in sorted(features)],
        "rejected_inputs": rejected,
        "truth_boundary": {
            "judgment_state": "model_generated_unreviewed",
            "read_only": True,
            "investment_advice": False,
            "not_investment_advice": True,
            "action_eligible": False,
            "publication_eligible": False,
        },
    }
    return result


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (_canonical_json(value) + "\n").encode("utf-8")


def _write_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(_json_bytes(payload))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _write_immutable(path: Path, payload: Mapping[str, Any]) -> str:
    encoded = _json_bytes(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = path.read_bytes()
        if existing != encoded:
            raise MarketRegimeModelError(f"analysis artifact identity collision: {path.name}")
        return sha256(existing).hexdigest()
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
    return sha256(encoded).hexdigest()


class MarketRegimeAnalysisStore:
    """Compile and persist an immutable analysis without mutating M1 evidence."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).expanduser().resolve()

    def compile_latest(self) -> dict[str, Any]:
        try:
            snapshot = MarketRegimeDataStore(self.root).latest()
        except MarketRegimeDataError as exc:
            raise MarketRegimeModelError(str(exc)) from exc
        analysis = compile_market_regime(snapshot)
        relative = f"analysis/artifacts/{analysis['analysis_id'].split(':', 1)[1]}.json"
        artifact_hash = _write_immutable(self.root / relative, analysis)
        pointer = {
            "schema_version": ANALYSIS_SCHEMA_VERSION,
            "analysis_id": analysis["analysis_id"],
            "input_fingerprint": analysis["input_fingerprint"],
            "artifact": {"path": relative, "sha256": artifact_hash},
        }
        _write_atomic(self.root / "analysis" / "latest.json", pointer)
        return analysis

    def latest(self) -> dict[str, Any]:
        pointer_path = self.root / "analysis" / "latest.json"
        try:
            pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise MarketRegimeModelError("market-regime analysis is unavailable") from exc
        except json.JSONDecodeError as exc:
            raise MarketRegimeModelError("market-regime analysis pointer is not JSON") from exc
        if not isinstance(pointer, dict) or pointer.get("schema_version") != ANALYSIS_SCHEMA_VERSION:
            raise MarketRegimeModelError("market-regime analysis pointer schema mismatch")
        reference = pointer.get("artifact")
        if not isinstance(reference, dict):
            raise MarketRegimeModelError("market-regime analysis reference is incomplete")
        relative = str(reference.get("path") or "")
        expected_hash = str(reference.get("sha256") or "")
        if not relative.startswith("analysis/artifacts/") or len(expected_hash) != 64:
            raise MarketRegimeModelError("market-regime analysis reference is incomplete")
        target = (self.root / relative).resolve()
        if self.root not in target.parents:
            raise MarketRegimeModelError("market-regime analysis path escapes runtime root")
        try:
            encoded = target.read_bytes()
        except FileNotFoundError as exc:
            raise MarketRegimeModelError("market-regime analysis artifact is missing") from exc
        if sha256(encoded).hexdigest() != expected_hash:
            raise MarketRegimeModelError("market-regime analysis artifact hash mismatch")
        try:
            analysis = json.loads(encoded)
        except json.JSONDecodeError as exc:
            raise MarketRegimeModelError("market-regime analysis artifact is not JSON") from exc
        if (
            not isinstance(analysis, dict)
            or analysis.get("schema_version") != ANALYSIS_SCHEMA_VERSION
            or analysis.get("model_version") != MODEL_VERSION
            or analysis.get("analysis_id") != pointer.get("analysis_id")
            or analysis.get("input_fingerprint") != pointer.get("input_fingerprint")
        ):
            raise MarketRegimeModelError("market-regime analysis pointer identity mismatch")
        expected_identity = sha256(
            f"{MODEL_VERSION}:{analysis['input_fingerprint']}".encode("utf-8")
        ).hexdigest()
        if (
            analysis["analysis_id"] != f"market-regime-analysis:{expected_identity}"
            or relative != f"analysis/artifacts/{expected_identity}.json"
        ):
            raise MarketRegimeModelError("market-regime analysis identity is invalid")
        return analysis
