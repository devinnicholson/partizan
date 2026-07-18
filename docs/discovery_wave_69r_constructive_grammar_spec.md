# Wave 69-R constructive grammar and proof obligations

Status: implementation specification; no Stage B or Wave 70 authorization.

This document specifies the repair prompted by the Wave 69 Stage A support
failure. It is bound to the source behavior at these commits:

- Partizan `6ddd22af4adb7ff8f6f4c361a9132720a47e87b7`
- Astralbase `1434fca1fc04d97798ec1b820c56f52f8014ccc7`
- Bitmesh `ade3417a007b9c8392d8a153abc4b3ed23edf0aa`
- Thermograph `1d9b6b01c3921aca8c2a8fb13972fee8a4de5041`

The generator family is `dfile_two_component_constructive_grammar_v2`. Its
construction contract is
`partizan.dfile_two_component_constructive_grammar.v0.2`. Accepted boards must
still carry Bitmesh's existing
`bitmesh:conservative_legal_independence:v0` proof. The proposed outcome-blind
supply audit is `partizan.wave69r_structural_supply_audit.v0.1`.

## Exact scope and nonclaim

Bitmesh v0 proves a property of the supplied board. It uses an eight-neighbor
partition around locked pawns, then conservatively checks geometric
destinations for both colors. It does not prove that the components remain
independent after a move or throughout an orthodox-chess game tree. The
Astralbase value rule is likewise a bounded, board-syntax construction: it
recurses to depth two over component-local moves and uses material balance at
the cutoff or a node with no moves. It is not an orthodox-chess evaluation.

Thermograph supplies the exact structural-tree identity used after replay. It
does not strengthen the Bitmesh separation claim. Accordingly, the theorem
below is a constructive sufficient condition for the current one-ply Bitmesh
screen and the bounded Astralbase domain, not a theorem of arbitrary CGT
equivalence or future chess independence.

## Why Stage A rejected 5,624 boards

The Wave 69 audit records four first-reported Bitmesh failures. They are not
necessarily exclusive: verification stops at the first error, so one board can
violate more than one underlying obligation.

- `RequiresStrictDecomposition` (2,315): `get_locked_pawns` omits a d-file
  pawn whenever that pawn has an opposing diagonal capture. The mixed grammar
  could therefore punch a hole in the intended wall. Under eight-neighbor
  connectivity, one missing d-file square reconnects the left and right free
  regions, leaving fewer than two active components.
- `BarrierPawnNotFrozen` (391): a d-file pawn can be considered locked because
  its forward square is occupied, while that forward pawn is itself omitted
  from the certified barrier because it has a capture. The verifier requires
  the forward blocker to be part of the barrier, not merely occupied.
- `BarrierPieceCanBeCaptured` (2,722): an active slider, leaper, or pawn had a
  geometric capture onto an oppositely colored d-file pawn. Sliders aimed at
  the wall and near-wall knights account for the obvious cases.
- `PieceCanEnterOtherComponent` (196): most directly, a knight on c or e can
  jump across the d-file wall. A locked-pawn wall blocks rays but not leapers.

The repair must remove these failure modes by construction. Calling Bitmesh or
Astralbase and discarding rejected candidates would merely hide the same
support defect before the ledger and is forbidden.

## Constructive sufficiency theorem

Number ranks 1 through 8 and write `w(r)` for White on odd ranks and Black on
even ranks. Let

```
W = {d1:P, d2:p, d3:P, d4:p, d5:P, d6:p, d7:P, d8:p}.
L = files a,b,c; R = files e,f,g,h.
```

For a board `B = W union A_L union A_R`, define `D_B(x)` exactly as Bitmesh
does: actual pawn captures plus conservative one- and two-square pawn quiet
destinations, or Shakmaty geometric attacks with friendly destinations removed
for any other role.

The following conditions are sufficient:

1. `A_L` and `A_R` are nonempty, disjoint from each other and from `W`, and
   every active square is in its named region.
2. No wall pawn has an opposing active piece on a diagonal attack square.
3. Every active pawn has an on-board, empty forward square. Thus no active pawn
   is annexed into the detected locked-pawn barrier.
4. For every active piece `x` in side `C`, `D_B(x)` is a subset of `C` and is
   disjoint from `W`.

Then `get_locked_pawns(B) = W`: each wall pawn is blocked by another wall pawn
or by the board edge and has no opposing capture, while condition 3 excludes
every other pawn. Removing the complete d-file leaves exactly the two
eight-connected regions `L` and `R`, and condition 1 makes both active.
`certify_decomposition` is therefore strict with exactly two components.
Conditions 2 and 4 then discharge every branch of
`verify_frozen_barrier_pawns` and `verify_active_piece_destinations`, yielding
`bitmesh:conservative_legal_independence:v0`.

