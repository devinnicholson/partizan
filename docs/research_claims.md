# Research Claims

## v0.1 release-readiness claim register

This section maps the frozen downstream validation IDs. It supersedes any
stronger interpretation of the chronological Wave notes below.

| ID | v0.1 status | Evidence and boundary |
| --- | --- | --- |
| P01 | Locally verified | `data/research-v0.1/manifest.json`, `agents/label_schema.py`, and `scripts/verify_release.py` bind and validate a reproducible five-row slice plus the frozen 13-row Wave 47 slice. Cross-platform CI remains pending execution. |
| P02 | Locally verified for the frozen slice | All 13 rows bind decomposition, component values, composition, and result digests; `scripts/verify_release.py` also requires an intentionally corrupted certificate to fail. This is bounded-rule provenance, not a full-game theorem. |
| P03 | Partial | The five-row vertical slice and deterministic event bytes reproduce. Historical Wave 47 rows record `code_commit=workspace`, so immutable regeneration of that slice and any published benchmark metric remain blocked. |
| P04 | Negative/null; not a release claim | Waves 57–67 produced no decomposition-aware model that beat controls on both development and test. |
| P05 | Unvalidated; not a release claim | No technical evidence demonstrates chess temperature, learned agency, or model-guided discovery. Those terms may be used only as clearly marked artistic interpretation or future hypothesis. |

The release-supported statement is: “an experimental suite for structural
decomposition and combinatorial-game representations in constrained chess
positions.”

This table is the claim ledger. Evidence, baselines, and a falsification
condition activate each claim.

The current vertical slice provides concrete evidence only for reproducible
plumbing: a schema-v0 JSONL shard at `/private/tmp/partizan-wave-03.jsonl`,
SHA-256 `ef791885bbeb30f68ce1dc63d826fbb41b048c7741fe8953099278674d15a167`,
with 5 rows (3 exact, 2 rejected), plus deterministic loader and baseline
smokes. Two exact rows are chess `number` labels; one exact row is a formal CGT
`switch` fixture with positive temperature. This evidence does not support the
broader agency, decomposition, chess-temperature, discovery, or OOD-shift claims
yet.

Wave 6 adds scale evidence for the label factory only: a deterministic KQK
frontier shard at `/private/tmp/partizan-frontier-wave-06.jsonl`, SHA-256
`4863eea78d53adcd7eca22bfdda55c5b5eb668c46065f3ad49c019ae3bf60792`, with
1000 rows (200 exact immediate terminal-frontier rows, 800 rejected
no-strict-decomposition controls), zero duplicate row IDs, zero duplicate
positions, and zero duplicate exact certificate digests. The deterministic split
report assigns 816/91/93 rows to train/dev/test with zero position-key or exact
certificate cross-split violations, but exposes 70 D4 symmetry-key cross-split
violations. The symmetry-key split report assigns 817/90/93 rows with zero
position-key, symmetry-key, or exact-certificate cross-split violations. This
supports reproducible frontier accounting and symmetry-safe IID splitting, not
agency or OOD claims.

Wave 7 adds generator-family diversity: a deterministic KQK+KRK frontier shard
at `/private/tmp/partizan-family-frontier-wave-07.jsonl`, SHA-256
`46581eddc4ef5ff745722b5559615a5298d5dd5f003e61d66ff23bdb8e352e31`, with
2000 rows (400 exact, 1600 rejected) and exact rows evenly split across KQK and
KRK generators. Its split report has zero position-key or exact-certificate
cross-split violations, but exposes 137 D4 symmetry-key cross-split violations
and is not family-held-out OOD because both families appear in train/dev/test.
Its symmetry-key split report removes those symmetry leaks while retaining both
families in all splits.

Wave 8 adds the first family-held-out split artifact over the Wave 7 shard:
`docs/family_frontier_wave_07_holdout_krk_report.json` holds all KRK rows out
as test and uses KQK only for train/dev, with zero position-key or exact
certificate cross-split violations, but exposes 38 D4 symmetry-key train/dev
violations in the KQK side.

Wave 9 adds the symmetry-safe family-held-out protocol:
`docs/family_frontier_wave_07_holdout_krk_symmetry_report.json` keeps all KRK
rows in test and splits KQK train/dev by D4-canonical FEN key, with zero
position-key, symmetry-key, or exact-certificate cross-split violations. This
activates an evaluation-ready OOD split artifact, not an OOD performance result.

Wave 10 scores the fixed `fen_string_material_gate_v0` baseline on that
symmetry-safe KRK holdout. The baseline predicts every row as `exact`, producing
0.198 train accuracy, 0.215 dev accuracy, and 0.200 KRK-test accuracy with zero
rejected recall. This is a weak floor for future learned models, not evidence
that the benchmark has a useful classifier.

Wave 11 adds `fen_geometry_logistic_probe_v0`, a dependency-free logistic probe
over hand-coded king/attacker geometry, trained only on the KQK train split and
scored on held-out KRK. It reaches 0.942 train accuracy, 0.935 dev accuracy, and
0.928 KRK-test accuracy, with KRK rejected recall 0.91. This is a strong
hand-feature baseline for the current terminal-frontier boundary, not evidence
for exact-value learning or agency representation.

Wave 12 expands material-family breadth to a deterministic KQK+KRK+KBK+KNK
frontier shard at `/private/tmp/partizan-expanded-family-frontier-wave-12.jsonl`,
SHA-256 `328c32715eecf5a2dc745042543022dd89c47af8c07f5c8faec22372d8661713`,
with 4000 rows (800 exact, 3200 rejected) and 200 exact rows per family. Its
position-hash split exposes 269 D4 symmetry-key cross-split violations; its
symmetry-hash split and KNK-family holdout have zero position-key, symmetry-key,
or exact-certificate cross-split violations.

Wave 14 scores the expanded KNK holdout. The fixed FEN gate remains weak at
0.200 test accuracy, while the hand geometry probe reaches 1.000 KNK-test
accuracy. This is useful as a baseline and as a warning: the current
terminal-frontier exact-vs-rejected boundary is easy for handcrafted geometry,
so the next serious evidence must add harder compositional splits and
non-number exact targets.

Wave 15 adds the first exact-only frontier metadata target report over the
expanded shard. With KRK held out, KQK/KBK/KNK train and dev exact rows only
show `frontier_mean=1`, while KRK test exact rows include 44 rows with
`frontier_mean=1` and 156 rows with `frontier_mean=2`. The train-majority floor
therefore scores 0.220 on KRK test, and the report explicitly flags `2` as an
unseen test label relative to train. This creates a small certified
option-structure target, but frontier temperature is still constant at `-1` on
the current shard.

