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

### Changed

- Rust dependencies now use version `0.1.0` instead of sibling paths.
- Dataset output defaults now use repository-local ignored artifacts rather than
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
