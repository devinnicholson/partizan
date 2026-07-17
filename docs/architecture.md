# Architecture and trust boundaries

## Runtime path

```text
FEN
 └─ partizan Python API / partizan-events
     └─ PyO3 `_native`
         ├─ Shakmaty: orthodox FEN and position rules
         ├─ Bitmesh 0.1.0: conservative structural observations
         ├─ Astralbase 0.1.0: bounded terminal retrograde plumbing
         └─ Thermograph 0.1.0: structural values and approximate thermography
```

The Python package is the release surface. `engine/ml_model.py`, the `agents/`
network, and historical Wave documents are research tooling, not a stable
Python library API.

## Data path

```text
Astralbase generator → JSONL → label_schema.py → split/baseline reports
                                      │
FEN → partizan-events → v0.1 stream ──┴─→ explicit Fugue adapter (downstream)
```

Partizan does not import Fugue. It emits a canonical, hashed input record whose
target schema is named. Fugue remains responsible for adapting the record,
adding complete component/thermography/score provenance, and validating its
own `partizan_fugue.event_log.v1` schema.

## Trust boundaries

- Shakmaty establishes parsing and orthodox move legality within its supported
  state model; it does not establish CGT value claims.
- Bitmesh's exported observation is conservative and current-position scoped;
  Partizan does not promote it to a future-game theorem.
- Astralbase `Unknown` is neither a draw nor proof. Bounded exploration is not a
  complete tablebase.
- Thermograph structural serialization and approximate floating-point analysis
  are distinct contracts.
- Partizan's schema validator establishes record shape and required provenance,
  not the truth of an upstream mathematical result.
- Learning, agency, temperature-in-chess, and discovery claims remain outside
  the v0.1 release surface.

## Version boundary

All three research dependencies are declared as `0.1.0` registry dependencies.
The repository contains no committed local path override. Before publication,
clean-room tests apply frozen source candidates using Cargo's external
`[patch."crates-io"]` mechanism. Those patches are test configuration, not
release dependency declarations.