Wave 17 adds an executable composition-certificate dispatch plan at
`agents/waves/wave_17_composition_certificates.json`, following the bitmesh
BMCOMPOSE v1 digest contract from commit `c6e8e4d`. This is infrastructure, not
evidence: the current certificate binds a decomposition digest, component value
digest strings, and a composed result digest, but it does not yet prove root
coverage, thermograph value correctness, CGT result composition, or full chess
dynamic independence. Wave 17 is the next route to composition evidence because
it requires astralbase generation, partizan schema/reporting, OOD leakage
checks, and decomposition-aware baselines before claims can move.

The first Wave 17 implementation slice adds a deterministic BMCOMPOSE fixture
shard at `/private/tmp/partizan-composition-hard-target-wave-17.jsonl`,
SHA-256 `8a15c6043a9129b90b94e2ffeb78a04a3c1d8076b5f4aa932183bec6f60d859d`,
with 21 rows (16 exact fixture-number composition certificates, 5 rejected
composition controls). The companion symmetry split report
`docs/composition_hard_target_wave_17_symmetry_split_report.json` has zero
position, symmetry, exact-certificate, decomposition, composition,
qualified component-root, component-value, component-pair, and result-value
cross-split leakage. This is still a plumbing result: exact rows use declared
fixture sums over verified component value digests, not legal chess value
proofs or model results.

Wave 17 also adds exact-only composition holdout reports for `component_count`,
`composition_digest`, and `result_value_digest`. The component-count report
holds out the four 3-component exact fixture rows; the digest reports each hold
out one exact fixture row. All three reports preserve zero composition-identity
cross-split leakage. These reports establish split protocols for future
baselines, not decomposition-benefit evidence.

The first composition baseline report scores exact result
`canonical_serialization` on the component-count holdout. Train-majority and
FEN/material controls score 0.0 on the held-out 3-component exact rows, while
the fixture-only component-sum verifier scores 1.0. This is not a learned
decomposition result: the target is defined by that fixture sum, so the report
mainly proves rejected-row exclusion, split reuse, and baseline accounting.

Wave 18 adds the first source-aware non-fixture composed-board topology
benchmark at `docs/non_fixture_composition_topology_wave_18_benchmark_report.json`.
The underlying Astralbase shard has SHA-256
`ae01fe8256a1c7a699e5f6f0358d499d6c1f4850148c9251e1c494bb059d3aa8` and
contains 20 rows: 17 exact non-fixture composed-board rows and 3 rejected
non-fixture composition controls. The benchmark covers six
`component_topology_family` holdouts with zero leakage violations and now
reports `composition_spec_source`, separating 11 curated exact rows from 6
profiled generated depth-two rows. This moves beyond fixture-only provenance,
but it is still a small reporting and target-support artifact rather than
learned decomposition evidence.

Astralbase commit `d00abf8d5fa0be85f6c888ee2aedb2e60c3d0e4a` adds an executable
non-fixture composition replay audit over this shard. The command
`cargo run --quiet -- --replay-non-fixture-composed-domain-shard /tmp/astralbase-w18-traceable-composition.jsonl`
recomputes the BitMesh conservative legal-independence proof, component CGT
values, BMCOMPOSE digest, and result exact-value payload for all 17 exact rows,
while skipping the 3 rejected controls. This strengthens root/value/result
verification for the current shard but does not change the scale or modeling
status.

Astralbase commit `d418379b3bc26ccb3fe746f63cf674fd8d474da8` adds
`--generated-depth-two-profile-search` as a pre-expansion capacity audit. The
current report with `--rows-per-family 10` finds 21 white profiles, 14 black
profiles, and only 8 selectable generated candidates under global no-reuse
component/result digest constraints, split 3/3/2 across local-move,
asymmetric-fan, and pawn-phalanx topologies. This means the next scaling blocker
is broader profile generation, not merely replacing the current six-pair plan.

Astralbase commit `ca6e9baa96cd6ae2ab34d302c1b95546542dc9ba` removes that
profile-pool capacity blocker without changing the default shard. The expanded
profile search reports 234 left-component profiles, 253 right-component
profiles, and 30 selected candidates for `--rows-per-family 10`, with 10 in
each generated topology family. Regenerating the default non-fixture shard still
produces SHA-256 `ae01fe8256a1c7a699e5f6f0358d499d6c1f4850148c9251e1c494bb059d3aa8`,
and replay still checks 17 exact rows while skipping the 3 rejected controls.
The next step is therefore an explicit expanded-shard generation and reporting
change, not more profile-capacity work.

Astralbase commit `289c3a5b246a97233f68d5094de0d05f97f23a0d` adds that
explicit expanded-shard command. The generated artifact
`/tmp/astralbase-w22-expanded-composition.jsonl` has SHA-256
`9d1b2754b880e64498b5deec12ac14c5b4be320446ed1319a67252599bd5dcc7` and
contains 44 rows: 41 exact non-fixture composed-board rows and 3 rejected
controls. The 30 newly generated exact rows are balanced 10/10/10 across the
three generated depth-two topology families and pass Astralbase replay
(`row_count=44`, `checked_exact_rows=41`, `skipped_rejected_rows=3`,
`skipped_non_target_rows=0`). To reach this scale the generator permits
generated component-value reuse while excluding seed component values and
keeping result digests and positions unique. Partizan reports therefore
correctly fail leakage gates: the generated-source holdout has train/dev/test
counts 13/1/30 but reports duplicate decomposition/component identities and
cross-split decomposition/component-root leakage. Wave 22 is a replay-valid
scale and leakage-audit artifact, not a learned or leakage-clean OOD result.

Astralbase commit `6333b2ea2a367f80c6b3e27eea6ea077b2ca600e` adds a separate
leakage-clean command:
`cargo run --quiet -- --leakage-clean-non-fixture-composed-domain-shard --rows-per-family 10`.
The resulting artifact `/tmp/astralbase-w27-clean-composition.jsonl` has
SHA-256 `7e1085cb0a212d7f3e620885c11bf709f8ce2bfa28204c664bbc0aa02875ef9c`
and contains 21 rows: 18 exact rows and 3 rejected controls. Current clean
capacity is 7 generated exact rows, split 3 local-move, 2 asymmetric-fan, and 2
pawn-phalanx. Astralbase replay passes, and Partizan topology/source/baseline
reports all pass `--fail-on-leakage`. This creates the first leakage-clean
non-fixture composition evaluation slice, but its generated support is small
and no learned model result exists yet.

