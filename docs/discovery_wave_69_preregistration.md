# Wave 69 preregistration: discovery baselines

Status: **draft; pending implementation**. Partizan commit
`89c325d52a67bde4d6ac997f4527b7c56a119cf7` is the implementation base, not
the commit containing this document. The preregistration becomes frozen only
at a future immutable Partizan commit containing this document and the
accepted target-registry, generator, and baseline implementations. That
integrated freeze must precede every Stage A proposal and result artifact.
Until then, commands for unimplemented artifacts in the Wave 69 manifest are
marked **pending implementation**, not presented as runnable gates.

## Question and claim boundary

Wave 69 asks whether a fixed, proposal-only structural heuristic finds more
distinct certified realizations of a requested bounded game form within a
fixed verifier-call budget than random ordering of the same frozen pool. It
also establishes the non-learned baseline that a later ranker must beat.

The verifier target remains
`bounded_structural_game_form` under
`component_depth2_local_move_game_v0`, with
`thermograph_structural_tree_v1` identity and `board_syntax_only` legality.
Structural-tree identity is not arbitrary CGT equivalence. The boards are
chess-derived formal objects, not certified legal orthodox-chess positions.
The Stiller/Elkies positions remain historical anchors and unsupported exact
targets.

## Target registry and frozen split

The registry source is the cleanly regenerated 108-row Wave 55 reference
atlas with this content boundary:

```text
row count: 108
atlas SHA-256: 58046bbcbb4644018d4bf31907fcd555220d2bb8e2a5f67607beb6f515883dbf
compressed atlas SHA-256: 471d40092d508e52fcf14d3e292818304fc7cea649c069c96d648ea8deb5ada1
Astralbase: 1434fca1fc04d97798ec1b820c56f52f8014ccc7
Bitmesh: ade3417a007b9c8392d8a153abc4b3ed23edf0aa
Thermograph: 1d9b6b01c3921aca8c2a8fb13972fee8a4de5041
Partizan implementation base: 89c325d52a67bde4d6ac997f4527b7c56a119cf7
replay report SHA-256: bc6de682ffc4fe0f155ef4b130a3edcd3b43595552ed67a664b93621fb5d9a7f
replay report row_count: 108
replay report checked_exact_rows: 108
replay report skipped_rejected_rows: 0
replay report skipped_non_target_rows: 0
target registry: registry-sha256:e7383432360d848b0fd2996a8d4b3c2bf85ebd1492c6e4fff596f7b3391fb4a5
```

The source artifacts are now durably located at
`data/discovery/wave_69/reference-atlas.jsonl.gz` and
`data/discovery/wave_69/reference-atlas-replay.json`. The registry binds their
paths and content hashes and was regenerated from those checked-in bytes.
Historical `code_commit=workspace` rows are not used as evidence. The future
integrated Partizan commit containing the registry, generator, policies, and
this preregistration must still be recorded before Stage A generation.

Eligibility is decided without Wave 69 candidate outcomes:

1. Exclude source rows `012` and `090`, which were exposed during Wave 68
   implementation and audit.
2. Require a successful replay under the declared bounded rule, a SHA-256
   structural identity, exactly two conservatively decomposed components, and
   one of the three recorded Wave 55 topology families.
3. Within each topology family, sort eligible targets by regenerated recursive
   node count, then identity SHA-256, then source row id. Divide that order into
   six contiguous, size-balanced bins. From each bin select the target with the
   lexicographically smallest identity SHA-256.
4. Assign bins 0 and 3 to Stage A, bins 1 and 4 to Stage B, and bins 2 and 5 to
   the Wave 70 holdout. This yields six targets per split, two from each
   topology family. Duplicate identities are an eligibility failure, not an
   invitation to substitute after seeing candidate results.

The complete 18-target registry, assignments, source rows, regenerated
identities, target specs, repository commits, and registry SHA-256 must be
committed before any Stage A proposal is generated. If the eligible source
does not support this deterministic selection, Wave 69 stops for an amended
preregistration; the selection rule is not repaired after inspecting pools.

