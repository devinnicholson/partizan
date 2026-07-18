# Wave 69-R preregistration: constructive candidate-supply repair

Status: **implementation-complete; pending immutable freeze at I**. No Wave
69-R candidate, structural result, target pool, verifier result, or
learned-model artifact exists at this status. This document becomes frozen
only at the immutable Partizan implementation commit **I** containing the
accepted constructive grammar, structure-only audit interface, schemas,
orchestration, and tests. I must precede every empirical Gate S or Gate C
suite input or result byte.

Wave 69-R is a new calibration, not a continuation that edits Wave 69 Stage A.
Wave 69 evidence commit
`6ddd22af4adb7ff8f6f4c361a9132720a47e87b7` and its 6,144 rows remain
immutable. Its sound NO-GO—520 certified nonmatches, 5,624 conservative
decomposition rejections, zero matches, and zero internal errors—is the reason
for this repair. Those rows cannot be deleted, relabeled, regenerated under
their old identity, or promoted to paper evidence.

## Question and decision boundary

Wave 69-R asks two sequential questions:

1. **Gate S, structural supply:** can a target-blind constructive grammar emit
   chess-derived boards that independently satisfy Bitmesh's conservative
   two-component decomposition contract on every preregistered audit row?
2. **Gate C, repaired calibration:** if Gate S passes, does that grammar supply
   enough certified exact realizations for the same six Wave 69 Stage A
   bounded structural targets to justify opening a separately preregistered
   Stage B experiment?

Gate S is outcome-blind. It may reveal only Bitmesh conservative-independence
certificate data, the four structural predicate results, structural failure
codes, and internal checker errors. Its input has no requested target. Its
implementation cannot invoke Astralbase target evaluation, Thermograph
expansion or identity, requested-value comparison, baseline evaluation,
learned ranking, or any result-label producer. A generator self-certificate is
not authoritative; independent Bitmesh certification decides Gate S.

Gate C is target-aware because it is the ordinary Astralbase exact-identity
calibration. It cannot begin until a committed and independently audited Gate
S GO. Both gates remain calibration. Neither is paper evidence.

The mathematical domain is still `bounded_structural_game_form` under
`component_depth2_local_move_game_v0`, with
`thermograph_structural_tree_v1` identity and `board_syntax_only` legality.
This is structural-tree identity, not arbitrary CGT equivalence. The boards
are chess-derived formal objects, not certified reachable orthodox-chess
positions. No Stiller/Elkies exactness, agency, learned-discovery, or aesthetic
performance claim is tested here.

## Immutable target and holdout boundary

Gate C reuses exactly the six targets assigned to Wave 69 Stage A:

```text
target-sha256:052f4191fdcbb6fa45716b97cc85949f8c2287c75d532893084955ab7c666122
target-sha256:07de65c35e848be61c6f96872b1b20f3a101efa9b461750c502060842599e0c6
target-sha256:8ceee173bf9c9f8e498a058ba15e2d6e4d37ec3ce0b2b7caf8607ac63744ab5b
target-sha256:41bb336e2bee89d4bdf6b5b7a9d9e1c3c8e1fd27da111dbaecac18ae9e553d6a
target-sha256:73492503d817eb3406951fa9fbe127e8f362401b7d9d695163d7e0c4b1ecdc00
target-sha256:f1b5c956d7454a2a939ed8e3a780a7baca58b2b5cddd44313db6f79b2fc20256
```

The source of truth remains
`docs/discovery_targets/wave_69_target_registry.v0.1.json`, registry id
`registry-sha256:e7383432360d848b0fd2996a8d4b3c2bf85ebd1492c6e4fff596f7b3391fb4a5`.
The two bins from each of the three topology families are retained. There is
no target substitution, even if one target produces no match.