Astralbase commit `46f6607d6003c7d74f11aacb4584f57f69d053e1` adds Wave 31
profile-search diagnostics without changing the Wave 18, Wave 22, or Wave 27
shard hashes. `docs/non_fixture_composition_profile_capacity_wave_31_report.json`
reports 14 left profiles, 13 right profiles, 182 candidate pairs per generated
topology family, and only 7 selected rows under a 10-per-family target. All 539
rejected candidates are blocked by `component_value_digest_reuse_before_materialization`,
so the next scale blocker is fresh component-value profile supply under the
current no-reuse rule, not Partizan leakage reporting or learned-model plumbing.
Wave 32 tested a bounded rank-3/rank-6 supplemental profile-source variant and
reverted it after measurement: support remained at 7 selected rows, with 616
component-value reuse rejections and 7 materialization failures. The next
attempt needs more substantive component geometry, a versioned value rule, or a
formally documented split change.
Wave 33 adds profile-inventory instrumentation at Astralbase commit
`90495057c88d8441b9d378056fe5e744c7212d5f`: white-side generation starts from
526 patterns but reaches only 14 accepted profiles after 397 wall-safety
rejections, 109 duplicate value digests, and 6 node-budget rejections; black
starts from 527 patterns and reaches 13 accepted profiles after 162 wall-safety
rejections, 261 duplicate value digests, and 91 node-budget rejections.
Wave 34 tests a depth-three local-move value rule as an inventory-only
diagnostic at Astralbase commit `04ea2b967c729f9d7219a3e4b624c976d97949e9`.
The report `docs/non_fixture_composition_depth_three_profile_inventory_wave_34_report.json`
has SHA-256 `52f4fd3853955bb854b256e0492c35d880064bdc68c17b63323598998e19411d`
and shows the naive depth increase worsens fresh profile supply: white accepted
profiles fall to 6 and black accepted profiles fall to 4, mainly because
component recursive-node budget rejections rise to 91 and 337 respectively.
This rules out increasing local-move depth under the same node budget as the
next clean-scale strategy.
Wave 35 tests a low-node edge/minor ladder source at Astralbase commit
`af839487a50d73fdfd4204758af633470480e62c`. The source inventory report
`docs/non_fixture_composition_profile_source_inventory_wave_35_report.json`
has SHA-256 `8448166424a8f39418de897a2605e4a4909633b7d89e20806024bbdc8d98f975`,
and the combined-source search report
`docs/non_fixture_composition_combined_source_profile_search_wave_35_report.json`
has SHA-256 `82de89155b7c3e6f1631edd4e5e6f7a572ec23db953c6e31eb2eeaa0e7706e87`.
The union reaches 15 white and 14 black profiles but still selects only 7 clean
rows, with 616 component-value reuse rejections and 7 materialization failures.
This rules out simple edge-ladder square shifts as the next scale strategy.
Wave 36 adds a duplicate-cluster diagnostic at Astralbase commit
`e3fb57cbd1bcbf8a2e8ea6e7b010b171e2b5d061`. The report
`docs/non_fixture_composition_duplicate_clusters_wave_36_report.json` has
SHA-256 `616ab229d5e0ad7a7be64ecb00c7632fee1df81617fe6d31bbf6302515038e78`.
It shows that the corner-plus-edge union has 254 budget-safe white profiles but
only 15 value digests, and 517 budget-safe black profiles but only 14 value
digests. The largest white duplicate cluster has 45 profiles and 8 distinct
material/local-move signatures; the largest black cluster has 125 profiles and
12 distinct signatures. This is evidence for a possible richer versioned target,
not supervision or model evidence yet.
Wave 37 adds a signature-profile support diagnostic at Astralbase commit
`1e5f54a051fd6b8711a760493676ce81a3dde7d6`. The report
`docs/non_fixture_composition_signature_profile_search_wave_37_report.json` has
SHA-256 `968aa1f7341a55e92f95dc54b4d81df3653c412bdf2bc18840175128da2ace9e`.
Using the diagnostic rule
`depth2_value_digest_plus_material_balance_plus_local_move_counts_v0`, it finds
90 left and 92 right signature profiles, 8280 candidate pairs per generated
topology family, and 30 selected diagnostic rows balanced 10/10/10 across
local-move, asymmetric-fan, and pawn-phalanx. This is a positive value-grammar
design signal only: it is not exact-value evidence, not a promoted shard, and
not a learned-model result until replay-compatible provenance, split semantics,
deterministic floors, and model baselines exist.
Wave 38 adds an executable signature target contract report:
`docs/non_fixture_composition_signature_target_contract_wave_38_report.json`,
SHA-256 `65012cbe11d8fda1b9107733c6ab36b0e6e0f523d795ce4b8755820603ac10d5`.
It validates the Wave 37 report as `support_gate.passed=true` with zero
duplicate component signatures and zero duplicate result signature keys, while
keeping `promotion_gate.passed=false`. The recorded blockers are a missing
versioned exact value rule, missing replay-compatible provenance, missing split
and leakage semantics, and missing deterministic/model baselines. This is the
current guardrail against treating signature support as supervision.
Wave 39 materializes the same selected targets as a diagnostic heuristic shard:
`docs/signature_target_diagnostic_wave_39.jsonl`, SHA-256
`4208f0fc076f4b5a9be3ed80293684bb492b1b890202b1fe38d41678e69c02a4`, from
Astralbase commit `de6e1ccdab2116376ef2b1043161ffc158b01ec9`. The shard has 30
schema-valid `label_kind=heuristic` rows and zero exact rows, with
`target_status=diagnostic_only` and `supervision_eligible=false` on every row.
Its split report has train/dev/test counts 25/3/2 and zero leakage violations.
This gives the target row-level auditability without changing its claim status.
Wave 40 adds the first deterministic floor for that heuristic target:
`docs/signature_target_diagnostic_wave_40_baseline_report.json`, SHA-256
`7e389123f93b1d5bf73ad99616eff605b48d9bd37e393fd0f0a67c18872f012e`. The
`heuristic_train_majority_target_v0` floor evaluates only
`label_kind=heuristic` rows and targets `heuristic.outputs.result_signature_key`
for method `signature_profile_target_diagnostic`. It includes all 30 rows,
scores 0.04 train accuracy and 0.0 dev/test accuracy, and records all 3 dev
labels plus both test labels as unseen relative to train. This is useful target
support evidence and a required future comparison, not evidence that the
signature is an exact value target.
Wave 41 screens coarser signature-target projections in
`docs/signature_target_projection_wave_41_report.json`, SHA-256
`a1901f142c12acced0f3db06ae4b00fbadc2295734b777594be6204727b38311`. The
inventory evaluates 9 projections over the same 30 heuristic rows. Only
`component_topology_family` removes dev/test unseen labels, but it is a
3-label generator-family target with train/dev/test majority accuracy
0.36/0.0/0.5. More informative value-digest, material, mobility, and
topology-material/mobility projections remain sparse with 23-30 labels and
unseen dev/test support. This rules out treating simple projection choice as a
model-ready target solution.
Wave 42 adds a bounded Astralbase support diagnostic for naive rpf20 signature
scaling at Astralbase commit `7f8dc31ac1ae7da173fbb7c4df2bfe6fdd50c8bd`.
The report
`docs/non_fixture_composition_signature_bounded_support_wave_42_report.json`
has SHA-256
`2d2ca5db4bc9cfe4d021fead472d763c89090496fa058ca8408517b854cf6011`. With a
2500 candidate-pair cap per topology family and a 20-row target, the selector
reaches only 35 rows total: 12 asymmetric-fan, 12 local-move, and 11
pawn-phalanx. All three families hit the cap before reaching target. This
shows that naive higher-support signature scaling needs either more candidate
diversity, a different grouping/split rule, or deeper target semantics; it is
not a promoted shard.
Wave 43 runs the same bounded support diagnostic at the full 8280 candidate
pairs per topology family. The report
`docs/non_fixture_composition_signature_bounded_support_wave_43_report.json`
has SHA-256
`d6d001219aa0434a7d9b49adcd0979373981b9527c8c86b3a3187b6f639e10ff` and
reaches the rpf20 target: 60 selected rows, exactly 20/20/20 across the three
topology families. It does not hit the cap, but it requires scanning 6108-6316
candidate pairs per family and records 18194 component-signature reuse
rejections. This turns rpf20 from an open scale question into a materialization
and audit task, not a modeling result.
Wave 44 materializes that rpf20 diagnostic shard in
`docs/signature_target_diagnostic_wave_44_rpf20.jsonl`, SHA-256
`3294d3207191db59371ad48761c762963871563ce4a9decc605783f29141908c`, and keeps
all 60 rows as `label_kind=heuristic` with `target_status=diagnostic_only` and
`supervision_eligible=false`. Partizan schema validation passes; the split
report has train/dev/test counts 46/11/3 with zero duplicate or cross-split
leakage violations. The full `result_signature_key` floor has 60 labels,
scores 0.0217 train accuracy and 0.0 dev/test accuracy, and records every
dev/test label as unseen relative to train. The projection inventory again
shows the central tradeoff: topology is supported but coarse, while material,
mobility, value-digest, and joined projections remain sparse. This is the
largest audited signature diagnostic slice so far, not exact value evidence.
Wave 45 makes the promotion boundary executable in
`docs/signature_target_promotion_wave_45_report.json`, SHA-256
`ea6d505a3fb2693a8fd1dd0b33667e14c12cdca0efbb07cb1f7e0b60b0af71f3`. The
`row_contract_gate` passes for all 60 Wave 44 rows: required output fields are
present, target status remains diagnostic-only, supervision remains false,
component/result signature reuse is zero, and result signature keys match the
topology plus left/right component signatures. The `promotion_gate` remains
closed with all four blocker IDs present on all rows, and the report records 17
duplicate `current_result_value_digest` values. This establishes a clean
diagnostic row contract while making the exact replay blocker sharper.
Wave 46 adds the Astralbase replay preflight at commit
`47933a33799571b29bd51b0896a141853da0e1b0`. The report
`docs/signature_target_replay_preflight_wave_46_report.json`, SHA-256
`448b8fa58c656212b9153d2491b8d343ef65817a2a2b60fedbb6fcdcee3fd191`, checks all
60 Wave 44 heuristic rows and recomputes active pieces, component value
digests, component signatures, result signature keys, current result value
digests, and recursive node totals from the FEN board. All replay checks pass
with zero missing fields, zero contract mismatches, zero replay failures, and
zero field mismatches. Promotion remains blocked on all four blocker IDs. This
upgrades the signature target from row-contract-complete to replay-preflighted,
but it still is not a promoted exact value rule or model result.
Wave 47 adds the first exact metadata shard for this target at Astralbase
commit `983f1f8f5644074c59737ec71789662631e65934`. The shard
`docs/signature_target_exact_wave_47.jsonl`, SHA-256
`ca2efe473ef4d4622ecf3b7000740fcf0f8dad2473a41661bb902555bced9c82`, contains
13 `label_kind=exact` rows and zero heuristic rows. Each row is a verified
depth-two local-move exact thermograph value, with signature metadata recorded
under `exact.value` as auxiliary fields rather than as a new `ExactValueClass`.
Astralbase replay checks all 13 rows, and the Partizan split report passes
`--fail-on-leakage` with zero duplicate component/result value digests and zero
cross-split digest leakage. The exact `result_signature_key` floor scores
0.0909 train accuracy and 0.0 dev/test accuracy, with one unseen label in each
of dev and test. This closes the exact-row semantics and split/floor audit for a
small shard, but it also shows the value-unique exact support limit: only 13 of
the 60 diagnostic support rows can currently be promoted without value-digest
reuse.
Wave 48 measures that exact-support collapse directly at Astralbase commit
`39a66d9ee0c2c7d79a9629e5a60e1da519528d89`. The report
`docs/non_fixture_composition_value_unique_signature_support_wave_48_report.json`,
SHA-256 `6192212cc78b22267964527c92dc793f774577d7acfeecd7b2eea94cfdb10dfa`,
runs the same value-unique signature selector used by Wave 47. It sees 90 left
and 92 right signature profiles and 8280 candidate pairs per topology family,
but still selects only 13 rows under the rpf20 target: 4 asymmetric-fan, 5
local-move, and 4 pawn-phalanx. The dominant rejection is
`component_value_digest_reuse_before_materialization=18391`, with 6412
component-signature reuse rejections. This makes the next support task concrete:
generate new component-value diversity, not merely more pair scanning.
Wave 49 adds the capacity upper-bound report at Astralbase commit
`2ff8363113cb1cb9fb457c4d13de0099910ee14e`. The report
`docs/non_fixture_composition_value_unique_signature_upper_bound_wave_49_report.json`,
SHA-256 `3f04aa17ef86297f9035c4c1fa3c06b7ce9c5816540c3aedc434c3a4dc6911db`,
shows the current source has 15 left and 14 right unique component value
digests, zero overlap, and 29 combined unique component values. The simple
component-value capacity upper bound is therefore 14 rows against the 60-row
rpf20 target. Since the current greedy selector gets 13 rows, exact support is
near the current source ceiling; selector tuning alone cannot produce a
material scale jump.
Wave 50 tests one new source-design branch at Astralbase commit
`64d6c4bcadb7ec11c40a3783633e9c1a184526ef`. The capacity-only sweep report
`docs/non_fixture_composition_value_unique_signature_source_sweep_wave_50_report.json`,
SHA-256 `7af88c92a5d5164b77690cc3a69e0e7543b77755fa22193a14078cd5fd1ffafe`,
compares five component-source families. Baseline and edge-ladder sources each
cap at 13 rows, the current combined source remains at 14, the rank-4/5 ladder
alone caps at 9, and the current-plus-rank-4/5 source still caps at 14. The
combined rank-4/5 source does raise signature-profile counts to 96/96, but it
does not increase the 15-left/14-right unique component-value supply. This is a
source-family no-go, not an exact-support improvement.
Wave 51 adds the first source-family breakthrough at Astralbase commit
`3fe37ce63abc950ae8a83318f97bfe7825751492`. The atlas report
`docs/non_fixture_composition_value_unique_signature_source_atlas_wave_51_report.json`,
SHA-256 `0ff40baae12a5ec00472bc41e95299ac7b37bec25e15413a80d26f2e2c7c9fb6`,
shows that same-color C/F bridge and wide-shelf variants still fail, but the
mixed-color hook source reaches the full 60-row capacity target with 113 left
and 204 right unique component values. The combined
`corner_plus_edge_plus_mixed_color_hook_v0` source reaches 115 left and 208
right unique values. The full selector report
`docs/non_fixture_composition_value_unique_signature_mixed_hook_wave_51_report.json`,
SHA-256 `48ee12bd61bb3be18e91af61f2b2c0c93f4796f6b5774859e29b844de759e0ad`,
selects 60 rows balanced 20/20/20 across topology families. This breaks the
exact-support source bottleneck, but it is still support evidence rather than a
promoted shard.
Wave 52 promotes that support into an audited exact metadata shard at
Astralbase commit `34c44d72d7b86d00b80855215e1d71178629327c`. The shard
`docs/signature_target_mixed_hook_exact_wave_52.jsonl`, SHA-256
`989587a985e8e325edaa130a017fb964034063a1772a8fe9817c00603d67670d`, contains
60 exact rows. Schema validation passes, Astralbase replay checks all 60 rows,
and the split report
`docs/signature_target_mixed_hook_exact_wave_52_split_report.json`, SHA-256
`b1f88ad2a8324684e5bf66391908a2af26a63190b3fa4cd27cea4a6bc109f574`,
passes `--fail-on-leakage` with train/dev/test 48/5/7 and zero duplicate or
cross-split component/result value-digest leakage. The exact
`result_signature_key` floor scores 0.0208/0.0/0.0 on train/dev/test, with all
5 dev labels and all 7 test labels unseen relative to train. This creates the
first scaled exact metadata split for model baselines, not a learned result.

