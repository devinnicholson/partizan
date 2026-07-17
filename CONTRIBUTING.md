# Contributing

Partizan is a claim-sensitive research codebase. Keep changes narrow,
reproducible, and explicit about what evidence they do and do not add.

1. Open an issue describing the domain, expected result, and affected claim ID.
2. Add or update a deterministic fixture before changing an algorithm.
3. Never mix `exact`, `rejected`, `heuristic`, and `prediction` rows.
4. Every promoted exact composition row must carry the P02 decomposition,
   component-value, composition, and result digests.
5. Record seeds, commands, versions, hashes, and a resource envelope.
6. Report negative/null results and leakage failures in the same place as
   positive results.
7. Do not describe artistic agency, tension, or discovery as technical evidence.

Run the commands in the root README. Pull requests must pass format, strict
Clippy, strict Rustdoc, locked tests, Python tests with zero required skips, all
Wave validators, and frozen-artifact verification.

Licensing is an unresolved owner gate. Contributions should not be accepted
until the project owner publishes contribution and licensing terms.