Wave 69 Stage B and Wave 70 are sealed throughout Wave 69-R. No proposal,
board pool, order commitment, verifier result, structural probe, tuning
artifact, or exploratory summary may be generated for their twelve targets.
The repository and execution-log audit must treat the existence of any such
artifact as an integrity failure.

## Constructive generator lock

The implementation commit I must freeze these identities before empirical
Gate S or Gate C suite output:

```text
name: partizan_candidate_pool_generator
version: 0.2.0
family: dfile_two_component_constructive_grammar_v2
config schema: partizan.candidate_generator.v0.2
operator: seeded_constructive_component_composition_v2
construction contract: partizan.dfile_two_component_constructive_grammar.v0.2
constructive catalog: partizan.dfile_two_component_constructive_catalog.v0.2
independent proof contract: bitmesh:conservative_legal_independence:v0
supply-audit contract: partizan.wave69r_structural_supply_audit.v0.1
PRNG: sha256_counter_prng_v1
FEN metadata: w - - 0 1 (fixed for every generated board)
maximum total attempts: 20 * requested_unique_rows
candidate state identity: clock-free FEN state
symmetry identity: clock-free file-reflection orbit
```

If implementation review changes any identity above, this draft and the wave
plan must be amended and revalidated before I. Once I exists, a change requires
a new generator version, seed domain, preregistration, and pools.

The constructive grammar must establish, by board construction rather than
verifier-result filtering:

1. a syntactically valid board under `board_syntax_only`;
2. the fixed wall `d1=P,d2=p,d3=P,d4=p,d5=P,d6=p,d7=P,d8=p`, frozen and
   non-capturable;
3. exactly two nonempty strict components under
   `bitmesh:conservative_legal_independence:v0`;
4. no legal move or capture by a component piece into the other component;
5. exactly one to five nonwall pieces per component, no e-file piece, and only
   `P/N/B/R/Q` color-relative source templates;
6. an on-board empty forward square for every active pawn, so no active pawn
   is annexed into the barrier;
7. for every nonpawn, a static source-family atom/cage proof that each
   wall-reaching geometric ray is friendly-wall terminated or occupied before
   the wall;
8. every conservative destination remains inside its origin free component
   and no wall pawn attacks an opposing active piece;
9. local component variation sufficient to produce unique clock-free states
   and reflection orbits.

All non-board FEN metadata is exactly `w - - 0 1` for every v0.2 board.
Astralbase's bounded evaluator ignores side-to-move, castling, en-passant, and
clocks while candidate-state and reflection-orbit identities include some of
that metadata. Varying it could therefore create distinct keys for semantically
duplicate evaluator inputs and is forbidden. Negative tests must reject `b`,
castling, en-passant, or clock variants of an otherwise identical board rather
than count them as independent support.

"Target-blind" has a narrow reproducible meaning: given an explicit seed and
the same non-target configuration, target specs and target outcomes are not
generator inputs and cannot alter the raw board stream. Gate C production
seeds are nevertheless derived from opaque target ids by this protocol, so
different targets will ordinarily receive different streams through their
different seeds. The claim is target-semantic- and outcome-blind generation,
not identity-invariant output across production targets.

The frozen depth-2 construction bound is at most 135 local moves per component:
`1 + B + B^2 <= 18,361` recursive nodes per component and at most 36,722 total,
strictly below the 100,000-node candidate budget. This arithmetic is a
construction bound, not permission for Gate S to invoke Astralbase or
Thermograph.

The generator may reject a partially constructed board only for rules fully
specified in its frozen configuration: syntax, its own construction
invariants, duplicate candidate identity, duplicate reflection orbit, or the
single total attempt cap. It cannot call Bitmesh, Astralbase, Thermograph, or
any evaluator during generation. In particular, it cannot generate broadly
and retain only boards that a verifier accepts.

The generator emits only the seven already preregistered proposal features:
`piece_count`, `white_piece_count`, `black_piece_count`, `pawn_count`,
`non_pawn_piece_count`, `occupied_file_count`, and
`has_locked_d_file_backbone`. No Bitmesh certificate, construction proof,
target comparison, structural identity, outcome, rejection, or prevalence
field enters the ranker-visible proposal projection.

