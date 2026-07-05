# Verification Gates

Status: Wave 46 signature replay-preflight gates, with Wave 3 negative
controls and Wave 22/27 composition replay and leakage gates retained.

The fixture at `agents/fixtures/wave_03_negative_controls.jsonl` is not a
training shard. It intentionally mixes rows that the current schema validator
must reject with schema-valid `rejected` rows that future domain and
decomposition checkers must keep out of exact training.

## Gate Summary

Wave 3 uses negative controls to keep the claim ledger conservative:

- Mixed payloads, missing exact provenance, and rejected rows without reasons
  address the reviewer risk that placeholder, prediction, or heuristic output
  could be mistaken for verified exact labels.
- Castling, en-passant, and undeclared generalized-board rows address the risk
  that the first constrained domain silently expands beyond the stated shard.
- Weak and unchecked decomposition rows address the risk that decomposition
  claims rest on ad hoc splits instead of strict, machine-checkable
  certificates.
- The exact-training split policy addresses the risk that rejected rows inflate
  exact-value support or make the `exact.value_class` baseline look meaningful.

## Gate Responsibilities

- `label_schema`: `agents/label_schema.py validate`; catches malformed or
  ambiguous JSONL rows before any training or evaluation loader reads them.
- `domain_gate`: future executable domain checker; rejects inputs outside
  `formal_domain:first_constrained_chess:v0`.
- `decomposition_certificate_gate`: future bitmesh/astralbase checker; accepts
  exact decomposition only with a strict, validated independence certificate.
- `composition_certificate_gate`: future bitmesh/astralbase/partizan checker;
  accepts exact composed rows only when component roots, component value
  digests, decomposition digest, and composed result digest validate together.
- `exact_training_split_gate`: future dataset loader policy; trains exact
  targets only from schema-valid rows with `label_kind: exact`,
  `exact.status: verified`, complete provenance, and accepted domain and
  decomposition/composition checks.

## Wave 3 Negative Controls

| Row ID | Control | Intended Gate | Expected Rejection Or Exclusion Reason |
| --- | --- | --- | --- |
| `w3-neg-mixed-exact-prediction-001` | Exact and prediction payloads appear in one row. | `label_schema` | A row must contain exactly one label payload object; exact verifier labels and model predictions cannot be mixed. |
| `w3-neg-mixed-rejected-heuristic-001` | Rejected and heuristic payloads appear in one row. | `label_schema` | A row must contain exactly one label payload object; rejected status and heuristic estimates cannot be mixed. |
| `w3-neg-exact-missing-provenance-001` | Exact row omits provenance. | `label_schema` | Exact rows require provenance with generator, verifier, domain definition, seed, config hash, and certificate. |
| `w3-neg-rejected-missing-reasons-001` | Rejected row has no reasons. | `label_schema` | Rejected rows require `rejected.reasons` as a non-empty list of strings. |
| `w3-neg-castling-rights-001` | FEN contains castling rights. | `domain_gate` | The first constrained exact domain allows no castling rights; the row is schema-valid only as `rejected.status: unsupported`. |
| `w3-neg-en-passant-target-001` | FEN contains an en-passant target square. | `domain_gate` | The first constrained exact domain allows no en-passant target; the row is schema-valid only as `rejected.status: unsupported`. |
| `w3-neg-weak-decomposition-001` | Locked-pawn structure is only weakly decomposed. | `decomposition_certificate_gate` | Weak decomposition lacks a strict independence certificate and is excluded from exact labels. |
| `w3-neg-unchecked-decomposition-exact-001` | Exact row carries top-level decomposition components and an unchecked certificate. | `label_schema`, then `decomposition_certificate_gate` | Top-level `components` is ambiguous under the label schema; even if normalized later, unchecked decomposition cannot support an exact label. |
| `w3-neg-generalized-board-undeclared-001` | Generalized-board encoding is used under the standard first constrained domain. | `domain_gate` | Generalized boards require a separately declared shard; standard `first_constrained_chess:v0` accepts only standard 8x8 FEN. |

