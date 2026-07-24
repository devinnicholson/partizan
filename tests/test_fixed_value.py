from __future__ import annotations

import importlib.util
import json
import sys
import types
import unittest
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "_partizan_fixed_value_tests"
PACKAGE_PATH = ROOT / "python" / "partizan"
package = types.ModuleType(PACKAGE_NAME)
package.__path__ = [str(PACKAGE_PATH)]
sys.modules[PACKAGE_NAME] = package


def load_package_module(name: str):
    qualified_name = f"{PACKAGE_NAME}.{name}"
    spec = importlib.util.spec_from_file_location(
        qualified_name, PACKAGE_PATH / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[qualified_name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


fixed_value = load_package_module("fixed_value")
fixed_value_cli = load_package_module("fixed_value_cli")

FIXTURES = ROOT / "tests" / "fixtures" / "fixed_value"
TARGET_PATH = FIXTURES / "target-zero.valid.json"
CANDIDATES_PATH = FIXTURES / "candidates-zero.valid.jsonl"


class FixedValueExplorerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.target = fixed_value.load_json(TARGET_PATH)
        self.candidates = fixed_value.load_jsonl(CANDIDATES_PATH)

    def build(self, **overrides):
        settings = {"seed": 0, "budget": 5, "max_results": 5}
        settings.update(overrides)
        return fixed_value.build_repertoire(self.target, self.candidates, **settings)

    def test_fixture_contracts_and_ids_are_valid(self) -> None:
        self.assertEqual(fixed_value.validate_target(self.target), [])
        for candidate in self.candidates:
            self.assertEqual(fixed_value.validate_candidate(candidate), [])
            self.assertEqual(
                candidate["candidate_id"],
                fixed_value.candidate_id_for(candidate),
            )
        self.assertEqual(
            CANDIDATES_PATH.read_bytes(),
            fixed_value.canonical_jsonl_bytes(self.candidates),
        )

    def test_exact_order_finds_distinct_literal_zero(self) -> None:
        zero = self.target["literal_game"]
        expanded_zero = self.candidates[2]["literal_game"]
        star = self.candidates[3]["literal_game"]
        equality = fixed_value.compare_short_games(expanded_zero, zero)
        mismatch = fixed_value.compare_short_games(star, zero)
        self.assertTrue(equality.left_ge_right)
        self.assertTrue(equality.right_ge_left)
        self.assertTrue(equality.equivalent)
        self.assertFalse(mismatch.left_ge_right)
        self.assertFalse(mismatch.right_ge_left)
        self.assertFalse(mismatch.equivalent)

    def test_recursive_order_matches_basic_short_games(self) -> None:
        zero = {"left": [], "right": []}
        one = {"left": [zero], "right": []}
        minus_one = {"left": [], "right": [zero]}
        one_vs_zero = fixed_value.compare_short_games(one, zero)
        minus_one_vs_zero = fixed_value.compare_short_games(minus_one, zero)
        self.assertTrue(one_vs_zero.left_ge_right)
        self.assertFalse(one_vs_zero.right_ge_left)
        self.assertFalse(minus_one_vs_zero.left_ge_right)
        self.assertTrue(minus_one_vs_zero.right_ge_left)

    def test_literal_identity_ignores_option_order_and_duplicates(self) -> None:
        zero = {"left": [], "right": []}
        one = {"left": [zero], "right": []}
        ordered = {"left": [zero, one], "right": []}
        reordered_with_duplicate = {
            "left": [one, zero, zero],
            "right": [],
        }
        self.assertEqual(
            fixed_value.literal_game_sha256(ordered),
            fixed_value.literal_game_sha256(reordered_with_duplicate),
        )
        self.assertEqual(
            fixed_value.canonicalize_literal_game(reordered_with_duplicate),
            fixed_value.canonicalize_literal_game(ordered),
        )

    def test_search_exposes_both_fixed_value_transition_classes(self) -> None:
        repertoire = self.build()
        self.assertEqual(fixed_value.validate_repertoire(repertoire), [])
        self.assertEqual(
            repertoire["summary"],
            {
                "source_candidate_count": 5,
                "evaluated_candidate_count": 5,
                "admitted_count": 3,
                "outcome_counts": {
                    "admitted": 3,
                    "duplicate_embodiment": 1,
                    "value_mismatch": 1,
                },
                "termination_reason": "candidate_stream_exhausted",
            },
        )
        transition_kinds = {
            entry["admission_relation"]["transition_kind"]
            for entry in repertoire["entries"]
        }
        self.assertIn("embodiment_only", transition_kinds)
        self.assertIn("literal_game_crossing", transition_kinds)
        prior_ids: set[str] = set()
        for index, entry in enumerate(repertoire["entries"]):
            relation = entry["admission_relation"]
            if index == 0:
                self.assertEqual(relation["transition_kind"], "initial")
                self.assertIsNone(relation["witness_candidate_id"])
            else:
                self.assertIn(relation["witness_candidate_id"], prior_ids)
            prior_ids.add(entry["candidate_id"])

    def test_generator_constructs_verified_literal_crossings(self) -> None:
        candidates = fixed_value.generate_candidates(
            self.target,
            seed=23,
            count=8,
            max_expansion_depth=3,
        )
        self.assertEqual(
            fixed_value.canonical_jsonl_bytes(candidates),
            fixed_value.canonical_jsonl_bytes(
                fixed_value.generate_candidates(
                    self.target,
                    seed=23,
                    count=8,
                    max_expansion_depth=3,
                )
            ),
        )
        repertoire = fixed_value.build_repertoire(
            self.target,
            candidates,
            seed=23,
            budget=8,
            max_results=8,
        )
        self.assertEqual(repertoire["summary"]["admitted_count"], 8)
        self.assertEqual(repertoire["summary"]["outcome_counts"]["value_mismatch"], 0)
        transition_kinds = {
            entry["admission_relation"]["transition_kind"]
            for entry in repertoire["entries"]
        }
        self.assertIn("embodiment_only", transition_kinds)
        self.assertIn("literal_game_crossing", transition_kinds)
        self.assertEqual(fixed_value.validate_repertoire(repertoire), [])

    def test_reversible_generator_preserves_varied_short_games(self) -> None:
        zero = {"left": [], "right": []}
        one = {"left": [zero], "right": []}
        minus_one = {"left": [], "right": [zero]}
        star = {"left": [zero], "right": [zero]}
        up = {"left": [zero], "right": [star]}
        for name, game in (
            ("zero", zero),
            ("one", one),
            ("minus-one", minus_one),
            ("star", star),
            ("up", up),
        ):
            with self.subTest(name):
                target = fixed_value.make_target(name, game)
                candidates = fixed_value.generate_candidates(
                    target,
                    seed=99,
                    count=6,
                    max_expansion_depth=2,
                )
                for candidate in candidates:
                    self.assertTrue(
                        fixed_value.compare_short_games(
                            candidate["literal_game"],
                            target["literal_game"],
                        ).equivalent
                    )

    def test_search_is_byte_deterministic(self) -> None:
        first = fixed_value.canonical_json_bytes(self.build())
        second = fixed_value.canonical_json_bytes(self.build())
        self.assertEqual(first, second)
        self.assertEqual(
            json.loads(first)["repertoire_id"],
            "fixed-repertoire-sha256:"
            "7b3f0a6de3b19a726a5250a33b8e5dfd9e97ce4d36c0fe88e92d92e7379471df",
        )

    def test_replay_rejects_certificate_corruption(self) -> None:
        repertoire = self.build()
        repertoire["evaluations"][0]["certificate"]["candidate_ge_target"] = False
        self.assertIn(
            "repertoire does not match deterministic replay",
            fixed_value.validate_repertoire(repertoire),
        )

    def test_candidate_value_and_identity_fail_closed(self) -> None:
        wrong_value = deepcopy(self.candidates[0])
        wrong_value["literal_game"] = self.candidates[3]["literal_game"]
        self.assertIn(
            "candidate.candidate_id does not bind the candidate payload",
            fixed_value.validate_candidate(wrong_value),
        )
        duplicate_id_stream = self.candidates + [deepcopy(self.candidates[0])]
        with self.assertRaisesRegex(ValueError, "duplicate candidate_id"):
            fixed_value.build_repertoire(
                self.target,
                duplicate_id_stream,
                seed=0,
                budget=6,
                max_results=6,
            )
        float_metadata = deepcopy(self.candidates[0])
        float_metadata["representation"]["metadata"]["score"] = 0.5
        float_metadata["candidate_id"] = fixed_value.candidate_id_for(float_metadata)
        self.assertIn(
            "candidate.representation.metadata.score cannot contain floats",
            fixed_value.validate_candidate(float_metadata),
        )
        embodiment_conflict = deepcopy(self.candidates[0])
        embodiment_conflict["ordinal"] = 5
        embodiment_conflict["literal_game"] = self.candidates[2]["literal_game"]
        embodiment_conflict["generator"]["operator"] = "conflicting-game"
        embodiment_conflict["candidate_id"] = fixed_value.candidate_id_for(
            embodiment_conflict
        )
        with self.assertRaisesRegex(
            ValueError, "embodiment binds conflicting literal games"
        ):
            fixed_value.build_repertoire(
                self.target,
                [self.candidates[0], embodiment_conflict],
                seed=0,
                budget=2,
                max_results=2,
            )

    def test_budget_and_repertoire_limit_are_explicit(self) -> None:
        budget_limited = self.build(budget=2)
        self.assertEqual(
            budget_limited["summary"]["termination_reason"],
            "verification_budget_reached",
        )
        self.assertEqual(budget_limited["summary"]["evaluated_candidate_count"], 2)
        result_limited = self.build(max_results=1)
        self.assertEqual(
            result_limited["summary"]["termination_reason"],
            "repertoire_limit_reached",
        )
        self.assertEqual(result_limited["summary"]["admitted_count"], 1)

    def test_compare_reports_literal_and_descriptor_changes(self) -> None:
        repertoire = self.build()
        by_text = {
            entry["representation"]["text"]: entry for entry in repertoire["entries"]
        }
        comparison = fixed_value.compare_repertoire_entries(
            repertoire,
            by_text["empty field"]["candidate_id"],
            by_text["a gate between -1 and 1"]["candidate_id"],
        )
        self.assertEqual(comparison["transition_kind"], "literal_game_crossing")
        self.assertFalse(comparison["same_literal_game"])
        self.assertEqual(
            comparison["descriptor_delta_right_minus_left"]["literal_node_count"],
            4,
        )

    def test_cli_search_and_verify(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "repertoire.json"
            self.assertEqual(
                fixed_value_cli.main(
                    [
                        "search",
                        "--target",
                        str(TARGET_PATH),
                        "--candidates",
                        str(CANDIDATES_PATH),
                        "--seed",
                        "0",
                        "--budget",
                        "5",
                        "--max-results",
                        "5",
                        "--output",
                        str(output),
                    ]
                ),
                0,
            )
            self.assertEqual(fixed_value_cli.main(["verify", str(output)]), 0)
            self.assertEqual(
                fixed_value.validate_repertoire(
                    json.loads(output.read_text(encoding="utf-8"))
                ),
                [],
            )

    def test_cli_explore_generates_and_certifies(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "generated-repertoire.json"
            self.assertEqual(
                fixed_value_cli.main(
                    [
                        "explore",
                        "--target",
                        str(TARGET_PATH),
                        "--seed",
                        "23",
                        "--count",
                        "8",
                        "--max-expansion-depth",
                        "3",
                        "--budget",
                        "8",
                        "--max-results",
                        "8",
                        "--output",
                        str(output),
                    ]
                ),
                0,
            )
            repertoire = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(repertoire["summary"]["admitted_count"], 8)
            self.assertEqual(
                fixed_value.validate_repertoire(repertoire),
                [],
            )


if __name__ == "__main__":
    unittest.main()
