# L1-M6 human review operations

This pack prepares review work only.  It grants no approval, Tier, target,
position, action, or issue #218 acceptance credit.

## Inputs and current boundary

- Judgment queue: `artifacts/e4-reports/300750.SZ.judgment-review-queue.json`.
  It contains 9 `pending_human_review` CATL judgment drafts from receipt
  `e4-m3-catl-judgments-v2:ba5e1b96eae378a3a116c88e39024ffbebcafab8bba54cd098d7b2a0f7b7281e`.
- Every citation has a `pdf_page_url`: open it, then verify its `document_id`,
  `raw_hash`, page number, and quoted anchor against the official CNINFO PDF.
- The previous 20-item spot-audit list is not silently retained: only 8 legacy
  assignments still match the latest financial-sequence document identity; 12
  are stale and require page-fact recovery.  The current conservative receipt
  has 7 pending assignments and 13 explicit coverage gaps.  It is an
  assignment list, not a completed audit.

## Reviewer procedure

For each judgment item, an independent human reviewer must:

1. Open every `pdf_page_url` and check the official PDF’s document identity,
   page, anchor, and surrounding paragraph/table context.
2. Check that each factual sentence in `body` is supported by the cited text;
   distinguish source fact, issuer self-description, and the AI conclusion.
3. Check that the conclusion does not overstate an issuer disclosure, and that
   caveats such as missing peer validation remain visible.
4. For a falsification/action item, verify direction, threshold, unit and
   time window against the cited page fact.
5. Record one of `approved`, `rejected`, or `needs_revision`, plus reviewer
   identity, UTC timestamp, item identifier, every checked citation, and a
   concise rationale.  An approval writeback may use only
   `human_reviewed_judgment` with `review_status=approved`; a rejection or
   revision keeps the input pending/partial.

The review record must be append-only and identity-bound.  The person running
this preparation must not write the human decision or approve their own draft.

## Sections that only lack human review

Provided all drafts in the listed section are approved and no receipt changes,
only these sections have no other missing required input:

| Section | Required pending approvals | Current state | State after all listed approvals |
| --- | --- | --- | --- |
| `risks_and_falsification` | `risk_register`, `falsification_tests` | PARTIAL (`pending_judgment_review`) | FULL |
| `monitoring_and_action_triggers` | `monitoring_kpis`, `action_triggers` | PARTIAL (`pending_judgment_review`) | FULL |

Approving one sibling alone does not complete either section.  Every other
queued section still has independently missing C1 inputs; its queue row names
those remaining inputs.  No reviewer action changes the C1 contract, Tier
strategy, B6 policy, or decision policy.
