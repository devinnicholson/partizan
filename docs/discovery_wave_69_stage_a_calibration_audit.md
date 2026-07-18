# Wave 69 Stage A calibration audit

Decision: **NO-GO. Do not open Stage B.**

The evidence is internally sound, but the generator/support calibration fails
the preregistered gate on every target. All 6,144 verifier rows and all
derived reports validate from source bytes; the failure is empirical rather
than an integrity failure.

## Audit boundary

- Pre-result commit: `411ad31aca9811a20f1d24fdc57528951b3d591a`
- Bound implementation commit: `604ab9ef1e7bfc4bcc8dd8fb0c19ebdc59cf0e5a`
- Frozen suite: `suite-sha256:709c91e45d5315d9b681636eaf4348a7d4a4edad229771ee7bbbe6bca9fbd60b` (`13ff886b3103829a4ed93e48e24a23766cff627a26e43020b066ab2d13dd6fba`)
- Post-result suite input: `baseline-suite-input-sha256:6b199cd4b1c9cd205791143f197270ee89b7543ad6894818649c14f4be0d6648` (`4f44de051a3ce8def03147d50e2520819c7e15b064a919ad5b9d0a6dde3146b6`)
- Macro report: `baseline-suite-report-sha256:d9dd52f4e595871747affecebdacb82f3be5be12f7f80d5ae0a537c2feeb381e` (`132ec3f65a435c8bc81845ab58e40961979cd1a8838642ca693e908577e97154`)

The pre-result commit is the direct child of the implementation commit and
changes only the 31 frozen Stage A input artifacts. The post-result suite
crosswalks exactly to those target, proposal, pool, receipt, and policy-order
references.

## Preregistered gates

| Target | Certified coverage | Match | Unique | Nonmatch | Rejected | Error | Gate |
|---|---:|---:|---:|---:|---:|---:|---|
| `052f4191fdcb` | 75/1024 (7.324%) | 0 | 0 | 75 | 949 | 0 | **FAIL** |
| `07de65c35e84` | 86/1024 (8.398%) | 0 | 0 | 86 | 938 | 0 | **FAIL** |
| `41bb336e2bee` | 87/1024 (8.496%) | 0 | 0 | 87 | 937 | 0 | **FAIL** |
| `73492503d817` | 82/1024 (8.008%) | 0 | 0 | 82 | 942 | 0 | **FAIL** |
| `8ceee173bf9c` | 96/1024 (9.375%) | 0 | 0 | 96 | 928 | 0 | **FAIL** |
| `f1b5c956d745` | 94/1024 (9.180%) | 0 | 0 | 94 | 930 | 0 | **FAIL** |

Each target needed at least 95% certified coverage, eight matches, four
symmetry-unique matches, and zero internal errors. Every target passes only
the zero-error condition. Suite totals are 520 certified nonmatches, 5,624
rejections, zero matches, zero unique matches, and zero internal errors;
certified coverage is 520/6,144 (8.464%).

## Baselines

No target has a verified match, so heuristic, all 1,000 fixed random
permutations per target, and generator ordinal have DE@64, DE@256, and
DE@1024 equal to zero. Macro heuristic DE@256 and random mean DE@256 are
both zero; the frozen upper-tail proportion is 1,000/1,000 and the contrast
and target-bootstrap interval are exactly zero. These are calibration
diagnostics, not paper evidence.

## Generator failure diagnosis

All 5,624 rejections occurred at the conservative decomposition gate. The
lossless verifier responses divide them into four causes:

- `BarrierPieceCanBeCaptured`: 2,722 (48.400% of rejections)
- `RequiresStrictDecomposition`: 2,315 (41.163%)
- `BarrierPawnNotFrozen`: 391 (6.952%)
- `PieceCanEnterOtherComponent`: 196 (3.485%)

The target-blind mixed-piece grammar therefore does not preserve the theorem
conditions needed by Bitmesh often enough to support an exact-identity search.
Any successor calibration must use a new generator version and new
preregistration. It should construct conservative two-component separation by
design; this result does not authorize filtering or repairing the frozen Stage
A rows after verification.

## Integrity and separation

Public validators accepted six target specs, 6,144 proposals, six receipts,
six pool manifests, six policy-order sets, 6,144 verifier results, six
baseline reports, the suite input, and the macro report. Validator replay
recomputed request/response hashes, gate rows, exact certificate digests,
result identities, repository provenance, order joins, report identities, and
macro aggregation. No Stage B or Wave 70 proposal/result artifact exists.

The preregistered failure policy therefore requires a new code commit,
seed/version, and pool under an amended preregistration. Targets must not be
swapped, and this Stage A result must not be promoted to evidence.
