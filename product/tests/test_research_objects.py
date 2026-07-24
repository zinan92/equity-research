from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT))

from data_core.research_objects import (  # noqa: E402
    OBJECT_SCHEMAS,
    ResearchObject,
    ResearchObjectStore,
    ResearchObjectType,
    object_contract_descriptor,
)
from data_core.store import DataFoundation  # noqa: E402


FACTS = {
    ResearchObjectType.COMPANY: {"company_id": "company-v1:catl", "display_name": "宁德时代", "ticker": "300750.SZ"},
    ResearchObjectType.SECTOR_POSITION: {"company_id": "company-v1:catl", "sector_id": "battery", "role": "manufacturer"},
    ResearchObjectType.EVIDENCE: {"evidence_id": "evidence:filing:1", "evidence_type": "filing", "citation": "document:1#p1"},
    ResearchObjectType.CATALYST: {"company_id": "company-v1:catl", "title": "capacity ramp", "time_horizon": "12m"},
    ResearchObjectType.ROADMAP: {"company_id": "company-v1:catl", "milestone": "new product", "time_horizon": "24m"},
    ResearchObjectType.SCORE_SNAPSHOT: {"company_id": "company-v1:catl", "as_of": "2026-07-24", "score_name": "quality", "score_value": 80},
    ResearchObjectType.FALSIFIER: {"company_id": "company-v1:catl", "title": "margin miss", "trigger": "gross margin < 15%"},
    ResearchObjectType.DOSSIER: {"company_id": "company-v1:catl", "dossier_version": "v1", "as_of": "2026-07-24"},
}


def item(kind: ResearchObjectType, *, revision: int = 1, revision_of: str | None = None, **kwargs: object) -> ResearchObject:
    return ResearchObject(
        object_id=f"research-v1:{kind.value}:catl",
        object_type=kind,
        revision=revision,
        state="accepted",
        source_ref="source:official:1",
        known_at="2026-07-24T00:00:00Z",
        confidence="high",
        evidence_refs=("evidence:filing:1",),
        facts=kwargs.pop("facts", FACTS[kind]),
        judgments=kwargs.pop("judgments", {}),
        model_version=kwargs.pop("model_version", None),
        revision_of=revision_of,
        **kwargs,
    )


class ResearchObjectContractTests(unittest.TestCase):
    def test_exactly_eight_versioned_object_contracts(self) -> None:
        self.assertEqual(set(OBJECT_SCHEMAS), set(ResearchObjectType))
        descriptor = object_contract_descriptor()
        self.assertEqual(set(descriptor["object_types"]), {item.value for item in ResearchObjectType})
        for kind in ResearchObjectType:
            item(kind).validate()

    def test_judgment_requires_model_version_and_stays_separate(self) -> None:
        with self.assertRaisesRegex(ValueError, "model_version"):
            item(ResearchObjectType.CATALYST, judgments={"thesis": "research judgment"}).validate()
        valid = item(ResearchObjectType.CATALYST, judgments={"thesis": "research judgment"}, model_version="model-v1")
        self.assertNotIn("thesis", valid.facts)
        valid.validate()

    def test_invalid_fact_payload_and_revision_identity_are_rejected(self) -> None:
        bad = item(ResearchObjectType.COMPANY, facts={"company_id": "company-v1:catl"})
        with self.assertRaisesRegex(ValueError, "display_name"):
            bad.validate()
        with self.assertRaisesRegex(ValueError, "first revision"):
            item(ResearchObjectType.COMPANY, revision_of="x" * 64).validate()

    def test_migration_readback_and_append_only_history(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            foundation = DataFoundation(Path(directory) / "canonical.db")
            foundation.initialize()
            store = ResearchObjectStore(foundation.connect)
            first = store.append(item(ResearchObjectType.COMPANY))
            second = item(ResearchObjectType.COMPANY, revision=2, revision_of=first["object_hash"])
            store.append(second)
            history = store.history(second.object_id)
            self.assertEqual([row["revision"] for row in history], [1, 2])
            with self.assertRaisesRegex(ValueError, "consecutive"):
                store.append(item(ResearchObjectType.COMPANY, revision=4, revision_of=first["object_hash"]))
            with foundation.connect() as connection:
                with self.assertRaisesRegex(Exception, "append-only"):
                    connection.execute("UPDATE core_research_object_revisions SET state='blocked' WHERE object_id=?", (second.object_id,))


if __name__ == "__main__":
    unittest.main()
