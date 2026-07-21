#!/usr/bin/env python3
"""Build and verify five cross-industry, explicitly non-live acceptance reports."""

from __future__ import annotations

import argparse
from hashlib import sha256
from html import escape as html_escape
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
PRODUCT = ROOT / "product"
sys.path.insert(0, str(PRODUCT))

from company_research import (  # noqa: E402
    COMPANY_ADAPTERS,
    acceptance_baseline,
    acceptance_evidence,
    build_cross_company_report,
    render_standalone_html,
    verify_report_integrity,
)
from report_contract import MODULE_SPECS, validate_report_contract  # noqa: E402


OUTPUT_ROOT = ROOT / "evidence" / "m4-cross-company-research"
CUTOFF = "2026-07-20T07:00:00+00:00"
CHROME_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "google-chrome", "chromium", "chromium-browser",
)


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def chrome_path() -> str:
    for candidate in CHROME_CANDIDATES:
        resolved = candidate if candidate.startswith("/") else shutil.which(candidate)
        if resolved and Path(resolved).exists():
            return str(resolved)
    raise RuntimeError("Chrome/Chromium is required for M4 PNG and PDF acceptance evidence")


def render(
    chrome: str, html_path: Path, png_path: Path, mobile_path: Path, pdf_path: Path,
) -> dict[str, int]:
    url = html_path.resolve().as_uri()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Python Playwright is required for full-page visual evidence") from exc
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=chrome, headless=True,
            args=["--disable-background-networking", "--disable-sync"],
        )
        try:
            desktop = browser.new_page(viewport={"width": 1440, "height": 1000})
            desktop.goto(url, wait_until="load", timeout=30_000)
            desktop_height = int(desktop.evaluate("document.documentElement.scrollHeight"))
            desktop.screenshot(path=str(png_path), full_page=True, timeout=30_000)

            mobile = browser.new_page(viewport={"width": 390, "height": 844})
            mobile.goto(url, wait_until="load", timeout=30_000)
            mobile_height = int(mobile.evaluate("document.documentElement.scrollHeight"))
            mobile.screenshot(path=str(mobile_path), full_page=True, timeout=30_000)
        finally:
            browser.close()
    with tempfile.TemporaryDirectory(prefix="m4-chrome-") as profile:
        common = [
            chrome, "--headless=new", "--disable-gpu", "--no-first-run",
            "--disable-background-networking", "--disable-sync", "--hide-scrollbars",
            f"--user-data-dir={profile}",
        ]
        _run_chrome_until_artifact(
            [*common, "--no-pdf-header-footer", f"--print-to-pdf={pdf_path}", url], pdf_path,
        )
    return {"desktop_scroll_height": desktop_height, "mobile_scroll_height": mobile_height}


def _run_chrome_until_artifact(command: list[str], target: Path) -> None:
    """Chrome on macOS may keep a helper alive after writing; accept only a stable file."""
    target.unlink(missing_ok=True)
    process = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    deadline = time.monotonic() + 30
    previous_size = -1
    stable_polls = 0
    try:
        while time.monotonic() < deadline:
            if target.exists() and target.stat().st_size > 1_000:
                size = target.stat().st_size
                stable_polls = stable_polls + 1 if size == previous_size else 0
                previous_size = size
                if stable_polls >= 3:
                    return
            if process.poll() is not None:
                if process.returncode != 0:
                    stdout, stderr = process.communicate()
                    raise RuntimeError(f"Chrome render failed: {stdout} {stderr}")
                if target.exists() and target.stat().st_size > 1_000:
                    return
                raise RuntimeError("Chrome exited without a complete render artifact")
            time.sleep(0.2)
        raise RuntimeError(f"Chrome render timed out before producing {target.name}")
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)


def png_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n" or len(data) < 24:
        raise RuntimeError(f"invalid PNG: {path}")
    width, height = struct.unpack(">II", data[16:24])
    return int(width), int(height)


def pdf_page_count(path: Path) -> int:
    data = path.read_bytes()
    if not data.startswith(b"%PDF-") or len(data) < 10_000:
        raise RuntimeError(f"invalid or empty PDF: {path}")
    return len(re.findall(rb"/Type\s*/Page(?!s)", data))


