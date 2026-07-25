#!/usr/bin/env python3
"""Write runtime-only page-cited E4 sell-side claim candidate receipts."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'product'))
from data_core.e4_sell_side_claim_candidates import write_sell_side_claim_candidates
def main()->None:
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('batch',type=Path);p.add_argument('page_evidence',type=Path);p.add_argument('--runtime-root',type=Path,required=True);a=p.parse_args()
 result=write_sell_side_claim_candidates(a.batch,a.page_evidence,a.runtime_root);print(json.dumps({'path':result['path'],'counts':result['receipt']['counts'],'receipt_hash':result['receipt']['receipt_hash']},ensure_ascii=False))
if __name__=='__main__':main()
