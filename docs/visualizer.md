# Partizan visualizer

The visualizer presents one fixed-value motif from the order-7 Digraph
Placement study. It is a small interface for comparing three certified forms.

## The three forms

All three positions have exact value 0 under Conway comparison:

```text
v(A) = v(B) = v(C) = 0
```

Their other identities differ. Form A has 19 nodes and 18 edges in its complete
game. Removing `2→3` produces form B with 15 nodes and 14 edges. Adding `6→0`
produces form C. B and C have different graph quotients and the same complete
game digest.

```text
ℓ(A) ≠ ℓ(B) = ℓ(C)
q(A), q(B), q(C) are pairwise distinct
```

The page exposes these values through three pairwise comparisons. Each crossing
moves through side-by-side structures, a difference map, and an identity stack.
The difference map mutes shared arcs and preserves changed vertices as a fixed
frame of reference. The identity stack reports graph quotient, complete game,
and exact value. A secondary technical drawer can copy or download a JSON
record containing the exact relation, arc differences, source completion hash,
and full records for the chosen pair. No interaction alters the evidence,
repertoire, or equality certificate.

## Evidence

The interface reads checked JSON from `visualizer/public/evidence/`.
`fixed-value-motif.json` records the positions, digests, exact comparison, run
completion, and event indices. `repertoire-browser.json` binds the motif to the
completed study. The study replayed 73,728 proposals and found 21,697
quotient-unique representatives across the targets `0`, `*`, and `1/2`.

The site states the boundary plainly. Exact equality, graph quotient, and
complete-game identity were measured. Aesthetic preference was not measured.

The historical note cites Lewis Stiller's account of the endgame kernel and
Noam Elkies's composition. The checked `elkies-study.json` artifact retains the
published line and its legal replay, although the current page does not render
the full move player.

Rebuild or check the evidence with:

```bash
PYTHONPATH=python python3 scripts/build_elkies_study_evidence.py --check
PYTHONPATH=python python3 scripts/build_visualizer_evidence.py --check
```

## Development

```bash
cd visualizer
npm ci
npm test
npm run lint
```

The production build uses vinext and targets OpenAI Sites.
