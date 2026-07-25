# Fixed-value explorer

Status: executable v0.1 contract for finite normal-play short games.

## Purpose

The fixed-value explorer searches a supplied candidate stream under one exact
target constraint. Every admitted candidate is equal to the target under
Conway's recursive order for finite normal-play games.

The output keeps three identities separate:

- the embodiment fingerprint hashes the declared representation;
- the literal-game fingerprint hashes the complete option tree;
- the fixed target identifies the equivalence relation certified by the run.

This separation exposes two transition classes. An `embodiment_only`
transition changes the representation while retaining the same literal game.
A `literal_game_crossing` transition changes the option tree while retaining
equality to the fixed target.

## Input contract

A literal game is recursive JSON:

```json
{"left": [], "right": []}
```

The example above is zero. Options contain games with the same shape. Inputs
are finite trees with at most 100,000 nodes and depth at most 128.
Literal-game fingerprints recursively sort options and remove repeated
identical subtrees because a game's left and right options form sets.
One comparison may evaluate at most 1,000,000 distinct recursive game pairs.
Representation metadata accepts deterministic JSON without floating-point
values. Metadata integers use the signed 64-bit range. Seeds and ordinals use
the unsigned 64-bit range. Candidate streams accept at most 100,000 records,
1,000,000 total literal nodes, and 256 MiB of JSONL input.

The checked fixtures use three important games:

```text
0       = { | }
{-1|1}  = 0
*       = {0|0}
```

The first two are equal under recursive comparison despite having different
literal trees. The third is a negative control.

## Search

Generate and certify a repertoire in one command:

```bash
partizan explore \
  --target tests/fixtures/fixed_value/target-zero.valid.json \
  --seed 23 \
  --count 8 \
  --max-expansion-depth 3 \
  --budget 8 \
  --max-results 8 \
  --output /tmp/generated-zero-repertoire.json
```

The built-in generator adds reversible left and right options. Each added
option has an immediate reply to the prior game, so the recursive comparison
gate can independently establish whether the expanded literal tree retains the
target value. Separate identity realizations also exercise embodiment-only
transitions.

Candidate generation can run separately:

```bash
partizan generate \
  --target tests/fixtures/fixed_value/target-zero.valid.json \
  --seed 23 \
  --count 8 \
  --output /tmp/generated-zero-candidates.jsonl
```

Search an existing candidate stream:

```bash
partizan search \
  --target tests/fixtures/fixed_value/target-zero.valid.json \
  --candidates tests/fixtures/fixed_value/candidates-zero.valid.jsonl \
  --seed 0 \
  --budget 5 \
  --max-results 5 \
  --output /tmp/zero-repertoire.json
```

Candidate order is determined by a SHA-256 rank binding the seed and candidate
identity. The verification budget counts exact target comparisons.
`max-results` limits admitted representatives.

Each declared embodiment binds one literal game. A candidate stream containing
the same embodiment fingerprint with conflicting literal games is rejected as
an invalid input contract.

Every evaluated candidate receives a recomputable comparison certificate. A
matching candidate can still be refused when its embodiment is already present
in the repertoire.

## Independent replay

```bash
partizan verify /tmp/zero-repertoire.json
partizan inspect /tmp/zero-repertoire.json
partizan compare /tmp/zero-repertoire.json \
  --left fixed-candidate-sha256:... \
  --right fixed-candidate-sha256:...
```

The repertoire contains the target, source candidates, search settings,
evaluations, certificates, fingerprints, and admitted entries. Verification
reruns the complete search and requires byte-level agreement with the stored
record.

Each admitted entry after the first stores one deterministic prior witness for
its transition class. The `compare` command derives the relationship between
any two admitted entries from their fingerprints, keeping stored repertoire
size linear in the number of entries.

Draft 2020-12 structural schemas are available in `docs/schemas` for targets,
candidates, repertoires, and bounded chess adapter records. The Python replay
validator additionally checks
identities, hashes, ordering, equality results, counts, relations, and
deterministic output bytes.

## Exact scope

`conway_recursive_order_v1` implements the recursive order theorem for finite
normal-play partizan games. Equality holds when each game is greater than or
equal to the other.

The contract accepts explicit option trees. The bounded chess adapter now
constructs those trees from constrained FENs through Astralbase, Bitmesh,
Shakmaty, and Thermograph. Its derived finite rule is documented in
`docs/bounded_chess_adapter.md`. Representation metadata is descriptive input
and does not enter the equality proof.
