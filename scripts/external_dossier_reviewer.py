#!/usr/bin/env python3
"""Ask an external model to choose the stronger dossier in each blind pair.

The key is read from an external file and never printed. The response is
validated as one external_reader preference object compatible with
``dossier_blind_review.py prefer``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


API_URL = "https://api.deepseek.com/chat/completions"


def _secret(path: Path) -> str:
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise ValueError("API key file is empty")
    return value


def _validate_choices(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError("response choices must be a list")
    by_pair: dict[str, dict[str, Any]] = {}
    for row in value:
        if not isinstance(row, dict):
            raise ValueError("choice row must be an object")
        pair_id = str(row.get("pair_id") or "")
        if pair_id in by_pair or pair_id not in {f"P{i}" for i in range(1, 6)}:
            raise ValueError(f"invalid or duplicate pair_id: {pair_id}")
        preferred = str(row.get("preferred") or "").upper()
        if preferred not in {"A", "B", "TIE"}:
            raise ValueError(f"{pair_id}/preferred must be A, B or tie")
        row["preferred"] = preferred
        by_pair[pair_id] = row
    if set(by_pair) != {f"P{i}" for i in range(1, 6)}:
        raise ValueError("response must choose P1 through P5")
    return [by_pair[f"P{i}"] for i in range(1, 6)]


def review(pack_path: Path, key_path: Path, *, model: str) -> dict[str, Any]:
    pack = pack_path.read_text(encoding="utf-8")
    system = (
        "You are an independent institutional-equity-research editor. "
        "Choose the stronger overall dossier in each A/B pair without guessing authorship. "
        "Judge company-specific detail, evidence density, readability and anti-hype discipline together. "
        "Traceable facts and explicit unknowns matter, but mechanical tables alone do not equal depth. "
        "Return valid JSON only with top-level choices. Include concise notes but do not quote either dossier."
    )
    user = (
        "Review all five pairs in this blind pack. Output "
        '{"choices":[{"pair_id":"P1","preferred":"A","notes":"short"}]} '
        'with P1-P5 exactly once. Use preferred "tie" only when neither document is stronger.\n\n'
        + pack
    )
    request_payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 4000,
        "stream": False,
    }
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(request_payload, ensure_ascii=False).encode(),
        headers={
            "Authorization": f"Bearer {_secret(key_path)}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=360) as response:
            payload = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:1000]
        raise RuntimeError(f"DeepSeek API HTTP {exc.code}: {detail}") from exc
    choice = payload["choices"][0]
    if choice.get("finish_reason") != "stop":
        raise RuntimeError(f"external review incomplete: {choice.get('finish_reason')}")
    parsed = json.loads(choice["message"]["content"])
    choices = _validate_choices(parsed.get("choices"))
    prompt_hash = hashlib.sha256((system + "\n" + user).encode()).hexdigest()
    return {
        "schema_version": "external-dossier-review-v1",
        "reviewer": {
            "id": f"deepseek:{payload.get('model') or model}",
            "role": "external_reader",
            "choices": choices,
        },
        "receipt": {
            "request_id": payload.get("id"),
            "model": payload.get("model") or model,
            "finish_reason": choice.get("finish_reason"),
            "usage": payload.get("usage") or {},
            "pack_sha256": hashlib.sha256(pack.encode()).hexdigest(),
            "prompt_sha256": prompt_hash,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pack", required=True, type=Path)
    parser.add_argument("--key-file", required=True, type=Path)
    parser.add_argument("--model", default="deepseek-chat")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    result = review(args.pack, args.key_file, model=args.model)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    receipt = result["receipt"]
    print(
        json.dumps(
            {
                "model": receipt["model"],
                "finish_reason": receipt["finish_reason"],
                "usage": receipt["usage"],
                "pack_sha256": receipt["pack_sha256"],
                "out": str(args.out),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
