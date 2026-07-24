"""E2-S3 acceptance receipt over existing corporate-action and valuation contracts."""
from __future__ import annotations

import subprocess
import sys


TESTS = (
    "product.tests.test_data_foundation.DataFoundationTest.test_quality_gate_blocks_missing_corporate_action_version",
    "product.tests.test_data_foundation.DataFoundationTest.test_future_corporate_action_cannot_back_current_adjustment_factor",
    "product.tests.test_a_share_pit_fundamentals.ASharePitFundamentalsTest.test_valuation_conflict_fails_closed",
    "product.tests.test_market_snapshot.MarketSnapshotTest.test_valuation_is_not_fabricated_from_bar",
    "product.tests.test_market_snapshot.MarketSnapshotTest.test_fx_records_are_frozen_by_trade_date",
)


def verify() -> dict:
    command = [sys.executable, "-m", "unittest", *TESTS, "-q"]
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    return {"schema_version": "e2-s3-actions-acceptance-v1", "status": "passed" if completed.returncode == 0 else "failed",
            "tests": list(TESTS), "returncode": completed.returncode}


if __name__ == "__main__":
    import json
    receipt = verify()
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    raise SystemExit(receipt["returncode"])