## Exact Training Policy

No row in `wave_03_negative_controls.jsonl` is eligible as exact training data:

- Schema-invalid rows fail before training split construction.
- Unsupported domain rows are represented as `label_kind: rejected`.
- Weak or unchecked decomposition rows are represented as `label_kind:
  rejected` or are schema-invalid.
- Future loaders should treat this fixture as a negative-control artifact, not
  as a source shard, even when individual rejected rows are schema-valid.

For the current vertical slice, the same policy applies to
`/private/tmp/partizan-wave-03.jsonl`: only its three `label_kind: exact` rows
are eligible for exact supervision. Two exact rows currently have
`exact.value_class: number`; one formal CGT row has `exact.value_class: switch`
and `position.encoding: cgt_canonical`. The exact-vs-rejected FEN gate excludes
that formal row by encoding, while the value-class baseline includes it and
records the minority-class miss. The two schema-valid `rejected` rows are
evidence for gate accounting only.

For the Wave 6 frontier shard at `/private/tmp/partizan-frontier-wave-06.jsonl`,
only the 200 `label_kind: exact` rows are eligible for exact supervision. The
800 `label_kind: rejected` rows are retained as no-strict-decomposition controls
and must not enter exact targets. The manifest records zero duplicate row IDs,
zero duplicate positions, and zero duplicate exact certificate digests; any
future split builder must preserve those leakage checks and add generator-family
and symmetry-normalized split reports before OOD claims are active. The
`docs/frontier_wave_06_split_report.json` is a deterministic position-key split
report only: it verifies no position or exact certificate crosses train/dev/test,
but exposes 70 D4 symmetry-key cross-split violations. The
`docs/frontier_wave_06_symmetry_split_report.json` report uses D4-canonical FEN
keys for supported rows and has zero symmetry-key cross-split violations.

Wave 7 extends this policy to
`/private/tmp/partizan-family-frontier-wave-07.jsonl`: only the 400 exact rows
are eligible for exact supervision, while 1600 rejected rows remain boundary
controls. `docs/family_frontier_wave_07_split_report.json` verifies zero
position-key and exact-certificate cross-split violations across KQK and KRK
families, but exposes 137 D4 symmetry-key cross-split violations and is not a
family-held-out OOD split because both families appear in every split.
`docs/family_frontier_wave_07_symmetry_split_report.json` removes the symmetry
leakage for IID-style split evaluation, but still contains both families in all
splits.

Wave 8 adds `docs/family_frontier_wave_07_holdout_krk_report.json`, which holds
all KRK rows in `test` and keeps KQK rows in `train`/`dev`. This is the first
generator-family OOD split artifact, but its KQK train/dev side has 38 D4
symmetry-key cross-split violations.

Wave 9 adds `docs/family_frontier_wave_07_holdout_krk_symmetry_report.json`,
which holds all KRK rows in `test` and splits KQK train/dev by D4-canonical FEN
key. It has zero position-key, symmetry-key, and exact-certificate cross-split
violations. This is the current evaluation-ready OOD split artifact.

Wave 10 adds
`docs/family_frontier_wave_07_holdout_krk_symmetry_baseline_report.json`, which
scores `fen_string_material_gate_v0` on the Wave 9 split. The fixed baseline
gets train/dev/test accuracy 0.198/0.215/0.200 and zero rejected recall because
it predicts every row as `exact`. Future learned OOD claims must report against
this same symmetry-safe split and beat this fixed floor.

Wave 11 adds
`docs/family_frontier_wave_07_holdout_krk_symmetry_geometry_probe_report.json`,
which trains `fen_geometry_logistic_probe_v0` on KQK train rows and evaluates
on held-out KRK test rows. It gets train/dev/test accuracy 0.942/0.935/0.928
and KRK rejected recall 0.91. Future structured or neural claims must report
against this same symmetry-safe split and beat this hand-feature probe, not only
the fixed floor.

