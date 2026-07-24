# N3-S2 · AI-compute relationship baseline

## Result

The existing E3-S1/E3-S2 path was replayed from its three public first-party
sources at `2026-07-24T15:04:00.777739Z`. It produced an evidence-bound
AI-compute graph with 12 major nodes, 108 canonical segments, and 30 accepted
segment relationships. All 30 relationships retain a raw-evidence identity.

## Source captures

| First-party source | SHA-256 of captured response |
| --- | --- |
| [ASML annual-report strategy material](https://www.asml.com/en/investors/annual-report/2025/strategy-and-stories) | `fbfaec7aabba08d1721ed309fcd2b257f77a81e13a30da444955ec3f4865528c` |
| [NVIDIA networking documentation](https://www.nvidia.com/en-eu/networking/) | `d9aeb6fc8f3a9b2969f8ab6d173b78d26a80ea6d946f899ac55c7845f5ef377d` |
| [NVIDIA data-center documentation](https://www.nvidia.com/en-us/data-center/) | `0a5908653f603eecdece758b023940dd38b4849b58e2e58c82ef23083e67859a` |

The captured bodies remain runtime-only. This committed note contains source
identity and aggregate evidence only.

## Graph receipt

```json
{
  "accepted": 30,
  "disputed": 0,
  "edge_count": 30,
  "needs_evidence": 0,
  "segment_count": 108,
  "unknown": 0
}
```

The ontology validation enforces 10–15 major nodes and at least 104 segments;
this replay has 12 nodes and 108 segments. Each accepted edge is linked to one
of the captured raw hashes above by the existing E3-S2 graph contract.

## Truth boundary

This is a **segment-relationship** baseline. It does not establish that a
particular company supplies, leads, benefits from, or is competitively superior
to another company. Company-level facts come only through the N3-S1/E3-S3
page-cited position path, while unaccepted company mappings stay in the review
queue. The graph is not a valuation, recommendation, target price, or position
policy input by itself.

## Reproduction

```bash
python3 scripts/verify_e3_s2_industry_graph.py
```

Any failed source capture must be recorded as a fresh gap; it must not be
silently replaced with an old raw hash or fixture.
