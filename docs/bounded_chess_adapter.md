# Bounded chess adapter

Status: executable v0.1 contract for constrained FENs.

## Purpose

The adapter turns one accepted chess position into an explicit finite
normal-play game. It supplies the missing bridge between the native chess
stack and the fixed-value explorer:

```text
FEN
 └─ Astralbase constrained-domain gate
     └─ Shakmaty legal-move expansion
         ├─ Bitmesh root certificate and one-ply status
         └─ bounded Left/Right option tree
             ├─ Thermograph structural identity
             └─ Partizan exact fixed-value comparison
```

Every output is a content-addressed adapter record. Accepted outputs carry the
literal game and both structural identities. Refused outputs carry a stable
reason code. `chess-verify` reconstructs the record from its FEN and settings
and requires exact agreement. Each record also names the frozen Astralbase,
Bitmesh, and Thermograph source-candidate commits used by clean-room CI.

## Projection rule

`bounded_alternating_legal_move_normal_play_v1` defines the following finite
game:

- a position with White to move places every legal chess move among Left's
  options;
- a position with Black to move places every legal chess move among Right's
  options;
- a position with no legal moves is the zero game;
- a nonterminal position at `max_plies` is also the zero game; and
- recursively identical options are sorted and deduplicated.

The horizon is part of the game definition. The resulting tree therefore has
exact finite semantics under
`formal_domain:bounded_chess_projection:v0`. Checkmate and stalemate counts
remain separate in the record even though both become no-option leaves.
Orthodox draw outcomes, historical draw claims, and unbounded chess solution
values lie outside this certificate.

The current limits are 1–8 plies and at most 100,000 visited position nodes.
Reaching the node budget produces `node_budget_exhausted`; the adapter never
inserts an unevaluated partial tree.

## Native trust boundary

Astralbase decides whether the root FEN belongs to
`formal_domain:first_constrained_chess:v0`. The adapter records its canonical
FEN, terminal/tactical status, and decomposition result.

Bitmesh contributes a root-position decomposition digest and the status of its
conservative one-ply independence screen. These fields retain their
board-local scope. The bounded legal tree is expanded directly from Shakmaty
and does not infer future additivity from the Bitmesh observation.

Thermograph supplies a versioned SHA-256 structural identity for the projected
tree. Partizan separately applies Conway's recursive order when a projected
tree enters fixed-value search. Structural identity and game-value equality
remain independently checkable.

## Command line

Create and replay a record:

```bash
partizan chess-adapt \
  --fen '7k/5K2/6Q1/8/8/8/8/8 w - - 0 1' \
  --max-plies 1 \
  --node-budget 100 \
  --output /tmp/mate-frontier-depth1.adapter.json

partizan chess-verify /tmp/mate-frontier-depth1.adapter.json
```

A typed refusal is still written to the requested output path.
`chess-adapt` returns exit status 2 for that outcome.

Convert an accepted record into fixed-value inputs:

```bash
partizan chess-target \
  /tmp/mate-frontier-depth1.adapter.json \
  --name mate-frontier-one \
  --output /tmp/mate-frontier.target.json

partizan chess-candidate \
  /tmp/mate-frontier-depth1.adapter.json \
  --ordinal 0 \
  --output /tmp/mate-frontier.candidates.jsonl
```

The candidate's embodiment identity uses the clock-free Shakmaty move-state
key: board, side to move, castling state, and en-passant state. Its generator
provenance binds the full adapter identity, which in turn binds the canonical
FEN, horizon, node budget, Bitmesh digest, Thermograph digest, literal-game
digest, and projection statistics. FEN clocks therefore cannot manufacture an
embodiment difference. Existing `partizan search` performs the exact target
comparison.

An adapter-record JSONL stream can run end to end:

```bash
partizan chess-search \
  --target-record /tmp/left.adapter.json \
  --candidate-records /tmp/candidate-adapters.jsonl \
  --name bounded-one \
  --seed 0 \
  --budget 2 \
  --max-results 2 \
  --output /tmp/chess-repertoire.json

partizan verify /tmp/chess-repertoire.json
```

Each line of `candidate-adapters.jsonl` is a complete accepted record produced
by `chess-adapt`.

## Checked crossing

Two legal KQK positions provide the checked same-horizon crossing:

```text
7k/8/5K2/8/8/8/8/6Q1 w - - 0 1
7k/8/5KQ1/8/8/8/8/8 w - - 0 1
```

Both use a four-ply horizon and the same 20,000-node budget. The first
projection has 19 literal nodes; the second has 11. Each position includes
`Qg7` as an immediate checkmate. Their SHA-256 literal-game identities differ.
Conway's recursive order certifies each game equal to

```text
{0 | } = 1.
```

The test suite admits both realizations into one repertoire and classifies
their relationship as `literal_game_crossing`. This fixture holds the
projection rule and resource settings fixed while the chess position and
complete literal tree both change.

## Record verification

The Draft 2020-12 schema is
`docs/schemas/partizan-bounded-chess-adapter-v0.1.schema.json`.
`validate_chess_adapter_record` additionally checks:

- the content-addressed adapter ID;
- the frozen upstream source-candidate map;
- canonical literal-game identity;
- linkage between Bitmesh proof and decomposition digests;
- linkage between literal tree and literal-game digest;
- bounded settings and accepted/refused state consistency; and
- byte-equivalent native replay.
