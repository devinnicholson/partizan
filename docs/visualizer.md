# Partizan visualizer

Status: executable visual witness for the checked fixed-value crossing.

## Purpose

The visualizer makes one certified comparison directly inspectable. It begins
with two legal KQK positions:

```text
7k/8/5K2/8/8/8/8/6Q1 w - - 0 1
7k/8/5KQ1/8/8/8/8/8 w - - 0 1
```

The native adapter expands each position through four plies with the same
20,000-position-node budget. Partizan admits both results into one
fixed-value repertoire. Conway's recursive order certifies each projected game
equal to `{0|} = 1` and equal to the other.

The visual sequence exposes four stages:

1. **Receive** — display the two source FENs.
2. **Distinguish** — reveal their different literal trees and search measures.
3. **Move** — animate the unique immediate mating witnesses `Qg1-g7` and
   `Qg6-g7`.
4. **Certify** — disclose the shared value and crossing relation.

The interface supports direct stage selection, timed replay, left/right arrow
navigation, responsive layouts, and reduced-motion preferences.

## Evidence contract

`scripts/build_visualizer_evidence.py` produces
`visualizer/public/evidence/crossing.json`. The bundle contains:

- the exact FEN and clock-free move-state key for each realization;
- the content-addressed chess-adapter identity;
- the unique immediate checkmating move;
- projection statistics, including the 19-node and 11-node literal games;
- separate literal-game and Thermograph structural identities;
- the fixed-value repertoire identity;
- exact equality results against `1` and between the realizations; and
- a SHA-256 digest over the complete evidence payload.

The generator refuses to write a bundle unless both native records are
accepted, both literal games compare equal to `1`, the games compare equal to
one another, the repertoire replays cleanly, and the admitted relationship
includes `literal_game_crossing`.

Rebuild or check the committed artifact:

```bash
PYTHONPATH=python python3 scripts/build_visualizer_evidence.py
PYTHONPATH=python python3 scripts/build_visualizer_evidence.py --check
```

`tests/test_visualizer_evidence.py` independently rebuilds the bundle and
requires byte equality with the committed artifact.

## Visual boundary

The animated moves are root-level terminal witnesses recorded by Astralbase's
immediate-tactic analysis. The literal-tree constellations encode the certified
node counts and distinct literal-game identities. Their layout is an
explanatory rendering; the complete recursive game objects and comparisons
remain in the adapter and repertoire records.

The visualizer never assigns chess-engine evaluations or claims an unbounded
solution value. Its equality statement remains scoped to the declared bounded
normal-play projection.

## Development

The application lives in `visualizer/` and uses the repository's generated
evidence as its only research input.

```bash
cd visualizer
npm ci
npm run dev
npm test
npm run lint
```

The production build targets the OpenAI Sites runtime through vinext.
