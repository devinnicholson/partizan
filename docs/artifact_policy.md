# Artifact policy

Partizan keeps executable source, specifications, compact fixtures, and
content-addressed manifests in Git. Large generated outputs belong in a
versioned research artifact release.

## Retained in the repository

- source code and build configuration;
- JSON Schemas and other executable contracts;
- compact positive, negative, corruption, and conformance fixtures;
- preregistered protocols that govern a retained result;
- manifests containing filenames, byte lengths, SHA-256 digests, schema IDs,
  source revisions, commands, seeds, and resource envelopes; and
- small summary tables needed to understand a public API guarantee.

## Published as release artifacts

- candidate or verifier streams measured in megabytes;
- model checkpoints and optimizer state;
- repeated-run traces and event logs;
- full experiment banks and bootstrap samples;
- rendered media source bundles; and
- intermediate reports whose claims are already represented by a compact
  authority and manifest.

GitHub Releases can carry software-adjacent artifacts. A long-lived research
deposit with a DOI is appropriate for evidence cited by a publication. Each
deposit must be immutable or versioned and must expose the manifest beside the
payloads.

## Promotion gate

Generated output begins under an ignored local artifact directory. Promotion
requires review of:

1. the governing protocol and claim;
2. provenance and source revisions;
3. schema validation;
4. deterministic replay or its declared stochastic controls;
5. payload hashes and byte lengths;
6. privacy, license, and redistribution rights; and
7. the durable artifact destination.

Tests consume compact fixtures or fetch no network data. Clean checkout and
package tests therefore remain deterministic.

## Historical records

Existing public commits and their bound artifacts remain reachable. Repository
history stays intact because research manifests and validation records cite
those commit identities. New large outputs follow this policy so repository
growth remains bounded.
