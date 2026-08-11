# Partizan v0.1 release blockers

The implementation is an alpha release candidate. Gates 1, 2, 4, 5, and 7 have
completed evidence. Open gates 3, 6, and 8 must remain visible in any
handoff or release note:

1. **Project license: resolved.** Partizan is licensed
   [GPL-3.0-or-later](../LICENSE) (see `LICENSE`, `engine/Cargo.toml`,
   `engine/gate_s_checker/Cargo.toml`, and `pyproject.toml`). Contributions use
   the checked-in Developer Certificate of Origin 1.1 sign-off.
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
5. **Cross-platform and MSRV evidence: resolved.** The public workflow for
   commit `7dcd5cb` passed on Linux, macOS, and Windows with Rust 1.88 and
   Python 3.10. The run is preserved as
   [GitHub Actions run 29781815615](https://github.com/devinnicholson/partizan/actions/runs/29781815615).
   Local validation also covers macOS arm64 with Rust 1.92 and Python 3.14.
6. **Wave 47 immutable provenance:** its 13 rows still record
   `code_commit=workspace`. Their bytes and report linkage are frozen, but
   source regeneration equivalence is not claimed.
7. **Research snapshot: resolved.** `v0.1.0-alpha.2` provides an immutable
   GitHub research snapshot. No crate, wheel, or stable `v0.1.0` package has
   been published; those distribution claims remain blocked by gate 3.
8. **Bounded short-game release evidence:** the independent Python comparison
   and canonicalization lanes have local source-only validation, including all
   65,536 ordered day-2 comparisons, 256 canonicalizations, and 22 semantic
   identities. The Python and Thermograph implementations reproduce the same
   frozen 22-ID set locally. The additive v2 certificate, shared conformance
   fixture, and package changes still require a clean public cross-platform CI
   run after integration.

P04 and P05 are scientific boundaries separate from release chores: learned
benefit remains negative/null, while chess temperature, learned agency, and
model-guided discovery remain unvalidated and outside the release claim.
