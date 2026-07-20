# Wave 69 Stage A suite freeze

Status: implementation contract. This command creates pre-verification inputs;
it does not call Astralbase and cannot produce verifier results.

## Frozen suite

`scripts/freeze_wave69_stage_a_suite.py` reads the committed Wave 69 registry,
selects its six `stage_a` targets, and derives each unsigned seed as the first
64 bits (big endian) of:

```text
SHA256(b"partizan/w69/pool/v1\0" + b"stage_a" + b"\0" + target_id_utf8)
```

For every target it invokes `discovery-generate-pool-v1` for exactly 1,024
unique proposals. That command performs two separate Python-process
generations and writes the canonical receipt. The suite then freezes a
Candidate Pool manifest v0.2 and invokes the baseline `freeze` command to
commit 1,000 random orderings and the fixed heuristic ordering. All policy
orders therefore exist before the first verifier result.

The canonical suite manifest uses `partizan.wave69_stage_suite.v0.1`. It binds
the registry, preregistration, implementation components, four clean commits,
and six full input bundles. Each bundle contains repository-relative paths and
byte hashes for its target, proposals, generation receipt, pool manifest, and
policy orders. The suite contains no result or report fields. A later,
separate post-verification evidence manifest must bind this immutable suite ID
plus results and reports, revalidate every full ledger, and recompute reports;
a self-hashed aggregate is not sufficient.

The post-verification handoff is `partizan.baseline_suite_input.v0.1`. Its six
bundles add result and report references to the frozen target, proposal, pool,
and policy-order references. It must bind this file through a canonical
`pre_verification_suite_ref` and cross-check the six shared input references
byte-for-byte. That artifact is intentionally produced only after P; it is
neither an input to this command nor a field in this pre-result suite.

Pre-result validation uses an exact recursive inventory, not a filename
heuristic. The Stage A root must contain only `suite-manifest.json` and the six
target-ID digest directories. Each target directory must contain exactly
`target.json`, `proposals.jsonl`, `generation-receipt.json`,
`pool-manifest.json`, and `policy-orders.json`. Extra files or directories,
hidden entries, symbolic links, and hard-link aliases are rejected.

## Clean-HEAD three-commit workflow

The implementation commit contains the preregistration, registry, generator,
baseline freezer, suite freezer, schemas, and tests. The generated Stage A tree
is deliberately ignored at `data/discovery/wave_69/stage_a/`. This lets all
six pools and policy commitments be written while Partizan remains at the same
clean implementation HEAD required by generator, freeze, and later verifier
gates.

The safe sequence uses three distinct commits:

1. **I (implementation):** commit the integrated implementation and
   preregistration. Check out I with clean Partizan, Astralbase, Bitmesh, and
   Thermograph repositories.
2. Run the suite freeze at clean HEAD I. Inspect with `--check-only`; this
   performs no subprocess or verifier call. Force-add only the complete
   pre-result suite, pools, receipts, and policy orders, then create **P (pre-result)**.
   P is the cryptographic temporal proof that all order
   commitments existed before results.
3. Create a clean detached worktree at I. Materialize the pre-result files
   from P into I's ignored `data/discovery/wave_69/stage_a/` tree. Because the
   files remain ignored, status stays clean and both the manifest's Partizan
   source commit and every generator `code_commit` remain I. Run verification
   only there. Copy complete verifier ledgers back to the main worktree at P,
   recompute reports from the full bundles, and create **E (evidence)**.
4. Require the post-result integrity gate on all six targets: at least 95%
   `verified_match + verified_nonmatch`, at least eight verified matches, at
   least four symmetry-unique matches, and zero `internal_error` outcomes.
   Stage B remains blocked unless the separate evidence manifest attests GO.

For reproduction, repeat the detached-I materialization from P, verify there,
and compare the recomputed ledgers and reports to E. Neither P nor E replaces
I as the implementation commit recorded in source provenance.

## Commands

```bash
python3 scripts/freeze_wave69_stage_a_suite.py
python3 scripts/freeze_wave69_stage_a_suite.py --check-only
```

After verification has produced exactly one canonical
`verifier-results.jsonl` beside each target, finalize the result-bound analysis
without invoking Astralbase:

```bash
python3 scripts/freeze_wave69_stage_a_suite.py --finalize-baseline-input
```

This recomputes each `baseline-report.json`, builds and validates
`baseline-suite-input.json` with its exact `pre_verification_suite_ref`, then
aggregates and validates `baseline-suite-report.json`. Existing derived files
are accepted only when their bytes exactly match the recomputation.

The build command refuses a dirty repository, a registry or preregistration
whose bytes are absent from HEAD, a source-commit mismatch, an existing
nonempty Stage A output tree, any pool other than v0.2, any proposal count
other than 1,024, missing receipt provenance, invalid policy commitments, or
any untracked file outside the ignored tree. The check-only command reloads
and revalidates all canonical input bundles and rejects any result/verifier
entry inside the exact pre-verification tree.

Wave 70 material and Stage B material are out of scope. Learned ranking also
remains NO-GO until the semantic target-view gate in the Wave 69
preregistration is satisfied.
