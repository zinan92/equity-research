#!/usr/bin/env python3
"""Fail closed on generic or uncited L1-M2 judgment drafts."""
from __future__ import annotations
import argparse, json
from pathlib import Path

REQUIRED=("investment_thesis","variant_view","moat_assessment","risk_register","falsification_tests","monitoring_kpis","action_triggers","accounting_checks","operating_kpis","margin_bridge")
NEED=("document_id","raw_hash","page_number","quoted_anchor","source_url")
def main():
 p=argparse.ArgumentParser();p.add_argument('receipt',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args();r=json.loads(a.receipt.read_text());errors=[];rows=[]
 for key in REQUIRED:
  v=r.get('content',{}).get(key,{}); status=v.get('status'); row={'id':key,'status':status,'reason':v.get('reason'),'citation_mix':v.get('citation_mix')}
  if status=='ai_generated_judgment_unreviewed':
   if '宁德时代' not in str(v.get('text')) or v.get('name_swap_test',{}).get('status')!='passed': errors.append(key+':name_swap')
   for f in v.get('facts',[]):
    if any(not f.get('citation',{}).get(x) for x in NEED): errors.append(key+':citation')
   if not v.get('claims'): errors.append(key+':claims')
  elif status!='missing': errors.append(key+':status')
  rows.append(row)
 tests=r.get('content',{}).get('falsification_tests',{}).get('tests',[])
 if tests and any(not all(t.get(x) is not None for x in ('direction','threshold','time_window')) for t in tests): errors.append('falsification_fields')
 out={'status':'passed' if not errors else 'failed','receipt_id':f"{r.get('schema_version')}:{r.get('receipt_hash')}",'judgments':rows,'name_swap_pass_rate':sum(x['status']=='ai_generated_judgment_unreviewed' for x in rows)/max(1,sum(x['status']!='missing' for x in rows)),'errors':errors};a.out.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps(out,ensure_ascii=False));raise SystemExit(bool(errors))
if __name__=='__main__':main()
