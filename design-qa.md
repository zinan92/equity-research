# Weekly Macro K-line mockups · Design QA

## Source visual truth

- Web overview: `/Users/wendy/.codex/generated_images/019fb234-c4e3-7670-a0d8-564c9f8fb9f2/exec-0b0e7389-f186-4304-8b19-35b3be4e4ed6.png` (1440×1024)
- Web asset workbench: `/Users/wendy/.codex/generated_images/019fb234-c4e3-7670-a0d8-564c9f8fb9f2/exec-04534196-178f-4443-ac6b-d676cf6f87a8.png` (1440×1024)
- Mini-program article: `/Users/wendy/.codex/generated_images/019fb234-c4e3-7670-a0d8-564c9f8fb9f2/exec-b3fca25d-e138-46fc-8ae1-fb0b32ee4eb1.png` (390×844)

## Implementation evidence

- Overview: `/tmp/mockup-overview.png` (1440×1024 CSS px, device scale 1)
- Asset workbench: `/tmp/mockup-asset.png` (1440×1024 CSS px, device scale 1)
- Mini article: `/tmp/mockup-mini.png` (390×844 CSS px, device scale 1)
- Local preview: `http://127.0.0.1:8906/`
- Data identity: `market-regime-weekly-report:f4221605f3ad02e7ef5f314b08eab8b4885c5f5d33dd94a1189caaf859eea6fd`

## State and interactions

- Real Weekly report data and immutable chart snapshots are used; production `latest.html` is not replaced.
- Overview anchor navigation was tested from the asset index to `#group-3`.
- All mockup image assets loaded successfully; no page errors or console errors were observed.
- Desktop overflow: `body.scrollWidth = 1440`, viewport `1440`.
- Mobile overflow: `body.scrollWidth = 390`, viewport `390`.

## Comparison history

### Pass 0

- Finding: mockup HTML referenced sibling snapshots that were not bundled into the mockup folder, producing 404s.
- Fix: the builder now copies all 39 referenced snapshot assets into `mockups-v1/snapshots/`.

### Pass 1

- Finding: overview rows allowed long position/structure prose to collide with the summary column.
- Fix: overview uses compact deterministic state labels and ellipsis for the summary column.

### Final pass

- Fonts/typography: one system sans stack, readable Chinese hierarchy, no clipped headings.
- Spacing/layout: overview, asset workbench and mobile article follow separate channel layouts; no horizontal overflow.
- Colors/tokens: shared navy/green/amber/red semantic palette on white surfaces.
- Image quality: real snapshot assets load at the intended target sizes; image scaling is contained by each renderer.
- Copy/content: no raw snapshot hashes or technical source IDs are shown in the mini-program article; web mockups keep compact source/status context.

No actionable P0/P1/P2 findings remain. The Standard K-line toolbar remains visible inside the real chart snapshots as an intentional provenance/renderer cue; removing it is a later production-renderer decision, not a mockup blocker.

final result: passed
