#!/usr/bin/env python3
"""Run honest no-action vertical receipts from an M2 financial-sequence receipt."""
from __future__ import annotations
import argparse, hashlib, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT / 'product'))
from data_core.e4_catl_vertical import compile_vertical

def main() -> int:
 p=argparse.ArgumentParser(); p.add_argument('m2_receipt',type=Path); p.add_argument('--out',required=True,type=Path); a=p.parse_args()
 src=json.loads(a.m2_receipt.read_text()); rows=[]
 for row in src['tickers']:
  ticker=row['ticker']
  if ticker=='000001.SZ':
   rows.append({'ticker':ticker,'status':'not_applicable','reason':'bank_dcf_not_applicable','raw_text_excerpt':'Bank income statements use net interest income and regulatory capital; manufacturing FCF DCF is not applied.','decision':{'action':'no_action','reasons':['bank_profile_required']}}); continue
  vertical=compile_vertical({'reports':row['reports']},{},ticker=ticker,context_manifest_hash='0'*64,dossier_id='m3-batch')
  rows.append({'ticker':ticker,'status':vertical['valuation']['status'],'reason':vertical['valuation'].get('methods_missing',[]),'decision':vertical['decision'],'valuation_completeness':vertical['valuation']['valuation_completeness']})
 out={'schema_version':'e4-m3-vertical-batch-v1','data_kind':'real','rows':rows,'counts':{'tickers':len(rows),'decision_receipts':sum('decision' in x for x in rows),'no_action':sum(x.get('decision',{}).get('action')=='no_action' for x in rows)},'truth_boundary':{'does_not_promote_tier_or_action':True}}
 out['receipt_hash']=hashlib.sha256(json.dumps(out,sort_keys=True,separators=(',',':')).encode()).hexdigest(); a.out.parent.mkdir(parents=True,exist_ok=True); a.out.write_text(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)+'\n'); print(json.dumps({'counts':out['counts'],'path':str(a.out)})); return 0
if __name__=='__main__': raise SystemExit(main())