Wave 12 adds `/private/tmp/partizan-expanded-family-frontier-wave-12.jsonl`,
generated from KQK, KRK, KBK, and KNK families at 1000 rows per family. It has
4000 rows total, 800 exact rows, 3200 rejected controls, zero duplicate row IDs,
zero duplicate positions, and zero duplicate exact certificate digests.
`docs/expanded_family_frontier_wave_12_split_report.json` is a position-hash
audit and exposes 269 D4 symmetry-key cross-split violations.

Wave 13 adds
`docs/expanded_family_frontier_wave_12_symmetry_split_report.json` and
`docs/expanded_family_frontier_wave_12_holdout_knk_symmetry_report.json`. The
symmetry split and KNK-family holdout both have zero position-key,
symmetry-key, and exact-certificate cross-split violations. The KNK holdout puts
all KNK rows in `test` and keeps KQK/KRK/KBK in `train`/`dev`.

Wave 14 adds fixed and trainable baselines for the Wave 13 KNK holdout. The
fixed FEN gate gets 0.200 KNK-test accuracy. The hand geometry probe gets 1.000
KNK-test accuracy, which means future research claims must move beyond this
terminal-frontier exact-vs-rejected boundary or beat this probe on a harder
symmetry-safe split.

Wave 15 adds
`docs/expanded_family_frontier_wave_12_holdout_krk_frontier_mean_report.json`,
an exact-only report for `exact.value.frontier_mean` with KRK held out. Rejected
rows are excluded from the target. The train-majority floor predicts
`frontier_mean=1`, scores 1.000 on train/dev, and drops to 0.220 on KRK test
because KRK exact rows include 156 `frontier_mean=2` cases. The report must flag
`2` under `target_support_coverage.unseen_labels_by_split.test`. Frontier
temperature is still constant on this shard, so this gate is a first
option-structure audit, not a temperature-learning result.

Wave 16 hard-target work cannot activate new agency, temperature, or aesthetic
claims unless all of these conditions hold:

- A strict composition certificate or non-number exact target has a
  machine-checkable verifier path and stable digest.
- The OOD split is symmetry-safe and reports generator-family, composition,
  certificate, and target-support leakage.
- Fixed floors and hand probes are reported on the same split.
- The target is not solved by the current hand geometry probe, or the result is
  explicitly recorded as a baseline warning rather than a main claim.
- Nonconstant temperature claims require at least two certified temperature
  target labels in train and at least one OOD split.

Wave 17 starts the executable composition-certificate integration plan in
`agents/waves/wave_17_composition_certificates.json`. The current bitmesh
BMCOMPOSE v1 certificate binds a strict decomposition digest, component
`component_root -> value_digest` entries, and a result value digest into a
stable payload. It is not yet a full value verifier. Wave 17 gates therefore
require astralbase and partizan to add root coverage, verified thermograph value
payloads, composition-result verification, nested schema validation, and
composition-certificate leakage reports before any decomposition-benefit claim
can activate.

The first Wave 17 fixture shard at
`/private/tmp/partizan-composition-hard-target-wave-17.jsonl` is eligible only
as a composition-certificate plumbing gate. It has 16 exact rows under the
declared `formal_domain:bitmesh_composition_fixture:v0` fixture domain and 5
rejected controls for weak decomposition, a missing component value digest, a
stale composition digest, a duplicate component root, and unsupported value
composition. Exact fixture rows may enter only fixture-scoped exact tests; they
must not be counted as legal chess value evidence or as decomposition-benefit
evidence. The companion report
`docs/composition_hard_target_wave_17_symmetry_split_report.json` must preserve
zero cross-split leakage for position, symmetry key, exact certificate,
decomposition digest, composition digest, qualified component roots
(`decomposition_digest:component_root`), component value digests, qualified
component/value pairs, and result value digest before any larger composition
shard can be used for model evaluation.