Wave 53 adds an exact projection inventory over that shard:
`docs/signature_target_mixed_hook_projection_wave_53_report.json`, SHA-256
`b739de03d9231ae7e1f8acead01fe38eef16b0aa420dde9303b5e565ebf3b82e`.
It keeps the same 48/5/7 split and screens 9 exact target projections. The full
`result_signature_key` still has 60 labels and all dev/test labels unseen, so
it is not a credible immediate learned target. The viable compact next targets
are `component_topology_family`, with 3 labels and zero dev/test unseen labels,
and `net_material_balance`, with 15 labels and zero dev/test unseen labels.
This is a target-selection gate for learned baselines, not model evidence.

Wave 54 runs those compact projection baselines in
`docs/signature_target_mixed_hook_projection_baseline_wave_54_report.json`,
SHA-256 `1d261db885f1b6a0886ba3acd0b004f36a66c1b389a827f2e88e3a6e2cda437a`.
`component_topology_family` does not improve on the train-majority test floor:
the best test score remains 0.2857. `net_material_balance` reaches 0.5714 test
accuracy under material/signature controls, which makes it a control target
rather than decomposition-benefit evidence. The next evidence must expand exact
support and define stronger ablations before model claims.

Wave 55 expands the mixed-hook exact shard to rpf36. The support sweep shows
rpf30 reaches 90 rows and rpf36 reaches 108 rows, both balanced across topology
families, while rpf50 reaches only 109 rows rather than the 150-row target. The
rpf36 exact shard, SHA-256
`86022f1abd7b4c10cda55fdc84f07c4c0252191dad55a3824786b1f0dd43f850`, replays
all 108 rows and passes the split/leakage gate with train/dev/test 89/9/10.
Full result signatures remain fully sparse on dev/test. The topology projection
has a small FEN/material logistic test lift, 0.3 versus a 0.2 majority floor,
but dev is worse than majority and the test split has only 10 rows. This is
expanded exact support plus tentative baseline evidence, not a claim.

