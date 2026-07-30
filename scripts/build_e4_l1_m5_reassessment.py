#!/usr/bin/env python3
"""Overlay only newly receipted L1 section inputs onto the frozen C1 result."""
from __future__ import annotations
import argparse,json,sys
from dataclasses import asdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'product'))
from data_core.e4_judgment_wiring import wire_unreviewed_judgment_receipt
from report_contract import build_research_section_contract_v3

def main():
 p=argparse.ArgumentParser();p.add_argument('wiring',type=Path);p.add_argument('judgments',type=Path);p.add_argument('governance',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
 base=json.loads(a.wiring.read_text());j=json.loads(a.judgments.read_text());g=json.loads(a.governance.read_text())
 catl=next(r for r in base['rows'] if r['ticker']=='300750.SZ')
 inputs=wire_unreviewed_judgment_receipt(j,ticker='300750.SZ')
 gi=g['inputs']; inputs['founder_and_team']={'management_evidence':[{'records':gi['management_record']['records'],'source_receipt':g['receipt_id']}],'governance_evidence':gi['governance_events']['records']}
 fresh=build_research_section_contract_v3(inputs)
 replace={s.section_id:asdict(s) for s in fresh.sections if s.section_id in inputs}
 sections=[replace.get(s['section_id'],s) for s in catl['result']['section_contract']['sections']]
 catl['result']['section_contract']['sections']=sections
 catl['result']['l1_receipts']={'judgments':j['receipt_id'] if 'receipt_id' in j else j['schema_version']+':'+j['receipt_hash'],'governance':g['receipt_id'],'sell_side_admission':'missing_policy_inadmissible_aggregator'}
 out={'schema_version':'e4-l1-m5-reassessment-v1','data_kind':'real','rows':base['rows'],'source_wiring_sha256':__import__('hashlib').sha256(a.wiring.read_bytes()).hexdigest(),'receipt_inputs':catl['result']['l1_receipts']}
 out['receipt_hash']=__import__('hashlib').sha256(json.dumps(out,ensure_ascii=False,sort_keys=True).encode()).hexdigest();a.out.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'receipt_hash':out['receipt_hash'],'changed_sections':sorted(replace)},ensure_ascii=False))
if __name__=='__main__':main()