Wave 17 composition holdout reports add exact-only split gates for
`component_count`, `composition_digest`, and `result_value_digest`. The
component-count gate currently holds out `component_count=3` exact rows, while
the digest gates each hold out one exact fixture row. Rejected rows with matching
metadata must stay in train/dev accounting rather than becoming exact test
targets, and all holdout reports must preserve zero cross-split leakage for the
same position, symmetry, certificate, decomposition, composition, qualified
component, component-value, and result-value identities before decomposition
baselines can be reported.

The first Wave 17 composition baseline report is a fixture sanity gate. It must
exclude rejected rows from exact target metrics, report train-majority and
FEN/material controls on the same component-count holdout, and mark
`fixture_component_sum` as fixture-only. A perfect fixture-component-sum score
cannot activate a decomposition-benefit claim because the fixture target is
defined as that integer sum.

Wave 19 adds an Astralbase replay gate for non-fixture composed-board rows:
`cargo run --quiet -- --replay-non-fixture-composed-domain-shard <jsonl>`.
For each exact row in `formal_domain:bitmesh_composed_board_material:v0`, the
gate reparses the serialized board, recomputes the BitMesh conservative
legal-independence proof, recomputes component CGT values under the declared
composition rule, rebuilds BMCOMPOSE, and compares every recomputable exact
value and nested certificate field. This is stricter than Partizan schema or
report validation, but it is still a replay of the declared finite rule, not a
learned-model result or a broad chess-value proof.

Wave 22 applies the same replay gate to
`/tmp/astralbase-w22-expanded-composition.jsonl`, generated by
`cargo run --quiet -- --expanded-non-fixture-composed-domain-shard --rows-per-family 10`.
The expanded shard has 44 rows, of which 41 exact rows replay successfully and
3 rejected controls are skipped. It is eligible as a replay-valid scale
artifact because schema validation and Astralbase replay both pass.

Wave 22 is not eligible as a leakage-clean OOD evaluation shard. The expanded
generator deliberately permits generated component-value reuse to reach 10
rows per generated depth-two topology family. Partizan topology and
generated-source reports must therefore be read as leakage audits: the topology
report records family leakage failures, and the generated-source holdout reports
duplicate decomposition/component identities plus cross-split decomposition and
component-root leakage. Future training or model claims must either regenerate
with no generated component/decomposition identity reuse or use a group-aware
split that keeps reused identities inside a single split before reporting
decomposition-benefit evidence.

Wave 27 adds a separate leakage-clean composition command:
`cargo run --quiet -- --leakage-clean-non-fixture-composed-domain-shard --rows-per-family 10`.
The resulting shard is smaller than Wave 22 but evaluation-clean under current
Partizan gates: 21 rows total, 18 exact rows replayed, 3 rejected controls
skipped, and 7 profiled generated exact rows. The topology benchmark,
generated-source holdout, and generated-source baseline reports all pass
`--fail-on-leakage`, with zero duplicate decomposition digests, component
identities, component value digests, component value pairs, composition digests,
positions, symmetry keys, certificates, and result digests. Future model work
may use this as the first leakage-clean non-fixture composition split, but must
state its small generated support and compare against deterministic floors on
the exact same split.

Before any generated composition shard is treated as evaluation data,
Astralbase must run
`cargo run --quiet -- --generated-depth-two-profile-search --rows-per-family <n>`
and the expanded artifact must pass both schema validation and replay. That
profile-search audit must report target support, selected row count,
topology/source counts, and the reuse constraints used for component and result
digests.

