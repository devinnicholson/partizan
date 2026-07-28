# Changelog

All notable changes to this project will be documented here. Versions follow
Semantic Versioning once an owner-approved release is published.

## [Unreleased]

### Added

- Root scope, installation, architecture, development, contribution, citation,
  and release documentation.
- Maturin mixed Python/Rust packaging for the `partizan` module.
- Versioned `partizan.event_stream.v0.1` generation and validation.
- Frozen Wave 47 artifact manifest and release verification command.
- Required local test harness without silent artifact/module skips.
- Cross-platform CI definition and clean-room registry-patch instructions.
- Exact fixed-value comparison and repertoire search for finite normal-play
  short games.
- Deterministic reversible-option candidate generation, replay certificates,
  representation/literal-game fingerprints, and transition classification.
- The `partizan` generate, explore, search, verify, inspect, and compare
  commands.
- A bounded chess-to-short-game adapter with Astralbase domain gating,
  Bitmesh certificate provenance, Shakmaty legal-move expansion, Thermograph
  structural identity, typed refusals, and deterministic native replay.
- The `partizan` chess-adapt, chess-verify, chess-target, chess-candidate, and
  chess-search commands.
- A same-horizon KQK fixture whose distinct literal trees are exactly equal
  under Conway comparison and enter one repertoire as a literal-game crossing.
- Bounded exact comparison for explicit finite normal-play short games with
  four outcomes, collision-checked literal identities, named resource
  profiles, and closed proof DAGs.
- Independent deterministic semantic canonicalization with domination and
  reversibility traces, domain-separated semantic IDs, typed limits, equality
  soundness, irreducibility, and idempotence audits.
- Frozen comparison certificate v1 semantics and an additive v2 certificate
  that binds independently recomputed semantic IDs and rewrite limits.
- Exhaustive source-only validation across all 65,536 ordered day-2
  comparisons and all 256 day-2 canonicalizations, yielding 22 semantic IDs.

### Changed

- Rust dependencies now use version `0.1.0` instead of sibling paths.
- Dataset output defaults now use repository-local ignored artifacts instead of
  system temporary paths.
- The formal domain is consolidated as the versioned v0.1 contract.
- Licensed the project GPL-3.0-or-later, matching the Shakmaty (GPL-3.0)
  dependency compiled into the native extension. Raised the minimum Maturin
  version to 1.9.3 for PEP 639 `license`/`license-files` support.
- The historical reproducibility commits for Astralbase, Bitmesh, and
  Thermograph are now reachable: each sibling repository's own readiness work
  (license, CI hardening) was pushed to its public `master` branch.

### Limitations

- Upstream registry publication (crates.io) for Bitmesh, Thermograph, and
  Astralbase remains an owner-controlled gate requiring registry credentials.
- Immutable tags and public release publication remain owner-controlled gates.
- Contribution terms (e.g. a CLA/DCO) remain unpublished.
- Learned benefit, agency, chess temperature, and model-guided discovery remain
  future research questions.
