from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


orchestrator = load_module("partizan_orchestrator", ROOT / "engine/orchestrator.py")
discovery = orchestrator.discovery_contract
FIXTURES = ROOT / "tests/fixtures/discovery"
TARGET_PATH = FIXTURES / "target.valid.json"
PROPOSALS_PATH = FIXTURES / "proposals.valid.jsonl"
RESULTS_PATH = FIXTURES / "verifier-results.valid.jsonl"
MANIFEST_PATH = FIXTURES / "candidate-pool.valid.manifest.json"


class DiscoveryOrchestratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.target = discovery.load_json(TARGET_PATH)
        self.proposals = discovery.load_jsonl(PROPOSALS_PATH)
        self.results = discovery.load_jsonl(RESULTS_PATH)
        self.manifest = discovery.load_json(MANIFEST_PATH)
        self.repositories = dict(self.manifest["source_repositories"])

    def astralbase_payload(self) -> bytes:
        target_digest = self.target["target"]["identity_sha256"]
        other_digest = self.results[1]["target_comparison"][
            "observed_identity_sha256"
        ]

        def actual(digest: str, marker: str, nodes: int) -> dict[str, object]:
            return {
                "identity_kind": "thermograph_structural_tree_v1",
                "semantics": "structural_tree_identity_only",
                "value_class": "game_tree",
                "digest_v1_sha256": digest,
                "legacy_digest": marker,
                "recursive_nodes": nodes,
                "decomposition_digest": marker * 64,
                "composition_digest": marker.upper().lower() * 64,
                "component_legacy_digests": {"a1": marker},
            }

        rows = [
            {
                "request_id": self.proposals[0]["proposal_id"],
                "status": "verified_match",
                "actual": actual(target_digest, "a", 37),
            },
            {
                "request_id": self.proposals[1]["proposal_id"],
                "status": "verified_nonmatch",
                "actual": actual(other_digest, "b", 41),
            },
            {
                "request_id": self.proposals[2]["proposal_id"],
                "status": "rejected",
                "reason_code": "no_strict_decomposition",
                "reason": "fixture rejection",
            },
            {
                "request_id": self.proposals[3]["proposal_id"],
                "status": "internal_error",
                "reason_code": "fixture_verifier_error",
                "reason": "fixture error",
            },
        ]
        return discovery.canonical_jsonl_bytes(rows)

    def test_freeze_canonicalizes_existing_pool_without_invoking_verifier(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            proposals_input = temp / "input.jsonl"
            proposals_input.write_text(
                "".join(json.dumps(row) + "\n" for row in self.proposals),
                encoding="utf-8",
            )
            proposals_output = temp / "frozen.jsonl"
            manifest_output = temp / "manifest.json"
            with patch.object(orchestrator, "_run_capture") as run_capture:
                manifest = orchestrator.freeze_discovery_pool(
                    target_path=TARGET_PATH,
                    proposals_input_path=proposals_input,
                    proposals_output_path=proposals_output,
                    manifest_output_path=manifest_output,
                    source_repositories=self.repositories,
                    candidate_artifact_path="artifacts/generated/test-frozen.jsonl",
                )
            run_capture.assert_not_called()
            self.assertEqual(
                proposals_output.read_bytes(),
                discovery.canonical_jsonl_bytes(self.proposals),
            )
            self.assertEqual(
                manifest["candidate_artifact"]["sha256"],
                discovery.sha256_hex(proposals_output.read_bytes()),
            )
            self.assertEqual(
                manifest["determinism"]["operation"], "canonicalization"
            )
            self.assertEqual(
                discovery.validate_candidate_pool_manifest(
                    manifest, self.target, self.proposals, proposals_output
                ),
                [],
            )

    def test_verify_refuses_invalid_manifest_before_subprocess(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            corrupt = deepcopy(self.manifest)
            corrupt["candidate_artifact"]["sha256"] = "0" * 64
            corrupt["pool_id"] = discovery.candidate_pool_id_for(corrupt)
            manifest_path = temp / "corrupt.json"
            manifest_path.write_bytes(discovery.canonical_json_bytes(corrupt))
            with patch.object(orchestrator, "_run_capture") as run_capture:
                with self.assertRaisesRegex(
                    orchestrator.ShardRunnerError, "candidate pool manifest"
                ):
                    orchestrator.verify_discovery_pool(
                        target_path=TARGET_PATH,
                        proposals_path=PROPOSALS_PATH,
                        manifest_path=manifest_path,
                        results_output_path=temp / "results.jsonl",
                        current_repositories=self.repositories,
                    )
            run_capture.assert_not_called()

    def test_verify_maps_node_budget_and_four_statuses(self) -> None:
        captured_requests: list[dict[str, object]] = []
        captured_invocations: list[tuple[tuple[str, ...], Path, str, dict[str, str]]] = []
        native_responses = [
            json.loads(line)
            for line in self.astralbase_payload().decode("utf-8").splitlines()
        ]

        def fake_run(command, cwd, label, env):
            request_path = Path(command[-1])
            captured_requests.extend(discovery.load_jsonl(request_path))
            captured_invocations.append((command, cwd, label, env))
            return self.astralbase_payload()

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            output = temp / "results.jsonl"
            astralbase_dir = temp / "astralbase"
            bitmesh_dir = temp / "bitmesh"
            thermograph_dir = temp / "thermograph"
            with patch.object(orchestrator, "_run_capture", side_effect=fake_run):
                results = orchestrator.verify_discovery_pool(
                    target_path=TARGET_PATH,
                    proposals_path=PROPOSALS_PATH,
                    manifest_path=MANIFEST_PATH,
                    results_output_path=output,
                    astralbase_dir=astralbase_dir,
                    bitmesh_dir=bitmesh_dir,
                    thermograph_dir=thermograph_dir,
                    current_repositories=self.repositories,
                )
            self.assertEqual(len(captured_invocations), 1)
            command, cwd, label, env = captured_invocations[0]
            self.assertEqual(cwd, astralbase_dir.resolve())
            self.assertEqual(label, "astralbase discovery verification")
            self.assertEqual(
                command[:-1],
                (
                    "cargo",
                    "--config",
                    f'patch."crates-io".bitmesh.path="{bitmesh_dir.resolve()}"',
                    "--config",
                    f'patch."crates-io".thermograph.path="{thermograph_dir.resolve()}"',
                    "run",
                    "--locked",
                    "--offline",
                    "--quiet",
                    "--",
                    "--verify-target-candidates",
                ),
            )
            request_path = Path(command[-1])
            self.assertEqual(
                Path(env["CARGO_TARGET_DIR"]), request_path.parent / "cargo-target"
            )
            self.assertTrue(Path(env["CARGO_TARGET_DIR"]).is_absolute())
            self.assertEqual(
                [row["node_budget"] for row in captured_requests],
                [
                    self.target["search_limits"][
                        "max_recursive_nodes_per_candidate"
                    ]
                ]
                * len(self.proposals),
            )
            self.assertEqual(
                [result["outcome"] for result in results],
                ["certified_target", "certified_other", "rejected", "error"],
            )
            for result, request, response in zip(
                results, captured_requests, native_responses
            ):
                self.assertEqual(result["verifier_io"]["request"], request)
                self.assertEqual(result["verifier_io"]["response"], response)
                self.assertEqual(
                    result["verifier_io"]["request_sha256"],
                    discovery.sha256_hex(discovery.canonical_json_bytes(request)),
                )
                self.assertEqual(
                    result["verifier_io"]["response_sha256"],
                    discovery.sha256_hex(discovery.canonical_json_bytes(response)),
                )
            self.assertEqual(
                results[0]["verifier_io"]["response"]["actual"]["legacy_digest"],
                "a",
            )
            self.assertEqual(
                results[0]["verifier_io"]["response"]["actual"][
                    "component_legacy_digests"
                ],
                {"a1": "a"},
            )
            self.assertEqual(
                results[2]["verifier_io"]["response"]["reason"],
                "fixture rejection",
            )
            self.assertEqual(
                output.read_bytes(), discovery.canonical_jsonl_bytes(results)
            )
            for result, proposal in zip(results, self.proposals):
                self.assertEqual(
                    discovery.validate_verifier_result(
                        result, self.target, proposal
                    ),
                    [],
                )

    def test_verified_nonmatch_compares_value_class_and_digest_as_a_pair(self) -> None:
        target_digest = self.target["target"]["identity_sha256"]
        cases = (
            ("number", target_digest),
            ("number", "1" * 64),
        )
        native_match = json.loads(
            self.astralbase_payload().decode("utf-8").splitlines()[0]
        )
        for value_class, digest in cases:
            with self.subTest(value_class=value_class, digest=digest):
                response = deepcopy(native_match)
                response["status"] = "verified_nonmatch"
                response["actual"]["value_class"] = value_class
                response["actual"]["digest_v1_sha256"] = digest
                result = orchestrator._translate_astralbase_result(
                    target=self.target,
                    proposal=self.proposals[0],
                    response=response,
                    source_repositories=self.repositories,
                )
                self.assertEqual(result["outcome"], "certified_other")
                self.assertIs(result["target_comparison"]["matches"], False)
                self.assertEqual(
                    result["target_comparison"]["observed_identity_sha256"], digest
                )
                self.assertEqual(
                    result["verifier_io"]["response"]["actual"]["value_class"],
                    value_class,
                )
                self.assertEqual(
                    discovery.validate_verifier_result(
                        result, self.target, self.proposals[0]
                    ),
                    [],
                )

    def test_replay_enforces_budget_and_recomputes_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            with self.assertRaisesRegex(
                orchestrator.ShardRunnerError, "target search limit"
            ):
                orchestrator.replay_discovery_run(
                    target_path=TARGET_PATH,
                    proposals_path=PROPOSALS_PATH,
                    manifest_path=MANIFEST_PATH,
                    results_path=RESULTS_PATH,
                    run_output_path=temp / "too-large.json",
                    verifier_budget=5,
                )
            run = orchestrator.replay_discovery_run(
                target_path=TARGET_PATH,
                proposals_path=PROPOSALS_PATH,
                manifest_path=MANIFEST_PATH,
                results_path=RESULTS_PATH,
                run_output_path=temp / "run.json",
                verifier_budget=3,
            )
            self.assertEqual(
                run["summary"]["outcome_counts"],
                {"certified_other": 1, "certified_target": 1, "rejected": 1},
            )
            self.assertEqual(
                discovery.validate_discovery_run(
                    run,
                    self.target,
                    self.manifest,
                    self.proposals,
                    self.results,
                ),
                [],
            )

    def test_replay_is_byte_deterministic_and_ignores_result_file_order(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            reversed_results = temp / "reversed.jsonl"
            reversed_results.write_bytes(
                discovery.canonical_jsonl_bytes(reversed(self.results))
            )
            first_path = temp / "first.json"
            second_path = temp / "second.json"
            first = orchestrator.replay_discovery_run(
                target_path=TARGET_PATH,
                proposals_path=PROPOSALS_PATH,
                manifest_path=MANIFEST_PATH,
                results_path=reversed_results,
                run_output_path=first_path,
                verifier_budget=4,
            )
            second = orchestrator.replay_discovery_run(
                target_path=TARGET_PATH,
                proposals_path=PROPOSALS_PATH,
                manifest_path=MANIFEST_PATH,
                results_path=RESULTS_PATH,
                run_output_path=second_path,
                verifier_budget=4,
            )
            self.assertEqual(first_path.read_bytes(), second_path.read_bytes())
            self.assertEqual(first, second)
            self.assertEqual(
                [call["proposal_id"] for call in first["calls"]],
                [proposal["proposal_id"] for proposal in self.proposals],
            )


if __name__ == "__main__":
    unittest.main()
