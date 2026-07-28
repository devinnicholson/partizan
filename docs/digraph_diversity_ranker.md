# Order-7 diversity-aware proposal ranker

Partizan can rank a pool of order-7 Digraph Placement edits using two frozen
neural signals:

1. the target-conditioned equality score from
   `digraph_neural_ranker.py`; and
2. graph-embedding distance from the exact representatives already encountered
   by one search arm.

The equality score concentrates verifier calls on likely matches. The distance
term encourages the trajectory to visit structurally different realizations.
The exact finite-game verifier decides value equality and controls every
repertoire update.

## Feature authority

The diversity encoder receives:

- directed arcs;
- blue vertices; and
- graph order, fixed at seven.

It has no target embedding. Proposal operators, candidate identities, exact
decisions, quotient codes, literal-game digests, descriptors, retention
records, and event indices remain outside the model feature tensor.

The training-only literal-game digest acts as an equivalence label. During
inference, distance is computed entirely from graph embeddings.

## Training corpus

The frozen V2 corpus contract uses the 73,728-row historical order-7 event
ledger. Of its 73,664 exact-evaluated rows:

- 60,744 complete literal-game digest groups are present;
- 6,868 groups contain at least two rows; and
- 19,788 rows belong to those repeated groups.

Repeated groups supply contrastive anchors and positives. Singleton groups do
not enter the supervised NT-Xent loss.

The loader recomputes the candidate graph digest, literal-game group counts,
and source-file SHA-256 before training.

## Encoder

The graph encoder uses:

- two node indicators, blue and red;
- hidden width 64;
- three directed message-passing layers;
- separate incoming, outgoing, and self transforms;
- ReLU activations and dropout 0.1;
- mean and maximum graph pooling; and
- a two-layer projection head with L2-normalized output.

The finite grid contains:

- embedding width 16 or 32;
- contrastive temperature 0.1 or 0.2;
- learning rate 0.001;
- AdamW weight decay `1e-4`;
- 60 epochs; and
- three fixed training seeds.

Each batch contains up to 64 literal-game groups and two graphs per group. For
each anchor, the second graph from its group is the positive. The other graphs
in the batch are negatives. Group order and within-group rotation are
deterministic functions of seed and epoch.

Train one member:

```bash
partizan-digraph-diversity-ranker train \
  --events ../partizan-fugue/output/research/digraph-order7-fixed-value-transitions-v1-00ac040294db/events.jsonl \
  --embedding-width 16 \
  --temperature 0.1 \
  --random-seed 11554741894640848524 \
  --model-out /tmp/diversity-member.json
```

The artifact records its feature contract, architecture, optimizer settings,
training-source hash, group counts, parameters, runtime, and content-derived
model id.

## Arm-local novelty memory

Every equality-plus-novelty trajectory owns a separate memory. The initial
entry is the shared Stage-0 control graph. After exact evaluation, the caller
may append a selected graph when it:

- equals the target; and
- passes the frozen prior-split candidate and quotient checks.

The memory consists of direct graph objects:

```json
{
  "arcs": [[0, 1], [1, 2]],
  "blue_vertices": [0, 2, 4],
  "order": 7
}
```

It carries no digest, quotient, target, certificate, or descriptor. Model
parameters remain fixed as memory grows.

## Novelty score

Embedding coordinates can rotate independently across training seeds.
Partizan therefore keeps ensemble members separate:

1. each member embeds the candidate and every memory graph;
2. each member computes the candidate's minimum cosine distance to memory; and
3. those minimum distances are averaged across members.

This ordering avoids averaging incompatible embedding coordinates.

## Rank fusion

Within the first nonempty structural tier, equality scores and novelty scores
are transformed separately to ascending midrank fractions in `[0,1]`. Exact
ties receive the same midrank.

The acquisition score is:

```text
equality_midrank + lambda * novelty_midrank
```

The frozen lambda grid is `0.25, 0.5, 1.0, 2.0`. Equal fusion scores are
resolved by the lexicographically smallest candidate SHA-256.

Library use:

```python
from pathlib import Path

from partizan.digraph_diversity_ranker import (
    build_resource_preflight_diversity_ranker,
)

rank_pool = build_resource_preflight_diversity_ranker(
    equality_model_artifact_path=Path("/tmp/equality-ensemble.json"),
    equality_model_id="ensemble-sha256:<digest>",
    novelty_model_artifact_path=Path("/tmp/diversity-ensemble.json"),
    novelty_model_id="ensemble-sha256:<digest>",
    lambda_weight=0.5,
)

ranked = rank_pool(outcome_free_proposal_rows, arm_local_memory_graphs)
selected = ranked[0]
```

The returned records contain scores, midranks, the fusion weight, model ids,
candidate identity, and deterministic rank. They contain no verifier outcome.

The command-line equivalent accepts one proposal-pool JSONL file and one
direct-graph memory JSONL file:

```bash
partizan-digraph-diversity-ranker rank \
  --proposals /tmp/pool.jsonl \
  --memory-candidates /tmp/memory.jsonl \
  --equality-model /tmp/equality-ensemble.json \
  --equality-model-id ensemble-sha256:<digest> \
  --novelty-model /tmp/diversity-ensemble.json \
  --novelty-model-id ensemble-sha256:<digest> \
  --lambda-weight 0.5 \
  --output /tmp/ranks.jsonl
```

## Validation contract

Model and lambda selection belongs to a separately committed validation
workflow. Every configuration must see the same ordered static candidate
pools. Each simulated trajectory maintains its own adaptive memory using
revealed validation outcomes.

An official model package binds:

- the historical training registry;
- the complete validation registry;
- all three member checkpoints;
- the selected architecture, epoch, temperature, and lambda;
- the Partizan source snapshot and pushed commit; and
- the frozen selection rule.

Fresh test generation begins after those bindings are sealed.