Gate C retains candidate proposal schema v0.1 but requires generation receipt
`partizan.candidate_generation_receipt.v0.2` and candidate pool manifest
`partizan.candidate_pool_manifest.v0.3`. Both new contracts bind generator
0.2.0, its configuration digest, code commit, seed, two raw process hashes,
canonical proposal bytes, repository-relative receipt, construction contract
`partizan.dfile_two_component_constructive_grammar.v0.2`, and the exact
constructive-catalog identifier
`partizan.dfile_two_component_constructive_catalog.v0.2` and content digest.
Receipt v0.2 and manifest v0.3 also bind all four source-repository commits and
validation requires those repositories to be clean at the exact pinned heads.
Receipt v0.1 and pool
manifest v0.2 remain accepted only for immutable Wave 69 replay; they cannot
authorize a Wave 69-R artifact. These schemas and migration/legacy tests must
be included at I and cannot change after Gate S output.

## Gate S: target-free structural-supply audit

Gate S contains four independently seeded shards of 1,024 boards, for exactly
4,096 audit rows. A shard seed is the unsigned first 64 bits, big-endian, of:

```text
SHA256("partizan/w69r/supply/v1\0" || ascii_decimal(shard_index))
```

where `shard_index` is exactly `0`, `1`, `2`, or `3`, without padding. The seed
domain, shard ordering, board count, generator configuration, construction
contract, attempt policy, serialization, receipt format, and four clean source
commits are fixed at I.

Gate S uses target-free `partizan.candidate_board_stream.v0.1`, not candidate
proposal v0.1, because that proposal contract contains a target id. Each board
row may contain only:

- schema and row identity;
- ordinal (the enclosing shard manifest supplies the shard binding);
- FEN board state and its clock-free candidate and reflection identities;
- generator identity, configuration digest, code commit, and seed;
- the same seven pre-verification board features used by the pure Gate C
  proposal projection;
- a non-ranker construction certificate under the frozen theorem contract.

The normative `partizan.wave69r_structural_supply_audit.v0.1` checker input is
a strict projection of those fields. A requested target, target identity,
target value, target family,
source-row provenance, candidate rank, label, or prior outcome is forbidden.
The checker output may contain only the bound board id, Bitmesh version and
commit, the conservative-independence certificate or first typed failure code,
the four structural predicates, and internal-error state. Each predicate is
tri-state: `pass`, `fail`, or `not_evaluated`. Because the pinned Bitmesh API
stops at its first typed failure, the mapped failing predicate is `fail`, any
already established predicates are `pass`, and later predicates are
`not_evaluated`. Every pinned error variant has a frozen exhaustive mapping;
an unknown variant is an internal error and Gate S NO-GO. Schema validation
must reject
unknown fields, including Astralbase evaluation, Thermograph identity or tree,
actual value class, target match, expanded nodes, baseline score, and learned
feature fields.

The authoritative Gate S implementation is the isolated Rust crate and binary
at `engine/gate_s_checker/src/main.rs`, with a narrow orchestration wrapper in
`scripts/wave69r_structural_supply.py` backed by
`python/partizan/gate_s.py`. It validates a six-field FEN
envelope, extracts only its board-placement field, and parses that field with
`shakmaty::Board::from_str`. It must not convert the input into a standard
`Chess` position; the research domain intentionally includes kingless formal
boards. It then calls the pinned Bitmesh conservative legal-independence proof
API and requires proof kind `bitmesh:conservative_legal_independence:v0`.

The Rust input and output contracts deny unknown fields and reject any target,
value, evaluator, rank, or label field before proof execution. The weaker
`analyze_subsystems` or `find_subsystems` observations are not Gate S evidence.
An Astralbase dummy target, Astralbase structural acceptance, or a Thermograph
call is also forbidden; none may substitute for the board-only Bitmesh proof.
This is an audited code and dependency-surface restriction, not a claim of
information-theoretic incapability.