Wave 31 upgrades the profile-search audit with candidate-pair counts and
rejection reasons. At Astralbase commit
`46f6607d6003c7d74f11aacb4584f57f69d053e1`, the 10-per-family clean target
still selects only 7 generated rows from 14 left profiles and 13 right profiles.
The report records 182 candidate pairs per generated topology family and 539
`component_value_digest_reuse_before_materialization` rejections. Future scale
waves must increase fresh component-value profile supply under the no-reuse
rule, or explicitly document a new split/grouping rule before claiming useful
clean support.

Wave 32 tested one bounded supply expansion using rank-3/rank-6 supplemental
profile-source groups, then reverted it after measurement. The experiment still
selected only 7 generated rows and increased component-value reuse rejections to
616, with 7 materialization failures. Repeating this variant is not a scale
strategy; the next generator change must introduce genuinely new
component-value diversity or document a different evaluation split rule.

Wave 33 adds a profile-inventory command:
`cargo run --quiet -- --generated-depth-two-profile-inventory`. The current
inventory shows white profile generation collapses from 526 patterns to 129
wall-safe patterns and 14 accepted profiles, while black collapses from 527
patterns to 365 wall-safe patterns and 13 accepted profiles. Future
profile-source changes must report which loss modes they improve:
`wall_safety`, `component_recursive_node_budget`, `materialization_failure`, or
`duplicate_value_digest`.

Wave 34 adds a depth-three profile-inventory command:
`cargo run --quiet -- --generated-depth-three-profile-inventory`. It is a
diagnostic no-go, not a promoted shard path. The current report keeps the same
526/527 generated patterns and wall-safety filters but accepts only 6 white
profiles and 4 black profiles under the existing recursive-node budget.
Component recursive-node budget rejections rise to 91 on white and 337 on
black, so increasing local-move depth under the same budget is not a valid
clean-scale strategy. Future attempts that use deeper component values must
state a versioned value rule, a new budget, or a split/grouping rule before
claiming useful generated support.

Wave 35 adds edge/minor ladder source diagnostics:
`cargo run --quiet -- --generated-depth-two-profile-source-inventory` and
`cargo run --quiet -- --generated-depth-two-combined-source-profile-search --rows-per-family 10`.
The edge source alone still accepts only 14 white and 13 black profiles. The
corner-plus-edge union reaches 15 white and 14 black profiles but still selects
only 7 leakage-clean rows, with 616 component-value reuse rejections before
materialization and 7 materialization failures. Future supply work should not
repeat edge-ladder or simple square-shift variants unless it demonstrates lower
component-value reuse pressure or materially higher selected clean support.

Wave 36 adds a duplicate-cluster diagnostic:
`cargo run --quiet -- --generated-depth-two-duplicate-clusters`. It groups
budget-safe corner-plus-edge profiles by depth-two value digest and reports
bounded material/local-move signatures for the largest duplicate clusters. The
current report shows 254 white budget-safe profiles collapsing to 15 value
digests and 517 black budget-safe profiles collapsing to 14 value digests. The
largest duplicate clusters contain multiple distinct mobility signatures, so a
future richer target may be justified, but those signatures are not labels until
a versioned value rule, replay semantics, split rules, and baselines are
defined.

Wave 37 adds a signature-profile support diagnostic:
`cargo run --quiet -- --generated-depth-two-signature-profile-search --rows-per-family 10`.
It uses the diagnostic signature rule
`depth2_value_digest_plus_material_balance_plus_local_move_counts_v0`, combining
component value digest, material balance, and local move counts. The current
report reaches 30 selected diagnostic rows, balanced 10/10/10 across local-move,
asymmetric-fan, and pawn-phalanx topology families, from 90 left and 92 right
signature profiles. This is not a promoted shard and not exact-value evidence.
Future use must define a versioned value rule, replay-compatible provenance,
split semantics, deterministic floors, and model baselines before any
signature-derived target can enter supervision or evaluation claims.

