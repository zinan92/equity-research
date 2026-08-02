"""Issuer profiles for the generic Round 7 whole-dossier runner.

Profiles are small, versioned input contracts.  They change evidence selection
and writing guidance for an issuer class, but never change the Round 7 chapter
order, the validator, or the Tier/B6 safety semantics.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


PROFILE_SCHEMA_VERSION = "round7-issuer-profile-v1"


def profile_hash(profile: Mapping[str, Any]) -> str:
    payload = {key: value for key, value in profile.items() if key != "profile_hash"}
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def load_profile(path: Path, *, ticker: str) -> dict[str, Any]:
    profile = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(profile, dict):
        raise ValueError("issuer profile must be a JSON object")
    if profile.get("schema_version") != PROFILE_SCHEMA_VERSION:
        raise ValueError("issuer profile schema mismatch")
    if str(profile.get("ticker") or "").upper() != ticker.upper():
        raise ValueError("issuer profile ticker mismatch")
    expected = profile_hash(profile)
    if profile.get("profile_hash") != expected:
        raise ValueError("issuer profile hash mismatch")
    issuer = profile.get("issuer")
    if not isinstance(issuer, Mapping) or str(issuer.get("short_name") or "").strip() == "":
        raise ValueError("issuer profile is missing issuer identity")
    if not isinstance(profile.get("section_rules"), Mapping):
        raise ValueError("issuer profile is missing section_rules")
    return profile


def section_rule(profile: Mapping[str, Any] | None, section_id: str, default: Mapping[str, Any]) -> dict[str, Any]:
    if not profile:
        return dict(default)
    rules = profile.get("section_rules") or {}
    override = rules.get(section_id)
    if not isinstance(override, Mapping):
        return dict(default)
    merged = dict(default)
    merged.update({key: value for key, value in override.items() if value is not None})
    return merged


def issuer_identity(profile: Mapping[str, Any] | None, fallback: Mapping[str, Any]) -> dict[str, Any]:
    if not profile:
        return dict(fallback)
    identity = dict(profile.get("issuer") or {})
    identity.setdefault("ticker", profile.get("ticker"))
    identity.setdefault("sector", profile.get("sector"))
    return identity


def profile_payload(profile: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not profile:
        return None
    return {
        "profile_id": profile.get("profile_id"),
        "profile_hash": profile.get("profile_hash"),
        "sector": profile.get("sector"),
        "business_lines": list(profile.get("business_lines") or []),
        # Receipt hashes keep every whole-chapter request replay-bound without
        # turning provenance into model-generated facts.
        "source_receipts": dict(profile.get("source_receipts") or {}),
    }
