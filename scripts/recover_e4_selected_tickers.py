#!/usr/bin/env python3
"""Recover one official page-fact set for named remaining M4 tickers.

The collector tries the most recent annual report first and only falls back to
an older official annual report when the current one has no page-bound facts.
It never substitutes a vendor field or manufactures an audit candidate.
"""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'product'))
from data_core.e4_financial_sequence_batch import _capture_one
from data_core.official_filings import OfficialHttpTransport


PERIODS = ("2025FY", "2024FY", "2023FY")


def recover_ticker(ticker: str, transport: OfficialHttpTransport) -> dict:
    attempts = []
    for period in PERIODS:
        report = _capture_one(ticker, period, transport=transport)
        attempts.append(report)
        if report.get("facts"):
            return {"ticker": ticker, "report": report, "attempts": attempts}
    return {"ticker": ticker, "report": attempts[-1], "attempts": attempts}
def main():
 p=argparse.ArgumentParser();p.add_argument('tickers',nargs='+');p.add_argument('--out',required=True,type=Path);a=p.parse_args();t=OfficialHttpTransport(timeout_seconds=5,min_request_interval_seconds=1);rows=[]
 for ticker in a.tickers:
  rows.append(recover_ticker(ticker, t))
 a.out.write_text(json.dumps({'schema_version':'e4-selected-recovery-v1','data_kind':'real','rows':rows},ensure_ascii=False,indent=2)+'\n'); print(json.dumps([(x['ticker'],len(x['report'].get('facts',()))) for x in rows]))
if __name__=='__main__':main()
