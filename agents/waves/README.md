# Agent Wave Plans

Wave files are machine-readable dispatch plans for the research agent network.
Each wave names the task graph, owning agent, repo scope, commands, and
acceptance gates.

## Commands

From the `partizan` repo root:

```bash
python3 agents/network.py validate-wave
python3 agents/network.py wave-plan
python3 agents/network.py wave-task w3_thermograph_value_contract
```

Use `wave-plan` to see the parallel dispatch order. Use `wave-task` to print
one assignment before sending it to an agent.

## Current Wave

`wave_03_vertical_slice.json` builds the first auditable vertical slice:

```text
position -> domain gate -> decomposition certificate -> exact/rejected label
         -> JSONL shard -> schema validation -> baseline-ready artifact
```

The critical rule is that exact, rejected, heuristic, and prediction payloads
remain separate throughout the pipeline.
