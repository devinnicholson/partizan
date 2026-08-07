# Partizan visualizer

Status: executable historical witness followed by a checked fixed-value
crossing.

## Historical prelude

The first instrument replays the thirteen-ply line published in Lewis Stiller's
*Multilinear Algebra and Chess Endgames* (1996), pp. 176–177. Stiller describes
the computer-found KQQKQQ mutual-zugzwang kernel and the eight-piece composition
Noam Elkies built around it. The visualizer follows:

```text
1. Qg7+ Kh2 2. f8=Q Qb5+ 3. Kh6 Qb6+
4. Bc6 Qxc6+ 5. Kxh7 b1=Q+ 6. Kh8 Kh1! 7. Qfg8!!
```

Partizan replays every UCI move from the preceding board state in the native
Shakmaty engine. The generated artifact records canonical FEN, SAN, check
state, legal-move count, captures, and promotions for the initial position and
all thirteen plies.

This witness has a narrow claim boundary. The artifact verifies legal replay
and reproduces the published final position. The publication supplies the
line's historical origin and analysis. The artifact does not independently
prove forcedness, optimality, mutual zugzwang, or a CGT value.

Rebuild or check it with:

```bash
PYTHONPATH=python python3 scripts/build_elkies_study_evidence.py
PYTHONPATH=python python3 scripts/build_elkies_study_evidence.py --check
```

`tests/test_chess_witness.py` checks the native replay and its refusal of an
illegal move. The visualizer's rendered-page test binds the 14-frame artifact,
final FEN, final `Qfg8`, and visible scope labels.

## Exact crossing

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

The exact crossing exposes four stages:

1. **Receive** — display the two source FENs.
2. **Distinguish** — reveal their different literal trees and search measures.
3. **Move** — animate the unique immediate mating witnesses `Qg1-g7` and
   `Qg6-g7`.
4. **Certify** — disclose the shared value and crossing relation.

Both instruments support direct selection and timed replay. The historical
line adds previous/next controls, a complete clickable score, six annotated
landmarks, and scoped arrow-key navigation. Responsive layouts and
reduced-motion preferences apply throughout.

## Composer's desk

The composer's desk loads the mechanically selected `A → B → C` target-0 motif
from the completed order-7 study. All three forms have already passed mutual
Conway comparison against the same target. The interface keeps three roles
visible:

1. the acquisition policy directs verifier attention;
2. exact comparison controls admission to the value-0 repertoire; and
3. the composer inspects the admitted forms and chooses one for further work.

Form A contains 19 literal nodes and 18 literal edges. Removing `2→3` produces
form B, changes the graph quotient, and contracts the complete literal game to
15 nodes and 14 edges. Adding `6→0` produces form C, changes the graph quotient
again, and leaves the complete literal-game digest byte-identical to B. The
interface exposes those certified differences without ranking the forms.

Choosing **Carry form forward** records only browser-local interaction state.
It does not alter an evidence artifact, update the repertoire, or enter the
equality certificate.

## Crossing evidence contract

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
