#!/usr/bin/env python3
"""Recover one current official annual-report fact for each M2 audit gap."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'product'))
from data_core.e4_financial_sequence_batch import _capture_one
from data_core.official_filings import OfficialHttpTransport
def main():
 p=argparse.ArgumentParser();p.add_argument('m2',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args();src=json.loads(a.m2.read_text());t=OfficialHttpTransport(timeout_seconds=5,min_request_interval_seconds=1);rows=[]
 for row in src['tickers']:
  if any(r.get('facts') for r in row['reports']): continue
  rows.append({'ticker':row['ticker'],'report':_capture_one(row['ticker'],'2025FY',transport=t)})
 out={'schema_version':'e4-audit-gap-recovery-v1','data_kind':'real','rows':rows,'counts':{'requested':len(rows),'facts':sum(len(x['report'].get('facts',())) for x in rows)}};a.out.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps(out['counts']))
if __name__=='__main__':main()
