# Bounded exact short games

## Scope

The bounded short-game API covers finite, loop-free, perfect-information,
two-player partizan games under normal play. A game is an explicit recursive
object:

```python
{"left": [left_option, ...], "right": [right_option, ...]}
```

Options have set semantics. Input order and repeated options do not affect the
transport serialization. Loopy games, draws, chance, hidden information,
misère play, and transfinite games are outside this API.

Callers must supply fully expanded explicit trees. The Partizan boundary does
not accept named constructors or numeric atoms. Standard expanded examples
are:

```python
zero = {"left": [], "right": []}
one = {"left": [zero], "right": []}
minus_one = {"left": [], "right": [zero]}
star = {"left": [zero], "right": [zero]}
```

The implementation is pure Python and does not import `partizan._native`,
Thermograph, Bitmesh, or Astralbase.

## Public API

The following names are exported from `partizan`:

| API | Result |
| --- | --- |
| `compare_short_game_bounded(left, right)` | Exact two-direction comparison and one of four outcomes |
| `equal_short_game_bounded(left, right)` | Mathematical equality from mutual comparison |
| `literal_game_transport_bounded(game)` | Closed explicit game table, identities, and resource counts |
| `semantic_canonical_form_bounded(game)` | Deterministic canonical form, trace, and audits |
| `semantic_canonical_id_v1(game)` | Domain-separated semantic value ID |
| `validate_semantic_canonical_form_bounded(game, claim)` | Independent recomputation of a claimed form |
| `build_short_game_comparison_certificate_v1(...)` | Frozen comparison certificate with historical semantic boundary |
| `verify_short_game_comparison_certificate_v1(...)` | Closed-table recurrence replay for v1 |
| `build_short_game_comparison_certificate_v2(...)` | Comparison certificate with semantic IDs and rewrite limit |
| `verify_short_game_comparison_certificate_v2(...)` | Comparison and semantic replay for v2 |

`BoundedComparison.outcome` is exactly one of:

- `less`
- `equal`
- `greater`
- `fuzzy`

`fuzzy` records that neither order direction holds.

## Exact comparison

For games `G` and `H`, the implementation uses Conway's recurrence:

```text
G <= H
    iff no left option G^L satisfies H <= G^L
    and no right option H^R satisfies H^R <= G.
```

Nodes are interned by their complete literal serialization. Comparison memo
keys are ordered pairs of internal node IDs. External digests identify
transport rows and cannot decide a recurrence.

Each comparison certificate contains:

- a closed game table for both roots;
- the complete two-root comparison dependency DAG;
- both order directions;
- the derived four-way outcome;
- exact candidate and target bindings;
- named resource limits and observed counts; and
- a hash over canonical JSON certificate bytes.

The verifier rebuilds every dependency and rejects cycles, missing followers,
unreachable rows, malformed identities, altered results, resource mismatches,
and equality/semantic-ID disagreement.

## Literal and semantic identities

The literal serialization is:

```text
serialize(G) =
    "{" + join(",", sort(unique(serialize(G^L)))) +
    "|" + join(",", sort(unique(serialize(G^R)))) + "}"
```

Partizan preserves the historical literal digest:

```text
legacy_literal_sha256 = sha256(UTF8(serialize(G)))
```

New transport rows also carry:

```text
literal_sha256_v1 = sha256(
    "partizan.explicit_short_game.v1\n" +
    UTF8(serialize(G))
)
```

The semantic canonical identity is:

```text
semantic_canonical_id_v1 = sha256(
    "partizan.semantic_canonical_game.v1\n" +
    UTF8(canonical_serialization(G))
)
```

Literal identity answers whether two explicit option structures are the same.
Semantic identity answers whether their deterministic reduced forms are the
same.

The result object reports both occurrence-tree and distinct-DAG measurements:

- `literal_occurrence_node_count`
- `literal_distinct_dag_node_count`
- `literal_option_reference_count`
- `literal_serialization_bytes`

## Semantic canonicalization

The independent Python reducer recursively canonicalizes all options and then
applies one deterministic eligible rewrite at a time:

