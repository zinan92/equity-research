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
from data_core.research_object_publish import ResearchObjectPublisher  # noqa: E402
from data_core.research_object_read import CanonicalResearchReader  # noqa: E402
from data_core.contracts import SourceManifest  # noqa: E402
from data_core.fixtures import AS_OF, KNOWN_AT, fixture_payload  # noqa: E402


FACTS = {
    ResearchObjectType.THESIS: {"company_id": "company-v1:catl", "statement": "Demand remains resilient.", "scope": "battery demand", "time_horizon": "12m"},
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
        raw_hashes=kwargs.pop("raw_hashes", ("a" * 64,)),
        snapshot_id=kwargs.pop("snapshot_id", "core_fixture_test"),
        facts=kwargs.pop("facts", FACTS[kind]),
        judgments=kwargs.pop("judgments", {}),
        model_version=kwargs.pop("model_version", None),
        revision_of=revision_of,
        **kwargs,
    )


class ResearchObjectContractTests(unittest.TestCase):
    def authority(self) -> tuple[DataFoundation, str, str]:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        foundation = DataFoundation(Path(directory.name) / "canonical.db")
        manifest = SourceManifest(
            source_key="research_object_fixture_v1", domain_scope="market", authority_tier="canonical",
            provider_version="fixture-1", schema_version="fixture-1", license_status="internal_test_only",
            source_url="fixture://research-object-v1", quality_flags=("fixture", "not_real_time"),
        )
        run = foundation.ingest_fixture(fixture_payload(), manifest)
        snapshot = foundation.create_snapshot(run["run_id"], as_of=AS_OF, known_at=KNOWN_AT)
        return foundation, run["raw_hash"], snapshot["snapshot_id"]

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
        foundation, raw_hash, snapshot_id = self.authority()
        store = ResearchObjectStore(foundation.connect)
        first = store.append(item(ResearchObjectType.COMPANY, raw_hashes=(raw_hash,), snapshot_id=snapshot_id))
        self.assertFalse(first["reused"])
        self.assertTrue(store.append(item(ResearchObjectType.COMPANY, raw_hashes=(raw_hash,), snapshot_id=snapshot_id))["reused"])
        second = item(ResearchObjectType.COMPANY, revision=2, revision_of=first["object_hash"], raw_hashes=(raw_hash,), snapshot_id=snapshot_id)
        store.append(second)
        history = store.history(second.object_id)
        self.assertEqual([row["revision"] for row in history], [1, 2])
        self.assertEqual(store.replay(second.object_id)["status"], "passed")
        with self.assertRaisesRegex(ValueError, "consecutive"):
            store.append(item(ResearchObjectType.COMPANY, revision=4, revision_of=first["object_hash"], raw_hashes=(raw_hash,), snapshot_id=snapshot_id))
        with self.assertRaisesRegex(ValueError, "unknown raw evidence"):
            store.append(item(ResearchObjectType.DOSSIER, raw_hashes=("b" * 64,), snapshot_id=snapshot_id))
        with foundation.connect() as connection:
            with self.assertRaisesRegex(Exception, "append-only"):
                connection.execute("UPDATE core_research_object_revisions SET state='blocked' WHERE object_id=?", (second.object_id,))

    def test_initialize_rebuilds_legacy_object_check_without_losing_rows(self) -> None:
        foundation, raw_hash, snapshot_id = self.authority()
        store = ResearchObjectStore(foundation.connect)
        saved = store.append(
            item(ResearchObjectType.COMPANY, raw_hashes=(raw_hash,), snapshot_id=snapshot_id)
        )
        with foundation.connect() as connection:
            connection.execute("DROP TRIGGER core_research_object_revisions_no_update")
            connection.execute("DROP TRIGGER core_research_object_revisions_no_delete")
            connection.execute("ALTER TABLE core_research_object_revisions RENAME TO legacy")
            connection.execute("CREATE TABLE core_research_object_revisions AS SELECT * FROM legacy")
            connection.execute("DROP TABLE legacy")
            connection.commit()
        foundation.initialize()
        with foundation.connect() as connection:
            sql = connection.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='core_research_object_revisions'").fetchone()[0]
            self.assertIn("'thesis'", sql)
            self.assertEqual(
                connection.execute(
                    "SELECT object_hash FROM core_research_object_revisions WHERE object_id=?",
                    ("research-v1:company:catl",),
                ).fetchone()[0],
                saved["object_hash"],
            )
            with self.assertRaisesRegex(Exception, "append-only"):
                connection.execute("UPDATE core_research_object_revisions SET state='blocked'")

    def test_atomic_publisher_preserves_last_good_on_failure(self) -> None:
        foundation, raw_hash, snapshot_id = self.authority()
        publisher = ResearchObjectPublisher(foundation.connect)
        good = item(ResearchObjectType.COMPANY, raw_hashes=(raw_hash,), snapshot_id=snapshot_id)
        accepted = publisher.publish((good,))
        self.assertEqual(accepted["status"], "accepted")
        self.assertFalse(accepted["records"][0]["reused"])
        bad = item(ResearchObjectType.DOSSIER, raw_hashes=("b" * 64,), snapshot_id=snapshot_id)
        blocked = publisher.publish((item(ResearchObjectType.CATALYST, raw_hashes=(raw_hash,), snapshot_id=snapshot_id), bad))
        self.assertEqual(blocked["status"], "blocked")
        store = ResearchObjectStore(foundation.connect)
        self.assertEqual(len(store.history(good.object_id)), 1)
        self.assertEqual(store.history("research-v1:catalyst:catl"), [])
        self.assertTrue(publisher.publish((good,))["records"][0]["reused"])

    def test_reader_fails_closed_when_fixture_is_disabled(self) -> None:
        foundation, raw_hash, snapshot_id = self.authority()
        publisher = ResearchObjectPublisher(foundation.connect)
        company = item(ResearchObjectType.COMPANY, raw_hashes=(raw_hash,), snapshot_id=snapshot_id)
        dossier = item(ResearchObjectType.DOSSIER, raw_hashes=(raw_hash,), snapshot_id=snapshot_id)
        self.assertEqual(publisher.publish((company, dossier))["status"], "accepted")
        self.assertEqual(CanonicalResearchReader(foundation.connect).by_ticker("300750.SZ")["reason"], "fixture_or_nonreal_snapshot")
        visible = CanonicalResearchReader(foundation.connect, allow_fixture=True).by_ticker("300750.SZ")
        self.assertEqual(visible["status"], "accepted")
        self.assertEqual(set(visible["objects"]), {"company", "dossier"})


if __name__ == "__main__":
    unittest.main()
