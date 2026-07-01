# Research Claims

This table is the paper spine. A claim is not active until it has evidence,
baselines, and a falsification condition.

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
SHA-256 `37abac744ee87fe1b79a6d75729477765b319f7f8e3c14c675b3fb5a60ecf392`,
with 17 rows (12 exact fixture-number composition certificates, 5 rejected
composition controls). The companion symmetry split report
`docs/composition_hard_target_wave_17_symmetry_split_report.json` has zero
position, symmetry, exact-certificate, decomposition, composition,
qualified component-root, component-value, component-pair, and result-value
cross-split leakage. This is still a plumbing result: exact rows use declared
fixture sums over verified component value digests, not legal chess value
proofs or model results.

| ID | Claim | Current Evidence Status | Required Evidence | Baselines | Falsification Condition | Current Blocker / Next Evidence | Owner |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C1 | Exact game-structure labels expose agency information not captured by scalar outcome labels. | Unproven. Current artifacts prove only that terminal, terminal-frontier, formal switch, deterministic frontier rows, and the Wave 17 composition plan can be serialized with provenance. `docs/agency_metrics.md` defines candidate metrics, but no agency metric has a baseline-beating model result. | Dataset rows with exact labels at useful scale, agency metrics, and representation probes comparing structured labels against scalar labels. | Scalar WDL/DTM model, material features, random labels; `fen_string_material_gate_v0` and `fen_geometry_logistic_probe_v0` are baselines, not agency evidence. | Scalar-supervised or hand-feature controls match structured-supervised models on agency probes and OOD tests. | Needs Wave 17 composition hard targets whose agency metrics are not solved by hand geometry and whose exact labels pass target-support and leakage gates. | `research_director`, `model_lab` |
| C2 | Certified decomposition improves generalization on composed positions. | Blocked by exactness. Negative controls and rejected rows show weak, unchecked, or absent strict decomposition must not enter exact training; the BMCOMPOSE v1 digest is a provenance contract, not yet value-composition evidence. The Wave 17 fixture shard proves nested certificate transport and leakage accounting only. | Strict decomposition certificates, verified composed positions, and a composition OOD split. | Full-board scalar model, no-decomposition structured model. | Decomposition-aware models do not improve on held-out compositions. | Needs non-fixture Wave 17 positive composition rows, root/value/result verification, and a held-out composition split at scale. The current fixture exact row and `no_strict_decomposition`/composition-control rejections only protect against overclaiming. | `topology_engineer`, `model_lab` |
| C3 | Temperature and option-value structure provide measurable proxies for initiative and forcedness. | Partially plumbed, not evidenced for chess. The artifacts include one formal `switch` fixture with temperature 1 and chess terminal-frontier rows with certified child-option metadata. Wave 15 adds an exact-only `frontier_mean` target with KRK-family OOD shift, but frontier temperature is constant and exact chess labels remain scalar `number`. | Exact temperature labels, option-value distributions, positive controls, and negative controls. | Legal move count, material delta, engine scalar evaluation, and train-majority frontier metadata floors. | Temperature or option-structure targets fail to predict forcedness or move urgency beyond simple controls. | Needs chess-derived exact nonterminal positions whose target includes nonconstant temperature or non-number exact values, not only frontier metadata. | `theory_steward`, `exact_value_engineer` |
| C4 | Model-guided search can discover compact, verified, agency-rich positions more efficiently than random or heuristic search. | Unproven and scale-blocked. The current slice has no model-guided search logs, verified gallery, leakage checks, or ranking comparisons. | Verified gallery, search logs, leakage checks, and beauty/agency metric rankings. | Random generation, material heuristic, handcrafted metric search. | Verified discovery precision does not beat baselines under matched budget. | Needs matched-budget discovery runs over labels that passed exact, domain, and decomposition gates. Negative controls only define what must be excluded. | `discovery_curator`, `verifier_red_team` |
| C5 | The benchmark supports reproducible evaluation of exact-label learning under OOD shift. | Partially evidenced. Current artifacts support schema, deterministic regeneration, manifest accounting, mixed FEN/CGT encodings, frontier shards, deterministic split/leakage reporting, symmetry-safe split reporting, KRK and KNK family-held-out splits, fixed deterministic floors, hand-feature probes, one exact-only frontier metadata target report, an executable Wave 17 composition plan, and a fixture-level BMCOMPOSE shard with composition leakage reporting. Learned structured-label performance and exact-value learning remain unproven. | Dataset manifest, schema validation, deterministic regeneration, baseline smoke, symmetry-safe OOD split report, fixed floor, hand-feature probe, frontier metadata target floor, composition certificate leakage report, and learned structured model result on a harder target. | Reproducibility and coverage checks; `fen_string_material_gate_v0` floors; `fen_geometry_logistic_probe_v0` as a hand-feature OOD probe; train-majority floors for frontier metadata. | Dataset cannot be regenerated, schema validation fails, exact/rejected split leaks unsupported rows into exact targets, OOD splits leak by symmetry/graph/family/composition certificate, or learned structured models fail to beat the fixed floor and hand-feature probe. | Blocked by target hardness and diversity: Wave 14 shows exact-vs-rejected KNK is solved by hand geometry, Wave 15 is only a small frontier-mean target with constant temperature, and Wave 17 is currently fixture-level. Next evidence must scale composition rows and add structured/neural baselines that beat hand probes on harder tasks. | `dataset_foundry` |

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
