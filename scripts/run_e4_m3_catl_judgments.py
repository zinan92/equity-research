#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'product'))
from data_core.e4_catl_judgment_content import compile_catl_judgments
def main():
 p=argparse.ArgumentParser();p.add_argument('m2_receipt',type=Path);p.add_argument('--narrative-receipt',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
 m2=json.loads(a.m2_receipt.read_text()); narrative=json.loads(a.narrative_receipt.read_text())
 if narrative.get('schema_version')!='e4-official-narrative-evidence-v1' or narrative.get('data_kind')!='real' or narrative.get('ticker')!='300750.SZ': raise ValueError('narrative receipt is not a real CATL official-PDF run')
 catl=next(x for x in m2['rows'] if x['ticker']=='300750.SZ')
 dossier_id='e4-l1-m2:'+str(narrative['receipt_hash'])
 content=compile_catl_judgments(catl['result']['page_facts'],dossier_id=dossier_id,narrative_blocks=narrative['blocks'])
 out={'schema_version':'e4-m3-catl-judgments-v2','data_kind':'real','ticker':'300750.SZ','source_narrative_receipt':narrative['receipt_id'],'source_financial_receipt_sha256':hashlib.sha256(a.m2_receipt.read_bytes()).hexdigest(),'content':content};out['receipt_hash']=hashlib.sha256(json.dumps(out,sort_keys=True).encode()).hexdigest();a.out.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(a.out)
if __name__=='__main__':main()
