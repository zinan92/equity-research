# L1-M1 · CATL 官方年报叙述页级抽取

- Real-run receipt: `e4-official-narrative-evidence-v1:ad4aecf4459d0e2f7b5aebe19f4d8f28a2d7f4d63995de1934daf4be47c9501e`.
- Scope: all eight declared CNINFO PDFs in `CATL_REPORTS`; all eight were available from their declared official URLs.
- Output: 907 resolved page-level narrative blocks across 96 pages and 1,888 explicit unresolved blocks. The unresolved rows retain a raw excerpt and `no_target_section_context`; none are silently assigned.
- Coverage is recorded per document and full heading path in the runtime receipt at `artifacts/evidence/300750.SZ-official-narrative-evidence.json`. It is deliberately runtime-only because it contains extracted official-PDF text and hashes; regenerate with `PYTHONPATH=product python3 scripts/run_e4_l1_m1_narrative_extraction.py`.
- Verification: `PYTHONPATH=product python3 scripts/verify_e4_l1_m1_narrative_evidence.py artifacts/evidence/300750.SZ-official-narrative-evidence.json --out artifacts/evidence/300750.SZ-official-narrative-verification.json` validates source identity, receipt hash, all eight document IDs, explicit unresolved semantics, and ten PDF/page/heading/text spot checks.

## Ten reproducible page checks

The verifier emits the verbatim text and direct official PDF URL for the ten deterministic checks. One representative path is document `1213027750`, page 11, `第三节 管理层讨论与分析 > 一、报告期内公司所处行业情况 > （二）行业发展状况及发展趋势 > 2、储能行业`, from <https://static.cninfo.com.cn/finalpage/2022-04-22/1213027750.PDF>.
