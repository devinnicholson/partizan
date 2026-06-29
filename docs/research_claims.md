# Research Claims

This table is the paper spine. A claim is not active until it has evidence,
baselines, and a falsification condition.

The current vertical slice provides concrete evidence only for reproducible
plumbing: a schema-v0 JSONL shard at `/private/tmp/partizan-wave-03.jsonl`,
SHA-256 `4a678e9a960e2349f15d8ea09744c354718703acd553923ecd6aa7758b0b2fc4`,
with 5 rows (3 exact, 2 rejected), plus deterministic loader and baseline
smokes. Two exact rows are chess `number` labels; one exact row is a formal CGT
`switch` fixture with positive temperature. This evidence does not support the
broader agency, decomposition, chess-temperature, discovery, or OOD-shift claims
yet.

| ID | Claim | Current Evidence Status | Required Evidence | Baselines | Falsification Condition | Current Blocker / Next Evidence | Owner |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C1 | Exact game-structure labels expose agency information not captured by scalar outcome labels. | Unproven. The slice proves only that terminal, terminal-frontier, and formal switch exact labels can be serialized with provenance; it has no agency metrics, representation probes, or scalar-label controls. | Dataset rows with exact labels at useful scale, agency metrics, and representation probes comparing structured labels against scalar labels. | Scalar WDL/DTM model, material features, random labels; `fen_string_material_gate_v0` is only a loader smoke baseline. | Scalar-supervised controls match structured-supervised models on agency probes and OOD tests. | Blocked by exactness and scale: three exact rows, including one formal switch, are not evidence about agency. Next wave needs chess-derived nontrivial exact rows, agency targets, and scalar-control probes. | `research_director`, `model_lab` |
| C2 | Certified decomposition improves generalization on composed positions. | Blocked by exactness. Negative controls and rejected rows show weak, unchecked, or absent strict decomposition must not enter exact training; they are guardrails, not positive evidence. | Strict decomposition certificates, verified composed positions, and a composition OOD split. | Full-board scalar model, no-decomposition structured model. | Decomposition-aware models do not improve on held-out compositions. | Needs machine-checked positive decomposition certificates and a held-out composition split. The current `no_strict_decomposition` rejection only protects against overclaiming. | `topology_engineer`, `model_lab` |
| C3 | Temperature and option-value structure provide measurable proxies for initiative and forcedness. | Partially plumbed, not evidenced for chess. The shard includes one formal `switch` fixture with temperature 1 and one chess mate-in-one row with terminal-frontier child metadata, but neither is a scaled chess temperature benchmark. | Exact temperature labels, option-value distributions, positive controls, and negative controls. | Legal move count, material delta, engine scalar evaluation. | Temperature fails to predict forcedness or move urgency beyond simple controls. | Needs chess-derived exact nonterminal positions with temperature and option-value labels. Current formal switch and one-ply frontier plumbing are necessary but not sufficient. | `theory_steward`, `exact_value_engineer` |
| C4 | Model-guided search can discover compact, verified, agency-rich positions more efficiently than random or heuristic search. | Unproven and scale-blocked. The current slice has no model-guided search logs, verified gallery, leakage checks, or ranking comparisons. | Verified gallery, search logs, leakage checks, and beauty/agency metric rankings. | Random generation, material heuristic, handcrafted metric search. | Verified discovery precision does not beat baselines under matched budget. | Needs matched-budget discovery runs over labels that passed exact, domain, and decomposition gates. Negative controls only define what must be excluded. | `discovery_curator`, `verifier_red_team` |
| C5 | The benchmark supports reproducible evaluation of exact-label learning under OOD shift. | Partially evidenced. The current slice concretely supports schema, manifest, validation, exact-vs-rejected baseline plumbing, mixed FEN/CGT encodings, and a tiny multi-class `exact.value_class` smoke over `number` and `switch`; OOD shift and exact-label learning remain unproven. | Dataset manifest, schema validation, deterministic regeneration, baseline smoke, and OOD split report. | Reproducibility and coverage checks; `fen_string_material_gate_v0` for exact-vs-rejected smoke; future split baselines for OOD. | Dataset cannot be regenerated, schema validation fails, exact/rejected split leaks unsupported rows into exact targets, or OOD splits leak by symmetry, graph hash, or generator family. | Blocked by scale and splits: current support is 5 rows, `exact.value_class` support is 3 with one minority `switch` row. Next wave needs larger deterministic shards, more non-number classes, and explicit leakage reports. | `dataset_foundry` |

## Reviewer Risks

- The domain may be too narrow. Mitigation: include explicit OOD composition and
  value-class tests, then state the domain as a controlled testbed rather than
  all of chess. Negative controls make castling rights, en-passant targets, and
  undeclared generalized boards explicit exclusions. The current mate-in-one row
  is a terminal-frontier exception, and the formal `switch` row is outside the
  chess domain by explicit `cgt_canonical` encoding.
- Exact labels may be expensive. Mitigation: report throughput, shard size,
  proof-check rate, and generator failure accounting. The current slice records
  exact row provenance, certificate digests, shard hash, and rejected-row
  reasons, but it does not yet measure throughput or proof-check scale.
- Aesthetic metrics may look subjective. Mitigation: separate metric definitions
  from human-facing gallery examples, and report negative controls. The current
  slice has no active aesthetic claim; the negative controls prevent weak
  decomposition or unsupported domains from becoming gallery evidence.
- Structured supervision may collapse to scalar proxies. Mitigation: include
  representation probes and ablations that remove temperature, decomposition,
  and option-structure labels independently. The 4/4 FEN material-gate smoke
  and 2/3 value-class majority smoke keep this risk open rather than resolving
  it.
