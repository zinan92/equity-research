from __future__ import annotations

import asyncio
import hashlib
import json
import sys
import unittest
from pathlib import Path
from urllib.parse import urlsplit


PRODUCT = Path(__file__).resolve().parents[1]
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from data_core import (  # noqa: E402
    CNINFO_FILING_DOCUMENT_SOURCE,
    SSE_FILING_INDEX_SOURCE,
    SSE_FILING_DOCUMENT_SOURCE,
    SZSE_FILING_DOCUMENT_SOURCE,
    FetchRequest,
    HttpResponse,
    MemoryAuthoritySink,
    RecordDomain,
    SourceChoice,
    SourceManifest,
    build_official_filing_runtime,
    classify_filing_title,
    sync_cninfo_filings,
    sync_exchange_filings,
    sync_sse_filings,
    validate_official_source_role,
)


INDEX_PREFIX = "https://www.cninfo.com.cn/new/fulltextSearch/full?"
SSE_INDEX_PREFIX = "https://query.sse.com.cn/security/stock/queryCompanyBulletin.do?"
DOCS = {
    "annual": "https://static.cninfo.com.cn/finalpage/2026-03-15/annual.PDF",
    "quarter": "https://static.cninfo.com.cn/finalpage/2026-04-20/quarter.PDF",
    "major": "https://static.cninfo.com.cn/finalpage/2026-05-01/major.PDF",
    "summary": "https://static.cninfo.com.cn/finalpage/2026-03-15/summary.PDF",
}


def announcement(document_id: str, title: str, timestamp: int) -> dict:
    return {
        "secCode": "300750",
        "announcementId": document_id,
        "announcementTitle": title,
        "announcementTime": timestamp,
        "adjunctUrl": urlsplit(DOCS[document_id]).path.lstrip("/"),
    }


class FakeTransport:
    def __init__(self, *, wrong_security: bool = False, invalid_pdf: str | None = None) -> None:
        rows = [
            announcement("annual", "宁德时代：2025年年度报告", 1773504000000),
            announcement("quarter", "宁德时代：2026年第一季度报告", 1776643200000),
            announcement("major", "宁德时代：关于重大合同的公告", 1777593600000),
            announcement("summary", "宁德时代：2025年年度报告摘要", 1773504000000),
        ]
        if wrong_security:
            rows[0]["secCode"] = "600519"
        self.index_body = json.dumps({"announcements": rows}, ensure_ascii=False).encode()
        self.sse_index_body = json.dumps({
            "result": [
                {
                    "SECURITY_CODE": "600036",
                    "BULLETIN_ID": "sse-annual-2024",
                    "TITLE": "招商银行2024年年度报告",
                    "SSEDATE": "2025-03-26",
                    "URL": "/disclosure/listedinfo/announcement/c/new/2025-03-26/600036_2024_n.pdf",
                }
            ]
        }, ensure_ascii=False).encode()
        self.invalid_pdf = invalid_pdf
        self.calls: list[str] = []

    def __call__(self, url: str, _headers) -> HttpResponse:
        self.calls.append(url)
        if url.startswith(INDEX_PREFIX):
            return HttpResponse(
                self.index_body,
                url,
                200,
                (("content-length", str(len(self.index_body))), ("content-type", "application/json")),
            )
        if url.startswith(SSE_INDEX_PREFIX):
            return HttpResponse(
                self.sse_index_body,
                url,
                200,
                (("content-length", str(len(self.sse_index_body))), ("content-type", "application/json")),
            )
        if url in DOCS.values():
            body = (
                b"not-a-pdf"
                if self.invalid_pdf and url == DOCS[self.invalid_pdf]
                else f"%PDF-1.7\n{url}\n%%EOF".encode()
            )
            return HttpResponse(
                body,
                url,
                200,
                (
                    ("content-length", str(len(body))),
                    ("content-type", "application/pdf"),
                    ("etag", f'"{hashlib.sha256(body).hexdigest()[:12]}"'),
                    ("last-modified", "Wed, 22 Jul 2026 01:00:00 GMT"),
                ),
            )
        if url.startswith("https://static.sse.com.cn/") or url.startswith(
            "https://disc.static.szse.cn/"
        ):
            body = f"%PDF-1.7\n{url}\n%%EOF".encode()
            return HttpResponse(
                body,
                url,
                200,
                (("content-length", str(len(body))), ("content-type", "application/pdf")),
            )
        raise AssertionError(f"unexpected URL: {url}")


