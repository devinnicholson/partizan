# Expanded Family Frontier Wave 12 Manifest

This manifest records the deterministic KQK+KRK+KBK+KNK frontier JSONL
shard generated for Wave 12 material-family breadth validation.

## Artifact

- Schema version: `partizan.dataset_label.v0`
- JSONL artifact: `/private/tmp/partizan-expanded-family-frontier-wave-12.jsonl`
- Artifact SHA-256: `328c32715eecf5a2dc745042543022dd89c47af8c07f5c8faec22372d8661713`
- Total rows: 4000
- Exact rows: 800
- Rejected rows: 3200

## Source

- Source repo: `../astralbase`
- Source commit: `a52ad62ba2542c6aed4ad641a1675a91e44f4103`
- Generator command: `cd ../astralbase && cargo run --quiet -- --expanded-family-frontier-label-shard --limit-per-family 1000`
- Runner command: `python3 engine/orchestrator.py expanded-family-frontier-label-shard`
- Validator command: `python3 agents/label_schema.py validate /private/tmp/partizan-expanded-family-frontier-wave-12.jsonl`
- Split report command: `python3 engine/ml_model.py split-report /private/tmp/partizan-expanded-family-frontier-wave-12.jsonl --output docs/expanded_family_frontier_wave_12_split_report.json`
- Symmetry split report command: `python3 engine/ml_model.py split-report /private/tmp/partizan-expanded-family-frontier-wave-12.jsonl --split-key-mode symmetry --output docs/expanded_family_frontier_wave_12_symmetry_split_report.json`
- Symmetry KNK holdout report command: `python3 engine/ml_model.py family-holdout-report /private/tmp/partizan-expanded-family-frontier-wave-12.jsonl --holdout-family astralbase_knk_frontier_generator --split-key-mode symmetry --output docs/expanded_family_frontier_wave_12_holdout_knk_symmetry_report.json`
- Symmetry KNK holdout baseline command: `python3 engine/ml_model.py split-baseline-report /private/tmp/partizan-expanded-family-frontier-wave-12.jsonl --holdout-family astralbase_knk_frontier_generator --split-key-mode symmetry --output docs/expanded_family_frontier_wave_12_holdout_knk_symmetry_baseline_report.json`
- Symmetry KNK holdout geometry-probe command: `python3 engine/ml_model.py geometry-probe-report /private/tmp/partizan-expanded-family-frontier-wave-12.jsonl --holdout-family astralbase_knk_frontier_generator --split-key-mode symmetry --output docs/expanded_family_frontier_wave_12_holdout_knk_symmetry_geometry_probe_report.json`
- Determinism check: the runner compares two generator invocations before writing.

## Label Counts

- `exact`: 800
- `rejected`: 3200

## Exact Value Class Counts

- `number`: 800

## Exact Solver Scope Counts

- `immediate_terminal_frontier`: 800

## Frontier Value Class Counts

- `game_tree`: 800

## Certificate Kind Counts

- `immediate-checkmate-enumeration+thermograph-exact-value+bitmesh-domain-gate`: 800

## Position Encoding Counts

- `fen`: 4000

## Rejection Counts By Status

- `unsupported`: 3200

## Rejection Counts By Reason

- `no_strict_decomposition`: 3200

## Leakage And Uniqueness Checks

- Duplicate row IDs: 0
- Duplicate positions: 0
- Duplicate D4 symmetry positions: 917
- Duplicate exact certificate digests: 0
- Position-hash split symmetry-key cross-split violations: 269
- Symmetry-hash split symmetry-key cross-split violations: 0
- Symmetry-hash KNK holdout symmetry-key cross-split violations: 0
- Symmetry-hash KNK holdout FEN-gate baseline accuracy: train 0.202, dev
  0.179, test 0.200
- Symmetry-hash KNK holdout geometry-probe accuracy: train 0.978, dev 0.975,
  test 1.000

## Notes

- Exact rows remain the only rows eligible as exact supervision targets.
- Rejected rows stay in the shard so unsupported inputs are visible and counted.
- The runner injects `ASTRALBASE_CODE_COMMIT` so exact-row provenance and this
  manifest record the same astralbase Git commit.
