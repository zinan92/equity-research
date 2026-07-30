#!/usr/bin/env python3
"""Offline issuer-generic report compiler over frozen receipts."""
from __future__ import annotations
import argparse, hashlib, html, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'product'))
from company_research import company_adapter
from data_core.e4_judgment_wiring import wire_unreviewed_judgment_receipt
def h(x): return hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('m1',type=Path);p.add_argument('m2',type=Path);p.add_argument('m3',type=Path);p.add_argument('--audit',type=Path);p.add_argument('--ticker',required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--receipt',type=Path,required=True);a=p.parse_args();ticker=a.ticker.upper()
 m1=json.loads(a.m1.read_text());m2=json.loads(a.m2.read_text());m3=json.loads(a.m3.read_text());audit=json.loads(a.audit.read_text()) if a.audit else {'findings':[]};bad={(x.get('document_id'),x.get('page_number')) for x in audit.get('findings',[])};audit_summary=f"{audit.get('facts_examined',0)} 条事实：{audit.get('counts',{}).get('passed',0)} 通过，{len(audit.get('internal_contradictions',[]))} internal_contradiction";catl=next(x for x in m2['rows'] if x['ticker']==ticker);d=next(x for x in m1['rows'] if x['ticker']==ticker)['decision'];sections=catl['result']['section_contract']['sections'];facts=catl['result']['page_facts']
 wire_unreviewed_judgment_receipt(m3,ticker=ticker)
 unreviewed=[key for key,value in m3['content'].items() if value.get('status')=='ai_generated_judgment_unreviewed']
 # Historical receipts predate the share-unit fix.  A monetary value may be
 # shown only as share_capital_amount, never as shares_outstanding.
 facts=[x for x in facts if x.get('metric')!='shares_outstanding' or x.get('unit') in {'股','shares'}]
 for x in facts:
  if x.get('metric')=='shares_outstanding': x['unit']='股'
 need=('document_id','raw_hash','page_number','quoted_anchor','source_url')
 if not all(all(x.get(k) for k in need) for x in facts): raise ValueError('citation gate rejected uncited fact')
 hashes={'m1':h(m1),'m2':h(m2),'m3':h(m3)};model=h({'ticker':ticker,'inputs':hashes,'sections':sections,'decision':d})
 rows=''.join(f"<tr><td>{html.escape(x['section_id'])}</td><td>{html.escape(x['status'])}</td><td>{html.escape(x.get('status_reason') or '—')}</td><td>{html.escape(', '.join(x['missing_required']) or '—')}</td></tr>" for x in sections)
 # Latest available observation is the lead fact; older facts form a visible
 # comparison series instead of silently becoming the report's headline.
 by_metric={}
 for item in facts:
  by_metric.setdefault(item['metric'],[]).append(item)
 lead=[]
 for metric, values in sorted(by_metric.items()):
  values.sort(key=lambda x: str(x.get('report_period','')))
  resolved=[x for x in values if x.get('report_period') not in {'unknown','unresolved'}]
  # An unresolved fact stays in the audit corpus, but must not become the
  # reader-facing "latest" observation merely because its label sorts last.
  lead.append((resolved or values)[-1])
 def line(x): return f"<li>{html.escape(x['metric'])} [{html.escape(x['report_period'])}]: {html.escape(str(x['value']))} {html.escape(x['unit'])} — <a href='{html.escape(x['source_url'])}'>PDF p.{x['page_number']}</a>; {html.escape(x['quoted_anchor'])}</li>"
 ev=''.join(line(x) for x in lead)
 trends=''.join(f"<h3>{html.escape(metric)}</h3><ul>{''.join(line(x) for x in values[-4:])}</ul>" for metric,values in sorted(by_metric.items()))
 def judgment_text(v): return v.get('text') or '; '.join(str(item.get('name',item)) if isinstance(item,dict) else str(item) for item in v.get('items',[])) or v.get('reason','')
 def judgment(v):
  unreliable=any((f['citation'].get('document_id'),f['citation'].get('page_number')) in bad for f in v.get('facts',[])); status='unreliable' if unreliable else v['status']; return f"<article class='judgment'><h3><em>{html.escape(status)}</em></h3><p>{html.escape(judgment_text(v))}</p><ul>{''.join(line({'metric':f['metric'],'report_period':f['citation']['report_period'],'value':f['value'],'unit':f['citation']['unit'],'source_url':f['citation']['source_url'],'page_number':f['citation']['page_number'],'quoted_anchor':f['citation']['quoted_anchor']}) for f in v.get('facts',[]))}</ul></article>"
 j=''.join(f"<h3>{html.escape(k)}</h3>"+judgment(v) for k,v in m3['content'].items())
 nav=[]
 for label,sid in [('产业链位置','industry_coordinates'),('靠什么赚钱','technology_products_and_business_model'),('财务兑现','financials_and_valuation'),('为什么能赢','why_it_can_win'),('推翻信号','core_risks')]:
  sec=next(x for x in sections if x['section_id']==sid); nav.append(f"<li>{label}：{'可回答，见 '+sid if sec['status']!='missing' else '尚无证据支撑；缺 '+', '.join(sec['missing_required'])}</li>")
 resolved_periods=[str(x.get('report_period','')) for x in facts if x.get('report_period') not in {'unknown','unresolved'}]
 latest=max(resolved_periods,default='unresolved'); market_quote=next(x for x in m1['rows'] if x['ticker']==ticker)['market']['quote']; market_asof=market_quote.get('observed_at','unknown'); issuer_name=company_adapter(ticker).name; positioning='基于冻结官方披露证据的研究对象；结论仍受未完成证据约束。'
 body=f'''<!doctype html><meta charset="utf-8"><title>{html.escape(issuer_name)} | Evidence-bound Research Report</title><style>body{{font-family:Arial,"PingFang SC";max-width:900px;margin:48px auto;line-height:1.6;color:#162436}}h1{{border-bottom:3px solid #143b66}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ccd6e0;padding:7px;text-align:left}}.note,.judgment{{background:#f2f6fa;padding:14px;margin:12px 0}}.alert{{background:#fff1f0;border:2px solid #9d2d20;color:#7a1f17;padding:12px;font-weight:700}}em{{color:#9d2d20}}</style><h1>{html.escape(issuer_name)}（{ticker}）</h1><p class=note><b>数据时点：最新财报期 {latest}；行情 as_of {market_asof}</b><br>Offline report · Report Model {model} · Facts and unreviewed AI judgment are separate.</p><p class=alert>含 {len(unreviewed)} 项未审阅 AI 判断：它们是待审阅草稿，不构成已完成研究、目标价或仓位建议。</p><h2>一句话定位</h2><p>{positioning}</p><h2>五问导航</h2><ol>{''.join(nav)}</ol><h2>决策边界（实际输入）</h2><pre>{html.escape(json.dumps(d,ensure_ascii=False,indent=2,default=str))}</pre><h2>9章终态</h2><table><tr><th>章节</th><th>状态</th><th>状态原因</th><th>缺失输入</th></tr>{rows}</table><h2>最新期页级事实</h2><ul>{ev}</ul><h2>历史趋势（每项实际期次）</h2>{trends}<h2>旧字段判断材料（未审阅，事实引用内联）</h2>{j}<h2>大白话点评</h2><p>这是一份可翻回官方 PDF 的底稿，不是直接买卖建议；缺口写在章节表里。</p>'''
 body=body.replace('Facts and unreviewed AI judgment are separate.</p>', 'Facts and unreviewed AI judgment are separate.<br><b>校验状态：'+html.escape(audit_summary)+'</b></p>')
 body=body.replace('<h2>决策边界（实际输入）</h2><pre>'+html.escape(json.dumps(d,ensure_ascii=False,indent=2,default=str))+'</pre>', '<h2>执行摘要（实际 required inputs）</h2><h3>市场快照</h3><pre>'+html.escape(json.dumps(market_quote,ensure_ascii=False,indent=2,default=str))+'</pre><h3>决策摘要</h3><pre>'+html.escape(json.dumps(d,ensure_ascii=False,indent=2,default=str))+'</pre>')
 judgment_source_receipt_id=f"{m3['schema_version']}:{m3['receipt_hash']}" if m3.get('ticker')==ticker and m3.get('schema_version') and m3.get('receipt_hash') else None
 a.out.parent.mkdir(parents=True,exist_ok=True);html_bytes=body.encode('utf-8');a.out.write_bytes(html_bytes);r={'schema_version':'round7-transitional-report-v1','body_kind':'transitional_evidence_status_not_round7_chapter_dossier','ticker':ticker,'data_kind':'real','section_contract_schema_version':catl['result']['section_contract']['schema_version'],'report_model_hash':model,'html_path':str(a.out),'html_sha256':hashlib.sha256(html_bytes).hexdigest(),'html_bytes':len(html_bytes),'word_count':len(body.split()),'sections':sections,'tier':catl['result']['degradation']['tier'],'tier_reasons':catl['result']['degradation']['reasons'],'input_hashes':hashes,'judgment_source_receipt_id':judgment_source_receipt_id,'unreviewed_judgment_count':len(unreviewed),'unreviewed_judgment_ids':unreviewed,'citation_gate':{'passed':True,'facts_rendered':len(facts)},'deepseek_narrative':{'used':False,'reason':'offline deterministic compile'}};r['receipt_hash']=h(r);a.receipt.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'html':str(a.out),'receipt':str(a.receipt),'tier':r['tier']}))
if __name__=='__main__':main()
