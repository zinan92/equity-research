#!/usr/bin/env python3
"""Apply column-identity period semantics to an existing immutable fact receipt."""
from __future__ import annotations
import argparse, json
from pathlib import Path
def period(value, identity):
 if identity=='unknown': return 'unresolved'
 y=int(value[:4])
 if identity=='period_begin': return f'{y-1}FY'
 if identity=='previous_period': return f'{y-1}{value[4:]}'
 return value
def main():
 p=argparse.ArgumentParser();p.add_argument('receipt',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args();x=json.loads(a.receipt.read_text());n=0
 for ticker in x.get('tickers',[]):
  for report in ticker.get('reports',[]):
   for fact in report.get('facts',[]):
    old=fact.get('report_period','');new=period(old,fact.get('column_identity','unknown'))
    if new!=old:n+=1;fact['report_period']=new
 x['period_reclassification_count']=n;a.out.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'period_reclassification_count':n}))
if __name__=='__main__':main()
