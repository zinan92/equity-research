"""Strict E4-S4 coverage gate; it reports gaps rather than manufacturing success."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping

from .contracts import digest


E4_ACCEPTANCE_SCHEMA_VERSION = "e4-s4-real-coverage-acceptance-v1"
IDENTITY_REQUIRED = 100
REPORT_MODEL_REQUIRED = 95
TIER_AB_REQUIRED = 80
SPOT_AUDIT_REQUIRED = 20


@dataclass(frozen=True)
class TickerCoverage:
    ticker: str
    data_kind: str
    report_model_hash: str | None
    tier: str | None
    numeric_spot_audit: bool
    page_citation_spot_audit: bool
    blockers: tuple[str, ...]

    def validated(self) -> "TickerCoverage":
        if not self.ticker or self.data_kind not in {"real", "fixture", "cached", "runtime_only_audit"}:
            raise ValueError("ticker coverage identity is invalid")
        if self.report_model_hash is not None and (len(self.report_model_hash) != 64 or any(char not in "0123456789abcdef" for char in self.report_model_hash)):
            raise ValueError("report model hash must be SHA-256")
        if self.tier not in {None, "A", "B", "C", "missing"}:
            raise ValueError("unsupported degradation tier")
        return self


def _coverage_for(ticker: str, input_rows: Mapping[str, Mapping[str, Any]]) -> TickerCoverage:
    row = input_rows.get(ticker.upper())
    if row is None:
        return TickerCoverage(ticker.upper(), "missing", None, None, False, False, ("missing_canonical_evidence",))
    blockers = tuple(sorted({str(item) for item in row.get("blockers") or []}))
    return TickerCoverage(
        ticker=ticker.upper(), data_kind=str(row.get("data_kind") or "missing"), report_model_hash=row.get("report_model_hash"),
        tier=row.get("tier"), numeric_spot_audit=bool(row.get("numeric_spot_audit")),
        page_citation_spot_audit=bool(row.get("page_citation_spot_audit")), blockers=blockers,
    ).validated()


def evaluate_e4_s4(
    security_master_receipt: Mapping[str, Any], *, coverage_rows: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Evaluate all fixed E4-S4 gates over a real runtime identity receipt."""
    if security_master_receipt.get("schema_version") != "ashare-security-master-v1":
        raise ValueError("E4-S4 requires an A-share security-master receipt")
    boundary = security_master_receipt.get("truth_boundary") or {}
    if security_master_receipt.get("data_kind") != "real" or not boundary.get("identity_only"):
        raise ValueError("E4-S4 rejects non-real or unbounded identity corpus")
    records = security_master_receipt.get("records")
    if not isinstance(records, list):
        raise ValueError("security-master records are invalid")
    tickers = [str(record.get("ticker") or "").upper() for record in records]
    if any(not ticker for ticker in tickers) or len(set(tickers)) != len(tickers):
        raise ValueError("security-master identities are missing or duplicated")
    selected = tuple(sorted(tickers)[:IDENTITY_REQUIRED])
    rows = coverage_rows or {}
    coverage = tuple(_coverage_for(ticker, rows) for ticker in selected)
    report_models = [item for item in coverage if item.data_kind == "real" and item.report_model_hash]
    tier_ab = [item for item in report_models if item.tier in {"A", "B"}]
    spot_audits = [item for item in report_models if item.numeric_spot_audit and item.page_citation_spot_audit]
    failures = {
        item.ticker: list(item.blockers or (
            "non_real_coverage" if item.data_kind != "real" else "missing_report_model" if not item.report_model_hash else "tier_or_spot_audit_gap"
        ))
        for item in coverage
        if not (item.data_kind == "real" and item.report_model_hash and item.tier in {"A", "B"} and item.numeric_spot_audit and item.page_citation_spot_audit)
    }
    counts = {
        "identity": len(selected), "report_models": len(report_models), "tier_a_or_b": len(tier_ab), "spot_audits": len(spot_audits),
    }
    thresholds = {
        "identity": IDENTITY_REQUIRED, "report_models": REPORT_MODEL_REQUIRED,
        "tier_a_or_b": TIER_AB_REQUIRED, "spot_audits": SPOT_AUDIT_REQUIRED,
    }
    passed = all(counts[name] >= required for name, required in thresholds.items())
    receipt = {
        "schema_version": E4_ACCEPTANCE_SCHEMA_VERSION,
        "status": "passed" if passed else "failed",
        "identity_receipt_hash": security_master_receipt.get("receipt_hash"),
        "counts": counts, "thresholds": thresholds,
        "ticker_coverage": [asdict(item) for item in coverage],
        "failure_taxonomy": failures,
        "truth_boundary": {
            "identity_only_corpus_is_not_evidence": True,
            "fixture_or_cached_coverage_is_not_counted": True,
            "thresholds_are_not_relaxed": True,
        },
    }
    receipt["receipt_hash"] = digest(receipt)
    return receipt
