#!/usr/bin/env python3
"""Compile explicit human review decisions into admitted sell-side claims."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'product'))
from data_core.e4_sell_side_claim_admission import write_admitted_sell_side_claims,write_empty_claim_review_decisions
def main()->None:
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('candidates',type=Path);p.add_argument('decisions',type=Path,nargs='?');p.add_argument('--runtime-root',type=Path,required=True);p.add_argument('--init-empty',action='store_true');a=p.parse_args()
 if a.init_empty:
  if a.decisions is not None:p.error('--init-empty does not take a decisions receipt')
  result=write_empty_claim_review_decisions(a.candidates,a.runtime_root);print(json.dumps({'path':result['path'],'counts':{'decisions':0},'receipt_hash':result['receipt']['receipt_hash']},ensure_ascii=False));return
 if a.decisions is None:p.error('decisions receipt is required unless --init-empty')
 result=write_admitted_sell_side_claims(a.candidates,a.decisions,a.runtime_root);print(json.dumps({'path':result['path'],'counts':result['receipt']['counts'],'receipt_hash':result['receipt']['receipt_hash']},ensure_ascii=False))
if __name__=='__main__':main()
