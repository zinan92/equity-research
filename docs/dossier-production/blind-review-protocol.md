# Dossier pilot blind-review protocol

This protocol tests whether five independently sourced dossiers are preferred to the local benchmark as complete documents. It does not import benchmark prose or preferences into product output.

## Reviewers

- One reviewer must use role `park`.
- At least one independent reader must use role `external_reader`.
- Reviewers receive only the runtime A/B pack. They must not receive the key file before scoring.

## Whole-document preference

For each pair, the reviewer selects `A`, `B`, or `tie`. The decision considers:

1. useful company-specific detail rather than generic coverage;
2. traceable evidence and explicit uncertainty;
3. readable synthesis rather than mechanical tables;
4. falsifiers and issuer-claim discipline.

Park and one `external_reader` must each complete all five pairs. Self-produced dossiers must win at least four of five pairs for each reviewer. Ties do not count as self wins. Missing pairs or reviewer roles fail closed.

## Runtime-only build

```bash
python3 scripts/dossier_blind_review.py build \
  --archive /absolute/local/archive/slow-knowledge/company-dossiers.json \
  --manifest docs/dossier-production/pilot-production-manifest.json \
  --out /tmp/dossier-blind-pack.md \
  --key-out /tmp/dossier-blind-key.json
```

The pack and key must remain outside Git. The benchmark archive is a comparison input only; its prose is not a product source.

## Preference input

```json
{
  "reviewers": [
    {
      "id": "park",
      "role": "park",
      "choices": [
        {
          "pair_id": "P1",
          "preferred": "A"
        }
      ]
    }
  ]
}
```

Every reviewer must provide every pair exactly once. The real input includes `P1` through `P5` and both required roles.

## Scoring receipt

```bash
python3 scripts/dossier_blind_review.py prefer \
  --key /tmp/dossier-blind-key.json \
  --preferences /tmp/dossier-blind-preferences.json \
  --out /tmp/dossier-blind-preference-receipt.json
```

Only a passed receipt plus reviewer identities closes the human evaluation gate. A model-generated or fabricated `park` choice is invalid.
