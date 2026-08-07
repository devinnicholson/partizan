# Contributing

Partizan is a claim-sensitive research codebase. Keep changes narrow,
reproducible, and explicit about the evidence they add and the boundary of that
evidence. Every commit contributed through a pull request must carry a
Developer Certificate of Origin sign-off as described in [`DCO.md`](DCO.md).

1. Open an issue describing the domain, expected result, and affected claim ID.
2. Add or update a deterministic fixture before changing an algorithm.
3. Never mix `exact`, `rejected`, `heuristic`, and `prediction` rows.
4. Every promoted exact composition row must carry the P02 decomposition,
   component-value, composition, and result digests.
5. Record seeds, commands, versions, hashes, and a resource envelope.
6. Report negative/null results and leakage failures in the same place as
   positive results.
7. Treat artistic agency, tension, and discovery as interpretation. Technical
   claims require their own declared evidence and gate.

Changes to bounded short-game semantics must also:

1. Preserve the explicit `{left|right}` serialization and both literal digest
   namespaces.
2. Preserve all four comparison outcomes and replay every dependency in a
   closed proof DAG.
3. Add soundness, irreducibility, idempotence, and mutation controls for any
   canonical rewrite.
4. Keep comparison certificate v1 frozen. Additive semantic fields require a
   new schema identifier and independent verifier coverage.
5. Run the exhaustive 65,536-comparison day-2 gate and the 256-game,
   22-semantic-ID canonicalization gate.
6. Record the named resource profile and every stricter rewrite limit used by
   a certificate or experiment.

Run the commands in the root README. Pull requests must pass format, strict
Clippy, strict Rustdoc, locked tests, Python tests with zero required skips, all
Wave validators, and frozen-artifact verification.

Sign each commit with:

```console
git commit -s
```

The sign-off certifies the statement in [`DCO.md`](DCO.md). Copyright remains
with contributors. Partizan is licensed
[GPL-3.0-or-later](LICENSE). Report vulnerabilities through
the private channel described in [`SECURITY.md`](SECURITY.md).
