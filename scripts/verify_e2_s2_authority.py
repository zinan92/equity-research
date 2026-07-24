"""E2-S2 acceptance receipt over the existing A4/A5 authority contract."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

PRODUCT = Path(__file__).resolve().parents[1] / "product"
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from data_core.contracts import SourceManifest
from data_core.fixtures import AS_OF, KNOWN_AT, fixture_payload
from data_core.store import DataFoundation


def verify() -> dict:
    with tempfile.TemporaryDirectory() as directory:
        foundation = DataFoundation(Path(directory) / "authority.db")
        manifest = SourceManifest(
            source_key="e2_s2_fixture_v1", domain_scope="market", authority_tier="canonical",
            provider_version="fixture-1", schema_version="fixture-1", license_status="internal_test_only",
            source_url="fixture://e2-s2", quality_flags=("fixture", "not_real_time"),
        )
        first = foundation.ingest_fixture(fixture_payload(), manifest)
        second = foundation.ingest_fixture(fixture_payload(), manifest)
        snapshot = foundation.create_snapshot(first["run_id"], as_of=AS_OF, known_at=KNOWN_AT)
        replay = foundation.replay_digest(snapshot["snapshot_id"])
        quality = foundation.quality_evaluation(first["run_id"], as_of=AS_OF, known_at=KNOWN_AT)
        return {"schema_version": "e2-s2-authority-acceptance-v1", "idempotent_retry": second["reused"],
                "snapshot_id": snapshot["snapshot_id"], "replay_digest": replay,
                "quality_blockers": quality["blockers"], "data_kind": first["data_kind"]}


if __name__ == "__main__":
    import json
    print(json.dumps(verify(), ensure_ascii=False, sort_keys=True))
