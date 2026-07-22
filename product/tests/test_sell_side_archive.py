from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


PRODUCT = Path(__file__).resolve().parents[1]
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from data_core import (  # noqa: E402
    HttpResponse,
    RateLimitedRetryTransport,
    build_sell_side_runtime,
    sync_sell_side_archive,
)


CATALOG = "https://reportapi.eastmoney.com/report/list"


def report(
    report_id: str,
    *,
    broker: str = "中金公司",
    analyst: str = "研究员甲",
    rating: str = "买入",
    pages: int = 28,
) -> dict:
    return {
        "infoCode": report_id,
        "title": f"宁德时代深度报告 {report_id}",
        "publishDate": "2026-07-20 08:30:00",
        "orgSName": broker,
        "researcher": analyst,
        "emRatingName": rating,
        "attachPages": pages,
    }


class FakeTransport:
    def __init__(
        self,
        rows: list[dict],
        *,
        pdf_bodies: dict[str, bytes] | None = None,
        missing_ids: tuple[str, ...] = (),
    ) -> None:
        self.rows = rows
        self.pdf_bodies = pdf_bodies or {}
        self.missing_ids = set(missing_ids)
        self.calls: list[str] = []

    def __call__(self, url: str, _headers) -> HttpResponse:
        self.calls.append(url)
        if url.startswith(CATALOG):
            query = parse_qs(urlsplit(url).query)
            page = int(query["pageNo"][0])
            page_size = int(query["pageSize"][0])
            start = (page - 1) * page_size
            body = json.dumps({"data": self.rows[start : start + page_size]}).encode()
            return HttpResponse(
                body,
                url,
                200,
                (("content-type", "application/json"),),
            )
        report_id = url.rsplit("H3_", 1)[1].rsplit("_1.pdf", 1)[0]
        if report_id in self.missing_ids:
            return HttpResponse(
                b"missing",
                url,
                404,
                (("content-type", "text/html"),),
            )
        body = self.pdf_bodies.get(
            report_id, f"%PDF-1.7\n{report_id}\n%%EOF".encode()
        )
        return HttpResponse(
            body,
            url,
            200,
            (("content-type", "application/pdf"),),
        )


class SellSideArchiveTest(unittest.TestCase):
    def test_catalog_and_pdf_archive_preserve_queryable_metadata(self) -> None:
        transport = FakeTransport(
            [
                report("r1"),
                report(
                    "r2",
                    broker="华泰证券",
                    analyst="研究员乙",
                    rating="增持",
                    pages=12,
                ),
            ]
        )
        batch = sync_sell_side_archive(
            "300750.SZ",
            runtime=build_sell_side_runtime(transport=transport),
            page_size=10,
        )

        self.assertEqual(len(batch.items), 2)
        self.assertEqual(batch.to_summary()["status_counts"], {"archived_pdf": 2})
        selected = batch.query(
            broker="华泰证券",
            analyst="研究员乙",
            published_after="2026-07-01",
            published_before="2026-07-31T23:59:59Z",
            min_pages=10,
        )
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0].report_id, "r2")
        self.assertEqual(selected[0].rating, "增持")
        self.assertEqual(selected[0].pages, 12)
        self.assertTrue(selected[0].raw_hash)
        self.assertTrue(selected[0].storage_uri)

    def test_incremental_sync_skips_known_report_before_pdf_fetch(self) -> None:
        transport = FakeTransport([report("known"), report("new")])
        batch = sync_sell_side_archive(
            "300750.SZ",
            runtime=build_sell_side_runtime(transport=transport),
            known_report_ids=("known",),
        )

        self.assertEqual(
            {item.report_id: item.archive_status for item in batch.items},
            {"known": "duplicate_url", "new": "archived_pdf"},
        )
        self.assertFalse(any("H3_known_1.pdf" in call for call in transport.calls))

    def test_identical_pdf_bytes_are_deduplicated_by_sha(self) -> None:
        body = b"%PDF-1.7\nsame research report\n%%EOF"
        transport = FakeTransport(
            [report("r1"), report("r2")],
            pdf_bodies={"r1": body, "r2": body},
        )
        batch = sync_sell_side_archive(
            "300750.SZ", runtime=build_sell_side_runtime(transport=transport)
        )

        self.assertEqual(
            [item.archive_status for item in batch.items],
            ["archived_pdf", "duplicate_sha"],
        )
        self.assertEqual(batch.items[0].raw_hash, batch.items[1].raw_hash)

    def test_missing_or_invalid_pdf_remains_explicit_metadata_only(self) -> None:
        transport = FakeTransport(
            [report("ok"), report("missing"), report("html")],
            missing_ids=("missing",),
            pdf_bodies={"html": b"<html>anti-bot page</html>"},
        )
        batch = sync_sell_side_archive(
            "300750.SZ", runtime=build_sell_side_runtime(transport=transport)
        )
        statuses = {item.report_id: item.archive_status for item in batch.items}

        self.assertEqual(
            statuses,
            {"ok": "archived_pdf", "missing": "metadata_only", "html": "metadata_only"},
        )
        self.assertTrue(batch.query(status="metadata_only"))
        self.assertTrue(all(item.error for item in batch.query(status="metadata_only")))

    def test_catalog_pagination_is_incremental_and_bounded(self) -> None:
        transport = FakeTransport([report("r1"), report("r2"), report("r3")])
        batch = sync_sell_side_archive(
            "300750.SZ",
            runtime=build_sell_side_runtime(transport=transport),
            page_size=2,
            max_pages=2,
        )

        self.assertEqual({item.report_id for item in batch.items}, {"r1", "r2", "r3"})
        catalog_calls = [call for call in transport.calls if call.startswith(CATALOG)]
        self.assertEqual(len(catalog_calls), 2)

    def test_rate_limit_and_retry_policy_are_controllable(self) -> None:
        clock = [0.0]
        sleeps: list[float] = []
        calls = [0]

        def monotonic() -> float:
            return clock[0]

        def sleep(seconds: float) -> None:
            sleeps.append(seconds)
            clock[0] += seconds

        def transient(url: str, _headers) -> HttpResponse:
            calls[0] += 1
            status = 503 if calls[0] == 1 else 200
            return HttpResponse(b"{}", url, status, (("content-type", "application/json"),))

        transport = RateLimitedRetryTransport(
            transient,
            min_interval=1.0,
            max_attempts=2,
            backoff_seconds=0.5,
            monotonic=monotonic,
            sleep=sleep,
        )
        response = transport(CATALOG, {})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(calls[0], 2)
        self.assertAlmostEqual(sum(sleeps), 1.0)


if __name__ == "__main__":
    unittest.main()
