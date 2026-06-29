# Frontier Wave 06 Manifest

This manifest records the deterministic KQK terminal-frontier JSONL shard
generated for Wave 6 scale-up validation.

## Artifact

- Schema version: `partizan.dataset_label.v0`
- JSONL artifact: `/private/tmp/partizan-frontier-wave-06.jsonl`
- Artifact SHA-256: `4863eea78d53adcd7eca22bfdda55c5b5eb668c46065f3ad49c019ae3bf60792`
- Total rows: 1000
- Exact rows: 200
- Rejected rows: 800

## Source

- Source repo: `../astralbase`
- Source commit: `02b0f678c70632fef0f754459fdb16d811ac9b29`
- Generator command: `cd ../astralbase && cargo run --quiet -- --frontier-label-shard --limit 1000`
- Runner command: `python3 engine/orchestrator.py frontier-label-shard`
- Validator command: `python3 agents/label_schema.py validate /private/tmp/partizan-frontier-wave-06.jsonl`
- Determinism check: the runner compares two generator invocations before writing.

## Label Counts

- `exact`: 200
- `rejected`: 800

## Exact Value Class Counts

- `number`: 200

## Exact Solver Scope Counts

- `immediate_terminal_frontier`: 200

## Frontier Value Class Counts

- `game_tree`: 200

## Certificate Kind Counts

- `immediate-checkmate-enumeration+thermograph-exact-value+bitmesh-domain-gate`: 200

## Position Encoding Counts

- `fen`: 1000

## Rejection Counts By Status

- `unsupported`: 800

## Rejection Counts By Reason

- `no_strict_decomposition`: 800

## Leakage And Uniqueness Checks

- Duplicate row IDs: 0
- Duplicate positions: 0
- Duplicate exact certificate digests: 0

## Notes

- Exact rows remain the only rows eligible as exact supervision targets.
- Rejected rows stay in the shard so unsupported inputs are visible and counted.
- The runner injects `ASTRALBASE_CODE_COMMIT` so exact-row provenance and this
  manifest record the same astralbase Git commit.
