from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "partizan_discovery_contract",
    ROOT / "python" / "partizan" / "discovery.py",
)
discovery = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(discovery)

FIXTURES = ROOT / "tests" / "fixtures" / "discovery"
TARGET_PATH = FIXTURES / "target.valid.json"
PROPOSALS_PATH = FIXTURES / "proposals.valid.jsonl"
RESULTS_PATH = FIXTURES / "verifier-results.valid.jsonl"
POOL_PATH = FIXTURES / "candidate-pool.valid.manifest.json"
RUN_PATH = FIXTURES / "run.valid.json"


class DiscoveryContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.target = discovery.load_json(TARGET_PATH)
        self.proposals = discovery.load_jsonl(PROPOSALS_PATH)
        self.results = discovery.load_jsonl(RESULTS_PATH)
        self.pool = discovery.load_json(POOL_PATH)
        self.run = discovery.load_json(RUN_PATH)

    def test_four_outcome_bundle_is_valid_and_canonical(self) -> None:
        self.assertEqual(
            discovery.validate_discovery_bundle(
                TARGET_PATH, PROPOSALS_PATH, RESULTS_PATH, POOL_PATH, RUN_PATH
            ),
            [],
        )
        self.assertEqual(len(self.proposals), 4)
        self.assertEqual(
            {result["outcome"] for result in self.results},
            {"certified_target", "certified_other", "rejected", "error"},
        )
        self.assertEqual(
            PROPOSALS_PATH.read_bytes(),
            discovery.canonical_jsonl_bytes(self.proposals),
        )

    def test_target_is_explicitly_bounded_and_not_arbitrary_cgt_equality(self) -> None:
        self.assertEqual(
            self.target["target"]["kind"], "bounded_structural_game_form"
        )
        self.assertEqual(
            self.target["target"]["identity_contract"],
            "thermograph_structural_tree_v1",
        )
        self.assertEqual(
            self.target["target"]["equality_scope"],
            "structural_tree_identity_only_not_arbitrary_cgt_equivalence",
        )
        self.assertEqual(self.target["target"]["value_rule"], discovery.VALUE_RULE)
        self.assertEqual(
            self.target["ranker_view"]["value_rule"], discovery.VALUE_RULE
        )
        self.assertGreater(
            self.target["search_limits"]["max_recursive_nodes_per_candidate"], 0
        )
        self.assertEqual(
            self.target["position_constraints"]["legality_contract"],
            "board_syntax_only",
        )
        self.assertNotIn("require_legal_position", self.target["position_constraints"])

    def test_typed_ids_bind_semantic_payloads(self) -> None:
        self.assertEqual(self.target["target_id"], discovery.target_id_for(self.target))
        for proposal in self.proposals:
            self.assertEqual(
                proposal["proposal_id"], discovery.proposal_id_for(proposal)
            )
            self.assertEqual(
                proposal["candidate_key"],
                discovery.candidate_key_for(
                    proposal["domain"], proposal["position"]
                ),
            )
        for result in self.results:
            self.assertEqual(
                result["result_id"], discovery.verifier_result_id_for(result)
            )
        self.assertEqual(self.pool["pool_id"], discovery.candidate_pool_id_for(self.pool))
        self.assertEqual(self.run["run_id"], discovery.discovery_run_id_for(self.run))

    def test_target_id_binds_the_recursive_node_budget(self) -> None:
        mutated = deepcopy(self.target)
        mutated["search_limits"]["max_recursive_nodes_per_candidate"] += 1
        self.assertNotEqual(
            discovery.target_id_for(mutated), self.target["target_id"]
        )
        errors = discovery.validate_target_spec(mutated)
        self.assertTrue(any("target_id" in error for error in errors))

    def test_same_candidate_from_another_generator_has_a_new_proposal_id(self) -> None:
        original = self.proposals[0]
        changed = deepcopy(original)
        changed["generator"]["operator"] = "another_preverification_operator"
        changed["proposal_id"] = discovery.proposal_id_for(changed)
        self.assertEqual(changed["candidate_key"], original["candidate_key"])
        self.assertNotEqual(changed["proposal_id"], original["proposal_id"])
        self.assertEqual(
            discovery.validate_candidate_proposal(changed, self.target), []
        )

    def test_ranker_projection_is_an_allowlist_not_a_redaction(self) -> None:
        ranker_input = discovery.build_ranker_input(self.target, self.proposals[0])
        self.assertEqual(
            set(ranker_input), {"schema_version", "target", "candidate"}
        )
        self.assertEqual(
            set(ranker_input["candidate"]), {"position", "proposal_features"}
        )
        serialized = discovery.canonical_json_bytes(ranker_input).decode("ascii")
        for forbidden in (
            '"certificate"',
            '"exact"',
            '"label"',
            '"outcome"',
            '"rejected"',
            '"result"',
            '"verifier"',
        ):
            self.assertNotIn(forbidden, serialized)

    def test_proposal_rejects_verifier_derived_feature_keys(self) -> None:
        for key in (
            "result_value_digest",
            "certificate_digest",
            "verifier_status",
            "solver_nodes",
            "target_match",
            "expanded_nodes",
        ):
            with self.subTest(key=key):
                leaked = deepcopy(self.proposals[0])
                leaked["proposal_features"]["categorical"][key] = "leak"
                leaked["proposal_id"] = discovery.proposal_id_for(leaked)
                errors = discovery.validate_candidate_proposal(leaked, self.target)
                self.assertTrue(
                    any(
                        "verifier-derived feature key is forbidden" in error
                        for error in errors
                    )
                )

    def test_raw_floats_fail_even_when_other_fields_are_valid(self) -> None:
        floated = deepcopy(self.target)
        floated["search_limits"]["max_pool_size"] = 4.0
        errors = discovery.validate_target_spec(floated)
        self.assertTrue(any("raw JSON floats are forbidden" in error for error in errors))
        with self.assertRaisesRegex(ValueError, "raw JSON floats are forbidden"):
            discovery.canonical_json_bytes(floated)

    def test_workspace_commits_fail(self) -> None:
        target = deepcopy(self.target)
        target["provenance"]["source_commit"] = "workspace"
        self.assertTrue(
            any("workspace" in error for error in discovery.validate_target_spec(target))
        )
        proposal = deepcopy(self.proposals[0])
        proposal["generator"]["code_commit"] = "workspace"
        proposal["proposal_id"] = discovery.proposal_id_for(proposal)
        self.assertTrue(
            any(
                "workspace" in error
                for error in discovery.validate_candidate_proposal(
                    proposal, self.target
                )
            )
        )

    def test_result_outcome_cross_checks_are_enforced(self) -> None:
        corrupted = deepcopy(self.results[0])
        corrupted["target_comparison"]["matches"] = False
        corrupted["result_id"] = discovery.verifier_result_id_for(corrupted)
        errors = discovery.validate_verifier_result(
            corrupted, self.target, self.proposals[0]
        )
        self.assertTrue(any("matching identities" in error for error in errors))

    def test_result_evidence_is_complete_only_for_certified_rows(self) -> None:
        for result in self.results[:2]:
            evidence = result["evidence"]
            self.assertIsNotNone(evidence["certificate_digest"])
            self.assertIsNotNone(evidence["decomposition_digest"])
            self.assertIsNotNone(evidence["composition_digest"])
            self.assertEqual(
                evidence["observed_structural_sha256"],
                result["target_comparison"]["observed_identity_sha256"],
            )
            self.assertIsInstance(evidence["recursive_nodes"], int)
        for result in self.results[2:]:
            evidence = result["evidence"]
            for key in (
                "certificate_digest",
                "decomposition_digest",
                "composition_digest",
                "observed_structural_sha256",
                "recursive_nodes",
            ):
                self.assertIsNone(evidence[key])

        corrupted = deepcopy(self.results[2])
        corrupted["evidence"]["decomposition_digest"] = "a" * 64
        corrupted["result_id"] = discovery.verifier_result_id_for(corrupted)
        errors = discovery.validate_verifier_result(
            corrupted, self.target, self.proposals[2]
        )
        self.assertTrue(any("cannot claim structural evidence" in e for e in errors))

    def test_verifier_io_hashes_and_gate_evidence_are_recomputed(self) -> None:
        cases = []

        bad_response_hash = deepcopy(self.results[0])
        bad_response_hash["verifier_io"]["response"]["actual"][
            "legacy_digest"
        ] = "tampered"
        cases.append((bad_response_hash, "response_sha256"))

        bad_semantics = deepcopy(self.results[0])
        bad_semantics["verifier_io"]["response"]["actual"][
            "semantics"
        ] = "arbitrary_cgt_equivalence"
        bad_semantics["verifier_io"]["response_sha256"] = discovery.sha256_hex(
            discovery.canonical_json_bytes(bad_semantics["verifier_io"]["response"])
        )
        cases.append((bad_semantics, "actual.semantics"))

        bad_gate = deepcopy(self.results[0])
        bad_gate["gates"][0]["evidence_sha256"] = "0" * 64
        cases.append((bad_gate, "recomputed response evidence"))

        bad_config = deepcopy(self.results[0])
        bad_config["verifier"]["config_sha256"] = "0" * 64
        cases.append((bad_config, "value_rule and node_budget"))

        bad_request = deepcopy(self.results[0])
        bad_request["verifier_io"]["request"]["node_budget"] += 1
        bad_request["verifier_io"]["request_sha256"] = discovery.sha256_hex(
            discovery.canonical_json_bytes(bad_request["verifier_io"]["request"])
        )
        cases.append((bad_request, "does not match target, proposal, and node budget"))

        for corrupted, expected_error in cases:
            with self.subTest(expected_error=expected_error):
                corrupted["result_id"] = discovery.verifier_result_id_for(corrupted)
                errors = discovery.validate_verifier_result(
                    corrupted, self.target, self.proposals[0]
                )
                self.assertTrue(
                    any(expected_error in error for error in errors), errors
                )

    def test_failure_reasons_select_the_first_gate_and_stop_later_gates(self) -> None:
        cases = (
            ("rejected", "unsupported_domain", ["failed", "not_run", "not_run", "not_run"]),
            ("rejected", "invalid_fen", ["passed", "failed", "not_run", "not_run"]),
            ("rejected", "no_strict_decomposition", ["passed", "passed", "failed", "not_run"]),
            ("internal_error", "unsupported_domain", ["error", "not_run", "not_run", "not_run"]),
            ("internal_error", "invalid_fen", ["passed", "error", "not_run", "not_run"]),
            ("internal_error", "solver_panic", ["passed", "passed", "error", "not_run"]),
        )
        for status, reason, expected_statuses in cases:
            with self.subTest(status=status, reason=reason):
                response = {
                    "request_id": self.proposals[0]["proposal_id"],
                    "status": status,
                    "reason_code": reason,
                    "reason": "fixture",
                }
                gates = discovery.verifier_gate_rows_for(response, self.proposals[0])
                self.assertEqual(
                    [gate["status"] for gate in gates], expected_statuses
                )
                failing_index = next(
                    index
                    for index, gate_status in enumerate(expected_statuses)
                    if gate_status in {"failed", "error"}
                )
                self.assertEqual(gates[failing_index]["reason_codes"], [reason])
                self.assertTrue(
                    all(
                        gate["status"] == "not_run"
                        for gate in gates[failing_index + 1 :]
                    )
                )

    def test_pool_and_run_recompute_counts_and_order(self) -> None:
        pool = deepcopy(self.pool)
        pool["candidate_artifact"]["row_count"] = 3
        pool["pool_id"] = discovery.candidate_pool_id_for(pool)
        self.assertTrue(
            any(
                "row_count" in error
                for error in discovery.validate_candidate_pool_manifest(
                    pool, self.target, self.proposals, PROPOSALS_PATH
                )
            )
        )
        run = deepcopy(self.run)
        run["summary"]["unique_certified_targets"] = 2
        run["run_id"] = discovery.discovery_run_id_for(run)
        self.assertTrue(
            any(
                "recomputed outcomes" in error
                for error in discovery.validate_discovery_run(
                    run, self.target, self.pool, self.proposals, self.results
                )
            )
        )

    def test_public_schemas_are_json_and_strict_at_the_root(self) -> None:
        schema_names = (
            "partizan-discovery-target-v0.1.schema.json",
            "partizan-candidate-proposal-v0.1.schema.json",
            "partizan-verifier-result-v0.1.schema.json",
            "partizan-candidate-pool-manifest-v0.1.schema.json",
            "partizan-candidate-pool-manifest-v0.2.schema.json",
            "partizan-candidate-generation-receipt-v0.1.schema.json",
            "partizan-discovery-run-v0.1.schema.json",
        )
        for name in schema_names:
            schema = json.loads((ROOT / "docs" / "schemas" / name).read_text())
            self.assertIs(schema["additionalProperties"], False, name)


if __name__ == "__main__":
    unittest.main()
