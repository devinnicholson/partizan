# Experiment Matrix

This matrix tracks executable artifacts before broader modeling claims. The
current vertical-slice rows are smoke gates only: they verify shard, schema,
terminal-frontier exact labeling, formal switch value-class plumbing, and loader
accounting, not agency, OOD generalization, or broad exact-value learning.

| ID | Dataset / Artifact | Command | Target | Gate / Baseline | Result on current shard | Does not prove | Falsification / Next Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `w5_shard_generation` | `/private/tmp/partizan-wave-03.jsonl`; SHA-256 `4a678e9a960e2349f15d8ea09744c354718703acd553923ecd6aa7758b0b2fc4`; source commit `63c34d5dcf6f1bcfa65434d05b98e3ad9ed657bc` | `python3 engine/orchestrator.py sample-label-shard` | Generate and record the current dataset-label shard. | Deterministic runner with two generator invocations before write; manifest row-count, value-class, encoding, and hash accounting. | 5 rows: 1 exact terminal checkmate, 1 exact mate-in-one terminal-frontier row with 14 terminal children, 1 exact formal CGT switch fixture, 2 rejected unsupported rows (`castling_rights`, `no_strict_decomposition`). | Model quality, OOD coverage, chess-domain completeness, decomposition generalization, or broad exact-label learning. | Fails if regeneration is nondeterministic, the manifest hash does not match the artifact, row counts/value-class counts drift without manifest updates, or rejected rows are promoted to exact supervision. |
| `w5_schema_validation` | Same shard, schema `partizan.dataset_label.v0`. | `python3 agents/label_schema.py validate /private/tmp/partizan-wave-03.jsonl` | Validate row shape, payload exclusivity, exact provenance, rejected-row reasons, and mixed FEN/CGT encodings before loading. | `label_schema` gate; negative controls documented in `docs/verification_gates.md`. | `labels: ok (5 row(s))` on the current shard. | Semantic domain acceptance, strict decomposition proof, chess value correctness, or train/test leakage safety. | Fails if malformed mixed-payload rows validate, exact rows without provenance validate, rejected rows without reasons validate, or future loaders bypass the schema gate. |
| `w5_baseline_eval_smoke` | Same shard, 5 rows: 3 exact, 2 rejected. | `python3 engine/ml_model.py baseline-eval /private/tmp/partizan-wave-03.jsonl` | `label_kind` exact-vs-rejected over FEN rows only; `exact.value_class` over all exact rows. | `fen_string_material_gate_v0` derives FEN string/material features and excludes `cgt_canonical` rows; `exact_majority_value_class_v0` is leave-one-out majority over exact classes. | FEN smoke metrics: 4/4 exact-vs-rejected accuracy, with the formal CGT row excluded by encoding. Value-class smoke: support 3, counts `number: 2`, `switch: 1`, leave-one-out majority accuracy 2/3 and zero recall for `switch`. | Generalization, switch learning, exact CGT value prediction at scale, domain-boundary completeness, or any broader behavioral claim. | Fails if exact/rejected labels are not loaded deterministically, rejected rows enter exact-value supervision, non-FEN rows enter the FEN gate, or the value-class baseline changes without an updated artifact and explanation. |

## Notes

- Exact rows and rejected rows are separated by `label_kind`; rejected rows are never used as `exact.value_class` supervision.
- The value-class baseline is now multi-class but intentionally tiny: it exposes
  the minority `switch` class and records that a majority baseline misses it.
- Current metrics are plumbing checks for the current vertical slice and should
  not be used as evidence beyond that slice.
- Negative-control rows are not training data. They define expected failures for schema, domain, decomposition, and exact-training gates.