## Pools and phase separation

| Property | Stage A: calibration | Stage B: evidence | Wave 70: holdout |
|---|---:|---:|---:|
| Targets | 6 | 6 | 6 |
| Unique proposals per target | 1,024 | 4,096 | 4,096 planned |
| Purpose | generator/support gate | baseline evidence | learned-ranker test |
| Verifier outcomes usable in Wave 69 development | yes | only after all locks | no |

For each target and stage, the seed is the unsigned first 64 bits of
`SHA256("partizan/w69/pool/v1\0" || stage || "\0" || target_id)`. The
generator must emit these pre-verification features with fixed definitions:
`piece_count`, `white_piece_count`, `black_piece_count`, `pawn_count`,
`non_pawn_piece_count`, `occupied_file_count`, and
`has_locked_d_file_backbone`. The feature schema and generator configuration
are frozen before Stage A verification.

Each pool contains the first required number of distinct `candidate_key`
values in generator order. The generator receives one total attempt budget of
`20 * requested_unique_rows` candidate-generation attempts; this is not a
fresh allowance for each row. Failure to fill a pool inside that total cap is
reported and stops that stage; rows are not padded or borrowed. Generation is
run twice in separate Python processes and must be byte-identical. A canonical
generation receipt and its repository-relative path are bound by the v0.2
pool manifest and revalidated whenever the pool is loaded. The target,
proposals, pool manifest, generator configuration, seed, feature schema, and
four clean 40-character commits are hashed before any verifier call.

All random and heuristic orderings are also computed and hashed before the
first result is revealed. Astralbase then verifies the pool once in generator
order. Baselines are evaluated by joining their precommitted orderings to that
single complete result ledger. There is no adaptive querying, early stopping,
selective retry, or baseline-specific verifier run.

Stage A may establish feasibility but cannot support a paper result. Any
change to target selection, generator operators, features, heuristic, budgets,
or analysis after Stage A outcomes requires a new versioned preregistration and
new pools. It cannot silently turn Stage A into evidence. Stage B is evidence
even when negative; targets and failed rows are never removed post hoc.

## Frozen baselines

**Random.** For each target, generate 1,000 permutations. Replicate `r` uses
the first 64 bits of
`SHA256("partizan/w69/random/v1\0" || pool_id || "\0" || r)` as its seed.
Permutations use versioned SplitMix64 with rejection-sampled Fisher--Yates.
Each compact pre-result commitment records the seed, algorithm version, and
SHA-256 of the complete reconstructed proposal order. Report the mean, median,
and 2.5/97.5 nearest-rank-ceiling percentiles across permutations.

**Fixed structural heuristic.** Rank descending by

```text
1000 * has_locked_d_file_backbone
  + 25 * occupied_file_count
  + 10 * non_pawn_piece_count
  -  5 * abs(white_piece_count - black_piece_count)
  -      piece_count
```

Break ties by ascending `candidate_key`. The formula is fixed before Stage A
outcomes, uses only proposal fields allowed by
`proposal_only_ranker_input_v0.1`, and is neither fitted nor verifier-aware.
Generator ordinal is reported only as an audit control, not promoted as a
competitive baseline.

## Outcomes and metrics

A success is a `verified_match` whose actual value class and structural
SHA-256 equal the requested target. A distinct realization is a previously
unseen `position.symmetry_sha256` among successes. Every attempted candidate,
including a duplicate realization, nonmatch, rejection, or error, consumes one
verifier call.

The primary metric is target-macro discovery efficiency at 256 calls:

```text
DE@256 = mean over the six targets(
  distinct certified symmetry classes in the first 256 ranked rows / 256
)
```