The proof is deliberately stated in the same conservative movement semantics
as Bitmesh. Side to move, check, pins, castling, en passant, promotion, and move
counters do not enter it.

## Static component grammar

Generation selects from checked-in, parameterized component constructors. It
does not create a mixed board and ask a verifier whether it happened to work.
The catalog freezes the four strata, their finite ray-cage and mixed-hook base
records, the allowed leaper and pawn parameters, and the composition schedule.
Its source boundary records public, pre-split Astralbase source families at the
pinned commit; target rows, target FENs, target digests, and the Wave 69
reference atlas are not catalog inputs.

Each emitted component receives a stable template ID computed from its
stratum, side, and one-to-five piece-square-color triples. Every finite base
record and every allowed parameter range is reviewed and versioned as source,
not synthesized or adapted during an experimental run. A static witness for
each wall-facing move is implicit in those frozen constructors: either the wall
pawn is friendly or an occupied intercept terminates the ray.

### Safe atoms

The following atoms are compositional: adding other active material can only
truncate a non-pawn ray, and pawn captures remain inside the same component.
Here `m` is the file distance from d.

- Pawns on a, b, f, g, or h may have either color, subject to an on-board empty
  forward square. A c-file pawn is allowed only when it is White on an even
  rank or Black on an odd rank; this is the color of both adjacent wall pawns
  that could attack it. The v0.2 catalog leaves the e-file empty.
- Knights on a, g, or h may have either color. A knight on b or f must be White
  on an even rank or Black on an odd rank, so every d-file landing square is
  friendly. Knights on c or e are forbidden because they can jump into the
  other component.
- A rook on a, b, f, g, or h must have color `w(r)`, matching the wall pawn on
  its horizontal ray.
- A bishop on a, b, f, g, or h must have color `w(r + m)`; both possible
  diagonal intersections with d have that parity.
- An uncaged queen is allowed only on b, f, or h and must have color `w(r)`.
  On these even-distance files its rook and bishop wall-color obligations
  agree.
- Kings are excluded. Although the board parser can represent them, they are
  absent from the declared source-family alphabet and add no needed support.

Every pawn atom includes its forward-square witness. Catalog composition must
reject overlaps before generation begins; it must not silently turn an active
pawn's forward witness into an occupied square.

### Indivisible ray cages

Some source-family structures obtain useful move topology from a slider that
would not be a safe atom alone. A ray cage is an indivisible template whose
mandatory occupied intercept stops each hostile wall-facing ray. The intercept
is itself a safe atom and cannot overlap the wall or another template record.
The initial v0.2 cages are:

- left white bishop or queen on a1 with b2 occupied by a compatible safe atom;
- right black bishop or queen on h8 with g7 occupied by a compatible safe
  atom;
- the exact checked-in base records only; v0.2 includes no rank translation.

White rooks on a1 and black rooks on h8 need no cage: d1 and d8,
respectively, are friendly. A cage
may add more interior pieces, but it may not replace, move, or conditionally
omit its intercept.

### Diversity strata

Every 1,024-row pool uses target-independent round-robin allocation: exactly
256 rows from each of four strata.

1. `outer_leaper`: safe edge knights with zero or more mobile pawn atoms;
2. `pawn_phalanx`: two or more mobile pawn atoms with at least one same-rank or
   adjacent-file relation;
3. `ray_cage`: at least one declared slider cage;
4. `mixed_color_hook`: both colors occur within at least one component using
   only safe atoms or cages.

Each stratum must expose at least eight component template IDs on each side,
and pair orientation is balanced. These are construction facts recorded in the
catalog manifest, not statistics learned from target outcomes. The grammar may
vary role, color, square, component cardinality, local blocking, and
left-right pairing. Every FEN envelope is fixed to `w - - 0 1`. Astralbase
evaluates only the board-placement field, so varying side to move or any other
ignored metadata would create nominally distinct Partizan identities for the
same evaluated object and is forbidden.

## Bounded depth-two domain

The grammar permits at most five active pieces per component. A queen has at
most 27 geometric destinations on an eight-by-eight board, so the combined
local branching bound is `B <= 5 * 27 = 135` per component. Captures cannot
increase the piece count. Astralbase's depth-two recursion therefore visits at
most

```
1 + B + B^2 = 18,361 nodes per component,
36,722 nodes across two components.
```

This is below the frozen 100,000-node candidate budget. The bound is
independent of target identity and does not require a trial verifier call.

## Target blindness and attempt accounting

The generator's random stream is controlled only by the explicit protocol
seed, generator version, stratum index, and counter. A target ID may bind a
proposal envelope after board generation; no target field may choose a
template, role, square, color, pairing, retry, or order. Given one explicit
seed, target specs that differ only in target content must produce identical
FEN streams before envelope binding.

