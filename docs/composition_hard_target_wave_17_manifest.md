# Composition Hard Target Wave 17 Manifest

This manifest records the deterministic Wave 17 composition-certificate
hard-target JSONL shard generated from the astralbase BMCOMPOSE fixture.

## Artifact

- Schema version: `partizan.dataset_label.v0`
- JSONL artifact: `/private/tmp/partizan-composition-hard-target-wave-17.jsonl`
- Artifact SHA-256: `8a15c6043a9129b90b94e2ffeb78a04a3c1d8076b5f4aa932183bec6f60d859d`
- Total rows: 21
- Exact rows: 16
- Rejected rows: 5

## Source

- Source repo: `../astralbase`
- Source commit: `8f90d2b3183ae516dc13854849d1f683fa73f728`
- Generator command: `cd ../astralbase && cargo run --quiet -- --composition-hard-target-shard --limit 21`
- Runner command: `python3 engine/orchestrator.py composition-hard-target-shard --limit 21`
- Validator command: `python3 agents/label_schema.py validate /private/tmp/partizan-composition-hard-target-wave-17.jsonl`
- Determinism check: the runner compares two generator invocations before writing.

## Label Counts

- `exact`: 16
- `rejected`: 5

## Exact Value Class Counts

- `number`: 16

## Exact Solver Scope Counts

- `composition_certificate_fixture`: 16

## Frontier Value Class Counts

- none

## Certificate Kind Counts

- `bitmesh-bmcompose-v1+thermograph-exact-value+fixture-sum`: 16

## Position Encoding Counts

- `fen`: 21

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