Wave 38 adds an executable contract gate:
`python3 engine/ml_model.py signature-profile-contract-report docs/non_fixture_composition_signature_profile_search_wave_37_report.json --rows-per-family-target 10 --fail-on-support-gate`.
The gate validates that Wave 37 has 30 selected diagnostic rows, 10 per
generated topology family, zero duplicate component signatures, and zero
duplicate result signature keys. It also records `promotion_gate.passed=false`
with four blockers: no versioned exact value rule, no replay-compatible
provenance, no split/leakage semantics, and no deterministic/model baselines.
Any future signature-derived target must clear those blockers before it is
eligible for exact supervision or OOD model evaluation.

Wave 39 adds a diagnostic heuristic shard:
`cargo run --quiet --manifest-path /Users/devinnicholson/astralbase/Cargo.toml -- --signature-target-diagnostic-shard --rows-per-family 10`.
The shard has 30 rows with `label_kind=heuristic`, zero exact rows,
`target_status=diagnostic_only`, and `supervision_eligible=false`. Partizan
schema validation passes, and the split report has train/dev/test counts 25/3/2
with zero duplicate or cross-split leakage violations. These rows may be used
for audit, visualization, and future contract development only; exact target
metrics and learned exact-label claims must exclude them.

Wave 40 adds a deterministic heuristic-target floor:
`python3 engine/ml_model.py heuristic-target-report docs/signature_target_diagnostic_wave_39.jsonl --target-field result_signature_key --heuristic-method signature_profile_target_diagnostic --output docs/signature_target_diagnostic_wave_40_baseline_report.json`.
The report targets only `heuristic.outputs.result_signature_key` on
`label_kind=heuristic` rows, includes all 30 rows, and preserves the Wave 39
25/3/2 train/dev/test split. The train-majority floor scores 0.04 on train and
0.0 on dev/test because all dev/test target labels are unseen relative to
train. Future diagnostic-model experiments over the signature shard must report
against this floor, but exact metrics and learned exact-label claims must still
exclude these heuristic rows.

Wave 41 adds a projection inventory:
`python3 engine/ml_model.py heuristic-target-projection-report docs/signature_target_diagnostic_wave_39.jsonl --heuristic-method signature_profile_target_diagnostic --output docs/signature_target_projection_wave_41_report.json`.
The report screens 9 heuristic-only projections and records target cardinality,
train-majority accuracy, and unseen dev/test label counts for each. The only
projection with zero dev/test unseen labels is `component_topology_family`, a
3-label generator-family target with train/dev/test majority accuracy
0.36/0.0/0.5. Value-digest, material, mobility, and richer topology-joined
projections remain sparse with 23-30 labels and unseen dev/test labels. Future
signature-target work must either increase repeated support for an informative
projection or define a replayed exact value rule; it must not promote topology
classification as decomposition-value evidence.

Wave 42 adds a bounded higher-support diagnostic:
`cargo run --quiet --manifest-path /Users/devinnicholson/astralbase/Cargo.toml -- --generated-depth-two-signature-bounded-support --rows-per-family 20 --candidate-pair-limit 2500`.
The report records selected counts, candidate offsets, target-reached flags,
candidate-limit flags, and rejection counts while preserving the existing
unbounded rpf10 signature path. With the 2500-pair cap, the rpf20 diagnostic
selects only 35 rows: 12 asymmetric-fan, 12 local-move, and 11 pawn-phalanx.
All three topology families hit the candidate-pair cap and none reaches the
20-per-family target. Future scale reports must expose equivalent cap/offset
fields and must not describe bounded partial support as a promoted shard.

Wave 43 runs the bounded higher-support diagnostic at the full 8280 candidate
pairs per topology family:
`cargo run --quiet --manifest-path /Users/devinnicholson/astralbase/Cargo.toml -- --generated-depth-two-signature-bounded-support --rows-per-family 20 --candidate-pair-limit 8280`.
The report reaches the 20-per-family target with 60 selected rows and no
candidate-pair cap hits. Candidate offsets are 6299 asymmetric-fan, 6108
local-move, and 6316 pawn-phalanx. This proves support reachability for an
rpf20 diagnostic shard, but it is not yet a dataset: the next gate must
materialize the shard, run Partizan schema validation, split/leakage reporting,
target floors, and projection inventories before any model experiment can use
it.

