# Partizan Research Agent Network

This directory defines the agent network for the research program. It is meant
to be executable project structure, not a brainstorm.

The network has one central rule: keep exact certified labels, heuristic labels,
and model predictions separate. Mixing those categories would undermine the
dataset, experiments, and paper claims.

## Commands

```bash
python3 agents/network.py validate
python3 agents/network.py summary
python3 agents/network.py first-sprint
python3 agents/network.py agent exact_value_engineer
```

## Operating Model

`research_network.json` defines:

- global verification gates
- agent roles and ownership boundaries
- phase plans and exit criteria
- first-sprint tasks

The network is designed around four build lanes:

- exact engines: `thermograph`, `bitmesh`, `astralbase`
- data foundry: schemas, manifests, splits, provenance
- model lab: baselines, structured models, probes, ablations
- discovery and paper: verified candidate positions, gallery, claim table

## Non-Negotiables

- Exact labels require certificates.
- Unsupported positions fail explicitly.
- Weak decomposition cannot enter exact training splits by default.
- Every result needs a baseline, ablation, and out-of-distribution split.
- Aesthetic claims need measurable structure plus verified examples.
- Citations are added only when they support a specific technical claim.
