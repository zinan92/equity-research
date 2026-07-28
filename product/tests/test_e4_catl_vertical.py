from __future__ import annotations
import sys
from pathlib import Path
PRODUCT=Path(__file__).resolve().parents[1]
if str(PRODUCT) not in sys.path: sys.path.insert(0,str(PRODUCT))
from data_core.e4_catl_vertical import compile_catl_vertical

def test_incomplete_page_bound_history_degrades_to_no_action():
 value=compile_catl_vertical({'reports':[{'period':'2025FY','facts':[],'missing_metrics':[{'metric':'revenue','raw_text_excerpt':'raw'}]}]}, {'quote':{'last_price':390.86}}, context_manifest_hash='a'*64,dossier_id='catl')
 assert value['valuation']['valuation_completeness']=='missing'
 assert value['decision']['action']=='no_action'
 assert 'insufficient_evidence_coverage' in value['decision']['reasons']
 assert value['decision']['valuation_completeness']=='missing'
