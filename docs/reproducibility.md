# Reproducibility record: Partizan v0.1 vertical slice

## Frozen inputs

- Partizan baseline: `f38d5d26096dcf3010a8888e2e2182345a231233`
- Astralbase: `7ad71b542733cb61507df4bf5fba241bcc35ef79`
- Bitmesh: `28aee03bf1acb299fc82d5119f37893264e070e4`
- Thermograph: `57df043a5940f4ea3bf29fcb7920f369e035030c`
- Generator seed: `0`
- Schema: `partizan.dataset_label.v0`

The upstream release candidates were supplied through an uncommitted
`[patch."crates-io"]` Cargo configuration. No sibling path appears in Partizan's
manifest.

## Command

```bash
python engine/orchestrator.py sample-label-shard \
  --astralbase-dir /absolute/path/to/astralbase
```

The runner invoked `cargo run --locked --offline --quiet --
--sample-label-shard` twice, compared raw bytes, validated all rows, and wrote a
manifest. The generated artifact was then promoted without modification to
`data/research-v0.1/vertical-slice.jsonl`.

## Result

- SHA-256: `a72dc3d8fdc334b81da5d492971433d8d0269b0f31cbafed51c9048047b259ef`
- Bytes: 5,313
- Rows: 5 (3 exact, 2 rejected)
- Duplicate row IDs, positions, and exact certificate digests: 0
- Observed wall time: 4.9 seconds on macOS arm64 after dependency compilation
- Resource envelope: 1 CPU, 2 GiB memory, 900-second regeneration budget;
  verification budget 1 CPU, 512 MiB, 30 seconds

This run evidences deterministic small-artifact plumbing under P01 and the
reproducible-input portion of P03. It does not establish a published benchmark
metric, learned benefit, agency, chess temperature, or discovery.
