from __future__ import annotations

import argparse
import hashlib
import ipaddress
import io
import json
import os
import re
import socket
import tempfile
import urllib.error
import urllib.request
from collections import defaultdict
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urljoin, urlsplit, urlunsplit

from data_store import DB_PATH, connect, initialize


EVIDENCE_POLICY_VERSION = "company-evidence-gate-v1"
MAX_PRIMARY_AGE_DAYS = 180
MAX_INDEPENDENT_AGE_DAYS = 365
COMPANY_DOMAINS = {
    "300750.SZ": {"catl.com"},
    "600519.SH": {"moutaichina.com", "moutai.com.cn"},
    "600036.SH": {"cmbchina.com"},
    "600900.SH": {"cypc.com.cn"},
    "000333.SZ": {"midea.com", "midea.com.cn"},
}
COMPANY_IDENTITIES = {
    "300750.SZ": ("宁德时代", "Contemporary Amperex Technology"),
    "600519.SH": ("贵州茅台", "Kweichow Moutai"),
    "600036.SH": ("招商银行", "China Merchants Bank"),
    "600900.SH": ("长江电力", "China Yangtze Power"),
    "000333.SZ": ("美的集团", "Midea Group"),
}
COMPANY_LEGAL_NAMES = {
    "300750.SZ": "宁德时代新能源科技股份有限公司",
    "600519.SH": "贵州茅台酒股份有限公司",
    "600036.SH": "招商银行股份有限公司",
    "600900.SH": "中国长江电力股份有限公司",
    "000333.SZ": "美的集团股份有限公司",
}
REGULATORY_DOMAINS = {"cninfo.com.cn", "sse.com.cn", "szse.cn"}
INDEPENDENT_DOMAINS = {
    "iea.org", "sneresearch.com", "xinhuanet.com", "news.cn", "people.com.cn",
    "nbd.com.cn", "cpnn.com.cn", "eeo.com.cn",
}
CURATED_SOURCE_PROFILES: dict[str, list[dict[str, Any]]] = {
    "600036.SH": [
        {
            "id": "cmb_2025_preliminary", "document_id": "cmb_2025_preliminary",
            "title": "招商银行 2025 年度业绩快报", "kind": "company_release", "strength": "中",
            "known_at": "2026-01-23", "url": "https://s3gw.cmbchina.com/lb5001-cmbweb-prd-1255000097/cmbir/20260123/721c99c0-1b86-47f7-ab46-e4b6aa68da0e.pdf",
        },
        {
            "id": "cmb_2025_annual", "document_id": "cmb_2025_annual",
            "title": "招商银行 2025 年年度报告", "kind": "primary", "strength": "强",
            "known_at": "2026-03-28", "url": "https://static.cninfo.com.cn/finalpage/2026-03-28/1225047590.PDF",
        },
        {
            "id": "cmb_2026_q1", "document_id": "cmb_2026_q1",
            "title": "招商银行 2026 年第一季度报告", "kind": "primary", "strength": "强",
            "known_at": "2026-04-29", "url": "https://static.cninfo.com.cn/finalpage/2026-04-29/1225231394.PDF",
        },
        {
            "id": "nbd_cmb_2025_results", "document_id": "nbd_cmb_2025_results",
            "title": "每日经济新闻 · 招商银行 2025 年经营结果交叉核验", "kind": "independent", "strength": "中",
            "known_at": "2026-03-30", "url": "https://www.nbd.com.cn/articles/2026-03-28/4313709.html",
        },
    ],
    "600900.SH": [
        {
            "id": "cypc_2025_annual", "document_id": "cypc_2025_annual",
            "title": "长江电力 2025 年年度报告", "kind": "primary", "strength": "强",
            "known_at": "2026-04-30", "url": "https://static.cninfo.com.cn/finalpage/2026-04-30/1225262036.PDF",
        },
        {
            "id": "cypc_2026_q1", "document_id": "cypc_2026_q1",
            "title": "长江电力 2026 年第一季度报告", "kind": "primary", "strength": "强",
            "known_at": "2026-04-30", "url": "https://static.cninfo.com.cn/finalpage/2026-04-30/1225262110.PDF",
        },
        {
            "id": "cpnn_cypc_2025_results", "document_id": "cpnn_cypc_2025_results",
            "title": "中国能源新闻网 · 长江电力 2025 年经营结果交叉核验", "kind": "independent", "strength": "中",
            "known_at": "2026-04-30", "url": "https://www.cpnn.com.cn/news/nyqy/202604/t20260430_1884834.html",
        },
    ],
    "000333.SZ": [
        {
            "id": "midea_2025_annual", "document_id": "midea_2025_annual",
            "title": "美的集团 2025 年年度报告", "kind": "primary", "strength": "强",
            "known_at": "2026-03-31", "url": "https://static.cninfo.com.cn/finalpage/2026-03-31/1225065145.PDF",
        },
        {
            "id": "midea_2026_q1", "document_id": "midea_2026_q1",
            "title": "美的集团 2026 年第一季度报告", "kind": "primary", "strength": "强",
            "known_at": "2026-04-30", "url": "https://static.cninfo.com.cn/finalpage/2026-04-30/1225259066.PDF",
        },
        {
            "id": "nbd_midea_2025_results", "document_id": "nbd_midea_2025_results",
            "title": "每日经济新闻 · 美的集团 2025 年经营结果交叉核验", "kind": "independent", "strength": "中",
            "known_at": "2026-03-31", "url": "https://www.nbd.com.cn/articles/2026-03-31/4318601.html",
        },
    ],
    "600519.SH": [
        {
            "id": "moutai_2025_annual", "document_id": "moutai_2025_annual",
            "title": "贵州茅台 2025 年年度报告", "kind": "primary", "strength": "强",
            "known_at": "2026-04-17", "url": "https://static.cninfo.com.cn/finalpage/2026-04-17/1225114741.PDF",
        },
        {
            "id": "moutai_2026_h1_market_meeting", "document_id": "moutai_2026_h1_market_meeting",
            "title": "贵州茅台酒销售有限公司 2026 年半年市场工作会", "kind": "company_release", "strength": "中",
            "known_at": "2026-07-14", "url": "https://www.moutaichina.com/mtgf/2026-07/14/article_2026071416305384715.html",
        },
        {
            "id": "xinhua_moutai_2025_results", "document_id": "xinhua_moutai_2025_results",
            "title": "新华网 · 贵州茅台 2025 年经营结果交叉核验", "kind": "independent", "strength": "中",
            "known_at": "2026-04-17", "url": "https://www.news.cn/enterprise/20260417/98403a5a2cb443d3af21723d0a800b28/c.html",
        },
    ],
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _canonical_url(url: str | None) -> str | None:
    if not url or not url.startswith("https://"):
        return None
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if not host or parts.username or parts.password or (parts.port and parts.port != 443):
        return None
    port = f":{parts.port}" if parts.port and parts.port != 443 else ""
    return urlunsplit(("https", host + port, parts.path or "/", parts.query, ""))


def _require_public_https_url(url: str, allowed_domains: set[str]) -> str:
    canonical = _canonical_url(url)
    if not canonical:
        raise RuntimeError("research capture URL must be canonical public HTTPS")
    host = (urlsplit(canonical).hostname or "").lower()
    if not _host_matches(host, allowed_domains):
        raise RuntimeError("research capture redirect left the approved domain allowlist")
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None and not literal.is_global:
        raise RuntimeError("research capture URL contains a non-public address")
    try:
        addresses = {
            item[4][0] for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        }
    except OSError as exc:
        raise RuntimeError("research capture host could not be resolved") from exc
    transport_proxy = ipaddress.ip_network("198.18.0.0/15")
    if not addresses or any(
        not ipaddress.ip_address(address).is_global
        and not (literal is None and ipaddress.ip_address(address) in transport_proxy)
        for address in addresses
    ):
        raise RuntimeError("research capture host resolved to a non-public address")
    return canonical


class _ValidatedRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, allowed_domains: set[str], chain: list[str]) -> None:
        super().__init__()
        self.allowed_domains = allowed_domains
        self.chain = chain

    def redirect_request(self, request, fp, code, msg, headers, newurl):  # type: ignore[override]
        target = _require_public_https_url(urljoin(request.full_url, newurl), self.allowed_domains)
        if len(self.chain) >= 6:
            raise RuntimeError("research capture exceeded five redirects")
        self.chain.append(target)
        return super().redirect_request(request, fp, code, msg, headers, target)