Wave 44 materializes that rpf20 diagnostic shard:
`cargo run --quiet --manifest-path /Users/devinnicholson/astralbase/Cargo.toml -- --signature-target-diagnostic-shard --rows-per-family 20`.
The artifact `docs/signature_target_diagnostic_wave_44_rpf20.jsonl` has 60
schema-valid heuristic rows, balanced 20/20/20 across the three generated
topology families. The split report has train/dev/test counts 46/11/3 and zero
duplicate position, duplicate row-id, duplicate symmetry-position, position-key
cross-split, or symmetry-position-key cross-split violations. All rows must
remain `target_status=diagnostic_only` and `supervision_eligible=false`; exact
training loaders and exact-label model reports must exclude them.

Wave 44 also reruns deterministic target support gates. The full
`result_signature_key` target has 60 labels and scores 0.0217 train accuracy
and 0.0 dev/test accuracy under the train-majority floor because all dev/test
labels are unseen relative to train. The projection inventory keeps 9 candidate
projections visible: `component_topology_family` has zero dev/test unseen
labels but is only a 3-label topology target, while value-digest, material,
mobility, and joined projections remain sparse. Any future diagnostic-model
experiment over this shard must report the Wave 44 floor and projection
inventory on the same split, and any exact-value claim must first add
replay-compatible value-rule semantics.

Wave 45 adds the executable promotion-readiness gate:
`python3 engine/ml_model.py heuristic-signature-promotion-report docs/signature_target_diagnostic_wave_44_rpf20.jsonl --heuristic-method signature_profile_target_diagnostic --output docs/signature_target_promotion_wave_45_report.json --fail-on-row-contract`.
The gate separates `row_contract_gate` from `promotion_gate`. On the Wave 44
shard, `row_contract_gate.passed=true`: all 60 rows have the required diagnostic
output fields, the versioned contract ID, `target_status=diagnostic_only`,
`supervision_eligible=false`, parseable component signatures, and result
signature keys matching topology plus left/right component signatures. Duplicate
component signatures and duplicate result signature keys are both zero.

Wave 45 keeps promotion closed. `promotion_gate.passed=false`, and all 60 rows
retain all four blocker IDs: missing versioned exact value rule, missing
replay-compatible provenance, missing split semantics, and missing deterministic
and learned-model baselines. The report also records 17 duplicate
`current_result_value_digest` values. Future promotion work must not remove
those blockers or train exact models from these rows until an external replay
checker supplies exact target semantics and the promoted split/reporting rules
are regenerated.

Wave 46 adds that first Astralbase replay preflight:
`cargo run --quiet --manifest-path /Users/devinnicholson/astralbase/Cargo.toml -- --signature-target-replay-preflight docs/signature_target_diagnostic_wave_44_rpf20.jsonl`.
The report recomputes each Wave 44 heuristic row from its FEN board under the
depth-two local-move rule. It checks active pieces, left/right component value
digests, left/right component signatures, result signature key, current result
value digest, and recursive node totals. On the current 60-row shard, required
output field misses and contract-field mismatches are empty, replay failure
count is 0, replay check failures are empty, and every checked replay field
passes on all 60 rows.

Wave 46 still does not promote the target. The report status is
`replay_preflight_passed_promotion_blocked`, `promotion_gate_passed=false`, and
all four blocker IDs remain counted on all 60 rows. Future work must convert
this replay-preflighted diagnostic into a versioned exact value rule, regenerate
split semantics and deterministic floors for the promoted target, and only then
run learned models.