def pdf_module_order(path: Path) -> list[str]:
    binary = shutil.which("pdftotext")
    if not binary:
        raise RuntimeError("pdftotext is required to verify PDF module content")
    result = subprocess.run(
        [binary, str(path), "-"], check=True, capture_output=True, text=True, timeout=20,
    )
    positions = []
    for spec in MODULE_SPECS:
        position = result.stdout.find(spec.title)
        if position < 0:
            raise RuntimeError(f"PDF is missing module title: {spec.title}")
        positions.append(position)
    if positions != sorted(positions):
        raise RuntimeError("PDF module order differs from research-report-v1")
    return [item.id for item in MODULE_SPECS]


def pdf_text(path: Path) -> str:
    binary = shutil.which("pdftotext")
    if not binary:
        raise RuntimeError("pdftotext is required to verify PDF evidence trace")
    return subprocess.run(
        [binary, str(path), "-"], check=True, capture_output=True, text=True, timeout=20,
    ).stdout


def _audit_text(narrative: dict, path: str) -> str:
    value: object = narrative
    for part in path.replace("]", "").split("."):
        if "[" in part:
            key, index = part.split("[", 1)
            value = value[key][int(index)]  # type: ignore[index]
        else:
            value = value[part]  # type: ignore[index]
    if not isinstance(value, str):
        raise RuntimeError(f"claim audit path is not text: {path}")
    return value


