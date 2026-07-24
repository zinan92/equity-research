# N3-S4 · three-company evidence-bound dossier baseline

## Result

The existing E4-S1 vertical-slice path deterministically compiles the same
company-dossier schema for 宁德时代、贵州茅台和招商银行. Each slice starts with a
public issuer/official-disclosure identity, builds an accepted filing Context
Pack, compiles a dossier and offline report model, then runs the decision
policy. The result is deliberately `partial_evidence_bound`: all three decision
receipts return **`no_action`**.

No fixture facts were used, and all three outputs use the same dossier schema.

## Reproducible receipts

| Company | Primary filing citation | Context Pack manifest | Dossier | Report export | Receipt |
| --- | --- | --- | --- | --- | --- |
| 宁德时代 `300750.SZ` | [PDF p.2](https://static.cninfo.com.cn/finalpage/2025-03-15/1222806982.PDF), `b4f1713d…65b0ad` | `ad582952…1b4bed` | `dossier_f42f6a25d94946eb4165b5f33726b29a46ddabda` | `157a7af5…adabd9` | `84d76eda…a05cf4` |
| 贵州茅台 `600519.SH` | [PDF p.5](https://static.cninfo.com.cn/finalpage/2025-04-03/1222993912.PDF), `8ad3773f…68fb7d` | `d4bdd1a7…a87585` | `dossier_a33841fc330f112f80058d7086cf3ce410e017c6` | `4bdc842b…3a1bff` | `c22fff12…6764582` |
| 招商银行 `600036.SH` | [PDF p.11](https://s3gw.cmbimg.com/lb5001-cmbweb-prd-1255000097/cmbir/20250325/e86337ff-2172-46c2-8174-411903fd7020.pdf), `3db21481…4c00c1` | `3a5e2f46…9ce80e` | `dossier_0d9e04ec19b570974d9cbf8ba80d14507903baef` | `b0c79923…33d2d` | `78d8c636…0cd0c2` |

Each abbreviated hash above is emitted in full by the verification command.
Raw PDFs remain outside Git.

## Required gaps and action boundary

Every company carries the same unresolved inputs: `market_price`, `valuation`,
`quality_risk_liquidity`, `sell_side`, and `catalyst_profile`. Consequently the
decision policy records `insufficient_evidence_coverage`,
`missing_market_price`, and `missing_quality_risk_or_liquidity`, then produces
`no_action`.

This baseline proves the pipeline shape — source identity → Context Pack →
industry position → dossier → report contract → decision policy — not a
complete research report. It does not assert target price, position, rating, or
company-specific catalyst.

## Reproduction

```bash
python3 scripts/verify_e4_s1_vertical_slices.py
```

The output must remain `partial_evidence_bound`, `shared_schema: true`, and
`fixture_facts_used: false`; any missing evidence must remain a gap.
