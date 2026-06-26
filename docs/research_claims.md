# Research Claims

This table is the paper spine. A claim is not active until it has evidence,
baselines, and a falsification condition.

| ID | Claim | Required Evidence | Baselines | Falsification Condition | Owner |
| --- | --- | --- | --- | --- | --- |
| C1 | Exact game-structure labels expose agency information not captured by scalar outcome labels. | Dataset rows with exact labels, agency metrics, and representation probes. | Scalar WDL/DTM model, material features, random labels. | Scalar-supervised controls match structured-supervised models on agency probes and OOD tests. | `research_director`, `model_lab` |
| C2 | Certified decomposition improves generalization on composed positions. | Strict decomposition certificates and composition OOD split. | Full-board scalar model, no-decomposition structured model. | Decomposition-aware models do not improve on held-out compositions. | `topology_engineer`, `model_lab` |
| C3 | Temperature and option-value structure provide measurable proxies for initiative and forcedness. | Exact temperature labels, option-value distributions, positive/negative controls. | Legal move count, material delta, engine scalar evaluation. | Temperature fails to predict forcedness or move urgency beyond simple controls. | `theory_steward`, `exact_value_engineer` |
| C4 | Model-guided search can discover compact, verified, agency-rich positions more efficiently than random or heuristic search. | Verified gallery, search logs, leakage checks, beauty/agency metric rankings. | Random generation, material heuristic, handcrafted metric search. | Verified discovery precision does not beat baselines under matched budget. | `discovery_curator`, `verifier_red_team` |
| C5 | The benchmark supports reproducible evaluation of exact-label learning under OOD shift. | Dataset manifest, schema validation, deterministic regeneration, OOD split report. | N/A dataset contribution baseline is reproducibility and coverage. | Dataset cannot be regenerated or OOD splits leak by symmetry, graph hash, or generator family. | `dataset_foundry` |

## Reviewer Risks

- The domain may be too narrow. Mitigation: include explicit OOD composition and
  value-class tests, then state the domain as a controlled testbed rather than
  all of chess.
- Exact labels may be expensive. Mitigation: report throughput, shard size,
  proof-check rate, and generator failure accounting.
- Aesthetic metrics may look subjective. Mitigation: separate metric definitions
  from human-facing gallery examples, and report negative controls.
- Structured supervision may collapse to scalar proxies. Mitigation: include
  representation probes and ablations that remove temperature, decomposition,
  and option-structure labels independently.