The primary Wave 69 contrast is fixed heuristic `DE@256` minus random mean
`DE@256` on Stage B. Report the upper-tail proportion over the 1,000 fixed
preregistered random permutations and a 95% target-bootstrap interval as
descriptive uncertainty. This proportion is not an exact probability over all
possible permutations, and six targets do not justify broad population claims.

Secondary metrics are `DE@64`, `DE@1024`, the normalized area under the
distinct-discoveries curve through 1,024 calls, calls to first success,
verified-match prevalence, verified-nonmatch rate, rejection rate,
internal-error rate, and raw versus symmetry-unique successes. All metrics are
reported per target and macro-aggregated. No secondary metric can replace the
primary one after outcomes are visible.

NAUDC uses right-endpoint discrete rectangles over calls 1 through 1,024 and
denominator `1024 * 1024`. Random-distribution percentiles and bootstrap
endpoints use nearest-rank ceiling. A no-success calls-to-first observation is
right-censored at `pool_size + 1`. These estimator choices are fixed before
Stage A outcomes.

## Gates and failure policy

Integrity gates, required for either stage:

- clean immutable commits for all four repositories and a committed registry;
- byte-identical double generation, unique candidate keys, complete frozen
  manifests, and pre-verification hashes for every ordering;
- ranker-input audit with no result, certificate, status, ordinal, expanded
  node, rejection, or label field;
- exactly one schema-valid verifier result per proposal, in input order, with
  all call and node budgets recomputable from the ledger;
- zero `internal_error` outcomes and deterministic full replay of the ledger;
- no row deletion, result-dependent retry, target replacement, or change to a
  locked artifact.

An integrity failure invalidates the stage. Repair requires new code commits,
new seeds/version, and a new pool; partial results remain diagnostic and are
not filtered into evidence.

Stage A additionally requires, for every target: all 1,024 unique proposals,
at least 95% `verified_match` plus `verified_nonmatch`, at least eight matches,
and at least four symmetry-unique matches. Any miss is a Wave 69 support
no-go. Stage B is not opened and targets are not swapped.

Stage B's results remain reportable evidence regardless of yield. A positive
discovery-efficiency claim additionally requires every target to have at least
eight symmetry-unique matches and the suite to have at least 96 in total.
Failure is reported as an adequately executed no-go, not converted to a
smaller favorable target set.

## Wave 70 holdout rule

Wave 70 target assignments and target specs are frozen in the pre-Stage-A
registry, but no Wave 70 proposals may be generated or verified during Wave
69. Wave 69 Stage A and B outcomes may later be used to design or train a
ranker. Before any Wave 70 pool is generated, the generator, feature schema,
model code, model weights, baseline code, primary analysis, and repository
commits must be frozen and hashed.

Wave 70 is also an explicit **NO-GO** while `target.ranker_view` supplies only
an opaque structural SHA-256 plus generic rule metadata. An opaque identifier
does not tell a ranker what semantic structure to seek and invites target-id
memorization rather than target-conditioned discovery. Before the holdout is
opened, a versioned ranker-view contract must expose a semantic target
representation, such as an approved canonical structural serialization or
invariant feature representation. The representation must be computable from
the target before candidate generation and must not contain candidate
outcomes, certificates, source-row identity, prevalence, split statistics, or
other result-derived data.

The verifier red team must approve that contract, its canonicalization, and
negative leakage controls before a learned Wave 70 ordering is allowed. The
audit must demonstrate that semantically different targets yield meaningfully
different ranker inputs and that changing an opaque id alone cannot provide
the target signal. Reserving the Wave 70 rows in this draft does not clear this
semantic-target gate.

The frozen ranker may then receive each Wave 70 target's allowed
`ranker_view` and its frozen proposal-only inputs. Its complete ordering and
the two baseline orderings must be committed before a single Wave 70 verifier
result is revealed. Wave 70 permits one unblinded verifier pass. Any prior
generation, inspection, tuning, or selective replacement of a Wave 70 pool or
outcome forfeits its held-out status and requires a new preregistered target
split.