Every shard is generated twice in separate Python processes. Both raw hashes
must equal the canonical artifact hash. Across all shards, candidate-state and
file-reflection-orbit identities must each be unique. The exact input inventory
and every receipt are committed before the first independent checker call.

Gate S GO requires all of the following without rounding:

- exactly 4,096 unique frozen input boards;
- byte-identical double generation for every shard;
- 4,096/4,096 independent Bitmesh
  `conservative_legal_independence` certifications;
- 4,096/4,096 frozen-barrier predicate passes;
- 4,096/4,096 non-capturable-barrier predicate passes;
- 4,096/4,096 strict-exactly-two-component predicate passes;
- 4,096/4,096 no-cross-component-entry predicate passes;
- zero generator-certificate/Bitmesh disagreements;
- zero internal checker errors;
- complete deterministic replay with all hashes and commits matching.

One failure is Gate S NO-GO. Failed rows remain in the ledger. There is no
retry, row replacement, favorable-shard selection, or relaxation to a
percentage threshold. A repair requires a new generator version, new seed
domain, new preregistration, and a new audit. Gate C artifacts remain absent.

Gate S reveals structural feasibility only. Its GO does not imply an exact
target realization, useful target support, discovery efficiency, or a learned
model result.

## Gate C: repaired six-target calibration

Only after the Gate S evidence commit records GO may Gate C proposal bytes be
generated. For each of the six immutable target ids, the seed is the unsigned
first 64 bits, big-endian, of:

```text
SHA256("partizan/w69r/calibration/v1\0" || target_id_utf8)
```

Each target receives the first 1,024 unique candidate states and unique
file-reflection orbits in generator order within the one total attempt cap of
20,480 attempts. Failure to fill one pool stops before any Astralbase call;
rows are not borrowed, padded, or regenerated under an uncommitted seed.

Each pool is generated twice in separate Python processes and must be
byte-identical. The target spec, generator configuration, proposals, receipt,
pool manifest, raw board stream, construction-certificate sidecar, source
commits, and policy orders are frozen and hashed before
the first target-aware verifier result. For every repaired pool, the 1,000
deterministic random permutations and fixed structural heuristic are freshly
computed and bound to those new proposal bytes under the unchanged Wave 69
algorithms. Old Wave 69 ordering-commitment bytes are not reusable because they
bind different proposals and pools. The new complete ordering commitments must
predate results. The algorithms cannot be reweighted using the Wave 69 NO-GO
or Gate S ledger. Random replicate `r` uses the unsigned first 64 bits of:

```text
SHA256("partizan/w69r/random/v1\0" || pool_id_utf8 || "\0" || ascii_decimal(r))
```

for `r=0..999`, with versioned SplitMix64 and rejection-sampled Fisher--Yates.
The fixed heuristic formula, candidate-key tie break, call budgets, metrics,
and estimator definitions remain exactly those frozen for Wave 69.

The raw generator board stream and its construction-certificate sidecar are
preserved in P_c. Target binding is a pure projection into proposal v0.1.
Receipt v0.2 and pool manifest v0.3 bind the raw row id and hash, sidecar
certificate id and hash, proposal id and hash, construction contract, and
constructive-catalog digest. The ranker projection still excludes construction
certificates and all verifier evidence.

Astralbase then verifies all 6,144 rows once in generator order. Every
verified match, verified nonmatch, structural rejection, duplicate
realization, and internal error consumes one call and remains in the complete
ledger. Baseline reports are computed only after the verifier pass by joining
precommitted orders to that ledger. There is no adaptive querying, early
stopping, retry, row deletion, or target replacement.

For each target, Gate C requires:

