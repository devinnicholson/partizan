# GitHub repository settings

These settings make the four repositories legible as one maintained research
software family. Apply them after the local hardening branches pass integration
review.

## Public metadata

| Repository | Description | Topics |
| --- | --- | --- |
| Partizan | Proof-carrying fixed-value search for finite combinatorial games and constrained chess | `combinatorial-game-theory`, `chess`, `creative-computation`, `exact-verification`, `python`, `rust`, `research-software` |
| Thermograph | Exact bounded comparison, canonicalization, and approximate thermography for finite partizan games | `combinatorial-game-theory`, `canonical-form`, `thermography`, `surreal-numbers`, `rust`, `mathematics` |
| Bitmesh | Conservative structural decomposition certificates for orthodox-chess bitboards | `chess`, `bitboards`, `graph-decomposition`, `certificates`, `rust`, `research-software` |
| Astralbase | Bounded in-memory retrograde exploration from declared orthodox-chess seeds | `chess`, `retrograde-analysis`, `game-solving`, `rust`, `research-software` |

Partizan serves as the ecosystem homepage until a documentation site has a
stable public URL. Rust packages use their docs.rs pages after publication.

## Default branches

Thermograph, Bitmesh, and Astralbase currently use `master`. Rename each to
`main`, update local tracking branches, documentation links, CI filters, and
cross-repository references, then retain GitHub's branch redirect. Commit
identities remain unchanged.

## Repository rulesets

Protect `main` with:

- required status checks from the repository CI workflow;
- required branch freshness when cross-repository compatibility can change;
- force pushes and branch deletion disabled;
- conversation resolution for reviewed pull requests;
- administrator bypass retained for security recovery; and
- tag protection for `v*` release tags.

A solo-maintainer repository can permit zero required approving reviews while
still enforcing CI and protected history. Increase the review requirement when
another maintainer joins.

## Features

- Keep Issues enabled and use the checked-in forms.
- Enable private vulnerability reporting.
- Disable empty Wikis.
- Keep Discussions disabled until there is a moderation and response plan.
- Enable dependency graph, Dependabot alerts, and secret scanning wherever the
  repository and GitHub account support them.
- Use squash merging for focused changes and preserve intentional release
  commits when their history carries provenance value.

## Release settings

Release workflows require manual dispatch and an exact tag/version input.
Ordinary pushes and pull requests run dry-run package checks only. Registry
credentials use the narrowest supported repository or environment scope, and
the release environment requires maintainer approval.
