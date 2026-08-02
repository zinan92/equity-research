"""Reader-facing V4 dossier contract.

The V4 contract is the production-facing name for the Round 7 dossier that
Park approved. It deliberately describes a document (chapters and evidence
markers), rather than the legacy field-by-field report model. Generation is
not implemented here; this module only validates a completed Markdown
dossier before a later compiler is allowed to consume it.
"""
from __future__ import annotations

from dataclasses import dataclass
import re


V4_SCHEMA_VERSION = "park-v4-dossier-v1"
V4_HEADINGS: tuple[str, ...] = (
    "一句话定位",
    "产业坐标",
    "创始人与团队",
    "发展时间线",
    "技术、产品与商业模式",
    "财务与估值",
    "风险与点评",
    "生产记录",
)


@dataclass(frozen=True)
class V4SectionSpec:
    number: int
    heading: str
    target_chars: int
    minimum_chars: int
    required_phrases: tuple[str, ...]
    evidence_source: str


V4_SECTION_SPECS: tuple[V4SectionSpec, ...] = (
    V4SectionSpec(1, "一句话定位", 360, 80, ("研究判断",), "issuer facts + industry evidence"),
    V4SectionSpec(2, "产业坐标", 520, 120, ("产业链位置", "大白话逻辑链"), "issuer + industry evidence"),
    V4SectionSpec(3, "创始人与团队", 360, 100, ("治理",), "issuer governance disclosure"),
    V4SectionSpec(4, "发展时间线", 620, 160, ("年",), "issuer history/technology disclosure"),
    V4SectionSpec(5, "技术、产品与商业模式", 760, 220, ("收入", "客户"), "issuer business disclosure"),
    V4SectionSpec(6, "财务与估值", 760, 240, ("收入", "利润"), "page-level financial facts"),
    V4SectionSpec(7, "风险与点评", 820, 260, ("核心风险", "大白话点评"), "facts + falsifiers"),
    V4SectionSpec(9, "生产记录", 300, 100, ("运行 ID", "复跑策略"), "immutable production receipt"),
)

_HEADING_RE = re.compile(r"^##\s+(?:(\d+)\.\s*)?(.+?)\s*$", re.MULTILINE)
_SOURCE_REF_RE = re.compile(r"\[S-(\d{2})\]")
_FACT_REF_RE = re.compile(r"\[F-(\d{2})\]")
_JUDGMENT_RE = re.compile(r"(?:研究判断|判断|当前判断|治理判断|事实结论|大白话点评)")


def _section_spans(markdown: str) -> list[tuple[str, int, int, int | None]]:
    matches = list(_HEADING_RE.finditer(markdown))
    rows: list[tuple[str, int, int, int | None]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        rows.append((match.group(2).strip(), match.start(), end, int(match.group(1)) if match.group(1) else None))
    return rows


def _source_ids(markdown: str) -> set[str]:
    return {f"S-{value}" for value in _SOURCE_REF_RE.findall(markdown)}


def validate_v4_dossier(markdown: str, *, preview_only: bool = False) -> list[str]:
    """Return deterministic contract errors; an empty list means valid."""
    errors: list[str] = []
    if not isinstance(markdown, str) or not markdown.strip():
        return ["dossier must be a non-empty Markdown string"]
    if "# " not in markdown:
        errors.append("document title is missing")
    if "## Sources" not in markdown:
        errors.append("Sources section is missing")
    spans = _section_spans(markdown)
    expected = list(V4_HEADINGS)
    actual = [heading for heading, _, _, _ in spans if heading in expected]
    if actual != expected:
        errors.append(f"section order must be {expected}; got {actual}")
    if len(actual) != len(expected):
        missing = [heading for heading in expected if heading not in actual]
        if missing:
            errors.append("missing sections: " + ", ".join(missing))
    source_ids = _source_ids(markdown)
    if not source_ids:
        errors.append("at least one [S-xx] source reference is required")
    if "| ID |" not in markdown or "| URL |" not in markdown:
        errors.append("Sources must contain an ID and URL column")
    if "http://" in markdown:
        errors.append("source URLs must use HTTPS")
    if not preview_only and re.search(r"fixture|归档|Eastmoney F10|东财F10", markdown, re.IGNORECASE):
        errors.append("fixture/archive/F10 wording is not allowed in production dossier")
    for spec in V4_SECTION_SPECS:
        matches = [row for row in spans if row[0] == spec.heading]
        if not matches:
            continue
        _, start, end, number = matches[0]
        body = markdown[start:end]
        if number is not None and number != spec.number:
            errors.append(f"section {spec.heading} has number {number}, expected {spec.number}")
        body_chars = len(body)
        if body_chars < spec.minimum_chars:
            errors.append(f"section {spec.number} {spec.heading} is below minimum {spec.minimum_chars} chars")
        for phrase in spec.required_phrases:
            if phrase not in body:
                errors.append(f"section {spec.number} {spec.heading} lacks required marker {phrase}")
        if spec.number != 9 and not _SOURCE_REF_RE.search(body):
            errors.append(f"section {spec.number} {spec.heading} has no source reference")
    if _FACT_REF_RE.search(markdown) and not source_ids:
        errors.append("fact markers require source references")
    if not _JUDGMENT_RE.search(markdown):
        errors.append("research judgments must be explicitly labelled")
    return errors


def assert_valid_v4_dossier(markdown: str, *, preview_only: bool = False) -> None:
    errors = validate_v4_dossier(markdown, preview_only=preview_only)
    if errors:
        raise ValueError("invalid V4 dossier: " + "; ".join(errors))


def v4_contract_manifest() -> dict[str, object]:
    """Expose the contract in a JSON-friendly shape for receipts and tooling."""
    return {
        "schema_version": V4_SCHEMA_VERSION,
        "section_order": list(V4_HEADINGS),
        "sections": [
            {
                "number": spec.number,
                "heading": spec.heading,
                "target_chars": spec.target_chars,
                "minimum_chars": spec.minimum_chars,
                "required_phrases": list(spec.required_phrases),
                "evidence_source": spec.evidence_source,
            }
            for spec in V4_SECTION_SPECS
        ],
        "claim_rules": {
            "facts": "must carry [F-xx] and [S-xx] when factual",
            "judgments": "must say 研究判断/判断/当前判断 and remain falsifiable",
            "issuer_self_description": "must be labelled 公司自述 or issuer-disclosed",
            "unknowns": "must be visible as 待补/待核验, never silently omitted",
            "preview": "fixture/archive samples require preview_only=true",
        },
        "source_rules": {
            "source_table": "required",
            "url_scheme": "https",
            "page_locator": "required for page-level facts in production receipts",
        },
        "legacy_boundary": "This contract replaces field-shaped reader output only after a later migration milestone; legacy C1/Tier semantics remain unchanged for now.",
    }
