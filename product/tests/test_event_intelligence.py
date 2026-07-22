from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
PRODUCT = ROOT / "product"
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from data_core import (  # noqa: E402
    AShareEntityResolver,
    AShareSecurityMasterEntry,
    IntelSourceSpec,
    attach_event_inference,
    collect_intelligence,
)


CATL = AShareSecurityMasterEntry(
    instrument_id="CN:300750.SZ",
    ticker="300750.SZ",
    exchange="SZ",
    board="ChiNext",
    name="宁德时代",
    aliases=("宁德时代", "CATL", "300750", "300750.SZ"),
)
MOUTAI = AShareSecurityMasterEntry(
    instrument_id="CN:600519.SH",
    ticker="600519.SH",
    exchange="SH",
    board="Main",
    name="贵州茅台",
    aliases=("贵州茅台", "茅台", "600519", "600519.SH"),
)


def source(
    source_key: str,
    source_type: str,
    items,
    *,
    source_url: str | None = None,
) -> IntelSourceSpec:
    def collect():
        if isinstance(items, Exception):
            raise items
        return items

    return IntelSourceSpec(
        source_key=source_key,
        source_type=source_type,
        display_name=source_key,
        source_url=source_url or f"https://{source_key}.example.test/feed",
        collector=collect,
        provider_version="intel-adapter-test-v1",
    )


def article(
    *,
    title: str,
    url: str,
    published_at: str = "2026-07-21T08:00:00Z",
    summary: str = "",
    tickers: list[str] | None = None,
    source_id: str = "item-1",
) -> dict[str, object]:
    return {
        "source_id": source_id,
        "title": title,
        "url": url,
        "published_at": published_at,
        "summary": summary,
        "tickers": tickers or [],
    }


def test_intel_collectors_expose_canonical_source_manifests() -> None:
    specs = [
        source("rss_finance", "rss", []),
        source("google_news_cn", "google_news", []),
        source("yahoo_finance_cn", "yahoo_finance", []),
        source(
            "szse_monitor",
            "official_monitor",
            [],
            source_url="https://www.szse.cn/disclosure/",
        ),
    ]

    for spec in specs:
        manifest = spec.manifest
        assert manifest.domain_scope == "event"
        assert manifest.authority_tier == "supplementary_only"
        assert manifest.schema_version == "park-event-intelligence-v1"
        assert manifest.quality_flags == ("news_discovery_not_official_fact",)
        assert len(manifest.manifest_hash) == 64


def test_a_share_entity_resolution_is_explicit_and_ambiguous_aliases_fail_closed() -> None:
    resolver = AShareEntityResolver((CATL, MOUTAI))

    by_name = resolver.resolve("宁德时代发布半年业绩预告")
    by_ticker = resolver.resolve("公司更新", source_tickers=("300750",))

    assert by_name.tickers == ("300750.SZ",)
    assert by_name.instrument_ids == ("CN:300750.SZ",)
    assert by_ticker.tickers == ("300750.SZ",)

    first = AShareSecurityMasterEntry(
        "CN:000001.SZ", "000001.SZ", "SZ", "Main", "平安银行", ("共同别名",)
    )
    second = AShareSecurityMasterEntry(
        "CN:000002.SZ", "000002.SZ", "SZ", "Main", "万科A", ("共同别名",)
    )
    ambiguous = AShareEntityResolver((first, second)).resolve("共同别名发布公告")
    assert ambiguous.tickers == ()
    assert ambiguous.ambiguous_aliases == ("共同别名",)


def test_collector_output_is_raw_bound_evidence_not_inference() -> None:
    batch = collect_intelligence(
        (
            source(
                "google_news_cn",
                "google_news",
                [
                    article(
                        title="宁德时代发布新一代电池",
                        url="https://news.example.test/catl?id=7&utm_source=google#top",
                        summary="公司在发布会上介绍产品。",
                    )
                ],
            ),
        ),
        resolver=AShareEntityResolver((CATL, MOUTAI)),
    )

    assert not batch.coverage_gaps
    assert len(batch.evidence) == 1
    evidence = batch.evidence[0]
    outcome = batch.outcomes["google_news_cn"]
    record = outcome.records[0]
    assert evidence.ticker == "300750.SZ"
    assert evidence.url == "https://news.example.test/catl?id=7"
    assert evidence.raw_hash == record.provenance.raw_hash
    assert record.payload["inference"] is None
    assert record.payload["is_llm_inferred"] is False
    assert hashlib.sha256(outcome.attempts[0].fetched.body).hexdigest() == evidence.raw_hash


