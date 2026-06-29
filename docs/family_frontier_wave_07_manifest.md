# Family Frontier Wave 07 Manifest

This manifest records the deterministic KQK+KRK terminal-frontier JSONL shard
generated for Wave 7 generator-family split validation.

## Artifact

- Schema version: `partizan.dataset_label.v0`
- JSONL artifact: `/private/tmp/partizan-family-frontier-wave-07.jsonl`
- Artifact SHA-256: `46581eddc4ef5ff745722b5559615a5298d5dd5f003e61d66ff23bdb8e352e31`
- Total rows: 2000
- Exact rows: 400
- Rejected rows: 1600

## Source

- Source repo: `../astralbase`
- Source commit: `fb5f3a91aedac2d177ea788c827054710a78330a`
- Generator command: `cd ../astralbase && cargo run --quiet -- --family-frontier-label-shard --limit-per-family 1000`
- Runner command: `python3 engine/orchestrator.py family-frontier-label-shard`
- Validator command: `python3 agents/label_schema.py validate /private/tmp/partizan-family-frontier-wave-07.jsonl`
- Split report command: `python3 engine/ml_model.py split-report /private/tmp/partizan-family-frontier-wave-07.jsonl --output docs/family_frontier_wave_07_split_report.json`
- Symmetry split report command: `python3 engine/ml_model.py split-report /private/tmp/partizan-family-frontier-wave-07.jsonl --split-key-mode symmetry --output docs/family_frontier_wave_07_symmetry_split_report.json`
- Family holdout report command: `python3 engine/ml_model.py family-holdout-report /private/tmp/partizan-family-frontier-wave-07.jsonl --holdout-family astralbase_krk_frontier_generator --output docs/family_frontier_wave_07_holdout_krk_report.json`
- Symmetry family holdout report command: `python3 engine/ml_model.py family-holdout-report /private/tmp/partizan-family-frontier-wave-07.jsonl --holdout-family astralbase_krk_frontier_generator --split-key-mode symmetry --output docs/family_frontier_wave_07_holdout_krk_symmetry_report.json`
- Symmetry family holdout baseline command: `python3 engine/ml_model.py split-baseline-report /private/tmp/partizan-family-frontier-wave-07.jsonl --holdout-family astralbase_krk_frontier_generator --split-key-mode symmetry --output docs/family_frontier_wave_07_holdout_krk_symmetry_baseline_report.json`
- Determinism check: the runner compares two generator invocations before writing.

## Label Counts

- `exact`: 400
- `rejected`: 1600

## Exact Value Class Counts

- `number`: 400

## Exact Solver Scope Counts

- `immediate_terminal_frontier`: 400

## Frontier Value Class Counts

- `game_tree`: 400

## Certificate Kind Counts

- `immediate-checkmate-enumeration+thermograph-exact-value+bitmesh-domain-gate`: 400

## Position Encoding Counts

- `fen`: 2000

## Rejection Counts By Status

- `unsupported`: 1600

## Rejection Counts By Reason

- `no_strict_decomposition`: 1600

## Leakage And Uniqueness Checks

- Duplicate row IDs: 0
- Duplicate positions: 0
- Duplicate D4 symmetry positions: 414
- Duplicate exact certificate digests: 0
- Position-hash split symmetry-key cross-split violations: 137
- Position-hash KRK holdout train/dev symmetry-key cross-split violations: 38
- Symmetry-hash split symmetry-key cross-split violations: 0
- Symmetry-hash KRK holdout symmetry-key cross-split violations: 0
- Symmetry-hash KRK holdout FEN-gate baseline accuracy: train 0.198, dev
  0.215, test 0.200

## Notes

- Exact rows remain the only rows eligible as exact supervision targets.
- Rejected rows stay in the shard so unsupported inputs are visible and counted.
- The runner injects `ASTRALBASE_CODE_COMMIT` so exact-row provenance and this
  manifest record the same astralbase Git commit.
