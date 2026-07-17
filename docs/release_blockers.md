# Partizan v0.1 release blockers

The implementation is an alpha release candidate. The following gates are not
resolved by this branch and must remain visible in any handoff or release note:

1. **Project license:** the copyright owner has not selected or added a license.
   Do not publish, redistribute, or solicit contributions as an open-source
   project until this is resolved.
2. **Third-party license review:** Maturin's generated SBOM warns that Shakmaty
   0.27 declares the legacy expression `GPL-3.0+`. The owner must review all
   dependency obligations and compatibility before choosing Partizan's terms.
3. **Upstream publication:** Bitmesh, Thermograph, and Astralbase 0.1.0 are not
   yet registry releases. This branch declares their versions but uses external
   release-candidate patches for tests.
4. **Immutable public refs:** CI pins three candidate commits. Those exact
   commits must be available on the public upstream repositories before CI can
   run successfully.
5. **Cross-platform evidence:** the workflow covers Linux, macOS, and Windows,
   but only the local macOS arm64 run is evidenced here.
6. **Wave 47 immutable provenance:** its 13 rows still record
   `code_commit=workspace`. Their bytes and report linkage are frozen, but
   source regeneration equivalence is not claimed.
7. **Release state:** no package was published and no tag, GitHub release, DOI,
   or external service state was created.

P04 and P05 are scientific boundaries rather than release chores: learned
benefit remains negative/null, while chess temperature, learned agency, and
model-guided discovery remain unvalidated and outside the release claim.
