# R7-M2 correction evidence: exact accepted nine-section dossier

Issue: [#648](https://github.com/zinan92/equity-research/issues/648)

## Outcome

The canonical report contract now uses the exact reader structure accepted in
`docs/dossier-production/samples/300750.SZ-v1.md`:

1. 一句话定位
2. 身份、创始人与治理
3. 技术来源与发展史
4. 商业模式与业务线
5. 财务与经营时间序列
6. 护城河的证据链
7. 风险、反题材与观察触发器
8. 研究结论与待补问题
9. 生产记录
10. `Sources` as a non-Tier appendix

The accepted CATL file is 4,249 characters. Its nine section bodies total
3,443 characters excluding headings. The machine contract therefore sets a
3,080–4,620 character aggregate target while preserving the accepted
section-specific proportions.

## What was corrected

The previously merged M2 interpretation had redesigned the taxonomy into
sections such as `industry_coordinates`, `founder_and_team`,
`financials_and_valuation`, and `plain_language_verdict`. Those were not the
accepted Round 7 chapter names and could not be used as the canonical
contract. They are now rejected by the contract verifier.

`production_record` is chapter 9 and is completed from the run receipt and
source manifest. It is not an appendix and it does not require an AI-generated
chapter draft. `Sources` is the only publication appendix and does not count
toward Tier.

## Direct consumers updated

- Contract definition and compiler: `product/report_contract.py`
- Tier input adapter: `product/data_core/e4_vertical_degradation.py`
- Judgment material adapter: `product/data_core/e4_judgment_wiring.py`
- Industry material adapter: `product/data_core/e4_r2_industry_wiring.py`
- North-star verifier: `product/data_core/round7_north_star.py`
- E4 wiring, inventory, migration and report compilation scripts
- Contract, Tier, judgment, industry, migration, inventory and north-star tests
- Contract documentation, decision log and registry

The retired redesigned identifiers remain in code only in negative
verifier/tests that prove they cannot silently become canonical again. Stale
tracked HTML, receipts, wiring and review queues built under either the
18-section contract or the redesigned nine-section taxonomy were removed.
They will be regenerated only by the exact chapter pipeline in R7-M3/R7-M5.

## Reuse and non-reuse decision

Reused:

- B6 evidence gate
- `research_degradation.assess_any_ticker` Tier staircase
- `_TIER_ALLOWED` and `_BLOCKED_FIELDS`
- decision policy
- unreviewed-judgment downgrade to `PARTIAL`
- existing evidence and wiring adapters

New:

- the exact nine-section identity and target ranges
- canonical CATL structure/hash verification
- a regression check preventing a chapter heading from satisfying a required
  falsifier or typed evidence gap
- a strict report verifier check for exact section ID and order, rather than
  accepting any list of nine sections
- retirement of the legacy L1 reassessment bridge, which could not preserve a
  coherent evidence-gate identity and degradation result while replacing the
  contract

Why the prior merged output could not be used: it represented a newly designed
taxonomy rather than the user-approved Round 7 structure. Keeping it would
continue optimizing a different product.

## Verification

Commands:

```text
python3 scripts/verify_round7_north_star.py --out artifacts/evidence/round7-north-star-baseline.json
python3 scripts/verify_round7_section_contract.py --out artifacts/evidence/round7-m2-section-contract-verification.json
python3 -m unittest discover -s product/tests -q
```

Results:

- North-star verifier: `passed`; 9 reader units; canonical CATL SHA-256
  `5c1c8d9eb2f138925c8218ac9e0cd8ce2869bbb811a812e39bbfd339ef709d0e`
- Section-contract verifier: `passed`; reviewed all-FULL fixture remains Tier A;
  one unreviewed chapter remains `PARTIAL`, Tier B, with
  `action`, `target_price`, and `position_range` blocked
- Product tests: 648 passed, 1 skipped

## Safety source proof

These protected implementations were not edited and retain their frozen
hashes:

| Source | SHA-256 |
| --- | --- |
| `product/data_core/research_degradation.py` | `98fc7820019a9f10b91d4533c17de38f4db9b178e3d33c1e5ed57ce98890fed1` |
| `product/data_core/evidence_gate.py` | `bddf93d9268633532efce4ba3ae9b5069217f08ba5d8353e846bf452ef28e805` |
| `product/data_core/decision_policy.py` | `34ace569be831712af1bd1c3cf7bdd42ba2c63a6e3b19935c29058a02e28f4b9` |

The verified safety behavior is unchanged: only all nine `FULL` sections can
produce Tier A, and unreviewed chapter content naturally holds its section at
`PARTIAL` and the report at Tier B.
