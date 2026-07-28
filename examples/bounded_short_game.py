"""Run the source-only bounded exact short-game workflow."""

from __future__ import annotations

import json

from partizan import (
    CANONICALIZATION_STATUS,
    ComparisonOutcome,
    build_short_game_comparison_certificate_v1,
    build_short_game_comparison_certificate_v2,
    compare_short_game_bounded,
    semantic_canonical_form_bounded,
    verify_short_game_comparison_certificate_v2,
)


def main() -> None:
    zero = {"left": [], "right": []}
    one = {"left": [zero], "right": []}
    star = {"left": [zero], "right": [zero]}
    half = {"left": [zero], "right": [one]}
    elkies_half = {"left": [zero, star], "right": [one]}
    candidate_binding = {"artifact": "elkies-half"}
    target_binding = {"artifact": "half"}

    fuzzy = compare_short_game_bounded(zero, star)
    assert fuzzy.outcome is ComparisonOutcome.FUZZY

    canonical = semantic_canonical_form_bounded(elkies_half)
    assert canonical.canonical_game == half
    assert canonical.soundness_equal
    assert canonical.irreducible
    assert canonical.idempotent

    v1 = build_short_game_comparison_certificate_v1(
        elkies_half,
        half,
        candidate_binding=candidate_binding,
        target_binding=target_binding,
    )
    assert v1["semantic_canonical"] == {
        "status": CANONICALIZATION_STATUS,
        "candidate_semantic_canonical_id": None,
        "target_semantic_canonical_id": None,
    }

    v2 = build_short_game_comparison_certificate_v2(
        elkies_half,
        half,
        candidate_binding=candidate_binding,
        target_binding=target_binding,
    )
    assert verify_short_game_comparison_certificate_v2(
        v2,
        expected_candidate_binding=candidate_binding,
        expected_target_binding=target_binding,
    ) == (True, "valid")

    print(
        json.dumps(
            {
                "elkies_half_canonical": canonical.canonical_serialization,
                "elkies_half_semantic_id": canonical.semantic_canonical_id_v1,
                "rewrite_rules": [step["rule"] for step in canonical.rewrite_trace],
                "v1_semantic_status": v1["semantic_canonical"]["status"],
                "v2_certificate_valid": True,
                "zero_vs_star": fuzzy.outcome.value,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