1. remove a dominated Left option `A` when another Left option `B` satisfies
   `A <= B`;
2. remove a dominated Right option `A` when another Right option `B` satisfies
   `B <= A`;
3. bypass a reversible Left option `A` when a Right response `A^R` satisfies
   `A^R <= G`, inserting every Left option of `A^R`;
4. bypass a reversible Right option `A` when a Left response `A^L` satisfies
   `G <= A^L`, inserting every Right option of `A^L`; and
5. coalesce and sort the option sets after each rewrite.

Rule class, removed option, witness or response, and inserted option
serializations determine the rewrite order. The trace is byte-deterministic.

Every completed result performs three mandatory audits:

- `soundness_equal`: input and output are mutually equal under exact
  comparison;
- `irreducible`: no domination or reversibility rewrite remains anywhere in
  the output closure;
- `idempotent`: a second complete reduction yields identical bytes and zero
  rewrites.

An audit failure raises an internal assertion and produces no semantic ID.

## Certificate versions

`partizan.short_game_comparison_certificate.v1` is frozen. Its
`semantic_canonical` object retains:

```json
{
  "status": "thermograph_semantic_api_required",
  "candidate_semantic_canonical_id": null,
  "target_semantic_canonical_id": null
}
```

`partizan.short_game_comparison_certificate.v2` is additive. It records:

- `status = "partizan_independent_validation_v1"`;
- the candidate semantic canonical ID;
- the target semantic canonical ID; and
- the exact maximum canonical rewrite count.

The v2 verifier first replays the frozen v1 comparison boundary. It then
reconstructs both explicit roots from the closed game table, independently
canonicalizes them, verifies both semantic IDs, and checks that equality agrees
with semantic identity.

## Named resource profiles

| Limit | `order7.v1` | `digraph8.v1` |
| --- | ---: | ---: |
| Root birthday | 7 | 8 |
| Canonical birthday | 7 | 8 |
| Source nodes per root | 128 | 256 |
| Options per side | 7 | 8 |
| Combined option references | 1,792 | 4,096 |
| Intermediate nodes | 4,096 | 8,192 |
| Comparison-DAG rows | 262,144 | 1,000,000 |
| Literal bytes per root | 16,777,216 | 33,554,432 |
| Certificate bytes | 67,108,864 | 134,217,728 |

The profile identifiers are:

- `partizan.bounded_short_game.order7.v1`
- `partizan.bounded_short_game.digraph8.v1`

Callers may supply stricter limits. Increasing a named limit requires a new
profile identifier. Canonical rewrite limits may also be tightened explicitly;
v2 certificates bind the selected value.

Limit crossings raise `ResourceLimitError`. Its portable record contains the
resource name, limit, and observed count. No comparison verdict or semantic ID
is emitted for the failed operation.

## Validation

Run the source-only exact layer from a checkout:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python python3 -m unittest \
  tests.test_bounded_short_game \
  tests.test_semantic_canonical_form -v

PYTHONPATH=python python3 examples/bounded_short_game.py
```

The checked tests cover:

- every one of the 65,536 ordered comparisons among the 256 games born by
  day 2;
- exactly 22 semantic IDs across those 256 literal games;
- explicit integer, dyadic, star, domination, and reversibility controls;
- the Elkies form `{0,*|1}` and canonical `1/2`;
- the explicit sum `* + *` and canonical zero;
- unequal fuzzy controls;
- typed birthday and rewrite-limit failures;
- digest-collision controls;
- unrelated game-table rows;
- rehashed result, identity, resource, and semantic-ID mutations;
- deterministic rewrite traces; and
- v1-frozen and v2-additive certificate behavior.

These tests run without the native extension. Native chess-adapter tests require
the complete development installation described in
[`development.md`](development.md).

## Runnable example

From the repository root:

```bash
PYTHONPATH=python python3 examples/bounded_short_game.py
```

The example compares zero and star, canonicalizes the Elkies half form, builds
both certificate versions, verifies v2, and prints a deterministic JSON
summary.
