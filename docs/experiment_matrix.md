# Experiment Matrix

This matrix tracks executable artifacts before broader modeling claims. The
current vertical-slice rows are smoke gates only: they verify shard, schema,
terminal-frontier exact labeling, and loader plumbing, not agency, OOD
generalization, or broad exact-value learning.

| ID | Dataset / Artifact | Command | Target | Gate / Baseline | Result on current shard | Does not prove | Falsification / Next Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `w4_shard_generation` | `/private/tmp/partizan-wave-03.jsonl`; SHA-256 `5cc22df67075907fbcbae8f611bfdabcb39f5ad502e7880e51f61937acdb3a88`; source commit `4117a61252a9dc49da48eb80848997de275b6f9b` | `python3 engine/orchestrator.py sample-label-shard` | Generate and record the current dataset-label shard. | Deterministic runner with two generator invocations before write; manifest row-count and hash accounting. | 4 rows: 1 exact terminal checkmate, 1 exact mate-in-one terminal-frontier row, 2 rejected unsupported rows (`castling_rights`, `no_strict_decomposition`). | Model quality, OOD coverage, domain completeness, decomposition generalization, or broad exact-label learning. | Fails if regeneration is nondeterministic, the manifest hash does not match the artifact, row counts drift without manifest updates, or rejected rows are promoted to exact supervision. |
| `w4_schema_validation` | Same shard, schema `partizan.dataset_label.v0`. | `python3 agents/label_schema.py validate /private/tmp/partizan-wave-03.jsonl` | Validate row shape, payload exclusivity, exact provenance, and rejected-row reasons before loading. | `label_schema` gate; negative controls documented in `docs/verification_gates.md`. | `labels: ok (4 row(s))` on the current shard. | Semantic domain acceptance, strict decomposition proof, value correctness, or train/test leakage safety. | Fails if malformed mixed-payload rows validate, exact rows without provenance validate, rejected rows without reasons validate, or future loaders bypass the schema gate. |
| `w4_baseline_eval_smoke` | Same shard, 4 rows: 2 exact, 2 rejected. | `python3 engine/ml_model.py baseline-eval /private/tmp/partizan-wave-03.jsonl` | `label_kind` exact-vs-rejected. `exact.value_class` remains exact-only and is evaluated only as a trivial two-row, one-class smoke check. | `fen_string_material_gate_v0`: derives FEN string, board occupancy, castling, and material-count features; predicts rejected when castling rights are present or only two kings are present, otherwise exact. | Deterministic smoke metrics: 4/4 exact-vs-rejected accuracy; confusion matrix has 2 exact true positives and 2 rejected true positives; `exact.value_class` support is 2, all `number`, leave-one-out majority accuracy 2/2. | Generalization, non-number value-class learning, exact CGT value prediction, domain-boundary completeness, or any broader behavioral claim. | Fails if exact/rejected labels are not loaded deterministically, rejected rows enter exact-value supervision, or the smoke baseline changes without an updated artifact and explanation. |

## Notes

- Exact rows and rejected rows are separated by `label_kind`; rejected rows are never used as `exact.value_class` supervision.
- The value-class baseline is now executable but still trivial: both exact rows
  are `number`, so it does not test class discrimination.
- Current metrics are plumbing checks for the current vertical slice and should
  not be used as evidence beyond that slice.
- Negative-control rows are not training data. They define expected failures for schema, domain, decomposition, and exact-training gates.
