# Partizan v0.1 release blockers

The implementation is an alpha release candidate. Gates 1, 2, and 4 below are
now resolved; the rest are not resolved by this branch and must remain visible
in any handoff or release note:

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
3. **Upstream publication:** Bitmesh, Thermograph, and Astralbase are now
   licensed and pushed to their public `master` branches (each also GPL-3.0-
   or-later, matching their own Shakmaty dependency, except Thermograph, which
   has no dependencies and is dual MIT OR Apache-2.0). None are yet published
   as `0.1.0` registry releases on crates.io; this branch still declares their
   versions but uses external release-candidate patches for tests. Publishing
   requires the registry account credentials of whoever runs `cargo publish`
   for each crate, which is outside what an assistant should hold or execute.
4. **Historical artifact provenance: resolved.** The three commits recorded in
   `docs/reproducibility.md` (Astralbase `7ad71b5`, Bitmesh `28aee03`,
   Thermograph `57df043`) previously existed only on local, unpushed
   `codex/readiness-*` branches in each sibling repository; they were
   unreachable from any public ref. All three have now been pushed to their
   respective public `master` branches and are confirmed reachable via each
   repository's commit API.
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
