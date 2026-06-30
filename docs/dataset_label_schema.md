# Dataset Label Schema v0

This scaffold implements the `label_integrity` and `reproducibility` gates in
`agents/research_network.json`. Dataset rows must make label status explicit so
exact verifier output, rejected rows, heuristic estimates, and model predictions
cannot be silently mixed.

The current schema version is:

```text
partizan.dataset_label.v0
```

## Common JSONL Row Fields

Every row is one JSON object with these required fields:

- `schema_version`: exactly `partizan.dataset_label.v0`.
- `row_id`: stable row identifier.
- `domain`: domain/version identifier, preferably pointing at the formal domain
  definition.
- `position`: object with `encoding` and `text`.
  - `encoding: fen` is used for standard chess positions.
  - `encoding: cgt_canonical` is used for formal thermograph CGT fixtures.
- `label_kind`: one of `exact`, `rejected`, `heuristic`, or `prediction`.

Every row must contain exactly one payload object whose key matches
`label_kind`: `exact`, `rejected`, `heuristic`, or `prediction`.

## Exact Rows

Exact rows are the only rows eligible as exact supervision targets by default.
They require:

- `exact.status`: must be `verified`.
- `exact.value`: exact value payload, intentionally flexible for the first
  thermograph/value serialization.
- `exact.value_class`: coarse value class currently emitted as `number` or
  `switch`, with schema room for `star`, `up`, `down`, and `game_tree` as
  thermograph coverage expands.
- `provenance.code_commit`.
- `provenance.generator`.
- `provenance.generator_config_hash`.
- `provenance.random_seed`.
- `provenance.domain_definition`.
- `provenance.verifier`.
- `provenance.verifier_version`.
- `provenance.certificate`.

For Wave 17 composition rows, `provenance.certificate` must become a structured
object rather than an opaque string. The planned shape is:

- `kind`: composition certificate kind/version.
- `digest`: aggregate composition certificate digest.
- `decomposition_digest`: bitmesh strict decomposition certificate digest.
- `composition_digest`: bitmesh BMCOMPOSE v1 digest.
- `component_values`: non-empty object mapping component-root identifiers to
  exact value digest strings.
- `result_value_digest`: digest of the verified composed exact value payload.

The schema gate must reject top-level `components` as ambiguous. Component
metadata belongs under `provenance.certificate`, where it can be tied to the
verified decomposition and exact-value payloads. A composition certificate binds
provenance; it does not by itself prove that the component values or composed
result are correct.

## Rejected Rows

Rejected rows are allowed and expected for unsupported positions, verifier
errors, and explicit exclusions. They require:

- `rejected.status`: one of `unsupported`, `error`, or `excluded`.
- `rejected.reasons`: non-empty list of strings.

Rejected rows do not need exact-label provenance because they are not exact
supervision. They still make the failed state visible to satisfy the no-silent
row-drop rule.

## Heuristic Rows

Heuristic rows are non-exact estimates and require:

- `heuristic.method`.
- `heuristic.method_version`.
- `heuristic.outputs`.

They must not include `exact` or `prediction` payloads.

## Prediction Rows

Prediction rows are model outputs and require:

- `prediction.model_id`.
- `prediction.model_version`.
- `prediction.checkpoint`.
- `prediction.outputs`.

They must not include `exact`, `rejected`, or `heuristic` payloads.

## Ambiguity Rules

The validator rejects rows that omit `label_kind`, include no payload, include
multiple payloads, or put label-like values in legacy top-level fields such as
`mean_value`, `temperature`, `components`, `expanded_nodes`, or `error`.

## Validation Commands

```bash
python3 agents/label_schema.py validate agents/fixtures/label_rows.valid.jsonl
python3 agents/label_schema.py self-test
```
