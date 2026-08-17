# Sector Rotation V1 Prototype

This artifact is the read-only prototype for GitHub issue #816.

Open `product/static/sector-rotation.html` through the existing local product
server, or open that file directly for a static review. The page validates the
reader sequence:

1. 20 peer-sector universe
2. leading / improving / watch rotation view
3. sector card comparison
4. single-sector K-line and fund-flow evidence drawer
5. visible data-quality and fail-closed boundary

All values in the page are fixtures. They are intentionally marked `FIXTURE`,
`NOT LIVE`, or `unknown`; they do not describe the current market and must not
be reused as market evidence. No provider request, broker path, order path, or
runtime scheduler is included.

The data contract and unresolved provider identities are documented in:

- `docs/research/sector-rotation/issue-811-data-contract.md`
- `docs/research/sector-rotation/issue-812-sector-universe.md`

## Local evidence command

```bash
python3 -m unittest product.tests.test_sector_rotation_prototype -v
node --check product/static/sector-rotation.js
```
