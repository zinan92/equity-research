# Dossier pilot blind-review protocol

This protocol tests whether five independently sourced dossiers reach at least 80% of the local benchmark on detail, evidence density, and anti-hype discipline. It does not import benchmark prose or scores into product output.

## Reviewers

- One reviewer must use role `park`.
- At least one independent reader must use role `external_reader`.
- Reviewers receive only the runtime A/B pack. They must not receive the key file before scoring.

## Scoring

Each A/B document receives three integer scores from 1 to 5:

1. `detail`: useful company-specific depth rather than generic coverage.
2. `evidence_density`: important factual claims are traceable and uncertainties are visible.
3. `anti_hype_discipline`: promotional claims are challenged with falsifiers and missing evidence.

The acceptance ratio is total self-produced score divided by total benchmark score across all pairs and required reviewers. Passing requires a ratio of at least `0.80`. Missing pairs, missing reviewer roles, or out-of-range scores fail closed.

## Runtime-only build

```bash
python3 scripts/dossier_blind_review.py build \
  --archive /absolute/local/archive/slow-knowledge/company-dossiers.json \
  --manifest docs/dossier-production/pilot-production-manifest.json \
  --out /tmp/dossier-blind-pack.md \
  --key-out /tmp/dossier-blind-key.json
```

The pack and key must remain outside Git. The benchmark archive is a comparison input only; its prose is not a product source.

## Score input

```json
{
  "reviewers": [
    {
      "id": "park",
      "role": "park",
      "scores": [
        {
          "pair_id": "P1",
          "A": {"detail": 1, "evidence_density": 1, "anti_hype_discipline": 1},
          "B": {"detail": 1, "evidence_density": 1, "anti_hype_discipline": 1}
        }
      ]
    }
  ]
}
```

Every reviewer must provide every pair exactly once. The real input includes `P1` through `P5` and both required roles.

## Scoring receipt

```bash
python3 scripts/dossier_blind_review.py score \
  --key /tmp/dossier-blind-key.json \
  --scores /tmp/dossier-blind-scores.json \
  --out /tmp/dossier-blind-score-receipt.json
```

Only a passed receipt plus reviewer identities closes the human evaluation gate. A model-generated or fabricated `park` score is invalid.
