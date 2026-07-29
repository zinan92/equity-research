#!/usr/bin/env python3
"""Fail closed on generic model-judgment receipt and sentence provenance."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping


NUMBER = re.compile(
    r"(?<![A-Za-z0-9])[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?(?![A-Za-z0-9])"
)
SENTENCE_BREAK = re.compile(r"(?<=[。！？；])\s*|\n+")
NEED = ("document_id", "raw_hash", "page_number", "quoted_anchor", "source_url")
FUTURE_MARKERS = ("下一", "下次", "后续", "未来")


def _receipt_hash(receipt: Mapping[str, Any]) -> str:
    payload = {key: value for key, value in receipt.items() if key != "receipt_hash"}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode()
    ).hexdigest()


def _source_text(fact: Mapping[str, Any]) -> str:
    if fact.get("evidence_type") in {"official_narrative", "narrative_block"}:
        return str(fact.get("value") or "")
    return str(
        (fact.get("citation") or {}).get("quoted_anchor")
        or fact.get("value")
        or ""
    )


def _source_constants(tree: ast.AST) -> dict[str, Any]:
    wanted = {
        "GENERATOR_VERSION",
        "PROMPT_VERSION",
        "VALIDATOR_VERSION",
        "_SYSTEM_PROMPT",
    }
    result = {}
    for node in getattr(tree, "body", ()):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if isinstance(target, ast.Name) and target.id in wanted:
            result[target.id] = ast.literal_eval(node.value)
    return result


def _verify_quotes(
    *,
    judgment_id: str,
    field_name: str,
    quotes: Any,
    evidence_ids: list[str],
    facts: Mapping[str, Mapping[str, Any]],
    errors: list[str],
) -> None:
    if not isinstance(quotes, list) or not quotes:
        errors.append(judgment_id + ": " + field_name + " lacks supporting quotes")
        return
    for quote in quotes:
        evidence_id = str(quote.get("evidence_id") or "")
        text = str(quote.get("quote") or "").strip()
        if evidence_id not in evidence_ids or evidence_id not in facts:
            errors.append(judgment_id + ": supporting quote evidence mismatch")
        elif len(text) < 8 or text not in _source_text(facts[evidence_id]):
            errors.append(judgment_id + ": supporting quote is not verbatim")


def _sentences(text: str) -> list[str]:
    return [
        item.strip()
        for item in SENTENCE_BREAK.split(text.strip())
        if item.strip()
    ]


def _numeric_displays(fact: Mapping[str, Any]) -> set[str]:
    displays = set()
    if fact.get("display_value") not in (None, ""):
        displays.add(str(fact["display_value"]))
    displays.update(re.findall(r"\d+", str(fact.get("citation", {}).get("report_period") or "")))
    if fact.get("evidence_type") == "deterministic_derived_metric":
        displays.add(str(fact.get("value") or ""))
    if fact.get("evidence_type") in {"official_narrative", "narrative_block"}:
        displays.update(NUMBER.findall(str(fact.get("value") or "")))
    return displays


def verify(receipt: Mapping[str, Any], generator_path: Path) -> dict[str, Any]:
    errors: list[str] = []
    if receipt.get("schema_version") != "e4-model-judgments-v1":
        errors.append("unsupported receipt schema")
    if receipt.get("data_kind") != "real":
        errors.append("receipt is not a real run")
    if receipt.get("receipt_hash") != _receipt_hash(receipt):
        errors.append("receipt hash mismatch")
    if not receipt.get("source_narrative_receipt"):
        errors.append("narrative source receipt is absent")
    if not receipt.get("source_financial_receipt_sha256"):
        errors.append("financial source receipt is absent")
    model_receipts = receipt.get("model_receipts") or []
    if not model_receipts or not all(
        row.get("request_id")
        and row.get("model")
        and row.get("finish_reason") == "stop"
        and row.get("purpose")
        for row in model_receipts
    ):
        errors.append("real model-call receipt is incomplete")
    response_hashes = receipt.get("response_hashes") or []
    if (
        len(response_hashes) != len(model_receipts)
        or any(not re.fullmatch(r"[0-9a-f]{64}", str(item)) for item in response_hashes)
    ):
        errors.append("model response hash chain is incomplete")

    source = generator_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    constants = _source_constants(tree)
    for receipt_key, source_key in (
        ("generator_version", "GENERATOR_VERSION"),
        ("prompt_version", "PROMPT_VERSION"),
        ("validator_version", "VALIDATOR_VERSION"),
    ):
        if receipt.get(receipt_key) != constants.get(source_key):
            errors.append(receipt_key + " does not match generator source")
    if receipt.get("prompt_hash") != _canonical_hash(constants.get("_SYSTEM_PROMPT")):
        errors.append("prompt hash does not match generator source")
    content = receipt.get("content") or {}
    if receipt.get("content_hash") != _canonical_hash(content):
        errors.append("content hash mismatch")
    if not re.fullmatch(r"[0-9a-f]{64}", str(receipt.get("input_hash") or "")):
        errors.append("input hash is malformed")
    identity = receipt.get("issuer_identity") or {}
    hardcoded = [
        term
        for term in (
            str(receipt.get("ticker") or ""),
            str(identity.get("name") or ""),
        )
        if term and term in source
    ]
    if "catl" in generator_path.name.lower():
        hardcoded.append("issuer-specific module name")
    if hardcoded:
        errors.append("generator contains issuer hardcoding: " + ", ".join(hardcoded))
    joined_strings = sum(isinstance(node, ast.JoinedStr) for node in ast.walk(tree))
    if joined_strings:
        errors.append("generator contains f-string syntax")

    sentence_total = 0
    sentence_specific = 0
    numeric_total = 0
    numeric_traced = 0
    available = 0
    rows = []
    reported_errors = (receipt.get("validation") or {}).get("errors") or {}
    for judgment_id, value in sorted(content.items()):
        status = value.get("status")
        if status == "missing":
            if not value.get("reason") or value.get("text") or value.get("claims"):
                errors.append(judgment_id + ": malformed missing item")
            if value.get("reason") == "generation_validation_failure":
                if judgment_id not in reported_errors:
                    errors.append(judgment_id + ": missing validation error mapping")
            elif judgment_id in reported_errors:
                errors.append(judgment_id + ": unexpected validation error mapping")
            rows.append(
                {
                    "judgment_id": judgment_id,
                    "status": status,
                    "reason": value.get("reason"),
                }
            )
            continue
        if status != "ai_generated_judgment_unreviewed":
            errors.append(judgment_id + ": invalid judgment status")
            continue
        available += 1
        sentences = _sentences(str(value.get("text") or ""))
        claims = value.get("claims") or []
        claim_texts = [str(item.get("text") or "").strip() for item in claims]
        if sentences != claim_texts:
            errors.append(judgment_id + ": sentence/claim mismatch")
        sentence_total += len(sentences)
        name_swap = value.get("name_swap_test") or {}
        audit_rows = name_swap.get("sentences") or []
        if len(audit_rows) != len(sentences):
            errors.append(judgment_id + ": incomplete sentence rename audit")
        for audit in audit_rows:
            if audit.get("status") == "passed" and audit.get("specific_anchors"):
                sentence_specific += 1
            else:
                errors.append(judgment_id + ": generic sentence survived validation")
        facts = {str(item.get("evidence_id")): item for item in value.get("facts") or []}
        for claim in claims:
            if claim.get("claim_type") != "inference":
                errors.append(judgment_id + ": claim is not an inference")
            evidence_ids = [str(item) for item in claim.get("evidence_ids") or []]
            if not evidence_ids or any(item not in facts for item in evidence_ids):
                errors.append(judgment_id + ": claim evidence identity mismatch")
                continue
            _verify_quotes(
                judgment_id=judgment_id,
                field_name="claim",
                quotes=claim.get("supporting_quotes"),
                evidence_ids=evidence_ids,
                facts=facts,
                errors=errors,
            )
            for citation in claim.get("citations") or []:
                if any(citation.get(key) in (None, "") for key in NEED):
                    errors.append(judgment_id + ": incomplete claim citation")
            allowed = {
                token
                for evidence_id in evidence_ids
                for token in _numeric_displays(facts[evidence_id])
            }
            for token in NUMBER.findall(str(claim.get("text") or "")):
                numeric_total += 1
                if token in allowed:
                    numeric_traced += 1
                else:
                    errors.append(
                        judgment_id + ": untraceable numeric token " + token
                    )
        if judgment_id == "falsification_tests":
            tests = value.get("tests")
            if not isinstance(tests, list) or not tests:
                errors.append(judgment_id + ": tests are absent")
            else:
                for test in tests:
                    evidence_ids = [
                        str(item) for item in test.get("evidence_ids") or []
                    ]
                    if (
                        test.get("direction") not in {"below", "above"}
                        or any(item not in facts for item in evidence_ids)
                    ):
                        errors.append(judgment_id + ": malformed test evidence")
                        continue
                    _verify_quotes(
                        judgment_id=judgment_id,
                        field_name="test",
                        quotes=test.get("supporting_quotes"),
                        evidence_ids=evidence_ids,
                        facts=facts,
                        errors=errors,
                    )
                    threshold_id = str(test.get("threshold_evidence_id") or "")
                    baseline = test.get("latest_actual_baseline") or {}
                    baseline_id = str(baseline.get("evidence_id") or "")
                    if threshold_id not in facts or baseline_id not in facts:
                        errors.append(judgment_id + ": test fact identity mismatch")
                        continue
                    if str(test.get("threshold") or "") != str(
                        facts[threshold_id].get("display_value") or ""
                    ):
                        errors.append(judgment_id + ": threshold display mismatch")
                    for key, fact_key in (
                        ("display_value", "display_value"),
                        ("unit", "unit"),
                        ("period", "citation"),
                    ):
                        if fact_key == "citation":
                            expected = (
                                facts[baseline_id].get("citation") or {}
                            ).get("report_period")
                        else:
                            expected = facts[baseline_id].get(fact_key)
                            if expected in (None, ""):
                                expected = (
                                    facts[baseline_id].get("citation") or {}
                                ).get(fact_key)
                        if str(baseline.get(key) or "") != str(expected or ""):
                            errors.append(
                                judgment_id + ": baseline " + key + " mismatch"
                            )
                    if not any(
                        marker in str(test.get("time_window") or "")
                        for marker in FUTURE_MARKERS
                    ):
                        errors.append(judgment_id + ": test window is not future")
                    allowed = {
                        token
                        for evidence_id in evidence_ids
                        for token in _numeric_displays(facts[evidence_id])
                    }
                    for token in NUMBER.findall(
                        json.dumps(test, ensure_ascii=False)
                    ):
                        numeric_total += 1
                        if token in allowed:
                            numeric_traced += 1
                        else:
                            errors.append(
                                judgment_id
                                + ": untraceable test numeric token "
                                + token
                            )
        rows.append(
            {
                "judgment_id": judgment_id,
                "status": status,
                "sentences": len(sentences),
                "specific_sentences": sum(
                    item.get("status") == "passed" for item in audit_rows
                ),
            }
        )
    reported = (receipt.get("validation") or {}).get("name_swap") or {}
    if (
        reported.get("passed_sentences") != sentence_specific
        or reported.get("total_sentences") != sentence_total
    ):
        errors.append("receipt name-swap aggregate mismatch")
    error_keys = set(reported_errors)
    missing_failure_keys = {
        judgment_id
        for judgment_id, value in content.items()
        if value.get("status") == "missing"
        and value.get("reason") == "generation_validation_failure"
    }
    if error_keys != missing_failure_keys:
        errors.append("validation errors do not match generation failures")
    return {
        "status": "passed" if not errors else "failed",
        "receipt_id": str(receipt.get("schema_version")) + ":" + str(receipt.get("receipt_hash")),
        "ticker": receipt.get("ticker"),
        "model": model_receipts[-1].get("model") if model_receipts else None,
        "available_judgments": available,
        "name_swap": {
            "passed_sentences": sentence_specific,
            "total_sentences": sentence_total,
            "pass_rate": sentence_specific / sentence_total if sentence_total else 0.0,
        },
        "concrete_sentence_ratio": (
            sentence_specific / sentence_total if sentence_total else 0.0
        ),
        "numeric_traceability": {
            "traced_tokens": numeric_traced,
            "total_tokens": numeric_total,
            "pass_rate": numeric_traced / numeric_total if numeric_total else 1.0,
        },
        "source_scan": {
            "generator_path": str(generator_path),
            "f_strings": joined_strings,
            "issuer_hardcoding": hardcoded,
        },
        "judgments": rows,
        "errors": sorted(set(errors)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument(
        "--generator",
        type=Path,
        default=Path("product/data_core/e4_model_judgments.py"),
    )
    args = parser.parse_args()
    result = verify(
        json.loads(args.receipt.read_text(encoding="utf-8")),
        args.generator,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