- exactly 1,024 unique frozen proposals and 1,024 result rows;
- certified coverage
  `(verified_match + verified_nonmatch) / 1024 >= 0.95`;
- at least eight certified exact matches;
- at least four distinct exact-match `position.symmetry_sha256` values;
- zero internal errors;
- exact deterministic replay of all requests, responses, certificates,
  identities, reports, and repository provenance.

Every target must pass every condition. There is no macro averaging across a
failed target and no substitution.

## Preregistered transition after Gate C

The independent audit records exactly one of these decisions:

1. **Integrity NO-GO.** A hash, receipt, temporal, capability, replay,
   completeness, or forbidden-access condition fails. No scientific
   interpretation is made until a new versioned protocol is run.
2. **Construction/coverage NO-GO.** Integrity passes, but any target has less
   than 95% certified coverage or an internal error. The constructive grammar
   or execution boundary remains the bottleneck. Stage B stays closed.
3. **Semantic-supply NO-GO.** Integrity passes and all six targets meet the
   coverage and zero-error gates, but any target has fewer than eight exact
   matches or four symmetry-unique matches. The structural repair succeeded;
   the remaining bottleneck is target-conditioned semantic proposal supply.
   The same calibration rows cannot be used to tune and then re-evaluate a
   replacement generator. A new preregistration, generator/seed version, and
   calibration boundary are required. Stage B stays closed.
4. **Calibration GO.** Every target passes coverage, exact support, unique
   support, error, and integrity gates. This authorizes planning—not running—a
   separately frozen Stage B baseline experiment. It does not convert Gate C
   into paper evidence and does not open Wave 70.

In particular, coverage GO with exact-support failure is useful: it shows that
the theorem-preserving composer fixed the observed Wave 69 structural failure
while failing to reach target identities often enough. The next technical
work would be a target-conditioned, outcome-blind semantic composer or target
representation, not hidden verifier filtering.

## Temporal provenance and clean-commit workflow

Wave 69-R uses two explicit pre-result/evidence pairs rooted at one immutable
implementation commit I.

At I, the three external repositories are pinned exactly to Astralbase
`1434fca1fc04d97798ec1b820c56f52f8014ccc7`, Bitmesh
`ade3417a007b9c8392d8a153abc4b3ed23edf0aa`, and Thermograph
`1d9b6b01c3921aca8c2a8fb13972fee8a4de5041`. Partizan I must be a direct child
of `6ddd22af4adb7ff8f6f4c361a9132720a47e87b7`. Generation and execution stop
if any repository is dirty or differs from these committed boundaries.

### Gate S chain

1. **I (implementation):** commit this preregistration, the wave plan,
   constructive grammar, construction contract, target-free supply schemas,
   structure-only checker interface, orchestration, and tests. I contains no
   empirical Wave 69-R output. An explicit `w69r_commit_implementation` gate
   creates I only after implementation red-team GO, records the exact reviewed
   inventory, and then rechecks clean Partizan, Astralbase, Bitmesh, and
   Thermograph commits before any empirical Gate S or Gate C suite byte.
2. At clean detached I with all four repositories clean, generate the four
   target-free supply shards twice. Add only the complete frozen supply inputs
   and receipts to create **P_s (supply pre-result)**.
3. Return to a clean detached worktree at I, materialize the exact inputs from
   P_s without changing I's recorded source provenance, and run only the
   structure-only Bitmesh checker.
4. Commit the complete structure-only ledger, independent replay, and Gate S
   decision as **E_s (supply evidence)**, a descendant of P_s. E_s records I
   and P_s by full commit and content hash.

### Gate C chain

5. Only if E_s records GO, use clean detached I to generate the six target
   calibration pools twice and freeze all receipts, manifests, and baseline
   order commitments. Add those complete inputs after E_s to create
   **P_c (calibration pre-result)**. P_c binds I, P_s, and E_s.
6. In a clean detached worktree at I, materialize the exact P_c inputs, run
   Astralbase once per row, and copy the complete ledgers back without changing
   I or P_c.