Wave 56 tests an expanded mixed-hook source at Astralbase commit
`234a48ab15bc9eb70b21e188d2a52df03e60e60c`. The diagnostic report
`docs/signature_target_mixed_hook_expanded_source_wave_56_rpf50_report.json`,
SHA-256 `df83ac5353d06a0a1a4c56606c2527ff7f8c1ac7e5bf90af4b976336105884a7`,
raises left/right unique component values to 125/226 and selects 112 rows at
rpf50, but the target is 150 rows. This is a source-design no-go, not an exact
support expansion.

Wave 57 adds a topology-balanced baseline ablation over the rpf36 exact shard:
`docs/signature_target_mixed_hook_topology_balanced_baseline_wave_57_rpf36_report.json`,
SHA-256 `f737b0c7d01a0a30bc000540cec212c390a9612ace84651e63fd84d4fb90a099`.
The split is 72/18/18 with each topology family contributing 24/6/6
train/dev/test rows. The best topology test score is 0.3889 from the
signature-metadata logistic probe, but dev is 0.2778 against a 0.3333 majority
floor. This strengthens the ablation story while keeping model claims blocked.

Wave 58 decomposes that topology-balanced probe into feature groups:
`docs/signature_target_mixed_hook_topology_balanced_ablation_wave_58_rpf36_report.json`,
SHA-256 `e6c749c70e9f63fb8d9e59708086c90d9ae9f723148a50d51fbe7604044e0e82`.
The report keeps the 72/18/18 split and scores ten feature groups. No topology
feature group beats train-majority on both dev and test: component material
gets 0.4444 test but only 0.2222 dev, while full signature metadata repeats
0.3889 test with 0.2778 dev. This is a no-go for citing current compact
topology probes as learned structure.

Wave 59 tests a materially different interior mixed-hook source at Astralbase
commit `754bc1dabafacf7f0bab5e7e01a1bd56324bbfbb`. The diagnostic report
`docs/signature_target_mixed_hook_interior_source_wave_59_rpf50_report.json`,
SHA-256 `1c370858746f669006211bc7b36a234f111daa59fe2e2365098b3425ed3d525e`,
selects only 11 standalone interior rows at rpf50, with topology counts 4/4/3.
The interior-first combined variants are capacity-only and reach capacity 81,
below the 150-row target and below Wave 56's expanded-source supply because the
pattern limit truncates stronger prior source patterns. This is another
source-design no-go.

Wave 60 tests whether that pattern limit is the main rpf50 blocker at
Astralbase commit `c5692f5cddbc6dca6f9177ce8bae3bf12ed37713`. The capacity-only
report
`docs/signature_target_mixed_hook_pattern_limit_atlas_wave_60_rpf50_report.json`,
SHA-256 `688ae4fd3a2fe8fb2eda756de3e27062b2d2ba958da4d619ef1b80ffab65e678`,
shows bounded expanded capacity 125, bounded expanded+interior capacity 125,
bounded interior-first+expanded capacity 81, and unbounded expanded+interior
capacity only 129. Since rpf50 requires 150 rows, pattern-limit tuning alone is
not enough; the next source needs genuinely new component-value supply.

Wave 61 tests whether the topology feature-ablation no-go is sensitive to small
deterministic logistic-probe hyperparameter choices:
`docs/signature_target_mixed_hook_topology_balanced_sweep_wave_61_rpf36_report.json`,
SHA-256 `2dcc03851cd0b4bcbd88865512914aa4c5c1aa33292bc85bdb17cc63e2d433e6`.
Across 10 feature groups and 18 trials per group, `claim_candidate_count` is
0 under the rule that the same trial must beat train-majority on both dev and
test. This rules out simple logistic-probe tuning as the explanation for the
current topology no-go.

