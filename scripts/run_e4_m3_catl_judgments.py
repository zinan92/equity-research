#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'product'))
from data_core.e4_catl_judgment_content import compile_catl_judgments
def main():
 p=argparse.ArgumentParser();p.add_argument('m2_receipt',type=Path);p.add_argument('r2_receipt',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
 m2=json.loads(a.m2_receipt.read_text()); r2=json.loads(a.r2_receipt.read_text())
 catl=next(x for x in m2['rows'] if x['ticker']=='300750.SZ'); dossier=next(x for x in r2['rows'] if x['ticker']=='300750.SZ')
 content=compile_catl_judgments(catl['result']['page_facts'],dossier_id=dossier['dossier_id'])
 out={'schema_version':'e4-m3-catl-judgments-v1','data_kind':'real','ticker':'300750.SZ','source_dossier_receipt':'n3-dossier-batch-10dd875e32907e14','content':content};out['receipt_hash']=hashlib.sha256(json.dumps(out,sort_keys=True).encode()).hexdigest();a.out.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(a.out)
if __name__=='__main__':main()
