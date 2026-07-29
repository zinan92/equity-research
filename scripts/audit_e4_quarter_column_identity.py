#!/usr/bin/env python3
"""Audit stored page facts for quarterly/half-year column identity debt."""
from __future__ import annotations
import argparse, collections, json
from pathlib import Path
def main():
 p=argparse.ArgumentParser();p.add_argument('receipt',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args();src=json.loads(a.receipt.read_text());rows=[];counts=collections.Counter()
 for ticker in src.get('tickers',[]):
  for report in ticker.get('reports',[]):
   for fact in report.get('facts',[]):
    period=str(fact.get('report_period','')); identity=str(fact.get('column_identity','unknown'))
    quarter=('Q' in period or 'H1' in period)
    status='passed'
    if quarter and identity not in {'period_end','period_begin','current_period','previous_period'}: status='unresolved_quarter_column'
    if fact.get('metric')=='shares_outstanding' and fact.get('unit') not in {'股','shares'}: status='invalid_share_currency_unit'
    counts[status]+=1
    if status!='passed': rows.append({'ticker':fact.get('ticker'), 'period':period,'metric':fact.get('metric'),'status':status,'document_id':fact.get('document_id'),'page_number':fact.get('page_number'),'raw_text_excerpt':str(fact.get('quoted_anchor',''))[:520]})
 out={'schema_version':'e4-quarter-column-audit-v1','facts_examined':sum(counts.values()),'counts':dict(counts),'findings':rows};a.out.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'facts_examined':out['facts_examined'],'counts':out['counts']}))
if __name__=='__main__':main()
