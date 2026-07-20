# Wave 68 Stiller/Elkies scope report

Status: implementation scope, not discovery evidence.

## Historical anchor

Lewis Stiller reports a program-found KQQKQQ mutual-zugzwang kernel and an
eight-piece composition by Noam Elkies derived from the same idea. The
positions transcribed from Stiller's Figure 7 are:

```text
8/q7/5q2/8/8/8/6QQ/k6K w - - 0 1
8/q7/5q2/8/8/8/6QQ/k6K b - - 0 1
```

The initial Elkies composition is:

```text
5Q2/5P1b/8/7K/8/1q4k1/1p4B1/8 w - - 0 1
```

Source: Lewis Stiller, "Multilinear Algebra and Chess Endgames," Figure 7,
pp. 176--177, <https://library.slmath.org/books/Book29/files/stiller.pdf>.

All three strings parse as legal standard-chess FENs. The two kernel records
differ only by side to move. This makes them suitable historical and visual
anchors for the paper.

## Current support boundary

The current stack cannot certify these positions as exact CGT values.

- The KQQKQQ kernel is within the eight-piece count, but Bitmesh reports one
  active component, no locked barrier, and no conservative decomposition.
- The initial Elkies study contains a locked pawn at f7, but still yields one
  active component and no accepted structural partition.
- Astralbase can represent the positions in its reusable retrograde store, but
  it does not provide exhaustive KQQKQQ tablebases, draw completeness, or CGT
  canonical forms.
- Thermograph's non-number identity is a stable structural serialization. It
  is not equality modulo arbitrary CGT equivalence.

The Stiller/Elkies positions therefore remain historical inspiration and
negative domain controls in Wave 68. They must not appear as machine-replayed
exact evidence.

## Executable fallback

Wave 68 uses one Wave 55 board construction as an infrastructure target. Its
declared semantics are:

```text
domain: formal_domain:bitmesh_composed_board_material:v0
value rule: component_depth2_local_move_game_v0
identity contract: thermograph_structural_tree_v1
target kind: bounded_structural_game_form
legality contract: board_syntax_only
```

This target is exact only under the declared depth-two local-move rule, which
uses material balance at cutoffs. Some Wave 55 board strings omit kings and are
not legal orthodox-chess positions. A successful Wave 68 replay proves target
comparison, provenance, refusal accounting, and ranker isolation. It does not
prove an exact nontrivial orthodox-chess CGT result.

The preferred golden is Wave 55 row 090, the row with the largest recorded
depth-two search:

```text
row id: astralbase-w52-mixed-hook-signature-target-exact-090
board: 3p4/3P2Nn/3p4/3P1n2/3p4/2pP4/3p4/Qn1P4 w - - 0 290
recursive nodes: 349
structural target SHA-256: d31d0b8acc19a8174b7c3a48d268cd7d63effc9213b7c91b7b50e70260398bbc
decomposition digest: cb18d5497662eadfeebfafe22ea8b3f3eddc609ab71fff49950411b749fe6115
composition digest: d311c1a0c1b3c8878b395b7ae5c531aa6579924ddeff495e11d04c3688ef4460
```

Historical `code_commit=workspace` provenance cannot be promoted. The Wave 68
artifact must be regenerated and replayed from immutable forty-character
commits for Partizan, Astralbase, Bitmesh, and Thermograph.

## Promotion gate for later waves

Model-guided chess discovery remains blocked until a later wave supplies a
nontrivial legal-chess target with a declared complete verifier, or narrows the
paper claim explicitly to chess-derived bounded games. The fallback artifact
may test discovery infrastructure and ranking isolation only.
