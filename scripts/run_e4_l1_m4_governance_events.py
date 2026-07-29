#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'product'))
from data_core.e4_l1_m4_governance_events import build
def main():
 p=argparse.ArgumentParser();p.add_argument('narrative',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args();r=build(json.loads(a.narrative.read_text()));a.out.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'receipt_id':r['receipt_id'],'management':len(r['inputs']['management_record']['records']),'governance_events':len(r['inputs']['governance_events']['records'])},ensure_ascii=False))
if __name__=='__main__':main()
