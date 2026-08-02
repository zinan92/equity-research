"""Reader-facing V4 contract.

V4 is now an exact Round 7 document contract.  The former seven-section
adapter shape is retained below only as a historical compatibility constant;
it is never accepted by the production validator or publication entrypoint.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from data_core.round7_north_star import ROUND7_REQUIRED_HEADINGS, ROUND7_READER_UNITS


V4_SCHEMA_VERSION = "park-v4-dossier-v1"
V4_HEADINGS: tuple[str, ...] = (
    "一句话定位",
    "身份、创始人与治理",
    "技术来源与发展史",
    "商业模式与业务线",
    "财务与经营时间序列",
    "护城河的证据链",
    "风险、反题材与观察触发器",
    "研究结论与待补问题",
    "生产记录",
)

# Historical output emitted by the retired field-shaped adapter.  Keeping the
# names makes old receipts/replay diagnostics readable, but this tuple is not
# part of the live contract.
LEGACY_V4_HEADINGS: tuple[str, ...] = (
    "一句话定位", "产业坐标", "创始人与团队", "发展时间线",
    "技术、产品与商业模式", "财务与估值", "风险与点评", "生产记录",
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
    V4SectionSpec(1, V4_HEADINGS[0], 360, 40, (), "issuer facts + bounded analysis"),
    V4SectionSpec(2, V4_HEADINGS[1], 420, 40, (), "issuer governance disclosure"),
    V4SectionSpec(3, V4_HEADINGS[2], 620, 40, (), "issuer history/technology disclosure"),
    V4SectionSpec(4, V4_HEADINGS[3], 760, 40, (), "issuer business disclosure"),
    V4SectionSpec(5, V4_HEADINGS[4], 700, 40, (), "page-level financial facts"),
    V4SectionSpec(6, V4_HEADINGS[5], 620, 40, (), "facts + falsifiers"),
    V4SectionSpec(7, V4_HEADINGS[6], 700, 40, (), "facts + typed gaps"),
    V4SectionSpec(8, V4_HEADINGS[7], 300, 40, (), "facts + open questions"),
    V4SectionSpec(9, V4_HEADINGS[8], 300, 40, (), "immutable production receipt"),
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
    expected_headings = list(ROUND7_REQUIRED_HEADINGS)
    found_heading_lines = [line.strip() for line in markdown.splitlines() if line.startswith("## ")]
    if any(heading in found_heading_lines for heading in ("## 产业坐标", "## 财务与估值", "## 风险与点评")):
        errors.append("legacy V4 section headings are not publishable")
    if found_heading_lines != expected_headings:
        errors.append(f"section headings must exactly match Round 7; got {found_heading_lines}")
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
        "reader_units": list(ROUND7_READER_UNITS),
        "legacy_boundary": "Round 7 exact nine chapters replace the retired seven-section V4 adapter on 2026-08-02. Legacy C1/Tier/B6/decision semantics remain unchanged.",
        "legacy_headings": list(LEGACY_V4_HEADINGS),
    }


def validate_legacy_v4_dossier(markdown: str) -> list[str]:
    """Diagnostic-only validator for historical mapped artifacts.

    This function deliberately is not imported by the publication path.  It
    exists so migration/replay tooling can say *why* an old artifact is being
    retired instead of silently treating it as canonical.
    """
    spans = _section_spans(markdown)
    actual = [heading for heading, _, _, _ in spans if heading in LEGACY_V4_HEADINGS]
    return [] if actual == list(LEGACY_V4_HEADINGS) else ["not a legacy V4 mapped dossier"]