def verify_live_publication(live_root: Path) -> dict:
    receipt_path = live_root / "publication-receipt.json"
    if not receipt_path.is_file():
        raise RuntimeError("live publication receipt is missing")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    editorial_path = live_root / "editorial-audit-receipt.json"
    editorial = json.loads(editorial_path.read_text(encoding="utf-8"))
    if (
        receipt.get("editorial_audit_receipt_sha256") != digest(editorial_path)
        or editorial.get("status") != "passed"
        or (editorial.get("blocking_findings") or {}).get("p0") != 0
        or (editorial.get("blocking_findings") or {}).get("p1") != 0
    ):
        raise RuntimeError("live publication is not bound to a passing independent editorial audit")
    editorial_map = {
        str(item.get("ticker") or "").upper(): item
        for item in editorial.get("companies") or [] if isinstance(item, dict)
    }
    if receipt.get("status") != "passed" or receipt.get("company_count") != 5:
        raise RuntimeError("live publication receipt is incomplete")
    for company in receipt["companies"]:
        ticker = company["ticker"]
        root = live_root / ticker
        report = json.loads((root / "report.json").read_text(encoding="utf-8"))
        artifact = json.loads((root / "narrative-artifact.json").read_text(encoding="utf-8"))
        editorial_company = editorial_map.get(ticker)
        if (
            not editorial_company or editorial_company.get("result") != "approved"
            or editorial_company.get("input_identity") != company.get("production_input_identity")
            or editorial_company.get("narrative_hash") != company.get("narrative_hash")
            or editorial_company.get("evidence_manifest_hash") != company.get("evidence_manifest_hash")
            or editorial_company.get("artifact_provenance_hash")
                != (company.get("editorial_approval") or {}).get("artifact_provenance_hash")
            or editorial_company.get("provider")
                != (company.get("editorial_approval") or {}).get("provider")
            or editorial_company.get("model")
                != (company.get("editorial_approval") or {}).get("model")
            or editorial_company.get("prompt_version")
                != (company.get("editorial_approval") or {}).get("prompt_version")
            or editorial_company.get("prompt_hash")
                != (company.get("editorial_approval") or {}).get("prompt_hash")
        ):
            raise RuntimeError(f"editorial audit company identity mismatch: {ticker}")
        evidence = json.loads((root / "evidence-manifest-receipt.json").read_text(encoding="utf-8"))
        audit = json.loads((root / "claim-source-audit-receipt.json").read_text(encoding="utf-8"))
        transport = json.loads((root / "transport-verification-receipt.json").read_text(encoding="utf-8"))
        html = (root / "report.html").read_text(encoding="utf-8")
        verify_report_integrity(report)
        errors = validate_report_contract(report["report_contract"], report)
        if errors:
            raise RuntimeError(f"live report contract failed: {ticker}: {errors}")
        if evidence.get("status") != "passed" or evidence.get("raw_bytes_committed") is not False:
            raise RuntimeError(f"redacted evidence receipt failed: {ticker}")
        if evidence.get("production_input_identity") != report["generated_from"]["production_input_identity"]:
            raise RuntimeError(f"evidence input identity mismatch: {ticker}")
        if evidence.get("snapshot_binding") != {
            key: report["generated_from"][key]
            for key in ("snapshot_id", "snapshot_manifest_hash", "baseline_payload_hash")
        }:
            raise RuntimeError(f"evidence snapshot binding mismatch: {ticker}")
        if (
            transport.get("status") != "passed"
            or transport.get("snapshot_id") != report["generated_from"]["snapshot_id"]
            or transport.get("snapshot_manifest_hash") != report["generated_from"]["snapshot_manifest_hash"]
            or transport.get("evidence_manifest_hash") != report["generated_from"]["evidence_manifest_hash"]
            or any(
                item.get("capture_policy_version") != "validated-redirect-v1"
                or item.get("content_matches_frozen") is not True
                or not item.get("final_url") or not item.get("redirect_chain")
                for item in transport.get("documents") or []
            )
        ):
            raise RuntimeError(f"secure transport receipt failed: {ticker}")
        expected_transport_hash = sha256(json.dumps(
            transport, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")).hexdigest()
        if evidence.get("current_transport_verification_hash") != expected_transport_hash:
            raise RuntimeError(f"evidence receipt is not bound to secure transport proof: {ticker}")
        source_ids = {item["id"] for item in report["sources"]}
        evidence_ids = {item["id"] for item in evidence["documents"]}
        if not evidence_ids or not evidence_ids.issubset(source_ids):
            raise RuntimeError(f"evidence receipt source set mismatch: {ticker}")
        for document in evidence["documents"]:
            capture = document.get("capture_provenance") or {}
            if (
                not re.fullmatch(r"[0-9a-f]{64}", str(document.get("raw_sha256") or ""))
                or not capture.get("final_url") or not capture.get("redirect_chain")
                or not capture.get("observed_at") or not capture.get("capture_receipt_hash")
            ):
                raise RuntimeError(f"evidence capture provenance is incomplete: {ticker}")
        if audit.get("status") != "passed" or audit.get("narrative_hash") != artifact.get("narrative_hash"):
            raise RuntimeError(f"claim/source audit identity mismatch: {ticker}")
        for row in audit["claims"]:
            text = _audit_text(artifact["narrative"], row["path"])
            if sha256(text.encode("utf-8")).hexdigest() != row["text_sha256"]:
                raise RuntimeError(f"claim/source audit text changed: {ticker}: {row['path']}")
            if not row["source_ids"] or not set(row["source_ids"]).issubset(source_ids):
                raise RuntimeError(f"claim/source audit citation failed: {ticker}: {row['path']}")
        extracted_pdf = pdf_text(root / "report.pdf")
        for source in report["sources"]:
            source_id = source["id"]
            if f'id="evidence-{source_id}"' not in html or f'data-evidence-id="{source_id}"' not in html:
                raise RuntimeError(f"HTML evidence trace is incomplete: {ticker}: {source_id}")
            if source_id not in extracted_pdf:
                raise RuntimeError(f"PDF evidence trace is incomplete: {ticker}: {source_id}")
            if source.get("url") and html_escape(str(source["url"]), quote=True) not in html:
                raise RuntimeError(f"HTML evidence URL is missing: {ticker}: {source_id}")
        artifacts = company["artifacts"]
        expected = {
            "report_json_sha256": root / "report.json",
            "report_html_sha256": root / "report.html",
            "long_png_sha256": root / "report-long.png",
            "mobile_png_sha256": root / "report-mobile.png",
            "pdf_sha256": root / "report.pdf",
            "narrative_artifact_sha256": root / "narrative-artifact.json",
            "evidence_manifest_receipt_sha256": root / "evidence-manifest-receipt.json",
            "claim_source_audit_receipt_sha256": root / "claim-source-audit-receipt.json",
            "transport_verification_receipt_sha256": root / "transport-verification-receipt.json",
        }
        if any(artifacts.get(key) != digest(path) for key, path in expected.items()):
            raise RuntimeError(f"live artifact digest mismatch: {ticker}")
    return {"status": "passed", "company_count": len(receipt["companies"])}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT_ROOT)
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.mkdir(parents=True, exist_ok=True)
    chrome = chrome_path()
    expected_modules = [item.id for item in MODULE_SPECS]
    companies = []
    for ticker, adapter in COMPANY_ADAPTERS.items():
        snapshot_id = f"acceptance_{ticker.replace('.', '_')}"
        baseline = acceptance_baseline(adapter, snapshot_id=snapshot_id, cutoff=CUTOFF)
        packet = acceptance_evidence(adapter, snapshot_id=snapshot_id, cutoff=CUTOFF)
        report = build_cross_company_report(baseline, packet)
        errors = validate_report_contract(report["report_contract"], report)
        if errors:
            raise RuntimeError(f"{ticker} report contract failed: {errors}")
        company_dir = output / ticker
        company_dir.mkdir(parents=True, exist_ok=True)
        json_path = company_dir / "report.json"
        html_path = company_dir / "report.html"
        png_path = company_dir / "report-long.png"
        mobile_path = company_dir / "report-mobile.png"
        pdf_path = company_dir / "report.pdf"
        json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        html = render_standalone_html(report)
        html_path.write_text(html, encoding="utf-8")
        rendered_modules = re.findall(r'data-report-module="([^"]+)"', html)
        if rendered_modules != expected_modules:
            raise RuntimeError(f"{ticker} rendered module order changed")
        for source in report["sources"]:
            if f'id="evidence-{source["id"]}"' not in html or f'data-evidence-id="{source["id"]}"' not in html:
                raise RuntimeError(f"{ticker} rendered evidence trace is incomplete")
            if source.get("url") and html_escape(str(source["url"]), quote=True) not in html:
                raise RuntimeError(f"{ticker} rendered evidence URL is missing")
        geometry = render(chrome, html_path, png_path, mobile_path, pdf_path)
        width, height = png_dimensions(png_path)
        mobile_width, mobile_height = png_dimensions(mobile_path)
        pages = pdf_page_count(pdf_path)
        pdf_modules = pdf_module_order(pdf_path)
        extracted_pdf = pdf_text(pdf_path)
        if any(source["id"] not in extracted_pdf for source in report["sources"]):
            raise RuntimeError(f"{ticker} PDF evidence trace is incomplete")
        if (
            width != 1440 or height != geometry["desktop_scroll_height"]
            or mobile_width != 390 or mobile_height != geometry["mobile_scroll_height"]
            or pages < 2
        ):
            raise RuntimeError(
                f"{ticker} render evidence is incomplete: desktop {width}x{height}, "
                f"mobile {mobile_width}x{mobile_height}, {pages} PDF pages"
            )
        companies.append({
            "ticker": ticker, "name": adapter.name, "industry": adapter.industry,
            "industry_key": adapter.industry_key, "report_hash": report["report_hash"],
            "production_input_identity": report["generated_from"]["production_input_identity"],
            "truth_set": report["report_contract"]["truth_set"],
            "module_ids": rendered_modules,
            "artifacts": {
                "json": str(json_path.relative_to(ROOT)), "json_sha256": digest(json_path),
                "html": str(html_path.relative_to(ROOT)), "html_sha256": digest(html_path),
                "long_png": str(png_path.relative_to(ROOT)), "png_dimensions": [width, height],
                "long_png_full_page": height == geometry["desktop_scroll_height"],
                "long_png_sha256": digest(png_path),
                "mobile_png": str(mobile_path.relative_to(ROOT)),
                "mobile_png_dimensions": [mobile_width, mobile_height],
                "mobile_png_full_page": mobile_height == geometry["mobile_scroll_height"],
                "mobile_png_sha256": digest(mobile_path),
                "pdf": str(pdf_path.relative_to(ROOT)), "pdf_pages": pages,
                "pdf_sha256": digest(pdf_path), "pdf_module_ids": pdf_modules,
            },
        })
    receipt = {
        "schema_version": "m4-cross-company-verification-v1",
        "status": "passed", "fixture_boundary": "format and pipeline acceptance only; not live investment research",
        "company_count": len(companies), "industry_count": len({item["industry_key"] for item in companies}),
        "same_eight_module_contract": all(item["module_ids"] == expected_modules for item in companies),
        "deepseek_boundary": "frozen evidence only; network forbidden during synthesis",
        "companies": companies,
    }
    receipt_path = output / "verification-receipt.json"
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    live_root = output / "live"
    if live_root.is_dir() and (live_root / "publication-receipt.json").is_file():
        receipt["live_publication"] = verify_live_publication(live_root)
        receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
