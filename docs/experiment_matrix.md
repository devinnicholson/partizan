# Experiment Matrix

This matrix tracks executable baselines before broader modeling claims.

| ID | Dataset | Command | Supervised target | Baseline | Result on current shard | Does not prove |
| --- | --- | --- | --- | --- | --- | --- |
| `w3_baseline_eval_scaffold` | `/private/tmp/partizan-wave-03.jsonl` (`partizan.dataset_label.v0`, 3 rows: 1 exact, 2 rejected; source commit `9c45f5e35c8d634dd5badb8a245e3da28af47c97`) | `python3 engine/ml_model.py baseline-eval /private/tmp/partizan-wave-03.jsonl` | `label_kind` exact-vs-rejected only. `exact.value_class` remains exact-only and is not evaluated with one exact row. | `fen_string_material_gate_v0`: derives FEN string, board occupancy, castling, and material-count features; predicts rejected when castling rights are present or only two kings are present, otherwise exact. | Deterministic smoke metrics: 3/3 exact-vs-rejected accuracy on the vertical slice; no randomness or seed. | Generalization, value-class learning, exact CGT value prediction, domain-boundary completeness, or any broader behavioral claim. |

## Notes

- Exact rows and rejected rows are separated by `label_kind`; rejected rows are never used as `exact.value_class` supervision.
- The value-class baseline is recorded as `not_meaningful` until at least two exact rows permit deterministic holdout metrics.
- Current metrics are plumbing checks for the Wave 3 slice and should not be used as evidence beyond that slice.
