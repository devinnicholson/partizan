from __future__ import annotations

import json
import unittest
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory

import partizan
from partizan.fixed_value_cli import main as fixed_value_cli_main

TERMINAL_FEN = "7k/5KQ1/8/8/8/8/8/8 b - - 0 1"
MATE_FRONTIER_FEN = "7k/5K2/6Q1/8/8/8/8/8 w - - 0 1"
OUTSIDE_DOMAIN_FEN = "8/8/8/8/8/8/8/4K2k w - - 0 1"
CROSSING_LEFT_FEN = "7k/8/5K2/8/8/8/8/6Q1 w - - 0 1"
CROSSING_RIGHT_FEN = "7k/8/5KQ1/8/8/8/8/8 w - - 0 1"
LEGACY_V01_FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures/fixed_value/chess-adapter-v0.1.valid.json"
)


class BoundedChessAdapterTests(unittest.TestCase):
    def test_current_contract_binds_hardened_release_candidates(self) -> None:
        record = partizan.adapt_chess_position(
            TERMINAL_FEN,
            max_plies=2,
            node_budget=100,
        )

        self.assertEqual(
            record["schema_version"],
            "partizan.bounded_chess_adapter.v0.2",
        )
        self.assertEqual(
            record["native_adapter_version"],
            "partizan.bounded_chess_adapter.native.v0.2",
        )
        self.assertEqual(
            {
                name: source["source_commit"]
                for name, source in record["upstream_sources"].items()
            },
            {
                "astralbase": "0e36d14b78a7a4915689e510bff6d7c0f20152e4",
                "bitmesh": "410550c0964004cd7ba9677539f17ae82c139dd8",
                "thermograph": "32d6bfbc966f47a87e7249d4ed8818370288e079",
            },
        )

    def test_legacy_v01_record_remains_replayable(self) -> None:
        record = json.loads(LEGACY_V01_FIXTURE.read_text(encoding="utf-8"))

        self.assertEqual(partizan.validate_chess_adapter_record(record), [])

        mixed = deepcopy(record)
        mixed["schema_version"] = "partizan.bounded_chess_adapter.v0.2"
        mixed["adapter_id"] = partizan.chess_adapter_id_for(mixed)
        self.assertIn(
            "adapter native_adapter_version must be "
            "partizan.bounded_chess_adapter.native.v0.2",
            partizan.validate_chess_adapter_record(mixed, replay=False),
        )

    def test_terminal_checkmate_projects_to_zero(self) -> None:
        record = partizan.adapt_chess_position(
            TERMINAL_FEN,
            max_plies=2,
            node_budget=100,
        )

        self.assertEqual(record["status"], "accepted")
        self.assertEqual(
            record["projection"]["literal_game"], {"left": [], "right": []}
        )
        self.assertEqual(
            record["domain_gate"]["terminal_status"],
            "checkmate",
        )
        self.assertEqual(
            record["projection"]["statistics"]["checkmate_leaves"],
            1,
        )
        self.assertEqual(partizan.validate_chess_adapter_record(record), [])

    def test_mate_frontier_projection_is_deterministic(self) -> None:
        first = partizan.adapt_chess_position(
            MATE_FRONTIER_FEN,
            max_plies=1,
            node_budget=100,
        )
        second = partizan.adapt_chess_position(
            MATE_FRONTIER_FEN,
            max_plies=1,
            node_budget=100,
        )

        self.assertEqual(first, second)
        self.assertEqual(
            first["projection"]["literal_game"],
            {"left": [{"left": [], "right": []}], "right": []},
        )
        self.assertEqual(
            first["projection"]["statistics"],
            {
                "visited_position_nodes": 27,
                "legal_edges": 26,
                "duplicate_literal_options_removed": 25,
                "horizon_leaves": 12,
                "checkmate_leaves": 4,
                "stalemate_leaves": 10,
                "max_depth_reached": 1,
                "literal_game_nodes": 2,
            },
        )

    def test_distinct_positions_expose_a_same_horizon_literal_crossing(self) -> None:
        left_record = partizan.adapt_chess_position(
            CROSSING_LEFT_FEN,
            max_plies=4,
            node_budget=20_000,
        )
        right_record = partizan.adapt_chess_position(
            CROSSING_RIGHT_FEN,
            max_plies=4,
            node_budget=20_000,
        )
        target = partizan.fixed_value_target_from_chess_adapter(
            left_record,
            name="bounded-one",
        )
        candidates = [
            partizan.fixed_value_candidate_from_chess_adapter(left_record, ordinal=0),
            partizan.fixed_value_candidate_from_chess_adapter(right_record, ordinal=1),
        ]
        zero = {"left": [], "right": []}
        one = {"left": [zero], "right": []}
        repertoire = partizan.build_repertoire(
            target,
            candidates,
            seed=0,
            budget=2,
            max_results=2,
        )

        self.assertEqual(repertoire["summary"]["admitted_count"], 2)
        self.assertEqual(partizan.validate_repertoire(repertoire), [])
        self.assertEqual(
            [
                left_record["projection"]["statistics"]["literal_game_nodes"],
                right_record["projection"]["statistics"]["literal_game_nodes"],
            ],
            [19, 11],
        )
        self.assertEqual(
            [
                left_record["domain_gate"]["immediate_terminal_tactic"][
                    "checkmating_moves"
                ],
                right_record["domain_gate"]["immediate_terminal_tactic"][
                    "checkmating_moves"
                ],
            ],
            [["Qg1-g7"], ["Qg6-g7"]],
        )
        self.assertNotEqual(
            candidates[0]["literal_game"],
            candidates[1]["literal_game"],
        )
        for candidate in candidates:
            self.assertTrue(
                partizan.compare_short_games(candidate["literal_game"], one).equivalent
            )
        self.assertTrue(
            partizan.compare_short_games(
                candidates[0]["literal_game"],
                candidates[1]["literal_game"],
            ).equivalent
        )
        self.assertIn(
            "literal_game_crossing",
            {
                entry["admission_relation"]["transition_kind"]
                for entry in repertoire["entries"]
            },
        )

    def test_move_state_identity_excludes_irrelevant_fen_clocks(self) -> None:
        first = partizan.adapt_chess_position(
            MATE_FRONTIER_FEN,
            max_plies=1,
            node_budget=100,
        )
        second = partizan.adapt_chess_position(
            MATE_FRONTIER_FEN.replace("0 1", "17 42"),
            max_plies=1,
            node_budget=100,
        )
        first_candidate = partizan.fixed_value_candidate_from_chess_adapter(
            first,
            ordinal=0,
        )
        second_candidate = partizan.fixed_value_candidate_from_chess_adapter(
            second,
            ordinal=1,
        )

        self.assertEqual(
            first_candidate["representation"],
            second_candidate["representation"],
        )
        self.assertEqual(
            partizan.representation_sha256(first_candidate["representation"]),
            partizan.representation_sha256(second_candidate["representation"]),
        )
        repertoire = partizan.build_repertoire(
            partizan.fixed_value_target_from_chess_adapter(
                first,
                name="clock-free-move-state",
            ),
            [first_candidate, second_candidate],
            seed=0,
            budget=2,
            max_results=2,
        )
        self.assertEqual(
            repertoire["summary"]["outcome_counts"]["duplicate_embodiment"],
            1,
        )

    def test_domain_settings_and_budget_refusals_are_typed(self) -> None:
        domain = partizan.adapt_chess_position(OUTSIDE_DOMAIN_FEN)
        settings = partizan.adapt_chess_position(MATE_FRONTIER_FEN, max_plies=0)
        budget = partizan.adapt_chess_position(
            MATE_FRONTIER_FEN,
            max_plies=2,
            node_budget=1,
        )

        self.assertEqual(domain["refusal"]["code"], "domain_rejected")
        self.assertEqual(
            domain["domain_gate"]["reasons"][0]["code"],
            "no_strict_decomposition",
        )
        self.assertEqual(settings["refusal"]["code"], "invalid_adapter_settings")
        self.assertIsNone(settings["domain_gate"])
        self.assertEqual(budget["refusal"]["code"], "node_budget_exhausted")
        for record in (domain, settings, budget):
            self.assertEqual(partizan.validate_chess_adapter_record(record), [])

    def test_replay_rejects_corruption(self) -> None:
        record = partizan.adapt_chess_position(MATE_FRONTIER_FEN, max_plies=1)
        corrupted = deepcopy(record)
        corrupted["projection"]["statistics"]["checkmate_leaves"] = 5
        corrupted["adapter_id"] = partizan.chess_adapter_id_for(corrupted)

        errors = partizan.validate_chess_adapter_record(corrupted)
        self.assertIn(
            "adapter record does not match deterministic native replay",
            errors,
        )

    def test_cli_writes_replayable_records_and_fixed_value_inputs(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            record_path = root / "adapter.json"
            target_path = root / "target.json"
            candidate_path = root / "candidate.jsonl"
            refused_path = root / "refused.json"

            self.assertEqual(
                fixed_value_cli_main(
                    [
                        "chess-adapt",
                        "--fen",
                        MATE_FRONTIER_FEN,
                        "--max-plies",
                        "1",
                        "--node-budget",
                        "100",
                        "--output",
                        str(record_path),
                    ]
                ),
                0,
            )
            self.assertEqual(
                fixed_value_cli_main(["chess-verify", str(record_path)]),
                0,
            )
            self.assertEqual(
                fixed_value_cli_main(
                    [
                        "chess-target",
                        str(record_path),
                        "--name",
                        "mate-frontier-one",
                        "--output",
                        str(target_path),
                    ]
                ),
                0,
            )
            self.assertEqual(
                fixed_value_cli_main(
                    [
                        "chess-candidate",
                        str(record_path),
                        "--ordinal",
                        "0",
                        "--output",
                        str(candidate_path),
                    ]
                ),
                0,
            )
            self.assertEqual(
                fixed_value_cli_main(
                    [
                        "chess-adapt",
                        "--fen",
                        OUTSIDE_DOMAIN_FEN,
                        "--output",
                        str(refused_path),
                    ]
                ),
                2,
            )

            record = json.loads(record_path.read_text(encoding="utf-8"))
            self.assertEqual(partizan.validate_chess_adapter_record(record), [])
            self.assertEqual(
                json.loads(refused_path.read_text(encoding="utf-8"))["status"],
                "refused",
            )

    def test_cli_runs_same_horizon_chess_search_end_to_end(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            left_record = partizan.adapt_chess_position(
                CROSSING_LEFT_FEN,
                max_plies=4,
                node_budget=20_000,
            )
            right_record = partizan.adapt_chess_position(
                CROSSING_RIGHT_FEN,
                max_plies=4,
                node_budget=20_000,
            )
            target_path = root / "target.adapter.json"
            candidates_path = root / "candidate-adapters.jsonl"
            repertoire_path = root / "repertoire.json"
            target_path.write_bytes(partizan.canonical_json_bytes(left_record))
            candidates_path.write_bytes(
                partizan.canonical_jsonl_bytes([left_record, right_record])
            )

            self.assertEqual(
                fixed_value_cli_main(
                    [
                        "chess-search",
                        "--target-record",
                        str(target_path),
                        "--candidate-records",
                        str(candidates_path),
                        "--name",
                        "bounded-one",
                        "--seed",
                        "0",
                        "--budget",
                        "2",
                        "--max-results",
                        "2",
                        "--output",
                        str(repertoire_path),
                    ]
                ),
                0,
            )
            repertoire = json.loads(repertoire_path.read_text(encoding="utf-8"))
            self.assertEqual(repertoire["summary"]["admitted_count"], 2)
            self.assertEqual(partizan.validate_repertoire(repertoire), [])


if __name__ == "__main__":
    unittest.main()
