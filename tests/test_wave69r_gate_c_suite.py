from __future__ import annotations

from copy import deepcopy
import importlib.util
import inspect
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SYNTHETIC_COMMIT = "6" * 40


def load_orchestrator():
    spec = importlib.util.spec_from_file_location(
        "wave69r_gate_c_test_orchestrator", ROOT / "engine/orchestrator.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_suite():
    spec = importlib.util.spec_from_file_location(
        "wave69r_gate_c_test_suite",
        ROOT / "python/partizan/wave69r_gate_c_suite.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


orchestrator = load_orchestrator()
suite = load_suite()
discovery = orchestrator.discovery_contract


class Wave69RGateCSuiteTests(unittest.TestCase):
    def test_published_schema_matches_exact_implementation_inventory(self) -> None:
        schema = json.loads(
            (
                ROOT
                / "docs/schemas/partizan-wave69r-gate-c-suite-v0.1.schema.json"
            ).read_text()
        )
        components = schema["properties"]["implementation"]["properties"][
            "components"
        ]
        expected = len(suite.IMPLEMENTATION_COMPONENT_PATHS)
        self.assertEqual(components["minItems"], expected)
        self.assertEqual(components["maxItems"], expected)

    def test_check_only_requires_clean_committed_direct_child_and_exact_diff(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            suite_path = (
                root
                / "data/discovery/wave_69r/calibration/inputs/suite-manifest.json"
            )
            suite_path.parent.mkdir(parents=True)
            manifest = {
                "temporal_boundary": {"pre_result_parent_commit": "e" * 40}
            }
            payload = suite.canonical_bytes(manifest)
            suite_path.write_bytes(payload)
            with (
                mock.patch.object(suite, "_load_json", return_value=(manifest, payload)),
                mock.patch.object(suite, "validate_suite_manifest") as validate,
                mock.patch.object(suite, "clean_commit", return_value="c" * 40) as clean,
                mock.patch.object(suite, "_require_direct_child") as direct,
                mock.patch.object(suite, "_require_exact_commit_inventory") as inventory,
                mock.patch.object(suite, "_git", return_value=payload),
            ):
                self.assertIs(suite.check_only(root=root, suite_path=suite_path), manifest)
            validate.assert_called_once()
            self.assertEqual(clean.call_count, 2)
            direct.assert_called_once_with(
                root.resolve(), "c" * 40, "e" * 40, "Gate C pre-result P_c"
            )
            inventory.assert_called_once()

    def test_atomic_freeze_removes_staging_after_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = root / "data/discovery/wave_69r/calibration/inputs"
            with mock.patch.object(
                suite,
                "_freeze_gate_c_suite_staged",
                side_effect=suite.GateCSuiteError("synthetic failure"),
            ):
                with self.assertRaisesRegex(suite.GateCSuiteError, "synthetic failure"):
                    suite.freeze_gate_c_suite(
                        artifact_root=root,
                        implementation_root=root,
                        registry_path=root / "registry.json",
                        preregistration_path=root / "prereg.md",
                        gate_s_evidence_path=root / "evidence.json",
                        output_root=output,
                        astralbase_dir=root,
                        bitmesh_dir=root,
                        thermograph_dir=root,
                    )
            self.assertFalse(output.exists())
            self.assertEqual(list(output.parent.glob("wave69r-gate-c-freeze-*")), [])

    def synthetic_bundle(self, size: int = 8):
        target = discovery.load_json(
            ROOT / "tests/fixtures/discovery/target.valid.json"
        )
        target["search_limits"]["max_pool_size"] = size
        target["target_id"] = discovery.target_id_for(target)
        boards = orchestrator.generate_discovery_board_states_v2(
            pool_size=size,
            random_seed=990011,
            generator_code_commit=SYNTHETIC_COMMIT,
        )
        proposals = discovery.project_board_stream_to_proposals(target, boards)
        return target, boards, proposals

    def test_seed_helpers_are_fully_specified_without_locked_targets(self) -> None:
        target_id = "target-sha256:" + "a" * 64
        pool_id = "pool-sha256:" + "b" * 64
        first = suite.calibration_seed(
            target_id, domain=suite.SYNTHETIC_SEED_DOMAIN
        )
        second = suite.calibration_seed(
            target_id, domain=suite.SYNTHETIC_SEED_DOMAIN
        )
        self.assertEqual(first, second)
        self.assertNotEqual(first, suite.calibration_seed(target_id))
        self.assertNotEqual(
            suite.random_order_seed(
                pool_id, 0, domain=suite.SYNTHETIC_SEED_DOMAIN
            ),
            suite.random_order_seed(
                pool_id, 1, domain=suite.SYNTHETIC_SEED_DOMAIN
            ),
        )

    def test_projection_internal_is_target_limited_and_byte_deterministic(self) -> None:
        target, boards, expected = self.synthetic_bundle()
        catalog_path = (
            ROOT / orchestrator.DISCOVERY_POOL_GENERATOR_CATALOG_PATH_V2
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target_path = root / "target.json"
            boards_path = root / "boards.jsonl"
            target_path.write_bytes(discovery.canonical_json_bytes(target))
            boards_path.write_bytes(discovery.canonical_jsonl_bytes(boards))
            outputs = []
            for index in range(2):
                proposal_path = root / f"proposals-{index}.jsonl"
                certificate_path = root / f"certificates-{index}.jsonl"
                suite.project_internal(
                    target_path=target_path,
                    board_stream_path=boards_path,
                    catalog_path=catalog_path,
                    proposals_path=proposal_path,
                    certificates_path=certificate_path,
                )
                outputs.append(
                    (proposal_path.read_bytes(), certificate_path.read_bytes())
                )
            self.assertEqual(outputs[0], outputs[1])
            self.assertEqual(
                discovery.load_jsonl(root / "proposals-0.jsonl"), expected
            )
            self.assertNotIn(b"identity_sha256", outputs[0][1])
            self.assertNotIn(b"target_id", outputs[0][1])

    def test_fresh_random_and_unchanged_heuristic_policy_contract(self) -> None:
        target, _, proposals = self.synthetic_bundle()
        pool = {"pool_id": "pool-sha256:" + "c" * 64}
        artifact = suite.build_policy_orders(
            target,
            pool,
            proposals,
            seed_domain=suite.SYNTHETIC_SEED_DOMAIN,
            replicates=7,
        )
        suite.validate_policy_orders(
            artifact, target, pool, proposals, production=False
        )
        self.assertEqual(artifact["random_policy"]["replicate_count"], 7)
        self.assertEqual(
            artifact["random_policy"]["permutation_algorithm"],
            "splitmix64_rejection_fisher_yates_v1",
        )
        self.assertEqual(
            artifact["heuristic_policy"]["formula"],
            suite.baselines.HEURISTIC_FORMULA,
        )
        tampered = deepcopy(artifact)
        tampered["random_policy"]["orders"][0]["seed"] += 1
        tampered["policy_orders_id"] = suite.policy_orders_id_for(tampered)
        with self.assertRaisesRegex(suite.GateCSuiteError, "random order"):
            suite.validate_policy_orders(
                tampered, target, pool, proposals, production=False
            )

    def test_production_policy_validator_recomputes_all_1000_r_domain_orders(self) -> None:
        target, _, proposals = self.synthetic_bundle()
        pool = {"pool_id": "pool-sha256:" + "9" * 64}
        artifact = suite.build_policy_orders(target, pool, proposals)
        self.assertEqual(len(artifact["random_policy"]["orders"]), 1000)
        suite.validate_policy_orders(artifact, target, pool, proposals)
        tampered = deepcopy(artifact)
        tampered["random_policy"]["orders"][999]["seed"] += 1
        tampered["random_policy"]["orders"][999]["order_id"] = suite._identity(
            "policy-order",
            tampered["random_policy"]["orders"][999],
            "order_id",
        )
        tampered["policy_orders_id"] = suite.policy_orders_id_for(tampered)
        with self.assertRaisesRegex(suite.GateCSuiteError, r"random order\[999\]"):
            suite.validate_policy_orders(tampered, target, pool, proposals)

    def test_gate_s_no_go_and_inexact_counts_keep_gate_c_closed(self) -> None:
        sources = {
            "partizan": SYNTHETIC_COMMIT,
            **suite.PINNED_EXTERNAL_COMMITS,
        }
        audit = {
            "schema_version": suite.GATE_S_EVIDENCE_SCHEMA_VERSION,
            "evidence_id": "evidence-sha256:" + "0" * 64,
            "audit_contract": suite.GATE_S_AUDIT_CONTRACT,
            "decision": "NO-GO",
            "implementation_commit": SYNTHETIC_COMMIT,
            "supply_pre_result": {},
            "source_repositories": sources,
            "checker": {},
            "executions": {},
            "audit": {},
        }
        audit["evidence_id"] = suite._identity("evidence", audit, "evidence_id")
        with self.assertRaisesRegex(suite.GateCSuiteError, "remains closed"):
            suite.validate_gate_s_go(
                audit,
                implementation_commit=SYNTHETIC_COMMIT,
                source_repositories=sources,
                evidence_commit="e" * 40,
            )

    def test_gate_s_exact_go_contract_and_rehashed_count_tamper(self) -> None:
        sources = {"partizan": SYNTHETIC_COMMIT, **suite.PINNED_EXTERNAL_COMMITS}
        file_ref = {"path": "evidence/file.json", "sha256": "a" * 64}
        evidence = {
            "schema_version": suite.GATE_S_EVIDENCE_SCHEMA_VERSION,
            "evidence_id": "evidence-sha256:" + "0" * 64,
            "audit_contract": suite.GATE_S_AUDIT_CONTRACT,
            "decision": "GO",
            "implementation_commit": SYNTHETIC_COMMIT,
            "supply_pre_result": {
                "commit": "d" * 40,
                "manifest": {
                    **file_ref,
                    "schema_version": "partizan.wave69r_structural_supply_suite.v0.1",
                },
                "checker_request_ref": {
                    **file_ref,
                    "schema_version": "partizan.wave69r_structural_supply_request.v0.1",
                    "row_count": 4096,
                },
                "construction_certificate_inventory": {
                    "schema_version": "partizan.structural_construction_certificate.v0.1",
                    "shard_count": 4,
                    "row_count": 4096,
                    "references_sha256": "b" * 64,
                    "canonical_jsonl_sha256": "c" * 64,
                },
            },
            "source_repositories": sources,
            "checker": {
                "name": "partizan_gate_s_checker",
                "version": "0.1.0",
                "manifest": file_ref,
                "lock": file_ref,
                "source": file_ref,
                "wrapper": file_ref,
                "bitmesh_crate_version": "0.1.0",
                "bitmesh_source_commit": suite.PINNED_EXTERNAL_COMMITS["bitmesh"],
                "proof_api": "bitmesh:conservative_legal_independence:v0",
            },
            "executions": {
                "mode": "separate_checker_processes_v1",
                "run_count": 2,
                "primary_ledger": {
                    **file_ref,
                    "schema_version": "partizan.wave69r_structural_supply_result.v0.1",
                    "row_count": 4096,
                },
                "replay_ledger": {
                    **file_ref,
                    "schema_version": "partizan.wave69r_structural_supply_result.v0.1",
                    "row_count": 4096,
                },
                "byte_identical": True,
            },
            "audit": {
                "expected_row_count": 4096,
                "observed_row_count": 4096,
                "construction_certificate_count": 4096,
                "outcome_counts": {"pass": 4096, "fail": 0, "error": 0},
                "predicate_counts": {
                    name: {"pass": 4096, "fail": 0, "not_evaluated": 0}
                    for name in (
                        "frozen_barrier",
                        "non_capturable_barrier",
                        "strict_exactly_two_components",
                        "no_cross_component_entry",
                    )
                },
                "failure_code_counts": [],
                "internal_error_count": 0,
                "certificate_disagreement_count": 0,
                "complete_ledger": True,
                "request_result_binding": True,
                "forbidden_field_scan": True,
            },
        }
        evidence["evidence_id"] = suite._identity(
            "evidence", evidence, "evidence_id"
        )
        suite.validate_gate_s_go(
            evidence,
            implementation_commit=SYNTHETIC_COMMIT,
            source_repositories=sources,
            evidence_commit="e" * 40,
        )
        tampered = deepcopy(evidence)
        tampered["audit"]["observed_row_count"] = 4095
        tampered["evidence_id"] = suite._identity(
            "evidence", tampered, "evidence_id"
        )
        with self.assertRaisesRegex(suite.GateCSuiteError, "4096/4096"):
            suite.validate_gate_s_go(
                tampered,
                implementation_commit=SYNTHETIC_COMMIT,
                source_repositories=sources,
                evidence_commit="e" * 40,
            )

    def test_public_interface_has_no_verifier_and_never_uses_legacy_pool_v2(self) -> None:
        parser = suite.build_parser()
        help_text = parser.format_help().lower()
        self.assertNotIn("discovery-verify", help_text)
        source = inspect.getsource(suite._freeze_gate_c_suite_staged)
        self.assertIn("discovery-generate-board-stream-v2", source)
        self.assertNotIn("discovery-generate-pool-v2", source)
        self.assertNotIn("discovery-verify", source)
        self.assertNotIn("astralbase_request", source)
        wrapper_source = inspect.getsource(suite.freeze_gate_c_suite)
        self.assertIn("os.replace", wrapper_source)
        self.assertIn("shutil.rmtree", wrapper_source)
        check_source = inspect.getsource(suite.check_only)
        self.assertNotIn("subprocess", check_source)

    def test_schemas_are_strict_and_wave69r_specific(self) -> None:
        for name, version in (
            (
                "partizan-wave69r-gate-c-suite-v0.1.schema.json",
                suite.SCHEMA_VERSION,
            ),
            (
                "partizan-wave69r-policy-orders-v0.1.schema.json",
                suite.POLICY_SCHEMA_VERSION,
            ),
        ):
            schema = json.loads((ROOT / "docs/schemas" / name).read_text())
            self.assertIs(schema["additionalProperties"], False)
            self.assertEqual(schema["properties"]["schema_version"]["const"], version)


if __name__ == "__main__":
    unittest.main()
