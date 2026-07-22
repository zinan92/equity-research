from __future__ import annotations

import asyncio
import json
import sys
import unittest
from pathlib import Path


PRODUCT = Path(__file__).resolve().parents[1]
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from data_core import (  # noqa: E402
    HttpResponse,
    FetchRequest,
    RecordDomain,
    SourceChoice,
    THS_FORECAST_SOURCE,
    build_consensus_snapshot,
    build_sell_side_runtime,
    build_ths_forecast_runtime,
    compare_consensus_snapshots,
    estimates_from_catalog_outcomes,
    normalize_broker_estimate,
    reconcile_ths_broker_estimates,
    sync_sell_side_archive,
    ths_consensus_references,
)


class CatalogTransport:
    def __call__(self, url: str, _headers) -> HttpResponse:
        if "reportapi.eastmoney.com" in url:
            body = json.dumps(
                {
                    "currentYear": 2026,
                    "data": [
                        {
                            "infoCode": "AP-CATL-1",
                            "title": "宁德时代盈利预测更新",
                            "publishDate": "2026-04-22 00:00:00",
                            "orgSName": "国信证券",
                            "researcher": "王研究员",
                            "emRatingName": "增持",
                            "predictThisYearEps": "21.11",
                            "predictThisYearPe": "21.2",
                            "predictNextYearEps": "26.31",
                            "predictNextYearPe": "17.0",
                            "predictNextTwoYearEps": "30.87",
                            "predictNextTwoYearPe": "14.5",
                            "indvAimPriceL": "460",
                            "indvAimPriceT": "500",
                        }
                    ],
                },
                ensure_ascii=False,
            ).encode()
            return HttpResponse(body, url, 200, (("content-type", "application/json"),))
        body = b"%PDF-1.7\nCATL estimate report\n%%EOF"
        return HttpResponse(body, url, 200, (("content-type", "application/pdf"),))


class ThsTransport:
    def __call__(self, url: str, _headers) -> HttpResponse:
        html = """
        <html><body>
        <table>
          <tr><th>机构名称</th><th>研究员</th><th>预测年报每股收益2026预测</th><th>预测年报净利润2026预测</th><th>报告日期</th></tr>
          <tr><td>国信证券</td><td>王研究员</td><td>21.11</td><td>961.43亿</td><td>2026-04-22</td></tr>
        </table>
        <table>
          <tr><th>预测指标</th><th>预测2026-平均</th><th>预测2027-平均</th></tr>
          <tr><td>营业收入(元)</td><td>5892.74亿</td><td>7241.97亿</td></tr>
          <tr><td>净利润(元)</td><td>950.81亿</td><td>1176.66亿</td></tr>
        </table>
        </body></html>
        """.encode("gb18030")
        return HttpResponse(html, url, 200, (("content-type", "text/html"),))


def estimate(
    report_id: str,
    value: float,
    *,
    report_date: str = "2026-04-01",
    fiscal_year: int = 2027,
    revenue: float | None = None,
    profit: float | None = None,
    target: float | None = None,
    broker: str | None = None,
):
    return normalize_broker_estimate(
        ticker="300750.SZ",
        broker=broker or f"券商-{report_id}",
        analyst="研究员",
        report_id=report_id,
        report_date=report_date,
        raw_hash=(report_id.encode().hex() + "0" * 64)[:64],
        fiscal_year=fiscal_year,
        eps=value,
        revenue=revenue,
        net_profit=profit,
        target_price=target,
        rating="买入",
    )


