# Composition Hard Target Wave 17 Manifest

This manifest records the deterministic Wave 17 composition-certificate
hard-target JSONL shard generated from the astralbase BMCOMPOSE fixture.

## Artifact

- Schema version: `partizan.dataset_label.v0`
- JSONL artifact: `/private/tmp/partizan-composition-hard-target-wave-17.jsonl`
- Artifact SHA-256: `b0218d2c215ca9cc08b495393391bc09b43f1acac7bf58178caaafdb10cd5e77`
- Total rows: 4
- Exact rows: 1
- Rejected rows: 3

## Source

- Source repo: `../astralbase`
- Source commit: `f0557f71586559584d598f9b240f39a2c7aea937`
- Generator command: `cd ../astralbase && cargo run --quiet -- --composition-hard-target-shard --limit 4`
- Runner command: `python3 engine/orchestrator.py composition-hard-target-shard --limit 4`
- Validator command: `python3 agents/label_schema.py validate /private/tmp/partizan-composition-hard-target-wave-17.jsonl`
- Determinism check: the runner compares two generator invocations before writing.

## Label Counts

- `exact`: 1
- `rejected`: 3

## Exact Value Class Counts

- `number`: 1

## Exact Solver Scope Counts

- `composition_certificate_fixture`: 1

## Frontier Value Class Counts

- none

## Certificate Kind Counts

- `bitmesh-bmcompose-v1+thermograph-exact-value+fixture-sum`: 1

## Position Encoding Counts

- `fen`: 4

## Rejection Counts By Status

- `excluded`: 3

## Rejection Counts By Reason

- `missing_component_value_digest`: 1
- `stale_composition_digest`: 1
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