Wave 62 tests genuinely new left-side component-value supply at Astralbase
commit `7087ed48e915b4e0d31b3df61c0864a5ce9e7007`:
`docs/signature_target_mixed_hook_left_supply_atlas_wave_62_rpf50_report.json`,
SHA-256 `9c04988510c61f3aec0958770802f3ffa8027d15a43b77013f4ffcc3ea680de5`.
The capacity-only atlas keeps `current_selection_evaluated=false` for every
source. It finds that `unbounded_expanded_plus_outer_left_vs_expanded_right_v0`
reaches the 150-row rpf50 capacity target with 155 left and 226 right unique
component-value digests, while `unbounded_all_left_supply_vs_expanded_right_v0`
also reaches capacity 150 with 167 left unique digests. This is the first
rpf50 capacity-clearing source diagnostic, but it still requires selector,
materialization, replay, leakage, and baseline gates before any exact-support
or model claim.

Wave 63 tests the Wave 62 capacity-clearing source under a value-unique bounded
selector at Astralbase commit `a09ad3210eea2370501cb9adc213c10dc7fbb222`:
`docs/signature_target_mixed_hook_left_supply_bounded_selection_wave_63_rpf50_limit2500_report.json`,
SHA-256 `4fed02cd00e3db0dd19421fff935178dd96b8437e84bc95a8542de9ba712b3f4`.
With a 2,500 candidate-pair limit per topology family, the selector chooses
only 12 rows, balanced 4/4/4, and hits the limit in every family. Rejections are
dominated by component-signature reuse before materialization (3,986) and
component-value digest reuse before materialization (3,491). The result keeps
Wave 62's capacity breakthrough intact but identifies deterministic candidate
ordering and value-aware pairing as the next exact-support blocker.

Wave 64 tests a static component-value-digest-spread ordering for the same
source and candidate-pair budget at Astralbase commit
`44663e65fd02c4f6cb883a04d7caab79b65cc9f1`:
`docs/signature_target_mixed_hook_left_supply_value_spread_selection_wave_64_rpf50_limit2500_report.json`,
SHA-256 `7b2a23fd26ba9ecb7715da17ea678d4ae63c313fdc1381bfab6bc7ae355a71e3`.
It selects only 4 rows, with topology counts 1/2/1, and hits the candidate
limit in every family. This is worse than Wave 63's 12-row profile-index order,
so static digest spreading is a no-go. The next selector work should be
dynamic: choose pairs against currently unseen component values/signatures and
materialization constraints rather than relying on a fixed hash order.

Wave 65 tests dynamic unseen-value/signature pairing before materialization at
Astralbase commit `5f638603c959a70ff53eaaff7e00ef943788d1db`:
`docs/signature_target_mixed_hook_left_supply_dynamic_pairing_preflight_wave_65_rpf50_report.json`,
SHA-256 `5ba07fc46870bfb86c317104c1d3e667a34521c6ea51b3f7641d923a78c4121d`.
The preflight selects 137 candidate pairs with topology counts 46/46/45,
improving sharply over Wave 63's 12-row bounded selector and Wave 64's 4-row
static value-spread order. It remains pre-materialization and still 13 rows
short of the 150-row rpf50 target, so exact-support promotion remains closed.

Wave 66 tests the all-left Wave 62 capacity-clearing source under the same
dynamic unseen-value/signature preflight at Astralbase commit
`1e7ce7a2e8ece442e63a20eb7600137b91b25cad`:
`docs/signature_target_mixed_hook_all_left_supply_dynamic_pairing_preflight_wave_66_rpf50_report.json`,
SHA-256 `b060baae0df987af3f42a2a48767acbad0df877119bc80b784b90ca79b0faa69`.
The preflight selects 145 candidate pairs with topology counts 48/49/48,
improving over Wave 65's 137 pairs but still 5 rows short of the 150-row rpf50
target before materialization. Per-topology rejection counts show
component-signature reuse dominates all three families. Exact-support promotion
remains closed until a selector yields materialized, replayed, leakage-clean
rows.

Wave 67 tests whether the remaining Wave 66 gap is solved by adding right-side
near-wall, outer, diagonal, and interior supply:
`docs/signature_target_mixed_hook_all_left_all_right_dynamic_pairing_preflight_wave_67_rpf50_report.json`,
SHA-256 `08d2a9cecfd00118a29ef5e023b212d37481442ad14207d2cb064c73c17395f3`.
The right signature profile count rises from 371 to 545, but selected support
remains 145 candidate pairs with the same 48/49/48 topology counts and the same
5-row gap. This rules out right-side source expansion alone as the next
credible rpf50 path.

Wave 18 also adds a generated-vs-curated source holdout using
`composition_spec_source=profiled_depth2_component_pair_generator_v0` as the
exact test selector. `docs/non_fixture_composition_source_wave_18_holdout_report.json`
isolates the six profiled generated exact rows in test and keeps curated exact
rows in train/dev, with zero leakage violations. The generated test rows are
balanced 2/2/2 across the three depth-two topology families. The companion baseline report
shows train-majority and FEN/material controls scoring 0.0 on generated test
rows, while the fixture component-sum sanity checker abstains on all six generated
rows. All six generated test labels are unseen relative to train, so this is an
OOD protocol and target-support warning, not a model result.

