from __future__ import annotations

from copy import deepcopy
import importlib.util
from itertools import islice, combinations
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "python/partizan/gate_s.py"
SPEC = importlib.util.spec_from_file_location("partizan_gate_s_test", MODULE)
assert SPEC is not None and SPEC.loader is not None
gate_s = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate_s)


ACCEPTED_BOARD = "3p3n/3P4/3p4/3P4/3p4/3P4/3p4/N2P4"
SECOND_BOARD = "3p3n/3P4/3p4/3P4/3p4/3P4/3p4/1N1P4"


def board_row(board: str, ordinal: int = 0) -> dict:
    fen = f"{board} w - - 0 1"
    return {
        "schema_version": gate_s.BOARD_STREAM_SCHEMA,
        "board_id": gate_s._board_id_for_fen(fen),
        "ordinal": ordinal,
        "position": {
            "encoding": "fen",
            "text": fen,
            "sha256": gate_s.sha256_hex(fen.encode("utf-8")),
            "symmetry_sha256": gate_s._reflection_sha256(fen),
        },
        "generator": {
            "name": "partizan_candidate_pool_generator",
            "version": "0.2.0",
            "code_commit": "0" * 40,
            "family": "dfile_two_component_constructive_grammar_v2",
            "operator": "seeded_constructive_component_composition_v2",
            "config_sha256": "1" * 64,
            "random_seed": 7,
        },
        "construction": {
            "contract": "partizan.dfile_two_component_constructive_grammar.v0.2",
            "stratum": "outer_leaper",
            "left_active_piece_count": 1,
            "right_active_piece_count": 1,
            "left_template_id": "template-sha256:" + "2" * 64,
            "right_template_id": "template-sha256:" + "3" * 64,
            "runtime_oracle_used": False,
        },
        "proposal_features": gate_s._expected_features(fen),
    }


def pass_result(board_id: str) -> dict:
    return {
        "schema_version": gate_s.RESULT_SCHEMA,
        "board_id": board_id,
        "checker": {
            "name": gate_s.CHECKER_NAME,
            "version": gate_s.CHECKER_VERSION,
            "bitmesh_crate_version": gate_s.BITMESH_CRATE_VERSION,
            "bitmesh_source_commit": gate_s.BITMESH_COMMIT,
            "proof_api": gate_s.PROOF_API,
        },
        "outcome": "pass",
        "certification": {
            "proof_kind": gate_s.PROOF_API,
            "decomposition_sha256": "4" * 64,
            "component_count": 2,
            "barrier_squares": [f"d{rank}" for rank in range(1, 9)],
        },
        "failure_code": None,
        "predicates": {
            "frozen_barrier": "pass",
            "non_capturable_barrier": "pass",
            "strict_exactly_two_components": "pass",
            "no_cross_component_entry": "pass",
        },
        "internal_error": False,
    }


def synthetic_board_field(squares: tuple[int, ...]) -> str:
    board = ["."] * 64
    for square in squares:
        board[square] = "N"
    ranks = []
    for rank in range(8):
        encoded = []
        empty = 0
        for token in board[rank * 8 : (rank + 1) * 8]:
            if token == ".":
                empty += 1
            else:
                if empty:
                    encoded.append(str(empty))
                    empty = 0
                encoded.append(token)
        if empty:
            encoded.append(str(empty))
        ranks.append("".join(encoded))
    return "/".join(ranks)


