# K-line World Report S3 · Design QA

## Comparison target

- Source visual truth: `/Users/wendy/.codex/visualizations/2026/08/13/019fb234-c4e3-7670-a0d8-564c9f8fb9f2/macro-vertical-prototype/implementation-light-defense-top-753x890.png`
- Source mobile truth: `/Users/wendy/.codex/visualizations/2026/08/13/019fb234-c4e3-7670-a0d8-564c9f8fb9f2/macro-vertical-prototype/implementation-light-mobile-390x844.png`
- Implementation: local Browser-rendered `defense.html` and `wait.html` from the versioned `market-regime-kline-world-report-v1` renderer.
- State: light theme; defense for desktop and wait for mobile. QA pages are visibly marked `VISUAL QA FIXTURE` and are not presented as current market data.

## Normalization

- Desktop source pixels: 753 × 890. Implementation pixels: 753 × 890. Browser CSS viewport: 768 × 908; the in-app browser removes a 15 px vertical scrollbar and 18 px browser surface from the captured content. Device pixel ratio: 1.
- Mobile source pixels: 375 × 812 (the source filename says 390 × 844, but the file itself measures 375 × 812). Implementation pixels: 375 × 812. Browser CSS viewport: 390 × 844, device pixel ratio: 1.
- Both comparisons use identical state, crop, pixel size and density after normalization.

## Full-view comparison evidence

- Desktop final: `evidence/market-regime-kline-world-report-s3/source-vs-implementation-defense-final.png`
- Mobile final: `evidence/market-regime-kline-world-report-s3/source-vs-implementation-wait-mobile-final.png`
- Three posture tokens: `evidence/market-regime-kline-world-report-s3/three-postures.png`

The implementation retains the source grammar: warm white paper, thin neutral
dividers, one oversized Song-style posture word, one secondary synthesis, a
square confidence block, restrained small metadata, and a vertical narrative
sequence. The discovery scenario tabs are intentionally absent because they
were fixtures; the first real section is the capital-migration map required by
the approved product contract.

## Focused region evidence

- Actionable trade plan and cross-section: `evidence/market-regime-kline-world-report-s3/trade-plan.png`
- Twelve relative-leadership sparklines and contradiction: `evidence/market-regime-kline-world-report-s3/relative-leadership.png`
- Completed-daily chart wall: `evidence/market-regime-kline-world-report-s3/charts.png`
- Mobile defense layout: `evidence/market-regime-kline-world-report-s3/defense-mobile.png`

Focused checks were necessary because recommendation hierarchy, dense numbers,
relative sparklines and canvas legibility are too small to judge from the
above-the-fold comparison alone.

## Required fidelity surfaces

- Fonts and typography: the implementation uses the same sans-serif UI / Song-style display split. Posture, headline and chain text retain the source's editorial hierarchy; small evidence text remains legible. Long instrument names truncate only in compact tables and remain complete in evidence controls.
- Spacing and layout rhythm: hero, confidence block and numbered sections follow the source's flat vertical rhythm. There is no generic rounded-card wall. Desktop and mobile show no horizontal overflow.
- Colors and tokens: warm-white paper and neutral dividers match the source. Attack, wait and defense use distinct green, amber and red tokens; state color is applied consistently to the posture, destination emphasis and section accents. No decorative gradients remain.
- Image quality and assets: the source has no logos, illustrations, photography or non-standard icon assets. The implementation introduces none. OHLC candles, rate lines and relative sparklines are functional data visualizations rendered from the report payload, not decorative substitutes.
- Copy and content: the page stands alone as `K 线世界日报`. Observed, inferred and recommended content are explicitly separated. The footer permits model-generated market advice, states local-only/unreviewed, and states no automatic execution; it does not say that investment advice is forbidden.
- Interaction and accessibility: citation chips are semantic buttons with keyboard focus and open a native evidence dialog; the close button works. All 17 main canvases and 12 relationship canvases render. Browser console warning/error count is zero. Visible text contrast and focus borders remain distinguishable in all three posture states.

## Findings and comparison history

### Iteration 1

- [P2] Mobile mast and posture scale drifted from the source.
  - Evidence: the initial same-size mobile comparison showed the English product subtitle wrapping to two extra lines while the posture word was optically smaller than the source.
  - Impact: the extra mast density weakened the first conclusion and delayed the eye from reaching the posture.
  - Fix: hide the secondary English mast label below 720 px, tighten badge typography, keep the Chinese product name on one line, and increase the mobile posture to 90 px.
  - Earlier evidence: `evidence/market-regime-kline-world-report-s3/source-vs-implementation-wait-mobile.png`.

### Iteration 2

- Post-fix evidence: `evidence/market-regime-kline-world-report-s3/source-vs-implementation-wait-mobile-revised.png` and the final normalized comparison.
- No actionable P0, P1 or P2 findings remain.

## Intentional deviations

- Source discovery tabs and historical case controls are omitted; shipping them would imply fixture cases are live history.
- The source's one confidence card becomes two code-owned measures: evidence quality and directional clarity. This resolves the earlier ambiguity between data completeness and model conviction.
- Dynamic fixture text differs from the historical source example. Layout, state and hierarchy—not the old market claim—are the fidelity target.

## Primary checks

- Browser-rendered desktop, mobile, attack, wait and defense states.
- Citation dialog open and close.
- 17 daily charts and 12 relative charts present and painted.
- Desktop and mobile `scrollWidth <= innerWidth` after accounting for the in-app browser scrollbar.
- Zero browser console warnings/errors.
- Model-unavailable state preserves all evidence and renders no stale flows or recommendations.

## Follow-up polish

- [P3] A production font package could reduce platform-specific Song-style glyph differences, but the current macOS fallback is visually aligned with the approved local target.

final result: passed
