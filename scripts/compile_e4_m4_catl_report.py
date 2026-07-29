#!/usr/bin/env python3
"""Offline CATL report compiler over frozen receipts."""
from __future__ import annotations
import argparse, hashlib, html, json
from pathlib import Path
def h(x): return hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('m1',type=Path);p.add_argument('m2',type=Path);p.add_argument('m3',type=Path);p.add_argument('--out',type=Path,required=True);p.add_argument('--receipt',type=Path,required=True);a=p.parse_args()
 m1=json.loads(a.m1.read_text());m2=json.loads(a.m2.read_text());m3=json.loads(a.m3.read_text());catl=next(x for x in m2['rows'] if x['ticker']=='300750.SZ');d=next(x for x in m1['rows'] if x['ticker']=='300750.SZ')['decision'];sections=catl['result']['section_contract']['sections'];facts=catl['result']['page_facts']
 need=('document_id','raw_hash','page_number','quoted_anchor','source_url')
 if not all(all(x.get(k) for k in need) for x in facts): raise ValueError('citation gate rejected uncited fact')
 hashes={'m1':h(m1),'m2':h(m2),'m3':h(m3)};model=h({'ticker':'300750.SZ','inputs':hashes,'sections':sections,'decision':d})
 rows=''.join(f"<tr><td>{html.escape(x['section_id'])}</td><td>{html.escape(x['status'])}</td><td>{html.escape(', '.join(x['missing_required']) or '—')}</td></tr>" for x in sections)
 ev=''.join(f"<li>{html.escape(x['metric'])}: {html.escape(str(x['value']))} {html.escape(x['unit'])} — <a href='{html.escape(x['source_url'])}'>PDF p.{x['page_number']}</a>; {html.escape(x['quoted_anchor'])}</li>" for x in facts[:12])
 j=''.join(f"<li><b>{html.escape(k)}</b>: {html.escape(v['status'])}</li>" for k,v in m3['content'].items())
 body=f'''<!doctype html><meta charset="utf-8"><title>宁德时代 | Evidence-bound Research Report</title><style>body{{font-family:Arial,"PingFang SC";max-width:900px;margin:48px auto;line-height:1.6;color:#162436}}h1{{border-bottom:3px solid #143b66}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ccd6e0;padding:7px;text-align:left}}.note{{background:#f2f6fa;padding:14px}}</style><h1>宁德时代（300750.SZ）</h1><p class=note>Offline report · Report Model {model} · Facts and unreviewed AI judgment are separate. No network request occurred during compilation.</p><h2>一句话定位</h2><p>基于冻结官方披露证据的电池产业链研究对象；结论仍受未完成证据约束。</p><h2>五问导航</h2><ol><li>产业链位置：业务模式与行业结构。</li><li>壁垒：竞争格局与护城河。</li><li>财务兑现：收入质量、盈利、现金流。</li><li>交易的未来：估值。</li><li>推翻信号：风险、反证与跟踪。</li></ol><h2>决策边界</h2><pre>{html.escape(json.dumps(d,ensure_ascii=False,indent=2,default=str))}</pre><h2>18章终态</h2><table><tr><th>章节</th><th>状态</th><th>缺失输入</th></tr>{rows}</table><h2>页级事实</h2><ul>{ev}</ul><h2>判断内容（未审阅）</h2><ul>{j}</ul><h2>大白话点评</h2><p>这是一份可翻回官方 PDF 的底稿，不是直接买卖建议；缺口写在章节表里。</p>'''
 a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(body,encoding='utf-8');r={'schema_version':'e4-m4-catl-report-v1','ticker':'300750.SZ','data_kind':'real','report_model_hash':model,'html_path':str(a.out),'word_count':len(body.split()),'sections':sections,'tier':catl['result']['degradation']['tier'],'tier_reasons':catl['result']['degradation']['reasons'],'input_hashes':hashes,'citation_gate':{'passed':True,'facts_rendered':len(facts)},'deepseek_narrative':{'used':False,'reason':'offline deterministic compile'}};r['receipt_hash']=h(r);a.receipt.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'html':str(a.out),'receipt':str(a.receipt),'tier':r['tier']}))
if __name__=='__main__':main()