class ConsensusHistoryTest(unittest.TestCase):
    def test_eastmoney_catalog_estimates_bind_report_broker_date_and_year(self) -> None:
        batch = sync_sell_side_archive(
            "300750.SZ",
            runtime=build_sell_side_runtime(transport=CatalogTransport()),
            page_size=10,
        )
        estimates = estimates_from_catalog_outcomes(batch.catalog_outcomes)

        self.assertEqual([item.fiscal_year for item in estimates], [2026, 2027, 2028])
        self.assertTrue(all(item.report_id == "AP-CATL-1" for item in estimates))
        self.assertTrue(all(item.broker == "国信证券" for item in estimates))
        self.assertTrue(all(item.report_date == "2026-04-22" for item in estimates))
        self.assertEqual([item.eps for item in estimates], [21.11, 26.31, 30.87])
        self.assertEqual(estimates[0].target_price, 480.0)
        self.assertIsNone(estimates[1].target_price)

    def test_ths_profit_and_revenue_are_normalized_and_report_match_is_fail_closed(self) -> None:
        runtime = build_ths_forecast_runtime(transport=ThsTransport())
        request = FetchRequest.create(
            request_id="ths-catl-forecast",
            domain=RecordDomain.EVENT,
            entity_key="300750.SZ",
            parameters={"as_of": "2026-04-30"},
        )
        outcome = asyncio.run(
            runtime.run(request, (SourceChoice(THS_FORECAST_SOURCE, "primary"),))
        )
        self.assertTrue(outcome.publishable)
        references = ths_consensus_references(outcome)
        revenue = next(
            item for item in references if item.metric == "revenue" and item.fiscal_year == 2026
        )
        self.assertEqual(revenue.mean, 5892.74e8)

        base = normalize_broker_estimate(
            ticker="300750.SZ",
            broker="国信证券",
            analyst="王研究员",
            report_id="AP-CATL-1",
            report_date="2026-04-22",
            raw_hash="a" * 64,
            fiscal_year=2026,
            eps=21.11,
        )
        enriched = reconcile_ths_broker_estimates([base], outcome)[0]
        self.assertEqual(enriched.report_id, "AP-CATL-1")
        self.assertEqual(enriched.net_profit, 961.43e8)
        self.assertIn(THS_FORECAST_SOURCE, enriched.source_key)
        self.assertEqual(enriched.supporting_raw_hashes, (outcome.attempts[-1].raw.raw_hash,))

    def test_all_required_metrics_are_standardized_by_fiscal_year(self) -> None:
        item = estimate(
            "metric-report",
            20.5,
            fiscal_year=2027,
            revenue=7200.0,
            profit=1180.0,
            target=520.0,
        )
        snapshot = build_consensus_snapshot("300750.SZ", [item], as_of="2026-04-30")

        for metric, expected in {
            "eps": 20.5,
            "revenue": 7200.0,
            "net_profit": 1180.0,
            "target_price": 520.0,
        }.items():
            point = snapshot.point(metric, 2027)
            self.assertIsNotNone(point)
            self.assertEqual(point.mean, expected)

    def test_snapshot_is_point_in_time_deterministic_and_replayable(self) -> None:
        old = estimate("old", 10.0, report_date="2026-03-01")
        future = estimate("future", 12.0, report_date="2026-05-01")
        first = build_consensus_snapshot(
            "300750.SZ", [future, old], as_of="2026-04-30"
        )
        replay = build_consensus_snapshot(
            "300750.SZ", [old, future], as_of="2026-04-30"
        )

        self.assertEqual(first.snapshot_id, replay.snapshot_id)
        self.assertEqual([item.report_id for item in first.estimates], ["old"])
        self.assertTrue(first.replay_valid())

    def test_outlier_is_quarantined_before_mean_and_remains_auditable(self) -> None:
        rows = [
            estimate("a", 9.5),
            estimate("b", 10.0),
            estimate("c", 10.5),
            estimate("d", 11.0),
            estimate("bad", 100.0),
        ]
        snapshot = build_consensus_snapshot("300750.SZ", rows, as_of="2026-04-30")
        point = snapshot.point("eps", 2027)

        self.assertEqual(point.contributor_count, 4)
        self.assertEqual(point.excluded_count, 1)
        self.assertEqual(point.mean, 10.25)
        self.assertEqual(len(snapshot.quarantine), 1)
        self.assertEqual(snapshot.quarantine[0].estimate_id, rows[-1].estimate_id)
        self.assertIn("outlier", snapshot.quarantine[0].reason)

    def test_only_latest_report_per_broker_and_year_enters_consensus(self) -> None:
        older = estimate("old", 8.0, report_date="2026-03-01", broker="同一券商")
        latest = estimate("latest", 12.0, report_date="2026-04-01", broker="同一券商")
        peer = estimate("peer", 10.0, report_date="2026-03-15", broker="另一券商")
        snapshot = build_consensus_snapshot(
            "300750.SZ", [latest, peer, older], as_of="2026-04-30"
        )
        point = snapshot.point("eps", 2027)

        self.assertEqual(point.mean, 11.0)
        self.assertEqual(point.contributor_count, 2)
        self.assertEqual(point.excluded_count, 1)
        self.assertTrue(any(item.estimate_id == older.estimate_id for item in snapshot.quarantine))

    def test_revision_model_exposes_direction_and_contributor_change(self) -> None:
        previous = build_consensus_snapshot(
            "300750.SZ",
            [estimate("a", 10.0), estimate("b", 12.0)],
            as_of="2026-04-01",
        )
        current = build_consensus_snapshot(
            "300750.SZ",
            [
                estimate("a", 10.0),
                estimate("b", 12.0),
                estimate("c", 14.0, report_date="2026-04-15"),
            ],
            as_of="2026-04-30",
        )
        revision = next(
            item for item in compare_consensus_snapshots(previous, current)
            if item.metric == "eps" and item.fiscal_year == 2027
        )

        self.assertEqual(revision.previous_mean, 11.0)
        self.assertEqual(revision.current_mean, 12.0)
        self.assertEqual(revision.absolute_change, 1.0)
        self.assertGreater(revision.percent_change, 9.0)
        self.assertEqual((revision.previous_contributors, revision.current_contributors), (2, 3))

    def test_invalid_or_empty_estimate_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least one"):
            normalize_broker_estimate(
                ticker="300750.SZ",
                broker="券商",
                analyst=None,
                report_id="report",
                report_date="2026-04-01",
                raw_hash="a" * 64,
                fiscal_year=2027,
            )


if __name__ == "__main__":
    unittest.main()
