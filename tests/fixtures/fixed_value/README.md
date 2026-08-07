# Fixed-value fixtures

The target is the zero game `0 = {|}`. The candidate stream contains:

- two distinct embodiments of the literal zero game;
- the distinct literal game `{-1|1}`, which is also equal to zero;
- the game `* = {0|0}`, which fails the equality certificate; and
- a repeated embodiment, which exercises repertoire deduplication.

The fixtures are canonical JSON/JSONL inputs for the exact
`conway_recursive_order_v1` comparison contract.

`chess-adapter-v0.1.valid.json` is the legacy adapter authority. Its payload
and `chess-adapter-sha256:67c668f73996f05fa963fe88dd2405ad08c8f1cc19488b26883a27fab713a144`
identity were independently reproduced from Partizan commit
`ec33853ab9b0a1702b7248b0ed2afe289a985193` with the three source commits
recorded inside the fixture. Release-contract tests freeze the schema and
fixture bytes.
