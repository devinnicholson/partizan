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

| ID | Claim | Current Evidence Status | Required Evidence | Baselines | Falsification Condition | Current Blocker / Next Evidence | Owner |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C1 | Exact game-structure labels expose agency information not captured by scalar outcome labels. | Unproven. Current artifacts prove only that terminal, terminal-frontier, formal switch, and 1000 deterministic KQK rows can be serialized with provenance; they have no agency metrics, representation probes, or scalar-label controls. | Dataset rows with exact labels at useful scale, agency metrics, and representation probes comparing structured labels against scalar labels. | Scalar WDL/DTM model, material features, random labels; `fen_string_material_gate_v0` is only a loader smoke baseline. | Scalar-supervised controls match structured-supervised models on agency probes and OOD tests. | Blocked by task definition: Wave 6 scales frontier accounting, not agency. Next wave needs agency targets and scalar-control probes over frontier/discovery splits. | `research_director`, `model_lab` |
| C2 | Certified decomposition improves generalization on composed positions. | Blocked by exactness. Negative controls and rejected rows show weak, unchecked, or absent strict decomposition must not enter exact training; they are guardrails, not positive evidence. | Strict decomposition certificates, verified composed positions, and a composition OOD split. | Full-board scalar model, no-decomposition structured model. | Decomposition-aware models do not improve on held-out compositions. | Needs machine-checked positive decomposition certificates and a held-out composition split. The current `no_strict_decomposition` rejection only protects against overclaiming. | `topology_engineer`, `model_lab` |
| C3 | Temperature and option-value structure provide measurable proxies for initiative and forcedness. | Partially plumbed, not evidenced for chess. The artifacts include one formal `switch` fixture with temperature 1 and 201 chess terminal-frontier rows with child-option metadata, but the exact chess labels remain scalar `number` targets. | Exact temperature labels, option-value distributions, positive controls, and negative controls. | Legal move count, material delta, engine scalar evaluation. | Temperature fails to predict forcedness or move urgency beyond simple controls. | Needs chess-derived exact nonterminal positions whose target includes temperature or option-value classes, not just frontier metadata. | `theory_steward`, `exact_value_engineer` |
| C4 | Model-guided search can discover compact, verified, agency-rich positions more efficiently than random or heuristic search. | Unproven and scale-blocked. The current slice has no model-guided search logs, verified gallery, leakage checks, or ranking comparisons. | Verified gallery, search logs, leakage checks, and beauty/agency metric rankings. | Random generation, material heuristic, handcrafted metric search. | Verified discovery precision does not beat baselines under matched budget. | Needs matched-budget discovery runs over labels that passed exact, domain, and decomposition gates. Negative controls only define what must be excluded. | `discovery_curator`, `verifier_red_team` |
| C5 | The benchmark supports reproducible evaluation of exact-label learning under OOD shift. | Partially evidenced. Current artifacts support schema, deterministic regeneration, manifest accounting, mixed FEN/CGT encodings, frontier shards, deterministic split/leakage reporting, symmetry-safe split reporting, one symmetry-safe family-held-out KRK test split, a fixed deterministic floor, and a trainable hand-feature probe on that split. Learned structured-label performance and exact-value learning remain unproven. | Dataset manifest, schema validation, deterministic regeneration, baseline smoke, symmetry-safe OOD split report, fixed floor, hand-feature probe, and learned structured model result. | Reproducibility and coverage checks; `fen_string_material_gate_v0` for exact-vs-rejected smoke and KRK holdout floor; `fen_geometry_logistic_probe_v0` as a hand-feature OOD probe. | Dataset cannot be regenerated, schema validation fails, exact/rejected split leaks unsupported rows into exact targets, OOD splits leak by symmetry/graph/family, or learned structured models fail to beat the fixed floor and hand-feature probe. | Blocked by structured model evaluation and target diversity: Wave 11 provides a strong hand-feature OOD probe, but no neural/structured model result yet, and all generated chess exact targets are `number`. Next wave needs a trainable structured baseline, more piece families, and non-number chess-derived targets. | `dataset_foundry` |

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
- Aesthetic metrics may look subjective. Mitigation: separate metric definitions
  from human-facing gallery examples, and report negative controls. The current
  slice has no active aesthetic claim; the negative controls prevent weak
  decomposition or unsupported domains from becoming gallery evidence.
- Structured supervision may collapse to scalar proxies. Mitigation: include
  representation probes and ablations that remove temperature, decomposition,
  and option-structure labels independently. The 4/4 vertical-slice FEN smoke,
  2/3 value-class majority smoke, and 0.2 Wave 6 FEN-gate accuracy keep this
  risk open rather than resolving it.
