# Wave 32 Fresh Component-Value Supply No-Go

Status: no-go for promoted Wave 32 clean-scale shard.

## Evidence Checked

- Base Astralbase commit: `46f6607d6003c7d74f11aacb4584f57f69d053e1`
- Wave 32 plan: `agents/waves/wave_32_fresh_component_value_profile_supply.json`
- Experimental profile report: `/tmp/astralbase-w32-profile-search.json`
- Experimental profile report SHA-256:
  `b9b169d9a08750f53a0e8ebb3a899f2b716fb77b0176e4560fd693fc39b2dc37`

## Decision

Do not promote a Wave 32 clean composition shard from this attempt. The bounded
rank-3/rank-6 supplemental profile-source experiment stayed fast enough, but it
did not materially improve clean generated support.

## Result

The experimental profile-search report found:

- `left_profile_count`: 15
- `right_profile_count`: 14
- `selected_row_count`: 7
- generated topology counts: 3 local-move, 2 asymmetric-fan, 2 pawn-phalanx
- rejection counts:
  - `component_value_digest_reuse_before_materialization`: 616
  - `materialization_failure`: 7

The attempt therefore remains below the model-readiness floor of 30 generated
exact rows with at least 10 rows in each generated depth-two topology family.

## Next Direction

The next generator attempt should use a more substantive profile source change
than rank-3/rank-6 variants. Candidate directions are new independent component
geometries, a versioned value rule that exposes fresh component values while
remaining replay-verifiable, or a formally documented group-aware split rule.
Any such change must keep rejected controls out of exact target metrics and must
preserve the current no-reuse claim unless the split rule is explicitly changed.