def write_evidence_fixture(root: Path) -> tuple[dict, dict, list[str]]:
    implementation = "a" * 40
    requests = []
    for occupied in islice(combinations(range(64), 3), gate_s.GATE_S_ROW_COUNT):
        board = synthetic_board_field(occupied)
        fen = f"{board} w - - 0 1"
        requests.append(
            {
                "schema_version": gate_s.REQUEST_SCHEMA,
                "board_id": gate_s._board_id_for_fen(fen),
                "board_fen": board,
            }
        )
    request_path = "data/discovery/wave_69r/structural_supply/inputs/checker-requests.jsonl"
    request_payload = gate_s.canonical_jsonl_bytes(requests)
    (root / request_path).parent.mkdir(parents=True)
    (root / request_path).write_bytes(request_payload)
    request_ref = gate_s._artifact_reference(
        path=request_path,
        schema_version=gate_s.REQUEST_SCHEMA,
        payload=request_payload,
        row_count=len(requests),
    )
    repositories = {
        "partizan": implementation,
        "astralbase": gate_s.ASTRALBASE_COMMIT,
        "bitmesh": gate_s.BITMESH_COMMIT,
        "thermograph": gate_s.THERMOGRAPH_COMMIT,
    }
    suite = {
        "schema_version": gate_s.SUPPLY_SUITE_SCHEMA,
        "implementation_commit": implementation,
        "source_repositories": repositories,
        "checker_request_ref": request_ref,
        "totals": {"row_count": len(requests)},
    }
    suite_path = (
        root
        / "data/discovery/wave_69r/structural_supply/inputs/suite-manifest.json"
    )
    suite_payload = gate_s.canonical_json_bytes(suite)
    suite_path.write_bytes(suite_payload)

    for source in (
        gate_s.CHECKER_MANIFEST,
        gate_s.CHECKER_LOCK,
        gate_s.CHECKER_SOURCE,
        gate_s.CHECKER_WRAPPER,
    ):
        destination = root / source.relative_to(gate_s.ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())

    results = [pass_result(request["board_id"]) for request in requests]
    ledger_payload = gate_s.canonical_jsonl_bytes(results)
    evidence_root = root / "data/discovery/wave_69r/structural_supply/evidence"
    evidence_root.mkdir(parents=True)
    (evidence_root / "primary.jsonl").write_bytes(ledger_payload)
    (evidence_root / "replay.jsonl").write_bytes(ledger_payload)
    certificate_ids = [request["board_id"] for request in requests]
    certificate_inventory = {
        "schema_version": gate_s.SUPPLY_CERTIFICATE_SCHEMA,
        "shard_count": 4,
        "row_count": gate_s.GATE_S_ROW_COUNT,
        "references_sha256": "5" * 64,
        "canonical_jsonl_sha256": "6" * 64,
    }
    return suite, certificate_inventory, certificate_ids


def git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ("git", "-C", str(root), *arguments),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode:
        raise AssertionError(result.stderr)
    return result.stdout.strip()


def commit_all(root: Path, message: str) -> str:
    git(root, "add", "--all")
    git(root, "commit", "-m", message)
    return git(root, "rev-parse", "HEAD")


def initialize_provenance_repository(root: Path) -> str:
    git(root, "init", "--quiet")
    git(root, "config", "user.name", "Wave 69-R Test")
    git(root, "config", "user.email", "wave69r@example.invalid")
    for relative in gate_s.EVIDENCE_VALIDATOR_DEPENDENCIES:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"implementation dependency: {relative}\n", encoding="utf-8")
    return commit_all(root, "I")


def commit_supply_pre_result(root: Path) -> str:
    input_file = root / gate_s.SUPPLY_INPUT_ROOT / "suite-manifest.json"
    input_file.parent.mkdir(parents=True, exist_ok=True)
    input_file.write_text("{}\n", encoding="utf-8")
    freeze_document = root / gate_s.SUPPLY_FREEZE_DOCUMENT
    freeze_document.parent.mkdir(parents=True, exist_ok=True)
    freeze_document.write_text("# Frozen structural supply\n", encoding="utf-8")
    return commit_all(root, "P_s")


def write_evidence_commit_files(root: Path) -> dict[str, bytes]:
    payloads = {
        gate_s.EVIDENCE_PRIMARY_PATH: b'{"primary":true}\n',
        gate_s.EVIDENCE_REPLAY_PATH: b'{"primary":true}\n',
        gate_s.EVIDENCE_MANIFEST_PATH: b'{"evidence":true}\n',
    }
    for relative, payload in payloads.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    for relative in gate_s.EVIDENCE_AUDIT_DOCUMENTS:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"audit document: {relative}\n", encoding="utf-8")
    return payloads