def _host_matches(host: str, domains: set[str]) -> bool:
    return any(host == domain or host.endswith("." + domain) for domain in domains)


def _trusted_document_kind(ticker: str, url: str | None, requested: str) -> str | None:
    canonical = _canonical_url(url)
    if not canonical:
        return None
    host = (urlsplit(canonical).hostname or "").lower()
    if requested == "primary" and _host_matches(host, REGULATORY_DOMAINS):
        return "primary"
    if requested == "primary" and _host_matches(host, COMPANY_DOMAINS.get(ticker.upper(), set())):
        return "company_release"
    if requested == "company_release" and _host_matches(host, COMPANY_DOMAINS.get(ticker.upper(), set())):
        return "company_release"
    if requested == "independent" and _host_matches(host, INDEPENDENT_DOMAINS):
        return "independent"
    if requested in {"supporting", "market_snapshot"}:
        return "supporting"
    return None


def _capture_domains(ticker: str, requested: str, canonical: str) -> set[str]:
    if requested in {"primary", "company_release"}:
        return set(REGULATORY_DOMAINS) | set(COMPANY_DOMAINS.get(ticker.upper(), set()))
    if requested == "independent":
        return set(INDEPENDENT_DOMAINS)
    host = (urlsplit(canonical).hostname or "").lower()
    return {host} if host else set()


def _capture_remote(
    url: str, allowed_domains: set[str], timeout: float = 30.0,
) -> tuple[bytes, str, int, str, list[str]]:
    initial = _require_public_https_url(url, allowed_domains)
    chain = [initial]
    opener = urllib.request.build_opener(_ValidatedRedirectHandler(allowed_domains, chain))
    request = urllib.request.Request(initial, headers={"User-Agent": "ParkResearchEvidenceBot/1.0"})
    with opener.open(request, timeout=timeout) as response:
        final_url = _require_public_https_url(response.geturl(), allowed_domains)
        if chain[-1] != final_url:
            chain.append(final_url)
        data = response.read(30 * 1024 * 1024 + 1)
        if len(data) > 30 * 1024 * 1024:
            raise RuntimeError("research source exceeds 30 MiB capture limit")
        return (
            data, response.headers.get_content_type() or "application/octet-stream",
            int(response.status), final_url, chain,
        )


