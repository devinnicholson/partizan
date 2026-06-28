# Verification Gates

Status: Wave 3 vertical-slice negative controls.

The fixture at `agents/fixtures/wave_03_negative_controls.jsonl` is not a
training shard. It intentionally mixes rows that the current schema validator
must reject with schema-valid `rejected` rows that future domain and
decomposition checkers must keep out of exact training.

## Gate Responsibilities

- `label_schema`: `agents/label_schema.py validate`; catches malformed or
  ambiguous JSONL rows before any training or evaluation loader reads them.
- `domain_gate`: future executable domain checker; rejects inputs outside
  `formal_domain:first_constrained_chess:v0`.
- `decomposition_certificate_gate`: future bitmesh/astralbase checker; accepts
  exact decomposition only with a strict, validated independence certificate.
- `exact_training_split_gate`: future dataset loader policy; trains exact
  targets only from schema-valid rows with `label_kind: exact`,
  `exact.status: verified`, complete provenance, and accepted domain and
  decomposition checks.

## Wave 3 Negative Controls

| Row ID | Control | Intended Gate | Expected Rejection Or Exclusion Reason |
| --- | --- | --- | --- |
| `w3-neg-mixed-exact-prediction-001` | Exact and prediction payloads appear in one row. | `label_schema` | A row must contain exactly one label payload object; exact verifier labels and model predictions cannot be mixed. |
| `w3-neg-mixed-rejected-heuristic-001` | Rejected and heuristic payloads appear in one row. | `label_schema` | A row must contain exactly one label payload object; rejected status and heuristic estimates cannot be mixed. |
| `w3-neg-exact-missing-provenance-001` | Exact row omits provenance. | `label_schema` | Exact rows require provenance with generator, verifier, domain definition, seed, config hash, and certificate. |
| `w3-neg-rejected-missing-reasons-001` | Rejected row has no reasons. | `label_schema` | Rejected rows require `rejected.reasons` as a non-empty list of strings. |
| `w3-neg-castling-rights-001` | FEN contains castling rights. | `domain_gate` | The first constrained exact domain allows no castling rights; the row is schema-valid only as `rejected.status: unsupported`. |
| `w3-neg-en-passant-target-001` | FEN contains an en-passant target square. | `domain_gate` | The first constrained exact domain allows no en-passant target; the row is schema-valid only as `rejected.status: unsupported`. |
| `w3-neg-weak-decomposition-001` | Locked-pawn structure is only weakly decomposed. | `decomposition_certificate_gate` | Weak decomposition lacks a strict independence certificate and is excluded from exact labels. |
| `w3-neg-unchecked-decomposition-exact-001` | Exact row carries top-level decomposition components and an unchecked certificate. | `label_schema`, then `decomposition_certificate_gate` | Top-level `components` is ambiguous under the label schema; even if normalized later, unchecked decomposition cannot support an exact label. |
| `w3-neg-generalized-board-undeclared-001` | Generalized-board encoding is used under the standard first constrained domain. | `domain_gate` | Generalized boards require a separately declared shard; standard `first_constrained_chess:v0` accepts only standard 8x8 FEN. |

## Exact Training Policy

No row in `wave_03_negative_controls.jsonl` is eligible as exact training data:

- Schema-invalid rows fail before training split construction.
- Unsupported domain rows are represented as `label_kind: rejected`.
- Weak or unchecked decomposition rows are represented as `label_kind:
  rejected` or are schema-invalid.
- Future loaders should treat this fixture as a negative-control artifact, not
  as a source shard, even when individual rejected rows are schema-valid.
