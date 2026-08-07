# Partizan ecosystem compatibility

This document records the intended first public release train. It is the
compatibility authority for Partizan, Thermograph, Bitmesh, and Astralbase.
Repository READMEs provide package-specific detail.

## Repository responsibilities

| Repository | Release candidate | Toolchain floor | Public responsibility |
| --- | --- | --- | --- |
| Partizan | `partizan-cgt` 0.1.0 | Python 3.10, Rust 1.88 | Candidate generation, acquisition policies, exact-admission orchestration, replay records, and repertoire inspection |
| Thermograph | `thermograph` 0.1.0 | Rust 1.85 | Exact bounded comparison and semantic canonicalization for explicit finite normal-play games; approximate thermography |
| Bitmesh | `bitmesh` 0.1.0 | Rust 1.88 | Conservative structural decomposition certificates for supplied orthodox-chess boards |
| Astralbase | `astralbase` 0.1.0 | Rust 1.88 | Bounded predecessor exploration and proof propagation from caller-declared seeds |

Each result inherits the intersection of the guarantees supplied by its input
records. A structural certificate, legal-move replay, finite-game value, and
research-policy decision remain separate authorities.

## Intended v0.1 dependency set

```text
Partizan 0.1.0
├── Thermograph 0.1.0
├── Bitmesh 0.1.0
└── Astralbase 0.1.0
    ├── Thermograph 0.1.0  [dataset feature]
    └── Bitmesh 0.1.0      [dataset feature]
```

Release-candidate CI may patch these dependencies to reviewed public commits.
Published releases must resolve from the registry without path or Git patches.

## Versioned compatibility surfaces

The following surfaces require explicit compatibility review:

- Thermograph structural, literal, and semantic identity namespaces;
- Thermograph canonical catalogue ordering and named resource profiles;
- Bitmesh certificate magic values, payload versions, canonical ordering, and
  digests;
- Astralbase proof-state meanings, dataset schema identifiers, manifests, and
  deterministic sample bytes;
- Partizan target, proposal, verifier, repertoire, adapter, and comparison
  certificate schemas; and
- cross-repository bindings that record an upstream package, profile, schema,
  or content digest.

An incompatible serialized change requires a new schema, payload version,
magic value, or domain-separated identity. Existing v0.1 fixtures remain
verifiable.

Partizan's bounded-chess generator emits adapter v0.2 for this release train.
Its projection payload is unchanged; v0.2 records the final hardened upstream
commits. The v0.1 schema, source map, adapter identity domain, and golden record
remain available for historical validation and replay.

## Supported release checks

The first release train targets Linux, macOS, and Windows. Rust packages test
their minimum supported Rust version and current stable Rust. Partizan tests
Python 3.10 as its declared floor and must add representative current-Python
wheel coverage before publication.

Every public package must pass:

1. locked format, lint, test, and documentation gates;
2. package assembly inspection;
3. installation into a clean consumer environment;
4. its documented five-minute example;
5. the shared identity and certificate conformance corpus where applicable;
6. dependency, license, and advisory review; and
7. deterministic artifact verification.

## Release order

1. Publish Thermograph 0.1.0 and confirm its docs.rs build.
2. Publish Bitmesh 0.1.0 and confirm its docs.rs build.
3. Resolve Astralbase against those registry releases, run its independent
   chess-oracle lane, publish 0.1.0, and confirm its docs.rs build.
4. Resolve Partizan against the three registry releases, build and test its
   source distribution and wheel matrix, then publish `partizan-cgt` 0.1.0.

Registry publication, immutable tags, and GitHub releases require an explicit
maintainer review after all dry-run artifacts have been inspected.

## Branch and artifact policy

The repositories converge on `main` as the default branch. Required checks
protect that branch after the migration. Existing commit-bound research
records remain valid, and repository history stays intact.

Large generated research outputs follow [`artifact_policy.md`](artifact_policy.md).
Small conformance fixtures and their manifests remain in the repository.

The shared day-two semantic-ID fixture lives at
`tests/fixtures/semantic/day2-semantic-ids-v1.txt` in Partizan and at
`conformance/day2-semantic-ids-v1.txt` in Thermograph. Both implementations
must reproduce its complete 22-ID set from all 256 literal games through
birthday two.
