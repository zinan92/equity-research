# N3-S3 · AI-compute catalyst baseline

## Result

The E3-S4 catalyst-profile path was replayed from current first-party captures
on 2026-07-24. It produced all 108 canonical segment profiles: 24 profiles
have one accepted **current-state** fact section and 84 profiles remain wholly
`missing_evidence`. There are exactly 24 fact sections in total.

## Source identities

| First-party source | SHA-256 of captured response |
| --- | --- |
| [ASML strategy material](https://www.asml.com/en/investors/annual-report/2025/strategy-and-stories) | `fbfaec7aabba08d1721ed309fcd2b257f77a81e13a30da444955ec3f4865528c` |
| [NVIDIA networking](https://www.nvidia.com/en-eu/networking/) | `d9aeb6fc8f3a9b2969f8ab6d173b78d26a80ea6d946f899ac55c7845f5ef377d` |
| [NVIDIA data center](https://www.nvidia.com/en-us/data-center/) | `0a5908653f603eecdece758b023940dd38b4849b58e2e58c82ef23083e67859a` |

The replay uses the existing E3-S4 seven-section order:
`current_state`, `driver`, `catalyst`, `leading_indicator`,
`risk_falsifier`, and `time_horizon`. A first-party relationship capture may
support only `current_state`; all other sections remain missing unless their
own accepted evidence exists.

## Coverage receipt

```json
{
  "total": 108,
  "available": 24,
  "missing_evidence": 84,
  "fact_sections": 24
}
```

The profile contract rejects future-visible evidence and evidence older than
seven days at the requested as-of date. Failed source capture results in an
explicit partial result, not a stale replay or fabricated catalyst.

## Truth boundary

This baseline does not assert a price catalyst, a company forecast, a buy/sell
recommendation, a target price, or a position. “Available” means only that a
segment has one cited current-state fact. It does **not** mean that its driver,
trigger, leading indicator, falsifier, or time horizon has been established.

## Reproduction

```bash
python3 scripts/verify_e3_s4_catalysts.py
```