class GateSContractTests(unittest.TestCase):
    def test_projection_is_only_bound_board_identity_and_board_field(self) -> None:
        request = gate_s.project_request(board_row(ACCEPTED_BOARD))
        self.assertEqual(set(request), gate_s._REQUEST_KEYS)
        self.assertEqual(request["board_fen"], ACCEPTED_BOARD)
        self.assertNotIn("target", json.dumps(request).lower())

    def test_request_board_id_must_bind_board_field(self) -> None:
        request = gate_s.project_request(board_row(ACCEPTED_BOARD))
        request["board_fen"] = SECOND_BOARD
        with self.assertRaisesRegex(gate_s.GateSContractError, "does not bind"):
            gate_s.validate_request(request)

    def test_metadata_only_variant_is_rejected(self) -> None:
        row = board_row(ACCEPTED_BOARD)
        row["position"]["text"] = f"{ACCEPTED_BOARD} b - - 0 1"
        row["position"]["sha256"] = gate_s.sha256_hex(
            row["position"]["text"].encode("utf-8")
        )
        with self.assertRaisesRegex(gate_s.GateSContractError, "metadata"):
            gate_s.project_request(row)

    def test_unknown_target_or_outcome_input_is_rejected(self) -> None:
        for key in ("target_id", "target", "target_value", "match", "label", "rank"):
            row = board_row(ACCEPTED_BOARD)
            row[key] = "forbidden"
            with self.subTest(key=key), self.assertRaises(gate_s.GateSContractError):
                gate_s.project_request(row)

    def test_unknown_nested_generator_field_is_rejected(self) -> None:
        row = board_row(ACCEPTED_BOARD)
        row["generator"]["verifier_result"] = "forbidden"
        with self.assertRaises(gate_s.GateSContractError):
            gate_s.project_request(row)

    def test_freeze_retains_input_order_and_every_row(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            shard0 = temp / "shard0.jsonl"
            shard1 = temp / "shard1.jsonl"
            output = temp / "suite.jsonl"
            shard0.write_bytes(gate_s.canonical_jsonl_bytes([board_row(ACCEPTED_BOARD)]))
            shard1.write_bytes(gate_s.canonical_jsonl_bytes([board_row(SECOND_BOARD)]))
            requests = gate_s.freeze_request_stream(
                [shard0, shard1], output, expected_row_count=2
            )
            self.assertEqual(
                [request["board_fen"] for request in requests],
                [ACCEPTED_BOARD, SECOND_BOARD],
            )
            self.assertEqual(output.read_bytes(), gate_s.canonical_jsonl_bytes(requests))

    def test_freeze_refuses_duplicate_board_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source = temp / "source.jsonl"
            source.write_bytes(
                gate_s.canonical_jsonl_bytes(
                    [board_row(ACCEPTED_BOARD, 0), board_row(ACCEPTED_BOARD, 1)]
                )
            )
            with self.assertRaisesRegex(gate_s.GateSContractError, "unique"):
                gate_s.freeze_request_stream(
                    [source], temp / "suite.jsonl", expected_row_count=2
                )

    def test_freeze_refuses_cross_shard_reflection_duplicate(self) -> None:
        reflected = gate_s._reflect_fen_files(
            f"{ACCEPTED_BOARD} w - - 0 1"
        ).split()[0]
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            shard0 = temp / "shard0.jsonl"
            shard1 = temp / "shard1.jsonl"
            shard0.write_bytes(
                gate_s.canonical_jsonl_bytes([board_row(ACCEPTED_BOARD)])
            )
            shard1.write_bytes(gate_s.canonical_jsonl_bytes([board_row(reflected)]))
            with self.assertRaisesRegex(
                gate_s.GateSContractError, "file-reflection orbit"
            ):
                gate_s.freeze_request_stream(
                    [shard0, shard1], temp / "suite.jsonl", expected_row_count=2
                )

    def test_result_schema_denies_unknown_leakage_fields(self) -> None:
        request = gate_s.project_request(board_row(ACCEPTED_BOARD))
        for key in (
            "target_id",
            "actual_value",
            "thermograph",
            "expanded_nodes",
            "match",
            "baseline_score",
            "learned_features",
        ):
            result = pass_result(request["board_id"])
            result[key] = "forbidden"
            with self.subTest(key=key), self.assertRaises(gate_s.GateSContractError):
                gate_s.validate_result(result, request["board_id"])

    def test_pass_requires_all_four_predicates_and_exactly_two_components(self) -> None:
        request = gate_s.project_request(board_row(ACCEPTED_BOARD))
        result = pass_result(request["board_id"])
        gate_s.validate_result(result, request["board_id"])
        result["predicates"]["frozen_barrier"] = "not_evaluated"
        with self.assertRaises(gate_s.GateSContractError):
            gate_s.validate_result(result, request["board_id"])

    def test_summary_recomputes_go_without_target_data(self) -> None:
        request = gate_s.project_request(board_row(ACCEPTED_BOARD))
        summary = gate_s.summarize_results(
            [request], [pass_result(request["board_id"])], expected_row_count=1
        )
        self.assertTrue(summary["go"])
        self.assertEqual(summary["row_count"], 1)
        self.assertEqual(summary["outcomes"], {"pass": 1})

    def test_request_and_result_schemas_are_strict(self) -> None:
        for name in (
            "partizan-structural-supply-request-v0.1.schema.json",
            "partizan-structural-supply-result-v0.1.schema.json",
            "partizan-structural-supply-evidence-v0.1.schema.json",
        ):
            schema = json.loads((ROOT / "docs/schemas" / name).read_text())
            self.assertIs(schema["additionalProperties"], False)

    def test_python_lane_has_no_evaluator_dependencies_or_options(self) -> None:
        source = MODULE.read_text(encoding="utf-8")
        for forbidden_import in (
            "import astralbase",
            "import thermograph",
            "from astralbase",
            "from thermograph",
        ):
            self.assertNotIn(forbidden_import, source.lower())
        parser_tokens = {
            "--target",
            "--target-id",
            "--ranker",
        }
        self.assertTrue(all(token not in source for token in parser_tokens))


class GateSGitProvenanceTests(unittest.TestCase):
    def test_supply_commit_diff_is_exact_and_additions_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            implementation = initialize_provenance_repository(root)
            supply = commit_supply_pre_result(root)
            gate_s._require_supply_pre_result_boundary(
                root,
                implementation,
                supply,
                root / gate_s.SUPPLY_INPUT_ROOT,
            )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            implementation = initialize_provenance_repository(root)
            unexpected = root / "python/partizan/unexpected-validator.py"
            unexpected.parent.mkdir(parents=True, exist_ok=True)
            unexpected.write_text("not preregistered\n", encoding="utf-8")
            supply = commit_supply_pre_result(root)
            with self.assertRaisesRegex(gate_s.GateSContractError, "extra="):
                gate_s._require_supply_pre_result_boundary(
                    root,
                    implementation,
                    supply,
                    root / gate_s.SUPPLY_INPUT_ROOT,
                )

    def test_every_evidence_validator_dependency_is_bound_to_i(self) -> None:
        self.assertEqual(
            set(gate_s.EVIDENCE_VALIDATOR_DEPENDENCIES),
            {
                "python/partizan/gate_s.py",
                "python/partizan/wave69r_supply.py",
                "python/partizan/discovery.py",
                "engine/orchestrator.py",
                "docs/discovery_wave_69r_construction_catalog.v0.2.json",
            },
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            implementation = initialize_provenance_repository(root)
            for relative in gate_s.EVIDENCE_VALIDATOR_DEPENDENCIES:
                path = root / relative
                original = path.read_bytes()
                path.write_bytes(original + b"tamper\n")
                with self.subTest(relative=relative), self.assertRaisesRegex(
                    gate_s.GateSContractError, "validator dependency"
                ):
                    gate_s._require_validator_dependencies_at_i(root, implementation)
                path.write_bytes(original)
            gate_s._require_validator_dependencies_at_i(root, implementation)

    def test_evidence_commit_diff_and_bytes_are_exact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            initialize_provenance_repository(root)
            supply = commit_supply_pre_result(root)
            payloads = write_evidence_commit_files(root)
            evidence = commit_all(root, "E_s")
            self.assertEqual(
                gate_s._require_evidence_commit_boundary(root, supply, payloads),
                evidence,
            )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            initialize_provenance_repository(root)
            supply = commit_supply_pre_result(root)
            payloads = write_evidence_commit_files(root)
            (root / "unexpected-result.json").write_text("{}\n", encoding="utf-8")
            commit_all(root, "invalid E_s")
            with self.assertRaisesRegex(gate_s.GateSContractError, "extra="):
                gate_s._require_evidence_commit_boundary(root, supply, payloads)


class GateSEvidenceTests(unittest.TestCase):
    def _build(self, root: Path) -> tuple[dict, dict, list[str]]:
        suite, certificate_inventory, certificate_ids = write_evidence_fixture(root)
        suite_payload = gate_s.canonical_json_bytes(suite)
        with (
            mock.patch.object(
                gate_s,
                "_validate_supply_suite_reference",
                return_value=(suite, suite_payload),
            ),
            mock.patch.object(
                gate_s,
                "_certificate_inventory_from_suite",
                return_value=(certificate_inventory, certificate_ids),
            ),
        ):
            evidence = gate_s.build_evidence_manifest(
                repository_root=root,
                implementation_commit="a" * 40,
                supply_pre_result_commit="b" * 40,
                supply_manifest_path=(
                    "data/discovery/wave_69r/structural_supply/inputs/"
                    "suite-manifest.json"
                ),
                primary_ledger_path=(
                    "data/discovery/wave_69r/structural_supply/evidence/primary.jsonl"
                ),
                replay_ledger_path=(
                    "data/discovery/wave_69r/structural_supply/evidence/replay.jsonl"
                ),
                require_git_binding=False,
            )
        return evidence, certificate_inventory, certificate_ids

    def _validate(
        self,
        root: Path,
        evidence: dict,
        certificate_inventory: dict,
        certificate_ids: list[str],
    ) -> dict:
        suite = json.loads(
            (
                root
                / "data/discovery/wave_69r/structural_supply/inputs/suite-manifest.json"
            ).read_text()
        )
        suite_payload = gate_s.canonical_json_bytes(suite)
        with (
            mock.patch.object(
                gate_s,
                "_validate_supply_suite_reference",
                return_value=(suite, suite_payload),
            ),
            mock.patch.object(
                gate_s,
                "_certificate_inventory_from_suite",
                return_value=(certificate_inventory, certificate_ids),
            ),
            mock.patch.object(
                gate_s,
                "evaluate_request_stream",
                side_effect=AssertionError("check-only validation invoked the checker"),
            ),
        ):
            return gate_s.validate_evidence_manifest(
                evidence, repository_root=root, require_git_binding=False
            )

    def test_go_binds_identical_complete_replay_and_certificates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence, inventory, board_ids = self._build(root)
            self.assertEqual(evidence["decision"], "GO")
            self.assertTrue(evidence["executions"]["byte_identical"])
            self.assertEqual(evidence["audit"]["outcome_counts"]["pass"], 4096)
            self.assertEqual(
                evidence["supply_pre_result"]["construction_certificate_inventory"],
                inventory,
            )
            self.assertEqual(self._validate(root, evidence, inventory, board_ids), evidence)

    def test_nonidentical_replay_is_no_go(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            suite, inventory, board_ids = write_evidence_fixture(root)
            replay_path = (
                root
                / "data/discovery/wave_69r/structural_supply/evidence/replay.jsonl"
            )
            replay = gate_s.load_jsonl(replay_path)
            replay[0]["certification"]["decomposition_sha256"] = "7" * 64
            replay_path.write_bytes(gate_s.canonical_jsonl_bytes(replay))
            suite_payload = gate_s.canonical_json_bytes(suite)
            with (
                mock.patch.object(
                    gate_s,
                    "_validate_supply_suite_reference",
                    return_value=(suite, suite_payload),
                ),
                mock.patch.object(
                    gate_s,
                    "_certificate_inventory_from_suite",
                    return_value=(inventory, board_ids),
                ),
            ):
                evidence = gate_s.build_evidence_manifest(
                    repository_root=root,
                    implementation_commit="a" * 40,
                    supply_pre_result_commit="b" * 40,
                    supply_manifest_path=(
                        "data/discovery/wave_69r/structural_supply/inputs/"
                        "suite-manifest.json"
                    ),
                    primary_ledger_path=(
                        "data/discovery/wave_69r/structural_supply/evidence/primary.jsonl"
                    ),
                    replay_ledger_path=(
                        "data/discovery/wave_69r/structural_supply/evidence/replay.jsonl"
                    ),
                    require_git_binding=False,
                )
            self.assertEqual(evidence["decision"], "NO-GO")
            self.assertFalse(evidence["executions"]["byte_identical"])

    def test_check_only_rejects_rewritten_counts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence, inventory, board_ids = self._build(root)
            tampered = deepcopy(evidence)
            tampered["audit"]["outcome_counts"]["pass"] -= 1
            tampered["evidence_id"] = gate_s.evidence_id_for(tampered)
            with self.assertRaisesRegex(gate_s.GateSContractError, "canonical audit"):
                self._validate(root, tampered, inventory, board_ids)

    def test_check_only_rejects_request_artifact_tamper(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence, inventory, board_ids = self._build(root)
            request_path = (
                root
                / "data/discovery/wave_69r/structural_supply/inputs/checker-requests.jsonl"
            )
            request_path.write_bytes(request_path.read_bytes() + b"\n")
            with self.assertRaisesRegex(gate_s.GateSContractError, "sha256"):
                self._validate(root, evidence, inventory, board_ids)

    def test_executor_uses_two_checker_processes_before_writing_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            implementation_root = temporary / "implementation"
            artifact_root = temporary / "artifacts"
            implementation_root.mkdir()
            artifact_root.mkdir()
            suite, inventory, board_ids = write_evidence_fixture(artifact_root)
            evidence_root = (
                artifact_root / "data/discovery/wave_69r/structural_supply/evidence"
            )
            (evidence_root / "primary.jsonl").unlink()
            (evidence_root / "replay.jsonl").unlink()

            implementation_paths = {}
            for name, source in (
                ("CHECKER_MANIFEST", gate_s.CHECKER_MANIFEST),
                ("CHECKER_LOCK", gate_s.CHECKER_LOCK),
                ("CHECKER_SOURCE", gate_s.CHECKER_SOURCE),
                ("CHECKER_WRAPPER", gate_s.CHECKER_WRAPPER),
            ):
                destination = implementation_root / source.relative_to(gate_s.ROOT)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(source.read_bytes())
                implementation_paths[name] = destination

            calls = []

            def fake_evaluate(request_path, result_path, **kwargs):
                calls.append((request_path, result_path, kwargs))
                requests = gate_s.load_jsonl(request_path)
                results = [pass_result(request["board_id"]) for request in requests]
                result_path.write_bytes(gate_s.canonical_jsonl_bytes(results))
                return results

            suite_payload = gate_s.canonical_json_bytes(suite)
            with (
                mock.patch.object(gate_s, "ROOT", implementation_root),
                mock.patch.object(
                    gate_s, "CHECKER_MANIFEST", implementation_paths["CHECKER_MANIFEST"]
                ),
                mock.patch.object(
                    gate_s, "CHECKER_LOCK", implementation_paths["CHECKER_LOCK"]
                ),
                mock.patch.object(
                    gate_s, "CHECKER_SOURCE", implementation_paths["CHECKER_SOURCE"]
                ),
                mock.patch.object(
                    gate_s, "CHECKER_WRAPPER", implementation_paths["CHECKER_WRAPPER"]
                ),
                mock.patch.object(gate_s, "_require_direct_child"),
                mock.patch.object(gate_s, "_require_git_artifact"),
                mock.patch.object(gate_s, "_require_supply_tree_frozen"),
                mock.patch.object(gate_s, "_require_supply_pre_result_boundary"),
                mock.patch.object(gate_s, "_require_evidence_commit_boundary"),
                mock.patch.object(gate_s, "verify_clean_checkout"),
                mock.patch.object(
                    gate_s,
                    "_validate_supply_suite_reference",
                    return_value=(suite, suite_payload),
                ),
                mock.patch.object(
                    gate_s,
                    "_certificate_inventory_from_suite",
                    return_value=(inventory, board_ids),
                ),
                mock.patch.object(
                    gate_s, "evaluate_request_stream", side_effect=fake_evaluate
                ),
            ):
                evidence = gate_s.execute_evidence(
                    artifact_root=artifact_root,
                    implementation_commit="a" * 40,
                    supply_pre_result_commit="b" * 40,
                    supply_manifest_path=(
                        "data/discovery/wave_69r/structural_supply/inputs/"
                        "suite-manifest.json"
                    ),
                    primary_ledger_path=(
                        "data/discovery/wave_69r/structural_supply/evidence/primary.jsonl"
                    ),
                    replay_ledger_path=(
                        "data/discovery/wave_69r/structural_supply/evidence/replay.jsonl"
                    ),
                    evidence_path=(
                        "data/discovery/wave_69r/structural_supply/evidence/evidence.json"
                    ),
                    astralbase_dir=temporary,
                    bitmesh_dir=temporary,
                    thermograph_dir=temporary,
                )
            self.assertEqual(len(calls), 2)
            self.assertNotEqual(calls[0][1], calls[1][1])
            self.assertEqual(evidence["decision"], "GO")
            self.assertTrue((evidence_root / "evidence.json").is_file())


if __name__ == "__main__":
    unittest.main()
