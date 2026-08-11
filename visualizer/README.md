# Partizan visualizer

This site compares three order-7 Digraph Placement positions with exact value
0. Their graph quotients are pairwise distinct. Form A has a different complete
game from forms B and C; B and C share a complete game.

The interface compares one pair at a time through three stages: side-by-side
structures, an isolated difference map, and the resulting identity stack. The
identity stack reports graph-quotient identity, complete-game identity, and
exact value. Machine-readable hashes and JSON exports remain in a secondary
technical drawer. Aesthetic ranking remains outside this instrument.

The displayed values come from checked evidence in `public/evidence/`:

- `fixed-value-atlas.json.gz` is the complete browser atlas, stored with
  deterministic gzip encoding. `fixed-value-atlas.manifest.json` binds its
  compressed and decoded bytes to the public Pages artifact.
- `fixed-value-fiber-193.json` is the compact first-load class: 193 actual
  quotient-distinct digraphs with exact value `1/2` and one shared literal-game
  digest. `fixed-value-fiber-193.manifest.json` binds its selection and bytes.
- `fixed-value-motif.json` records the three forms and their exact relation.
- `repertoire-browser.json` binds the motif to the completed held-out study.
- `elkies-study.json` records the historical chess source cited on the page.

The application uses vinext and is packaged for OpenAI Sites.

The same application can be built for the repository Pages path by setting
`PARTIZAN_ASSET_BASE` and `NEXT_PUBLIC_PARTIZAN_BASE_PATH` to
`/partizan-reproducibility/`.

```bash
npm ci
npm test
npm run lint
```
