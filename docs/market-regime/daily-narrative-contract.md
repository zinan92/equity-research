# Market Regime Daily · constrained narrative contract

Status: S4 implementation contract, Issue #745. This story adds a local
narrative compiler; it does not change the daily route, the live API, the
intraday scheduler or publication rights.

## Boundary

The compiler receives one verified `market-regime-daily-evidence-v1` pack. It
does not fetch the web, read the prior 财经日报, or treat generated prose as
evidence. Each statement in the output cites one or more evidence IDs from the
pack. The model returns predicates only: posture/theme, driver/response/status
chain, contradiction relationships and falsifier field/change pairs. It has no
free-text claim, condition, confidence or boundary field. A deterministic
renderer creates the Chinese explanation from those predicates, so action,
publication, confidence and causal semantics cannot be smuggled through prose.

`进攻 / 等待 / 防守 / 未知` is a market-posture description, never a user
instruction. Causal status is constrained to
`supported_observation`, `plausible_interpretation` and `unavailable`; the
renderer owns the language associated with each status.

## Output

The versioned JSON output contains one posture/theme, a three-to-five step
structured transmission chain, one-to-four structured contradictions, exactly
two structured observable falsifiers, and deterministic rendered fields. Every
citation must resolve through the evidence-pack resolver. A
`supported_observation` must match the Evidence Pack's code-owned direction
labels and cite both driver and response sides; ambiguous combinations must be
marked plausible or unavailable. Unknown IDs, extra fields, invalid enum
relationships or attempted prose injection fail closed.

The model is labelled `model_generated_unreviewed`. It selects bounded
predicates but cannot calculate, increase, relabel or hide confidence. No LLM
output is publication- or action-eligible.

## Failure behavior

Missing key, timeout, provider error, invalid JSON/schema, citation failure or
unsafe text produces a same-pack deterministic fallback with posture `unknown`.
The fallback explicitly says that the model explanation is unavailable, cites
the same frozen evidence, contains exactly two falsifiers, and never reuses
older prose. Failure reasons are a fixed allowlist; provider exception text is
not persisted.

## Identity and receipts

The artifact identity binds schema/compiler/prompt versions, pack ID, generation
status, validated output hash and the exact read-only truth boundary. The
immutable run receipt binds request hash, prompt hash, provider metadata,
output hash, validation result, generation status and canonical artifact path.
`state.json` is the canonical single atomic state object containing the latest
pointer and its receipt floor; `latest.json` is only a compatibility mirror.
Readback recomputes the identity, request, output and truth boundary, checks
current pack equality, validates citations again and rejects incoherent
artifact/receipt/state/path or truth-boundary mismatches. Content hashes provide
integrity and identity binding; they are not an external authenticity or
anti-rollback signature, so a party able to rewrite every bound file remains
outside this local threat model.

Runtime output remains under gitignored local storage. The CLI's `--status`
mode reports unavailable when no narrative has been published and reports a
corrupt existing state with a non-zero exit code.