def _extract_capture_text(raw_bytes: bytes, mime_type: str | None) -> str:
    if raw_bytes.startswith(b"%PDF"):
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(raw_bytes))
            text = "\n".join((page.extract_text() or "") for page in reader.pages[:8])
            if text.strip():
                return text
        except Exception:
            pass
    decoded = raw_bytes.decode("utf-8", errors="ignore")
    return re.sub(r"<[^>]+>", " ", decoded)


def _extract_regulatory_header_text(raw_bytes: bytes, mime_type: str | None) -> str:
    """Extract only the filing cover page; body mentions cannot establish issuer identity."""
    if raw_bytes.startswith(b"%PDF"):
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(raw_bytes))
            return (reader.pages[0].extract_text() or "") if reader.pages else ""
        except Exception:
            return ""
    return _extract_capture_text(raw_bytes, mime_type)[:4000]


def _verify_regulatory_identity(raw_bytes: bytes, mime_type: str | None, ticker: str) -> dict[str, str] | None:
    header = _extract_regulatory_header_text(raw_bytes, mime_type)
    text = re.sub(r"\s+", " ", header).strip()
    compact = re.sub(r"\s+", "", header)
    code = ticker.split(".", 1)[0]
    names = COMPANY_IDENTITIES.get(ticker.upper(), ())
    short_name = names[0] if names else ""
    legal_name = COMPANY_LEGAL_NAMES.get(ticker.upper(), "")
    first_code = re.search(r"(?:证券代码|公司代码)\s*[:：]?\s*(\d{6})(?:\D|$)", text)
    first_short_name = re.search(r"(?:证券简称|公司简称)\s*[:：]?\s*([^\s，。；:：]+)", text)
    legal_name_matches = bool(legal_name and re.sub(r"\s+", "", legal_name) in compact)
    code_matches = first_code is None or first_code.group(1) == code
    short_name_matches = first_short_name is None or first_short_name.group(1).startswith(short_name)
    if not (legal_name_matches and code_matches and short_name_matches):
        return None
    return {
        "ticker": ticker.upper(), "company_name": legal_name,
        "matched_by": (
            "cover_code_short_name_legal_name"
            if first_code and first_short_name
            else "regulatory_cover_legal_name"
        ),
        "excerpt_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "extractor_version": "regulatory-identity-v2",
    }


