# Formal Domain Specification

Status: draft for the first exact benchmark.

The first benchmark domain must be narrow enough for exact verification and
wide enough to test agency, temperature, decomposition, and composition.

## Label Classes

- `exact`: every legal child is known, the value is derived by the exact engine,
  and the row includes a certificate.
- `rejected`: the position is valid input but outside the exact domain.
- `heuristic`: the position uses weak-coupling or model-assisted assumptions and
  is excluded from exact training splits by default.
- `prediction`: model output only; never treated as ground truth.

## Required Position Fields

- board representation
- side to move
- legal move list hash
- component masks or explicit non-decomposable marker
- terminal status
- generator config id
- verifier version

## First Candidate Domain

The first candidate domain is locked-structure mini-endgames:

- standard legal chess positions unless a separate generalized-board shard is
  explicitly declared
- kings are present and legal
- barrier structures are certified by `bitmesh`
- components are solved independently only when strict independence is certified
- positions with captures that can break a barrier are rejected from exact
  decomposition unless the break is included in the local game graph

## Open Decisions

- Maximum piece count for Dataset v0.
- Whether Dataset v0 allows non-pawn pieces or starts with kings plus pawns only.
- Whether generalized boards are a separate benchmark or a later OOD split.
- Exact serialization format for canonical values and proof certificates.

## Acceptance Criteria

- Unsupported positions are rejected before solving.
- Strict decompositions include a machine-checkable certificate.
- Weak decompositions are tracked separately from exact labels.
- Small domains can be exhaustively checked against brute-force search.