An attempt begins when a left template, right template, and pairing
orientation have been decoded. Side to move is not sampled. Attempt counters
distinguish emitted rows, candidate-key collisions, and
file-reflection-orbit collisions. Syntactic deduplication is allowed. A
catalog or construction-invariant failure is a hard generator error, is
recorded, and terminates the run; it is never a retry or a discard. The
existing finite attempt cap remains binding, and exhaustion fails the pool
rather than reducing its size.

The generation receipt binds the catalog manifest, construction-contract
version, PRNG, seed, decoded-attempt count, collision counts, emitted count,
and two byte-identical separate-process artifacts.

## Property and mutation test plan

Implementation is not ready until all of the following tests exist.

### Catalog and construction properties

- Validate every record against the JSON schema and recompute all static
  wall-color, ray-intercept, knight-landing, and pawn-forward witnesses with an
  implementation independent of the generator selector.
- For every component template, assert no overlap with the wall, one to five
  pieces, the declared side, role alphabet, and stratum predicate.
- Exercise every catalog record on both sides and the full declared pair
  schedule. Assert that the detected barrier equals exactly `W`, the structural
  certificate is strict, there are exactly two active components, and the
  Bitmesh proof kind is the pinned v0 contract.
- Exercise Astralbase's bounded evaluator in ordinary implementation tests and
  assert the analytic 36,722-node bound. These tests are compatibility checks,
  not Gate S evidence; no Astralbase value, identity, target comparison, or
  Thermograph output enters the outcome-blind supply audit.
- Recompute candidate and file-reflection-orbit identities, check all final
  rows are unique, and require separate-process byte identity.
- Assert that every generated FEN has the exact metadata `w - - 0 1`; a
  metadata-only mutation must be rejected rather than counted as new support.
- Assert identical pre-envelope FEN bytes for target specs with different
  identities, values, provenance, and ranker views under the same seed.

### Mutation tests for the Stage A failures

- Put an opposing piece on a wall pawn's capture square or remove one d-file
  pawn; expect loss of strict decomposition.
- Make a forward wall blocker capture-capable while leaving the pawn behind it
  locked; expect `BarrierPawnNotFrozen`.
- Flip the color of a wall-facing slider or remove a mandatory cage intercept;
  expect `BarrierPieceCanBeCaptured`.
- Move a knight to c or e; expect `PieceCanEnterOtherComponent`.
- Occupy an active pawn's forward witness without giving it a capture; assert
  that it is annexed into the barrier and that the catalog validator fails
  before generation.

Each mutation must kill the corresponding property even if Bitmesh reports an
earlier failure on a multi-defect board. Unit fixtures should isolate one defect
at a time.

## Outcome-blind structural supply audit

Before a new calibration, run four independent, preregistered, target-free
seeds of 1,024 rows each. Gate S passes only with all of the following:

- 4,096/4,096 exact wall detections and strict two-component certificates;
- 4,096/4,096 `bitmesh:conservative_legal_independence:v0` proofs;
- zero rejected rows, internal errors, invariant failures, candidate-key
  duplicates, or reflection-orbit duplicates in the emitted artifacts;
- byte-identical replay from a second clean process for every seed;
- exactly 1,024 emitted rows per diversity stratum across the four seeds.

Because the grammar claims construction, the gate is 100%, not an estimated
95% threshold. Any failure is an implementation or theorem defect and requires
a new generator version and preregistration. The independent Gate S authority
is Bitmesh only. The audit report may reveal only structural and
generator-resource facts; Astralbase values, Thermograph identities, target
comparisons, and exact-value outcomes are outside Gate S.

## Frozen prohibitions

- Do not read or derive templates from the six Stage A source FENs, any Stage B
  record, any Wave 70 record, target identities, or verifier outcomes.
- Do not call Bitmesh, Astralbase, or Thermograph from candidate generation and
  do not filter, repair, reorder, or retry according to their results.
- Do not add or remove templates after Gate S bytes are visible. A catalog
  change requires a new version, seeds, receipts, and preregistration.
- Do not substitute targets or erase the original Wave 69 Stage A failure.
- Gate S does not open Stage B or Wave 70. A separately frozen calibration
  protocol must authorize reuse of the six Stage A targets.

## Remaining caveats

The theorem guarantees structural supply, not target support. Gate S can pass
with zero matches. If a properly preregistered calibration obtains structural
coverage but still no exact identities, the bottleneck has moved from board
validity to target-conditioned semantic supply. That would justify a new,
leakage-audited representation and generator/ranker study; it would not justify
quietly adapting this catalog to the held-out targets.
