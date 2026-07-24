from __future__ import annotations

import sys
import unittest
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

PRODUCT = Path(__file__).resolve().parents[1]
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from data_core.company_positions import REVIEW_TARGETS  # noqa: E402
from data_core.n3_dossier_batch import (  # noqa: E402
    N3_DOSSIER_BATCH_SIZE,
    compile_batch,
    compile_position,
    selected_positions,
    selection_identity,
)


class N3DossierBatchTest(unittest.TestCase):
    def setUp(self) -> None:
        self.positions = selected_positions()
        self.payloads = {item.ticker: (item.ticker + " official PDF").encode() for item in self.positions}
        self.positions = tuple(
            replace(item, citation=(item.citation[0], item.citation[1], sha256(self.payloads[item.ticker]).hexdigest()))
            for item in self.positions
        )

    def test_selection_is_deterministic_and_uses_accepted_positions(self) -> None:
        canonical = selected_positions()
        self.assertEqual(len(canonical), N3_DOSSIER_BATCH_SIZE)
        self.assertEqual(tuple(item.ticker for item in canonical), tuple(sorted(item.ticker for item in canonical)))
        self.assertTrue(all(item.status == "accepted" and item.citation for item in canonical))
        self.assertEqual(selection_identity(canonical), selection_identity(tuple(canonical)))

    def test_batch_compiles_partial_no_action_receipts(self) -> None:
        receipt = compile_batch(
            known_at="2025-05-01T00:00:00Z",
            positions=self.positions,
            fetcher=lambda item: self.payloads[item.ticker],
        )
        self.assertEqual(receipt["counts"], {"requested": 20, "resolved": 20, "compiled": 20, "failed": 0, "no_action": 20})
        self.assertTrue(receipt["truth_boundary"]["partial_evidence_bound"])
        self.assertTrue(all(row["decision_action"] == "no_action" for row in receipt["rows"]))
        self.assertTrue(all(row["gaps"] for row in receipt["rows"]))

    def test_raw_hash_mismatch_fails_without_dossier(self) -> None:
        position = self.positions[0]
        with self.assertRaisesRegex(ValueError, "raw_hash_mismatch"):
            compile_position(position, known_at="2025-05-01T00:00:00Z", fetcher=lambda _item: b"wrong")

    def test_partial_failure_is_typed_and_does_not_promote(self) -> None:
        failed = self.positions[1].ticker
        receipt = compile_batch(
            known_at="2025-05-01T00:00:00Z",
            positions=self.positions,
            fetcher=lambda item: b"wrong" if item.ticker == failed else self.payloads[item.ticker],
        )
        self.assertEqual(receipt["counts"], {"requested": 20, "resolved": 20, "compiled": 19, "failed": 1, "no_action": 19})
        row = next(item for item in receipt["rows"] if item["ticker"] == failed)
        self.assertEqual(row["status"], "failed")
        self.assertEqual(row["error"], "ValueError")

    def test_resume_reuses_only_exact_compiled_rows_and_retries_failures(self) -> None:
        first = compile_batch(
            known_at="2025-05-01T00:00:00Z",
            positions=self.positions,
            fetcher=lambda item: b"wrong" if item.ticker == self.positions[0].ticker else self.payloads[item.ticker],
        )
        calls: list[str] = []
        resumed = compile_batch(
            known_at="2025-05-01T00:00:00Z",
            positions=self.positions,
            prior_receipt=first,
            fetcher=lambda item: (calls.append(item.ticker), self.payloads[item.ticker])[1],
        )
        self.assertEqual(resumed["counts"], {"requested": 20, "resolved": 20, "compiled": 20, "failed": 0, "no_action": 20})
        self.assertEqual(calls, [self.positions[0].ticker])

    def test_resume_rejects_different_citation_selection(self) -> None:
        first = compile_batch(known_at="2025-05-01T00:00:00Z", positions=self.positions, fetcher=lambda item: self.payloads[item.ticker])
        changed = (replace(self.positions[0], citation=(self.positions[0].citation[0], self.positions[0].citation[1], "a" * 64)), *self.positions[1:])
        with self.assertRaisesRegex(ValueError, "selection identity mismatch"):
            compile_batch(known_at="2025-05-01T00:00:00Z", positions=changed, prior_receipt=first, fetcher=lambda item: self.payloads[item.ticker])


if __name__ == "__main__":
    unittest.main()
