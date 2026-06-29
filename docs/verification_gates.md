# Verification Gates

Status: Wave 3 vertical-slice negative controls.

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
- `exact_training_split_gate`: future dataset loader policy; trains exact
  targets only from schema-valid rows with `label_kind: exact`,
  `exact.status: verified`, complete provenance, and accepted domain and
  decomposition checks.

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
because KRK exact rows include 156 `frontier_mean=2` cases. Frontier temperature
is still constant on this shard, so this gate is a first option-structure audit,
not a temperature-learning result.
