#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRODUCT = ROOT / "product"
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from data_core import DataFoundation, SourceManifest  # noqa: E402
from data_core.fixtures import AS_OF, KNOWN_AT, fixture_payload  # noqa: E402
import data_core.store as foundation_store  # noqa: E402


def verify() -> dict:
    foundation_store._now = lambda: "2026-07-21T08:00:00Z"
    manifest = SourceManifest(
        source_key="acceptance_fixture_v1",
        domain_scope="market",
        authority_tier="canonical",
        provider_version="fixture-1",
        schema_version="fixture-1",
        license_status="internal_test_only",
        source_url="fixture://data-foundation-v1",
        quality_flags=("fixture", "not_real_time"),
    )
    with tempfile.TemporaryDirectory() as temp:
        source = DataFoundation(Path(temp) / "source.db")
        ingestion = source.ingest_fixture(fixture_payload(), manifest)
        reused = source.ingest_fixture(fixture_payload(), manifest)
        snapshot = source.create_snapshot(ingestion["run_id"], as_of=AS_OF, known_at=KNOWN_AT)
        replay_digest = source.replay_digest(snapshot["snapshot_id"])
        bundle = source.export_bundle()
        restored = DataFoundation(Path(temp) / "restored.db")
        restored.import_bundle(bundle)
        restored_digest = restored.replay_digest(snapshot["snapshot_id"])
        if replay_digest != restored_digest:
            raise RuntimeError("restore replay digest mismatch")
        return {
            "status": "passed",
            "fixture_only": True,
            "schema_version": bundle["schema_version"],
            "ingestion": {**ingestion, "second_run_reused": reused["reused"]},
            "coverage": source.coverage_report(),
            "snapshot": snapshot,
            "replay_digest": replay_digest,
            "restore": {"status": "passed", "replay_digest": restored_digest},
        }


if __name__ == "__main__":
    print(json.dumps(verify(), ensure_ascii=False, sort_keys=True, indent=2))
