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

`wave_62_left_supply_source_atlas.json` is the current execution target. It
tests whether genuinely new left-side component-value supply can clear the
rpf50 capacity gate before selector/materialization work:

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
                             -> promotion-readiness row contract
                             -> replay preflight for diagnostic fields
                             -> value-unique exact metadata shard
                             -> value-unique exact support bottleneck report
                             -> component-value capacity upper bound
                             -> component-source capacity sweep
                             -> mixed-hook value source breakthrough
                             -> mixed-hook exact shard audit
                             -> exact target projection inventory
                             -> compact exact-projection learned baselines
                             -> exact support expansion + ablation design
                             -> source-capacity expansion or stronger OOD splits
                             -> expanded source no-go / next source design
                             -> topology-balanced baseline ablation
                             -> topology feature-group ablation no-go
                             -> interior mixed-hook source no-go
                             -> pattern-limit capacity atlas
                             -> topology ablation hyperparameter sweep
                             -> left-supply capacity atlas
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
