from __future__ import annotations

import sys
from pathlib import Path

import pytest

PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT))

from data_core.research_outcomes import build_outcome_receipt  # noqa: E402


REPORT = {
    "ticker": "300750.SZ", "as_of": "2026-07-20", "known_at": "2026-07-20T15:00:00+08:00",
    "report_hash": "a" * 64, "generated_from": {"snapshot_id": "snapshot-1"}, "market": {"price": 100.0},
}


def test_outcome_is_separate_from_frozen_research_and_attributes_components() -> None:
    receipt = build_outcome_receipt(
        publication_id="pub-1", snapshot_id="snapshot-1", ticker="300750.SZ", frozen_report=REPORT,
        outcome_observations=({"known_at": "2026-08-20T15:00:00+08:00", "company_price": 120.0,
                               "benchmark_price": 110.0, "benchmark_start_price": 100.0,
                               "industry_price": 105.0, "industry_start_price": 100.0,
                               "fundamental_observation": "revenue beat"},),
    )
    row = receipt["outcome_window"][0]
    assert row["company_return"] == pytest.approx(0.2)
    assert row["benchmark_return"] == pytest.approx(0.1)
    assert row["relative_return"] == pytest.approx(0.1)
    assert row["industry_return"] == pytest.approx(0.05)
    assert receipt["frozen_research"]["research_inputs_mutable"] is False
    assert "action" in receipt["boundary"]


def test_pre_cutoff_data_and_identity_mismatches_fail_closed() -> None:
    with pytest.raises(ValueError, match="after frozen research cutoff"):
        build_outcome_receipt(publication_id="pub-1", snapshot_id="snapshot-1", ticker="300750.SZ", frozen_report=REPORT, outcome_observations=({"known_at": "2026-07-20T15:00:00+08:00", "company_price": 110.0, "benchmark_price": 100.0, "benchmark_start_price": 100.0},))
    with pytest.raises(ValueError, match="snapshot mismatch"):
        build_outcome_receipt(publication_id="pub-1", snapshot_id="wrong", ticker="300750.SZ", frozen_report=REPORT, outcome_observations=())
