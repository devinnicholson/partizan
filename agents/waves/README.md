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

`wave_35_edge_ladder_profile_supply.json` is the current execution target. It
tests whether a low-node edge/minor ladder profile source creates fresh
component-value supply, and records the result as a no-go if the combined
source still cannot increase selected leakage-clean rows:

```text
depth-two profile bottleneck -> edge-ladder source inventory
                             -> combined-source clean search
                             -> support/rejection report
                             -> next diversity strategy constraint
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
