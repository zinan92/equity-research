from __future__ import annotations

import sys
from pathlib import Path
import unittest


PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT))

from data_core.market_regime_weekly_ranking import (  # noqa: E402
    WeeklyRankingError,
    build_ranking_request,
    compile_ranking,
    validate_ranking_output,
)
from data_core.market_regime_weekly_source import WEEKLY_KEYS  # noqa: E402


def vector(*, unavailable: str | None = None) -> list[dict]:
    result = []
    for index, key in enumerate(WEEKLY_KEYS):
        if key == unavailable:
            result.append({"asset_key": key, "status": "analysis_unavailable", "reason_code": "source_missing"})
            continue
        analysis_id = f"analysis:{key}"
        evidence_id = f"evidence:{key}"
        result.append(
            {
                "asset_key": key,
                "status": "validated",
                "analysis_id": analysis_id,
                "output": {
                    "asset_key": key,
                    "agreement": "aligned_bullish" if index % 2 == 0 else "mixed",
                    "synthesis": {"text": f"{key} synthesis", "evidence_ids": [evidence_id]},
                    "confirmation": {"text": "confirm", "evidence_ids": [evidence_id]},
                    "invalidation": {"text": "invalidate", "evidence_ids": [evidence_id]},
                    "opportunity_state": "wait",
                    "rationale": {"text": "rationale", "evidence_ids": [evidence_id]},
                },
            }
        )
    return result


def valid_output(request: dict) -> dict:
    entries = []
    rank = 0
    for slot in request["slots"]:
        if slot["status"] == "analysis_unavailable":
            entries.append({"asset_key": slot["asset_key"], "status": "unavailable", "rank": None, "text": "数据不可用", "evidence_ids": []})
        else:
            rank += 1
            entries.append({"asset_key": slot["asset_key"], "status": "wait", "rank": rank, "text": "等待确认", "evidence_ids": [slot["analysis_id"], *slot["evidence_ids"][:1]]})
    return {
        "generation_status": "model_generated_unreviewed",
        "important_changes": [{"text": "本周变化", "evidence_ids": [request["slots"][0]["analysis_id"]]}],
        "ordered_assets": entries,
    }


class WeeklyRankingTest(unittest.TestCase):
    def test_request_contains_the_ordered_terminal_vector_only(self) -> None:
        request = build_ranking_request(vector(unavailable="gold"))
        self.assertEqual(request["asset_keys"], list(WEEKLY_KEYS))
        self.assertEqual(len(request["slots"]), 17)
        self.assertEqual(next(item for item in request["slots"] if item["asset_key"] == "gold")["status"], "analysis_unavailable")
        self.assertNotIn("open", repr(request))

    def test_valid_ranking_accepts_all_slots_and_preserves_unavailable(self) -> None:
        request = build_ranking_request(vector(unavailable="gold"))
        output = validate_ranking_output(valid_output(request), request)
        gold = next(item for item in output["ordered_assets"] if item["asset_key"] == "gold")
        self.assertEqual(gold["status"], "unavailable")
        self.assertEqual(len(output["ordered_assets"]), 17)

    def test_unknown_citation_fails_closed(self) -> None:
        request = build_ranking_request(vector())
        output = valid_output(request)
        output["important_changes"][0]["evidence_ids"] = ["not-known"]
        with self.assertRaisesRegex(WeeklyRankingError, "ranking_evidence_unknown"):
            validate_ranking_output(output, request)

    def test_duplicate_or_missing_rank_fails_closed(self) -> None:
        request = build_ranking_request(vector())
        output = valid_output(request)
        output["ordered_assets"][1]["rank"] = output["ordered_assets"][0]["rank"]
        with self.assertRaisesRegex(WeeklyRankingError, "ranking_order_invalid"):
            validate_ranking_output(output, request)

    def test_provider_failure_returns_typed_unavailable_ranking(self) -> None:
        request = build_ranking_request(vector())
        artifact = compile_ranking(request, lambda _: (_ for _ in ()).throw(RuntimeError("provider detail")))
        self.assertEqual(artifact["generation_status"], "ranking_unavailable")
        self.assertEqual(artifact["failure_code"], "provider_error")

    def test_compile_binds_request_identity_and_receipt(self) -> None:
        request = build_ranking_request(vector())
        artifact = compile_ranking(request, lambda _: valid_output(request))
        self.assertTrue(artifact["ranking_id"].startswith("market-regime-weekly-ranking:"))
        self.assertEqual(artifact["receipt"]["request_hash"], artifact["request_hash"])


if __name__ == "__main__":
    unittest.main()
