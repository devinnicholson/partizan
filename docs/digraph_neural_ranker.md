# Order-7 neural proposal ranker

Partizan includes an experimental neural policy for order-7 Digraph Placement.
The policy ranks graph edits before exact evaluation. The existing exact
verifier remains the sole authority for value equality and repertoire
admission.

## Scope

The component is deliberately small:

1. adapt the immutable order-7 event ledger into graphs and binary
   exact-equality labels;
2. train the frozen deterministic CPU model grid and write content-addressed
   checkpoints;
3. rank a fresh pool of `toggle_one_arc` proposals without reading verifier
   outcomes; and
4. compare the frozen ordering with deterministic random orderings after the
   fresh pool has been verified.

The 73,728-row v1 ledger is training-only. Quotient collisions connect its 36
streams, so subdivisions of that ledger cannot serve as independent
validation or test evidence. Validation and test pools must come from fresh,
precommitted seed domains.

## Model

Each graph becomes a seven-node directed graph with blue/red node features.
An input layer maps the two colors into the hidden width. Each message-passing
layer combines a node's state with separate unnormalized sums over incoming
and outgoing neighbors. Mean and max pooling produce a
permutation-invariant graph representation. The head combines this
representation with a learned width-8 target embedding.

The frozen grid contains eight configurations:

- hidden width 32 or 64;
- two or three directed message-passing layers; and
- learning rate 0.001 or 0.0003.

Every configuration uses ReLU, dropout 0.1 after message updates and in the
head, AdamW with weight decay `1e-4`, unweighted mean binary cross-entropy,
batch size 256, and exactly 80 epochs. Three fixed seeds are trained per
configuration. The selected model averages their logits.

The model never receives:

- vertex labels as positional features;
- color-isomorphism quotient codes;
- proposal operator identity;
- verifier decisions, certificates, measurements, rejections, or retention
  outcomes; or
- event order, parent identity, or corpus frequency.

Operator and pool identifiers remain metadata used to enforce the evaluation
contract. The primary task contains only `toggle_one_arc` proposals, preventing
the model from exploiting the large success-rate differences between
operators.

## Install and train

NumPy is an optional training and inference dependency:

```bash
python -m pip install -e '.[neural]'
```

With `partizan` and `partizan-fugue` checked out as sibling repositories:

```bash
partizan-digraph-ranker train \
  --events ../partizan-fugue/output/research/digraph-order7-fixed-value-transitions-v1-00ac040294db/events.jsonl \
  --model-out /tmp/partizan-order7-ranker.json \
  --hidden-width 32 \
  --layers 2 \
  --learning-rate 0.001 \
  --random-seed 10025726846852382910
```

The command reads the actual order-7 study ledger. Its current SHA-256 is
`304797fe69622f4d2d88363e89538d10a6ef33d39eac01533b8aebf3bf3b5b6c`.
Training uses all 73,664 rows with a semantic equality decision across every
proposal operator. The 64 candidates rejected before semantic evaluation are
excluded from supervised loss and recorded by stage and reason. The output
binds the source hash, feature contract, architecture, weights, optimizer
configuration, and training-only status into `model_id`.

Training loss serves as a diagnostic. Validation claims require the separately
committed validation corpus.

## Frozen validation selector

After the separately frozen 16-member validation groups have been generated,
ranked, and exactly evaluated, run the complete selector:

```bash
partizan-digraph-ranker select-grid \
  --training-events ../partizan-fugue/output/research/digraph-order7-fixed-value-transitions-v1-00ac040294db/events.jsonl \
  --validation-events /tmp/fresh-validation-events.jsonl \
  --ensemble-out /tmp/partizan-order7-ensemble.json \
  --report-out /tmp/partizan-order7-grid-report.json
```

The selector trains eight configurations with all three fixed seeds, captures
all 80 epoch checkpoints, and records every checkpoint digest and validation
metric. It chooses the maximum target-macro validation top-one exact rate,
then the minimum target-macro BCE, parameter count, epoch, and lexicographic
configuration id. The ensemble and selection report are independently
self-hashed.

## Rank a fresh pool

Fresh proposal rows use the same proposal fields as the historical event rows:

