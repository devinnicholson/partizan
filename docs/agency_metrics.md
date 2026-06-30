# Agency And Aesthetic Metrics

Status: Wave 16 hard-target specification.

These metrics are paper-facing only after they are attached to exact,
schema-valid rows and reported against leakage-safe splits. A metric can be
useful as a search or analysis signal before then, but it cannot support an
agency or beauty claim without verifier-backed labels and controls.

## Agency Metrics

### Terminal Option Leverage

Measures how much the side to move can force terminal outcomes from the current
position.

- Eligible rows: `label_kind: exact`, `solver_scope:
  immediate_terminal_frontier`.
- Required fields: `legal_move_count`, `terminal_child_count`,
  `checkmating_move_count`, `stalemating_move_count`.
- Formula: `terminal_child_count / legal_move_count`.
- Positive controls: rows with multiple terminal children and mixed terminal
  outcomes.
- Negative controls: rejected no-strict-decomposition rows and rows with zero
  terminal children.

### Choice Asymmetry

Measures whether terminal options are concentrated in one player-action type.

- Eligible rows: exact terminal-frontier rows.
- Formula: `(checkmating_move_count - stalemating_move_count) /
  max(1, terminal_child_count)`.
- Expected range: `[-1, 1]`.
- Positive controls: positions with both checkmating and stalemating children.
- Falsification: the metric is explained entirely by legal move count or
  material family under matched split controls.

### Frontier Mean Shift

Measures the certified option-structure mean attached to terminal-frontier
metadata.

- Eligible rows: exact rows with `exact.value.frontier_mean`.
- Current evidence: Wave 15 exposes a KRK-family OOD shift from train-only
  `frontier_mean=1` to KRK test labels `{1, 2}`.
- Required report: target-support coverage must list train labels, split
  labels, and unseen target labels by split.
- Falsification: a train-majority or material-family lookup baseline explains
  the target under a symmetry-safe OOD split.

### Temperature Signal

Measures nonconstant thermograph temperature or equivalent hot-game structure.

- Eligible rows: exact rows with nonconstant certified temperature targets.
- Current status: not active for chess rows. Wave 12 frontier temperature is
  constant at `-1`; the formal switch fixture is not chess-derived.
- Activation gate: at least two temperature labels must appear in train and at
  least one OOD split, with target-support coverage reported.

## Aesthetic Metrics

### Compactness

Rewards positions that express a verified target with fewer active pieces and
fewer legal moves.

- Formula candidate: `1 / (1 + piece_count + legal_move_count)`.
- Positive controls: minimal certified examples within a family.
- Negative controls: positions whose label is rejected or heuristic.

### Surprise Against Hand Probes

Rewards positions where exact structure is not solved by the current hand
geometry probe.

- Required baseline: `fen_geometry_logistic_probe_v0` or stronger successor.
- Positive controls: exact OOD rows where hand-probe confidence is wrong or low.
- Falsification: hand-coded geometry reaches near-perfect accuracy on the
  target, as in the Wave 14 KNK holdout.

### Symmetry Novelty

Rewards examples that are not duplicate up to D4 board symmetry within the
training or gallery set.

- Required key: `fen_d4` canonical key from the split reports.
- Gate: gallery candidates with a D4 key seen in training are ineligible for
  OOD aesthetic claims.

## Reporting Requirements

- Every metric report must name eligible rows and excluded rows.
- Every OOD report must include raw-position, D4-symmetry, certificate, family,
  and target-support leakage checks.
- Every model or search result must compare against fixed floors and hand
  probes before supporting an agency or aesthetic claim.
