from __future__ import annotations

from collections import Counter
from copy import deepcopy
import importlib.util
import inspect
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
COMMIT = "6" * 40


def load_orchestrator():
    spec = importlib.util.spec_from_file_location(
        "partizan_orchestrator_wave69r", ROOT / "engine/orchestrator.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


orchestrator = load_orchestrator()
discovery = orchestrator.discovery_contract
TARGET_PATH = ROOT / "tests/fixtures/discovery/target.valid.json"


class DiscoveryCandidatePoolV2Tests(unittest.TestCase):
    def boards(self, size=256, seed=6902001):
        return orchestrator.generate_discovery_board_states_v2(
            pool_size=size,
            random_seed=seed,
            generator_code_commit=COMMIT,
        )

    def test_raw_generator_interface_is_target_free_and_deterministic(self) -> None:
        self.assertNotIn(
            "target",
            inspect.signature(
                orchestrator.generate_discovery_board_states_v2
            ).parameters,
        )
        first = discovery.canonical_jsonl_bytes(self.boards())
        second = discovery.canonical_jsonl_bytes(self.boards())
        other = discovery.canonical_jsonl_bytes(self.boards(seed=6902002))
        self.assertEqual(first, second)
        self.assertNotEqual(first, other)
        self.assertNotIn(b"target_id", first)
        self.assertNotIn(b"proposal_id", first)
        self.assertNotIn(b"identity_sha256", first)

    def test_catalog_identity_and_config_binding_are_stable(self) -> None:
        catalog_path = ROOT / orchestrator.DISCOVERY_POOL_GENERATOR_CATALOG_PATH_V2
        catalog = discovery.load_json(catalog_path)
        self.assertEqual(discovery.validate_construction_catalog(catalog), [])
        identity_input = deepcopy(catalog)
        identity_input["catalog_id"] = "catalog-sha256:" + "0" * 64
        expected = "catalog-sha256:" + discovery.sha256_hex(
            discovery.canonical_json_bytes(identity_input)
        )
        self.assertEqual(catalog["catalog_id"], expected)
        self.assertEqual(expected, orchestrator.DISCOVERY_POOL_GENERATOR_CATALOG_ID_V2)
        config = orchestrator._discovery_generator_config_v2(
            pool_size=1024, random_seed=6902001
        )
        self.assertEqual(
            config["construction_catalog"]["catalog_id"], expected
        )
        self.assertEqual(
            catalog["board_contract"]["barrier"],
            [[square, piece] for square, piece in orchestrator._DISCOVERY_BARRIER.items()],
        )
        self.assertEqual(
            set(catalog["strata"]), set(orchestrator._DISCOVERY_V2_STRATA)
        )
        self.assertEqual(
            catalog["strata"]["ray_cage"]["left_bases"],
            [[list(piece) for piece in base] for base in orchestrator._DISCOVERY_V2_LEFT_RAY_CAGES],
        )
        self.assertEqual(
            catalog["strata"]["ray_cage"]["right_bases"],
            [[list(piece) for piece in base] for base in orchestrator._DISCOVERY_V2_RIGHT_RAY_CAGES],
        )
        self.assertEqual(
            catalog["strata"]["mixed_color_hook"]["left_base"],
            [list(piece) for piece in orchestrator._DISCOVERY_V2_LEFT_MIXED_HOOKS[0]],
        )
        self.assertEqual(
            catalog["strata"]["mixed_color_hook"]["right_base"],
            [list(piece) for piece in orchestrator._DISCOVERY_V2_RIGHT_MIXED_HOOKS[0]],
        )

    def test_large_stream_is_balanced_unique_and_semantically_clock_safe(self) -> None:
        rows = self.boards(size=4096)
        self.assertEqual([row["ordinal"] for row in rows], list(range(4096)))
        self.assertEqual(len({row["board_id"] for row in rows}), 4096)
        self.assertEqual(
            len({row["position"]["symmetry_sha256"] for row in rows}), 4096
        )
        self.assertEqual(
            len({row["position"]["text"].split()[0] for row in rows}), 4096
        )
        self.assertEqual(
            Counter(row["construction"]["stratum"] for row in rows),
            Counter({stratum: 1024 for stratum in orchestrator._DISCOVERY_V2_STRATA}),
        )
        for row in rows:
            self.assertEqual(row["position"]["text"].split()[1:], ["w", "-", "-", "0", "1"])
            self.assertEqual(
                discovery.validate_candidate_board_stream_row(row), []
            )
            self.assertFalse(row["construction"]["runtime_oracle_used"])
            self.assertLessEqual(row["construction"]["left_active_piece_count"], 5)
            self.assertLessEqual(row["construction"]["right_active_piece_count"], 5)

    def test_target_binding_cannot_change_board_generation(self) -> None:
        target = discovery.load_json(TARGET_PATH)
        target["search_limits"]["max_pool_size"] = 4096
        other = deepcopy(target)
        other["target"]["identity_sha256"] = "1" * 64
        other["ranker_view"]["identity_sha256"] = "1" * 64
        other["target_id"] = discovery.target_id_for(other)
        boards = self.boards()
        first = orchestrator.bind_discovery_board_states_v2(
            target=target, board_rows=boards
        )
        rebound = orchestrator.bind_discovery_board_states_v2(
            target=other, board_rows=boards
        )
        for left, right, board in zip(first, rebound, boards):
            self.assertEqual(left["position"], right["position"])
            self.assertEqual(left["position"], board["position"])
            self.assertEqual(left["generator"], right["generator"])
            self.assertEqual(left["proposal_features"], right["proposal_features"])
            self.assertNotEqual(left["proposal_id"], right["proposal_id"])

    def test_construction_postcondition_names_the_four_stage_a_failure_modes(self) -> None:
        base = dict(orchestrator._DISCOVERY_BARRIER)
        base.update({"a1": "N", "h8": "n"})
        self.assertEqual(
            orchestrator._constructive_v2_invariant_errors(
                base, stratum="outer_leaper"
            ),
            [],
        )
        no_right = {key: value for key, value in base.items() if key != "h8"}
        self.assertIn(
            "RequiresStrictDecomposition",
            orchestrator._constructive_v2_invariant_errors(
                no_right, stratum="outer_leaper"
            ),
        )
        mobile_wall = dict(base)
        del mobile_wall["d2"]
        self.assertIn(
            "BarrierPawnNotFrozen",
            orchestrator._constructive_v2_invariant_errors(
                mobile_wall, stratum="outer_leaper"
            ),
        )
        capturable_wall = dict(base)
        capturable_wall["e2"] = "N"
        self.assertIn(
            "BarrierPieceCanBeCaptured",
            orchestrator._constructive_v2_invariant_errors(
                capturable_wall, stratum="outer_leaper"
            ),
        )
        crossing = dict(base)
        crossing["b1"] = "N"
        self.assertIn(
            "PieceCanEnterOtherComponent",
            orchestrator._constructive_v2_invariant_errors(
                crossing, stratum="outer_leaper"
            ),
        )

    def test_attempt_cap_is_exact_and_invariant_failure_is_fatal(self) -> None:
        def constant_component(_rng, *, stratum, side):
            del stratum
            return {"a1": "N"} if side == "left" else {"h8": "n"}

        with patch.object(
            orchestrator,
            "_construct_discovery_v2_component",
            side_effect=constant_component,
        ), patch.object(orchestrator, "_DISCOVERY_V2_STRATA", ("outer_leaper",)):
            with self.assertRaisesRegex(
                orchestrator.ShardRunnerError, r"1/2; attempts=40/40"
            ):
                self.boards(size=2)

        with patch.object(
            orchestrator,
            "_constructive_v2_invariant_errors",
            return_value=["BarrierPawnNotFrozen"],
        ):
            with self.assertRaisesRegex(
                orchestrator.ShardRunnerError,
                "construction theorem postcondition failed",
            ):
                self.boards(size=1)

    def test_public_board_cli_runs_two_separate_processes(self) -> None:
        original = orchestrator._run_discovery_board_stream_process_v2
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "boards.jsonl"
            report = Path(temp_dir) / "determinism.json"
            with (
                patch.object(
                    orchestrator, "_immutable_repo_commit", return_value=COMMIT
                ),
                patch.object(
                    orchestrator,
                    "_run_discovery_board_stream_process_v2",
                    wraps=original,
                ) as process,
            ):
                status = orchestrator.cli_main(
                    [
                        "discovery-generate-board-stream-v2",
                        "--output",
                        str(output),
                        "--determinism-report",
                        str(report),
                        "--pool-size",
                        "64",
                        "--random-seed",
                        "6902001",
                    ]
                )
            self.assertEqual(status, 0)
            self.assertEqual(process.call_count, 2)
            self.assertEqual(len(discovery.load_jsonl(output)), 64)
            determinism = discovery.load_json(report)
            self.assertEqual(determinism["executions"]["run_count"], 2)
            self.assertTrue(determinism["executions"]["byte_identical"])
            self.assertEqual(determinism["target_fields_consumed"], [])


if __name__ == "__main__":
    unittest.main()
