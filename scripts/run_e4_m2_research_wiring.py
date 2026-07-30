#!/usr/bin/env python3
"""Bind previously generated, receipt-identified E4/R2 outputs into C1."""
from __future__ import annotations
import argparse, hashlib, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'product'))
from data_core.e4_page_level_filing_facts import FilingNumericFact
from data_core.e4_judgment_wiring import wire_unreviewed_judgment_receipt
from data_core.e4_l1_m4_governance_events import validate_receipt as validate_governance_receipt
from data_core.e4_r2_industry_wiring import wire_r2_industry_receipts
from data_core.e4_vertical_degradation import compile_vertical_degradation

TARGETS=('300750.SZ','600519.SH','000001.SZ')
def fact(x):
 return FilingNumericFact(x['ticker'],x['metric'],float(x['value']),x['document_id'],x['raw_hash'],int(x['page_number']),x['quoted_label'],x['quoted_anchor'],x['report_period'],x['statement_scope'],x['unit'],x['currency'],x['source_url'])
def main():
 p=argparse.ArgumentParser();p.add_argument('financial_sequences',type=Path);p.add_argument('m1_receipt',type=Path);p.add_argument('r2_receipt',type=Path);p.add_argument('--r2-acceptance',type=Path);p.add_argument('--judgments',type=Path,action='append');p.add_argument('--governance',type=Path,action='append');p.add_argument('--out',type=Path,required=True);a=p.parse_args()
 seq={x['ticker']:x for x in json.loads(a.financial_sequences.read_text())['tickers']}; m1={x['ticker']:x for x in json.loads(a.m1_receipt.read_text())['rows']}; r2_receipt=json.loads(a.r2_receipt.read_text())
 judgment_receipts=[json.loads(path.read_text()) for path in (a.judgments or [])]
 judgments_by_ticker={str(receipt.get('ticker','')).upper():receipt for receipt in judgment_receipts}
 if len(judgments_by_ticker)!=len(judgment_receipts): raise ValueError('duplicate or missing judgment receipt ticker')
 governance_receipts=[json.loads(path.read_text()) for path in (a.governance or [])]
 for receipt in governance_receipts: validate_governance_receipt(receipt,ticker=str(receipt.get('ticker','')))
 governance_by_ticker={str(receipt.get('ticker','')).upper():receipt for receipt in governance_receipts}
 if len(governance_by_ticker)!=len(governance_receipts): raise ValueError('duplicate or missing governance receipt ticker')
 r2_acceptance=json.loads(a.r2_acceptance.read_text()) if a.r2_acceptance else None
 rows=[]
 for ticker in TARGETS:
  source=seq[ticker]; fs=[fact(x) for report in source['reports'] for x in report.get('facts',[]) if x.get('statement_scope')=='consolidated']
  inputs={}
  market=m1.get(ticker,{}).get('market',{})
  decision=m1.get(ticker,{}).get('decision')
  reports=source.get('reports',[])
  if market.get('status')=='available':
   quote=market['quote'];inputs.setdefault('one_line_positioning',{})['market_snapshot']={'quote':quote,'receipt_id':m1[ticker].get('ticker')+':m1'}
  if decision:
   inputs.setdefault('plain_language_verdict',{})['decision_policy_output']={'receipt':decision,'receipt_id':ticker+':m1'}
  income=[x for report in reports for x in report.get('facts',[]) if x.get('metric') in {'revenue','operating_cost','net_profit_parent'}]
  cash=[x for report in reports for x in report.get('facts',[]) if x.get('metric') in {'operating_cash_flow','capital_expenditure'}]
  balance=[x for report in reports for x in report.get('facts',[]) if x.get('metric') in {'total_assets','total_liabilities','total_equity','cash','short_term_borrowings','long_term_borrowings'}]
  financial_evidence=income+cash+balance
  if financial_evidence: inputs.setdefault('financials_and_valuation',{})['financial_evidence']=financial_evidence
  if r2_acceptance:
   r2_inputs, _r2_gaps=wire_r2_industry_receipts(r2_acceptance, r2_receipt, ticker=ticker)
   for section_id, values in r2_inputs.items(): inputs.setdefault(section_id,{}).update(values)
  judgments=judgments_by_ticker.get(ticker)
  if judgments:
   for section_id, values in wire_unreviewed_judgment_receipt(judgments, ticker=ticker).items():
    inputs.setdefault(section_id, {}).update(values)
  governance=governance_by_ticker.get(ticker)
  if governance:
   gi=governance['inputs']
   if gi.get('management_record',{}).get('status')=='available': inputs.setdefault('founder_and_team',{})['management_evidence']=[{'records':gi['management_record']['records'],'source_receipt':governance['receipt_id']}]
   if gi.get('governance_events',{}).get('status')=='available': inputs.setdefault('founder_and_team',{})['governance_evidence']=gi['governance_events']['records']
  result=compile_vertical_degradation(ticker,fs,known_at='2026-07-29T00:00:00Z',additional_section_inputs=inputs)
  rows.append({'ticker':ticker,'status':'available','result':result,'input_receipts':{'financial_sequences_sha256':hashlib.sha256(a.financial_sequences.read_bytes()).hexdigest(),'m1_sha256':hashlib.sha256(a.m1_receipt.read_bytes()).hexdigest(),'r2_receipt_id':f"{r2_receipt.get('schema_version')}:{r2_receipt.get('receipt_hash')}" if r2_acceptance else None,'r2_acceptance_receipt_id':f"{r2_acceptance.get('schema_version')}:{r2_acceptance.get('receipt_hash')}" if r2_acceptance else None,'judgment_receipt_id':f"{judgments['schema_version']}:{judgments['receipt_hash']}" if judgments else None,'governance_receipt_id':governance.get('receipt_id') if governance else None}})
 out={'schema_version':'e4-m2-research-wiring-v1','data_kind':'real','rows':rows};out['receipt_hash']=hashlib.sha256(json.dumps(out,sort_keys=True,default=str).encode()).hexdigest();a.out.write_text(json.dumps(out,ensure_ascii=False,indent=2,default=str)+'\n'); print(a.out)
if __name__=='__main__':main()
