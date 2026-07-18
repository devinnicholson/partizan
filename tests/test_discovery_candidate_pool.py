from __future__ import annotations

from copy import deepcopy
import importlib.util
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


orchestrator = load_module("partizan_orchestrator_w69", ROOT / "engine/orchestrator.py")
discovery = orchestrator.discovery_contract
TARGET_PATH = ROOT / "tests/fixtures/discovery/target.valid.json"
PARTIZAN_COMMIT = "89c325d52a67bde4d6ac997f4527b7c56a119cf7"


class DiscoveryCandidatePoolV1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.target = discovery.load_json(TARGET_PATH)
        self.target["search_limits"]["max_pool_size"] = 4096
        self.target["search_limits"]["max_verifier_calls"] = 4096

    def generate(self, *, target=None, size=128, seed=69001):
        return orchestrator.generate_discovery_candidate_pool_v1(
            target=target or self.target,
            pool_size=size,
            random_seed=seed,
            generator_code_commit=PARTIZAN_COMMIT,
        )

    def receipt_for(self, proposals):
        artifact_sha = discovery.sha256_hex(
            discovery.canonical_jsonl_bytes(proposals)
        )
        return orchestrator.build_discovery_generation_receipt_v1(
            target=self.target,
            proposals=proposals,
            raw_artifact_sha256=[artifact_sha, artifact_sha],
        )

    def write_receipt(self, directory: Path, proposals):
        path = directory / "generation-receipt.json"
        path.write_bytes(
            discovery.canonical_json_bytes(self.receipt_for(proposals))
        )
        return path

    def repositories(self):
        fixture_manifest = discovery.load_json(
            ROOT / "tests/fixtures/discovery/candidate-pool.valid.manifest.json"
        )
        repositories = dict(fixture_manifest["source_repositories"])
        repositories["partizan"] = PARTIZAN_COMMIT
        return repositories

    def freeze_fixture(self, directory: Path, proposals):
        target_path = directory / "target.json"
        proposals_path = directory / "proposals.jsonl"
        manifest_path = directory / "manifest.json"
        receipt_path = self.write_receipt(directory, proposals)
        target_path.write_bytes(discovery.canonical_json_bytes(self.target))
        proposals_path.write_bytes(discovery.canonical_jsonl_bytes(proposals))
        manifest = orchestrator.freeze_discovery_pool(
            target_path=target_path,
            proposals_input_path=proposals_path,
            proposals_output_path=proposals_path,
            manifest_output_path=manifest_path,
            source_repositories=self.repositories(),
            candidate_artifact_path="artifacts/generated/wave69-test.jsonl",
            generation_receipt_path=receipt_path,
            repository_root=directory,
        )
        return target_path, proposals_path, manifest_path, receipt_path, manifest

    def rewrite_manifest_for(self, manifest, proposals):
        rewritten = deepcopy(manifest)
        artifact_sha = discovery.sha256_hex(
            discovery.canonical_jsonl_bytes(proposals)
        )
        rewritten["candidate_artifact"]["row_count"] = len(proposals)
        rewritten["candidate_artifact"]["sha256"] = artifact_sha
        rewritten["determinism"]["artifact_sha256"] = artifact_sha
        rewritten["determinism"]["raw_artifact_sha256"] = [
            artifact_sha,
            artifact_sha,
        ]
        rewritten["pool_id"] = discovery.candidate_pool_id_for(rewritten)
        return rewritten

    def test_generation_is_byte_deterministic_and_seeded(self) -> None:
        first = discovery.canonical_jsonl_bytes(self.generate())
        second = discovery.canonical_jsonl_bytes(self.generate())
        another_seed = discovery.canonical_jsonl_bytes(self.generate(seed=69002))
        self.assertEqual(first, second)
        self.assertEqual(
            discovery.sha256_hex(first),
            "8c8d87b59fc1fba4413c57f31ca359efa47b6fa018351498333ffcfbe06f9371",
        )
        self.assertNotEqual(first, another_seed)
        self.assertEqual(
            orchestrator._discovery_generator_config(
                pool_size=128, random_seed=69001
            )["maximum_attempts_per_required_row"],
            20,
        )

    def test_generation_never_invokes_verifier_and_features_validate(self) -> None:
        with patch.object(orchestrator, "_run_capture") as run_capture:
            proposals = self.generate(size=256)
        run_capture.assert_not_called()
        for proposal in proposals:
            self.assertEqual(
                discovery.validate_candidate_proposal(proposal, self.target), []
            )
            self.assertEqual(
                proposal["proposal_features"]["derivation_stage"],
                "pre_verification",
            )
            integers = proposal["proposal_features"]["integer"]
            booleans = proposal["proposal_features"]["boolean"]
            self.assertEqual(
                set(integers),
                {
                    "black_piece_count",
                    "non_pawn_piece_count",
                    "occupied_file_count",
                    "pawn_count",
                    "piece_count",
                    "white_piece_count",
                },
            )
            self.assertEqual(
                proposal["proposal_features"]["categorical"], {}
            )
            self.assertEqual(set(booleans), {"has_locked_d_file_backbone"})
            self.assertTrue(booleans["has_locked_d_file_backbone"])

    def test_target_content_cannot_steer_candidate_generation(self) -> None:
        other = deepcopy(self.target)
        other["target"]["identity_sha256"] = "1" * 64
        other["ranker_view"]["identity_sha256"] = "1" * 64
        other["target_id"] = discovery.target_id_for(other)
        first = self.generate(target=self.target)
        second = self.generate(target=other)
        for original, rebound in zip(first, second):
            self.assertEqual(original["position"], rebound["position"])
            self.assertEqual(original["candidate_key"], rebound["candidate_key"])
            self.assertEqual(
                original["proposal_features"], rebound["proposal_features"]
            )
            self.assertEqual(original["generator"], rebound["generator"])
            self.assertNotEqual(original["proposal_id"], rebound["proposal_id"])
            self.assertEqual(rebound["target_id"], other["target_id"])
            self.assertEqual(
                discovery.validate_candidate_proposal(rebound, other), []
            )

    def test_thousands_scale_pool_has_ordered_unique_states_and_symmetries(self) -> None:
        proposals = self.generate(size=2048)
        self.assertEqual(
            [proposal["ordinal"] for proposal in proposals], list(range(2048))
        )
        self.assertEqual(
            len({proposal["candidate_key"] for proposal in proposals}), 2048
        )
        self.assertEqual(
            len(
                {
                    proposal["position"]["symmetry_sha256"]
                    for proposal in proposals
                }
            ),
            2048,
        )
        for proposal in proposals:
            self.assertEqual(proposal["position"]["text"].split()[4:], ["0", "1"])
            self.assertEqual(
                proposal["candidate_key"],
                discovery.candidate_state_key_for(
                    proposal["domain"], proposal["position"]
                ),
            )

    def test_candidate_state_identity_ignores_clocks(self) -> None:
        proposal = self.generate(size=1)[0]
        changed = deepcopy(proposal["position"])
        fields = changed["text"].split()
        fields[4:] = ["99", "417"]
        changed["text"] = " ".join(fields)
        self.assertEqual(
            discovery.candidate_state_key_for(proposal["domain"], changed),
            proposal["candidate_key"],
        )

    def test_freeze_rejects_clock_only_duplicate_states(self) -> None:
        first = self.generate(size=1)[0]
        second = deepcopy(first)
        fields = second["position"]["text"].split()
        fields[4:] = ["7", "99"]
        second["position"]["text"] = " ".join(fields)
        second["position"]["sha256"] = discovery.sha256_hex(
            second["position"]["text"].encode("utf-8")
        )
        second["position"]["symmetry_sha256"] = (
            discovery.fen_file_reflection_orbit_sha256(
                second["position"]["text"]
            )
        )
        second["ordinal"] = 1
        second["proposal_id"] = discovery.proposal_id_for(second)
        self.assertEqual(first["candidate_key"], second["candidate_key"])
        self.assertEqual(
            discovery.validate_candidate_proposal(second, self.target), []
        )

        fixture_manifest = discovery.load_json(
            ROOT / "tests/fixtures/discovery/candidate-pool.valid.manifest.json"
        )
        repositories = dict(fixture_manifest["source_repositories"])
        repositories["partizan"] = PARTIZAN_COMMIT
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            target_path = temp / "target.json"
            proposals_path = temp / "proposals.jsonl"
            target_path.write_bytes(discovery.canonical_json_bytes(self.target))
            proposals_path.write_bytes(
                discovery.canonical_jsonl_bytes([first, second])
            )
            with self.assertRaisesRegex(
                orchestrator.ShardRunnerError,
                "(duplicate candidate_key|symmetry duplicate)",
            ):
                orchestrator.freeze_discovery_pool(
                    target_path=target_path,
                    proposals_input_path=proposals_path,
                    proposals_output_path=temp / "frozen.jsonl",
                    manifest_output_path=temp / "manifest.json",
                    source_repositories=repositories,
                    candidate_artifact_path=(
                        "artifacts/generated/clock-duplicate.jsonl"
                    ),
                    generation_receipt_path=self.write_receipt(
                        temp, [first, second]
                    ),
                    repository_root=temp,
                )

    def test_freeze_rejects_file_reflection_duplicate_states(self) -> None:
        first = self.generate(size=1)[0]
        second = deepcopy(first)
        reflected_state = discovery.reflect_fen_state_files(
            first["position"]["text"]
        )
        second["position"]["text"] = f"{reflected_state} 0 1"
        second["position"]["sha256"] = discovery.sha256_hex(
            second["position"]["text"].encode("utf-8")
        )
        second["position"]["symmetry_sha256"] = (
            discovery.fen_file_reflection_orbit_sha256(
                second["position"]["text"]
            )
        )
        second["candidate_key"] = discovery.candidate_state_key_for(
            second["domain"], second["position"]
        )
        second["proposal_features"] = discovery.partizan_pool_features_for_fen(
            second["position"]["text"]
        )
        second["ordinal"] = 1
        second["proposal_id"] = discovery.proposal_id_for(second)
        self.assertNotEqual(first["candidate_key"], second["candidate_key"])
        self.assertEqual(
            first["position"]["symmetry_sha256"],
            second["position"]["symmetry_sha256"],
        )
        self.assertEqual(
            discovery.validate_candidate_proposal(second, self.target), []
        )

        fixture_manifest = discovery.load_json(
            ROOT / "tests/fixtures/discovery/candidate-pool.valid.manifest.json"
        )
        repositories = dict(fixture_manifest["source_repositories"])
        repositories["partizan"] = PARTIZAN_COMMIT
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            target_path = temp / "target.json"
            proposals_path = temp / "proposals.jsonl"
            target_path.write_bytes(discovery.canonical_json_bytes(self.target))
            proposals_path.write_bytes(
                discovery.canonical_jsonl_bytes([first, second])
            )
            with self.assertRaisesRegex(
                orchestrator.ShardRunnerError, "file-reflection symmetry duplicate"
            ):
                orchestrator.freeze_discovery_pool(
                    target_path=target_path,
                    proposals_input_path=proposals_path,
                    proposals_output_path=temp / "frozen.jsonl",
                    manifest_output_path=temp / "manifest.json",
                    source_repositories=repositories,
                    candidate_artifact_path=(
                        "artifacts/generated/reflection-duplicate.jsonl"
                    ),
                    generation_receipt_path=self.write_receipt(
                        temp, [first, second]
                    ),
                    repository_root=temp,
                )

    def test_invalid_generator_shape_returns_contract_errors(self) -> None:
        proposal = deepcopy(self.generate(size=1)[0])
        proposal["generator"] = []
        errors = discovery.validate_candidate_proposal(proposal, self.target)
        self.assertTrue(any("proposal.generator" in error for error in errors))

    def test_generation_receipt_rejects_unequal_execution_hashes(self) -> None:
        proposals = self.generate(size=4)
        artifact_sha = discovery.sha256_hex(
            discovery.canonical_jsonl_bytes(proposals)
        )
        with self.assertRaisesRegex(
            orchestrator.ShardRunnerError,
            "both runs must equal the candidate artifact",
        ):
            orchestrator.build_discovery_generation_receipt_v1(
                target=self.target,
                proposals=proposals,
                raw_artifact_sha256=[artifact_sha, "0" * 64],
            )

    def test_generation_receipt_schema_is_strict(self) -> None:
        schema = discovery.load_json(
            ROOT
            / "docs/schemas/partizan-candidate-generation-receipt-v0.1.schema.json"
        )
        self.assertIs(schema["additionalProperties"], False)
        pool_schema = discovery.load_json(
            ROOT
            / "docs/schemas/partizan-candidate-pool-manifest-v0.2.schema.json"
        )
        self.assertIs(pool_schema["additionalProperties"], False)

    def test_loader_requires_persisted_receipt_sidecar(self) -> None:
        proposals = self.generate(size=4)
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            target_path, proposals_path, manifest_path, receipt_path, manifest = (
                self.freeze_fixture(temp, proposals)
            )
            loaded = orchestrator._load_frozen_discovery_pool(
                target_path,
                proposals_path,
                manifest_path,
                repository_root=temp,
            )
            self.assertEqual(loaded[2]["pool_id"], manifest["pool_id"])
            receipt_path.unlink()
            errors = discovery.validate_candidate_pool_manifest(
                manifest,
                self.target,
                proposals,
                proposals_path,
                repository_root=temp,
            )
            self.assertTrue(any("cannot resolve" in error for error in errors))
            with self.assertRaisesRegex(
                orchestrator.ShardRunnerError, "cannot resolve"
            ):
                orchestrator._load_frozen_discovery_pool(
                    target_path,
                    proposals_path,
                    manifest_path,
                    repository_root=temp,
                )
            with patch.object(orchestrator, "_run_capture") as run_capture:
                with self.assertRaisesRegex(
                    orchestrator.ShardRunnerError, "cannot resolve"
                ):
                    orchestrator.verify_discovery_pool(
                        target_path=target_path,
                        proposals_path=proposals_path,
                        manifest_path=manifest_path,
                        results_output_path=temp / "results.jsonl",
                        repository_root=temp,
                    )
            run_capture.assert_not_called()

    def test_loader_rejects_noncanonical_or_altered_receipt_bytes(self) -> None:
        proposals = self.generate(size=4)
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            target_path, proposals_path, manifest_path, receipt_path, _ = (
                self.freeze_fixture(temp, proposals)
            )
            receipt_path.write_bytes(receipt_path.read_bytes() + b"\n")
            with self.assertRaisesRegex(
                orchestrator.ShardRunnerError,
                "receipt bytes are not canonical",
            ):
                orchestrator._load_frozen_discovery_pool(
                    target_path,
                    proposals_path,
                    manifest_path,
                    repository_root=temp,
                )

    def test_loader_rejects_forged_reference_to_wrong_valid_receipt(self) -> None:
        proposals = self.generate(size=4)
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            target_path, proposals_path, manifest_path, receipt_path, manifest = (
                self.freeze_fixture(temp, proposals)
            )
            wrong_proposals = self.generate(size=4, seed=69002)
            wrong_receipt = self.receipt_for(wrong_proposals)
            wrong_bytes = discovery.canonical_json_bytes(wrong_receipt)
            receipt_path.write_bytes(wrong_bytes)
            forged = deepcopy(manifest)
            receipt_ref = forged["determinism"]["generation_receipt_ref"]
            receipt_ref["receipt_id"] = wrong_receipt["receipt_id"]
            receipt_ref["sha256"] = discovery.sha256_hex(wrong_bytes)
            forged["pool_id"] = discovery.candidate_pool_id_for(forged)
            manifest_path.write_bytes(discovery.canonical_json_bytes(forged))
            errors = discovery.validate_candidate_pool_manifest(
                forged,
                self.target,
                proposals,
                proposals_path,
                repository_root=temp,
            )
            self.assertTrue(
                any("does not match proposals" in error for error in errors)
            )
            with self.assertRaisesRegex(
                orchestrator.ShardRunnerError, "does not match proposals"
            ):
                orchestrator._load_frozen_discovery_pool(
                    target_path,
                    proposals_path,
                    manifest_path,
                    repository_root=temp,
                )

    def test_partizan_features_reject_unregistered_extras(self) -> None:
        proposal = deepcopy(self.generate(size=1)[0])
        proposal["proposal_features"]["integer"]["unregistered"] = 1
        proposal["proposal_id"] = discovery.proposal_id_for(proposal)
        errors = discovery.validate_candidate_proposal(proposal, self.target)
        self.assertTrue(
            any("seven preregistered" in error for error in errors)
        )

    def test_public_validators_and_loader_reject_self_hashed_orbit_tampering(self) -> None:
        proposals = self.generate(size=2)
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            target_path = temp / "target.json"
            proposals_path = temp / "proposals.jsonl"
            manifest_path = temp / "manifest.json"
            target_path.write_bytes(discovery.canonical_json_bytes(self.target))
            proposals_path.write_bytes(discovery.canonical_jsonl_bytes(proposals))
            manifest = orchestrator.freeze_discovery_pool(
                target_path=target_path,
                proposals_input_path=proposals_path,
                proposals_output_path=proposals_path,
                manifest_output_path=manifest_path,
                source_repositories=self.repositories(),
                candidate_artifact_path="artifacts/generated/orbit-tamper.jsonl",
                generation_receipt_path=self.write_receipt(temp, proposals),
                repository_root=temp,
            )

            tampered = deepcopy(proposals)
            tampered[0]["position"]["symmetry_sha256"] = "0" * 64
            tampered[0]["proposal_id"] = discovery.proposal_id_for(tampered[0])
            forged_manifest = self.rewrite_manifest_for(manifest, tampered)
            proposals_path.write_bytes(discovery.canonical_jsonl_bytes(tampered))
            manifest_path.write_bytes(
                discovery.canonical_json_bytes(forged_manifest)
            )

            proposal_errors = discovery.validate_candidate_proposal(
                tampered[0], self.target
            )
            self.assertTrue(
                any("clock-free file-reflection orbit" in error for error in proposal_errors)
            )
            pool_errors = discovery.validate_candidate_pool_manifest(
                forged_manifest,
                self.target,
                tampered,
                proposals_path,
                repository_root=temp,
            )
            self.assertTrue(
                any("clock-free file-reflection orbit" in error for error in pool_errors)
            )
            with self.assertRaisesRegex(
                orchestrator.ShardRunnerError,
                "clock-free file-reflection orbit",
            ):
                orchestrator._load_frozen_discovery_pool(
                    target_path,
                    proposals_path,
                    manifest_path,
                    repository_root=temp,
                )

    def test_public_pool_validator_and_loader_reject_orbit_duplicates(self) -> None:
        proposals = self.generate(size=2)
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            target_path = temp / "target.json"
            proposals_path = temp / "proposals.jsonl"
            manifest_path = temp / "manifest.json"
            target_path.write_bytes(discovery.canonical_json_bytes(self.target))
            proposals_path.write_bytes(discovery.canonical_jsonl_bytes(proposals))
            manifest = orchestrator.freeze_discovery_pool(
                target_path=target_path,
                proposals_input_path=proposals_path,
                proposals_output_path=proposals_path,
                manifest_output_path=manifest_path,
                source_repositories=self.repositories(),
                candidate_artifact_path="artifacts/generated/orbit-duplicate.jsonl",
                generation_receipt_path=self.write_receipt(temp, proposals),
                repository_root=temp,
            )

            duplicated = [deepcopy(proposals[0]), deepcopy(proposals[0])]
            reflected_state = discovery.reflect_fen_state_files(
                duplicated[0]["position"]["text"]
            )
            duplicated[1]["position"]["text"] = f"{reflected_state} 8 144"
            duplicated[1]["position"]["sha256"] = discovery.sha256_hex(
                duplicated[1]["position"]["text"].encode("utf-8")
            )
            duplicated[1]["position"]["symmetry_sha256"] = (
                discovery.fen_file_reflection_orbit_sha256(
                    duplicated[1]["position"]["text"]
                )
            )
            duplicated[1]["candidate_key"] = discovery.candidate_state_key_for(
                duplicated[1]["domain"], duplicated[1]["position"]
            )
            duplicated[1]["proposal_features"] = (
                discovery.partizan_pool_features_for_fen(
                    duplicated[1]["position"]["text"]
                )
            )
            duplicated[1]["ordinal"] = 1
            duplicated[1]["proposal_id"] = discovery.proposal_id_for(duplicated[1])
            forged_manifest = self.rewrite_manifest_for(manifest, duplicated)
            proposals_path.write_bytes(discovery.canonical_jsonl_bytes(duplicated))
            manifest_path.write_bytes(
                discovery.canonical_json_bytes(forged_manifest)
            )

            self.assertEqual(
                discovery.validate_candidate_proposal(
                    duplicated[1], self.target
                ),
                [],
            )
            pool_errors = discovery.validate_candidate_pool_manifest(
                forged_manifest,
                self.target,
                duplicated,
                proposals_path,
                repository_root=temp,
            )
            self.assertTrue(any("duplicate clock-free" in error for error in pool_errors))
            with self.assertRaisesRegex(
                orchestrator.ShardRunnerError,
                "duplicate clock-free",
            ):
                orchestrator._load_frozen_discovery_pool(
                    target_path,
                    proposals_path,
                    manifest_path,
                    repository_root=temp,
                )

    def test_file_reflection_has_one_symmetry_identity(self) -> None:
        fen = self.generate(size=1)[0]["position"]["text"]
        reflected_state = discovery.reflect_fen_state_files(fen)
        reflected_with_different_clocks = f"{reflected_state} 91 713"
        self.assertEqual(
            discovery.fen_file_reflection_orbit_sha256(fen),
            discovery.fen_file_reflection_orbit_sha256(
                reflected_with_different_clocks
            ),
        )

    def test_target_limit_is_enforced_before_generation(self) -> None:
        limited = deepcopy(self.target)
        limited["search_limits"]["max_pool_size"] = 4
        with self.assertRaisesRegex(
            orchestrator.ShardRunnerError, "exceeds target max_pool_size"
        ):
            self.generate(target=limited, size=5)

    def test_generated_output_can_be_frozen_with_partizan_provenance(self) -> None:
        proposals = self.generate(size=32)
        fixture_manifest = discovery.load_json(
            ROOT / "tests/fixtures/discovery/candidate-pool.valid.manifest.json"
        )
        repositories = dict(fixture_manifest["source_repositories"])
        repositories["partizan"] = PARTIZAN_COMMIT
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            target_path = temp / "target.json"
            input_path = temp / "input.jsonl"
            output_path = temp / "output.jsonl"
            manifest_path = temp / "manifest.json"
            target_path.write_bytes(discovery.canonical_json_bytes(self.target))
            input_path.write_bytes(discovery.canonical_jsonl_bytes(proposals))
            manifest = orchestrator.freeze_discovery_pool(
                target_path=target_path,
                proposals_input_path=input_path,
                proposals_output_path=output_path,
                manifest_output_path=manifest_path,
                source_repositories=repositories,
                candidate_artifact_path="artifacts/generated/wave69-smoke.jsonl",
                generation_receipt_path=self.write_receipt(temp, proposals),
                repository_root=temp,
            )
            self.assertEqual(manifest["candidate_artifact"]["row_count"], 32)
            self.assertEqual(
                discovery.validate_candidate_pool_manifest(
                    manifest,
                    self.target,
                    proposals,
                    output_path,
                    repository_root=temp,
                ),
                [],
            )

    def test_cli_runs_generator_twice_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "proposals.jsonl"
            receipt_path = Path(temp_dir) / "receipt.json"
            args = [
                "discovery-generate-pool-v1",
                "--target",
                str(TARGET_PATH),
                "--output",
                str(output),
                "--receipt",
                str(receipt_path),
                "--pool-size",
                "4",
                "--random-seed",
                "69001",
            ]
            original = orchestrator._run_discovery_generator_process
            with (
                patch.object(
                    orchestrator,
                    "_immutable_repo_commit",
                    return_value=PARTIZAN_COMMIT,
                ),
                patch.object(
                    orchestrator,
                    "_run_discovery_generator_process",
                    wraps=original,
                ) as generate_process,
                patch.object(orchestrator, "_run_capture") as run_capture,
            ):
                self.assertEqual(orchestrator.cli_main(args), 0)
            self.assertEqual(generate_process.call_count, 2)
            run_capture.assert_not_called()
            proposals = discovery.load_jsonl(output)
            receipt = discovery.load_json(receipt_path)
            self.assertEqual(len(proposals), 4)
            self.assertEqual(
                discovery.validate_generation_receipt(
                    receipt,
                    discovery.load_json(TARGET_PATH),
                    proposals,
                ),
                [],
            )
            self.assertEqual(
                receipt["executions"]["mode"],
                "separate_python_processes_v1",
            )


if __name__ == "__main__":
    unittest.main()
