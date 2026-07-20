# Partizan v0.1 release blockers

The implementation is an alpha release candidate. Gates 1 and 2 below are now
resolved; the rest are not resolved by this branch and must remain visible in
any handoff or release note:

1. **Project license: resolved.** Partizan is licensed
   [GPL-3.0-or-later](../LICENSE) (see `LICENSE`, `engine/Cargo.toml`,
   `engine/gate_s_checker/Cargo.toml`, and `pyproject.toml`). Code
   contributions still wait on separate contribution terms (e.g. a CLA/DCO),
   which remain unpublished.
2. **Third-party license review: resolved.** Shakmaty's own repository
   (confirmed via its GitHub license metadata, not just Maturin's SBOM
   heuristic) is GPL-3.0. It is a direct, load-bearing dependency of
   `engine/src/lib.rs` and `engine/gate_s_checker`, compiled into the
   `partizan._native` extension, so the whole project is licensed
   GPL-3.0-or-later to stay compatible with that obligation. `bitmesh` and
   `astralbase` independently depend on Shakmaty too; `thermograph` does not.
3. **Upstream publication:** Bitmesh, Thermograph, and Astralbase 0.1.0 are not
   yet registry releases. This branch declares their versions but uses external
   release-candidate patches for tests.
4. **Historical artifact provenance:** `docs/reproducibility.md` records three
   earlier release-candidate commits. Public regeneration requires publishing
   those refs or reviewing and re-freezing the artifact with public inputs.
5. **Cross-platform and MSRV evidence:** the public workflow covers Linux,
   macOS, Windows, Rust 1.88, and Python 3.10. Local validation covers macOS
   arm64 with Rust 1.92 and Python 3.14.
6. **Wave 47 immutable provenance:** its 13 rows still record
   `code_commit=workspace`. Their bytes and report linkage are frozen, but
   source regeneration equivalence is not claimed.
7. **Release state:** no package was published and no tag, GitHub release, DOI,
   or external service state was created.

P04 and P05 are scientific boundaries rather than release chores: learned
benefit remains negative/null, while chess temperature, learned agency, and
model-guided discovery remain unvalidated and outside the release claim.
