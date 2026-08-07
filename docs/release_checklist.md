# Partizan v0.1 release checklist

This checklist governs an immutable Partizan release. Publication has a
separate maintainer review after source, package, and clean-install gates.

## Contract freeze

- [ ] Public Python, CLI, Rust, schema, and certificate surfaces are inventoried.
- [ ] Compatibility-sensitive payloads have golden fixtures.
- [ ] [`ecosystem_compatibility.md`](ecosystem_compatibility.md) names the exact dependency set.
- [ ] All limitations in the README match executable behavior.
- [ ] The changelog describes every user-visible change.

## Dependency release

- [ ] Thermograph 0.1.0 resolves from crates.io and builds on docs.rs.
- [ ] Bitmesh 0.1.0 resolves from crates.io and builds on docs.rs.
- [ ] Astralbase 0.1.0 resolves from crates.io and builds on docs.rs.
- [ ] Partizan's release lockfile contains no path or Git patch.

## Verification

- [ ] Linux, macOS, and Windows CI pass from a clean checkout.
- [ ] Minimum Rust and supported Python checks pass.
- [ ] Cross-language semantic identity conformance passes.
- [ ] Certificate mutation and corruption suites pass.
- [ ] Independent chess-oracle evidence is current for the pinned dependency set.
- [ ] Dependency, license, and advisory checks have no unresolved release blocker.
- [ ] Every documented quickstart runs in CI.

## Distribution

- [ ] `maturin sdist` completes and the archive contents are reviewed.
- [ ] `scripts/check_sdist_contents.py` accepts the exact source archive.
- [ ] The exact source archive builds a wheel with `maturin build --locked`;
      that wheel installs and passes bounded-game, semantic-ID,
      bounded-chess-adapter, and CLI smoke tests.
- [ ] The supported wheel matrix builds successfully.
- [ ] Every wheel installs and runs in a clean environment.
- [ ] Package metadata, license files, citation data, and project links are present.
- [ ] Checksums, an SBOM, and build provenance accompany the release artifacts.

## Publication review

- [ ] The maintainer reviewed the exact immutable artifacts.
- [ ] The registry name and version are confirmed.
- [ ] The Git tag points to the reviewed source commit.
- [ ] GitHub release notes state guarantees, limitations, and dependency versions.
- [ ] Registry publication is explicitly authorized.

After publication, verify the registry installation path from a new environment
and record the result in the release notes.