def _insert_identity_assertion(db_path: Path, document_id: str, identity: dict[str, str]) -> None:
    with closing(connect(db_path)) as conn:
        conn.execute(
            """INSERT OR IGNORE INTO research_document_identity_assertions
               (document_id, ticker, company_name, matched_by, excerpt_hash, extractor_version, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                document_id, identity["ticker"], identity["company_name"], identity["matched_by"],
                identity["excerpt_hash"], identity["extractor_version"], _now(),
            ),
        )
        conn.commit()


def _write_raw_capture(db_path: Path, ticker: str, raw_bytes: bytes, mime_type: str) -> tuple[str, str]:
    raw_hash = hashlib.sha256(raw_bytes).hexdigest()
    suffix = ".pdf" if mime_type == "application/pdf" or raw_bytes.startswith(b"%PDF") else ".html" if "html" in mime_type else ".bin"
    directory = db_path.parent / "research_raw" / ticker.upper().replace("/", "_")
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{raw_hash}{suffix}"
    if not target.exists():
        fd, temporary_name = tempfile.mkstemp(prefix=f".{raw_hash}.", suffix=".tmp", dir=directory)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(raw_bytes)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, target)
        finally:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
    return raw_hash, str(target)


def _first_url(value: Any) -> str | None:
    if isinstance(value, str) and value.startswith(("http://", "https://")):
        return value
    if isinstance(value, dict):
        preferred = ("source_url", "url", "announcement_url", "report_url", "link")
        for key in preferred:
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.startswith(("http://", "https://")):
                return candidate
        for candidate in value.values():
            found = _first_url(candidate)
            if found:
                return found
    if isinstance(value, list):
        for candidate in value:
            found = _first_url(candidate)
            if found:
                return found
    return None


def _explicit_published_at(value: Any) -> str | None:
    keys = {"published_at", "publish_date", "announcement_date", "notice_date", "release_date"}
    candidates: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, candidate in node.items():
                if key.lower() in keys and isinstance(candidate, str) and re.match(r"^20\d{2}-\d{2}-\d{2}", candidate):
                    candidates.append(candidate[:10])
                elif isinstance(candidate, (dict, list)):
                    walk(candidate)
        elif isinstance(node, list):
            for candidate in node:
                walk(candidate)

    walk(value)
    return max(candidates) if candidates else None


def _instant(value: str, *, date_only_end: bool = False) -> datetime:
    text = value.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        hour, minute, second = (23, 59, 59) if date_only_end else (0, 0, 0)
        return datetime.fromisoformat(text).replace(
            hour=hour, minute=minute, second=second, tzinfo=timezone(timedelta(hours=8))
        ).astimezone(timezone.utc)
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone(timedelta(hours=8)))
    return parsed.astimezone(timezone.utc)


def _capture_is_valid(row: dict[str, Any]) -> bool:
    raw_path = row.get("raw_path")
    raw_hash = row.get("raw_sha256")
    if not raw_path or not raw_hash or not row.get("canonical_url"):
        return False
    path = Path(raw_path)
    try:
        return path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == raw_hash
    except OSError:
        return False


def _capture_provenance(row: dict[str, Any]) -> dict[str, Any]:
    try:
        payload = json.loads(row.get("payload_json") or "{}")
    except (TypeError, json.JSONDecodeError):
        payload = {}
    final_url = payload.get("final_url") or row.get("canonical_url")
    redirect_chain = payload.get("redirect_chain")
    validated_redirect = bool(payload.get("final_url") and isinstance(redirect_chain, list) and redirect_chain)
    if not isinstance(redirect_chain, list) or not redirect_chain:
        redirect_chain = [final_url] if final_url else []
    receipt = {
        "capture_policy_version": (
            "validated-redirect-v1" if validated_redirect else "legacy-capture-current-url-only"
        ),
        "initial_url": payload.get("initial_url") or row.get("source_url"),
        "final_url": final_url,
        "redirect_chain": redirect_chain,
        "observed_at": row.get("observed_at"), "fetched_at": row.get("fetched_at"),
        "raw_sha256": row.get("raw_sha256"),
    }
    return {**receipt, "capture_receipt_hash": _hash(receipt)}


def _insert_document(db_path: Path, document: dict[str, Any]) -> dict[str, Any]:
    payload_json = _canonical_json(document["payload"])
    raw_bytes = document.get("raw_bytes")
    raw_hash = document.get("raw_sha256")
    raw_path = document.get("raw_path")
    mime_type = document.get("raw_mime_type")
    if isinstance(raw_bytes, bytes):
        raw_hash, raw_path = _write_raw_capture(db_path, document["ticker"], raw_bytes, mime_type or "application/octet-stream")
    content_hash = raw_hash or hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
    document_id = f"rdoc_{content_hash[:20]}"
    created_at = _now()
    with closing(connect(db_path)) as conn:
        conn.execute(
            """INSERT OR IGNORE INTO research_documents (
               id, ticker, source_adapter, source_key, source_url, title, document_kind,
               evidence_strength, published_at, observed_at, quality_status, content_hash,
               canonical_url, raw_sha256, raw_mime_type, http_status, fetched_at,
               payload_json, raw_path, created_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                document_id, document["ticker"].upper(), document["source_adapter"], document["source_key"],
                document.get("source_url"), document["title"], document["document_kind"],
                document["evidence_strength"], document.get("published_at"), document["observed_at"],
                document["quality_status"], content_hash, document.get("canonical_url"), raw_hash, mime_type,
                document.get("http_status"), document.get("fetched_at"), payload_json, raw_path, created_at,
            ),
        )
        row = conn.execute(
            "SELECT id, ticker, content_hash, quality_status, evidence_strength, published_at, raw_sha256, raw_path FROM research_documents WHERE ticker=? AND content_hash=?",
            (document["ticker"].upper(), content_hash),
        ).fetchone()
        conn.commit()
    if not row:
        raise RuntimeError("research document insert failed")
    return dict(row)


def sync_profile_sources(
    ticker: str,
    sources: Iterable[dict[str, Any]],
    db_path: Path = DB_PATH,
    *,
    source_adapter: str = "curated_profile",
    capture_remote: bool = False,
    observed_at: str | None = None,
) -> dict[str, Any]:
    """Normalize curated report locators into immutable, distinct source documents."""
    initialize(db_path)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for source in sources:
        grouped[str(source.get("document_id") or source.get("id"))].append(dict(source))
    documents = []
    for external_id, locators in grouped.items():
        primary = locators[0]
        strengths = {str(item.get("strength") or "") for item in locators}
        requested_strength = "strong" if "强" in strengths else "medium" if "中" in strengths else "weak"
        kinds = {str(item.get("kind") or "supporting") for item in locators}
        requested_kind = (
            "independent" if "independent" in kinds else
            "primary" if "primary" in kinds else
            "company_release" if "company_release" in kinds else
            "supporting"
        )
        canonical = _canonical_url(primary.get("url"))
        trusted_kind = _trusted_document_kind(ticker, canonical, requested_kind)
        raw_bytes: bytes | None = None
        mime_type: str | None = None
        http_status: int | None = None
        final_url: str | None = None
        redirect_chain: list[str] = []
        capture_error: str | None = None
        if capture_remote and canonical:
            try:
                captured_result = _capture_remote(
                    canonical, _capture_domains(ticker, requested_kind, canonical),
                )
                if len(captured_result) == 3:  # backwards-compatible deterministic transports
                    raw_bytes, mime_type, http_status = captured_result
                    final_url, redirect_chain = canonical, [canonical]
                else:
                    raw_bytes, mime_type, http_status, final_url, redirect_chain = captured_result
                trusted_kind = _trusted_document_kind(ticker, final_url, requested_kind)
            except Exception as exc:
                capture_error = f"{type(exc).__name__}: {exc}"
        identity = _verify_regulatory_identity(raw_bytes, mime_type, ticker) if raw_bytes is not None and trusted_kind == "primary" else None
        captured = (
            raw_bytes is not None and http_status == 200 and trusted_kind is not None
            and (trusted_kind != "primary" or identity is not None)
        )
        strength = requested_strength if captured else "lead"
        kind = trusted_kind if captured else "upstream_dimension"
        quality_status = "accepted" if captured else "degraded"
        captured_at = observed_at or _now()
        inserted = _insert_document(db_path, {
            "ticker": ticker, "source_adapter": source_adapter, "source_key": external_id,
            "source_url": primary.get("url"), "title": primary.get("title") or external_id,
            "document_kind": kind, "evidence_strength": strength,
            "published_at": primary.get("known_at"), "observed_at": captured_at, "quality_status": quality_status,
            "canonical_url": final_url or canonical, "raw_bytes": raw_bytes, "raw_mime_type": mime_type,
            "http_status": http_status, "fetched_at": captured_at if raw_bytes is not None else None,
            "payload": {
                "external_document_id": external_id, "locators": locators,
                "requested_kind": requested_kind, "trusted_kind": trusted_kind,
                "capture_error": capture_error, "capture_method": "remote_http" if raw_bytes is not None else None,
                "initial_url": canonical, "final_url": final_url, "redirect_chain": redirect_chain,
                "regulatory_identity": identity,
            }, "raw_path": None,
        })
        if identity is not None:
            _insert_identity_assertion(db_path, inserted["id"], identity)
        documents.append(inserted)
    return {"ticker": ticker.upper(), "source_adapter": source_adapter, "document_count": len(documents), "documents": documents}


