# Partizan formal domain v0.1

Status: frozen release-candidate contract.

This document is the single normative Partizan v0.1 domain specification.
Earlier Wave plans and reports remain historical records; when their prose
conflicts with this document, their artifact bytes remain valid but this scope
controls new public claims.

## Label classes

- `exact`: a declared finite solver produced a verified payload and certificate
  inside one of the domains below.
- `rejected`: input was retained but is outside the declared exact contract.
- `heuristic`: an estimate or diagnostic, excluded from exact supervision.
- `prediction`: a model output, never ground truth.

These classes are mutually exclusive. “Exact” is exact under the named finite
rule and certificate; it is not a claim of complete orthodox-chess value.

<a id="first-candidate-domain"></a>

## `formal_domain:first_constrained_chess:v0`

A FEN is eligible only when all of the following hold:

- Shakmaty parses it as a legal orthodox 8×8 chess position.
- The board contains at most eight pieces; non-pawn pieces are permitted.
- It has no castling rights and no en-passant target.
- It is terminal, has an immediate checkmating/stalemating move, or receives a
  strict Bitmesh structural partition under the declared certificate contract.

Bitmesh's positive result is a conservative current-position observation. It
does not prove that regions remain independent throughout future play or that
their CGT values add. A capture or move that could invalidate the boundary must
be represented inside the finite local rule or the candidate is rejected.

Repetition, the fifty-/seventy-five-move rules, historical draw claims, and
general draw propagation are outside v0.1. Astralbase `Unknown` is neither a
draw nor a proof. The terminal scalar hook is plumbing evidence only.

## `formal_domain:thermograph_golden_cgt:v0`

This is a non-chess control domain for finite normal-play CGT fixtures. Position
encoding is `cgt_canonical`. Its switch fixture can test structural payloads and
approximate thermography, but it is not chess-temperature evidence.

<a id="composition-fixture"></a>

## `formal_domain:bitmesh_composition_fixture:v0`

Synthetic fixture rows exercise nested BMCOMPOSE certificate validation.
Fixture FENs or abstract boards may not be reachable chess positions. They are
plumbing controls, not evidence of full-game decomposition, value correctness,
learned benefit, or discovery.

## `formal_domain:bitmesh_composed_chess:v0`

Generated orthodox-FEN candidates must first pass the constrained-chess gate.
Unsupported candidates remain structured rejections. Exact rows must identify
the finite component-value rule and bind:

- a Bitmesh decomposition digest and conservative one-ply proof contract;
- a non-empty root-to-component-value digest map;
- a BMCOMPOSE composition digest; and
- a Thermograph result payload digest.

These fields establish traceable provenance under P02. They do not upgrade a
one-ply observation to a theorem over all future play.

<a id="wave-18-board-material-composition"></a>

## `formal_domain:bitmesh_composed_board_material:v0`

This Board-level diagnostic domain can contain abstract 64-square constructions.
Acceptance does not establish reachability as orthodox chess. The Wave 47
frozen slice uses a depth-two local-move rule with material values at its depth
cutoff or at no-move leaves. “Exact” therefore means exact replay of that
declared bounded rule, not complete chess solution.

Each promoted row must include `component_topology_family`,
`composition_spec_source`, the solver depth/scope, and all P02 certificate
fields. Value-identity and split-leakage gates remain mandatory.

## Required position and provenance fields

Every dataset row carries the versioned schema, stable row ID, domain ID,
position encoding/text, and exactly one label payload. Exact rows additionally
carry generator/version/config/seed, domain definition, verifier/version, and
certificate. The normative field-level contract is
`docs/dataset_label_schema.md` and its executable validator is
`agents/label_schema.py`.

## Active evidence and blocked claims

- P01: locally evidenced for the frozen Wave 47 bytes, manifest hashes, and
  clean validation command.
- P02: locally evidenced for those 13 rows and a corrupted-certificate control.
- P03: partial; hashes and deterministic reports are frozen, but historical
  row provenance says `workspace`, so immutable regeneration equivalence is not
  yet a release claim.
- P04: negative/null; no learned decomposition benefit is a release claim.
- P05: unvalidated; chess temperature, learned agency, and model-guided
  discovery remain hypotheses or artistic interpretation only.

## Promotion criteria

New exact data must pass domain rejection, schema validation, independent
replay, value/certificate identity checks, deterministic generation, and
position/symmetry/component/result leakage checks. Reports must expose unseen
target labels, weak controls, negative results, resource limits, and every
skipped optional integration artifact. No missing required input may be treated
as a pass.