Wave 47 adds the promoted exact metadata shard:
`cargo run --quiet --manifest-path /Users/devinnicholson/astralbase/Cargo.toml -- --signature-target-exact-shard --rows-per-family 20`.
The generated shard must pass `python3 agents/label_schema.py validate`,
Astralbase non-fixture composed-domain replay, and
`python3 engine/ml_model.py validate-report docs/signature_target_exact_wave_47_split_report.json --fail-on-leakage`.
The current artifact has 13 exact rows and no heuristic rows. It is
self-value-unique: duplicate component value digests, duplicate result value
digests, component-value cross-split leakage, and result-value cross-split
leakage are all zero.

Wave 47 exact rows are verified depth-two local-move exact thermograph values.
The signature fields live under `exact.value` as metadata:
`signature_target_rule`, `component_signature_rule`, component signatures,
component value digests, and `result_signature_key`. They must not be treated
as a new `ExactValueClass`. Any model experiment over this shard must use the
Wave 47 split and report the `exact.value.result_signature_key` train-majority
floor: train/dev/test accuracy 0.0909/0.0/0.0, with one unseen label in dev and
one unseen label in test.

Wave 48 adds the support-collapse diagnostic:
`cargo run --quiet --manifest-path /Users/devinnicholson/astralbase/Cargo.toml -- --generated-depth-two-value-unique-signature-profile-search --rows-per-family 20`.
This report must remain separate from promoted exact shards. It runs the same
value-unique signature selector used by Wave 47 and records the current rpf20
limit: 90 left signature profiles, 92 right signature profiles, 8280 candidate
pairs per topology family, and only 13 selected rows. The dominant blocker is
`component_value_digest_reuse_before_materialization=18391`. Future exact
support claims must either increase `selected_row_count` under this report or
explicitly document a new value rule or split rule before changing the gate.

Wave 49 adds the matching component-value capacity upper-bound report:
`cargo run --quiet --manifest-path /Users/devinnicholson/astralbase/Cargo.toml -- --generated-depth-two-value-unique-signature-upper-bound --rows-per-family 20`.
The current source has 15 left and 14 right unique component value digests, zero
overlap, 29 combined unique component values, and a simple component-value
capacity upper bound of 14 rows against the 60-row target. The current selector
selects 13 rows. Future scale work should therefore add fresh component-value
diversity before spending effort on longer pair scans or greedy selector
tuning.

Wave 21 established syntactic target support for `--rows-per-family 10` at
Astralbase commit `ca6e9baa96cd6ae2ab34d302c1b95546542dc9ba` while keeping the
existing Wave 18 shard byte-identical. Wave 22 then added an explicit expanded
command and replayed the expanded artifact successfully. The active gate is now
useful clean support: Wave 27 avoids generated component/decomposition identity
reuse and passes leakage validation, but it currently supports only 7 generated
exact rows. Wave 31 identifies the immediate clean-support bottleneck as
component-value reuse pressure, not report validation. Wave 37 shows a richer
material/mobility signature can recover 30 diagnostic rows, and Wave 38 makes
that support machine-checkable. Wave 39 adds row-level heuristic diagnostics
and Wave 40 adds a deterministic heuristic floor while keeping promotion
closed. Wave 41 shows that simple projection choice does not solve informative
target support, and Wave 42 shows naive higher-support scaling hits a bounded
candidate-pair cap before reaching rpf20. Wave 43 shows rpf20 support is
reachable with a full-pair scan. Wave 44 materializes and audits the rpf20
heuristic shard. Wave 45 adds an executable row-contract/promotion-readiness
gate. Wave 46 adds field-by-field Astralbase replay preflight. Wave 47 converts
that target into a small leakage-clean exact metadata shard. Wave 48 measures
the exact support collapse and Wave 49 shows that the current component-value
capacity ceiling is 14 rows, so the active gate is fresh component-value supply
plus deterministic and learned baselines on a scaled exact split.