class OfficialFilingIngestTest(unittest.TestCase):
    def test_incremental_cninfo_sync_captures_raw_pdf_and_http_receipt(self) -> None:
        transport = FakeTransport()
        sink = MemoryAuthoritySink()
        first = sync_cninfo_filings(
            "300750.SZ",
            transport=transport,
            authority_sink=sink,
            start_date="2026-01-01",
            end_date="2026-07-22",
            known_document_ids=("major",),
        )

        self.assertTrue(first.publishable)
        self.assertEqual(set(first.documents), {"annual", "quarter", "summary"})
        self.assertEqual(first.skipped_document_ids, ("major",))
        expected_types = {
            "annual": "annual_report",
            "quarter": "quarterly_report",
            "summary": "annual_report_summary",
        }
        for document_id, outcome in first.documents.items():
            self.assertTrue(outcome.publishable)
            attempt = outcome.attempts[-1]
            record = outcome.records[0]
            expected_body = f"%PDF-1.7\n{DOCS[document_id]}\n%%EOF".encode()
            expected_hash = hashlib.sha256(expected_body).hexdigest()
            self.assertEqual(attempt.raw.raw_hash, expected_hash)
            self.assertEqual(record.payload["content_hash"], expected_hash)
            self.assertEqual(record.payload["storage_uri"], attempt.raw.storage_uri)
            self.assertEqual(record.payload["document_type"], expected_types[document_id])
            self.assertEqual(record.payload["source_role"], "official_primary")
            self.assertEqual(record.payload["http_metadata"]["status_code"], 200)
            self.assertEqual(record.payload["http_metadata"]["mime_type"], "application/pdf")
            self.assertIn("etag", record.payload["http_metadata"]["headers"])
            self.assertEqual(
                record.payload["http_metadata"]["redirect_chain"], [DOCS[document_id]]
            )
        self.assertEqual(len(sink.attempts), 4)

        document_calls = len([url for url in transport.calls if url in DOCS.values()])
        second = sync_cninfo_filings(
            "300750.SZ",
            transport=transport,
            known_document_ids=tuple(DOCS),
            start_date="2026-01-01",
            end_date="2026-07-22",
        )
        self.assertTrue(second.publishable)
        self.assertEqual(second.documents, {})
        self.assertEqual(second.skipped_document_ids, tuple(sorted(DOCS)))
        self.assertEqual(
            len([url for url in transport.calls if url in DOCS.values()]), document_calls
        )

    def test_filing_classification_keeps_summary_and_full_report_distinct(self) -> None:
        cases = {
            "2025年年度报告": "annual_report",
            "2025年年度报告摘要": "annual_report_summary",
            "2026年第一季度报告": "quarterly_report",
            "2026年第三季度报告": "quarterly_report",
            "2026年半年度报告": "semiannual_report",
            "关于重大资产重组进展的公告": "major_announcement",
            "第六届董事会第十次会议决议公告": "other_announcement",
        }
        self.assertEqual(
            {title: classify_filing_title(title) for title in cases}, cases
        )

    def test_cninfo_identity_mismatch_fails_closed_before_document_fetch(self) -> None:
        transport = FakeTransport(wrong_security=True)
        result = sync_cninfo_filings("300750.SZ", transport=transport)
        self.assertFalse(result.publishable)
        self.assertEqual(result.documents, {})
        self.assertIn("another security", result.discovery.attempts[-1].error)
        self.assertEqual(len(transport.calls), 1)

    def test_aggregator_cannot_claim_official_primary_role(self) -> None:
        forged = SourceManifest(
            source_key=CNINFO_FILING_DOCUMENT_SOURCE,
            domain_scope=RecordDomain.DOCUMENT.value,
            authority_tier="official",
            provider_version="forged",
            schema_version="forged-v1",
            license_status="unknown",
            source_url="https://finance.example.com/filings",
        )
        with self.assertRaisesRegex(ValueError, "aggregator"):
            validate_official_source_role(
                forged,
                "https://finance.example.com/reprinted-report.pdf",
            )

    def test_exchange_document_adapters_accept_only_their_official_hosts(self) -> None:
        transport = FakeTransport()
        runtime = build_official_filing_runtime(transport=transport)
        cases = (
            (
                SSE_FILING_DOCUMENT_SOURCE,
                "600519.SH",
                "sse-1",
                "https://static.sse.com.cn/disclosure/listedinfo/announcement/c/new.pdf",
            ),
            (
                SZSE_FILING_DOCUMENT_SOURCE,
                "300750.SZ",
                "szse-1",
                "https://disc.static.szse.cn/disc/finalpage/new.PDF",
            ),
        )
        for source_key, ticker, document_id, url in cases:
            request = FetchRequest.create(
                request_id=f"request-{document_id}",
                domain=RecordDomain.DOCUMENT,
                entity_key=ticker,
                parameters={
                    "document_id": document_id,
                    "document_url": url,
                    "title": "2025年年度报告",
                    "published_at": "2026-03-31T00:00:00Z",
                },
            )
            outcome = asyncio.run(
                runtime.run(request, (SourceChoice(source_key, "primary"),))
            )
            self.assertTrue(outcome.publishable)

        wrong = FetchRequest.create(
            request_id="request-cross-host",
            domain=RecordDomain.DOCUMENT,
            entity_key="600519.SH",
            parameters={
                "document_id": "wrong-1",
                "document_url": "https://finance.example.com/reprint.pdf",
                "title": "2025年年度报告",
                "published_at": "2026-03-31T00:00:00Z",
            },
        )
        rejected = asyncio.run(
            runtime.run(wrong, (SourceChoice(SSE_FILING_DOCUMENT_SOURCE, "primary"),))
        )
        self.assertFalse(rejected.publishable)
        self.assertIn("aggregator", rejected.attempts[-1].error)

    def test_non_pdf_official_response_is_not_promoted(self) -> None:
        result = sync_cninfo_filings(
            "300750.SZ",
            transport=FakeTransport(invalid_pdf="annual"),
        )
        self.assertFalse(result.publishable)
        self.assertFalse(result.documents["annual"].publishable)
        self.assertIn("not a PDF", result.documents["annual"].attempts[-1].error)
        self.assertTrue(result.documents["quarter"].publishable)

    def test_sse_sync_keeps_index_raw_identity_and_only_uses_declared_url(self) -> None:
        transport = FakeTransport()
        sink = MemoryAuthoritySink()
        result = sync_sse_filings(
            "600036.SH", transport=transport, authority_sink=sink,
            start_date="2025-01-01", end_date="2025-12-31",
        )
        self.assertTrue(result.publishable)
        self.assertEqual(set(result.documents), {"sse-annual-2024"})
        discovery_attempt = result.discovery.attempts[-1]
        self.assertEqual(result.discovery.selected_source, SSE_FILING_INDEX_SOURCE)
        self.assertIsNotNone(discovery_attempt.raw)
        document = result.documents["sse-annual-2024"].records[0]
        self.assertEqual(document.payload["official_platform"], SSE_FILING_DOCUMENT_SOURCE)
        self.assertEqual(
            document.payload["http_metadata"]["source_url"],
            "https://static.sse.com.cn/disclosure/listedinfo/announcement/c/new/2025-03-26/600036_2024_n.pdf",
        )
        self.assertEqual(len(sink.attempts), 2)

    def test_sse_rejects_missing_or_unofficial_declared_document_url(self) -> None:
        transport = FakeTransport()
        transport.sse_index_body = json.dumps({"result": [{
            "SECURITY_CODE": "600036", "TITLE": "招商银行2024年年度报告",
            "SSEDATE": "2025-03-26", "URL": "https://finance.example.com/600036.pdf",
        }]}, ensure_ascii=False).encode()
        result = sync_sse_filings("600036.SH", transport=transport)
        self.assertFalse(result.publishable)
        self.assertIn("outside official SSE", result.discovery.attempts[-1].error)

    def test_exchange_selection_is_explicit_and_never_falls_back(self) -> None:
        sse = sync_exchange_filings("600036.SH", transport=FakeTransport())
        cninfo = sync_exchange_filings("300750.SZ", transport=FakeTransport())
        self.assertTrue(sse.publishable)
        self.assertTrue(cninfo.publishable)


if __name__ == "__main__":
    unittest.main()