| ID | Claim | Current Evidence Status | Required Evidence | Baselines | Falsification Condition | Current Blocker / Next Evidence | Owner |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C1 | Exact game-structure labels expose agency information not captured by scalar outcome labels. | Unproven. Current artifacts prove only that terminal, terminal-frontier, formal switch, deterministic frontier rows, and the Wave 17 composition plan can be serialized with provenance. `docs/agency_metrics.md` defines candidate metrics, but no agency metric has a baseline-beating model result. | Dataset rows with exact labels at useful scale, agency metrics, and representation probes comparing structured labels against scalar labels. | Scalar WDL/DTM model, material features, random labels; `fen_string_material_gate_v0` and `fen_geometry_logistic_probe_v0` are baselines, not agency evidence. | Scalar-supervised or hand-feature controls match structured-supervised models on agency probes and OOD tests. | Needs Wave 17 composition hard targets whose agency metrics are not solved by hand geometry and whose exact labels pass target-support and leakage gates. | `research_director`, `model_lab` |
| C2 | Certified decomposition improves generalization on composed positions. | Blocked by modeling evidence. Negative controls and rejected rows show weak, unchecked, or absent strict decomposition must not enter exact training. The Wave 17 fixture shard proves nested certificate transport, leakage accounting, rejected-row exclusion, and baseline wiring. Wave 18 adds small source-aware non-fixture topology and generated-vs-curated holdouts. Wave 19 adds replay verification for the 17 current non-fixture exact rows. Wave 22 expands to 41 replay-verified exact non-fixture composed-board rows but fails leakage gates because generated component/decomposition identities are reused. Wave 27 adds a leakage-clean source/topology slice with 18 exact rows, including 7 generated exact rows, and zero Partizan leakage violations. Wave 31 diagnoses the clean-scale blocker as fresh component-value profile supply: 539 candidates are rejected for component-value reuse before materialization. Wave 32 shows simple rank-3/rank-6 variants are insufficient. Wave 33 localizes profile collapse to wall safety, duplicate value digests, and black-side node budget. Wave 34 shows a naive depth-three local-move value rule worsens support to 6 white and 4 black accepted profiles under the current node budget. Wave 35 shows a low-node edge/minor ladder source still selects only 7 clean rows after 616 component-value reuse rejections. Wave 36 shows duplicate value digests hide distinct material/local-move signatures. Wave 37 tests one versioned diagnostic signature and recovers 30 selected diagnostic rows, balanced 10/10/10 across generated topology families. Wave 38 makes the support/promotion boundary executable, Wave 39 materializes those rows as heuristic diagnostics with `supervision_eligible=false`, Wave 40 adds a heuristic-only train-majority floor that scores 0.04/0.0/0.0 on train/dev/test, Wave 41 shows only the coarse topology projection has zero unseen dev/test labels, Wave 42 shows naive rpf20 signature scaling reaches only 12/12/11 rows under a 2500-pair cap, Wave 43 shows rpf20 is reachable with a full-pair bounded scan, Wave 44 materializes and audits the 60-row rpf20 heuristic shard with zero split leakage but unique full-signature labels and sparse informative projections, Wave 45 shows those rows pass a strict diagnostic row-contract gate, Wave 46 shows all diagnostic fields replay from the board under Astralbase preflight, Wave 47 promotes a value-unique 13-row exact metadata shard with replay, leakage, and exact target-floor reports, Wave 48 identifies component-value reuse as the immediate support blocker with 18,391 reuse rejections, Wave 49 shows the current component-value capacity upper bound is only 14 rows, Wave 50 shows the tested rank-4/5 component-source branch does not raise that ceiling, Wave 51 finds a mixed-color hook source whose selector reaches 60 value-unique support rows, Wave 52 materializes those rows as a schema-valid, replayed, leakage-clean exact metadata shard with a deterministic target floor, Wave 53 shows compact exact projections are the immediate credible targets while full result signatures remain unseen-label sparse, Wave 54 shows no topology test lift over majority while net material is solved mainly by material controls, Wave 55 expands exact support to 108 rows but leaves model evidence tentative and rpf50 source-limited, Wave 56 shows one expanded mixed-hook source remains far below rpf50, Wave 57 shows topology test lift does not hold on dev under a balanced ablation split, Wave 58 shows no topology feature group beats majority on both dev and test, Wave 59 shows an interior mixed-hook source does not solve rpf50 support, Wave 60 shows unbounded pattern capacity still stays below rpf50, Wave 61 shows simple logistic-probe tuning yields zero matched dev/test topology candidates, Wave 62 finds capacity-only left-supply variants that clear rpf50, Wave 63 shows the first bounded selector over that source selects only 12 rows under a 2,500-pair per-family limit, Wave 64 shows static value-digest spreading worsens that bounded result to 4 rows, Wave 65 dynamic preflight recovers 137 pre-materialization pairs but remains 13 short of rpf50, Wave 66 all-left dynamic preflight recovers 145 pairs but remains 5 short, and Wave 67 shows all-right source expansion still selects only 145 pairs. No learned decomposition model has beaten controls. | Strict decomposition certificates, verified composed positions, a composition OOD split at useful scale, and learned decomposition-aware results on a leakage-clean split. | Full-board scalar model, no-decomposition structured model. | Decomposition-aware models do not improve on held-out compositions. | Needs materialization-aware pairing/search or a different model class; simply adding right-side source supply did not close the Wave 66 gap. | `topology_engineer`, `model_lab` |
| C3 | Temperature and option-value structure provide measurable proxies for initiative and forcedness. | Partially plumbed, not evidenced for chess. The artifacts include one formal `switch` fixture with temperature 1 and chess terminal-frontier rows with certified child-option metadata. Wave 15 adds an exact-only `frontier_mean` target with KRK-family OOD shift, but frontier temperature is constant and exact chess labels remain scalar `number`. | Exact temperature labels, option-value distributions, positive controls, and negative controls. | Legal move count, material delta, engine scalar evaluation, and train-majority frontier metadata floors. | Temperature or option-structure targets fail to predict forcedness or move urgency beyond simple controls. | Needs chess-derived exact nonterminal positions whose target includes nonconstant temperature or non-number exact values, not only frontier metadata. | `theory_steward`, `exact_value_engineer` |
| C4 | Model-guided search can discover compact, verified, agency-rich positions more efficiently than random or heuristic search. | Unproven and scale-blocked. The current slice has no model-guided search logs, verified gallery, leakage checks, or ranking comparisons. | Verified gallery, search logs, leakage checks, and beauty/agency metric rankings. | Random generation, material heuristic, handcrafted metric search. | Verified discovery precision does not beat baselines under matched budget. | Needs matched-budget discovery runs over labels that passed exact, domain, and decomposition gates. Negative controls only define what must be excluded. | `discovery_curator`, `verifier_red_team` |
| C5 | The benchmark supports reproducible evaluation of exact-label learning under OOD shift. | Partially evidenced. Current artifacts support schema, deterministic regeneration, manifest accounting, mixed FEN/CGT encodings, frontier shards, deterministic split/leakage reporting, symmetry-safe split reporting, KRK and KNK family-held-out splits, fixed deterministic floors, hand-feature probes, one exact-only frontier metadata target report, an executable Wave 17 composition plan, a fixture-level BMCOMPOSE shard with composition leakage reporting, exact-only composition holdout protocols, a source-aware Wave 18 non-fixture topology benchmark, a generated-vs-curated source holdout with zero leakage violations, a Wave 19 replay audit for current non-fixture composition certificates, Wave 20/21 generated profile-search capacity audits, a Wave 22 expanded composition shard with replay and leakage-audit reports, a Wave 27 leakage-clean composition slice with deterministic baseline reports, a Wave 31 clean-profile rejection diagnostic, a Wave 32 capacity no-go, a Wave 33 profile inventory, a Wave 34 depth-three no-go inventory, a Wave 35 edge-ladder no-go inventory/search, a Wave 36 duplicate-cluster diagnostic, a Wave 37 signature-profile support diagnostic, a Wave 38 signature target contract gate, a Wave 39 heuristic signature target diagnostic shard, a Wave 40 heuristic target train-majority floor, a Wave 41 heuristic projection inventory, a Wave 42 bounded higher-support diagnostic, a Wave 43 full-pair support gate, a Wave 44 materialized rpf20 heuristic diagnostic shard with schema, split/leakage, floor, and projection reports, a Wave 45 promotion-readiness report separating row-contract readiness from promotion eligibility, a Wave 46 Astralbase replay-preflight report over all 60 diagnostic rows, a Wave 47 exact metadata shard with schema, replay, split/leakage, and exact target-floor reports over 13 value-unique rows, a Wave 48 support-collapse report showing 18,391 component-value reuse rejections under the exact selector, a Wave 49 capacity upper-bound report showing the current 14-row ceiling, a Wave 50 source-sweep no-go for the tested rank-4/5 ladder, a Wave 51 mixed-hook support breakthrough to 60 selected rows, a Wave 52 mixed-hook exact metadata shard with schema, replay, split/leakage, and deterministic floor reports, a Wave 53 exact projection inventory that separates compact viable targets from unseen full-signature targets, a Wave 54 compact-projection baseline report, a Wave 55 rpf36 exact support expansion with full audit reports, a Wave 56 expanded-source no-go, a Wave 57 topology-balanced baseline ablation, a Wave 58 topology feature-group ablation, a Wave 59 interior-source no-go, a Wave 60 pattern-limit atlas, a Wave 61 topology sweep, a Wave 62 left-supply capacity atlas, a Wave 63 bounded-selector diagnostic, a Wave 64 static value-spread selector no-go, a Wave 65 dynamic pairing preflight, a Wave 66 all-left dynamic pairing preflight, and a Wave 67 all-right source-supply no-go. Learned structured-label performance and exact-value learning remain unproven. | Dataset manifest, schema validation, deterministic regeneration, baseline smoke, symmetry-safe OOD split report, fixed floor, hand-feature probe, frontier metadata target floor, composition certificate leakage report, composition holdout report, source-aware generated-row accounting, generated-vs-curated target-support reporting, generated profile-search capacity reporting, replay verification, leakage-clean expanded composition splitting, deterministic floors, projection inventories, bounded support diagnostics, diagnostic shard audits, promotion-readiness gates, replay-preflight gates, exact metadata target floors, support-collapse diagnostics, capacity/source sweeps, selected-support reports, exact-shard audits, exact projection inventories, compact projection baselines, exact support expansion audits, source no-go diagnostics, topology-balanced ablations, feature-group ablations, interior-source diagnostics, pattern-limit atlases, topology hyperparameter sweeps, left-supply capacity atlases, bounded-selector diagnostics, static ordering no-gos, dynamic pairing preflights, right-supply no-go diagnostics, and learned structured model result on a harder exact target. | Reproducibility and coverage checks; `fen_string_material_gate_v0` floors; `fen_geometry_logistic_probe_v0` as a hand-feature OOD probe; train-majority, FEN/material, signature-metadata, feature-group, and learned probe floors for frontier metadata, composition targets, heuristic diagnostics, and exact signature metadata projections. | Dataset cannot be regenerated, schema validation fails, replay verification fails, exact/rejected split leaks unsupported rows into exact targets, heuristic diagnostic rows enter exact metrics, OOD splits leak by symmetry/graph/family/composition certificate or reused component identities, generated-vs-curated provenance becomes opaque, generated profile-search capacity is overclaimed, profile-search reasons disappear, rpf50 source limits are hidden, profile-inventory loss modes disappear, depth-increase, edge-ladder, or expanded mixed-hook no-gos are overclaimed as scale progress, duplicate-cluster signatures are treated as labels without a versioned target, signature-profile support is overclaimed as exact supervision without replay/split/baseline rules, signature support and promotion gates are collapsed, unseen generated or heuristic labels are hidden, projection inventories are omitted, bounded support caps are hidden, rpf20/rpf36 support is treated as a dataset before materialization/split/projection audit, materialized diagnostics are treated as exact supervision, row-contract or replay-preflight readiness is mistaken for promotion eligibility, exact metadata support limits are hidden, support-collapse rejection counts disappear, capacity-only source sweeps are overclaimed as exact support progress, support reports are overclaimed as promoted shards, signature metadata is treated as a new exact value class, exact projection unseen-label counts are hidden, material-control performance is overclaimed as decomposition learning, balanced-split or feature-ablation test lifts are cited without dev evidence, profile-index diagnostics are treated as scientific signal, interior-source capacity-only reports are treated as selected support, unbounded pattern-limit capacity is treated as selected support, left-supply capacity is treated as selected exact support, bounded-selector diagnostics are treated as full selector results, static value-spread ordering is treated as a selector improvement, dynamic preflight pairs are treated as materialized exact rows, right-side source expansion is treated as solving the Wave 66 gap, logistic-probe tuning is treated as a new model class, or learned structured models fail to beat the fixed floor and hand-feature probe. | Blocked by model evidence: Waves 57-58 improve ablation support but do not produce matched dev/test lift, Wave 59 does not solve rpf50 source support, Wave 60 shows pattern-limit removal still leaves capacity below rpf50, Wave 61 finds zero matched dev/test topology candidates under logistic-probe tuning, Wave 62 clears rpf50 capacity with left-supply variants, Wave 63 shows the first bounded selector still selects only 12 rows, Wave 64 shows static value-spread ordering worsens the bounded result to 4 rows, Wave 65 dynamic preflight reaches 137 pairs but remains 13 short before materialization, Wave 66 all-left dynamic preflight reaches 145 pairs but remains 5 short before materialization, and Wave 67 shows right-side source expansion still leaves the same 145-pair support. Next evidence needs materialization-aware dynamic selection/search that produces selected, materialized, replayed, leakage-clean exact rows or a materially different model class. | `dataset_foundry` |

