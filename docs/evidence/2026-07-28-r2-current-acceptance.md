# R2 · Current AI-compute world-model acceptance

## Result

**Passed** on 2026-07-28. This supersedes neither the historical partial audit
nor any R3--R5 gate: it records that the approved R2 evidence contract is now
satisfied by the exact runtime receipts below.

## Reproduction inputs

Runtime receipts remain outside Git by design. Their paths and independently
computed SHA-256 identities are recorded so the audit can be rerun without
turning them into product fixtures:

| Input | Path | SHA-256 |
| --- | --- | --- |
| N3 dossier batch | `/Users/wendy/Documents/equity-research-n3-s5a-runtime/n3-dossier-batch-10dd875e32907e14.json` | `c215ace7d2a96426b35ba041d0cbb16326c9a5cb27dc518c538a1c68af1b74c7` |
| PIT financial delivery | `/Users/wendy/Documents/equity-research-n3-s7d-runtime/n3-financial-delivery-e3cd6e06ae0993b7.json` | `1019a4e1162f1479ead12dd36f133ac43450edc351eafe317a282d588f88ec41` |
| Falsifier evidence | `/Users/wendy/Documents/equity-research-n3-s8d-runtime/n3-falsifier-evidence-0ef0c3c1052ccc7e.json` | `c5c075d6202bd489ecf82a48d272b9fba4e9b1eced22d201b65f3a801a514599` |
| Moat evidence | `/Users/wendy/Documents/equity-research-n3-s9b-runtime/n3-moat-evidence-3e3be84f79f76c9d.json` | `6eef6ee0511273ed05dbe49c932e03322ea538404755162ed3ca0421bcd75d07` |
| Market-future evidence | `/Users/wendy/Documents/equity-research-n3-s10b-runtime/n3-market-future-evidence-1dd226f975205c35.json` | `235d7e2acf2d2dd47939f255cc6ce4fba3055a1cb4440b3483bfa449cdfdcc76` |

```bash
python3 scripts/verify_r2_ai_compute_world_model.py \
  /Users/wendy/Documents/equity-research-n3-s5a-runtime/n3-dossier-batch-10dd875e32907e14.json \
  --financial-delivery-receipt /Users/wendy/Documents/equity-research-n3-s7d-runtime/n3-financial-delivery-e3cd6e06ae0993b7.json \
  --falsifier-evidence-receipt /Users/wendy/Documents/equity-research-n3-s8d-runtime/n3-falsifier-evidence-0ef0c3c1052ccc7e.json \
  --moat-evidence-receipt /Users/wendy/Documents/equity-research-n3-s9b-runtime/n3-moat-evidence-3e3be84f79f76c9d.json \
  --market-future-evidence-receipt /Users/wendy/Documents/equity-research-n3-s10b-runtime/n3-market-future-evidence-1dd226f975205c35.json
```

## Observed gate result

| Gate | Result |
| --- | --- |
| Ontology | Pass: 12 nodes, 108 segments |
| Company positions | Pass: 50 reviewed, 30 accepted/page-cited |
| Relationship graph | Pass: 30 accepted first-party evidence-bound edges |
| Dossiers | Pass: 20 requested, 20 compiled, 0 failed, 20 `no_action` |
| Five company questions | Pass: layer, moat, financial delivery, market future and falsifier are each 20/20 |
| Archive isolation | Pass: 11 production modules inspected, 0 archive dependencies |

## Boundary and next gate

This is a world-model evidence gate, not an investment-decision release. The
20 dossiers remain `no_action`; R2 supplies no target price, position, action
or product-ready 100-ticker coverage. R3 remains blocked on #218's fixed
100/95/80/20 acceptance contract, including independent numeric/page audits.
