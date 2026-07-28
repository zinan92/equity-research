from __future__ import annotations

class IndustryIntelligenceError(RuntimeError):
    pass


def load_snapshot() -> dict:
    """Reject the retired benchmark-derived snapshot.

    Canonical E1--E3 data must be introduced through the authority/evidence
    path.  This module intentionally has no fallback while that replacement is
    unavailable, so an archived score or dossier can never look like product
    research.
    """
    raise IndustryIntelligenceError(
        "industry intelligence is unavailable until canonical evidence-backed data is published"
    )


def overview_payload() -> dict:
    return load_snapshot()


def dossier_payload(code: str) -> dict | None:
    del code
    return load_snapshot()
