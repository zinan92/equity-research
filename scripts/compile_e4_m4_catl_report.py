#!/usr/bin/env python3
"""Offline CATL report compiler over frozen receipts."""
from __future__ import annotations
import argparse, hashlib, html, json
from pathlib import Path
def h(x): return hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('m1',type=Path);p.add_argument('m2',type=Path);p.add_argument('m3',type=Path);p.add_argument('--out',type=Path,required=True);p.add_argument('--receipt',type=Path,required=True);a=p.parse_args()
 m1=json.loads(a.m1.read_text());m2=json.loads(a.m2.read_text());m3=json.loads(a.m3.read_text());catl=next(x for x in m2['rows'] if x['ticker']=='300750.SZ');d=next(x for x in m1['rows'] if x['ticker']=='300750.SZ')['decision'];sections=catl['result']['section_contract']['sections'];facts=catl['result']['page_facts']
 # Historical receipts predate the share-unit fix.  A monetary value may be
 # shown only as share_capital_amount, never as shares_outstanding.
 facts=[x for x in facts if x.get('metric')!='shares_outstanding' or x.get('unit') in {'股','shares'}]
 for x in facts:
  if x.get('metric')=='shares_outstanding': x['unit']='股'
 need=('document_id','raw_hash','page_number','quoted_anchor','source_url')
 if not all(all(x.get(k) for k in need) for x in facts): raise ValueError('citation gate rejected uncited fact')
 hashes={'m1':h(m1),'m2':h(m2),'m3':h(m3)};model=h({'ticker':'300750.SZ','inputs':hashes,'sections':sections,'decision':d})
 rows=''.join(f"<tr><td>{html.escape(x['section_id'])}</td><td>{html.escape(x['status'])}</td><td>{html.escape(', '.join(x['missing_required']) or '—')}</td></tr>" for x in sections)
 # Latest available observation is the lead fact; older facts form a visible
 # comparison series instead of silently becoming the report's headline.
 by_metric={}
 for item in facts:
  by_metric.setdefault(item['metric'],[]).append(item)
 lead=[]
 for metric, values in sorted(by_metric.items()):
  values.sort(key=lambda x: str(x.get('report_period','')))
  lead.append(values[-1])
 def line(x): return f"<li>{html.escape(x['metric'])} [{html.escape(x['report_period'])}]: {html.escape(str(x['value']))} {html.escape(x['unit'])} — <a href='{html.escape(x['source_url'])}'>PDF p.{x['page_number']}</a>; {html.escape(x['quoted_anchor'])}</li>"
 ev=''.join(line(x) for x in lead)
 trends=''.join(f"<h3>{html.escape(metric)}</h3><ul>{''.join(line(x) for x in values[-4:])}</ul>" for metric,values in sorted(by_metric.items()))
 def judgment_text(v): return v.get('text') or '; '.join(str(item.get('name',item)) if isinstance(item,dict) else str(item) for item in v.get('items',[])) or v.get('reason','')
 j=''.join(f"<article class='judgment'><h3>{html.escape(k)} <em>{html.escape(v['status'])}</em></h3><p>{html.escape(judgment_text(v))}</p><ul>{''.join(line({'metric':f['metric'],'report_period':f['citation']['report_period'],'value':f['value'],'unit':f['citation']['unit'],'source_url':f['citation']['source_url'],'page_number':f['citation']['page_number'],'quoted_anchor':f['citation']['quoted_anchor']}) for f in v.get('facts',[]))}</ul></article>" for k,v in m3['content'].items())
 nav=[]
 for label,sid in [('产业链位置','industry_structure'),('壁垒','competition_and_moat'),('财务兑现','profitability_and_earnings_quality'),('市场交易的未来','valuation'),('推翻信号','risks_and_falsification')]:
  sec=next(x for x in sections if x['section_id']==sid); nav.append(f"<li>{label}：{'可回答，见 '+sid if sec['status']!='missing' else '尚无证据支撑；缺 '+', '.join(sec['missing_required'])}</li>")
 latest=max((str(x.get('report_period','')) for x in facts),default='unknown'); market_asof=next(x for x in m1['rows'] if x['ticker']=='300750.SZ')['market']['quote'].get('observed_at','unknown')
 body=f'''<!doctype html><meta charset="utf-8"><title>宁德时代 | Evidence-bound Research Report</title><style>body{{font-family:Arial,"PingFang SC";max-width:900px;margin:48px auto;line-height:1.6;color:#162436}}h1{{border-bottom:3px solid #143b66}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ccd6e0;padding:7px;text-align:left}}.note,.judgment{{background:#f2f6fa;padding:14px;margin:12px 0}}em{{color:#9d2d20}}</style><h1>宁德时代（300750.SZ）</h1><p class=note><b>数据时点：最新财报期 {latest}；行情 as_of {market_asof}</b><br>Offline report · Report Model {model} · Facts and unreviewed AI judgment are separate.</p><h2>一句话定位</h2><p>基于冻结官方披露证据的电池产业链研究对象；结论仍受未完成证据约束。</p><h2>五问导航</h2><ol>{''.join(nav)}</ol><h2>决策边界（实际输入）</h2><pre>{html.escape(json.dumps(d,ensure_ascii=False,indent=2,default=str))}</pre><h2>18章终态</h2><table><tr><th>章节</th><th>状态</th><th>缺失输入</th></tr>{rows}</table><h2>最新期页级事实</h2><ul>{ev}</ul><h2>历史趋势（每项实际期次）</h2>{trends}<h2>判断内容（未审阅，事实引用内联）</h2>{j}<h2>大白话点评</h2><p>这是一份可翻回官方 PDF 的底稿，不是直接买卖建议；缺口写在章节表里。</p>'''
 a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(body,encoding='utf-8');r={'schema_version':'e4-m4-catl-report-v1','ticker':'300750.SZ','data_kind':'real','report_model_hash':model,'html_path':str(a.out),'word_count':len(body.split()),'sections':sections,'tier':catl['result']['degradation']['tier'],'tier_reasons':catl['result']['degradation']['reasons'],'input_hashes':hashes,'citation_gate':{'passed':True,'facts_rendered':len(facts)},'deepseek_narrative':{'used':False,'reason':'offline deterministic compile'}};r['receipt_hash']=h(r);a.receipt.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'html':str(a.out),'receipt':str(a.receipt),'tier':r['tier']}))
if __name__=='__main__':main()