7. Commit result ledgers, derived reports, independent replay, and the Gate C
   decision as **E_c (calibration evidence)**. E_c binds I, P_s, E_s, and P_c.

The corresponding graph is:

```text
Git ancestry: I -> P_s -> E_s -> P_c -> E_c
Gate S execution annotation: P_s -> detached-I structure-only run -> E_s
Gate C execution annotation: P_c -> detached-I target run -> E_c
```

The arrows through detached I describe execution provenance, not Git ancestry.
The manifests and reports record both ancestry and execution commits. Result
bytes are never backfilled into I or a pre-result commit. Reproduction starts
from I, materializes the relevant P bytes, reruns the pinned checker, and
compares complete ledgers to E.

## Adaptation and leakage prohibitions

The following require a new preregistration and cannot be done inside Wave
69-R after the corresponding input lock:

- change the construction grammar, material alphabet, regions, barrier,
  attempt cap, PRNG, serialization, seed, feature derivation, or deduplication;
- use any Gate S checker response to filter, reorder, or regenerate a Gate S
  row;
- create Gate C pools before committed Gate S GO;
- change Gate C generation or ranking after seeing any Gate C result;
- omit an error, rejection, duplicate realization, target, or failed gate;
- probe a Stage B or Wave 70 target in any generator, structural checker,
  verifier, baseline, model, or exploratory notebook;
- promote a calibration metric to paper evidence.

Pre-I implementation tests and hand-constructed adversarial fixtures may
generate synthetic bytes and exercise the four known structural failure
classes. They must use explicitly non-empirical test seed domains, synthetic
boards, and synthetic target fixtures under declared contracts. They cannot
use either locked seed domain (`partizan/w69r/supply/v1` or
`partizan/w69r/calibration/v1`), any of the 18 Wave 69 registry target specs,
any empirical output path, or any prior result. Synthetic fixture bytes are
test artifacts, not Gate S/Gate C inputs or evidence.

## Learned ranking remains NO-GO

Wave 69-R does not train or evaluate a model. The current
`target.ranker_view` exposes an opaque structural SHA-256 plus generic rule
metadata. That is not an adequate semantic target representation and creates
a target-id memorization channel.

Before any learned ranker or Wave 70 proposal pool, a separate versioned
contract must expose a canonical semantic representation—such as approved
recursive structural serialization or invariant structural features—computed
before candidate generation. It must exclude opaque source identity as model
signal, source-row provenance, split assignment, target prevalence, candidate
outcomes, certificates, and all result-derived statistics. A verifier red
team must demonstrate that changing an opaque id alone cannot change the
semantic input and that structurally different targets do produce different
inputs.

Gate C GO does not waive this condition. Wave 70 remains untouched and NO-GO
until the semantic target-view contract, model code and weights, proposal
generator, baselines, analysis, source commits, and complete orderings are
frozen under a future preregistration.

## Commands at pre-I implementation status

The implementation and its synthetic tests are runnable now:

```bash
python3 agents/network.py validate
python3 agents/network.py validate-wave agents/waves/wave_69r_proof_carrying_generator_repair.json
python3 scripts/validate_waves.py
python3 -m unittest tests.test_discovery_candidate_pool_v2 tests.test_discovery_wave69r_lineage_contracts
python3 -m unittest tests.test_wave69r_supply_freeze tests.test_wave69r_structural_supply tests.test_wave69r_gate_c_suite tests.test_wave69r_gate_c_evidence
cargo --config 'patch."crates-io".bitmesh.path="../bitmesh"' test --manifest-path engine/gate_s_checker/Cargo.toml --locked --offline
git diff --check
```

The production supply-freeze, structure-only execution, calibration-freeze,
and Astralbase execution commands are implemented but remain forbidden until
their required immutable ancestors exist. This preregistration does not claim
that any empirical gate has run or passed.
