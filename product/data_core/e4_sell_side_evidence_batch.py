"""Bounded, runtime-only B2 sell-side evidence batch for E4's real corpus."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Callable, Mapping

from .ashare import MemoryAuthoritySink
from .contracts import digest
from .e4_official_evidence_batch import load_real_identity_tickers
from .official_filings import default_http_transport
from .sell_side_archive import (
    RateLimitedRetryTransport,
    SellSideArchiveBatch,
    build_sell_side_runtime,
    sync_sell_side_archive,
)


E4_SELL_SIDE_EVIDENCE_BATCH_SCHEMA_VERSION = "e4-s4-sell-side-evidence-batch-v1"
E4_SELL_SIDE_EVIDENCE_CHECKPOINT_SCHEMA_VERSION = "e4-s4-sell-side-evidence-checkpoint-v1"
SyncFn = Callable[..., SellSideArchiveBatch]


class RuntimeRawAuthoritySink:
    """Persist only verified ingestion payloads beneath an ignored runtime root."""

    def __init__(self, raw_root: Path) -> None:
        self.raw_root = raw_root.resolve()
        self.paths: dict[str, str] = {}

    def persist_attempt(self, attempt: Any) -> None:
        raw, fetched = getattr(attempt, "raw", None), getattr(attempt, "fetched", None)
        if raw is None or fetched is None:
            return
        body = bytes(getattr(fetched, "body", b""))
        raw_hash = str(getattr(raw, "raw_hash", ""))
        if len(raw_hash) != 64 or hashlib.sha256(body).hexdigest() != raw_hash:
            raise ValueError("runtime raw bytes do not match ingestion raw hash")
        target = (self.raw_root / raw_hash[:2] / f"{raw_hash}.bin").resolve()
        try:
            target.relative_to(self.raw_root)
        except ValueError as exc:
            raise ValueError("runtime raw path escapes configured root") from exc
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.read_bytes() != body:
            raise ValueError("runtime raw hash collision")
        if not target.exists():
            temporary = target.with_suffix(".tmp")
            temporary.write_bytes(body)
            temporary.replace(target)
        self.paths[raw_hash] = str(target)

    def path_for(self, raw_hash: str | None) -> str | None:
        path = self.paths.get(str(raw_hash or ""))
        if not path:
            return None
        candidate = Path(path)
        if not candidate.is_file() or hashlib.sha256(candidate.read_bytes()).hexdigest() != raw_hash:
            raise ValueError("runtime raw file is unavailable or hash-mismatched")
        return path


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _config(identity_receipt_path: Path, *, max_tickers: int, inter_ticker_delay_seconds: float, max_reports_per_ticker: int) -> dict[str, Any]:
    return {
        "identity_receipt_sha256": hashlib.sha256(identity_receipt_path.read_bytes()).hexdigest(),
        "max_tickers": max_tickers,
        "inter_ticker_delay_seconds": inter_ticker_delay_seconds,
        "max_reports_per_ticker": max_reports_per_ticker,
    }


def _attempt_identity(outcome: Any, *, raw_sink: RuntimeRawAuthoritySink) -> dict[str, Any]:
    attempts = tuple(getattr(outcome, "attempts", ()) or ())
    attempt = attempts[-1] if attempts else None
    raw = getattr(attempt, "raw", None)
    return {
        "status": "captured" if getattr(outcome, "publishable", False) else "failed",
        "source_url": getattr(raw, "source_url", None),
        "raw_hash": getattr(raw, "raw_hash", None),
        "storage_uri": getattr(raw, "storage_uri", None),
        "runtime_raw_path": raw_sink.path_for(getattr(raw, "raw_hash", None)) if raw else None,
        "error": getattr(attempt, "error", None),
    }


def _row_for_batch(ticker: str, batch: SellSideArchiveBatch, *, raw_sink: RuntimeRawAuthoritySink) -> dict[str, Any]:
    catalog = [_attempt_identity(outcome, raw_sink=raw_sink) for outcome in batch.catalog_outcomes]
    reports = [{
        "report_id": item.report_id, "title": item.title, "broker": item.broker,
        "published_at": item.published_at, "rating": item.rating, "pages": item.pages,
        "source_url": item.canonical_url, "archive_status": item.archive_status,
        "pdf_raw_hash": item.raw_hash, "storage_uri": item.storage_uri,
        "runtime_raw_path": raw_sink.path_for(item.raw_hash) if item.raw_hash else None, "error": item.error,
    } for item in batch.items]
    catalog_ok = bool(catalog) and all(item["status"] == "captured" for item in catalog)
    archived = sum(item["archive_status"] == "archived_pdf" for item in reports)
    metadata_only = sum(item["archive_status"] == "metadata_only" for item in reports)
    blockers: list[str] = []
    if not catalog_ok:
        blockers.append("sell_side_catalog_unavailable")
    elif not reports:
        blockers.append("sell_side_catalog_empty")
    elif not archived:
        blockers.append("sell_side_pdf_unavailable_metadata_only")
    return {
        "ticker": ticker, "status": "captured" if catalog_ok else "failed", "data_kind": "real",
        "catalog": catalog, "reports": reports,
        "counts": {"catalog_reports": len(reports), "archived_pdf": archived, "metadata_only": metadata_only},
        "blockers": blockers,
    }


def _checkpoint(runtime_root: Path, *, config: Mapping[str, Any], rows: list[dict[str, Any]]) -> None:
    payload = {
        "schema_version": E4_SELL_SIDE_EVIDENCE_CHECKPOINT_SCHEMA_VERSION, "state": "in_progress", "data_kind": "real",
        "config": dict(config), "tickers": rows,
        "truth_boundary": {"counts_as_tier_a_or_b": False, "counts_as_numeric_page_audit": False, "counts_as_position_or_target": False},
    }
    _write_json(runtime_root / "sell-side-evidence-batch-checkpoint.json", payload)
    _write_json(runtime_root / "sell-side-evidence-batch-latest.json", {"state": "in_progress", "receipt": "sell-side-evidence-batch-checkpoint.json"})


def run_sell_side_evidence_batch(
    identity_receipt_path: Path, runtime_root: Path, *, max_tickers: int = 100,
    inter_ticker_delay_seconds: float = 1.0, max_reports_per_ticker: int = 1,
    sync: SyncFn = sync_sell_side_archive, sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Collect at most one archiveable B2 report per ticker, sequentially and resumably."""
    if not isinstance(max_tickers, int) or not 1 <= max_tickers <= 100:
        raise ValueError("max_tickers must be 1-100")
    if inter_ticker_delay_seconds < 0 or not isinstance(max_reports_per_ticker, int) or max_reports_per_ticker < 1:
        raise ValueError("sell-side batch limits are invalid")
    tickers = load_real_identity_tickers(identity_receipt_path)[:max_tickers]
    runtime_root.mkdir(parents=True, exist_ok=True)
    config = _config(identity_receipt_path, max_tickers=max_tickers, inter_ticker_delay_seconds=inter_ticker_delay_seconds, max_reports_per_ticker=max_reports_per_ticker)
    latest = runtime_root / "sell-side-evidence-batch-latest.json"
    previous: dict[str, dict[str, Any]] = {}
    if latest.is_file():
        pointer = json.loads(latest.read_text(encoding="utf-8"))
        previous_path = runtime_root / str(pointer.get("receipt") or "")
        if previous_path.is_file():
            saved = json.loads(previous_path.read_text(encoding="utf-8"))
            if pointer.get("state") == "completed":
                if saved.get("config") != config:
                    raise ValueError("completed sell-side receipt does not match this corpus configuration")
                return {"path": str(previous_path), "receipt": saved}
            if saved.get("schema_version") != E4_SELL_SIDE_EVIDENCE_CHECKPOINT_SCHEMA_VERSION or saved.get("config") != config:
                raise ValueError("sell-side checkpoint does not match this corpus configuration")
            previous = {str(row.get("ticker") or "").upper(): row for row in saved.get("tickers") or []}
    rows: list[dict[str, Any]] = []
    for index, ticker in enumerate(tickers):
        if ticker in previous:
            rows.append({**previous[ticker], "status": "skipped", "resumed_from": previous[ticker].get("status")})
            continue
        try:
            raw_sink = RuntimeRawAuthoritySink(runtime_root / "raw")
            runtime = build_sell_side_runtime(authority_sink=raw_sink, transport=RateLimitedRetryTransport(default_http_transport, min_interval=inter_ticker_delay_seconds, max_attempts=2))
            batch = sync(ticker, runtime=runtime, max_reports=max_reports_per_ticker)
            row = _row_for_batch(ticker, batch, raw_sink=raw_sink)
        except Exception as exc:
            row = {"ticker": ticker, "status": "failed", "data_kind": "real", "catalog": [], "reports": [], "counts": {"catalog_reports": 0, "archived_pdf": 0, "metadata_only": 0}, "blockers": ["sell_side_collector_exception"], "error": type(exc).__name__}
        rows.append(row)
        _checkpoint(runtime_root, config=config, rows=rows)
        if index < len(tickers) - 1 and inter_ticker_delay_seconds:
            sleep(inter_ticker_delay_seconds)
    receipt = {
        "schema_version": E4_SELL_SIDE_EVIDENCE_BATCH_SCHEMA_VERSION, "state": "completed", "data_kind": "real", "config": config,
        "tickers": rows,
        "counts": {"requested": len(tickers), "catalog_available": sum(row["status"] in {"captured", "skipped"} for row in rows), "archived_pdf": sum(row["counts"]["archived_pdf"] for row in rows), "metadata_only": sum(row["counts"]["metadata_only"] for row in rows), "failed": sum(row["status"] == "failed" for row in rows)},
        "truth_boundary": {"sell_side_is_input_not_matrix": True, "counts_as_tier_a_or_b": False, "counts_as_numeric_page_audit": False, "counts_as_position_or_target": False},
    }
    receipt["receipt_hash"] = digest(receipt)
    path = runtime_root / f"sell-side-evidence-batch-{receipt['receipt_hash'][:16]}.json"
    _write_json(path, receipt)
    _write_json(latest, {"state": "completed", "receipt": path.name, "receipt_hash": receipt["receipt_hash"]})
    checkpoint = runtime_root / "sell-side-evidence-batch-checkpoint.json"
    if checkpoint.exists():
        checkpoint.unlink()
    return {"path": str(path), "receipt": receipt}
