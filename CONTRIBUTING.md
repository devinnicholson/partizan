# Contributing

Partizan is a claim-sensitive research codebase. Keep changes narrow,
reproducible, and explicit about the evidence they add and the boundary of that
evidence.

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

Run the commands in the root README. Pull requests must pass format, strict
Clippy, strict Rustdoc, locked tests, Python tests with zero required skips, all
Wave validators, and frozen-artifact verification.

Partizan is licensed [GPL-3.0-or-later](LICENSE). Contribution review still
waits on the project owner publishing separate contribution terms (e.g. a
CLA/DCO).
