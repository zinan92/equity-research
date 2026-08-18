"""DeepSeek providers for isolated Weekly asset and late-ranking calls."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any, Mapping


ASSET_SYSTEM_PROMPT = """你是宏观 K 线周报的单资产分析师。你只分析用户 JSON 中的一个资产，不能引用任何外部事实，不能读取别的资产，也不能补造数字。

请分别解释 weekly、daily，以及请求中存在的 four_hour。周线重点是位置和上一根 K 线方向；日线重点是结构和位置；4H 是上下文结构。每段必须引用该请求里的 evidence_ids。最后给出一个多周期结论、确认条件、失效条件和市场层面的 opportunity_state。

只返回合法 JSON，不要 Markdown。字段必须严格是：
{"asset_key":"string","generation_status":"model_generated_unreviewed","weekly":{"text":"string","evidence_ids":["..."]},"daily":{"text":"string","evidence_ids":["..."]},"synthesis":{"text":"string","evidence_ids":["..."]},"agreement":"aligned_bullish|aligned_bearish|mixed|neutral","confirmation":{"text":"string","evidence_ids":["..."]},"invalidation":{"text":"string","evidence_ids":["..."]},"opportunity_state":"participate|wait|avoid","rationale":{"text":"string","evidence_ids":["..."]},"four_hour":{"text":"string","evidence_ids":["..."]}}
如果请求没有 four_hour，省略该字段，并且所有文字中都不得出现 4H、4小时或任何未提供的小时级分析。禁止输出个人持仓、仓位比例、经纪订单或保证收益。
"""


RANKING_SYSTEM_PROMPT = """你是宏观 K 线周报的末尾排序编辑。输入只包含 17 个资产已经完成的独立分析，不能读取原始 OHLC，不能新增外部事实，也不能把排序提前影响资产分析。

请输出 17 个资产的完整顺序；analysis_unavailable 必须原样保留为 unavailable 且不占排名。important_changes 最多三项，每项引用输入中的 analysis_id 或 evidence_ids。只返回合法 JSON：
{"generation_status":"model_generated_unreviewed","important_changes":[{"text":"string","evidence_ids":["..."]}],"ordered_assets":[{"asset_key":"string","status":"participate|wait|avoid|unavailable","rank":1,"text":"string","evidence_ids":["..."]}]}
禁止输出个人仓位、订单或收益预测。
"""


ALLOWED_LATIN_WORDS = frozenset({"Nasdaq", "Bitcoin", "Nikkei", "KOSPI", "SCHD", "OHLC"})


def _has_forbidden_english(value: Mapping[str, Any]) -> bool:
    texts = [str(item.get("text", "")) for item in value.values() if isinstance(item, Mapping) and isinstance(item.get("text"), str)]
    words = re.findall(r"[A-Za-z]{4,}", " ".join(texts))
    return any(word not in ALLOWED_LATIN_WORDS for word in words)


class DeepSeekWeeklyAssetProvider:
    provider_name = "DeepSeek"

    def __init__(self, key_file: Path | str, *, model: str = "deepseek-v4-flash") -> None:
        self.key_file = Path(key_file).expanduser().resolve()
        self.model = model

    def __call__(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        from deepseek_writer import call_structured_deepseek

        no_four_hour = "four_hour" not in (request.get("timeframes") or {})
        prompt = ASSET_SYSTEM_PROMPT
        prompt += "\n所有 text 字段必须使用简体中文；只能保留资产官方符号或名称 Nasdaq、Bitcoin、Nikkei、KOSPI、SCHD、OHLC，不能写英文句子。"
        if no_four_hour:
            prompt += "\n本次请求没有 four_hour。输出 JSON 中绝对不能有 four_hour 字段，任何文字也不能出现 4H、4小时或小时级走势；只讨论周线和日线。"
        output: Mapping[str, Any] = {}
        for attempt in range(2):
            output, _receipt = call_structured_deepseek(
                system_prompt=prompt,
                request_object=request,
                key_file=self.key_file,
                model=self.model,
                max_tokens=3200,
                reasoning_effort="low",
                temperature=0.1,
                thinking_type="disabled",
            )
            if not no_four_hour and not _has_forbidden_english(output):
                return output
            text = " ".join(str(value) for value in output.values() if isinstance(value, str) or isinstance(value, Mapping))
            if (not no_four_hour or not any(token in text.lower() for token in ("4h", "4小时", "小时"))) and not _has_forbidden_english(output):
                break
            prompt += "\n上一次输出违反了语言或时间周期边界。请重写：所有 text 必须为简体中文，不得写英文句子；若请求没有 four_hour，也不得提及任何小时或 4H。"
        # The request is authoritative: cash/rate assets have no 4H field.
        if no_four_hour and isinstance(output, dict):
            output = {key: value for key, value in output.items() if key != "four_hour"}
        return output


class DeepSeekWeeklyRankingProvider:
    provider_name = "DeepSeek"

    def __init__(self, key_file: Path | str, *, model: str = "deepseek-v4-flash") -> None:
        self.key_file = Path(key_file).expanduser().resolve()
        self.model = model

    def __call__(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        from deepseek_writer import call_structured_deepseek

        output, _receipt = call_structured_deepseek(
            system_prompt=RANKING_SYSTEM_PROMPT,
            request_object=request,
            key_file=self.key_file,
            model=self.model,
            max_tokens=6000,
            reasoning_effort="low",
            temperature=0.1,
            thinking_type="disabled",
        )
        return output