## Reviewer Risks

- The domain may be too narrow. Mitigation: include explicit OOD composition and
  value-class tests, then state the domain as a controlled testbed rather than
  all of chess. Negative controls make castling rights, en-passant targets, and
  undeclared generalized boards explicit exclusions. The current mate-in-one row
  is a terminal-frontier exception, and the formal `switch` row is outside the
  chess domain by explicit `cgt_canonical` encoding.
- Exact labels may be expensive. Mitigation: report throughput, shard size,
  proof-check rate, and generator failure accounting. Wave 6 records exact row
  provenance, certificate digests, shard hash, rejected-row reasons, and
  duplicate checks for 1000 rows, but it does not yet benchmark throughput.
- Aesthetic metrics may look subjective. Mitigation: keep metric definitions in
  `docs/agency_metrics.md`, separate them from human-facing gallery examples,
  and report negative controls. The current slice has no active aesthetic claim;
  the negative controls prevent weak decomposition or unsupported domains from
  becoming gallery evidence.
- Structured supervision may collapse to scalar proxies. Mitigation: include
  representation probes and ablations that remove temperature, decomposition,
  and option-structure labels independently. The 4/4 vertical-slice FEN smoke,
  2/3 value-class majority smoke, and 0.2 Wave 6 FEN-gate accuracy keep this
  risk open rather than resolving it.
