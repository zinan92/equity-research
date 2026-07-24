from __future__ import annotations
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from data_core.research_quality_dashboard import build_expansion_gate
def test_gate_is_fail_closed_and_requires_issue_for_correction():
    good={"status":"passed"}
    assert build_expansion_gate(coverage=good,cadence=good,citations=good,outcomes=good)["decision"] == "go"
    blocked=build_expansion_gate(coverage=good,cadence={"status":"missing"},citations=good,outcomes=good,correction_issue="#12")
    assert blocked["decision"] == "no_go"
    assert blocked["blocked_by"] == ["cadence","manual_correction"]
