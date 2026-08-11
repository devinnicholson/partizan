# Partizan fixed-value atlas

The visualizer presents the observed fixed-value repertoire from the frozen
order-7 Digraph Placement study. The opening canvas contains all 21,697
quotient-distinct representatives admitted by the study's checked population
predicate. Visitors can move the same population through three identity
layers:

```text
21,697 graph forms → 16,120 complete games → 3 exact values
```

The canvas uses deterministic coordinates generated offline. The graph-form
layer places representatives by directed-arc count and complete-game node
count. The complete-game layer uses digest-ordered deterministic packing and
draws group halos around complete games with multiple graph embodiments. The
exact-value layer gathers every form tightly around the targets `0`, `*`, and
`1/2`. Complete-game packing separates islands; distance between islands does
not represent a similarity measurement.

Every rendered mark maps to one retained event and carries its graph quotient,
literal-game group, target, source event index, seven-node adjacency encoding,
vertex colors, birthday, arc count, and complete-game node count. The display
covers the observed repertoire and makes no estimate of the total mathematical
fiber.

## The guided crossing

The five-step crossing follows forms A, B, and C inside value zero:

```text
v(A) = v(B) = v(C) = 0
ℓ(A) ≠ ℓ(B) = ℓ(C)
q(A), q(B), q(C) are pairwise distinct
```

Removing `2→3` changes A into B and removes four complete-game nodes. Adding
`6→0` changes B into C while preserving the complete-game digest. The interface
then resolves B and C to their shared literal option DAG. A belongs to an
observed 32-form complete-game island; B and C belong to an observed 54-form
island.

## Evidence contract

`visualizer/public/evidence/fixed-value-atlas.json.gz` is generated from the
independently replayed frozen ledger. The generator:

1. requires a passing independent verification and paper-evidence completion;
2. applies the frozen held-out population predicate;
3. keeps the first event for each `(target, graph quotient)` pair;
4. reconstructs and checks the representative-set hash;
5. checks the per-target quotient and literal-game counts;
6. verifies the retained derivation sidecars for A and B;
7. identifies the largest observed literal-game group by a declared mechanical
   rule; and
8. serializes the evidence and deterministic layouts with content hashes.

The resulting authority binds 73,728 source proposals, 21,697 quotient forms,
16,120 complete games, three exact values, the source ledger hash, the
independent replay hash, and the representative-set hash
`54488c811edd8a09155864fd1af3c469c7daba334c62788a86882e0e9c404a02`.

The full 165 MB source ledger and its content-addressed sidecars are archived in
the [Partizan reproducibility deposit](https://doi.org/10.5281/zenodo.21833142).
Download and verify the files as described in the deposit's
`FULL_EVIDENCE_ARCHIVE_AUTHORITY.json`, then extract the archive at the
reproducibility-repository root. The generator expects the directory
`output/research/digraph-order7-fixed-value-transitions-v1-00ac040294db` and
binds its completion, event, manifest, negative-test, report, summary, and
independent-verification file hashes.

### First-load 193-form fiber

`visualizer/public/evidence/fixed-value-fiber-193.json` is a 60 KB first-load
asset containing 193 actual order-7 digraphs. It is generated from the same
checked population as the full atlas. The selection rule chooses the observed
literal-game group with the most quotient-distinct representatives, breaking
ties by target order (`0`, `*`, `{0|1}`) and then literal-game digest. The
largest group is unique in this population:

```text
target: {0|1} (1/2)
literal game: 830ef59c3454d13324e6841d466a702ef3e168bab7615bb4043d6e6d58e8fd66
observed quotient-distinct digraphs: 193
directed-arc counts: 17 through 27
```

Each row binds its adjacency bits and color mask to candidate, event, and graph
quotient hashes. The small payload also includes the shared literal option DAG
and a layout in which the horizontal axis records directed-arc count. Vertical
order is digest-based and does not measure graph similarity. The companion
`fixed-value-fiber-193.manifest.json` binds the file bytes, selection, full-atlas
authority, completion authority, and representative-set hash.

This is the largest group in the frozen observed population. It does not
estimate the size or prevalence of the mathematical fiber, and it does not
measure aesthetic or human preference.

Rebuild or check it from the main Partizan repository:

```bash
python3 scripts/build_fixed_value_atlas_evidence.py \
  --source /path/to/partizan-reproducibility/output/research/digraph-order7-fixed-value-transitions-v1-00ac040294db \
  --check
```

The interface also reads checked historical and motif evidence from
`visualizer/public/evidence/`. Exact equality, graph quotient, and
complete-game identity were measured. Aesthetic preference was not measured.

## Development

```bash
cd visualizer
npm ci
npm test
npm run lint
```

The production build uses vinext and targets OpenAI Sites. Canvas provides the
dense atlas; every inspected specimen is rendered in the DOM. Keyboard arrows
move through forms, Escape closes a specimen, touch targets remain at least 44
pixels, and reduced-motion preferences disable animated identity transitions.
