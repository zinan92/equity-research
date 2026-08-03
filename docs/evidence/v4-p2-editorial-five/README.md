# V4-P2 · five-company editorial evidence

Issue: [#692](https://github.com/zinan92/equity-research/issues/692)

This is a review-only delivery. Each dossier was generated from its own
official CNINFO PDF evidence packet, then checked by
`product/editorial_v4_contract.py` and an independent DeepSeek QA call. The
five final rows are recorded in
[`artifacts/editorial-v4/batch-receipt.json`](../../../artifacts/editorial-v4/batch-receipt.json).

| Ticker | Body chars | Machine | Independent QA | HTML |
| --- | ---: | --- | --- | --- |
| 600519.SH | 2,492 | passed | passed | [`report.html`](../../../artifacts/editorial-v4/600519.SH/report.html) |
| 000333.SZ | 2,513 | passed | passed | [`report.html`](../../../artifacts/editorial-v4/000333.SZ/report.html) |
| 600900.SH | 2,269 | passed | passed | [`report.html`](../../../artifacts/editorial-v4/600900.SH/report.html) |
| 300750.SZ | 2,515 | passed | passed | [`report.html`](../../../artifacts/editorial-v4/300750.SZ/report.html) |
| 000001.SZ | 2,623 | passed | passed | [`report.html`](../../../artifacts/editorial-v4/000001.SZ/report.html) |

The pipeline deliberately keeps sharp positioning such as “绝对龙头”“强定价
权”“精密制造杂货铺” when it is represented as `[J-xx]` judgment with
evidence references and a falsifier. It does not require a page to say the
phrase verbatim. Page-bound facts remain `[F-xx]`, issuer statements remain
`[C-xx]`, and missing material remains `[G-xx]`.

All five artifacts carry `review_only=true`, `pending` human review,
`action_state=blocked`, `no_tier_credit=true`, and `no_publication_credit=true`.
They are not live recommendations or canonical publication files.