def test_same_event_is_deduplicated_across_sources_within_48_hours() -> None:
    batch = collect_intelligence(
        (
            source(
                "rss_finance",
                "rss",
                [
                    article(
                        title="宁德时代发布新一代快充电池",
                        url="https://finance.example.test/a",
                        source_id="rss-1",
                    ),
                    article(
                        title="宁德时代与供应商签署长期协议",
                        url="https://finance.example.test/b",
                        published_at="2026-07-21T09:00:00Z",
                        source_id="rss-2",
                    ),
                ],
            ),
            source(
                "google_news_cn",
                "google_news",
                [
                    article(
                        title="宁德时代发布新一代快充电池产品",
                        url="https://media.example.test/c",
                        published_at="2026-07-22T07:00:00Z",
                        source_id="google-1",
                    )
                ],
            ),
        ),
        resolver=AShareEntityResolver((CATL, MOUTAI)),
    )

    assert len(batch.evidence) == 3
    assert len(batch.events) == 2
    duplicated = next(item for item in batch.events if item.source_count == 2)
    assert duplicated.source_keys == ("google_news_cn", "rss_finance")
    assert len(duplicated.evidence_ids) == 2


def test_inference_requires_model_prompt_and_version_metadata() -> None:
    batch = collect_intelligence(
        (
            source(
                "rss_finance",
                "rss",
                [article(title="贵州茅台召开股东大会", url="https://finance.example.test/moutai")],
            ),
        ),
        resolver=AShareEntityResolver((CATL, MOUTAI)),
    )
    event = batch.events[0]

    enriched = attach_event_inference(
        event,
        provider="deepseek",
        model_id="deepseek-reasoner",
        prompt_id="a-share-event-impact",
        prompt_version="v1.2.0",
        generated_at="2026-07-22T09:00:00Z",
        output={"impact": "neutral", "confidence": 0.64},
    )

    assert enriched.inference is not None
    assert enriched.inference.evidence_ids == event.evidence_ids
    assert enriched.inference.model_id == "deepseek-reasoner"
    assert enriched.inference.prompt_version == "v1.2.0"
    with pytest.raises(ValueError, match="model_id"):
        attach_event_inference(
            event,
            provider="deepseek",
            model_id="",
            prompt_id="a-share-event-impact",
            prompt_version="v1",
            generated_at="2026-07-22T09:00:00Z",
            output={},
        )


def test_source_failure_is_visible_without_discarding_healthy_coverage() -> None:
    batch = collect_intelligence(
        (
            source(
                "rss_finance",
                "rss",
                [article(title="宁德时代公布经营数据", url="https://finance.example.test/catl")],
            ),
            source("google_news_cn", "google_news", RuntimeError("upstream unavailable")),
        ),
        resolver=AShareEntityResolver((CATL, MOUTAI)),
    )

    assert len(batch.evidence) == 1
    assert batch.outcomes["rss_finance"].publishable is True
    assert batch.outcomes["google_news_cn"].publishable is False
    assert len(batch.coverage_gaps) == 1
    gap = batch.coverage_gaps[0]
    assert gap.source_key == "google_news_cn"
    assert gap.status == "failed"
    assert "upstream unavailable" in gap.reason
    assert len(gap.manifest_hash) == 64


def test_official_monitor_rejects_cross_host_discovery_as_non_authoritative() -> None:
    batch = collect_intelligence(
        (
            source(
                "szse_monitor",
                "official_monitor",
                [
                    article(
                        title="宁德时代公告",
                        url="https://mirror.example.test/fake-announcement",
                    )
                ],
                source_url="https://www.szse.cn/disclosure/",
            ),
        ),
        resolver=AShareEntityResolver((CATL, MOUTAI)),
    )

    assert batch.evidence == ()
    assert batch.events == ()
    assert len(batch.coverage_gaps) == 1
    attempt = batch.outcomes["szse_monitor"].attempts[0]
    assert attempt.records[0].rejection_reason == "official monitor item left configured host"
    assert attempt.records[0].violations == ("official_host_mismatch",)
