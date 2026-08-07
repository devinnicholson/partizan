# Partizan visualizer

This site compares three order-7 Digraph Placement positions with exact value
0. Their graph quotients are pairwise distinct. Form A has a different complete
game from forms B and C; B and C share a complete game.

The interface compares one pair at a time. Its graph overlay separates shared
arcs from arcs found only in either form, while the result panel reports exact
value, graph-quotient identity, and complete-game identity. Readers move between
the two forms and reveal their exact relation. Machine-readable hashes and JSON
exports remain in a secondary technical drawer. The page does not create an
aesthetic score.

The displayed values come from checked evidence in `public/evidence/`:

- `fixed-value-motif.json` records the three forms and their exact relation.
- `repertoire-browser.json` binds the motif to the completed held-out study.
- `elkies-study.json` records the historical chess source cited on the page.

The application uses vinext and is packaged for OpenAI Sites.

```bash
npm ci
npm test
npm run lint
```
