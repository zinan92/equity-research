# Market Regime Live v1 · deterministic overlay contract

Status: S2 experimental model contract. Schema:
`market-regime-intraday-overlay-v1`. Story: #721.

This layer answers one bounded question: does the currently eligible A-share
tape confirm or diverge from the already-frozen completed-daily structure? It
also lists evidence-linked cross-asset signal contributions and whether the
result changed materially from the previous successfully verified overlay. It
does not forecast, recommend, size a position, explain news causality, replace
a daily structural label, publish data, or execute an action.

## Inputs and immutable boundary

The compiler accepts exactly:

1. one verified `market-regime-analysis-v1` structural analysis;
2. one verified `market-regime-intraday-data-v1` snapshot; and
3. zero or one previously verified overlay.

The structural `analysis_id`, dimensions, scenario and asset features are
read-only inputs. The overlay binds their identity but never mutates or
recalculates them. The intraday snapshot binds each accepted signal to the
exact instrument key, completed-bar end, session, freshness and normalized
artifact SHA-256. A cash index and a futures proxy keep separate evidence
identities even when both contribute to the same explanatory group.

An asset is score-eligible only when its current snapshot entry is accepted,
`session_state=open`, `freshness=live_candidate`, and it contains enough valid
completed 5-minute bars. Closed, delayed, stale, last-good fallback and unknown
records remain visible as exclusions; they cannot silently contribute.

## Experimental impulse and contributions

For each eligible asset, the model takes the newest contiguous block of up to
13 completed bars (12 five-minute returns). It estimates noise from valid
adjacent five-minute returns in the frozen input, floors five-minute noise at
5 basis points, standardizes the trailing move by `sigma * sqrt(intervals)`,
and maps it through `50 * tanh(z / 2)`. The bounded asset impulse is therefore
between -50 and +50.

Cross-asset contributions use fixed group weights. When cash and futures
evidence from the same US group are simultaneously eligible, that group's
weight is divided between them; neither series is spliced or substituted.
Volatility and precious-metal impulses have a negative risk-appetite sign;
their contribution is an observable model input, not a causal claim. Every
contribution reports instrument, role, signed weight, impulse, contribution,
completed-bar time and evidence identity. `top_drivers` means the largest
absolute deterministic contributions, never news causes.

The A-share tape score uses fixed weights: Shanghai Composite 50%, STAR 50 30%,
and SSE Dividend 20%, renormalized only when Shanghai plus at least one of the
two style indices are eligible. The structural A-share score applies the same
weights to the existing daily asset trend scores. Missing Shanghai evidence
degrades the A-share relation to `insufficient`; one missing style index does
not invalidate the other dependencies.

## Four relations and frozen thresholds

The only top-level relation values are `confirms`, `diverges`, `insufficient`,
and `closed`.

- If no A-share index is open and every observed A-share state is a known
  non-open state (`pre`, `lunch_break`, `post`, or `closed`), relation is
  immediately `closed`.
- If session evidence is conflicting/unknown, or required eligible data is
  missing, relation is immediately `insufficient`.
- A directional structural score uses +10 / -10. Against a positive structure,
  A-share impulse at or above +18 confirms and at or below -18 diverges; the
  signs reverse for a negative structure.
- Against a neutral structure, absolute impulse at or below 8 confirms
  neutrality and absolute impulse at or above 18 diverges. Values between
  exit 8 and enter 18 are insufficient to establish a new relation.

Enter threshold is 18 and exit threshold is 8. A new directional relation or
a weak-signal exit needs two consecutive unique, successfully verified
overlays. A directional transition starts a 30-minute cooldown; an opposite
candidate may remain visible during cooldown but cannot replace the stable
relation until cooldown expires. Closed or genuinely missing/unknown evidence
degrades immediately and is never masked by hysteresis.

## Delta and material change

The baseline is the previous successfully verified overlay, not the previous
HTTP attempt, poll, scheduler wakeup or page view. With no baseline, the first
overlay says `baseline_not_available` and does not claim a change.

A later overlay is material when at least one frozen condition holds:

- the stable four-way relation changes;
- the structural `analysis_id` changes;
- the cross-asset score moves by at least 15 points; or
- the A-share score crosses a frozen negative/transition/neutral/positive band.

Small score motion is still shown but is not promoted to material change. The
output always carries exactly two deterministic watch conditions. They express
session/evidence, score, persistence or material-delta thresholds; they never
express a price target, return forecast, trade or position action.

## Append-only verified history

Overlay identity is a canonical SHA-256 over the complete output core,
including structural and intraday identities and the previous overlay
baseline. Replaying the same frozen inputs with the same previous overlay
produces the same overlay identity.

Each successful non-duplicate overlay is stored as an immutable artifact and
an immutable history entry. A history entry binds sequence number, overlay
artifact hash and the prior history-entry hash. The mutable `latest.json` is
only an atomic pointer; verification walks the full chain, verifies every file
hash and overlay identity, and rejects cycles, gaps, path escape or tampering.

If compilation or persistence fails, `latest.json` is not advanced. If the
structural analysis and intraday snapshot fingerprint exactly duplicate the
current verified overlay, the existing overlay is returned and no artifact,
history entry, baseline or persistence counter advances.

## Truth boundary

Every overlay is `experimental`, `model_generated_unreviewed`, read-only,
non-predictive, non-advisory, non-publishable and non-actionable. Current
Yahoo/Tencent inputs remain supplementary local-evaluation evidence. Fixture
replay proves deterministic behavior only; weekend acceptance proves honest
closed-state handling, not market-open reliability or provider latency.
