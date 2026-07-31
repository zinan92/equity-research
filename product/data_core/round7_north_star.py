"""Frozen product north star for the accepted Round 7 research dossier."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROUND7_NORTH_STAR_VERSION = "round7-north-star-v1"
ROUND7_STRUCTURE_SIGNATURE = (
    "1c25130d38341372cbd96308c57e48553175764178e2e38c6ac645852f975ea5"
)
ROUND7_CANONICAL_DOSSIER_SHA256 = (
    "5c1c8d9eb2f138925c8218ac9e0cd8ce2869bbb811a812e39bbfd339ef709d0e"
)
ROUND7_LEGACY_BLIND_STRUCTURE_SIGNATURE = (
    "bb6e0c1399cb75c4433eb0692168dfa90aaaff7ef1b0eb57788b1091ed7e0add"
)
ROUND7_TEMPLATE_SHA256 = (
    "4b6ef701fc7cf2e68936d19ec84588e275023b0f7498f892e0a667c505053462"
)
ROUND7_EXTERNAL_RECEIPT_SHA256 = (
    "41c7ee835c5113ba52751d8d9fe0af7c447acc5a1d90c27870dc3af25792a666"
)
ROUND7_PARK_RECEIPT_SHA256 = (
    "52a22168bace013fc5b674fc4f447ddde895fdd996c21d46ea64a7b4da96d819"
)
ROUND7_BLIND_PACK_SHA256 = (
    "28aab8c17464ad94368f3356550c09a6ebdf49ad98e05ba05ca626b59ad1ea04"
)
SAFETY_SOURCE_SHA256 = {
    "product/data_core/research_degradation.py": (
        "98fc7820019a9f10b91d4533c17de38f4db9b178e3d33c1e5ed57ce98890fed1"
    ),
    "product/data_core/evidence_gate.py": (
        "bddf93d9268633532efce4ba3ae9b5069217f08ba5d8353e846bf452ef28e805"
    ),
    "product/data_core/decision_policy.py": (
        "34ace569be831712af1bd1c3cf7bdd42ba2c63a6e3b19935c29058a02e28f4b9"
    ),
}
ROUND7_BLIND_TICKERS = (
    "002371.SZ",
    "002594.SZ",
    "300308.SZ",
    "300502.SZ",
    "NVDA",
)
ROUND7_BLIND_SAMPLE_SHA256 = {
    "002371.SZ": (
        "6bbedaf6b0ffa2ad778ff26ef222d9ad3ab59ced3fa91cbdf98402e8fa7272c5"
    ),
    "002594.SZ": (
        "09680c98837ab4d55a4dff59baf000343b726b678445caf10a0b294778c9853e"
    ),
    "300308.SZ": (
        "00ecc86ae35e03ba7b9a82c4ce2810f0186f980d738fb75124c019a6a160b3e2"
    ),
    "300502.SZ": (
        "54d426f40f8a543997e63efa9633c08d669224b79aa515ed50c831e97b0d0319"
    ),
    "NVDA": (
        "6f1b6718986332c5321b8e65f9c6a39c2d815ca101f3768953f74bb3fe49be1e"
    ),
}
ROUND7_REPLAY_SHA256 = (
    "af70a072afb670d78abc76b4b326a1714de43e196ae8ce0e2271d7cb40f57534"
)
ROUND7_READER_UNITS = (
    "one_line_positioning",
    "identity_founder_and_governance",
    "technology_origin_and_development_history",
    "business_model_and_business_lines",
    "financial_and_operating_time_series",
    "moat_evidence_chain",
    "risks_counter_thesis_and_triggers",
    "research_conclusion_and_open_questions",
    "production_record",
)
ROUND7_REQUIRED_HEADINGS = (
    "## 1. 一句话定位",
    "## 2. 身份、创始人与治理",
    "## 3. 技术来源与发展史",
    "## 4. 商业模式与业务线",
    "## 5. 财务与经营时间序列",
    "## 6. 护城河的证据链",
    "## 7. 风险、反题材与观察触发器",
    "## 8. 研究结论与待补问题",
    "## 9. 生产记录",
    "## Sources",
)
ROUND7_QUALITY_GATES = {
    "evidence_boundary_present": True,
    "page_citation_trace_rate": 1.0,
    "numeric_trace_rate": 1.0,
    "name_swap_specificity_rate": 1.0,
    "concrete_sentence_rate": 1.0,
    "uncited_factual_sentences": 0,
    "cross_company_leakage": 0,
    "ticker_specific_generator_branches": 0,
    "minimum_falsifiers": 1,
    "minimum_typed_gaps": 1,
    "target_body_characters": (4000, 5500),
}

_TABLE_DIVIDER = re.compile(r"^\|(?:\s*:?-+:?\s*\|)+$")
_SOURCE_ROW = re.compile(r"^\| S-\d+ \|")
_NUMBER = re.compile(r"\d")
_SOURCE_CITATION = re.compile(r"\[S-\d+\]")
_FALSIFIER_MARKERS = ("证伪", "推翻", "下调", "不成立", "明显恶化")
_GAP_MARKERS = (
    "待补",
    "待核验",
    "未验证",
    "尚未",
    "没有证明",
    "不能确认",
    "没有披露",
    "没有单独",
    "缺少",
    "未知",
)


@dataclass(frozen=True)
class NorthStarCheck:
    path: str
    structure_signature: str
    body_characters: int
    source_rows: int
    fact_ids: int
    problems: tuple[str, ...]


def structure_signature(text: str) -> str:
    structural_lines = [
        line.strip()
        for line in text.splitlines()
        if line.startswith("## ") or _TABLE_DIVIDER.match(line)
    ]
    return hashlib.sha256("\n".join(structural_lines).encode()).hexdigest()


def verify_round7_document(path: Path) -> NorthStarCheck:
    text = path.read_text(encoding="utf-8")
    problems: list[str] = []
    positions = []
    for heading in ROUND7_REQUIRED_HEADINGS:
        position = text.find(heading)
        if position < 0:
            problems.append("missing heading: " + heading)
        positions.append(position)
    if all(position >= 0 for position in positions) and positions != sorted(positions):
        problems.append("Round 7 heading order changed")
    if "[F-" not in text:
        problems.append("missing fact identities")
    if "[S-" not in text:
        problems.append("missing source citations")
    source_rows = sum(_SOURCE_ROW.match(line) is not None for line in text.splitlines())
    if source_rows < 2:
        problems.append("fewer than two source rows")
    source_lines = [
        line for line in text.splitlines() if _SOURCE_ROW.match(line)
    ]
    if any("https://" not in line for line in source_lines):
        problems.append("source row without HTTPS URL")
    body = text.split("---", 2)[-1].strip()
    reader_content = "\n".join(
        line
        for line in body.splitlines()
        if not line.lstrip().startswith("#")
    )
    minimum = int(ROUND7_QUALITY_GATES["target_body_characters"][0])
    if len(body) < minimum:
        problems.append("body shorter than Round 7 minimum")
    if not any(marker in reader_content for marker in _FALSIFIER_MARKERS):
        problems.append("missing falsifier")
    if not any(marker in reader_content for marker in _GAP_MARKERS):
        problems.append("missing typed evidence gap")
    in_reader = False
    for line_number, line in enumerate(text.splitlines(), start=1):
        if line == "## 1. 一句话定位":
            in_reader = True
        elif line == "## 9. 生产记录":
            in_reader = False
        if (
            in_reader
            and _NUMBER.search(line)
            and not line.startswith("#")
            and not _TABLE_DIVIDER.match(line)
            and not _SOURCE_CITATION.search(line)
        ):
            problems.append(
                "numeric factual line lacks source citation at line "
                + str(line_number)
            )
    signature = structure_signature(text)
    if signature != ROUND7_STRUCTURE_SIGNATURE:
        problems.append("structure signature differs from accepted Round 7")
    return NorthStarCheck(
        path=str(path),
        structure_signature=signature,
        body_characters=len(body),
        source_rows=source_rows,
        fact_ids=len(set(re.findall(r"\[F-\d+\]", text))),
        problems=tuple(problems),
    )


def verify_blind_set(paths: Iterable[Path]) -> tuple[NorthStarCheck, ...]:
    checks = tuple(verify_round7_document(path) for path in paths)
    if len(checks) != len(ROUND7_BLIND_TICKERS):
        raise ValueError("Round 7 blind set cardinality changed")
    if any(check.problems for check in checks):
        raise ValueError("Round 7 blind set no longer matches the north star")
    return checks