def import_uzi_raw(raw_path: Path, db_path: Path = DB_PATH) -> dict[str, Any]:
    """Store UZI dimensions as leads. UZI is a connector, never primary evidence by itself."""
    initialize(db_path)
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    ticker = str(raw.get("full") or raw.get("ticker") or "").upper()
    if not ticker:
        raise ValueError("UZI raw_data.json has no ticker identity")
    dimensions = raw.get("dimensions")
    if not isinstance(dimensions, dict):
        raise ValueError("UZI raw_data.json has no dimensions object")
    observed_at = datetime.fromtimestamp(raw_path.stat().st_mtime, tz=timezone.utc).isoformat()
    documents = []
    counts = {"accepted": 0, "degraded": 0, "rejected": 0}
    for dim_key, value in sorted(dimensions.items()):
        if not isinstance(value, dict):
            continue
        pipeline = value.get("_pipeline") or {}
        quality = str(pipeline.get("quality") or ("error" if value.get("fallback") else "partial"))
        data = value.get("data") or {}
        status = "accepted" if quality == "full" and data else "degraded" if data else "rejected"
        counts[status] += 1
        source_key = str(value.get("source") or "unknown")
        document = _insert_document(db_path, {
            "ticker": ticker, "source_adapter": "uzi-skill", "source_key": source_key,
            "source_url": _first_url(data), "title": f"UZI dimension · {dim_key}",
            "document_kind": "upstream_dimension", "evidence_strength": "lead",
            "published_at": _explicit_published_at(data), "observed_at": observed_at,
            "quality_status": status,
            "payload": {
                "dim_key": dim_key, "quality": quality, "data_gaps": pipeline.get("data_gaps") or [],
                "error": pipeline.get("error"), "source": source_key, "data": data,
            },
            "raw_path": str(raw_path),
        })
        documents.append(document)
    return {
        "ticker": ticker, "source_adapter": "uzi-skill", "raw_path": str(raw_path),
        "raw_hash": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
        "dimension_count": len(documents), "quality_counts": counts, "documents": documents,
    }


