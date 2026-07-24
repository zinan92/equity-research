"""Page-bound PDF text extraction and fail-closed publication citations."""

from __future__ import annotations

import hashlib
import io
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Protocol, Sequence
from urllib.parse import urlsplit


DEFAULT_PARSER_VERSION = "park-document-parser-v1"


def _sha256(value: bytes | str) -> str:
    if isinstance(value, str):
        value = value.encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def _compact_length(text: str) -> int:
    return len(re.sub(r"\s+", "", text))


def _normalize_text(text: str) -> str:
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


class OCRBackend(Protocol):
    def __call__(self, pdf_bytes: bytes, page_number: int) -> str:
        ...


class TesseractCliOCR:
    """Local OCR fallback using mature `pdftoppm` and Tesseract CLIs."""

    def __init__(
        self,
        *,
        pdftoppm: str | None = None,
        tesseract: str | None = None,
        language: str | None = None,
        dpi: int = 220,
        timeout_seconds: float = 90.0,
    ) -> None:
        self.pdftoppm = pdftoppm or shutil.which("pdftoppm") or ""
        self.tesseract = tesseract or shutil.which("tesseract") or ""
        self.language = language
        self.dpi = dpi
        self.timeout_seconds = timeout_seconds

    @property
    def available(self) -> bool:
        return bool(self.pdftoppm and self.tesseract)

    def _language(self) -> str:
        if self.language:
            return self.language
        result = subprocess.run(
            [self.tesseract, "--list-langs"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        languages = set(result.stdout.splitlines())
        return "chi_sim+eng" if "chi_sim" in languages and "eng" in languages else "eng"

    def __call__(self, pdf_bytes: bytes, page_number: int) -> str:
        if not self.available:
            raise RuntimeError("OCR fallback requires pdftoppm and tesseract")
        if page_number < 1:
            raise ValueError("page_number must be one-based")
        with tempfile.TemporaryDirectory(prefix="park-document-ocr-") as directory:
            root = Path(directory)
            pdf_path = root / "source.pdf"
            image_stem = root / "page"
            pdf_path.write_bytes(pdf_bytes)
            render = subprocess.run(
                [
                    self.pdftoppm,
                    "-f", str(page_number),
                    "-l", str(page_number),
                    "-singlefile",
                    "-r", str(self.dpi),
                    "-png",
                    str(pdf_path),
                    str(image_stem),
                ],
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
            image_path = image_stem.with_suffix(".png")
            if render.returncode or not image_path.is_file():
                raise RuntimeError(f"PDF rasterization failed: {render.stderr.strip()}")
            ocr = subprocess.run(
                [
                    self.tesseract,
                    str(image_path),
                    "stdout",
                    "-l", self._language(),
                    "--psm", "6",
                ],
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
            if ocr.returncode:
                raise RuntimeError(f"Tesseract OCR failed: {ocr.stderr.strip()}")
            return ocr.stdout


@dataclass(frozen=True)
class ParserConfig:
    parser_version: str = DEFAULT_PARSER_VERSION
    native_text_min_chars: int = 24
    ocr_text_min_chars: int = 8
    chunk_chars: int = 1200
    chunk_overlap: int = 120
    max_pages: int = 600
    page_mapping_threshold: float = 0.95
    scanned_text_coverage_threshold: float = 0.90

    def validate(self) -> None:
        if not self.parser_version.strip():
            raise ValueError("parser_version is required")
        if self.native_text_min_chars < 0 or self.ocr_text_min_chars < 1:
            raise ValueError("text thresholds are invalid")
        if self.chunk_chars < 100 or not 0 <= self.chunk_overlap < self.chunk_chars:
            raise ValueError("chunk policy is invalid")
        if self.max_pages < 1:
            raise ValueError("max_pages must be positive")
        if not 0 <= self.page_mapping_threshold <= 1:
            raise ValueError("page mapping threshold is invalid")
        if not 0 <= self.scanned_text_coverage_threshold <= 1:
            raise ValueError("OCR coverage threshold is invalid")


@dataclass(frozen=True)
class DocumentPage:
    document_id: str
    page_number: int
    raw_hash: str
    parser_version: str
    text: str
    text_hash: str
    extraction_method: str
    table_status: str
    extraction_error: str | None = None


@dataclass(frozen=True)
class DocumentChunk:
    chunk_id: str
    document_id: str
    page_number: int
    raw_hash: str
    parser_version: str
    char_start: int
    char_end: int
    text: str
    extraction_method: str


@dataclass(frozen=True)
class DocumentParseResult:
    document_id: str
    raw_hash: str
    parser_version: str
    parse_id: str
    pages: tuple[DocumentPage, ...]
    chunks: tuple[DocumentChunk, ...]
    warnings: tuple[str, ...]

    def page(self, page_number: int) -> DocumentPage | None:
        return next((page for page in self.pages if page.page_number == page_number), None)


def _looks_like_table(text: str) -> bool:
    numeric_rows = 0
    for line in text.splitlines():
        numeric_cells = re.findall(r"(?<!\w)[-+]?\d[\d,.%]*(?!\w)", line)
        if len(numeric_cells) >= 2 and ("\t" in line or "|" in line or " " in line):
            numeric_rows += 1
    return numeric_rows >= 2


def _chunks_for_page(page: DocumentPage, config: ParserConfig) -> tuple[DocumentChunk, ...]:
    if not page.text:
        return ()
    chunks = []
    start = 0
    while start < len(page.text):
        end = min(len(page.text), start + config.chunk_chars)
        if end < len(page.text):
            boundary = max(page.text.rfind("\n", start, end), page.text.rfind("。", start, end))
            if boundary > start + config.chunk_chars // 2:
                end = boundary + 1
        left = start
        right = end
        while left < right and page.text[left].isspace():
            left += 1
        while right > left and page.text[right - 1].isspace():
            right -= 1
        if right > left:
            text = page.text[left:right]
            chunk_id = "chunk_" + _sha256(
                f"{page.document_id}:{page.raw_hash}:{page.parser_version}:"
                f"{page.page_number}:{left}:{right}:{_sha256(text)}"
            )[:40]
            chunks.append(
                DocumentChunk(
                    chunk_id=chunk_id,
                    document_id=page.document_id,
                    page_number=page.page_number,
                    raw_hash=page.raw_hash,
                    parser_version=page.parser_version,
                    char_start=left,
                    char_end=right,
                    text=text,
                    extraction_method=page.extraction_method,
                )
            )
        if end >= len(page.text):
            break
        start = max(end - config.chunk_overlap, start + 1)
    return tuple(chunks)


def parse_pdf_document(
    document_id: str,
    pdf_bytes: bytes,
    *,
    expected_raw_hash: str | None = None,
    config: ParserConfig | None = None,
    ocr_backend: OCRBackend | None = None,
) -> DocumentParseResult:
    """Extract page-native text, falling back to OCR without crossing page boundaries."""

    config = config or ParserConfig()
    config.validate()
    if not document_id.strip():
        raise ValueError("document_id is required")
    if not pdf_bytes.startswith(b"%PDF"):
        raise ValueError("document intelligence accepts PDF bytes only")
    raw_hash = _sha256(pdf_bytes)
    if expected_raw_hash and expected_raw_hash != raw_hash:
        raise ValueError("PDF bytes do not match expected raw hash")
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(pdf_bytes))
    except Exception as exc:
        raise ValueError(f"PDF cannot be parsed: {exc}") from exc
    if not reader.pages or len(reader.pages) > config.max_pages:
        raise ValueError("PDF page count is outside parser limits")
    if ocr_backend is None:
        default_ocr = TesseractCliOCR()
        ocr_backend = default_ocr if default_ocr.available else None

    pages = []
    warnings = []
    for page_number, source_page in enumerate(reader.pages, start=1):
        extraction_error = None
        try:
            native = source_page.extract_text(extraction_mode="layout") or ""
        except TypeError:
            native = source_page.extract_text() or ""
        except Exception as exc:
            native = ""
            extraction_error = f"native extraction failed: {type(exc).__name__}"
        text = _normalize_text(native)
        method = "native_text"
        if _compact_length(text) < config.native_text_min_chars:
            if ocr_backend is None:
                method = "unreadable"
                extraction_error = extraction_error or "OCR backend unavailable"
                text = ""
            else:
                try:
                    text = _normalize_text(ocr_backend(pdf_bytes, page_number))
                    if _compact_length(text) < config.ocr_text_min_chars:
                        method = "unreadable"
                        extraction_error = "OCR produced insufficient searchable text"
                        text = ""
                    else:
                        method = "ocr"
                except Exception as exc:
                    method = "unreadable"
                    extraction_error = f"OCR failed: {type(exc).__name__}: {exc}"
                    text = ""
        table_status = "possible_unlocated" if _looks_like_table(text) else "none_detected"
        if table_status == "possible_unlocated":
            warnings.append(f"page {page_number}: possible table has no verified coordinates")
        if method == "unreadable":
            warnings.append(f"page {page_number}: {extraction_error}")
        pages.append(
            DocumentPage(
                document_id=document_id,
                page_number=page_number,
                raw_hash=raw_hash,
                parser_version=config.parser_version,
                text=text,
                text_hash=_sha256(text),
                extraction_method=method,
                table_status=table_status,
                extraction_error=extraction_error,
            )
        )
    chunks = tuple(chunk for page in pages for chunk in _chunks_for_page(page, config))
    parse_id = "parse_" + _sha256(
        f"{document_id}:{raw_hash}:{config.parser_version}:"
        + ":".join(page.text_hash for page in pages)
    )[:40]
    return DocumentParseResult(
        document_id=document_id,
        raw_hash=raw_hash,
        parser_version=config.parser_version,
        parse_id=parse_id,
        pages=tuple(pages),
        chunks=chunks,
        warnings=tuple(warnings),
    )


@dataclass(frozen=True)
class CorpusQuality:
    page_mapping_accuracy: float
    scanned_text_coverage: float
    passed: bool
    reasons: tuple[str, ...]


def assess_corpus_quality(
    result: DocumentParseResult,
    *,
    expected_page_markers: Mapping[int, str],
    scanned_page_numbers: Iterable[int] = (),
    config: ParserConfig | None = None,
) -> CorpusQuality:
    config = config or ParserConfig(parser_version=result.parser_version)
    config.validate()
    mapped = sum(
        bool(result.page(page_number) and marker in result.page(page_number).text)
        for page_number, marker in expected_page_markers.items()
    )
    page_accuracy = mapped / len(expected_page_markers) if expected_page_markers else 1.0
    scanned = tuple(sorted(set(scanned_page_numbers)))
    covered = sum(
        bool(
            result.page(page_number)
            and result.page(page_number).extraction_method == "ocr"
            and _compact_length(result.page(page_number).text) >= config.ocr_text_min_chars
        )
        for page_number in scanned
    )
    ocr_coverage = covered / len(scanned) if scanned else 1.0
    reasons = []
    if page_accuracy < config.page_mapping_threshold:
        reasons.append("page mapping accuracy is below threshold")
    if ocr_coverage < config.scanned_text_coverage_threshold:
        reasons.append("scanned-page searchable text coverage is below threshold")
    return CorpusQuality(page_accuracy, ocr_coverage, not reasons, tuple(reasons))


@dataclass(frozen=True)
class PageCitation:
    document_id: str
    page_number: int
    raw_hash: str
    quote: str | None = None
    chunk_id: str | None = None


@dataclass(frozen=True)
class CitationReturnPath:
    """Immutable source coordinates needed to return a reader to evidence."""

    document_id: str
    page_number: int
    raw_hash: str
    source_url: str
    storage_uri: str


def resolve_citation_return_path(
    citation: PageCitation, document_payload: Mapping[str, object]
) -> CitationReturnPath:
    """Bind a page citation to its official document receipt without guessing URLs."""

    document_id = str(document_payload.get("document_id") or "")
    content_hash = str(document_payload.get("content_hash") or "")
    storage_uri = str(document_payload.get("storage_uri") or "")
    metadata = document_payload.get("http_metadata")
    source_url = str(metadata.get("source_url") or "") if isinstance(metadata, Mapping) else ""
    if document_id != citation.document_id:
        raise ValueError("citation document_id does not match document receipt")
    if content_hash != citation.raw_hash:
        raise ValueError("citation raw_hash does not match document receipt")
    parsed = urlsplit(source_url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("citation source URL is missing or not HTTPS")
    if not storage_uri:
        raise ValueError("citation storage URI is missing")
    if citation.page_number < 1:
        raise ValueError("citation page_number must be one-based")
    return CitationReturnPath(document_id, citation.page_number, content_hash, source_url, storage_uri)


@dataclass(frozen=True)
class ReportClaim:
    claim_id: str
    text: str
    citations: tuple[PageCitation, ...]


@dataclass(frozen=True)
class CitationCheck:
    claim_id: str
    citation: PageCitation | None
    valid: bool
    errors: tuple[str, ...]


@dataclass(frozen=True)
class PublicationGateResult:
    published_claims: tuple[ReportClaim, ...]
    blocked_claims: tuple[ReportClaim, ...]
    checks: tuple[CitationCheck, ...]

    @property
    def publishable(self) -> bool:
        return not self.blocked_claims


def validate_publication_citations(
    claims: Sequence[ReportClaim],
    corpus: Mapping[str, DocumentParseResult],
) -> PublicationGateResult:
    """Block a claim unless every citation resolves to the exact document/page/raw bytes."""

    published = []
    blocked = []
    checks = []
    for claim in claims:
        claim_valid = bool(claim.citations)
        if not claim.citations:
            checks.append(CitationCheck(claim.claim_id, None, False, ("claim has no citation",)))
        for citation in claim.citations:
            errors = []
            document = corpus.get(citation.document_id)
            page = document.page(citation.page_number) if document else None
            if document is None:
                errors.append("unknown document_id")
            elif document.raw_hash != citation.raw_hash:
                errors.append("raw_hash mismatch")
            if page is None:
                errors.append("unknown page_number")
            elif citation.quote and _normalize_text(citation.quote) not in page.text:
                errors.append("quote not found on cited page")
            if citation.chunk_id:
                chunk = next(
                    (
                        item for item in document.chunks
                        if item.chunk_id == citation.chunk_id
                        and item.page_number == citation.page_number
                    ),
                    None,
                ) if document else None
                if chunk is None:
                    errors.append("chunk_id is not bound to cited page")
            valid = not errors
            claim_valid = claim_valid and valid
            checks.append(CitationCheck(claim.claim_id, citation, valid, tuple(errors)))
        (published if claim_valid else blocked).append(claim)
    return PublicationGateResult(tuple(published), tuple(blocked), tuple(checks))
