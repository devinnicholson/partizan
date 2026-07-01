# Composition Hard Target Wave 17 Manifest

This manifest records the deterministic Wave 17 composition-certificate
hard-target JSONL shard generated from the astralbase BMCOMPOSE fixture.

## Artifact

- Schema version: `partizan.dataset_label.v0`
- JSONL artifact: `/private/tmp/partizan-composition-hard-target-wave-17.jsonl`
- Artifact SHA-256: `37abac744ee87fe1b79a6d75729477765b319f7f8e3c14c675b3fb5a60ecf392`
- Total rows: 17
- Exact rows: 12
- Rejected rows: 5

## Source

- Source repo: `../astralbase`
- Source commit: `2a7c1c8beeeba6dfd3a01fadcfe31e0d4c1e0869`
- Generator command: `cd ../astralbase && cargo run --quiet -- --composition-hard-target-shard --limit 17`
- Runner command: `python3 engine/orchestrator.py composition-hard-target-shard --limit 17`
- Validator command: `python3 agents/label_schema.py validate /private/tmp/partizan-composition-hard-target-wave-17.jsonl`
- Determinism check: the runner compares two generator invocations before writing.

## Label Counts

- `exact`: 12
- `rejected`: 5

## Exact Value Class Counts

- `number`: 12

## Exact Solver Scope Counts

- `composition_certificate_fixture`: 12

## Frontier Value Class Counts

- none

## Certificate Kind Counts

- `bitmesh-bmcompose-v1+thermograph-exact-value+fixture-sum`: 12

## Position Encoding Counts

- `fen`: 17

## Rejection Counts By Status

- `excluded`: 5

## Rejection Counts By Reason

- `duplicate_component_root`: 1
- `missing_component_value_digest`: 1
- `stale_composition_digest`: 1
- `unsupported_composition_value`: 1
- `weak_decomposition`: 1

## Leakage And Uniqueness Checks

- Duplicate row IDs: 0
- Duplicate positions: 0
- Duplicate exact certificate digests: 0

## Notes

- Exact rows remain the only rows eligible as exact supervision targets.
- Rejected rows stay in the shard so unsupported inputs are visible and counted.
- The runner injects `ASTRALBASE_CODE_COMMIT` so exact-row provenance and this
  manifest record the same astralbase Git commit.