def build_evidence_set(
    ticker: str,
    snapshot_id: str,
    db_path: Path = DB_PATH,
    *,
    knowledge_cutoff: str | None = None,
) -> dict[str, Any]:
    """Freeze only dated strong/medium documents that existed by the snapshot cutoff."""
    initialize(db_path)
    ticker = ticker.upper()
    with closing(connect(db_path)) as conn:
        snapshot = conn.execute(
            "SELECT id, known_at, data_mode, quality_status FROM dataset_snapshots WHERE id=?",
            (snapshot_id,),
        ).fetchone()
        if not snapshot:
            raise KeyError(snapshot_id)
        snapshot_cutoff = str(snapshot["known_at"])
        cutoff = knowledge_cutoff or snapshot_cutoff
        if _instant(cutoff) < _instant(snapshot_cutoff):
            raise ValueError("research knowledge cutoff cannot precede the dataset snapshot cutoff")
        rows = conn.execute(
            """SELECT d.*, x.matched_by AS identity_matched_by,
                      x.excerpt_hash AS identity_excerpt_hash,
                      x.extractor_version AS identity_extractor_version
               FROM research_documents d
               LEFT JOIN research_document_identity_assertions x
                 ON x.document_id=d.id AND x.ticker=d.ticker AND x.extractor_version='regulatory-identity-v2'
               WHERE d.ticker=? AND d.quality_status='accepted'
                 AND d.evidence_strength IN ('strong', 'medium')
                 AND d.published_at IS NOT NULL
               ORDER BY d.published_at, d.id""",
            (ticker,),
        ).fetchall()
        cutoff_instant = _instant(cutoff)
        point_in_time_documents = []
        for raw_row in rows:
            row = dict(raw_row)
            try:
                point_in_time_ok = (
                    _instant(str(row["published_at"]), date_only_end=True) <= cutoff_instant
                    and _instant(str(row["observed_at"])) <= cutoff_instant
                    and (not row.get("fetched_at") or _instant(str(row["fetched_at"])) <= cutoff_instant)
                )
            except (TypeError, ValueError):
                point_in_time_ok = False
            if point_in_time_ok and _capture_is_valid(row):
                point_in_time_documents.append(row)
        # A locator can be recaptured as the upstream page changes.  A frozen set
        # uses only the newest capture available by the cutoff, never multiple
        # versions of the same logical source as independent evidence.
        newest_by_source: dict[str, dict[str, Any]] = {}
        for row in point_in_time_documents:
            source_key = str(row.get("source_key") or row["id"])
            previous = newest_by_source.get(source_key)
            row_order = (str(row.get("fetched_at") or row.get("observed_at") or ""), str(row["id"]))
            previous_order = (
                str(previous.get("fetched_at") or previous.get("observed_at") or ""),
                str(previous["id"]),
            ) if previous else ("", "")
            if previous is None or row_order > previous_order:
                newest_by_source[source_key] = row
        point_in_time_documents = list(newest_by_source.values())
        cutoff_date = cutoff_instant.date()

        def age_days(row: dict[str, Any]) -> int:
            return (cutoff_date - _instant(str(row["published_at"]), date_only_end=True).date()).days

        primary = [
            row for row in point_in_time_documents
            if row["document_kind"] in {"primary", "company_release"} and age_days(row) <= MAX_PRIMARY_AGE_DAYS
        ]
        regulatory_primary = [
            row for row in primary
            if _host_matches((urlsplit(str(row["canonical_url"])).hostname or "").lower(), REGULATORY_DOMAINS)
            and row.get("identity_matched_by")
        ]
        independent = [
            row for row in point_in_time_documents
            if row["document_kind"] == "independent" and age_days(row) <= MAX_INDEPENDENT_AGE_DAYS
        ]
        documents = sorted({row["id"]: row for row in [*primary, *independent]}.values(), key=lambda row: (row["published_at"], row["id"]))
        primary_age = min((age_days(row) for row in primary), default=None)
        independent_age = min((age_days(row) for row in independent), default=None)
        failures = []
        if snapshot["data_mode"] != "REAL" or snapshot["quality_status"] != "passed":
            failures.append("snapshot is not a quality-passed REAL snapshot")
        if len(primary) < 2:
            failures.append("at least two captured, recent primary/company documents are required")
        if len(regulatory_primary) < 1:
            failures.append("at least one captured, recent primary/regulatory document is required")
        if len(independent) < 1:
            failures.append("at least one dated independent cross-check is required")
        if len(primary) + len(independent) < 3:
            failures.append("at least three captured, recent core documents are required")
        manifest = {
            "ticker": ticker, "snapshot_id": snapshot_id, "knowledge_cutoff": cutoff,
            "policy_version": EVIDENCE_POLICY_VERSION,
            "documents": [
                {
                    "id": row["id"], "content_hash": row["content_hash"], "raw_sha256": row["raw_sha256"],
                    "canonical_url": row["canonical_url"], "published_at": row["published_at"],
                    "observed_at": row["observed_at"], "document_kind": row["document_kind"],
                    "evidence_strength": row["evidence_strength"],
                    "identity_matched_by": row.get("identity_matched_by"),
                    "identity_excerpt_hash": row.get("identity_excerpt_hash"),
                    "identity_extractor_version": row.get("identity_extractor_version"),
                    "capture_provenance": _capture_provenance(row),
                }
                for row in documents
            ],
        }
        manifest_hash = _hash(manifest)
        set_id = f"rset_{manifest_hash[:20]}"
        status = "passed" if not failures else "insufficient"
        gate = {
            "status": status, "failures": failures, "document_count": len(documents),
            "primary_document_count": len(primary), "independent_document_count": len(independent),
            "regulatory_primary_count": len(regulatory_primary),
            "latest_primary_age_days": primary_age, "latest_independent_age_days": independent_age,
            "max_primary_age_days": MAX_PRIMARY_AGE_DAYS, "max_independent_age_days": MAX_INDEPENDENT_AGE_DAYS,
            "lead_documents_excluded": conn.execute(
                "SELECT COUNT(*) FROM research_documents WHERE ticker=? AND evidence_strength='lead'",
                (ticker,),
            ).fetchone()[0],
        }
        gate_hash = _hash(gate)
        conn.execute(
            """INSERT OR IGNORE INTO research_evidence_sets
               (id, ticker, snapshot_id, knowledge_cutoff, policy_version, manifest_hash, status, gate_json, gate_hash, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (set_id, ticker, snapshot_id, cutoff, EVIDENCE_POLICY_VERSION, manifest_hash, status, _canonical_json(gate), gate_hash, _now()),
        )
        for row in documents:
            role = "independent" if row["document_kind"] == "independent" else "primary" if row["document_kind"] in {"primary", "company_release"} else "supporting"
            conn.execute(
                "INSERT OR IGNORE INTO research_evidence_set_items (evidence_set_id, document_id, role) VALUES (?, ?, ?)",
                (set_id, row["id"], role),
            )
        conn.commit()
    return {
        "evidence_set_id": set_id, "ticker": ticker, "snapshot_id": snapshot_id,
        "manifest_hash": manifest_hash, "gate_hash": gate_hash, "knowledge_cutoff": cutoff,
        "policy_version": EVIDENCE_POLICY_VERSION, "status": status,
        "gate": gate, "documents": [
            {
                "id": row["id"], "title": row["title"], "source_url": row["source_url"],
                "document_kind": row["document_kind"], "evidence_strength": row["evidence_strength"],
                "published_at": row["published_at"], "content_hash": row["content_hash"],
                "canonical_url": row["canonical_url"], "raw_sha256": row["raw_sha256"],
                "source_key": row["source_key"], "identity_matched_by": row.get("identity_matched_by"),
                "observed_at": row.get("observed_at"), "fetched_at": row.get("fetched_at"),
                "capture_provenance": _capture_provenance(row),
            }
            for row in documents
        ],
    }


def evidence_coverage(ticker: str, db_path: Path = DB_PATH) -> dict[str, Any]:
    initialize(db_path)
    with closing(connect(db_path)) as conn:
        rows = conn.execute(
            """SELECT evidence_strength, quality_status, COUNT(*) AS count
               FROM research_documents WHERE ticker=?
               GROUP BY evidence_strength, quality_status ORDER BY evidence_strength, quality_status""",
            (ticker.upper(),),
        ).fetchall()
        latest = conn.execute(
            """SELECT id, snapshot_id, status, gate_json, manifest_hash, created_at
               FROM research_evidence_sets WHERE ticker=? ORDER BY created_at DESC LIMIT 1""",
            (ticker.upper(),),
        ).fetchone()
    return {
        "ticker": ticker.upper(), "document_counts": [dict(row) for row in rows],
        "latest_evidence_set": ({**dict(latest), "gate": json.loads(latest["gate_json"])} if latest else None),
    }


def load_evidence_set(
    ticker: str,
    snapshot_id: str,
    db_path: Path = DB_PATH,
    *,
    passed_only: bool = True,
) -> dict[str, Any] | None:
    """Load the newest evidence set that still satisfies the complete policy gate."""
    status_clause = "AND s.status='passed'" if passed_only else ""
    with closing(connect(db_path)) as conn:
        rows = conn.execute(
            f"""SELECT s.*, d.known_at AS snapshot_known_at,
                       d.data_mode AS snapshot_data_mode, d.quality_status AS snapshot_quality_status
                FROM research_evidence_sets s
                JOIN dataset_snapshots d ON d.id=s.snapshot_id
                WHERE s.ticker=? AND s.snapshot_id=? {status_clause}
                ORDER BY s.created_at DESC, s.id DESC""",
            (ticker.upper(), snapshot_id),
        ).fetchall()
        for raw_row in rows:
            row = dict(raw_row)
            documents_list = [dict(item) for item in conn.execute(
                """SELECT d.id, d.title, d.source_key, d.source_url, d.canonical_url, d.payload_json,
                          d.document_kind, d.evidence_strength, d.published_at, d.observed_at,
                          d.fetched_at, d.content_hash, d.raw_sha256, d.raw_path, i.role,
                          x.matched_by AS identity_matched_by,
                          x.excerpt_hash AS identity_excerpt_hash,
                          x.extractor_version AS identity_extractor_version
                   FROM research_evidence_set_items i
                   JOIN research_documents d ON d.id=i.document_id
                   LEFT JOIN research_document_identity_assertions x
                     ON x.document_id=d.id AND x.ticker=d.ticker AND x.extractor_version='regulatory-identity-v2'
                   WHERE i.evidence_set_id=? ORDER BY d.published_at, d.id""",
                (row["id"],),
            ).fetchall()]
            for item in documents_list:
                item["capture_provenance"] = _capture_provenance(item)
                item.pop("payload_json", None)
            try:
                gate = json.loads(row["gate_json"])
                cutoff = _instant(row["knowledge_cutoff"])
                cutoff_date = cutoff.date()
                manifest = {
                    "ticker": row["ticker"], "snapshot_id": row["snapshot_id"],
                    "knowledge_cutoff": row["knowledge_cutoff"], "policy_version": row["policy_version"],
                    "documents": [
                        {
                            "id": item["id"], "content_hash": item["content_hash"], "raw_sha256": item["raw_sha256"],
                            "canonical_url": item["canonical_url"], "published_at": item["published_at"],
                            "observed_at": item["observed_at"], "document_kind": item["document_kind"],
                            "evidence_strength": item["evidence_strength"],
                            "identity_matched_by": item.get("identity_matched_by"),
                            "identity_excerpt_hash": item.get("identity_excerpt_hash"),
                            "identity_extractor_version": item.get("identity_extractor_version"),
                            "capture_provenance": item["capture_provenance"],
                        }
                        for item in documents_list
                    ],
                }
                primary_count = sum(
                    item["document_kind"] in {"primary", "company_release"}
                    and (cutoff_date - _instant(item["published_at"], date_only_end=True).date()).days <= MAX_PRIMARY_AGE_DAYS
                    for item in documents_list
                )
                regulatory_count = sum(
                    item["document_kind"] == "primary"
                    and _host_matches((urlsplit(str(item["canonical_url"])).hostname or "").lower(), REGULATORY_DOMAINS)
                    and bool(item.get("identity_matched_by"))
                    for item in documents_list
                )
                independent_count = sum(
                    item["document_kind"] == "independent"
                    and (cutoff_date - _instant(item["published_at"], date_only_end=True).date()).days <= MAX_INDEPENDENT_AGE_DAYS
                    for item in documents_list
                )
                integrity_ok = (
                    row["status"] == "passed"
                    and row["snapshot_data_mode"] == "REAL"
                    and row["snapshot_quality_status"] == "passed"
                    and row["policy_version"] == EVIDENCE_POLICY_VERSION
                    and cutoff >= _instant(row["snapshot_known_at"])
                    and row["manifest_hash"] == _hash(manifest)
                    and row["id"] == f"rset_{row['manifest_hash'][:20]}"
                    and row["gate_hash"] == _hash(gate)
                    and gate.get("status") == "passed"
                    and gate.get("failures") == []
                    and primary_count >= 2
                    and regulatory_count >= 1
                    and independent_count >= 1
                    and len(documents_list) >= 3
                    and len({str(item.get("source_key") or item["id"]) for item in documents_list}) == len(documents_list)
                    and gate.get("primary_document_count") == primary_count
                    and gate.get("regulatory_primary_count") == regulatory_count
                    and gate.get("independent_document_count") == independent_count
                    and gate.get("document_count") == len(documents_list)
                    and all(_capture_is_valid(item) for item in documents_list)
                    and all(
                        _instant(item["published_at"], date_only_end=True) <= cutoff
                        and _instant(item["observed_at"]) <= cutoff
                        and (not item.get("fetched_at") or _instant(item["fetched_at"]) <= cutoff)
                        for item in documents_list
                    )
                    and all(
                        item["role"] == ("independent" if item["document_kind"] == "independent" else "primary" if item["document_kind"] in {"primary", "company_release"} else "supporting")
                        for item in documents_list
                    )
                    and all(
                        (item["document_kind"] in {"primary", "company_release"} and
                         (cutoff_date - _instant(item["published_at"], date_only_end=True).date()).days <= MAX_PRIMARY_AGE_DAYS)
                        or (item["document_kind"] == "independent" and
                            (cutoff_date - _instant(item["published_at"], date_only_end=True).date()).days <= MAX_INDEPENDENT_AGE_DAYS)
                        for item in documents_list
                    )
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                integrity_ok = False
            if integrity_ok:
                return {
                    "evidence_set_id": row["id"], "ticker": row["ticker"], "snapshot_id": row["snapshot_id"],
                    "manifest_hash": row["manifest_hash"], "gate_hash": row["gate_hash"], "knowledge_cutoff": row["knowledge_cutoff"],
                    "policy_version": row["policy_version"], "status": row["status"],
                    "gate": gate, "documents": documents_list,
                }
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize research sources and freeze report evidence sets")
    parser.add_argument("--db", type=Path, default=DB_PATH)
    subparsers = parser.add_subparsers(dest="command", required=True)
    import_parser = subparsers.add_parser("import-uzi", help="Import one UZI raw_data.json as lead-only documents")
    import_parser.add_argument("raw_path", type=Path)
    sync_parser = subparsers.add_parser("sync-profile", help="Normalize the deterministic report's curated sources")
    sync_parser.add_argument("ticker")
    sync_parser.add_argument("--capture", action="store_true", help="Fetch and freeze the remote source bytes")
    build_parser = subparsers.add_parser("build-set", help="Freeze a policy-gated evidence set")
    build_parser.add_argument("ticker")
    build_parser.add_argument("snapshot_id")
    build_parser.add_argument("--knowledge-cutoff", help="ISO timestamp; defaults to the dataset snapshot cutoff")
    status_parser = subparsers.add_parser("status", help="Show document coverage and latest gate")
    status_parser.add_argument("ticker")
    args = parser.parse_args()
    if args.command == "import-uzi":
        result = import_uzi_raw(args.raw_path, args.db)
    elif args.command == "sync-profile":
        from research_reports import CATL_PROFILE, report_payload

        report = report_payload(args.ticker, args.db)
        if args.ticker.upper() in CURATED_SOURCE_PROFILES:
            sources = CURATED_SOURCE_PROFILES[args.ticker.upper()]
        elif args.ticker.upper() == "300750.SZ":
            sources = CATL_PROFILE["sources"]
        elif report and report.get("sources"):
            sources = report["sources"]
        else:
            raise SystemExit(f"no deterministic report for {args.ticker}")
        result = sync_profile_sources(args.ticker, sources, args.db, capture_remote=args.capture)
    elif args.command == "build-set":
        result = build_evidence_set(args.ticker, args.snapshot_id, args.db, knowledge_cutoff=args.knowledge_cutoff)
    else:
        result = evidence_coverage(args.ticker, args.db)
    print(json.dumps(result, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