```json
{
  "base_seed": 200003,
  "candidate": {
    "arcs": [[0, 1]],
    "blue_vertices": [0, 2, 4],
    "order": 7
  },
  "candidate_sha256": "<sha256>",
  "proposal": {
    "mode": "local_mutation",
    "operator": "toggle_one_arc"
  },
  "ranker_pool": {
    "pool_id": "pool-sha256:<sha256>"
  },
  "target": "0"
}
```

The frozen validation ledger places `pool_id` at the top level. The public
proposal API also accepts the earlier `ranker_pool.pool_id` envelope shown
above. If both are present, they must agree. Every row in one pool must share
the pool id, target, base seed, and operator.
Candidate identities must be unique. Rows supplied to ranking do not contain
`exact_decision`, `quotient`, `retention`, or other verifier outputs.

```bash
partizan-digraph-ranker rank \
  --proposals /tmp/fresh-toggle-one-pools.jsonl \
  --model /tmp/partizan-order7-ranker.json \
  --output /tmp/fresh-toggle-one-ranks.jsonl
```

Library callers can use:

```python
from partizan.digraph_neural_ranker import rank_pool

ranks = rank_pool(model, proposal_rows, model_id=model_record["model_id"])
```

The returned records contain candidate identity, pool metadata, score, and
rank. They carry no labels or verifier evidence.

## Resource-preflight adapter

The frozen resource gate can bind this module directly. Its public factory
loads either a single-model or ensemble artifact, verifies the artifact's
content-derived model id, and returns scores in input-row order:

```python
from pathlib import Path
from partizan.digraph_neural_ranker import build_resource_preflight_ranker

score_pool = build_resource_preflight_ranker(
    model_artifact_path=Path("/tmp/partizan-order7-ensemble.json"),
    model_id="ensemble-sha256:<sha256>",
)
scores = score_pool(outcome_free_pool_rows)
```

The callback applies the same pool, operator, identity, and finite-score
checks as `rank_pool`. It rejects verifier decisions, quotients, descriptors,
retention fields, certificates, and other outcome-bearing fields.

## Fresh evaluation

After every proposal in a frozen pool has been evaluated once by the exact
verifier, evaluate the model:

```bash
partizan-digraph-ranker evaluate \
  --training-events ../partizan-fugue/output/research/digraph-order7-fixed-value-transitions-v1-00ac040294db/events.jsonl \
  --evaluation-events /tmp/fresh-validation-events.jsonl \
  --model /tmp/partizan-order7-ranker.json \
  --role validation \
  --budgets 8 16 \
  --random-replicates 256 \
  --report-out /tmp/fresh-validation-report.json
```

Candidate or quotient collisions with training remain in the validation
ledger and are reported. Each validation row carries
`eligible_for_validation_metric` and `exclusion_reasons`. The selector checks
those markers against recomputed connectivity, candidate collisions,
structural-quotient collisions, and censored labels. The declared booleans,
eligibility bit, and ordered reason set must agree exactly; a builder cannot
drop an otherwise clean row. The selector filters ineligible rows within each
committed group and excludes a group only when no eligible row remains. During
test evaluation, such rows remain in the ranked sequence and consume verifier
calls while contributing no discovery.

For each pool and call budget the evaluator reports:

- certified exact matches;
- quotient-unique certified matches; and
- literal-game-unique certified matches.

The learned order and every random order use the same candidate pool,
`toggle_one_arc` operator, and verifier-call budget. Random permutations are
derived by SHA-256 from the pool id, replicate number, and candidate identity,
making them reproducible without platform-specific pseudorandom state.

## Required official workflow

The component is ready to train and rank. An official result still requires:

1. freeze the pool generator, pool size, model code, hyperparameters, model
   record, random baseline, budgets, and seed domains;
2. generate outcome-free validation pools from fresh seeds;
3. rank and commit all validation orderings before exact evaluation;
4. verify every candidate once and audit identity leakage;
5. use the frozen selector once for the predeclared model decision;
6. freeze the self-hashed three-member ensemble without further tuning;
7. repeat once on untouched test seeds; and
8. independently replay every promoted certificate and report negative or
   null results unchanged.

Fresh-pool generation belongs to the separately frozen experimental workflow.
This component supplies the training, outcome-free ranking, identity audit,
and matched evaluation contracts consumed by that run.
