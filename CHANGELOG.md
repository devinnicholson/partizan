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

### Limitations

- License selection, upstream registry publication, immutable tags, and public
  release publication remain owner-controlled gates.
- No learned benefit, agency, chess-temperature, or discovery claim is active.
