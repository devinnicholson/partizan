# Partizan

Partizan is an alpha research suite for structural decomposition and
combinatorial-game representations in constrained chess positions. It combines
three independently versioned Rust libraries behind a small Python extension,
dataset validators, deterministic benchmark reports, and a versioned event
stream intended as input to Partizan Fugue.

This is a research-release candidate, not a general chess CGT solver. No
license has yet been selected by the copyright owner, so the repository is not
ready for third-party redistribution or reuse. Package publication, immutable
release tags, and licensing remain release-owner gates.

The exact remaining owner/external blockers are tracked in
[docs/release_blockers.md](docs/release_blockers.md).

## Supported v0.1 surface

- Parse orthodox FEN through Shakmaty.
- Expose Bitmesh locked-pawn and conservative structural-partition
  observations.
- Run a terminal checkmate/stalemate plumbing smoke through Astralbase and
  Thermograph.
- Validate `partizan.dataset_label.v0` JSONL and the frozen 13-row Wave 47
  exact-metadata slice.
- Produce deterministic `partizan.event_stream.v0.1` JSON for a Fugue adapter.

The exact domain is specified in [docs/formal_domain.md](docs/formal_domain.md).
Architecture and data flow are in [docs/architecture.md](docs/architecture.md).

## Non-claims

Partizan v0.1 does **not** claim:

- that a current structural partition proves independence over all future play;
- that structural Thermograph identity proves arbitrary CGT equivalence;
- that decomposition improves a learned model or search process;
- that chess temperature or learned agency has been demonstrated; or
- that model-guided discovery has occurred.

The current learning result is negative/null: no tested decomposition-aware
model has beaten the matched controls on both development and test splits. See
[docs/research_claims.md](docs/research_claims.md).

## Installation

Requirements are Python 3.10+, Rust 1.85+, and Maturin 1.8+. After the upstream
`thermograph`, `bitmesh`, and `astralbase` 0.1.0 packages are published:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install .
```

Until that owner-controlled publication step, test the release candidates with
uncommitted Cargo registry patches. Exact commands and frozen upstream commits
are documented in [docs/development.md](docs/development.md); committed sibling
`path` dependencies are intentionally not used.

## Five-minute quickstart

With the package installed:

```bash
partizan-events from-fen \
  --fen '7k/5KQ1/8/8/8/8/8/8 b - - 0 1' \
  --output /tmp/partizan-event.json
partizan-events validate /tmp/partizan-event.json
python scripts/verify_release.py
```

The first command writes canonical JSON bytes. The record includes P01–P05
claim boundaries and explicitly identifies itself as a versioned input that
still requires a Fugue adapter; it is not a complete Fugue event log.

## Tests

```bash
cargo fmt --manifest-path engine/Cargo.toml --all -- --check
cargo clippy --manifest-path engine/Cargo.toml --locked --all-targets --all-features -- -D warnings
cargo test --manifest-path engine/Cargo.toml --locked --all-targets
python -m unittest discover -s tests -v
python engine/test.py
python agents/label_schema.py self-test
python scripts/validate_waves.py
python scripts/verify_release.py
```

The Rust commands require the registry packages or the non-committed patches
described above. Required tests fail when a fixture or native module is absent;
they do not silently skip. Historical multi-thousand-row Wave 6/7/12 smokes are
explicit optional integration tests:

```bash
python engine/test.py --legacy-artifact-dir /absolute/path/to/legacy-artifacts
```

All three named large artifacts must be present when that option is supplied.

## Frozen representative artifact

[`data/research-v0.1/manifest.json`](data/research-v0.1/manifest.json) binds a
byte-reproducible five-row vertical slice, the 13-row Wave 47 shard, and its
three reports by SHA-256, with schema, seed, commands, resource envelope, and
limitations. Wave 47's historical rows record the source commit as `workspace`;
the manifest preserves that provenance gap rather than inventing an immutable
origin. These slices are validation evidence, not a broad benchmark or a
learned-benefit result. The regeneration record is in
[docs/reproducibility.md](docs/reproducibility.md).

## Contributing and citation

See [CONTRIBUTING.md](CONTRIBUTING.md) for claim and artifact requirements. Use
[CITATION.cff](CITATION.cff) when citing the software after its release owner
approves the final metadata. Release history is in [CHANGELOG.md](CHANGELOG.md).
