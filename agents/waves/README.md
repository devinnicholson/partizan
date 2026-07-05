# Agent Wave Plans

Wave files are machine-readable dispatch plans for the research agent network.
Each wave names the task graph, owning agent, repo scope, commands, and
acceptance gates.

## Commands

From the `partizan` repo root:

```bash
python3 agents/network.py validate-wave agents/waves/wave_22_expanded_composition_benchmark.json
python3 agents/network.py wave-plan agents/waves/wave_22_expanded_composition_benchmark.json
python3 agents/network.py wave-task w22_astralbase_expanded_non_fixture_shard --wave agents/waves/wave_22_expanded_composition_benchmark.json
```

Use `wave-plan` to see the parallel dispatch order. Use `wave-task` to print
one assignment before sending it to an agent.

## Current Wave

`wave_44_rpf20_signature_diagnostic_shard.json` is the current execution
target. It materializes the rows-per-family 20 signature diagnostic shard after
Wave 43 proved full-pair support reachability, then runs schema validation,
split/leakage reporting, deterministic floors, and projection inventory while
keeping those rows outside exact supervision:

```text
depth-two profile bottleneck -> duplicate-cluster report
                             -> versioned signature diagnostic
                             -> support gate + promotion blockers
                             -> heuristic diagnostic shard
                             -> deterministic heuristic target floor
                             -> projection support inventory
                             -> bounded higher-support diagnostic
                             -> full-pair rpf20 support gate
                             -> materialized rpf20 diagnostic shard
                             -> replayed exact value-rule/split/baseline work
```

The older `wave_17_composition_certificates.json` remains the certificate
foundation:

```text
strict decomposition -> component exact values -> composition certificate
                    -> JSONL shard -> composition OOD reports -> baselines
```

The critical rule is that a composition certificate binds provenance but does
not, by itself, prove chess value correctness. Exact rows still need verified
component values, verified composed result values, and schema-valid provenance;
weak or unchecked decompositions remain rejected controls.
