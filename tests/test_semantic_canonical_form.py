from __future__ import annotations

import copy
import hashlib
import importlib.util
import itertools
import sys
import unittest
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "python" / "partizan" / "bounded_short_game.py"
SPEC = importlib.util.spec_from_file_location(
    "_partizan_semantic_canonical_form_tests", MODULE_PATH
)
bounded = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = bounded
assert SPEC.loader is not None
SPEC.loader.exec_module(bounded)


ZERO = {"left": [], "right": []}
ONE = {"left": [ZERO], "right": []}
MINUS_ONE = {"left": [], "right": [ZERO]}
TWO = {"left": [ONE], "right": []}
STAR = {"left": [ZERO], "right": [ZERO]}
HALF = {"left": [ZERO], "right": [ONE]}
ELKIES_HALF = {"left": [ZERO, STAR], "right": [ONE]}


def game_sum(left: dict, right: dict) -> dict:
    return {
        "left": [game_sum(option, right) for option in left["left"]]
        + [game_sum(left, option) for option in right["left"]],
        "right": [game_sum(option, right) for option in left["right"]]
        + [game_sum(left, option) for option in right["right"]],
    }


class SemanticCanonicalFormTests(unittest.TestCase):
    def assert_canonicalizes(self, source: dict, expected: dict) -> None:
        result = bounded.semantic_canonical_form_bounded(source)
        expected_result = bounded.semantic_canonical_form_bounded(expected)
        self.assertEqual(result.canonical_game, expected_result.canonical_game)
        self.assertEqual(
            result.semantic_canonical_id_v1,
            expected_result.semantic_canonical_id_v1,
        )
        self.assertTrue(result.soundness_equal)
        self.assertTrue(result.irreducible)
        self.assertTrue(result.idempotent)
        self.assertEqual(
            bounded.validate_semantic_canonical_form_bounded(
                source,
                result.canonical_game,
                claimed_semantic_canonical_id_v1=(result.semantic_canonical_id_v1),
            ),
            (True, "valid"),
        )

    def test_standard_integer_and_dyadic_trees_are_stable(self) -> None:
        for game in (ZERO, ONE, MINUS_ONE, TWO, HALF, STAR):
            with self.subTest(game=game):
                result = bounded.semantic_canonical_form_bounded(game)
                self.assertEqual(result.canonical_game, game)
                self.assertEqual(result.rewrite_count, 0)
                self.assertEqual(
                    bounded.semantic_canonical_id_v1(game),
                    result.semantic_canonical_id_v1,
                )
                self.assertEqual(
                    result.semantic_canonical_id_v1,
                    hashlib.sha256(
                        bounded.SEMANTIC_CANONICAL_SHA256_V1_PREFIX
                        + result.canonical_serialization.encode("ascii")
                    ).hexdigest(),
                )

    def test_elkies_form_reduces_to_half(self) -> None:
        result = bounded.semantic_canonical_form_bounded(ELKIES_HALF)
        self.assertEqual(result.canonical_game, HALF)
        self.assertIn(
            "left_reversibility",
            [step["rule"] for step in result.rewrite_trace],
        )
        self.assert_canonicalizes(ELKIES_HALF, HALF)

    def test_left_and_right_domination(self) -> None:
        left_dominated = {"left": [MINUS_ONE, ZERO], "right": []}
        right_dominated = {"left": [], "right": [ZERO, ONE]}
        left_result = bounded.semantic_canonical_form_bounded(left_dominated)
        right_result = bounded.semantic_canonical_form_bounded(right_dominated)
        self.assertEqual(left_result.canonical_game, ONE)
        self.assertEqual(right_result.canonical_game, MINUS_ONE)
        self.assertIn(
            "left_domination",
            [step["rule"] for step in left_result.rewrite_trace],
        )
        self.assertIn(
            "right_domination",
            [step["rule"] for step in right_result.rewrite_trace],
        )

    def test_left_and_right_reversibility_reduce_to_zero(self) -> None:
        left_reversible = {"left": [MINUS_ONE], "right": []}
        right_reversible = {"left": [], "right": [ONE]}
        left_result = bounded.semantic_canonical_form_bounded(left_reversible)
        right_result = bounded.semantic_canonical_form_bounded(right_reversible)
        self.assertEqual(left_result.canonical_game, ZERO)
        self.assertEqual(right_result.canonical_game, ZERO)
        self.assertIn(
            "left_reversibility",
            [step["rule"] for step in left_result.rewrite_trace],
        )
        self.assertIn(
            "right_reversibility",
            [step["rule"] for step in right_result.rewrite_trace],
        )

    def test_star_plus_star_reduces_to_zero(self) -> None:
        star_plus_star = game_sum(STAR, STAR)
        result = bounded.semantic_canonical_form_bounded(star_plus_star)
        self.assertEqual(result.canonical_game, ZERO)
        self.assertEqual(
            result.semantic_canonical_id_v1, bounded.semantic_canonical_id_v1(ZERO)
        )
        self.assertGreaterEqual(result.rewrite_count, 2)

    def test_fuzzy_games_retain_unequal_semantic_ids(self) -> None:
        comparison = bounded.compare_short_game_bounded(ZERO, STAR)
        self.assertEqual(comparison.outcome, bounded.ComparisonOutcome.FUZZY)
        self.assertNotEqual(
            bounded.semantic_canonical_id_v1(ZERO),
            bounded.semantic_canonical_id_v1(STAR),
        )

    def test_canonical_and_rewrite_limits_are_typed(self) -> None:
        canonical_profile = bounded.BoundedResourceProfile(
            maximum_root_birthday=2,
            maximum_canonical_birthday=1,
        )
        with self.assertRaises(bounded.ResourceLimitError) as canonical:
            bounded.semantic_canonical_form_bounded(
                TWO,
                profile=canonical_profile,
            )
        self.assertEqual(canonical.exception.resource, "canonical_birthday")

        with self.assertRaises(bounded.ResourceLimitError) as rewrites:
            bounded.semantic_canonical_form_bounded(
                game_sum(STAR, STAR),
                maximum_rewrite_steps=1,
            )
        self.assertEqual(rewrites.exception.resource, "canonical_rewrite_steps")

    def test_validator_rejects_wrong_form_and_identifier(self) -> None:
        self.assertFalse(
            bounded.validate_semantic_canonical_form_bounded(
                STAR,
                ZERO,
            )[0]
        )
        self.assertFalse(
            bounded.validate_semantic_canonical_form_bounded(
                ELKIES_HALF,
                HALF,
                claimed_semantic_canonical_id_v1="0" * 64,
            )[0]
        )

    def test_v1_certificate_stays_frozen_and_v2_binds_semantic_ids(self) -> None:
        bindings = {
            "candidate_binding": {"artifact": "elkies-half"},
            "target_binding": {"artifact": "half"},
        }
        v1 = bounded.build_short_game_comparison_certificate_v1(
            ELKIES_HALF,
            HALF,
            **bindings,
        )
        self.assertEqual(
            v1["semantic_canonical"],
            {
                "status": bounded.CANONICALIZATION_STATUS,
                "candidate_semantic_canonical_id": None,
                "target_semantic_canonical_id": None,
            },
        )
        v2 = bounded.build_short_game_comparison_certificate_v2(
            ELKIES_HALF,
            HALF,
            **bindings,
        )
        self.assertEqual(
            v2["schema_version"],
            bounded.CERTIFICATE_SCHEMA_VERSION_V2,
        )
        self.assertEqual(
            v2["semantic_canonical"]["candidate_semantic_canonical_id"],
            v2["semantic_canonical"]["target_semantic_canonical_id"],
        )
        self.assertEqual(
            bounded.verify_short_game_comparison_certificate_v2(
                v2,
                expected_candidate_binding=bindings["candidate_binding"],
                expected_target_binding=bindings["target_binding"],
            ),
            (True, "valid"),
        )

        mutation = copy.deepcopy(v2)
        mutation["semantic_canonical"]["candidate_semantic_canonical_id"] = "0" * 64
        mutation.pop("certificate_sha256")
        mutation["certificate_sha256"] = hashlib.sha256(
            bounded.canonical_json_bytes(mutation)
        ).hexdigest()
        self.assertFalse(
            bounded.verify_short_game_comparison_certificate_v2(mutation)[0]
        )

    def test_reduction_is_byte_deterministic_and_idempotent(self) -> None:
        first = bounded.semantic_canonical_form_bounded(ELKIES_HALF)
        second = bounded.semantic_canonical_form_bounded(ELKIES_HALF)
        repeated = bounded.semantic_canonical_form_bounded(first.canonical_game)
        self.assertEqual(first.rewrite_trace, second.rewrite_trace)
        self.assertEqual(
            first.semantic_canonical_id_v1,
            repeated.semantic_canonical_id_v1,
        )
        self.assertEqual(repeated.rewrite_count, 0)


