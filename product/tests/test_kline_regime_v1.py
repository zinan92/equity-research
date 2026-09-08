from __future__ import annotations

import ast
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from product.kline_regime import build_regime, validate_contract  # noqa: E402


def bars(count: int, direction: float = 0.0, *, forming: bool = False) -> list[dict]:
    result = []
    for index in range(count):
        close = 100.0 + direction * index
        result.append(
            {
                "timestamp": f"2026-01-{index + 1:02d}T00:00:00+00:00",
                "open": close - 0.2,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "volume": 1.0,
                **({"is_forming": True} if forming and index == count - 1 else {}),
            }
        )
    return result


class KlineRegimeV1Tests(unittest.TestCase):
    def test_trend_up_and_down_are_deterministic(self) -> None:
        upward = build_regime("XAU", bars(20, 2), bars(30, 1))
        downward = build_regime("XAU", bars(20, -2), bars(30, -1))
        self.assertEqual(upward["regime"], "trend_up")
        self.assertEqual(downward["regime"], "trend_down")
        self.assertFalse(upward["action_eligible"])
        self.assertEqual(upward, build_regime("XAU", bars(20, 2), bars(30, 1)))
        validate_contract(upward)

    def test_flat_series_is_range_with_percentile_bounds(self) -> None:
        result = build_regime("XAU", bars(20), bars(30))
        self.assertEqual(result["regime"], "range")
        self.assertEqual((result["range_low"], result["range_high"]), (99.0, 101.0))
        validate_contract(result)

    def test_insufficient_and_forming_bars_are_unavailable_with_reason(self) -> None:
        insufficient = build_regime("XAU", bars(19), bars(30))
        forming = build_regime("XAU", bars(20, forming=True), bars(30))
        for result in (insufficient, forming):
            self.assertEqual(result["regime"], "unavailable")
            self.assertTrue(result["reason"])
            self.assertFalse(result["action_eligible"])
            validate_contract(result)

    def test_digest_changes_when_input_changes(self) -> None:
        first = build_regime("XAU", bars(20), bars(30))
        changed = bars(20)
        changed[-1]["close"] = 100.5
        second = build_regime("XAU", changed, bars(30))
        self.assertNotEqual(first["inputs_digest"], second["inputs_digest"])

    def test_schema_is_strict_and_versioned(self) -> None:
        schema = json.loads((ROOT / "product/kline_regime/kline-regime-v1.schema.json").read_text())
        self.assertEqual(schema["additionalProperties"], False)
        self.assertEqual(schema["properties"]["action_eligible"]["const"], False)
        self.assertEqual(schema["properties"]["version"]["const"], "kline-regime-v1")

    def test_contract_modules_have_no_execution_or_control_imports(self) -> None:
        forbidden = {"broker", "execution", "risk", "strategy", "trading_system", "control"}
        for path in (ROOT / "product/kline_regime").glob("*.py"):
            tree = ast.parse(path.read_text(), filename=str(path))
            imports = [node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]
            imported = {alias.name.split(".")[0].lower() for node in imports for alias in node.names}
            self.assertTrue(forbidden.isdisjoint(imported), f"forbidden import in {path}: {imported & forbidden}")


if __name__ == "__main__":
    unittest.main()
