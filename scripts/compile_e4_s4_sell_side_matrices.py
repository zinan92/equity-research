#!/usr/bin/env python3
"""Compile C3 sell-side matrices from E4 runtime receipts."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'product'))
from data_core.e4_sell_side_matrix import compile_sell_side_matrices  # noqa: E402
def main() -> None:
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('batch',type=Path); p.add_argument('page_evidence',type=Path); p.add_argument('--runtime-root',type=Path,required=True); p.add_argument('--as-of',required=True); p.add_argument('--research-cutoff',required=True); p.add_argument('--out',type=Path,required=True); a=p.parse_args()
    value=compile_sell_side_matrices(a.batch,a.page_evidence,a.runtime_root,as_of=a.as_of,research_cutoff=a.research_cutoff); a.out.write_text(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8'); print(json.dumps({'path':str(a.out),'counts':value['counts'],'receipt_hash':value['receipt_hash']},ensure_ascii=False))
if __name__=='__main__': main()
