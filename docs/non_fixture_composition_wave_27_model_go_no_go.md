# Wave 27 Composition Model Go/No-Go

Status: no-go for learned decomposition-benefit claims.

## Evidence Checked

- Clean shard: `/tmp/astralbase-w27-clean-composition.jsonl`
- Clean shard SHA-256: `7e1085cb0a212d7f3e620885c11bf709f8ce2bfa28204c664bbc0aa02875ef9c`
- Astralbase source commit: `6333b2ea2a367f80c6b3e27eea6ea077b2ca600e`
- Replay: `row_count=21`, `checked_exact_rows=18`, `skipped_rejected_rows=3`, `skipped_non_target_rows=0`
- Source holdout report: `docs/non_fixture_composition_source_wave_27_holdout_report.json`
- Baseline report: `docs/non_fixture_composition_source_wave_27_baseline_report.json`
- Topology report: `docs/non_fixture_composition_topology_wave_27_benchmark_report.json`

## Decision

Do not train or claim a decomposition-benefit model result on this slice yet.
The split is leakage-clean, but generated-source test support is only 7 exact
rows. That is enough to validate the split/reporting machinery, not enough to
support a NeurIPS-grade learned-model claim.

## Current Floors

The Wave 27 generated-source baseline report validates with
`--fail-on-leakage` and records these overall deterministic accuracies:

- `train_majority`: 0.0556
- `fen_material_feature_majority`: 0.5556
- `fixture_component_sum`: 0.1667

The FEN/material floor is strong enough that any learned model must beat it on
the same leakage-clean split and also report per-topology/source slices,
unseen-label support, and abstentions.

## Unblockers

- Increase leakage-clean generated support beyond the current 7 exact rows.
- Preserve zero duplicate and cross-split composition identity violations.
- Keep rejected controls out of exact target metrics.
- Train decomposition-aware, no-decomposition structured, and full-board
  controls on the same split only after support is large enough.
- Treat failure to beat `fen_material_feature_majority` as a blocker, not as a
  negative result to hide.