@dataclass(frozen=True)
class TinyGame:
    left: tuple["TinyGame", ...] = ()
    right: tuple["TinyGame", ...] = ()


def tiny_serialization(game: TinyGame) -> str:
    return (
        "{"
        + ",".join(tiny_serialization(option) for option in game.left)
        + "|"
        + ",".join(tiny_serialization(option) for option in game.right)
        + "}"
    )


def tiny_game(
    left: tuple[TinyGame, ...] = (),
    right: tuple[TinyGame, ...] = (),
) -> TinyGame:
    return TinyGame(
        tuple(sorted(set(left), key=tiny_serialization)),
        tuple(sorted(set(right), key=tiny_serialization)),
    )


def powerset(values: tuple[TinyGame, ...]):
    for size in range(len(values) + 1):
        yield from itertools.combinations(values, size)


def tiny_to_json(game: TinyGame) -> dict:
    return {
        "left": [tiny_to_json(option) for option in game.left],
        "right": [tiny_to_json(option) for option in game.right],
    }


class DayTwoCanonicalConformanceTests(unittest.TestCase):
    def test_256_day_two_games_reduce_to_exactly_22_ids(self) -> None:
        zero = tiny_game()
        day_one = tuple(
            sorted(
                {
                    tiny_game(left, right)
                    for left in powerset((zero,))
                    for right in powerset((zero,))
                },
                key=tiny_serialization,
            )
        )
        day_two = tuple(
            sorted(
                {
                    tiny_game(left, right)
                    for left in powerset(day_one)
                    for right in powerset(day_one)
                },
                key=tiny_serialization,
            )
        )
        self.assertEqual(len(day_two), 256)
        results = [
            bounded.semantic_canonical_form_bounded(tiny_to_json(game))
            for game in day_two
        ]
        actual_ids = sorted(
            {result.semantic_canonical_id_v1 for result in results}
        )
        fixture = (
            ROOT / "tests" / "fixtures" / "semantic" / "day2-semantic-ids-v1.txt"
        )
        expected_ids = fixture.read_text(encoding="ascii").splitlines()
        self.assertEqual(
            actual_ids,
            expected_ids,
        )
        self.assertTrue(
            all(
                result.soundness_equal and result.irreducible and result.idempotent
                for result in results
            )
        )


if __name__ == "__main__":
    unittest.main()
