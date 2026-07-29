#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'product'))
from data_core.e4_l1_m3_sell_side_admission import probe_catl_sell_side_admission
def main():
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();r=probe_catl_sell_side_admission();a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'receipt_id':r['receipt_id'],'inputs':r['inputs']},ensure_ascii=False))
if __name__=='__main__':main()
