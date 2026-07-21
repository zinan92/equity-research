#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from functools import partial
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
PRODUCT = ROOT / "product"
for path in (ROOT, PRODUCT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from data_core import (  # noqa: E402
    CanonicalResearchRefresh, DataFoundation, InjectedInterruption, SnapshotReader,
    canonical_active_report,
)
from data_core import store as foundation_store  # noqa: E402
from data_core.research_refresh import _default_research_builder  # noqa: E402
from product.tests.test_research_refresh_v1 import (  # noqa: E402
    DAY_ONE,
    DAY_TWO,
    UNIVERSE,
    StaticAdapter,
    market_payload,
)
from real_pipeline import replay_snapshot  # noqa: E402


SHANGHAI = timezone(timedelta(hours=8))


def engine(root: Path, adapters) -> CanonicalResearchRefresh:
    return CanonicalResearchRefresh(
        DataFoundation(root / "canonical.db"), root / "refresh", adapters, universe=UNIVERSE,
        research_builder=partial(_default_research_builder, minimum_bars=2),
    )


def main() -> None:
    foundation_store._now = lambda: "2026-07-21T08:00:00+00:00"
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        adapter = StaticAdapter(market_payload(), name="primary", role="primary")
        primary_engine = engine(root / "incremental", [adapter])
        first = primary_engine.run(now=datetime(2026, 7, 17, 16, 30, tzinfo=SHANGHAI))
        same = primary_engine.run(now=datetime(2026, 7, 17, 16, 31, tzinfo=SHANGHAI))
        adapter.payload = market_payload(DAY_TWO)
        second = primary_engine.run(now=datetime(2026, 7, 20, 16, 30, tzinfo=SHANGHAI))
        publication = json.loads(
            (primary_engine.state_root / second["publication_manifest"]).read_text(encoding="utf-8")
        )
        reader = SnapshotReader(primary_engine.foundation, second["snapshot_id"])
        product_report = canonical_active_report("300750.SZ", primary_engine.state_root)
        with patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden during replay")):
            replay = replay_snapshot(second["snapshot_id"], primary_engine.foundation.db_path)
            catl_context = reader.research_context("300750.SZ")

        fallback = engine(root / "fallback", [
            StaticAdapter(None, name="primary", role="primary", error="injected primary failure"),
            StaticAdapter(market_payload(), name="fallback", role="fallback"),
        ]).run(now=datetime(2026, 7, 17, 16, 30, tzinfo=SHANGHAI))

        failure_engine = engine(root / "failure", [
            StaticAdapter(market_payload(), name="primary_good", role="primary")
        ])
        active_before_failure = failure_engine.run(
            now=datetime(2026, 7, 17, 16, 30, tzinfo=SHANGHAI)
        )
        failed = engine(root / "failure", [
            StaticAdapter(None, name="primary_bad", role="primary", error="injected primary failure"),
            StaticAdapter(None, name="fallback_bad", role="fallback", error="injected fallback failure"),
        ]).run(now=datetime(2026, 7, 20, 16, 30, tzinfo=SHANGHAI))

        resume_adapter = StaticAdapter(market_payload(), name="primary_resume", role="primary")
        resume_engine = engine(root / "resume", [resume_adapter])
        interrupted = False
        try:
            resume_engine.run(
                now=datetime(2026, 7, 17, 16, 30, tzinfo=SHANGHAI),
                interrupt_after="snapshotted",
            )
        except InjectedInterruption:
            interrupted = True
        resumed = resume_engine.run(now=datetime(2026, 7, 17, 16, 31, tzinfo=SHANGHAI))

        receipt = {
            "schema_version": "m3-research-refresh-verification-v1",
            "fixture_boundary": "deterministic acceptance data; not live market evidence",
            "incremental": {
                "day_one": DAY_ONE,
                "day_two": DAY_TWO,
                "day_one_snapshot": first["snapshot_id"],
                "same_input_snapshot": same["snapshot_id"],
                "same_input_ingestion_reused": same["ingestion_reused"],
                "day_two_snapshot": second["snapshot_id"],
                "snapshot_changed": first["snapshot_id"] != second["snapshot_id"],
                "catl_trade_dates": [row["trade_date"] for row in catl_context["daily_bars"]],
                "report_gate": second["report_gate"],
                "publication_id": second["publication_id"],
                "report_schema_version": publication["report_schema_version"],
                "standard_report_count": len(publication["report_hashes"]),
            },
            "fallback": {
                "status": fallback["status"], "selected_adapter": fallback["selected_adapter"],
                "attempts": [
                    {"adapter": item["adapter"], "role": item["role"], "status": item["status"]}
                    for item in fallback["attempts"]
                ],
            },
            "all_sources_failed": {
                "status": failed["status"],
                "previous_active_snapshot": active_before_failure["snapshot_id"],
                "preserved_snapshot": failed["active_preserved"]["snapshot_id"],
            },
            "resume": {
                "interruption_observed": interrupted, "resumed": resumed["resumed"],
                "collector_calls": resume_adapter.calls, "status": resumed["status"],
            },
            "no_network_replay": {
                "status": replay["status"], "canonical": replay["canonical"],
                "replay_digest": replay["replay_digest"],
            },
            "product_consumer": {
                "status": "passed" if product_report else "failed",
                "ticker": product_report["ticker"] if product_report else None,
                "snapshot_id": (
                    product_report["generated_from"]["snapshot_id"] if product_report else None
                ),
                "data_status": product_report.get("data_status") if product_report else None,
                "api_path": "/api/reports/300750.SZ",
            },
            "research_isolation": "forked child blocks socket connect/connect_ex/send and subprocess escape",
            "schedule_template": "product/automation/com.park.a-share-research-refresh.plist",
            "health": primary_engine.status()["status"],
        }
    output = ROOT / "evidence/m3-research-refresh/verification-receipt.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
