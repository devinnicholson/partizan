# Fixed-value fixtures

The target is the zero game `0 = {|}`. The candidate stream contains:

- two distinct embodiments of the literal zero game;
- the distinct literal game `{-1|1}`, which is also equal to zero;
- the game `* = {0|0}`, which fails the equality certificate; and
- a repeated embodiment, which exercises repertoire deduplication.

The fixtures are canonical JSON/JSONL inputs for the exact
`conway_recursive_order_v1` comparison contract.
