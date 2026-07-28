from __future__ import annotations

import copy
import hashlib
import importlib.util
import itertools
import sys
import unittest
from dataclasses import dataclass
from functools import cache
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "python" / "partizan" / "bounded_short_game.py"
SPEC = importlib.util.spec_from_file_location(
    "_partizan_bounded_short_game_tests", MODULE_PATH
)
bounded = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = bounded
assert SPEC.loader is not None
SPEC.loader.exec_module(bounded)


ZERO = {"left": [], "right": []}
ONE = {"left": [ZERO], "right": []}
MINUS_ONE = {"left": [], "right": [ZERO]}
STAR = {"left": [ZERO], "right": [ZERO]}


def rehash(certificate: dict[str, object]) -> None:
    payload = copy.deepcopy(certificate)
    payload.pop("certificate_sha256")
    certificate["certificate_sha256"] = hashlib.sha256(
        bounded.canonical_json_bytes(payload)
    ).hexdigest()


class BoundedShortGameTests(unittest.TestCase):
    def test_four_comparison_outcomes_and_semantic_equality(self) -> None:
        cases = (
            (ZERO, ZERO, bounded.ComparisonOutcome.EQUAL),
            (ONE, ZERO, bounded.ComparisonOutcome.GREATER),
            (ZERO, ONE, bounded.ComparisonOutcome.LESS),
            (ZERO, STAR, bounded.ComparisonOutcome.FUZZY),
        )
        for left, right, outcome in cases:
            with self.subTest(outcome=outcome):
                comparison = bounded.compare_short_game_bounded(left, right)
                self.assertEqual(comparison.outcome, outcome)
                self.assertEqual(
                    bounded.equal_short_game_bounded(left, right),
                    outcome is bounded.ComparisonOutcome.EQUAL,
                )

    def test_transport_uses_brace_serialization_and_unambiguous_counts(self) -> None:
        transport = bounded.literal_game_transport_bounded(STAR)
        self.assertEqual(transport["root_literal_serialization"], "{{|}|{|}}")
        self.assertEqual(
            transport["root_legacy_literal_sha256"],
            hashlib.sha256(b"{{|}|{|}}").hexdigest(),
        )
        self.assertEqual(
            transport["root_literal_sha256_v1"],
            hashlib.sha256(bounded.LITERAL_SHA256_V1_PREFIX + b"{{|}|{|}}").hexdigest(),
        )
        self.assertEqual(
            transport["resources"],
            {
                "root_birthday": 1,
                "literal_occurrence_node_count": 3,
                "literal_distinct_dag_node_count": 2,
                "literal_option_reference_count": 2,
                "literal_serialization_bytes": 9,
            },
        )

    def test_named_profiles_are_frozen_and_default_to_order7(self) -> None:
        self.assertIs(
            bounded.DEFAULT_RESOURCE_PROFILE,
            bounded.ORDER7_RESOURCE_PROFILE,
        )
        self.assertEqual(
            bounded.ORDER7_RESOURCE_PROFILE.profile_id,
            "partizan.bounded_short_game.order7.v1",
        )
        self.assertEqual(
            bounded.DIGRAPH8_RESOURCE_PROFILE.profile_id,
            "partizan.bounded_short_game.digraph8.v1",
        )
        self.assertEqual(
            bounded.BoundedResourceProfile.from_record(
                bounded.ORDER7_RESOURCE_PROFILE.as_record()
            ),
            bounded.ORDER7_RESOURCE_PROFILE,
        )
        relaxed = bounded.ORDER7_RESOURCE_PROFILE.as_record()
        relaxed["maximum_comparison_dag_rows"] += 1
        with self.assertRaisesRegex(ValueError, "relaxes unsupported"):
            bounded.BoundedResourceProfile.from_record(relaxed)

    def test_resource_limits_are_typed(self) -> None:
        profile = bounded.BoundedResourceProfile(
            maximum_root_birthday=1,
            maximum_canonical_birthday=1,
        )
        two = {"left": [ONE], "right": []}
        with self.assertRaises(bounded.ResourceLimitError) as captured:
            bounded.compare_short_game_bounded(two, ZERO, profile=profile)
        self.assertEqual(
            captured.exception.as_record(),
            {
                "status": "resource_limit",
                "resource": "root_birthday",
                "limit": 1,
                "observed": 2,
            },
        )

    def test_interner_checks_bytes_when_digests_collide(self) -> None:
        digest_overrides = (
            {"legacy_digest_function": lambda _: "0" * 64},
            {"versioned_digest_function": lambda _: "0" * 64},
        )
        for digest_override in digest_overrides:
            with self.subTest(digest_override=tuple(digest_override)):
                interner = bounded._GameInterner(  # pylint: disable=protected-access
                    bounded.DEFAULT_RESOURCE_PROFILE,
                    **digest_override,
                )
                interner.intern(ZERO)
                with self.assertRaises(bounded.DigestCollisionError):
                    interner.intern(ONE)

    def test_built_certificates_self_verify_for_all_outcomes(self) -> None:
        cases = ((ZERO, ZERO), (ONE, ZERO), (ZERO, ONE), (ZERO, STAR))
        for index, (candidate, target) in enumerate(cases):
            candidate_binding = {"artifact": f"candidate-{index}"}
            target_binding = {"artifact": f"target-{index}"}
            with self.subTest(index=index):
                certificate = bounded.build_short_game_comparison_certificate_v1(
                    candidate,
                    target,
                    candidate_binding=candidate_binding,
                    target_binding=target_binding,
                )
                self.assertEqual(
                    bounded.verify_short_game_comparison_certificate_v1(
                        certificate,
                        expected_candidate_binding=candidate_binding,
                        expected_target_binding=target_binding,
                    ),
                    (True, "valid"),
                )

    def test_rehashed_unreachable_game_table_row_is_rejected(self) -> None:
        certificate = bounded.build_short_game_comparison_certificate_v1(
            ZERO,
            ZERO,
            candidate_binding={"artifact": "candidate"},
            target_binding={"artifact": "target"},
        )
        one_transport = bounded.literal_game_transport_bounded(ONE)
        extra = next(
            row
            for row in one_transport["game_table"]
            if row["literal_serialization"] != "{|}"
        )
        certificate["game_table"].append(extra)
        certificate["game_table"].sort(key=lambda row: row["literal_sha256_v1"])
        rehash(certificate)
        valid, reason = bounded.verify_short_game_comparison_certificate_v1(certificate)
        self.assertFalse(valid)
        self.assertEqual(reason, "game table contains unreachable rows")

    def test_rehashed_resource_and_comparison_mutations_are_rejected(self) -> None:
        original = bounded.build_short_game_comparison_certificate_v1(
            STAR,
            ZERO,
            candidate_binding={"artifact": "candidate"},
            target_binding={"artifact": "target"},
        )
        mutations = []

        resource = copy.deepcopy(original)
        resource["resources"]["candidate"]["literal_distinct_dag_node_count"] += 1
        rehash(resource)
        mutations.append(resource)

        comparison = copy.deepcopy(original)
        comparison["comparison_dag"][0]["result"] = not comparison["comparison_dag"][0][
            "result"
        ]
        rehash(comparison)
        mutations.append(comparison)

        legacy_identity = copy.deepcopy(original)
        legacy_identity["game_table"][0]["legacy_literal_sha256"] = "0" * 64
        rehash(legacy_identity)
        mutations.append(legacy_identity)

        versioned_identity = copy.deepcopy(original)
        versioned_identity["game_table"][0]["literal_sha256_v1"] = "0" * 64
        versioned_identity["game_table"].sort(key=lambda row: row["literal_sha256_v1"])
        rehash(versioned_identity)
        mutations.append(versioned_identity)

        for mutation in mutations:
            self.assertFalse(
                bounded.verify_short_game_comparison_certificate_v1(mutation)[0]
            )


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


@cache
def tiny_leq(left: TinyGame, right: TinyGame) -> bool:
    return all(not tiny_leq(right, option) for option in left.left) and all(
        not tiny_leq(option, left) for option in right.right
    )


def powerset(values: tuple[TinyGame, ...]):
    for size in range(len(values) + 1):
        yield from itertools.combinations(values, size)


def tiny_to_json(game: TinyGame) -> dict[str, object]:
    return {
        "left": [tiny_to_json(option) for option in game.left],
        "right": [tiny_to_json(option) for option in game.right],
    }


class DayTwoConformanceTests(unittest.TestCase):
    def test_all_65536_ordered_day_two_comparisons(self) -> None:
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
        encoded = [tiny_to_json(game) for game in day_two]
        for left_index, left in enumerate(day_two):
            for right_index, right in enumerate(day_two):
                observed = bounded.compare_short_game_bounded(
                    encoded[left_index],
                    encoded[right_index],
                )
                self.assertEqual(
                    observed.left_leq_right,
                    tiny_leq(left, right),
                    (left_index, right_index),
                )
                self.assertEqual(
                    observed.right_leq_left,
                    tiny_leq(right, left),
                    (left_index, right_index),
                )


if __name__ == "__main__":
    unittest.main()
