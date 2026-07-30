from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "inventory_e4_section_completion.py"
spec = importlib.util.spec_from_file_location("inventory", SCRIPT)
inventory = importlib.util.module_from_spec(spec); assert spec and spec.loader; spec.loader.exec_module(inventory)


def section(section_id: str, status: str, present=(), missing=()):
    return {"section_id": section_id, "status": status, "present_required": list(present), "missing_required": list(missing)}


class InventoryTest(unittest.TestCase):
    def test_counts_distinct_section_dependencies_not_three_issuer_copies(self) -> None:
        rows = []
        for ticker in ("300750.SZ", "600519.SH", "000001.SZ"):
            sections = [section(item.section_id, "missing", missing=[entry.key for entry in item.required_inputs]) for item in inventory.RESEARCH_SECTION_SPECS_V3]
            rows.append({"ticker": ticker, "status": "available", "result": {"section_contract": {"sections": sections}}})
        result = inventory.build_inventory({"rows": rows})
        self.assertEqual(result["independent_missing_required_inputs"], 18)
        self.assertEqual(max(item["dependent_sections"] for item in result["leverage"]), 9)


if __name__ == "__main__":
    unittest.main()
