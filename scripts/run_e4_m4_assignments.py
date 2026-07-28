#!/usr/bin/env python3
"""Select one page-bound M2 fact per ticker for audit, preserving coverage gaps."""
from __future__ import annotations
import argparse,json
from pathlib import Path
def main():
 p=argparse.ArgumentParser();p.add_argument('m2',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args(); src=json.loads(a.m2.read_text()); assignments=[]; gaps=[]
 for row in src['tickers']:
  facts=[f for report in row['reports'] for f in report.get('facts',[]) if f.get('column_identity') in ('current_period','period_end')]
  if not facts: gaps.append({'ticker':row['ticker'],'reason':'no_eligible_page_bound_fact'}); continue
  f=facts[0]; assignments.append({'ticker':row['ticker'],'numeric_check':{'metric':f['metric'],'expected_value':f['value'],'unit':f['unit'],'currency':f['currency'],'report_period':f['report_period'],'statement_scope':f['statement_scope'],'column_identity':f['column_identity'],'cross_year_status':'unverified'},'page_citation_check':{'document_id':f['document_id'],'raw_hash':f['raw_hash'],'page_number':f['page_number'],'quoted_label':f['quoted_label'],'quoted_anchor':f['quoted_anchor'],'source_url':f['source_url']},'review_status':'pending_human_review'})
 out={'schema_version':'e4-m4-page-bound-assignments-v1','data_kind':'runtime_only_audit','assignments':assignments,'coverage_gaps':gaps,'counts':{'assigned':len(assignments),'unassigned':len(gaps)},'truth_boundary':{'assignments_are_not_completed_audits':True,'counts_as_numeric_page_audit':False,'counts_as_tier_a_or_b':False}}
 a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps(out['counts']))
if __name__=='__main__': main()
