# Experiment Matrix

This matrix tracks executable artifacts before broader modeling claims. Wave 3
rows are smoke gates only: they verify shard, schema, and loader plumbing, not
agency, OOD generalization, or exact-value learning.

| ID | Dataset / Artifact | Command | Target | Gate / Baseline | Result on current shard | Does not prove | Falsification / Next Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `w3_shard_generation` | `/private/tmp/partizan-wave-03.jsonl`; SHA-256 `6d5f3ac6e520fab355597eafccb80adc7b24f46cc6aef96166eb26eaf7a5266b`; source commit `9c45f5e35c8d634dd5badb8a245e3da28af47c97` | `python3 engine/orchestrator.py sample-label-shard` | Generate and record the Wave 3 dataset-label shard. | Deterministic runner with two generator invocations before write; manifest row-count and hash accounting. | 3 rows: 1 exact terminal checkmate, 2 rejected unsupported rows (`castling_rights`, `no_strict_decomposition`). | Model quality, OOD coverage, domain completeness, decomposition generalization, or exact-label learning. | Fails if regeneration is nondeterministic, the manifest hash does not match the artifact, row counts drift without manifest updates, or rejected rows are promoted to exact supervision. |
| `w3_schema_validation` | Same shard, schema `partizan.dataset_label.v0`. | `python3 agents/label_schema.py validate /private/tmp/partizan-wave-03.jsonl` | Validate row shape, payload exclusivity, exact provenance, and rejected-row reasons before loading. | `label_schema` gate; negative controls documented in `docs/verification_gates.md`. | `labels: ok (3 row(s))` on the current shard. | Semantic domain acceptance, strict decomposition proof, value correctness, or train/test leakage safety. | Fails if malformed mixed-payload rows validate, exact rows without provenance validate, rejected rows without reasons validate, or future loaders bypass the schema gate. |
| `w3_baseline_eval_smoke` | Same shard, 3 rows: 1 exact, 2 rejected. | `python3 engine/ml_model.py baseline-eval /private/tmp/partizan-wave-03.jsonl` | `label_kind` exact-vs-rejected only. `exact.value_class` remains exact-only and is not evaluated with one exact row. | `fen_string_material_gate_v0`: derives FEN string, board occupancy, castling, and material-count features; predicts rejected when castling rights are present or only two kings are present, otherwise exact. | Deterministic smoke metrics: 3/3 exact-vs-rejected accuracy; confusion matrix has 1 exact true positive and 2 rejected true positives; `exact.value_class` support is 1 and status is `not_meaningful`. | Generalization, value-class learning, exact CGT value prediction, domain-boundary completeness, or any broader behavioral claim. | Fails if exact/rejected labels are not loaded deterministically, rejected rows enter exact-value supervision, or the smoke baseline changes without an updated artifact and explanation. |

## Notes

- Exact rows and rejected rows are separated by `label_kind`; rejected rows are never used as `exact.value_class` supervision.
- The value-class baseline is recorded as `not_meaningful` until at least two exact rows permit deterministic holdout metrics.
- Current metrics are plumbing checks for the Wave 3 slice and should not be used as evidence beyond that slice.
- Negative-control rows are not training data. They define expected failures for schema, domain, decomposition, and exact-training gates.
